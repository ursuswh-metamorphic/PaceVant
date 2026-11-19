from app.portfolio.observations import content_hash
from app.temporal.models import ConstraintAssessment, Violation

PRIORITY = {"PASS": 0, "REPLAN": 1, "ESCALATE": 2, "REJECT": 3}


def provenance_matches(spec, link, mandate, proposal, mode, now):
    return (
        spec.status == "AUTHENTICATED"
        and spec.revision == link["revision"]
        and spec.mode == mode
        and now < spec.terms.deadline
        and proposal.deadline <= spec.terms.deadline
        and content_hash(mandate.model_dump()) == spec.mandate_hash
        and (proposal.mandate_id, proposal.mandate_version) == (mandate.mandate_id, mandate.version)
        and proposal.chain_id == spec.chain_id
        and proposal.vault_address.lower() == spec.vault_address.lower()
        and proposal.recipient.lower() == spec.vault_address.lower()
        and proposal.token_in.lower() == spec.token_in.lower()
        and proposal.token_out.lower() == spec.token_out.lower()
        and proposal.router.lower() == spec.router.lower()
    )


def confirmed_state(entry, spec):
    outcome = entry.get("outcome")
    if not outcome or entry["invalidated"]:
        return None
    proof = outcome["verification"]
    state = entry["state"]
    expected = {"CONFIRMED": "SUCCESS", "REVERTED": "REVERTED"}.get(state)
    amount = entry["build"]["amount_in_base_units"]
    if (
        expected
        and proof["receipt_status"] == expected
        and proof["canonical"] is True
        and proof["verification_status"] == "VERIFIED"
        and outcome["state"] == state
        and not outcome["reason_codes"]
        and outcome["attribution_status"] == "EXACT_SNAPSHOT_AND_TRANSACTION_LOGS"
        and proof["decision_id"] == entry["decision_id"]
        and proof["build_id"] == outcome["build_id"] == entry["build"]["build_id"]
        and outcome["policy_hash"] == spec.policy_hash
        and proof["chain_id"] == spec.chain_id
        and proof["vault_address"].lower() == spec.vault_address.lower()
        and proof["tx_hash"]
        and proof["tx_hash"] == entry["tx_hash"]
        and proof["block_hash"]
        and proof["block_number"] is not None
        and len(entry.get("snapshots", {})) == 2
        and proof["token_in_delta_base_units"] == ("-" + amount if state == "CONFIRMED" else "0")
        and proof.get("token_out_delta_base_units") is not None
        and (
            int(proof["token_out_delta_base_units"])
            >= int(entry["build"]["min_amount_out_base_units"])
            if state == "CONFIRMED"
            else proof["token_out_delta_base_units"] == "0"
        )
    ):
        return state
    return None


def verify(spec, link, mandate, proposal, built, mode, now, entries):
    violations = []
    candidate = proposal.intent_id
    ref = f"{spec.spec_id}:{spec.revision}"

    def fail(policy, code, detail, *nodes, verdict="REJECT"):
        violations.append(
            Violation(
                policy=policy,
                code=code,
                verdict=verdict,
                node_ids=list(dict.fromkeys([candidate, *nodes])),
                detail=detail,
            )
        )

    if (
        spec.status != "AUTHENTICATED"
        or spec.revision != link["revision"]
        or now >= spec.terms.deadline
    ):
        fail(
            "TASK_REVISION_AND_CANCELLATION",
            "ITAG_INVALID_INTENT_REVISION",
            "The workflow authorization is no longer active for this revision.",
            ref,
        )
    if not provenance_matches(spec, link, mandate, proposal, mode, now):
        fail(
            "AUTHORIZED_ACTION_PROVENANCE",
            "ITAG_ACTION_SCOPE_MISMATCH",
            "The candidate does not match the authenticated mandate, chain, tokens, recipient or deadline.",
            ref,
        )
    if not built:
        fail(
            "AUTHORIZED_ACTION_PROVENANCE",
            "ITAG_BUILD_UNAVAILABLE",
            "A verified transaction build is required for approval.",
            verdict="ESCALATE",
        )
    elif (
        built.amount_in_base_units != proposal.amount_in_base_units
        or built.intent_id != candidate
        or built.chain_id != spec.chain_id
        or built.policy_hash != spec.policy_hash
        or built.vault_address.lower() != spec.vault_address.lower()
        or built.router.lower() != spec.router.lower()
        or built.token_in.lower() != spec.token_in.lower()
        or built.token_out.lower() != spec.token_out.lower()
        or built.deadline != proposal.deadline
    ):
        fail(
            "AUTHORIZED_ACTION_PROVENANCE",
            "ITAG_BUILD_MISMATCH",
            "The built transaction differs from its authenticated candidate.",
            ref,
        )

    spent = reserved = 0
    completed = {}
    for entry in entries:
        previous = entry["build"]
        prior_node = previous["intent_id"]
        amount = int(previous["amount_in_base_units"])
        if (
            previous["chain_id"] != spec.chain_id
            or previous["vault_address"].lower() != spec.vault_address.lower()
            or previous["policy_hash"] != spec.policy_hash
        ):
            fail(
                "CROSS_WORKFLOW_CONSISTENCY",
                "ITAG_HISTORY_SCOPE_MISMATCH",
                "A prior workflow has a different chain, vault or policy scope.",
                prior_node,
                verdict="ESCALATE",
            )
        verified = confirmed_state(entry, spec)
        if verified == "CONFIRMED":
            spent += amount
            completed[entry["step_id"]] = "outcome:" + entry["decision_id"]
        elif verified != "REVERTED":
            reserved += amount
            if entry["outcome"] or entry["state"] in {"CONFIRMED", "REVERTED", "RECEIPT_MISMATCH"}:
                fail(
                    "REORG_AND_HISTORY_INTEGRITY",
                    "ITAG_UNVERIFIED_OUTCOME",
                    "Prior execution lacks a canonical verified receipt and reconciled snapshots.",
                    "outcome:" + entry["decision_id"] if entry["outcome"] else prior_node,
                    verdict="ESCALATE",
                )
            else:
                fail(
                    "PENDING_OR_UNKNOWN_OUTCOME",
                    "ITAG_PENDING_RESERVATION",
                    "A signed or submitted action still reserves this intent's budget.",
                    prior_node,
                    verdict="ESCALATE",
                )
    remaining = max(0, int(spec.terms.total_budget) - spent - reserved)
    amount = int(proposal.amount_in_base_units)
    step = next((s for s in spec.terms.steps if s.step_id == link["step_id"]), None)
    if not step:
        fail(
            "DEPENDENCY_ORDERING",
            "ITAG_UNKNOWN_STEP",
            "The selected step is missing from the intent.",
            ref,
        )
    else:
        if step.step_id in completed and spec.terms.kind != "BOUNDED_SWAP":
            fail(
                "TASK_COMPLETION",
                "ITAG_STEP_ALREADY_COMPLETE",
                "A verified prior outcome already completed this step.",
                completed[step.step_id],
            )
        if any(dep not in completed for dep in step.prerequisites):
            fail(
                "DEPENDENCY_ORDERING",
                "ITAG_DEPENDENCY_UNMET",
                "Every prerequisite needs a canonical successful outcome.",
                ref,
            )
        if amount < int(step.min_amount):
            fail(
                "CUMULATIVE_TASK_BUDGET",
                "ITAG_BELOW_AUTHORIZED_AMOUNT",
                "The candidate is below the authorized step minimum.",
                ref,
            )
        if amount > min(int(step.max_amount), remaining):
            # Preserve budget for later required steps rather than make the ordered plan impossible.
            can_reduce = (
                int(step.min_amount) <= remaining and amount > int(step.min_amount) and not reserved
            )
            fail(
                "CUMULATIVE_TASK_BUDGET",
                "ITAG_BUDGET_EXCEEDED",
                "The candidate exceeds the step maximum or remaining task budget.",
                ref,
                verdict="REPLAN" if can_reduce else "REJECT",
            )
        later_min = sum(
            int(s.min_amount)
            for s in spec.terms.steps
            if s.step_id != step.step_id and s.step_id not in completed
        )
        if spec.terms.kind == "ORDERED_TASK" and amount + later_min > remaining:
            fail(
                "CUMULATIVE_TASK_BUDGET",
                "ITAG_FUTURE_STEP_BUDGET",
                "This action would leave insufficient budget for the remaining required steps.",
                ref,
                verdict="REPLAN" if int(step.min_amount) + later_min <= remaining else "REJECT",
            )
    if spec.terms.kind == "BOUNDED_SWAP" and spent >= int(spec.terms.total_budget):
        fail(
            "TASK_COMPLETION",
            "ITAG_BUDGET_ALREADY_SPENT",
            "The verified task budget is exhausted.",
            ref,
        )
    verdict = max((v.verdict for v in violations), key=PRIORITY.__getitem__, default="PASS")
    return ConstraintAssessment(
        verdict=verdict,
        violations=violations,
        spent=str(spent),
        reserved=str(reserved),
        remaining=str(remaining),
    )
