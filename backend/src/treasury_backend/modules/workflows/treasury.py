"""V3 coordinator using existing Shield, ITAG semantics, risk, proof, SDE and attestor.

The execution port owns EVM/relay details. No signing capability is passed to execution.
"""

from uuid import uuid4

from treasury_backend.core.errors import ControlError
from treasury_backend.modules.alignment.provider import inference_window
from treasury_backend.modules.alignment.runtime import ShieldRuntime
from treasury_backend.modules.alignment.types import TaskUpdate
from treasury_backend.modules.decision.service import decide_operation
from treasury_backend.modules.persistence.v3 import TreasuryStore
from treasury_backend.modules.planning.rebalance import propose_rebalance
from treasury_backend.modules.planning.treasury import plan_operation
from treasury_backend.modules.risk.operations import assess_operation
from treasury_backend.modules.temporal.operations import evaluate_operation
from treasury_contracts.crypto import content_hash
from treasury_contracts.proof_v3 import prove_operation
from treasury_contracts.v3 import Constraints, Operation


class TreasuryWorkflows:
    def __init__(self, control, execution):
        self.control, self.execution = control, execution
        self.store = TreasuryStore(control.store)
        self.clock = control.clock
        self.on_progress = None
        if control.attestor.address.lower() != execution.manifest.attestor:
            raise ValueError("ATTESTOR_IDENTITY_MISMATCH")

    def progress(self, stage):
        if self.on_progress is not None:
            self.on_progress(stage)

    def _runtime(self, id_, intent):
        shield = self.control.shield
        if not shield.active or shield.config.mode not in {"wallet_pipeline", "wallet_hardened"}:
            raise ControlError("TASK_SHIELD_REQUIRED", 503)
        session = "shield_v3_" + uuid4().hex
        shield.state.create_operation(session, self.execution.manifest, self.clock(), id_)
        shield.update_user(
            session,
            TaskUpdate(
                message_id="request_" + uuid4().hex,
                content=intent.objective + "\nExact authorized terms: " + intent.model_dump_json(),
                expected_revision=0,
            ),
            authenticated=True,
        )
        return ShieldRuntime(shield, session)

    def run(self, intent, key):
        if getattr(self.execution, "protocol", None) == "PACEVANT_MVP" and (
            intent.operation not in {"TOKEN_SWAP", "TOKEN_PAYMENT"}
            or intent.operation == "TOKEN_PAYMENT"
            and intent.token_in != self.execution.manifest.usdc
        ):
            raise ControlError("MVP_UNSUPPORTED_OPERATION", 400)
        with self.execution.exclusive(), inference_window(max(1, min(180, intent.deadline - self.clock() - 15))):
            # A previously confirmed record is rechecked before it can authorize another action.
            for previous in self.store.history(1000):
                if previous.get("outcome", {}).get("tx_hash"):
                    self.reconcile(previous["workflow_id"])
            record, fresh = self.store.claim(key, intent, self.clock())
            id_ = record["workflow_id"]
            if not fresh:
                return self.reconcile(id_)
            signed = False
            try:
                context = self.execution.context(intent.session_id)
                self.store.event(id_, "OWNER_AUTHORITY", context, self.clock())
                self.progress("PLANNING")
                runtime = self._runtime(id_, intent)
                runtime.before("propose_fixed_operation", intent.model_dump(mode="json"))
                plan = plan_operation(self.control.shield.provider, intent)
                explanation = plan.model_dump(mode="json")
                runtime.assistant(plan.model_dump_json())
                self.store.event(
                    id_,
                    "AGENT_PROPOSAL",
                    {
                        "typed_intent": intent.model_dump(mode="json"),
                        "explanation": explanation["explanation"],
                        "candidate_plan": explanation,
                        "authority": "OWNER_SESSION_ONLY",
                    },
                    self.clock(),
                )
                self.progress("BUILD")
                built = runtime.invoke(
                    "build_fixed_operation",
                    intent.model_dump(mode="json"),
                    lambda: self.execution.build(intent, context),
                )
                self.store.event(id_, "BUILD", built, self.clock())
                self.store.update(id_, "BUILT", build_id=built["build_id"])
                self.progress("SIMULATION")
                effects = runtime.invoke(
                    "simulate_fixed_operation",
                    {"build_id": built["build_id"]},
                    lambda: self.execution.simulate(built, context),
                )
                self.store.event(id_, "SIMULATION", effects, self.clock())
                self.progress("RISK")
                risk = assess_operation(intent, built, effects, context, self.clock())
                self.store.event(id_, "RISK", risk, self.clock())
                history = [
                    r
                    for r in self.store.history()
                    if r["workflow_id"] != id_ and r["intent"]["session_id"] == intent.session_id
                ]
                self.progress("ITAG")
                temporal = evaluate_operation(
                    self.control.temporal, intent, built, context, history, runtime
                )
                self.store.event(id_, "ITAG", temporal, self.clock())
                if temporal["verdict"] != "PASS" or risk["result"] != "PASS":
                    raise ControlError("SECURITY_GATE_FAILED", 409)
                self.progress("PROOF")
                proof = prove_operation(intent, built, effects, context)
                self.store.event(id_, "PROOF", proof, self.clock())
                runtime.defer_data(
                    "verify_constraints",
                    {"build_id": built["build_id"]},
                    {k: v for k, v in proof.items() if k != "queries"},
                )
                runtime.flush_data()
                self.progress("SDE")
                decision = decide_operation(
                    intent, built, effects, risk, proof, temporal, self.clock()
                )
                self.store.event(id_, "SDE", decision, self.clock())
                if decision["verdict"] != "APPROVE":
                    raise ControlError("DECISION_NOT_APPROVED", 409)
                self.store.update(id_, "PROVED", decision=decision)

                def revalidate():
                    self.execution.revalidate(intent, built, context)
                    current_risk = assess_operation(intent, built, effects, context, self.clock())
                    if (
                        current_risk["result"] != "PASS"
                        or content_hash(current_risk) != decision["risk_hash"]
                    ):
                        raise ControlError("ECONOMIC_RISK_REVALIDATION_FAILED", 409)
                    shield_proof = runtime.proof(intent)
                    self.control.shield.validate(
                        shield_proof["session_id"],
                        shield_proof["check_ids"],
                        shield_proof["revision"],
                    )
                    if shield_proof["unresolved_feedback"]:
                        raise ControlError("TASK_MISALIGNED", 403)

                runtime.before(
                    "execute_fixed_operation",
                    {
                        "build_id": built["build_id"],
                        "intent_hash": intent.hash,
                        "proof_hash": proof["proof_hash"],
                    },
                )
                self.progress("ATTESTATION")
                approval = self.store.sign_once(
                    id_,
                    lambda: self.control.attestor.attest_operation(
                        intent, built, effects, context, proof, decision, revalidate
                    ),
                )
                signed = True
                operation, phi = (
                    Operation.model_validate(approval["operation"]),
                    Constraints.model_validate(approval["phi"]),
                )
                self.store.event(
                    id_,
                    "ATTESTATION",
                    {
                        "domain_version": "3",
                        "chain_id": intent.chain_id,
                        "verifying_contract": intent.treasury,
                        "signer": context["attestor"],
                        "nonce": operation.nonce,
                        "deadline": operation.deadline,
                        "typed_data_hash": approval["typed_data_hash"],
                        "constraints_hash": phi.hash,
                    },
                    self.clock(),
                )
                self.progress("EXACT_SIGNED_PREFLIGHT")
                final = self.execution.preflight(
                    built, context, operation, phi, approval["signature"]
                )
                self.store.event(id_, "EXACT_SIGNED_PREFLIGHT", final, self.clock())
                revalidate()
                self.progress("RELAY")
                outcome = self.execution.execute(built, operation, phi, approval["signature"])
                self.store.event(id_, "OUTCOME", outcome, self.clock())
                self.store.update(
                    id_, outcome["status"], outcome=outcome, environment=context["environment"]
                )
            except Exception as error:
                if hasattr(error, "queries"):
                    self.store.event(
                        id_,
                        "PROOF_REJECTION",
                        {
                            "queries": error.queries,
                            "counterexample": getattr(error, "counterexample", None),
                            "status": "NOT_PROVEN",
                        },
                        self.clock(),
                    )
                # Signed-but-uncertain workflows keep the session reservation until reconciliation/expiry.
                code = getattr(
                    error,
                    "code",
                    str(error) if isinstance(error, ValueError) else "TREASURY_WORKFLOW_FAILED",
                )
                import re

                if not isinstance(code, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", code):
                    code = "TREASURY_WORKFLOW_FAILED"
                self.store.event(
                    id_, "REJECTION_OR_RECOVERY",
                    {"code": code, "signed": signed, "error_type": type(error).__name__},
                    self.clock(),
                )
                self.store.update(
                    id_, "SIGNED_REQUIRES_RECOVERY" if signed else "REJECTED", reason_code=code
                )
            return self.store.get(id_)

    def reconcile(self, id_):
        record = self.store.get(id_)
        tx_hash = (record.get("outcome") or {}).get("tx_hash")
        if not tx_hash and record.get("build_id"):
            tx_hash = self.execution.submission_hash(record["build_id"])
        if tx_hash:
            outcome = self.execution.reconcile(tx_hash)
            if outcome != record.get("outcome"):
                self.store.event(id_, "RECONCILIATION", outcome, self.clock())
            self.store.update(id_, outcome["status"], outcome=outcome)
        elif (
            record["status"] not in {"CONFIRMED", "REVERTED", "REJECTED", "EXPIRED_UNSIGNED"}
            and self.clock() > record["intent"]["deadline"]
        ):
            self.store.update(
                id_, "EXPIRED_UNSIGNED", reason_code="APPROVAL_EXPIRED_WITHOUT_SUBMISSION"
            )
        return self.store.get(id_)

    def rebalance(self, request, key):
        with self.execution.exclusive():
            prior = self.store.by_key(key)
            if prior:
                if prior.get("rebalance_request_hash") != content_hash(
                    request.model_dump(mode="json")
                ):
                    raise ControlError("IDEMPOTENCY_CONFLICT", 409)
                return self.reconcile(prior["workflow_id"])
            context = self.execution.context(request.session_id)
            policy = self.execution.manifest.rebalance_policy
            if policy.target_wavax_bps > context["max_wavax_exposure_bps"]:
                raise ControlError("TARGET_EXCEEDS_OWNER_EXPOSURE", 409)
            proposal, reason = propose_rebalance(
                context, policy, request.session_id, request.objective, self.clock()
            )
            if not proposal or not request.execute:
                return {
                    "operation": "TREASURY_REBALANCE",
                    "reason": reason,
                    "proposal": proposal.model_dump(mode="json") if proposal else None,
                    "executed": False,
                    "environment": context["environment"],
                }
            result = self.run(proposal, key)
            self.store.update(
                result["workflow_id"],
                result["status"],
                rebalance_request_hash=content_hash(request.model_dump(mode="json")),
            )
            return self.store.get(result["workflow_id"])
