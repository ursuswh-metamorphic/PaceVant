import json
from secrets import randbelow
from time import monotonic, time
from uuid import uuid4

import httpx
from eth_keys import keys
from eth_keys.constants import SECPK1_N

from treasury_backend.config.control import FIXTURES, Settings
from treasury_backend.core.errors import ControlError
from treasury_backend.core.models import Alignment, Mandate
from treasury_backend.modules import alignment
from treasury_backend.modules import decision as sde
from treasury_backend.modules import planning as planner
from treasury_backend.modules import portfolio as portfolio
from treasury_backend.modules.alignment.engine import TaskShield
from treasury_backend.modules.alignment.runtime import ShieldBlocked, ShieldRuntime
from treasury_backend.modules.alignment.types import TaskUpdate
from treasury_backend.modules.monitoring.service import OutcomeMonitor
from treasury_backend.modules.oracle import build_provider
from treasury_backend.modules.oracle.fuji.fuji_data import LFJ_TEST_USDC
from treasury_backend.modules.persistence import Store
from treasury_backend.modules.signing import Attestor
from treasury_backend.modules.temporal import storage as temporal_storage
from treasury_backend.modules.temporal.service import TemporalService
from treasury_backend.modules.workflows.client import ExecutionClient, RestExecutionClient
from treasury_backend.modules.workflows.evidence import evidence_issues, json_object
from treasury_backend.modules.workflows.fuji import FujiVerifier
from treasury_backend.modules.workflows.mock import MockExecutionClient

from .authorization import AuthorizationPipeline
from .evaluation import EvaluationPipeline
from .monitoring import WorkflowMonitor


def utc_now() -> int:
    return int(time())


class ControlPlane(EvaluationPipeline, AuthorizationPipeline, WorkflowMonitor):
    def __init__(self, settings: Settings, clock=utc_now, client_factory=None, shield_provider=None):
        self.settings = settings
        self.client_factory = client_factory
        self.clock = clock
        self.store = Store(settings.db)
        self.planner = planner.GoalPlanner(settings.planning, settings.db.parent)
        self.shield = TaskShield(self.store, settings.shield, provider=shield_provider, clock=clock)
        self.temporal = TemporalService(self.store, self.shield, settings.mode, clock)
        self.shield_runtimes = {}
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
        self.monitor = OutcomeMonitor(self.store, settings.mode, self._monitor_client, clock)
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

    @property
    def shield_version(self):
        if self.settings.shield.algorithm == "hybrid-v1":
            return "task-shield-hybrid-v1"
        return ("task-shield-wallet-pipeline-v1" if self.settings.shield.mode == "wallet_pipeline"
                else "task-shield-acl2025-v1")

    def close(self):
        self.planner.close()
        self.shield.close()
        if self.http:
            self.http.close()
        if self.fuji_http:
            self.fuji_http.close()

    def verify_evidence(self, client, built, evidence, context, workflow_id=None):
        gate = (
            (
                lambda ref, read: self._tool(
                    workflow_id,
                    "read_simulation_artifact",
                    {"reference": ref},
                    read,
                    deadline=built.deadline,
                )
            )
            if workflow_id in self.shield_runtimes
            else None
        )
        issues = evidence_issues(
            client, self.settings.mode, built, evidence, context, self.clock(), artifact_gate=gate
        )
        runtime = self.shield_runtimes.get(workflow_id)
        if runtime and runtime.last_feedback and self.settings.shield.mode == "wallet_hardened":
            issues.append(runtime.last_feedback.code)
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
            client = self.client_factory(workflow_id, self.settings, self.store)
            if self.settings.mode != "MOCK" and (
                isinstance(client, MockExecutionClient) or getattr(client, "fixture_mode", False)
            ):
                raise ControlError("LIVE_FIXTURE_CLIENT_FORBIDDEN", 503)
            return client
        if self.http:
            return RestExecutionClient(self.http, workflow_id, self.settings, self.store)
        if self.settings.mode != "MOCK":
            raise ControlError("EXECUTION_CLIENT_UNAVAILABLE", 503)
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
            if context.proof_session is not None:
                deadline = min(deadline, context.proof_session.expires_at)
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
        observation = self.observe(client, mandate, balances, context)
        snapshot = None
        try:
            self.require_priced_assets(mandate)
            price = self.price(client)
            if not portfolio.price_fresh(price, self.clock(), portfolio.state_age(context)):
                issues.append("STALE_PRICE")
            if (price.chain_id, price.vault_address) != (mandate.chain_id, mandate.vault_address):
                issues.append("UNVERIFIED_PRICE")
            else:
                snapshot = portfolio.snapshot(
                    balances,
                    price,
                    self.store.history_version(
                        mandate.chain_id, mandate.vault_address, self.settings.mode
                    ),
                )
        except ControlError as error:
            issues.append(error.code)
        return {
            "mode": self.settings.mode,
            "mandate": mandate,
            "proof_session": context.proof_session,
            "portfolio": snapshot,
            "observed_portfolio": observation,
            "decision_eligible": False,
            "chain_balances": balances,
            "issues": list(dict.fromkeys(issues)),
        }

    def run(self, payload, *, workflow_id=None):
        workflow_started = monotonic()
        mandate = self.mandate(payload.mandate_id)
        selection = payload.temporal_intent
        if self.settings.require_itag and selection is None:
            raise ControlError("ITAG_STRUCTURED_INTENT_REQUIRED", 422)
        intent_deadline = None
        if selection:
            if not self.shield.active:
                raise ControlError("ITAG_ACTIVE_TASK_SHIELD_REQUIRED", 409)
            with self.store.connection() as conn:
                spec = temporal_storage.current(conn, selection.spec_id)
            if (
                spec.status != "AUTHENTICATED"
                or spec.revision != selection.revision
                or spec.terms.mandate_id != mandate.mandate_id
                or spec.mode != self.settings.mode
                or not any(s.step_id == selection.step_id for s in spec.terms.steps)
                or self.clock() >= spec.terms.deadline
            ):
                raise ControlError("ITAG_INTENT_NOT_ACTIVE_FOR_WORKFLOW", 409)
            intent_deadline = spec.terms.deadline
        if self.settings.mode != "MOCK" and payload.scenario is not None:
            raise ControlError("MOCK_SCENARIO_FORBIDDEN", 422)
        # Optional identity is allocated by a trusted API adapter for durable demo
        # request idempotency; it is never accepted in the public WorkflowRequest.
        workflow_id = workflow_id or f"workflow_{uuid4().hex}"
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
                **({"temporal_intent": selection.model_dump()} if selection else {}),
            },
            temporal_intent=selection,
        )
        try:
            from treasury_contracts.oracle import SOURCE_HASH

            if (self.settings.mode == "FUJI" and mandate.proof_policy
                    and mandate.proof_policy.oracle_source_hash == SOURCE_HASH):
                from treasury_backend.modules.oracle.window import wait_for_round_window

                def waiting(remaining):
                    if intent_deadline and self.clock() >= intent_deadline:
                        raise ControlError("ITAG_INTENT_NOT_ACTIVE_FOR_WORKFLOW", 409)
                    self.store.event(workflow_id, "WAITING_FOR_ORACLE", self.clock(),
                                     remaining_feed_freshness_seconds=remaining,
                                     required_freshness_seconds=300)

                wait_for_round_window(lambda: self.price(client), required_seconds=300,
                                      on_wait=waiting)
            if self.shield.active:
                session_id = "session_" + uuid4().hex
                self.shield.state.create(session_id, mandate, self.clock(), workflow_id)
                self.shield.update_user(
                    session_id,
                    TaskUpdate(
                        message_id="user_" + uuid4().hex, content=payload.goal, expected_revision=0
                    ),
                    authenticated=True,
                )
                self.shield_runtimes[workflow_id] = ShieldRuntime(self.shield, session_id)
                if selection:
                    self.shield.state.swap_scope(session_id, spec, selection, int(self.clock()))
            self._run_attempts(
                workflow_id, mandate, client, payload.goal, intent_deadline, workflow_started
            )
        except ControlError as error:
            trace = getattr(self.planner.provider, "last_attempts", [])
            self.store.event(workflow_id, "ESCALATED", self.clock(), reason_codes=[error.code],
                             **({"provider_attempts": list(trace)} if trace else {}))
        finally:
            status = self.store.workflow(workflow_id)["status"]
            if status not in {"SUBMITTING", "SUBMITTED"}:
                self.mock_clients.pop(workflow_id, None)
                self.shield_runtimes.pop(workflow_id, None)
        return {"workflow_id": workflow_id, "status": status}

    def _monitor_client(self, workflow_id, mandate):
        if self.settings.mode == "MOCK":
            if workflow_id not in self.mock_clients:
                raise ControlError("MOCK_MONITOR_RUNTIME_UNAVAILABLE", 503)
            return self.mock_clients[workflow_id]
        return self.client(workflow_id, mandate)

    def observe(
        self,
        client,
        mandate,
        balances,
        context,
        *,
        workflow_id=None,
        built=None,
        decision_id=None,
        phase="OBSERVED",
        persist=True,
    ):
        version = self.store.history_version(
            mandate.chain_id, mandate.vault_address, self.settings.mode
        )
        if isinstance(client, MockExecutionClient):
            observation = portfolio.fixture_observation(balances, context, version, self.clock())
        else:
            observation = client.observe(
                mandate,
                block_number=balances.block_number,
                history_version=version,
                # Signing snapshots need verified balances/policy. Authoritative
                # Chainlink rounds are read separately by price() for risk/proof;
                # dashboard-only Witnet/Pyth/reference observations add no gate here.
                include_oracles=self.settings.mode == "FUJI" and phase not in {"PRE", "REVALIDATION"},
            )
        if persist:
            self.store.save_snapshot(
                observation,
                phase=phase,
                workflow_id=workflow_id,
                decision_id=decision_id,
                build_id=built.build_id if built else None,
            )
        return observation

    def _tool(self, workflow_id, name, arguments, execute, *, deadline=None):
        runtime = self.shield_runtimes.get(workflow_id)
        purpose = {
            "read_chain_context": "Read the configured treasury vault policy, chain and session to verify prerequisites for the requested swap; this does not execute a transaction.",
            "read_portfolio": "Read current treasury balances and spend history to enforce the requested swap's balance, exposure and budget constraints.",
            "read_simulation_artifact": "Read the content-addressed simulation evidence required to verify this exact swap before approving or signing it.",
            "observe_portfolio": "Record block-pinned treasury balances for risk checks and post-transaction reconciliation of the requested swap.",
        }.get(name, "")
        if runtime and self.settings.shield.mode == "wallet_pipeline" and name in {
            "read_chain_context", "read_portfolio", "observe_portfolio",
            "build_swap", "simulate_swap", "read_simulation_artifact",
        }:
            # These are fixed backend data operations, not model-selected financial
            # actions. Their output stays untrusted and is flushed before SDE/signing.
            if deadline is not None and self.clock() >= deadline:
                raise ControlError("STALE_REQUIRES_REEVALUATION")
            value = execute()
            runtime.defer_data(name, arguments, value)
            return value
        if deadline is None:
            return runtime.invoke(name, arguments, execute, purpose) if runtime else execute()

        def within_window():
            if self.clock() >= deadline:
                raise ControlError("STALE_REQUIRES_REEVALUATION")

        def checked_execute():
            within_window()
            return execute()

        within_window()
        return runtime.invoke(name, arguments, checked_execute, purpose) if runtime else execute()

    def check_alignment(self, mandate, proposal, goal, tool_output=""):
        if not self.shield.active:
            return (
                alignment.check(mandate, proposal, goal, tool_output)
                if self.settings.shield.mode == "legacy_fixture"
                else alignment.wallet_constraints(mandate, proposal, goal)
            )
        session_id = "session_" + uuid4().hex
        self.shield.state.create(session_id, mandate, self.clock())
        try:
            self.shield.update_user(
                session_id,
                TaskUpdate(message_id="user_" + uuid4().hex, content=goal, expected_revision=0),
                authenticated=True,
            )
            runtime = ShieldRuntime(self.shield, session_id)
            if tool_output:
                runtime.output(
                    "external_tool",
                    "inspection",
                    {"tool_name": "external_tool", "arguments": {}},
                    tool_output,
                )
            runtime.assistant(proposal.user_goal_reason)
            runtime.before("build_swap", proposal.model_dump(), proposal.user_goal_reason)
            value = alignment.wallet_constraints(mandate, proposal, goal)
            return value.model_copy(update={"shield_model_version": self.shield_version})
        except ShieldBlocked as error:
            return Alignment(
                verdict="MISALIGNED" if error.report.status == "MISALIGNED" else "UNCERTAIN",
                reason_codes=[error.code],
                shield_model_version=self.shield_version,
                evidence_refs=[error.report.candidate_hash],
            )
        except ControlError:
            return Alignment(
                verdict="UNCERTAIN",
                reason_codes=["TASK_SHIELD_UNAVAILABLE"],
                shield_model_version=self.shield_version,
                evidence_refs=[],
            )

    def _shield_plan(self, workflow_id, mandate, client, goal, proposal, amount, deadline, fixture):
        runtime = self.shield_runtimes.get(workflow_id)
        if runtime is None:
            value = (
                alignment.check(mandate, proposal, goal, fixture.get("tool_output", ""))
                if self.settings.shield.mode == "legacy_fixture"
                else alignment.wallet_constraints(mandate, proposal, goal)
            )
            return proposal, value
        for attempt in range(self.settings.shield.max_replans + 1):
            try:
                if attempt == 0 and fixture.get("tool_output"):
                    runtime.output(
                        "external_market_data",
                        "fixture_call",
                        {"tool_name": "external_market_data", "arguments": {}},
                        fixture["tool_output"],
                    )
                # Input-Shield feedback is delivered even in paper mode, which retains the raw output.
                if runtime.last_feedback:
                    proposal = planner.revise(mandate, amount, deadline, runtime.last_feedback,
                                              reverse=proposal.token_in == mandate.token_out)
                    self.shield.state.event(
                        runtime.session_id,
                        "REPLAN_AFTER_INPUT",
                        self.clock(),
                        {
                            "feedback": runtime.last_feedback.model_dump(mode="json"),
                            "new_intent_id": proposal.intent_id,
                        },
                    )
                    runtime.last_feedback = None
                runtime.assistant(proposal.user_goal_reason)
                runtime.before("build_swap", proposal.model_dump(), proposal.user_goal_reason)
                constraints = alignment.wallet_constraints(mandate, proposal, goal)
                value = constraints.model_copy(
                    update={"shield_model_version": self.shield_version}
                )
                return proposal, value
            except ShieldBlocked as error:
                self.shield.state.event(
                    runtime.session_id,
                    "REPLAN_REQUESTED",
                    self.clock(),
                    {"attempt": attempt, "feedback": error.report.feedback.model_dump(mode="json")},
                )
                if (
                    error.report.status in {"UNAVAILABLE", "UNCERTAIN"}
                    or attempt >= self.settings.shield.max_replans
                ):
                    return proposal, Alignment(
                        verdict="UNCERTAIN"
                        if error.report.status in {"UNAVAILABLE", "UNCERTAIN"}
                        else "MISALIGNED",
                        reason_codes=[error.code],
                        evidence_refs=[],
                        shield_model_version=self.shield_version,
                    )
                proposal = planner.revise(mandate, amount, deadline, error.report.feedback,
                                          reverse=proposal.token_in == mandate.token_out)
                runtime.last_feedback = None
        raise ControlError("TASK_SHIELD_RETRY_LIMIT")
