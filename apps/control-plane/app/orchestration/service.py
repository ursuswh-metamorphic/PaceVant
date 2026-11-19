import json
from dataclasses import dataclass
from secrets import randbelow
from time import monotonic, time
from uuid import uuid4

import httpx
from eth_keys import keys
from eth_keys.constants import SECPK1_N
from pydantic import ValidationError

from app import alignment, economic_risk, experience, planner, portfolio, sde
from app.alignment.engine import TaskShield
from app.alignment.runtime import ShieldBlocked, ShieldRuntime
from app.alignment.types import TaskUpdate
from app.attestor import Attestor
from app.domain import EconomicRiskAssessment, PortfolioSnapshot, SecurityDecision
from app.errors import ControlError
from app.models import Alignment, ChainBalances, Mandate, OraclePrice
from app.monitoring.service import OutcomeMonitor
from app.orchestration.client import ExecutionClient, RestExecutionClient
from app.orchestration.evidence import evidence_issues, json_object, verify_build
from app.orchestration.fuji import FujiVerifier
from app.orchestration.mock import MockExecutionClient
from app.settings import FIXTURES, Settings
from app.storage import Store
from app.temporal import storage as temporal_storage
from app.temporal.models import HybridTemporalAssessment
from app.temporal.service import TemporalService
from treasury_contracts.models import BuiltTransaction, SimulationEvidence, TransactionProposal

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
        self.shield = TaskShield(self.store, settings.shield, clock=clock)
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
        if settings.mode != "MOCK":
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
        self.shield.close()
        if self.http:
            self.http.close()
        if self.fuji_http:
            self.fuji_http.close()

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
                include_oracles=self.settings.mode == "FUJI",
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

    def verify_evidence(self, client, built, evidence, context, workflow_id=None):
        gate = (
            (
                lambda ref, read: self._tool(
                    workflow_id, "read_simulation_artifact", {"reference": ref}, read
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
            return RestExecutionClient(self.http, workflow_id, self.settings, self.store)
        if workflow_id in self.mock_clients:
            return self.mock_clients[workflow_id]
        return MockExecutionClient(
            mandate, self.attestor.address, self.fixture(scenario), self.clock
        )

    def _tool(self, workflow_id, name, arguments, execute):
        runtime = self.shield_runtimes.get(workflow_id)
        return runtime.invoke(name, arguments, execute) if runtime else execute()

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
            return value.model_copy(update={"shield_model_version": "task-shield-acl2025-v1"})
        except ShieldBlocked as error:
            return Alignment(
                verdict="MISALIGNED" if error.report.status == "MISALIGNED" else "UNCERTAIN",
                reason_codes=[error.code],
                shield_model_version="task-shield-acl2025-v1",
                evidence_refs=[error.report.candidate_hash],
            )
        except ControlError:
            return Alignment(
                verdict="UNCERTAIN",
                reason_codes=["TASK_SHIELD_UNAVAILABLE"],
                shield_model_version="task-shield-acl2025-v1",
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
                    proposal = planner.revise(mandate, amount, deadline, runtime.last_feedback)
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
                    update={"shield_model_version": "task-shield-acl2025-v1"}
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
                    error.report.status == "UNAVAILABLE"
                    or attempt >= self.settings.shield.max_replans
                ):
                    return proposal, Alignment(
                        verdict="UNCERTAIN"
                        if error.report.status == "UNAVAILABLE"
                        else "MISALIGNED",
                        reason_codes=[error.code],
                        evidence_refs=[],
                        shield_model_version="task-shield-acl2025-v1",
                    )
                proposal = planner.revise(mandate, amount, deadline, error.report.feedback)
                runtime.last_feedback = None
        raise ControlError("TASK_SHIELD_RETRY_LIMIT")

    def price(self, client: ExecutionClient):
        if isinstance(client, MockExecutionClient):
            return client.price()
        if self.settings.mode == "FUJI":
            # LFJ faucet USDC is not Circle USDC. A file labelled TRUSTED_TEST_ORACLE
            # cannot establish an independent USD valuation for this traded asset.
            raise ControlError("ORACLE_TOKEN_IDENTITY_MISMATCH", 409)
        try:
            return OraclePrice.model_validate(json_object(self.settings.oracle_file.read_bytes()))
        except (ValueError, OSError):
            raise ControlError("UNVERIFIED_PRICE", 503) from None

    def standalone_proposal(self, goal, mandate_id):
        mandate = self.mandate(mandate_id)
        client = self.client(f"propose_{uuid4().hex}", mandate)
        context = client.context()
        issues = portfolio.policy_issues(mandate, context, self.clock())
        if issues:
            raise ControlError(issues[0])
        amount = planner.requested_amount(goal)
        if not amount:
            raise ControlError("TASK_UNCERTAIN", 422)
        return planner.propose(mandate, amount, self._deadline(mandate, self.clock(), context))

    @staticmethod
    def _deadline(mandate, now, context=None):
        deadline = min(now + sde.TTL, mandate.expires_at, (now // 86400 + 1) * 86400 - 1)
        if context is not None:
            deadline = min(
                deadline,
                context.block_timestamp + min(sde.TTL, context.max_approval_ttl),
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
        observation = self.observe(client, mandate, balances, context)
        snapshot = None
        try:
            price = self.price(client)
            if not portfolio.fresh(price.price_timestamp, self.clock()):
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
            "portfolio": snapshot,
            "observed_portfolio": observation,
            "decision_eligible": False,
            "chain_balances": balances,
            "issues": list(dict.fromkeys(issues)),
        }

    def run(self, payload):
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
                **({"temporal_intent": selection.model_dump()} if selection else {}),
            },
            temporal_intent=selection,
        )
        try:
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
            self._run_attempts(
                workflow_id, mandate, client, payload.goal, intent_deadline, workflow_started
            )
        except ControlError as error:
            self.store.event(workflow_id, "ESCALATED", self.clock(), reason_codes=[error.code])
        finally:
            status = self.store.workflow(workflow_id)["status"]
            if status not in {"SUBMITTING", "SUBMITTED"}:
                self.mock_clients.pop(workflow_id, None)
                self.shield_runtimes.pop(workflow_id, None)
        return {"workflow_id": workflow_id, "status": status}

    def _run_attempts(self, workflow_id, mandate, client, goal, intent_deadline, workflow_started):
        amount = planner.requested_amount(goal) or 0
        fixture = client.fixture if isinstance(client, MockExecutionClient) else {}
        for index in range(mandate.max_replans + 1):
            now = self.clock()
            context = (
                self._tool(workflow_id, "read_chain_context", {}, client.context)
                if isinstance(client, RestExecutionClient)
                else None
            )
            deadline = self._deadline(mandate, now, context)
            if intent_deadline:
                deadline = min(deadline, intent_deadline)
            proposed = planner.propose(
                mandate,
                amount,
                deadline,
                alternate_recipient=fixture.get("poisoned_recipient"),
            )
            self.store.event(
                workflow_id, "PROPOSED", now, attempt=index + 1, proposal=proposed.model_dump()
            )
            proposed, aligned = self._shield_plan(
                workflow_id, mandate, client, goal, proposed, amount, deadline, fixture
            )
            self.store.event(
                workflow_id, aligned.verdict, self.clock(), alignment=aligned.model_dump()
            )
            decision = self._evaluate(
                workflow_id, mandate, client, proposed, aligned, context, workflow_started
            )
            runtime = self.shield_runtimes.get(workflow_id)
            if runtime:
                for shield_retry in range(self.settings.shield.max_replans):
                    feedback = runtime.last_feedback
                    if feedback is None or feedback.code == "TASK_SHIELD_UNAVAILABLE":
                        break
                    self.shield.state.event(
                        runtime.session_id,
                        "REPLAN_AFTER_TOOL_OUTPUT",
                        self.clock(),
                        {
                            "retry": shield_retry + 1,
                            "feedback": feedback.model_dump(mode="json"),
                            "previous_decision_id": decision.decision_id,
                        },
                    )
                    # The original candidate and rejected tool output are never reused as executable instructions.
                    retry_deadline = self._deadline(mandate, self.clock(), context)
                    if intent_deadline:
                        retry_deadline = min(retry_deadline, intent_deadline)
                    proposed = planner.revise(mandate, amount, retry_deadline, feedback)
                    runtime.last_feedback = None
                    proposed, aligned = self._shield_plan(
                        workflow_id, mandate, client, goal, proposed, amount, proposed.deadline, {}
                    )
                    decision = self._evaluate(
                        workflow_id, mandate, client, proposed, aligned, context, workflow_started
                    )
                if runtime.last_feedback:
                    self.shield.state.event(
                        runtime.session_id,
                        "SHIELD_STOPPED",
                        self.clock(),
                        {
                            "feedback": runtime.last_feedback.model_dump(mode="json"),
                            "decision_id": decision.decision_id,
                        },
                    )
                    if decision.verdict == "APPROVE":
                        self.store.event(
                            workflow_id,
                            "ESCALATED",
                            self.clock(),
                            reason_codes=["TASK_SHIELD_FEEDBACK_PENDING"],
                            decision_id=decision.decision_id,
                        )
                    return
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

    def _evaluate(
        self, workflow_id, mandate, client, proposal, aligned, context=None, workflow_started=None
    ):
        evaluation_started = monotonic()
        built = sim = evaluation = balances = snapshot = observation = None
        issues = []
        try:
            context = context or self._tool(workflow_id, "read_chain_context", {}, client.context)
            issues = portfolio.policy_issues(mandate, context, self.clock())
            if aligned.verdict == "ALIGNED" and not issues:
                if int(proposal.amount_in_base_units) > int(mandate.max_usdc_per_swap_base_units):
                    # The builder may enforce the same cap before simulation.
                    issues.append("TRADE_SIZE_LIMIT")
                    raise ControlError("TRADE_SIZE_LIMIT")
                built = self._tool(
                    workflow_id, "build_swap", proposal.model_dump(), lambda: client.build(proposal)
                )
                verify_build(mandate, proposal, built)
                self.store.event(workflow_id, "BUILT", self.clock(), build=built.model_dump())
                sim = self._tool(
                    workflow_id,
                    "simulate_swap",
                    {"build": built.model_dump()},
                    lambda: client.simulate(built),
                )
                balances = self._tool(workflow_id, "read_portfolio", {}, client.balances)
                context = self._tool(
                    workflow_id,
                    "read_chain_context",
                    {"build_id": built.build_id, "fork_block": sim.fork_block},
                    lambda: client.context(built=built, fork_block=sim.fork_block),
                )
                issues = self.verify_evidence(client, built, sim, context, workflow_id)
                observation = self._tool(
                    workflow_id,
                    "observe_portfolio",
                    {"vault_address": mandate.vault_address, "block_number": balances.block_number},
                    lambda: self.observe(
                        client,
                        mandate,
                        balances,
                        context,
                        workflow_id=workflow_id,
                        built=built,
                        phase="PRE",
                    ),
                )
                self.store.event(
                    workflow_id,
                    "SIMULATED",
                    self.clock(),
                    simulation=sim.model_dump(),
                    provenance="UNVERIFIED" if issues else "VERIFIED",
                )
                if not issues:
                    snapshot = portfolio.decision_snapshot(
                        observation, balances, self.price(client), context, built, self.clock()
                    )
                    evaluation = economic_risk.evaluate(
                        mandate, proposal, built, sim, snapshot, balances, context, self.clock()
                    )
        except ControlError as error:
            issues.append(
                "TRADE_SIZE_LIMIT"
                if error.code in {"DAILY_SPEND_LIMIT", "INSUFFICIENT_BALANCE"}
                else error.code
            )
            if error.code in {"DAILY_SPEND_LIMIT", "INSUFFICIENT_BALANCE"}:
                try:
                    balances = client.balances()
                except ControlError as balance_error:
                    issues.append(balance_error.code)

        temporal, temporal_hash = self.temporal.evaluate(
            workflow_id,
            mandate,
            proposal,
            built,
            sim,
            observation,
            aligned,
            self.shield_runtimes.get(workflow_id),
        )
        sde_started = monotonic()
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
            temporal=temporal,
        )
        if temporal:
            self.store.event(
                workflow_id,
                "ITAG_ASSESSED",
                self.clock(),
                assessment_hash=temporal_hash,
                verdict=temporal.verdict,
                reason_codes=temporal.reason_codes,
                timing_ms={
                    **temporal.timing_ms,
                    "evaluation_through_sde": int((monotonic() - evaluation_started) * 1000),
                    "workflow_through_sde": int(
                        (monotonic() - (workflow_started or evaluation_started)) * 1000
                    ),
                    "sde": int((monotonic() - sde_started) * 1000),
                },
            )
        suggested = evaluation.suggested_amount if evaluation else 0
        if decision.verdict == "REPLAN" and not evaluation and "TRADE_SIZE_LIMIT" in issues:
            suggested = min(
                int(mandate.max_usdc_per_swap_base_units), int(proposal.amount_in_base_units) - 1
            )
            if balances is not None:
                suggested = min(
                    suggested,
                    int(balances.usdc_base_units),
                    max(
                        0,
                        int(mandate.max_usdc_spend_per_day_base_units)
                        - int(balances.daily_spent_usdc_base_units),
                    ),
                )
        if temporal and temporal.suggested_amount is not None:
            suggested = (
                min(suggested, int(temporal.suggested_amount))
                if suggested
                else int(temporal.suggested_amount)
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
                "chain_context": context.model_dump() if context else None,
                "pre_snapshot_id": observation.snapshot_id if observation else None,
                "itag_assessment_hash": temporal_hash,
                "task_shield_proof": self.shield_runtimes[workflow_id].proof(proposal)
                if workflow_id in self.shield_runtimes
                else None,
                **evidence,
            },
            suggested,
            evidence,
        )
        if observation:
            self.store.save_snapshot(
                observation,
                phase="PRE",
                workflow_id=workflow_id,
                decision_id=decision.decision_id,
                build_id=built.build_id if built else None,
            )
        return decision

    def _approved(self, id_) -> ApprovedAttempt:
        workflow_id, bundle = self.store.decision(decision_id=id_)
        decision = SecurityDecision.model_validate(bundle["decision"])
        if self.settings.require_itag and not bundle.get("itag_assessment_hash"):
            raise ControlError("ITAG_APPROVAL_PROOF_REQUIRED", 403)
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
            snapshot = portfolio.parse_decision_snapshot(bundle["portfolio"])
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
        _, bundle = self.store.decision(decision_id=approved.decision.decision_id)
        temporal = None
        if bundle.get("itag_assessment_hash"):
            with self.store.connection() as conn:
                _, body, _ = temporal_storage.load(conn, bundle["itag_assessment_hash"])
            temporal = HybridTemporalAssessment.model_validate(body)
        proof = bundle.get("task_shield_proof")
        if self.shield.active or proof:
            if not proof or not proof.get("check_ids") or proof.get("unresolved_feedback"):
                raise ControlError("TASK_SHIELD_APPROVAL_PROOF_REQUIRED")
            from app.alignment.provider import safe_value

            if proof["proposal"] != safe_value(approved.proposal):
                raise ControlError("TASK_SHIELD_PROPOSAL_MISMATCH")
            self.shield.validate(proof["session_id"], proof["check_ids"], proof["revision"])
            from app.portfolio.observations import content_hash

            session = self.shield.state.session(proof["session_id"])
            if (
                session["mandate_hash"] != content_hash(mandate.model_dump())
                or session["workflow_id"] != approved.workflow_id
            ):
                raise ControlError("TASK_SHIELD_MANDATE_MISMATCH")
        snapshot = approved.snapshot
        if hasattr(snapshot, "observation_snapshot_id"):
            from app.domain import ObservedPortfolioSnapshot
            from app.portfolio.observations import verify_snapshot_hash

            original = ObservedPortfolioSnapshot.model_validate(
                self.store.snapshot_record(snapshot.observation_snapshot_id)["snapshot"]
            )
            if (
                not verify_snapshot_hash(original)
                or original.content_hash != snapshot.observation_hash
            ):
                raise ControlError("SNAPSHOT_HASH_MISMATCH")
            if (
                self.store.history_version(
                    mandate.chain_id, mandate.vault_address, self.settings.mode
                )
                != snapshot.history_version
            ):
                raise ControlError("STALE_REQUIRES_REEVALUATION")
        if self.mandate(mandate.mandate_id) != mandate:
            raise ControlError("POLICY_REVOKED")
        client = self.client(approved.workflow_id, mandate)
        verify_build(mandate, approved.proposal, built)
        balances = client.balances()
        context = client.context(built=built, fork_block=sim.fork_block)
        fresh_observed = self.observe(
            client,
            mandate,
            balances,
            context,
            workflow_id=approved.workflow_id,
            built=built,
            decision_id=approved.decision.decision_id,
            phase="REVALIDATION",
            persist=False,
        )
        if hasattr(snapshot, "observation_snapshot_id") and not isinstance(
            client, MockExecutionClient
        ):
            header = client.rpc.eth.get_block(snapshot.block_number)
            if "0x" + header.hash.hex().removeprefix("0x") != snapshot.block_hash:
                raise ControlError("BLOCK_HASH_MISMATCH")
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
            "daily_execution_cost_wei",
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
        fresh_snapshot = portfolio.decision_snapshot(
            fresh_observed, balances, price, context, built, self.clock()
        )
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
            temporal=temporal,
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
        # No LLM calls inside the attestor's SQLite reservation. The final write check is here,
        # before SUBMITTING and before client.execute, while deterministic verification remains intact.
        runtime = self.shield_runtimes.get(workflow_id)
        execute_call = None
        if self.shield.active:
            if runtime is None:
                session = self.shield.state.for_workflow(workflow_id)
                if not session:
                    raise ControlError("TASK_SHIELD_SESSION_NOT_FOUND")
                runtime = ShieldRuntime(self.shield, session["id"])
            try:
                execute_call = runtime.before(
                    "execute_approved_swap",
                    {"build": built.model_dump(), "decision_id": id_},
                    approved.proposal.user_goal_reason,
                )
                # A concurrent user cancellation invalidates the saved approval even if the model said yes.
                _, saved = self.store.decision(decision_id=id_)
                proof = saved["task_shield_proof"]
                self.shield.validate(proof["session_id"], proof["check_ids"], proof["revision"])
            except ControlError as error:
                self.store.transition(
                    workflow_id, id_, "ATTESTED", "EXPIRED", self.clock(), reason_codes=[error.code]
                )
                return
        try:
            started = self.store.transition(
                workflow_id, id_, "ATTESTED", "SUBMITTING", self.clock()
            )
        except ControlError as error:
            self.store.transition(
                workflow_id, id_, "ATTESTED", "EXPIRED", self.clock(), reason_codes=[error.code]
            )
            return
        if not started:
            raise ControlError("SUBMISSION_ALREADY_STARTED")
        self.store.track_execution(workflow_id, id_, self.settings.mode, built, self.clock())
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
            self.store.track_execution(
                workflow_id, id_, self.settings.mode, built, self.clock(), submission.tx_hash
            )
            self.store.transition(
                workflow_id,
                id_,
                "SUBMITTING",
                "SUBMITTED",
                self.clock(),
                tx_hash=submission.tx_hash,
            )
            if execute_call:
                try:
                    runtime.output(
                        "execute_approved_swap", execute_call[0], execute_call[1], submission
                    )
                except ControlError as error:
                    # Broadcast has already happened. Preserve its hash and monitoring reservation;
                    # a shield failure after submission must never cause a replacement/retry write.
                    self.shield.state.event(
                        runtime.session_id,
                        "POST_SUBMISSION_FEEDBACK",
                        self.clock(),
                        {"code": error.code, "decision_id": id_},
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
        self.store.track_execution(
            workflow_id, id_, self.settings.mode, built, self.clock(), tx_hash
        )
        return self.monitor.process(id_, force=True, client=client, receipt=receipt)

    def workflow(self, id_):
        workflow = self.store.workflow(id_)
        if workflow["mode"] != self.settings.mode:
            return workflow
        candidates = [e for e in reversed(workflow["timeline"]) if e.get("decision_id")]
        if candidates and workflow["status"] in {
            "SUBMITTING",
            "SUBMITTED",
            "CONFIRMED",
            "REVERTED",
            "RECEIPT_MISMATCH",
        }:
            id_decision = candidates[0]["decision_id"]
            job = self.store.monitor_job(id_decision)
            if job is None:
                self.monitor.bootstrap()
                job = self.store.monitor_job(id_decision)
            if job and (self.settings.mode != "MOCK" or id_ in self.mock_clients):
                self.monitor.process(id_decision, force=True)
            workflow = self.store.workflow(id_)
            if workflow["status"] == "SUBMITTING":
                _, bundle = self.store.decision(decision_id=id_decision)
                built = BuiltTransaction.model_validate(bundle["build"])
                if self.clock() > built.deadline:
                    try:
                        mandate = Mandate.model_validate(bundle["mandate"])
                        self._expire_unknown_submission(
                            id_, id_decision, built, self._monitor_client(id_, mandate)
                        )
                    except ControlError:
                        pass
            workflow = self.store.workflow(id_)
            job = self.store.monitor_job(id_decision)
            workflow["reconciliation"] = self.store.outcome_projection(id_decision)
            workflow["monitoring"] = (
                {"state": job["state"], "next_poll_at": job["next_at"], "attempts": job["attempts"]}
                if job
                else None
            )
            if workflow["status"] not in {"SUBMITTING", "SUBMITTED"}:
                self.mock_clients.pop(id_, None)
        return workflow

    def _expire_unknown_submission(self, workflow_id, decision_id, built, client):
        try:
            context = client.context(built=built)
        except ControlError:
            return
        if (
            (context.chain_id, context.vault_address, context.deployment)
            == (built.chain_id, built.vault_address.lower(), self.settings.mode)
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
