"""Integer-only trigger/size calculation. LLM explanations cannot change these numbers."""

from treasury_contracts.v3 import OperationIntent


def propose_rebalance(context, policy, session_id, objective, now):
    usdc, wavax = (int(v) for v in context["balances"][:2])
    pu, pw = (int(v) for v in context["nominal_prices"])
    # Allocation mandate applies to liquid USDC/WAVAX; shares/native are separately disclosed.
    value_usdc = usdc * pu // 10**6
    value_wavax = wavax * pw // 10**18
    total = value_usdc + value_wavax
    if total <= 0:
        return None, "EMPTY_LIQUID_PORTFOLIO"
    deviation = value_wavax * 10000 - total * policy.target_wavax_bps
    if abs(deviation) < total * policy.minimum_deviation_bps:
        return None, "WITHIN_TARGET_BAND"
    auth = context["authority"]
    if not (auth["operation_mask"] & 16):
        raise ValueError("REBALANCE_NOT_AUTHORIZED")
    if auth["last_rebalance"] and now < auth["last_rebalance"] + auth["cooldown"]:
        return None, "REBALANCE_COOLDOWN"
    size = min(abs(deviation) // 10000, int(policy.max_trade_usd_e8), int(context["max_operation_usd_e8"]),
               int(context["spend_remaining"]), int(context["daily_spend_remaining"]))
    if size < int(policy.minimum_trade_usd_e8):
        return None, "BELOW_MINIMUM_ECONOMIC_SIZE"
    sell_wavax = deviation > 0
    unit, price, balance = (10**18, pw, wavax) if sell_wavax else (10**6, pu, usdc)
    # Upper-band spend sizing prevents rounding or oracle-band expansion from exceeding the cap.
    high = int(context["price_intervals"][1 if sell_wavax else 0][1])
    amount = min(balance, size * unit // max(price, high))
    if amount <= 0:
        return None, "ROUNDING_TO_ZERO"
    return OperationIntent(operation="TOKEN_SWAP", chain_id=context["chain_id"], treasury=context["treasury"],
                           session_id=session_id, token_in=context["wavax" if sell_wavax else "usdc"],
                           token_out=context["usdc" if sell_wavax else "wavax"], recipient=context["treasury"],
                           amount=str(amount), slippage_bps=min(context["max_slippage_bps"], 40),
                           deadline=min(context.get("oracle_valid_until",2**53-1),context["timestamp"] + context["max_ttl"], now + context["max_ttl"],
                                        context["session_expires_at"], context["policy_expires_at"]),
                           objective=objective, rebalance=True), "REBALANCE_REQUIRED"
