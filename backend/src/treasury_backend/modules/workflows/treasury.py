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
from treasury_backend.modules.risk.operations import assess_operation, risk_observations
from treasury_backend.modules.temporal.operations import evaluate_operation
from treasury_backend.modules.workflows.observability import WorkflowTrace
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

    def _runtime(self, id_, intent, on_check=None):
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
        shield.state.fixed_scope(session, intent, self.clock())
        return ShieldRuntime(shield, session, on_check=on_check)

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
            trace = WorkflowTrace(self.store, id_, self.clock, self.progress)
            previous_activity = getattr(self.execution, "on_activity", None)
            self.execution.on_activity = trace.execution
            try:
                trace.move("OWNER_AUTHORITY", inputs={
                    "chain_id": intent.chain_id, "treasury": intent.treasury,
                    "session_id": intent.session_id,
                    "manifest": self.execution.manifest.model_dump(mode="json"),
                })
                context = self.execution.context(intent.session_id)
                self.store.event(id_, "OWNER_AUTHORITY", context, self.clock())
                trace.check("OWNER_CONTEXT", "PASS", expected={"policy_active": True, "session_active": True, "paused": False},
                            observed={k: context.get(k) for k in ("policy_active", "session_active", "paused", "block_number", "policy_version", "policy_expires_at", "session_expires_at", "manifest_hash")})
                trace.move("PLANNING", inputs={"typed_intent": intent.model_dump(mode="json")}, input_refs=["OWNER_AUTHORITY"])
                runtime = self._runtime(id_, intent, trace.shield)
                runtime.before("propose_fixed_operation", intent.model_dump(mode="json"))
                trace.check("AI_MODEL", "RUNNING")
                plan = plan_operation(self.control.shield.provider, intent,
                    on_complete=lambda value: trace.check("AI_MODEL", "PASS", observed=value))
                terms = ("operation", "token_in", "token_out", "recipient", "amount")
                trace.check("EXACT_INTENT", "PASS", expected={k: getattr(intent, k) for k in terms},
                            observed={k: getattr(plan, k) for k in terms})
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
                trace.move("BUILD", input_refs=["AGENT_PROPOSAL", "OWNER_AUTHORITY"])
                built = runtime.invoke(
                    "build_fixed_operation",
                    intent.model_dump(mode="json"),
                    lambda: self.execution.build(intent, context),
                )
                self.store.event(id_, "BUILD", built, self.clock())
                trace.check("FIXED_CALL", "PASS", observed={
                    "build_id": built["build_id"], "target": built["call"]["target"],
                    "function_selector": built["call"]["data"][:10],
                    "min_output": built["min_output"], "quote": built["quote"],
                    "route": built["route"], "context_hash": built["context_hash"],
                })
                self.store.update(id_, "BUILT", build_id=built["build_id"])
                trace.move("SIMULATION", input_refs=["BUILD", "OWNER_AUTHORITY"])
                effects = runtime.invoke(
                    "simulate_fixed_operation",
                    {"build_id": built["build_id"]},
                    lambda: self.execution.simulate(built, context),
                )
                self.store.event(id_, "SIMULATION", effects, self.clock())
                trace.check("SIMULATED_EFFECTS", "PASS" if effects["execution_status"] == "SUCCESS" else "FAIL",
                            expected="SUCCESS", observed={k: effects.get(k) for k in ("execution_status", "source_block", "source_block_hash", "deltas", "received", "allowances", "gas_used")})
                trace.move("RISK", input_refs=["SIMULATION", "BUILD", "OWNER_AUTHORITY"])
                assessed_at = self.clock()
                risk = assess_operation(intent, built, effects, context, assessed_at)
                for check in risk_observations(intent, built, effects, context, risk, assessed_at):
                    trace.check(**check)
                self.store.event(id_, "RISK", risk, self.clock())
                history = [
                    r
                    for r in self.store.history()
                    if r["workflow_id"] != id_ and r["intent"]["session_id"] == intent.session_id
                ]
                trace.move("ITAG", inputs={"history_count": len(history), "history_refs": [h["workflow_id"] for h in history[-12:]]},
                           input_refs=["AGENT_PROPOSAL", "BUILD", "OWNER_AUTHORITY"])
                temporal = evaluate_operation(
                    self.control.temporal, intent, built, context, history, runtime, plan, on_check=trace.check
                )
                self.store.event(id_, "ITAG", temporal, self.clock())
                if temporal["verdict"] != "PASS" or risk["result"] != "PASS":
                    raise ControlError("SECURITY_GATE_FAILED", 409)
                trace.move("PROOF", input_refs=["BUILD", "SIMULATION", "OWNER_AUTHORITY", "RISK", "ITAG"])
                proof = prove_operation(intent, built, effects, context,
                    on_query=lambda name, status, expected, observed: trace.check("Z3_" + name.upper(), status, expected=expected, observed=observed))
                self.store.event(id_, "PROOF", proof, self.clock())
                trace.check("PROOF_BUDGETS", "PASS", expected={
                    "risk_remaining_usd_e8": context["risk_remaining"],
                    "global_risk_remaining_usd_e8": context["global_risk_remaining"],
                    "payment_spend_remaining_usdc": context.get("payment_spend_remaining_usdc"),
                    "daily_payment_remaining_usdc": context.get("daily_payment_remaining_usdc"),
                    "max_wavax_balance": proof["phi"]["max_wavax_balance"],
                }, observed={"risk_debit_usd_e8": proof["risk_debit_usd_e8"], "spend_debit_usd_e8": proof["spend_debit_usd_e8"],
                             "receipt_credit": proof["phi"]["receipt_credit"], "next_wavax_balance": str(int(context["balances"][1])+int(effects["deltas"][1]))})
                runtime.defer_data(
                    "verify_constraints",
                    {"build_id": built["build_id"]},
                    {k: v for k, v in proof.items() if k != "queries"},
                )
                runtime.flush_data()
                trace.move("SDE", input_refs=["RISK", "ITAG", "PROOF", "BUILD", "SIMULATION"])
                decision = decide_operation(
                    intent, built, effects, risk, proof, temporal, self.clock()
                )
                self.store.event(id_, "SDE", decision, self.clock())
                trace.check("CONJUNCTIVE_DECISION", "PASS" if decision["verdict"] == "APPROVE" else "FAIL",
                            expected={"risk": "PASS", "itag": "PASS", "proof": "VERIFIED"},
                            observed={"risk": risk["result"], "itag": temporal["verdict"], "proof": proof["status"], "verdict": decision["verdict"], "reason_codes": decision["reason_codes"]})
                if decision["verdict"] != "APPROVE":
                    raise ControlError("DECISION_NOT_APPROVED", 409)
                self.store.update(id_, "PROVED", decision=decision)

                def revalidate():
                    trace.check("STATE_REVALIDATION", "RUNNING", expected={"context_hash": built["context_hash"]})
                    current = self.execution.revalidate(intent, built, context)
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
                    trace.check("STATE_REVALIDATION", "PASS", expected={"risk_hash": decision["risk_hash"], "context_hash": built["context_hash"]},
                                observed={"risk_hash": content_hash(current_risk), "context_hash": content_hash(context),
                                          "block_number": current.get("block_number") if current else None,
                                          "check_ids": shield_proof["check_ids"], "revision": shield_proof["revision"]})

                trace.move("ATTESTATION", input_refs=["SDE", "PROOF", "BUILD", "OWNER_AUTHORITY", "ITAG"])
                runtime.before(
                    "execute_fixed_operation",
                    {
                        **intent.model_dump(mode="json"),
                        "build_id": built["build_id"],
                        "intent_hash": intent.hash,
                        "proof_hash": proof["proof_hash"],
                    },
                )
                trace.check("SIGN_ONCE", "RUNNING", observed={"workflow_id": id_, "nonce": built["operation"]["nonce"]})
                with trace.buffered():
                    approval = self.store.sign_once(
                        id_,
                        lambda: self.control.attestor.attest_operation(
                            intent, built, effects, context, proof, decision, revalidate, on_check=trace.check
                        ),
                    )
                    signed = True
                trace.check("SIGN_ONCE", "PASS", observed={"workflow_id": id_, "typed_data_hash": approval["typed_data_hash"]})
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
                        "signed_fields": operation.model_dump(mode="json"),
                    },
                    self.clock(),
                )
                trace.move("EXACT_SIGNED_PREFLIGHT", input_refs=["ATTESTATION", "BUILD", "PROOF", "OWNER_AUTHORITY"])
                final = self.execution.preflight(
                    built, context, operation, phi, approval["signature"]
                )
                self.store.event(id_, "EXACT_SIGNED_PREFLIGHT", final, self.clock())
                trace.check("EXACT_SIGNED_TRANSACTION", "PASS" if final["execution_status"] == "SUCCESS" and final.get("exact_signed_preflight") else "UNKNOWN",
                            expected={"execution_status": "SUCCESS", "exact_signed_preflight": True, "constraints_hash": phi.hash},
                            observed={"execution_status": final["execution_status"], "exact_signed_preflight": final.get("exact_signed_preflight"), "constraints_hash": phi.hash})
                revalidate()
                trace.move("RELAY", input_refs=["EXACT_SIGNED_PREFLIGHT", "ATTESTATION", "PROOF"])
                outcome = self.execution.execute(built, operation, phi, approval["signature"])
                self.store.event(id_, "OUTCOME", outcome, self.clock())
                self.store.update(
                    id_, outcome["status"], outcome=outcome, environment=context["environment"]
                )
                trace.finish("PASS" if outcome["status"] == "CONFIRMED" else "FAIL" if outcome["status"] == "REVERTED" else "UNKNOWN", output_refs=["OUTCOME"])
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
                trace.fail(code, signed=signed)
                self.store.event(
                    id_, "REJECTION_OR_RECOVERY",
                    {"code": code, "signed": signed, "error_type": type(error).__name__},
                    self.clock(),
                )
                self.store.update(
                    id_, "SIGNED_REQUIRES_RECOVERY" if signed else "REJECTED", reason_code=code
                )
            finally:
                self.execution.on_activity = previous_activity
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
