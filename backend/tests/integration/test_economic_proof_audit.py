"""Economic audit regressions. No network, wallet secrets or public-chain writes."""

from fractions import Fraction

import pytest
import z3
from test_proof_v2 import case

from treasury_contracts.proof import PGSProofEngine


def test_nominal_only_interval_cannot_hide_owner_band_counterexample():
    args = list(case(output=485 * 10**16))
    assert PGSProofEngine().prove(*args).check_mode == "SAT"
    args[4] = args[4].model_copy(update={"prices": tuple(
        p.model_copy(update={"low_usd_e8": p.nominal_usd_e8,
                             "high_usd_e8": p.nominal_usd_e8})
        for p in args[4].prices
    )})
    result = PGSProofEngine().prove(*args)
    assert result.status == "ERROR" and result.phi is None, result


def test_fractional_owner_band_uses_conservative_outward_rounding():
    args = list(case(output=51 * 10**17))
    prices = []
    for p in args[4].prices:
        nominal = int(p.nominal_usd_e8) + 1
        prices.append(p.model_copy(update={
            "nominal_usd_e8": str(nominal),
            "low_usd_e8": str(nominal * 9900 // 10000),
            "high_usd_e8": str((nominal * 10100 + 9999) // 10000),
        }))
    args[4] = args[4].model_copy(update={"prices": tuple(prices)})
    result = PGSProofEngine().prove(*args)
    assert result.status == "VERIFIED", result
    for p in args[4].prices:
        assert int(p.low_usd_e8) <= Fraction(int(p.nominal_usd_e8) * 99, 100)
        assert int(p.high_usd_e8) >= Fraction(int(p.nominal_usd_e8) * 101, 100)


@pytest.mark.parametrize("relative,band,tau,output", [
    (300, 100, 40, 5 * 10**18),
    (300, 100, 1000, 5 * 10**18),
    (0, 0, 0, 5 * 10**18),
    (9999, 100, 1000, 6 * 10**18),
    (100, 10, 10, 5 * 10**18),
    (300, 100, 40, 51 * 10**17),
])
def test_independent_full_phi_counterexample_search(relative, band, tau, output):
    """Quantify actual deltas as well as prices, independently of corner reduction."""
    b, effects, policy, registry, oracle, session, now = args = case(
        relative=relative, band=band, tolerance=tau, output=output)
    proof = PGSProofEngine().prove(*args)
    assert proof.status == "VERIFIED", proof
    solver = z3.Solver()
    solver.set(timeout=5000)
    terms = []
    for i, (a, p, bound, measured) in enumerate(zip(
        registry.assets, oracle.prices, proof.phi.balance_bounds, effects.balances, strict=True
    )):
        price, delta = z3.Real(f"independent_price_{i}"), z3.Int(f"actual_delta_{i}")
        solver.add(price >= int(p.low_usd_e8), price <= int(p.high_usd_e8))
        solver.add(delta >= int(bound.min_delta), delta >= -int(measured.before),
                   delta <= 2**255 - 1, delta + int(measured.before) <= 2**256 - 1)
        if a.address == b.token_in.lower():
            solver.add(delta == -int(b.amount_in_base_units))
        terms.append(delta * price / 10**a.decimals)
    loss = -z3.Sum(terms)
    outgoing = -z3.Sum([z3.If(t < 0, t, 0) for t in terms])
    solver.add(z3.Or(
        loss > z3.RealVal(str(Fraction(relative, 10000))) * outgoing
        + int(policy.fixed_loss_usd_e8),
        loss > int(proof.risk_debit_usd_e8),
        loss > int(session.limit_usd_e8) - int(session.used_usd_e8),
        loss > int(session.global_limit_usd_e8) - int(session.global_used_usd_e8),
    ))
    assert solver.check() == z3.unsat, solver.sexpr()


@pytest.mark.parametrize("unknown_query", range(1, 6))
def test_solver_unknown_at_each_proof_stage_never_authorizes(unknown_query):
    calls = 0

    class TimeoutSolver:
        def __init__(self):
            self.inner = z3.Solver()

        def set(self, **kwargs):
            self.inner.set(**kwargs)

        def add(self, *args):
            self.inner.add(*args)

        def sexpr(self):
            return self.inner.sexpr()

        def check(self):
            nonlocal calls
            calls += 1
            # Deterministic timeout-result injection, not a claim of real timeout latency.
            return z3.unknown if calls == unknown_query else self.inner.check()

        def model(self):
            return self.inner.model()

    proof = PGSProofEngine(solver_factory=TimeoutSolver).prove(*case())
    assert calls == unknown_query
    assert proof.status == "INCONCLUSIVE" and proof.phi is None


def test_unsatisfiable_assumptions_are_not_a_vacuous_proof():
    class ContradictorySolver:
        def __init__(self):
            self.inner = z3.Solver()
            self.inner.add(z3.BoolVal(False))

        def set(self, **kwargs):
            self.inner.set(**kwargs)

        def add(self, *args):
            self.inner.add(*args)

        def sexpr(self):
            return self.inner.sexpr()

        def check(self):
            return self.inner.check()

    proof = PGSProofEngine(solver_factory=ContradictorySolver).prove(*case())
    assert proof.status == "INCONCLUSIVE"
    assert not proof.assumptions_satisfiable and proof.phi is None
