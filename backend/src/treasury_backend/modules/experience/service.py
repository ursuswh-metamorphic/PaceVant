from treasury_backend.modules.persistence import Store

REDUCE_AMOUNT = {"BAD_PRICE_OR_SLIPPAGE", "REQUIRED_STRESS_NOT_SATISFIED"}


def next_amount(store: Store, workflow_id: str, current_amount: int) -> int | None:
    attempts = store.attempts(workflow_id)
    latest = attempts[-1]
    if latest["decision"]["verdict"] != "REPLAN":
        return None
    reasons = set(latest["decision"]["reason_codes"])
    suggested = min(latest["suggested_amount"], current_amount - 1)
    if reasons & REDUCE_AMOUNT:
        suggested = min(suggested, current_amount // 2)
    prior_amounts = {int(attempt["proposal"]["amount_in_base_units"]) for attempt in attempts}
    return suggested if suggested > 0 and suggested not in prior_amounts else None
