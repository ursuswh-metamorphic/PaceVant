from app.errors import ControlError
from app.portfolio.observations import content_hash
from app.temporal.models import IntentSpec


def make_spec(terms, mandate, mode, spec_id, revision, now, status):
    budget = int(terms.total_budget)
    ids = [step.step_id for step in terms.steps]
    limit = int(mandate.max_usdc_per_swap_base_units)
    if terms.mandate_id != mandate.mandate_id or not now < terms.deadline <= mandate.expires_at:
        raise ControlError("ITAG_INTENT_SCOPE_OR_DEADLINE", 422)
    if not budget or len(set(ids)) != len(ids):
        raise ControlError("ITAG_INVALID_TASK_BUDGET", 422)
    if terms.kind != "ORDERED_TASK" and len(terms.steps) != 1:
        raise ControlError("ITAG_INVALID_TASK_STEPS", 422)
    for index, step in enumerate(terms.steps):
        minimum, maximum = int(step.min_amount), int(step.max_amount)
        if not 0 < minimum <= maximum <= min(limit, budget):
            raise ControlError("ITAG_INVALID_STEP_AMOUNT", 422)
        if len(set(step.prerequisites)) != len(step.prerequisites) or not set(
            step.prerequisites
        ).issubset(ids[:index]):
            raise ControlError("ITAG_INVALID_DEPENDENCY", 422)
        if terms.kind == "ORDERED_TASK" and index and ids[index - 1] not in step.prerequisites:
            raise ControlError("ITAG_ORDERED_STEP_REQUIRES_PREDECESSOR", 422)
        if terms.kind == "ONE_SHOT_SWAP" and minimum != maximum:
            raise ControlError("ITAG_ONE_SHOT_REQUIRES_EXACT_AMOUNT", 422)
    if sum(int(step.min_amount) for step in terms.steps) > budget:
        raise ControlError("ITAG_UNREACHABLE_COMPLETION", 422)
    return IntentSpec(
        spec_id=spec_id,
        revision=revision,
        status=status,
        terms=terms,
        mode=mode,
        chain_id=mandate.chain_id,
        vault_address=mandate.vault_address,
        token_in=mandate.token_in,
        token_out=mandate.token_out,
        router=mandate.router,
        mandate_hash=content_hash(mandate.model_dump()),
        policy_hash=mandate.policy_hash,
        authorization_source="PROPOSAL_ONLY" if status == "PROPOSED" else "OPERATOR_API",
        recorded_at=now,
        completion="BUDGET_SPENT" if terms.kind == "BOUNDED_SWAP" else "ALL_STEPS_VERIFIED",
    )
