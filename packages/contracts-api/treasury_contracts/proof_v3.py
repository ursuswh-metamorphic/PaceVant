"""Payment-aware PGS over the fixed V3 registry, sharing V2 exact math/solver lock.

Guarantee assumes trusted token balance semantics and owner-approved share valuation.
The owner share-rate interval is relative to underlying USDC, not an independent USD peg.
"""

from fractions import Fraction
from pathlib import Path

import z3

from .crypto import content_hash, keccak
from .proof import _SOLVER_LOCK, ceil_nonnegative, owner_price_interval
from .v3 import KINDS, ZERO, Constraints


class ProofRejected(ValueError):
    """Failed obligations retain their real SMT queries and SAT witness; never an approval."""
    def __init__(self,reason,queries,counterexample=None):
        super().__init__(reason)
        self.queries=list(queries)
        self.counterexample=counterexample


def prove_operation(intent, build, effects, context):
    with _SOLVER_LOCK:
        return _prove(intent, build, effects, context)


def _prove(intent, build, effects, context):
    if build["intent"] != intent.model_dump(mode="json") or build["operation"]["intentHash"] != intent.hash:
        raise ValueError("INTENT_BUILD_MISMATCH")
    if context.get("mvp"):
        if intent.operation not in {"TOKEN_SWAP","TOKEN_PAYMENT"}:
            raise ValueError("MVP_UNSUPPORTED_OPERATION")
        if intent.operation=="TOKEN_PAYMENT" and intent.token_in!=context["usdc"]:
            raise ValueError("MVP_CIRCLE_USDC_PAYMENT_REQUIRED")
        if int(effects["deltas"][2]) or int(effects["deltas"][3]):
            raise ValueError("UNEXPECTED_DISABLED_ASSET_MOVEMENT")
    if effects["execution_status"] != "SUCCESS" or effects["build_hash"] != content_hash(build):
        raise ValueError("SIMULATION_INCOMPLETE")
    if effects["source"] != "LOCAL_FORK_EVM" or not effects["gas_used"]:
        raise ValueError("UNVERIFIED_EFFECTS")
    if any(int(v) != 0 for v in effects["allowances"]):
        raise ValueError("UNAUTHORIZED_APPROVAL")
    before = [int(v) for v in effects["before"]]
    deltas = [int(v) for v in effects["deltas"]]
    if before != [int(v) for v in context["balances"]] or len(deltas) != 4:
        raise ValueError("HASH_MISMATCH")
    registry = [context["usdc"], context["wavax"], context["shares"], ZERO]
    i = registry.index(intent.token_in)
    j = registry.index(intent.token_out)
    if deltas[i] != -int(intent.amount):
        raise ValueError("UNEXPECTED_TRANSFER")
    if any(d < 0 for k, d in enumerate(deltas) if k != i):
        raise ValueError("UNEXPECTED_TRANSFER")
    if intent.operation != "TOKEN_PAYMENT" and deltas[j] < int(build["min_output"]):
        raise ValueError("MIN_OUTPUT_NOT_MET")
    credit = 0
    if intent.operation == "TOKEN_PAYMENT":
        credit = min(int(intent.amount), max(0, int(effects["received"])))
        if credit < int(build["min_output"]):
            raise ValueError("RECEIPT_NOT_MET")
    policy = context["proof_policy"]
    # The exact minOut compiled by the trusted builder is enforced, with no retry that relaxes it.
    minimum = max(int(build["min_output"]), deltas[j] * (10000 - int(policy["tolerance_bps"])) // 10000) if i != j else 0
    lower = [-int(intent.amount) if k == i else minimum if k == j and i != j else 0
             for k in range(4)]
    units = [10**6, 10**18, int(context["share_unit"]), 10**18]
    intervals = context["price_intervals"]
    prices = [z3.Real(f"price_{k}_usdE8") for k in range(4)]
    assumptions = [c for p, (lo, hi) in zip(prices, intervals, strict=True) for c in (p >= int(lo), p <= int(hi))]
    assumptions.extend((prices[2] >= prices[0] * z3.RealVal(str(Fraction(int(context["share_rate_low"]), 10**6))),
                        prices[2] <= prices[0] * z3.RealVal(str(Fraction(int(context["share_rate_high"]), 10**6))),
                        prices[3] == prices[1]))
    if any(int(lo) <= 0 or int(hi) < int(lo) for lo, hi in intervals):
        raise ValueError("INVALID_PRICE_BAND")
    queries = []

    def query(name, clauses, expected):
        solver = z3.Solver()
        solver.set(timeout=2000)
        solver.add(*assumptions, *clauses)
        # sexpr uses query-local let names; to_smt2 embeds process-global AST IDs.
        raw = solver.sexpr() + "\n(check-sat)\n"
        result = str(solver.check()).upper()
        queries.append({"name": name, "result": result, "smt2": raw, "hash": keccak(raw.encode())})
        if result != expected:
            witness={str(p):str(solver.model().eval(p,model_completion=True)) for p in prices} if result=="SAT" else None
            raise ProofRejected("PROOF_" + name.upper() + "_" + result,queries,witness)

    def expressions(ds):
        terms = [z3.RealVal(str(Fraction(d, u))) * p for d, u, p in zip(ds, units, prices, strict=True)]
        credited = z3.RealVal(str(Fraction(credit, units[i]))) * prices[i]
        return -z3.Sum(terms) - credited, -z3.Sum([min(Fraction(d, u), 0) * p for d, u, p in zip(ds, units, prices, strict=True)]) - credited

    relative = z3.RealVal(str(Fraction(policy["max_relative_loss_bps"], 10000)))
    fixed = int(policy["fixed_loss_usd_e8"])
    room = min(int(context["risk_remaining"]), int(context["global_risk_remaining"]))
    query("feasible_prices", [], "SAT")
    loss, outgoing = expressions(deltas)
    query("check_mode", [z3.Or(loss > relative * outgoing + fixed, loss > room)], "UNSAT")
    if any(b + d < 0 for b, d in zip(before, lower, strict=True)):
        raise ValueError("INFEASIBLE_COMPILED_REGION")
    # For s<1, L-sV is nonincreasing in each delta; the lower corner is conservative.
    loss, outgoing = expressions(lower)
    query("compile_mode", [loss > relative * outgoing + fixed], "UNSAT")
    net = [d + (credit if k == i else 0) for k, d in enumerate(lower)]
    rate = int(context["share_rate_low" if net[2] >= 0 else "share_rate_high"])
    stable = Fraction(net[0], units[0]) + Fraction(net[2] * rate, units[2] * 10**6)
    volatile = Fraction(net[1], units[1]) + Fraction(net[3], units[3])
    worst_loss = -stable * int(intervals[0][0 if stable >= 0 else 1]) - volatile * int(intervals[1][0 if volatile >= 0 else 1])
    debit = ceil_nonnegative(worst_loss)
    if debit > room:
        raise ValueError("CUMULATIVE_RISK_EXHAUSTED")
    query("risk_bound", [loss > debit], "UNSAT")
    spend = ceil_nonnegative(Fraction(int(intent.amount) * int(intervals[i][1]), units[i]))
    if intent.token_in == context["usdc"]:
        spend = max(spend, int(intent.amount) * 100)
    if not (context.get("mvp") and intent.operation=="TOKEN_PAYMENT") and spend > min(int(context["spend_remaining"]), int(context["daily_spend_remaining"]), int(context["max_operation_usd_e8"])):
        raise ValueError("SPEND_BUDGET_EXHAUSTED")
    if context.get("mvp"):
        if intent.operation=="TOKEN_PAYMENT":
            if credit!=int(intent.amount) or credit>min(int(context["payment_spend_remaining_usdc"]),
                int(context["daily_payment_remaining_usdc"]),int(context["max_payment_usdc"])):
                raise ValueError("PAYMENT_SPENDING_LIMIT")
        elif spend>min(int(context["swap_spend_remaining"]),int(context["daily_swap_remaining"])):
            raise ValueError("SWAP_SPENDING_LIMIT")
    # Non-WAVAX value at its lower bound, WAVAX at upper price. This cap stays atomic.
    non_wavax = sum(Fraction((b + d) * int(intervals[k][0]), units[k])
                    for k, (b, d) in enumerate(zip(before, lower, strict=True)) if k != 1)
    cap_bps = context["max_wavax_exposure_bps"]
    max_wavax = (2**255 - 1 if cap_bps == 10000 else
                 int(non_wavax * cap_bps * units[1] / ((10000 - cap_bps) * int(intervals[1][1]))))
    if before[1] + deltas[1] > max_wavax:
        raise ValueError("TOKEN_EXPOSURE_LIMIT")
    phi = Constraints(before_balances=tuple(str(v) for v in before), min_deltas=tuple(str(v) for v in lower),
                      receipt_credit=str(credit), max_wavax_balance=str(max_wavax))
    base = {"version": 3, "status": "VERIFIED", "kind": KINDS[intent.operation],
            "intent_hash": intent.hash, "build_hash": content_hash(build), "evidence_root": content_hash(effects),
            "context_hash": content_hash(context), "phi": phi.model_dump(mode="json"), "phi_hash": phi.hash,
            "risk_debit_usd_e8": str(debit), "spend_debit_usd_e8": str(spend),
            "solver_version": z3.get_version_string(), "queries": queries,
            "source_hash": keccak(Path(__file__).read_bytes() + Path(__file__).with_name("v3.py").read_bytes()),
            "assumptions": ["trusted balanceOf semantics", "complete fixed registry", "owner share-rate interval",
                            "prices inside independently validated bands", "attestor integrity"]}
    return base | {"proof_hash": content_hash(base)}


def price_intervals(usdc, wavax, band, rate_low, rate_high):
    u = owner_price_interval(usdc, band)
    w = owner_price_interval(wavax, band)
    # Price per whole share, not a false 1:1 share/USDC identity.
    shares = (u[0] * rate_low // 10**6, (u[1] * rate_high + 10**6 - 1) // 10**6)
    return [[str(v) for v in interval] for interval in (u, w, shares, w)]
