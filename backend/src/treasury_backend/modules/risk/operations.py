"""Shared economic gate with fixed-operation effect checks; PGS supplies the universal bound."""

from treasury_contracts.crypto import content_hash
from treasury_contracts.v3 import ZERO


def assess_operation(intent, built, effects, context, now):
    reasons = []
    gas_economics = None
    if context.get("mvp"):
        max_cost = min(
            (int(effects["gas_used"]) * 12 // 10 + 10000) * int(context["max_gas_price_wei"]),
            int(context["max_tx_fee_wei"]),
        )
        combined = max_cost + int(context["gas_spent_or_reserved_wei"])
        gas_usd = (combined * int(context["price_intervals"][1][1]) + 10**18 - 1) // 10**18
        gas_economics = {
            "separate_from_trading_loss": True,
            "maximum_next_fee_wei": str(max_cost),
            "daily_spent_reserved_plus_next_reference_usd_e8": str(gas_usd),
        }
        if gas_usd > int(context["max_daily_execution_cost_usd_e8"]):
            reasons.append("SYSTEM_GAS_REFERENCE_BUDGET")
        if now >= context["oracle_valid_until"] or intent.deadline > context["oracle_valid_until"]:
            reasons.append("ORACLE_WINDOW_UNAVAILABLE")
    if (
        now >= intent.deadline
        or now - context["timestamp"] > context["proof_policy"]["max_oracle_age"]
    ):
        reasons.append("STALE_EVIDENCE")
    if (
        effects["build_hash"] != content_hash(built)
        or effects["source_block_hash"] != context["block_hash"]
        or effects["execution_status"] != "SUCCESS"
    ):
        reasons.append("UNVERIFIED_EFFECTS")
    if any(int(v) for v in effects["allowances"]):
        reasons.append("UNAUTHORIZED_APPROVAL")
    registry = [context["usdc"], context["wavax"], context["shares"], ZERO]
    i, j = registry.index(intent.token_in), registry.index(intent.token_out)
    deltas = [int(v) for v in effects["deltas"]]
    if deltas[i] != -int(intent.amount) or any(d < 0 for k, d in enumerate(deltas) if k != i):
        reasons.append("UNEXPECTED_TRANSFER")
    if intent.operation == "TOKEN_PAYMENT":
        if int(effects["received"]) < int(built["min_output"]):
            reasons.append("PAYEE_RECEIPT_SHORTFALL")
    elif deltas[j] < int(built["min_output"]):
        reasons.append("MIN_OUTPUT_NOT_MET")
    return {
        "result": "PASS" if not reasons else "FAIL",
        "reason_codes": reasons,
        "operation": intent.operation,
        "oracle_source": context["oracle"].get("source", context["oracle"].get("price_source")),
        "effects_hash": content_hash(effects),
        "balance_semantics": "measured on isolated EVM",
        "gas_economics": gas_economics,
    }
