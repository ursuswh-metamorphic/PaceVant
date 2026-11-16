import json
from dataclasses import dataclass
from secrets import randbelow
from time import time
from uuid import uuid4

import httpx
from eth_keys import keys
from eth_keys.constants import SECPK1_N
from pydantic import ValidationError

from app import alignment, economic_risk, experience, planner, portfolio, sde
from app.attestor import Attestor
from app.errors import ControlError
from app.models import Alignment, ChainBalances, Mandate, OraclePrice
from app.orchestration.client import ExecutionClient, RestExecutionClient
from app.orchestration.evidence import evidence_issues, json_object, verify_build
from app.orchestration.fuji import FujiVerifier
from app.orchestration.mock import MockExecutionClient
from app.settings import FIXTURES, Settings
from app.storage import Store
from treasury_contract.wire import (
    BuiltTransaction,
    EconomicRiskAssessment,
    PortfolioSnapshot,
    SecurityDecision,
    SimulationEvidence,
    TransactionProposal,
)

STAGES = {
    "APPROVE": "APPROVED",
    "REPLAN": "REPLAN_REQUIRED",
    "REJECT": "REJECTED",
    "ESCALATE": "ESCALATED",
}


@dataclass(frozen=True)
class ApprovedAttempt:
    workflow_id: str
    decision: SecurityDecision
    mandate: Mandate
    proposal: TransactionProposal
    alignment: Alignment
    built: BuiltTransaction
    evidence: SimulationEvidence
    snapshot: PortfolioSnapshot
    balances: ChainBalances


def utc_now() -> int:
    return int(time())


class ControlPlane:
    def __init__(self, settings: Settings, clock=utc_now):
        self.settings = settings
        self.clock = clock
        self.store = Store(settings.db)
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
        if settings.mode != "MOCK":
            self.http = httpx.Client(
                base_url=settings.execution_url,
                headers={"Authorization": f"Bearer {settings.execution_token}"},
                timeout=httpx.Timeout(8, connect=3),
                trust_env=False,
                follow_redirects=False,
            )
        if settings.mode == "FUJI":
            self.fuji_http = httpx.Client(timeout=3, trust_env=False, follow_redirects=False)

    def close(self):
        if self.http:
            self.http.close()
        if self.fuji_http:
            self.fuji_http.close()

    def verify_evidence(self, client, built, evidence, context):
        issues = evidence_issues(client, self.settings.mode, built, evidence, context, self.clock())
        if not issues and self.fuji_http is not None:
            try:
                FujiVerifier(self.fuji_http).verify(context, self.clock())
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
        if self.http:
            return RestExecutionClient(self.http, workflow_id)
        if workflow_id in self.mock_clients:
            return self.mock_clients[workflow_id]
        return MockExecutionClient(
            mandate, self.attestor.address, self.fixture(scenario), self.clock
        )

    def price(self, client: ExecutionClient):
        if isinstance(client, MockExecutionClient):
            return client.price()
        try:
            return OraclePrice.model_validate(json_object(self.settings.oracle_file.read_bytes()))
        except (ValueError, OSError):
            raise ControlError("UNVERIFIED_PRICE", 503) from None

    def standalone_proposal(self, goal, mandate_id):
        mandate = self.mandate(mandate_id)
        client = self.client(f"propose_{uuid4().hex}", mandate)
        issues = portfolio.policy_issues(mandate, client.context(), self.clock())
        if issues:
            raise ControlError(issues[0])
        amount = planner.requested_amount(goal)
        if not amount:
            raise ControlError("TASK_UNCERTAIN", 422)
        return planner.propose(mandate, amount, min(self.clock() + sde.TTL, mandate.expires_at))

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
            price = self.price(client)
            if not portfolio.fresh(price.price_timestamp, self.clock()):
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
                "planner_version": planner.VERSION,
            },
        )
        try:
            self._run_attempts(workflow_id, mandate, client, payload.goal)
        except ControlError as error:
            self.store.event(workflow_id, "ESCALATED", self.clock(), reason_codes=[error.code])
        finally:
            status = self.store.workflow(workflow_id)["status"]
            if status not in {"SUBMITTING", "SUBMITTED"}:
                self.mock_clients.pop(workflow_id, None)
        return {"workflow_id": workflow_id, "status": status}

    def _run_attempts(self, workflow_id, mandate, client, goal):
        amount = planner.requested_amount(goal) or 0
        fixture = client.fixture if isinstance(client, MockExecutionClient) else {}
        for index in range(mandate.max_replans + 1):
            now = self.clock()
            deadline = min(now + sde.TTL, mandate.expires_at, (now // 86400 + 1) * 86400 - 1)
            proposed = planner.propose(
                mandate,
                amount,
                deadline,
                alternate_recipient=fixture.get("poisoned_recipient"),
            )
            self.store.event(
                workflow_id, "PROPOSED", now, attempt=index + 1, proposal=proposed.model_dump()
            )
            aligned = alignment.check(mandate, proposed, goal, fixture.get("tool_output", ""))
            self.store.event(
                workflow_id, aligned.verdict, self.clock(), alignment=aligned.model_dump()
            )
            decision = self._evaluate(workflow_id, mandate, client, proposed, aligned)
            if decision.verdict == "APPROVE":
                signed = self.attest(decision.decision_id)
                self._submit(workflow_id, decision, signed)
                return
            if decision.verdict != "REPLAN" or index >= mandate.max_replans:
                return
            replacement = experience.next_amount(self.store, workflow_id, amount)
            if replacement is None:
                return
            amount = replacement

    def _evaluate(self, workflow_id, mandate, client, proposal, aligned):
        built = sim = evaluation = balances = snapshot = None
        issues = []
        context = None
        try:
            context = client.context()
            issues = portfolio.policy_issues(mandate, context, self.clock())
            if aligned.verdict == "ALIGNED" and not issues:
                if int(proposal.amount_in_base_units) > int(mandate.max_usdc_per_swap_base_units):
                    # The builder may enforce the same cap before simulation.
                    issues.append("TRADE_SIZE_LIMIT")
                    raise ControlError("TRADE_SIZE_LIMIT")
                built = client.build(proposal)
                verify_build(mandate, proposal, built)
                self.store.event(workflow_id, "BUILT", self.clock(), build=built.model_dump())
                sim = client.simulate(built)
                balances = client.balances()
                context = client.context(nonce=built.nonce, fork_block=sim.fork_block)
                issues = self.verify_evidence(client, built, sim, context)
                self.store.event(
                    workflow_id,
                    "SIMULATED",
                    self.clock(),
                    simulation=sim.model_dump(),
                    provenance="UNVERIFIED" if issues else "VERIFIED",
                )
                if not issues:
                    snapshot = portfolio.snapshot(
                        balances, self.price(client), self.store.history_version()
                    )
                    evaluation = economic_risk.evaluate(
                        mandate, proposal, built, sim, snapshot, balances, context, self.clock()
                    )
        except ControlError as error:
            issues.append(error.code)

        decision = sde.decide(
            mandate,
            proposal,
            aligned,
            context,
            self.clock(),
            built=built,
            evidence=sim,
            risk=evaluation.risk if evaluation else None,
            provenance_issues=issues,
        )
        suggested = evaluation.suggested_amount if evaluation else 0
        if decision.verdict == "REPLAN" and not evaluation and "TRADE_SIZE_LIMIT" in issues:
            suggested = min(
                int(mandate.max_usdc_per_swap_base_units), int(proposal.amount_in_base_units) - 1
            )
        evidence = (
            {
                "risk": evaluation.risk.model_dump(),
                "portfolio": snapshot.model_dump(),
                "chain_balances": balances.model_dump(),
            }
            if evaluation
            else {}
        )
        self.store.record(
            workflow_id,
            STAGES[decision.verdict],
            decision,
            {
                "mode": self.settings.mode,
                "decision": decision.model_dump(),
                "mandate": mandate.model_dump(),
                "proposal": proposal.model_dump(),
                "alignment": aligned.model_dump(),
                "build": built.model_dump() if built else None,
                "simulation": sim.model_dump() if sim else None,
                "suggested_amount": suggested,
                **evidence,
            },
            suggested,
            evidence,
        )
        return decision

    def _approved(self, id_) -> ApprovedAttempt:
        workflow_id, bundle = self.store.decision(decision_id=id_)
        decision = SecurityDecision.model_validate(bundle["decision"])
        if decision.verdict != "APPROVE" or decision.decision_id != id_:
            raise ControlError("DECISION_NOT_APPROVED", 403)
        if bundle["mode"] != self.settings.mode:
            raise ControlError("UNVERIFIED_SIMULATION_SOURCE", 403)
        if self.clock() >= decision.expires_at:
            raise ControlError("STALE_REQUIRES_REEVALUATION")
        try:
            mandate = Mandate.model_validate(bundle["mandate"])
            proposal = TransactionProposal.model_validate(bundle["proposal"])
            aligned = Alignment.model_validate(bundle["alignment"])
            built = BuiltTransaction.model_validate(bundle["build"])
            sim = SimulationEvidence.model_validate(bundle["simulation"])
            risk = EconomicRiskAssessment.model_validate(bundle["risk"])
            snapshot = PortfolioSnapshot.model_validate(bundle["portfolio"])
            balances = ChainBalances.model_validate(bundle["chain_balances"])
        except (ValidationError, KeyError):
            raise ControlError("INVALID_APPROVAL_RECORD") from None
        if (
            (
                decision.intent_id,
                decision.build_id,
                decision.policy_hash,
                decision.calldata_hash,
                decision.simulation_evidence_root,
                decision.mandate_version,
                decision.snapshot_id,
            )
            != (
                proposal.intent_id,
                built.build_id,
                mandate.policy_hash,
                built.calldata_hash,
                sim.evidence_root,
                mandate.version,
                snapshot.snapshot_id,
            )
            or (risk.intent_id, risk.build_id, risk.snapshot_id)
            != (decision.intent_id, decision.build_id, decision.snapshot_id)
            or risk.result != "PASS"
            or aligned.verdict != "ALIGNED"
        ):
            raise ControlError("HASH_MISMATCH")
        return ApprovedAttempt(
            workflow_id, decision, mandate, proposal, aligned, built, sim, snapshot, balances
        )

    def _verify_approval(self, approved: ApprovedAttempt):
        mandate, built, sim = approved.mandate, approved.built, approved.evidence
        snapshot = approved.snapshot
        if self.mandate(mandate.mandate_id) != mandate:
            raise ControlError("POLICY_REVOKED")
        client = self.client(approved.workflow_id, mandate)
        verify_build(mandate, approved.proposal, built)
        balances = client.balances()
        context = client.context(nonce=built.nonce, fork_block=sim.fork_block)
        if portfolio.policy_issues(mandate, context, self.clock()):
            raise ControlError("STALE_REQUIRES_REEVALUATION")
        if (
            context.attestor != self.attestor.address
            or len({context.owner, context.relayer, context.attestor}) != 3
        ):
            raise ControlError("ATTESTOR_NOT_AUTHORIZED", 403)
        issues = self.verify_evidence(client, built, sim, context)
        price = self.price(client)
        balance_fields = (
            "usdc_base_units",
            "wavax_base_units",
            "daily_spent_usdc_base_units",
            "daily_execution_cost_usd_e8",
            "utc_day",
        )
        if any(
            getattr(approved.balances, field) != getattr(balances, field)
            for field in balance_fields
        ) or (snapshot.price_usdc_usd_e8, snapshot.price_wavax_usd_e8) != (
            price.price_usdc_usd_e8,
            price.price_wavax_usd_e8,
        ):
            raise ControlError("STALE_REQUIRES_REEVALUATION")
        fresh_snapshot = portfolio.snapshot(balances, price, 0)
        now = self.clock()
        if not portfolio.fresh(snapshot.price_timestamp, now):
            raise ControlError("STALE_PRICE")
        risk = economic_risk.evaluate(
            mandate, approved.proposal, built, sim, fresh_snapshot, balances, context, now
        ).risk
        recomputed = sde.decide(
            mandate,
            approved.proposal,
            approved.alignment,
            context,
            now,
            built=built,
            evidence=sim,
            risk=risk,
            provenance_issues=issues,
        )
        if recomputed.verdict != "APPROVE" or now >= approved.decision.expires_at:
            raise ControlError(next(iter(recomputed.reason_codes), "STALE_REQUIRES_REEVALUATION"))
        return client

    def attest(self, id_):
        approved = self._approved(id_)
        mandate = approved.mandate
        scope = f"{self.settings.mode}:{mandate.chain_id}:{mandate.vault_address}"
        if self.settings.mode == "MOCK":
            scope += f":{approved.workflow_id}"
        return self.attestor.attest(
            id_,
            approved.workflow_id,
            approved.decision,
            approved.built,
            scope,
            lambda: self._verify_approval(approved),
        )

    def _submit(self, workflow_id, decision, pdr):
        id_ = decision.decision_id
        try:
            approved = self._approved(id_)
            client = self._verify_approval(approved)
        except ControlError as error:
            self.store.transition(
                workflow_id, id_, "ATTESTED", "EXPIRED", self.clock(), reason_codes=[error.code]
            )
            return
        built = approved.built
        if not self.store.transition(workflow_id, id_, "ATTESTED", "SUBMITTING", self.clock()):
            raise ControlError("SUBMISSION_ALREADY_STARTED")
        if self.clock() >= decision.expires_at:
            self.store.transition(
                workflow_id,
                id_,
                "SUBMITTING",
                "EXPIRED",
                self.clock(),
                reason_codes=["STALE_REQUIRES_REEVALUATION"],
            )
            return
        try:
            submission = client.execute(built, pdr)
        except ControlError as error:
            self.store.transition(
                workflow_id,
                id_,
                "SUBMITTING",
                "SUBMITTING",
                self.clock(),
                reason_codes=["SUBMISSION_OUTCOME_UNKNOWN", error.code],
            )
            return
        if submission.tx_hash:
            self.store.transition(
                workflow_id,
                id_,
                "SUBMITTING",
                "SUBMITTED",
                self.clock(),
                tx_hash=submission.tx_hash,
            )
            self._reconcile(workflow_id, id_, built, client, submission.tx_hash)
        elif submission.status in {"STALE_REQUIRES_REEVALUATION", "FAILED_TO_SUBMIT"}:
            self.store.transition(
                workflow_id,
                id_,
                "SUBMITTING",
                "FAILED_TO_SUBMIT",
                self.clock(),
                reason_codes=[submission.status],
            )
        else:
            self.store.transition(
                workflow_id,
                id_,
                "SUBMITTING",
                "SUBMITTING",
                self.clock(),
                reason_codes=["SUBMISSION_OUTCOME_UNKNOWN"],
            )

    def _reconcile(self, workflow_id, id_, built, client, tx_hash, receipt=None):
        try:
            receipt = receipt or client.execution(tx_hash)
        except ControlError:
            return
        if receipt.status in {"SUBMITTED", "PENDING"}:
            return
        details = {"receipt": receipt.model_dump()}
        state = receipt.status
        if (
            (receipt.tx_hash, receipt.decision_id, receipt.build_id, receipt.chain_id)
            != (tx_hash, id_, built.build_id, built.chain_id)
            or receipt.block_number is None
            or receipt.gas_used is None
        ):
            state = "RECEIPT_MISMATCH"
        elif state == "CONFIRMED":
            if (
                receipt.actual_token_in_delta_base_units != f"-{built.amount_in_base_units}"
                or int(receipt.actual_token_out_delta_base_units or "0")
                < int(built.min_amount_out_base_units)
                or not receipt.event_refs
                or receipt.revert_reason
            ):
                state = "RECEIPT_MISMATCH"
            else:
                try:
                    updated = client.balances()
                    if (updated.chain_id, updated.vault_address) == (
                        built.chain_id,
                        built.vault_address,
                    ) and updated.block_number >= receipt.block_number:
                        details["post_execution_balances"] = updated.model_dump()
                except ControlError:
                    pass
        elif state == "REVERTED" and (
            receipt.actual_token_in_delta_base_units
            == receipt.actual_token_out_delta_base_units
            == "0"
        ):
            if receipt.revert_reason == "MIN_OUTPUT_NOT_MET":
                details["reason_codes"] = ["PROTECTED_REVERT"]
        else:
            state = "RECEIPT_MISMATCH"
        self.store.transition(workflow_id, id_, "SUBMITTED", state, self.clock(), **details)

    def workflow(self, id_):
        workflow = self.store.workflow(id_)
        if workflow["mode"] != self.settings.mode:
            return workflow
        if workflow["status"] in {"SUBMITTED", "SUBMITTING"}:
            event = workflow["timeline"][-1]
            _, bundle = self.store.decision(decision_id=event["decision_id"])
            mandate = Mandate.model_validate(bundle["mandate"])
            built = BuiltTransaction.model_validate(bundle["build"])
            client = self.client(id_, mandate)
            if workflow["status"] == "SUBMITTED":
                self._reconcile(id_, event["decision_id"], built, client, event["tx_hash"])
            elif self.clock() > built.deadline:
                self._expire_unknown_submission(id_, event["decision_id"], built, client)
            workflow = self.store.workflow(id_)
            if workflow["status"] not in {"SUBMITTED", "SUBMITTING"}:
                self.mock_clients.pop(id_, None)
        return workflow

    def _expire_unknown_submission(self, workflow_id, decision_id, built, client):
        try:
            context = client.context(nonce=built.nonce)
        except ControlError:
            return
        if (
            (context.chain_id, context.vault_address, context.deployment)
            == (built.chain_id, built.vault_address, self.settings.mode)
            and portfolio.fresh(context.block_timestamp, self.clock())
            and context.block_timestamp > built.deadline
            and context.nonce_used is False
        ):
            self.store.transition(
                workflow_id,
                decision_id,
                "SUBMITTING",
                "EXPIRED",
                self.clock(),
                reason_codes=["SUBMISSION_NOT_CONFIRMED_BY_DEADLINE"],
            )

    def recover_submission(self, workflow_id, tx_hash):
        workflow = self.store.workflow(workflow_id)
        if workflow["mode"] != self.settings.mode or workflow["status"] != "SUBMITTING":
            raise ControlError("NO_UNKNOWN_SUBMISSION")
        id_ = workflow["timeline"][-1]["decision_id"]
        _, bundle = self.store.decision(decision_id=id_)
        mandate = Mandate.model_validate(bundle["mandate"])
        built = BuiltTransaction.model_validate(bundle["build"])
        client = self.client(workflow_id, mandate)
        receipt = client.execution(tx_hash)
        if (receipt.tx_hash, receipt.decision_id, receipt.build_id, receipt.chain_id) != (
            tx_hash,
            id_,
            built.build_id,
            built.chain_id,
        ) or receipt.status not in {"SUBMITTED", "PENDING", "CONFIRMED", "REVERTED"}:
            raise ControlError("RECEIPT_MISMATCH")
        if self.store.transition(
            workflow_id, id_, "SUBMITTING", "SUBMITTED", self.clock(), tx_hash=tx_hash
        ):
            self._reconcile(workflow_id, id_, built, client, tx_hash, receipt)
        return self.store.workflow(workflow_id)

    def saved_risk(self, evidence, snapshot_id):
        _, bundle = self.store.decision(build_id=evidence.build_id)
        if bundle.get("simulation") != evidence.model_dump():
            raise ControlError("HASH_MISMATCH")
        if "risk" not in bundle or bundle["risk"]["snapshot_id"] != snapshot_id:
            raise ControlError("SNAPSHOT_NOT_FOUND", 404)
        return EconomicRiskAssessment.model_validate(bundle["risk"])

    def saved_decision(self, refs):
        _, bundle = self.store.decision(intent_id=refs.intent_id, build_id=refs.build_id)
        decision = SecurityDecision.model_validate(bundle["decision"])
        if (decision.build_id, decision.snapshot_id, decision.simulation_evidence_root) != (
            refs.build_id,
            refs.snapshot_id,
            refs.simulation_evidence_root,
        ) or refs.alignment.model_dump() != bundle["alignment"]:
            raise ControlError("HASH_MISMATCH")
        return decision
