"""Independent exact-rational specification oracle. No production imports or Z3.

For two assets, linear loss inequalities over a rectangular price domain attain
their maxima at its four vertices. This oracle enumerates those vertices; it does
not call the implementation being evaluated. Inputs are synthetic EVM observations.
"""

from fractions import Fraction as F
from itertools import product


def label(x):
    if (
        x["age"] >= 300
        or x["age"] + x["ttl"] > 300
        or not x["verified"]
        or x["allowance"]
        or x["extra_debit"]
        or x["amount"] > x["cash"]
        or any(lo <= 0 or hi < lo for lo, hi in x["prices"])
    ):
        return "REJECT"
    payment = x["operation"] == "payment"
    amount = x["amount"]
    received = min(amount, max(0, x["received"])) if payment else 0
    if payment and (received != amount or received < x["minimum"]):
        return "REJECT"
    if not payment and x["output"] < x["minimum"]:
        return "REJECT"
    floor_output = (
        0 if payment else max(x["minimum"], x["output"] * (10000 - x["tolerance"]) // 10000)
    )
    room = min(x["session_risk"], x["global_risk"])
    debit = F(0)
    for pu, pw in product(*x["prices"]):
        for output in [0] if payment else [x["output"], floor_output]:
            loss = F((amount - received) * pu, 10**6) - F(output * pw, 10**18)
            outgoing = F((amount - received) * pu, 10**6)
            if loss > outgoing * F(x["loss_bps"], 10000) + x["fixed_loss"] or loss > room:
                return "REJECT"
            debit = max(debit, loss)
    if -(-debit.numerator // debit.denominator) > room:
        return "REJECT"
    spend = max(amount * 100, -(-(amount * x["prices"][0][1]) // 10**6))
    if payment:
        if amount > min(x["payment_limit"], x["session_payment"], x["daily_payment"]):
            return "REJECT"
    elif spend > min(
        x["trade_limit"], x["session_spend"], x["daily_spend"], x["swap_session"], x["swap_daily"]
    ):
        return "REJECT"
    # Exposure at pessimistic compiled balances, priced with upper WAVAX/lower cash.
    if x["exposure_bps"] < 10000:
        stable = F((x["cash"] - amount) * x["prices"][0][0], 10**6)
        max_w = int(
            stable * x["exposure_bps"] * 10**18 / ((10000 - x["exposure_bps"]) * x["prices"][1][1])
        )
        if x["wavax"] + (0 if payment else x["output"]) > max_w:
            return "REJECT"
    return "APPROVE"
