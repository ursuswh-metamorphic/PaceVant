"""One pure PGS engine shared by the signer and guarded fork simulator.

Independent positive intervals, swap-only (payment credit zero), exact rational math.
No upstream code imported; see docs/migration/v2_1_pgs_reference_map.md.
"""

from fractions import Fraction
from pathlib import Path
from threading import RLock

import z3
from eth_abi import encode

from .v2 import (
    INT_MAX,
    AllowanceCap,
    BalanceBound,
    PostConditionsV2,
    ProofArtifactV2,
    call_hash,
    keccak,
    session_hash,
)

_SOLVER_LOCK = RLock()  # Z3's default native context is not thread-safe.


def loss_e8(deltas, registry, prices):
    """Exact USD-e8 loss and outgoing value; usable independently of Z3."""
    terms = [
        Fraction(d * p, 10**a.decimals)
        for d, a, p in zip(deltas, registry.assets, prices, strict=True)
    ]
    return -sum(terms), -sum(min(t, 0) for t in terms)


def ceil_nonnegative(value):
    value = max(Fraction(0), value)
    return (value.numerator + value.denominator - 1) // value.denominator


class PGSProofEngine:
    def __init__(self, timeout_ms=1000, query_sink=None, solver_factory=z3.Solver):
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= 5000:
            raise ValueError("solver timeout must be 1..5000ms")
        self.timeout_ms, self.query_sink, self.solver_factory = (
            timeout_ms,
            query_sink,
            solver_factory,
        )

    def prove(self, built, effects, policy, registry, oracle, session, now):
        with _SOLVER_LOCK:
            return self._prove(built, effects, policy, registry, oracle, session, now)

    def _prove(self, built, effects, policy, registry, oracle, session, now):
        base = dict(
            solver_version=z3.get_version_string(),
            source_hash=keccak(
                Path(__file__).read_bytes() + Path(__file__).with_name("v2.py").read_bytes()
            ),
            policy_hash=built.policy_hash,
            policy_config_hash=policy.hash,
            registry_hash=registry.hash,
            oracle_hash=oracle.hash,
            exact_call_hash=call_hash(built),
            evidence_root=effects.hash,
            session_context_hash=session_hash(session),
        )
        state = dict(
            check_mode="UNKNOWN",
            compile_mode="UNKNOWN",
            risk_bound="UNKNOWN",
            assumptions_satisfiable=False,
            compiled_region_satisfiable=False,
        )
        queries = []

        def result(status, reason, **extra):
            return ProofArtifactV2(
                status=status, reason=reason, query_hashes=tuple(queries), **base, **(state | extra)
            )

        try:
            self._validate(built, effects, policy, registry, oracle, session, now)
            prices = [z3.Real(f"price_{i}_usdE8") for i in range(2)]
            assumptions = [
                clause
                for p, b in zip(prices, oracle.prices, strict=True)
                for clause in (p >= int(b.low_usd_e8), p <= int(b.high_usd_e8), p > 0)
            ]

            def query(clause):
                solver = self.solver_factory()
                solver.set(timeout=self.timeout_ms)
                solver.add(*assumptions, clause)
                # sexpr uses traversal-local let names. to_smt2 embeds process-global
                # AST IDs, which change across otherwise identical signer rechecks.
                raw = (solver.sexpr() + "\n(check-sat)\n").encode()
                query_hash = keccak(raw)
                queries.append(query_hash)
                if self.query_sink:
                    self.query_sink(query_hash, raw)
                verdict = solver.check()
                label = (
                    "UNSAT" if verdict == z3.unsat else "SAT" if verdict == z3.sat else "UNKNOWN"
                )
                witness = None
                if label == "SAT":
                    model = solver.model()
                    witness = {
                        a.address: str(model.eval(p, model_completion=True))
                        for a, p in zip(registry.assets, prices, strict=True)
                    }
                return label, witness

            def expressions(deltas):
                terms = [
                    z3.RealVal(str(Fraction(d, 10**a.decimals))) * p
                    for d, a, p in zip(deltas, registry.assets, prices, strict=True)
                ]
                loss = -z3.Sum(terms)
                outgoing = -z3.Sum([t for d, t in zip(deltas, terms, strict=True) if d < 0])
                return loss, outgoing

            assumptions_status, _ = query(z3.BoolVal(True))
            if assumptions_status != "SAT":
                return result("INCONCLUSIVE", "PRICE_ASSUMPTIONS_NOT_SAT")
            state["assumptions_satisfiable"] = True
            deltas = [b.delta for b in effects.balances]
            loss, outgoing = expressions(deltas)
            relative = z3.RealVal(str(Fraction(policy.max_relative_loss_bps, 10000)))
            session_room = int(session.limit_usd_e8) - int(session.used_usd_e8)
            label, witness = query(
                z3.Or(
                    loss > relative * outgoing + int(policy.fixed_loss_usd_e8), loss > session_room
                )
            )
            state["check_mode"] = label
            if label != "UNSAT":
                return result(
                    "VIOLATED" if label == "SAT" else "INCONCLUSIVE",
                    "VALUE_POLICY_COUNTEREXAMPLE" if label == "SAT" else "PROOF_INCONCLUSIVE",
                    witness=witness,
                )

            for tau in dict.fromkeys((policy.tolerance_bps, 0)):
                lower = [d if d <= 0 else d * (10000 - tau) // 10000 for d in deltas]
                output_index = [a.address for a in registry.assets].index(built.token_out.lower())
                lower[output_index] = max(lower[output_index], int(built.min_amount_out_base_units))
                bounds = tuple(
                    BalanceBound(asset=a.address, min_delta=str(d))
                    for a, d in zip(registry.assets, lower, strict=True)
                )
                phi = PostConditionsV2(
                    balance_bounds=bounds,
                    allowance_caps=tuple(
                        AllowanceCap(token=a.address, spender=built.router) for a in registry.assets
                    ),
                )
                # Check feasible bounded post-state region separately; integer base-unit deltas.
                region = []
                for i, (b, c) in enumerate(zip(effects.balances, lower, strict=True)):
                    d = z3.Int(f"delta_{i}")
                    region += [
                        d >= c,
                        d >= -int(b.before),
                        d <= INT_MAX,
                        d + int(b.before) <= 2**256 - 1,
                    ]
                    if b.asset == built.token_in.lower():
                        region.append(d == -int(built.amount_in_base_units))
                feasible, _ = query(z3.And(*region))
                if feasible != "SAT":
                    return result(
                        "ERROR" if feasible == "UNSAT" else "INCONCLUSIVE", "PHI_REGION_NOT_SAT"
                    )
                state["compiled_region_satisfiable"] = True
                loss, outgoing = expressions(lower)
                label, witness = query(loss > relative * outgoing + int(policy.fixed_loss_usd_e8))
                state["compile_mode"] = label
                if label == "UNSAT":
                    break
                if label == "UNKNOWN":
                    return result("INCONCLUSIVE", "PROOF_INCONCLUSIVE")
            else:
                return result("VIOLATED", "PHI_COUNTEREXAMPLE", witness=witness)

            # Independent rational bound; select pessimistic interval corner per delta sign.
            worst_prices = [
                int(p.high_usd_e8 if d < 0 else p.low_usd_e8)
                for d, p in zip(lower, oracle.prices, strict=True)
            ]
            worst_loss, _ = loss_e8(lower, registry, worst_prices)
            debit = ceil_nonnegative(worst_loss)
            if debit >= 2**256:
                return result("ERROR", "RISK_DEBIT_OVERFLOW")
            label, _ = query(loss > debit)
            state["risk_bound"] = label
            if label != "UNSAT":
                return result("INCONCLUSIVE", "RISK_BOUND_UNVERIFIED")
            if debit > min(
                session_room, int(session.global_limit_usd_e8) - int(session.global_used_usd_e8)
            ):
                return result("VIOLATED", "SESSION_OR_GLOBAL_RISK_LIMIT")
            return result(
                "VERIFIED",
                "PROOF_VERIFIED",
                phi=phi,
                risk_debit_usd_e8=str(debit),
                fallback_tau_zero=tau == 0 and policy.tolerance_bps != 0,
            )
        except Exception:
            # No exception/unsupported encoding can yield an authorization.
            return result("ERROR", "PROOF_INVALID")

    @staticmethod
    def _validate(b, e, policy, registry, oracle, session, now):
        for value in (b, e, policy, registry, oracle, session):
            type(value).model_validate(value.model_dump(mode="json"))
        assets = [a.address for a in registry.assets]
        if type(now) is not int or b.chain_id not in (31337, 43113):
            raise ValueError("unsupported chain")
        if b.chain_id == 43113 and policy.authorization != "OWNER_APPROVED":
            raise ValueError("test policy cannot authorize Fuji")
        if (
            e.chain_id,
            e.vault,
            e.policy_hash,
            e.calldata_hash,
            e.intent_hash,
            e.registry_hash,
        ) != (
            b.chain_id,
            b.vault_address.lower(),
            b.policy_hash,
            b.calldata_hash,
            keccak(b.intent_id.encode()),
            registry.hash,
        ):
            raise ValueError("evidence binding")
        if (oracle.chain_id, oracle.vault, oracle.block_number, oracle.block_hash) != (
            b.chain_id,
            e.vault,
            e.block_number,
            e.block_hash,
        ):
            raise ValueError("oracle context")
        if not all(
            0 <= now - t <= policy.max_oracle_age
            for t in (oracle.timestamp, e.timestamp, session.timestamp)
        ):
            raise ValueError("stale snapshot/oracle/session")
        if not now < b.deadline or now > session.expires_at or now < session.starts_at:
            raise ValueError("expired approval/session")
        if (
            session.policy_hash != b.policy_hash
            or not session.active
            or session.session_id == "0x" + "00" * 32
            or int(session.limit_usd_e8) > int(policy.max_session_risk_usd_e8)
            or int(session.used_usd_e8) > int(session.limit_usd_e8)
            or session.global_limit_usd_e8 != policy.global_daily_risk_usd_e8
            or int(session.global_used_usd_e8) > int(session.global_limit_usd_e8)
        ):
            raise ValueError("session/budget")
        if session.block_number != e.block_number or session.block_hash != e.block_hash:
            raise ValueError("mixed snapshots")
        if (
            oracle.source_hash != policy.oracle_source_hash
            or [p.asset for p in oracle.prices] != assets
        ):
            raise ValueError("untrusted/incomplete price source")
        for p in oracle.prices:
            nominal, low, high = map(int, (p.nominal_usd_e8, p.low_usd_e8, p.high_usd_e8))
            if low * 10000 < nominal * (
                10000 - policy.oracle_band_bps
            ) or high * 10000 > nominal * (10000 + policy.oracle_band_bps):
                raise ValueError("band outside owner domain")
        if [v.asset for v in e.balances] != assets or [v.token for v in e.allowances] != assets:
            raise ValueError("incomplete registry/allowance coverage")
        if any(a.spender != b.router.lower() or int(a.after) != 0 for a in e.allowances):
            raise ValueError("residual/unknown spender")
        if e.unexpected_transfer or e.unauthorized_approval:
            raise ValueError("unsafe effects")
        if set((b.token_in.lower(), b.token_out.lower())) != set(assets):
            raise ValueError("pair")
        for a in registry.assets:
            d = next(v.delta for v in e.balances if v.asset == a.address)
            if not -INT_MAX <= d <= INT_MAX:
                raise ValueError("int256 delta overflow")
            if a.address == b.token_in.lower() and d != -int(b.amount_in_base_units):
                raise ValueError("not exact input")
            if a.address == b.token_out.lower() and d < int(b.min_amount_out_base_units):
                raise ValueError("output below minOut")
            if (
                a.address == b.token_in.lower()
                and a.decimals == 18
                and (
                    int(policy.max_wavax_per_swap) == 0
                    or int(b.amount_in_base_units) > int(policy.max_wavax_per_swap)
                )
            ):
                raise ValueError("reverse trade disabled/over cap")
        if (
            not 0 < int(b.amount_in_base_units) <= INT_MAX
            or not 0 < int(b.min_amount_out_base_units) <= INT_MAX
        ):
            raise ValueError("zero/overflow trade")
        data = bytes.fromhex(b.router_calldata[2:])
        expected = bytes.fromhex(
            keccak(b"exactInput(address,address,uint256,uint256,address)")[2:10]
        ) + encode(
            ["address", "address", "uint256", "uint256", "address"],
            [
                b.token_in,
                b.token_out,
                int(b.amount_in_base_units),
                int(b.min_amount_out_base_units),
                b.vault_address,
            ],
        )
        if data != expected or keccak(data) != b.calldata_hash:
            raise ValueError("malformed/exact calldata mismatch")
