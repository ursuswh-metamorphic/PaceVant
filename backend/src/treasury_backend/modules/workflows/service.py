import json
from secrets import randbelow
from time import time
from uuid import uuid4

import httpx
from eth_keys import keys
from eth_keys.constants import SECPK1_N

from treasury_backend.config.control import FIXTURES, Settings
from treasury_backend.core.errors import ControlError
from treasury_backend.core.models import Mandate
from treasury_backend.modules import decision as sde
from treasury_backend.modules import planning as planner
from treasury_backend.modules import portfolio as portfolio
from treasury_backend.modules.oracle import build_provider
from treasury_backend.modules.oracle.fuji.fuji_data import LFJ_TEST_USDC
from treasury_backend.modules.persistence import Store
from treasury_backend.modules.signing import Attestor
from treasury_backend.modules.workflows.client import ExecutionClient, RestExecutionClient
from treasury_backend.modules.workflows.evidence import evidence_issues, json_object
from treasury_backend.modules.workflows.fuji import FujiVerifier
from treasury_backend.modules.workflows.mock import MockExecutionClient

from .authorization import AuthorizationPipeline
from .evaluation import EvaluationPipeline
from .monitoring import OutcomeMonitor


def utc_now() -> int:
    return int(time())


class ControlPlane(EvaluationPipeline, AuthorizationPipeline, OutcomeMonitor):
    def __init__(self, settings: Settings, clock=utc_now, client_factory=None):
        self.settings = settings
        self.client_factory = client_factory
        self.clock = clock
        self.store = Store(settings.db)
        self.planner = planner.GoalPlanner(settings.planning, settings.db.parent)
        if settings.mode == "MOCK":
            key_bytes = (1 + randbelow(SECPK1_N - 1)).to_bytes(32, "big")
        else:
            key_bytes = bytes.fromhex(settings.attestor_key.removeprefix("0x"))
            if len(key_bytes) != 32 or not 0 < int.from_bytes(key_bytes, "big") < SECPK1_N:
                raise RuntimeError("PACEVANT_ATTESTOR_KEY must be a valid secp256k1 private key")
        key = keys.PrivateKey(key_bytes)
        self.attestor = Attestor(self.store, key, clock)
        self.mock_clients = {}
        self.http = None
        self.fuji_http = None
        if settings.mode != "MOCK" and client_factory is None:
            self.http = httpx.Client(
                base_url=settings.execution_url,
                headers={"X-API-Key": settings.execution_token},
                timeout=httpx.Timeout(15, connect=3),
                trust_env=False,
                follow_redirects=False,
            )
        if settings.mode == "FUJI":
            self.fuji_http = httpx.Client(timeout=3, trust_env=False, follow_redirects=False)

    def close(self):
        self.planner.close()
        if self.http:
            self.http.close()
        if self.fuji_http:
            self.fuji_http.close()

    def verify_evidence(self, client, built, evidence, context):
        issues = evidence_issues(client, self.settings.mode, built, evidence, context, self.clock())
        if not issues and self.fuji_http is not None:
            try:
                FujiVerifier(self.fuji_http, self.settings.fuji_verification_rpc).verify(
                    context, self.clock()
                )
            except ControlError as error:
                issues.append(error.code)
        return issues

    def mandate(self, mandate_id: str | None = None) -> Mandate:
        try:
            mandate = Mandate.model_validate(json_object(self.settings.mandate_file.read_bytes()))
        except (ValueError, OSError):
            raise ControlError("MANDATE_UNAVAILABLE", 503) from None
        if mandate_id is not None and mandate.mandate_id != mandate_id:
            raise ControlError("MANDATE_NOT_FOUND", 404)
        if (
            not mandate.required_stress
            or mandate.token_in == mandate.token_out
            or min(
                int(mandate.max_usdc_per_swap_base_units),
                int(mandate.max_usdc_spend_per_day_base_units),
            )
            <= 0
        ):
            raise ControlError("INVALID_MANDATE", 503)
        return mandate

    @staticmethod
    def fixture(scenario):
        return json.loads((FIXTURES / f"{scenario or 'normal_swap'}.json").read_text("utf-8"))

    def client(self, workflow_id: str, mandate: Mandate, scenario: str | None = None):
        if self.client_factory is not None:
            return self.client_factory(workflow_id, self.settings, self.store)
        if self.http:
            return RestExecutionClient(self.http, workflow_id, self.settings, self.store)
        if workflow_id in self.mock_clients:
            return self.mock_clients[workflow_id]
        return MockExecutionClient(
            mandate, self.attestor.address, self.fixture(scenario), self.clock
        )

    def price(self, client: ExecutionClient, block="latest"):
        if isinstance(client, MockExecutionClient):
            return client.price()
        from treasury_backend.modules.oracle.chainlink import ChainlinkPriceProvider
        from treasury_contracts.oracle import SOURCE_HASH

        mandate = self.mandate()
        if mandate.proof_policy and mandate.proof_policy.oracle_source_hash == SOURCE_HASH:
            return ChainlinkPriceProvider(self.settings.chain_rpc_url, mandate.vault_address).read(block)
        return build_provider(self.settings.oracle_file).read()

    @staticmethod
    def require_priced_assets(mandate):
        if mandate.chain_id == 43113 and LFJ_TEST_USDC.lower() in {
            mandate.token_in.lower(),
            mandate.token_out.lower(),
        }:
            raise ControlError("ORACLE_TOKEN_IDENTITY_MISMATCH")

    def standalone_proposal(self, goal, mandate_id):
        mandate = self.mandate(mandate_id)
        plan = self.planner.parse(goal)
        client = self.client(f"propose_{uuid4().hex}", mandate)
        context = client.context()
        issues = portfolio.policy_issues(mandate, context, self.clock())
        if issues:
            raise ControlError(issues[0])
        amount = plan.amount
        if not amount:
            raise ControlError("TASK_UNCERTAIN", 422)
        return planner.propose(
            mandate,
            amount,
            self._deadline(mandate, self.clock(), context),
            reverse=plan.reverse,
        )

    @staticmethod
    def _deadline(mandate, now, context=None):
        ttl = min(300, context.max_approval_ttl) if context is not None else sde.TTL
        deadline = min(now + ttl, mandate.expires_at, (now // 86400 + 1) * 86400 - 1)
        if context is not None:
            deadline = min(
                deadline,
                context.block_timestamp + ttl,
                context.policy_expires_at or mandate.expires_at,
            )
        return deadline

    def treasury(self, request_id):
        mandate = self.mandate()
        client = self.client(request_id, mandate)
        balances = client.balances()
        context = client.context()
        issues = portfolio.policy_issues(mandate, context, self.clock())
        if (balances.chain_id, balances.vault_address, balances.policy_hash) != (
            mandate.chain_id,
            mandate.vault_address,
            mandate.policy_hash,
        ):
            issues.append("HASH_MISMATCH")
        snapshot = None
        try:
            self.require_priced_assets(mandate)
            price = self.price(client)
            if not portfolio.price_fresh(price, self.clock(), portfolio.state_age(context)):
                issues.append("STALE_PRICE")
            if (price.chain_id, price.vault_address) != (mandate.chain_id, mandate.vault_address):
                issues.append("UNVERIFIED_PRICE")
            else:
                snapshot = portfolio.snapshot(balances, price, self.store.history_version())
        except ControlError as error:
            issues.append(error.code)
        return {
            "mode": self.settings.mode,
            "mandate": mandate,
            "proof_session": context.proof_session,
            "portfolio": snapshot,
            "chain_balances": balances,
            "issues": list(dict.fromkeys(issues)),
        }

    def run(self, payload):
        mandate = self.mandate(payload.mandate_id)
        if self.settings.mode != "MOCK" and payload.scenario is not None:
            raise ControlError("MOCK_SCENARIO_FORBIDDEN", 422)
        workflow_id = f"workflow_{uuid4().hex}"
        scenario = payload.scenario
        client = self.client(workflow_id, mandate, scenario)
        if isinstance(client, MockExecutionClient):
            self.mock_clients[workflow_id] = client
        self.store.start(
            workflow_id,
            {
                "mode": self.settings.mode,
                "scenario": scenario,
                "mandate_id": mandate.mandate_id,
                **self.planner.metadata,
            },
        )
        try:
            self._run_attempts(workflow_id, mandate, client, payload.goal)
        except ControlError as error:
            trace = getattr(self.planner.provider, "last_attempts", [])
            self.store.event(workflow_id, "ESCALATED", self.clock(), reason_codes=[error.code],
                             **({"provider_attempts": list(trace)} if trace else {}))
        finally:
            status = self.store.workflow(workflow_id)["status"]
            if status not in {"SUBMITTING", "SUBMITTED"}:
                self.mock_clients.pop(workflow_id, None)
        return {"workflow_id": workflow_id, "status": status}
