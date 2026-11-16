from uuid import uuid4

from app.models import Alignment, ChainContext, Mandate
from app.portfolio import MAX_BLOCK_DRIFT, policy_issues
from treasury_contract.wire import (
    BuiltTransaction,
    EconomicRiskAssessment,
    SecurityDecision,
    SimulationEvidence,
    TransactionProposal,
)

TTL = 30
HARD = {
    "TASK_MISALIGNED",
    "TOKEN_NOT_ALLOWED",
    "ROUTER_NOT_ALLOWED",
    "BAD_RECIPIENT",
    "POLICY_REVOKED",
    "UNEXPECTED_TRANSFER",
    "UNAUTHORIZED_APPROVAL",
    "UNSAFE_EXECUTION",
    "NONCE_REPLAY",
}
RECOVERABLE = {
    "TOKEN_EXPOSURE_LIMIT",
    "TRADE_SIZE_LIMIT",
    "BAD_PRICE_OR_SLIPPAGE",
    "REQUIRED_STRESS_NOT_SATISFIED",
}


def simulation_issues(mandate: Mandate, built: BuiltTransaction, evidence: SimulationEvidence):
    baseline = evidence.baseline
    issues = []
    if baseline.unexpected_transfer:
        issues.append("UNEXPECTED_TRANSFER")
    if baseline.unauthorized_approval:
        issues.append("UNAUTHORIZED_APPROVAL")
    if any(test.status == "UNSAFE_EXECUTION" for test in evidence.stress_tests):
        issues.append("UNSAFE_EXECUTION")
    statuses = {test.scenario_id: test for test in evidence.stress_tests}
    if (
        baseline.execution_status != "SUCCESS"
        or evidence.verification_status != "COMPLETE"
        or len(statuses) != len(evidence.stress_tests)
        or set(mandate.required_stress) - statuses.keys()
    ):
        issues.append("SIMULATION_INCOMPLETE")
    if baseline.execution_status == "SUCCESS" and (
        int(baseline.token_in_delta_base_units) != -int(built.amount_in_base_units)
        or int(baseline.token_out_delta_base_units) < int(built.min_amount_out_base_units)
        or int(built.min_amount_out_base_units) <= 0
        or int(baseline.gas_used) <= 0
    ):
        issues.append("HASH_MISMATCH")
    for test in statuses.values():
        if test.status == "INCONCLUSIVE":
            issues.append("SIMULATION_INCOMPLETE")
        if test.status == "SUCCESS_SAFE" and (
            test.output_base_units is None
            or int(test.output_base_units) < int(built.min_amount_out_base_units)
            or test.revert_reason is not None
        ):
            issues.append("SIMULATION_INCOMPLETE")
        if test.status == "PROTECTED_REVERT":
            if test.revert_reason != "MIN_OUTPUT_NOT_MET" or test.output_base_units is not None:
                issues.append("SIMULATION_INCOMPLETE")
            elif mandate.required_stress.get(test.scenario_id) == "SUCCESS_REQUIRED":
                issues.append("REQUIRED_STRESS_NOT_SATISFIED")
    return issues


def decide(
    mandate: Mandate,
    proposal: TransactionProposal,
    alignment: Alignment,
    context: ChainContext | None,
    now: int,
    *,
    built: BuiltTransaction | None = None,
    evidence: SimulationEvidence | None = None,
    risk: EconomicRiskAssessment | None = None,
    provenance_issues: list[str] | None = None,
) -> SecurityDecision:
    reasons = list(alignment.reason_codes)
    if context is None:
        reasons.append("SIMULATION_INCOMPLETE")
    else:
        reasons.extend(policy_issues(mandate, context, now))
    if alignment.verdict == "MISALIGNED":
        reasons.append("TASK_MISALIGNED")
    elif alignment.verdict == "UNCERTAIN":
        reasons.append("TASK_UNCERTAIN")
    if provenance_issues:
        reasons.extend(provenance_issues)
    if now >= proposal.deadline:
        reasons.append("STALE_REQUIRES_REEVALUATION")
    if built and evidence:
        reasons.extend(simulation_issues(mandate, built, evidence))
        if context is not None:
            if (
                evidence.bytecode_hash != context.bytecode_hash
                or not 0 <= context.block_number - evidence.fork_block <= MAX_BLOCK_DRIFT
            ):
                reasons.append("HASH_MISMATCH")
            if context.nonce_used is not False:
                reasons.append("NONCE_REPLAY" if context.nonce_used else "SIMULATION_INCOMPLETE")
    if risk:
        reasons.extend(risk.violations)
        if risk.result == "INCONCLUSIVE":
            reasons.append("RISK_INCONCLUSIVE")
        if built and (risk.intent_id, risk.build_id) != (built.intent_id, built.build_id):
            reasons.append("HASH_MISMATCH")

    verdict = "ESCALATE"
    if HARD.intersection(reasons):
        verdict = "REJECT"
    elif set(reasons) - RECOVERABLE:
        verdict = "ESCALATE"
    elif reasons:
        verdict = "REPLAN"
    elif alignment.verdict == "ALIGNED" and built and evidence and risk and risk.result == "PASS":
        verdict = "APPROVE"
    else:
        reasons.append("SIMULATION_INCOMPLETE")
    return SecurityDecision(
        decision_id=f"decision_{uuid4().hex}",
        intent_id=proposal.intent_id,
        build_id=built.build_id if built else None,
        verdict=verdict,
        reason_codes=list(dict.fromkeys(reasons)),
        policy_hash=mandate.policy_hash,
        calldata_hash=built.calldata_hash if built else None,
        simulation_evidence_root=evidence.evidence_root if evidence else None,
        mandate_version=mandate.version,
        snapshot_id=risk.snapshot_id if risk else None,
        created_at=now,
        expires_at=min(now + TTL, proposal.deadline, mandate.expires_at),
    )
