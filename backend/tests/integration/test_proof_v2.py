import itertools
from fractions import Fraction

import pytest
import z3
from eth_abi import encode
from pydantic import ValidationError

from treasury_contracts.models import BuiltTransaction
from treasury_contracts.proof import PGSProofEngine, ceil_nonnegative, loss_e8
from treasury_contracts.v2 import (
    AllowanceRead,
    Asset,
    BalanceBound,
    BalanceRead,
    EffectEvidenceV2,
    OracleEvidence,
    PostConditionsV2,
    Price,
    ProofPolicy,
    Registry,
    SessionContext,
    keccak,
)

NOW = 1800000000
U, W, V, R = ["0x" + f"{n:040x}" for n in (0x1111, 0x2222, 0x3333, 0x4444)]
H = keccak(b"TEST_ONLY_policy")
BH = keccak(b"TEST_ONLY_block")


def case(output=5 * 10**18, tolerance=40, fixed="0", band=100, relative=300):
    registry = Registry(assets=(Asset(address=U, decimals=6), Asset(address=W, decimals=18)))
    policy = ProofPolicy(
        max_wavax_per_swap=str(10 * 10**18),
        max_relative_loss_bps=relative,
        fixed_loss_usd_e8=fixed,
        oracle_band_bps=band,
        tolerance_bps=tolerance,
        max_oracle_age=60,
        max_session_risk_usd_e8="1000000000",
        global_daily_risk_usd_e8="2000000000",
        oracle_source_hash=keccak(b"TRUSTED_TEST_ORACLE"),
        authorization="TEST_ONLY",
    )
    data = bytes.fromhex(
        keccak(b"exactInput(address,address,uint256,uint256,address)")[2:10]
    ) + encode(
        ["address", "address", "uint256", "uint256", "address"], [U, W, 100 * 10**6, 4 * 10**18, V]
    )
    b = BuiltTransaction(
        build_id="TEST_ONLY_build",
        intent_id="TEST_ONLY_intent",
        chain_id=31337,
        vault_address=V,
        router=R,
        token_in=U,
        token_out=W,
        amount_in_base_units=str(100 * 10**6),
        min_amount_out_base_units=str(4 * 10**18),
        router_calldata="0x" + data.hex(),
        calldata_hash=keccak(data),
        policy_hash=H,
        nonce="1",
        deadline=NOW + 30,
        quote_ref="TEST_ONLY",
    )
    e = EffectEvidenceV2(
        chain_id=31337,
        vault=V,
        intent_hash=keccak(b.intent_id.encode()),
        policy_hash=H,
        calldata_hash=b.calldata_hash,
        block_number=10,
        block_hash=BH,
        timestamp=NOW,
        registry_hash=registry.hash,
        balances=(
            BalanceRead(asset=U, before=str(10000 * 10**6), after=str(9900 * 10**6)),
            BalanceRead(asset=W, before="0", after=str(output)),
        ),
        allowances=tuple(AllowanceRead(token=a, spender=R, before="0", after="0") for a in (U, W)),
        unexpected_transfer=False,
        unauthorized_approval=False,
    )
    oracle = OracleEvidence(
        chain_id=31337,
        vault=V,
        source_hash=policy.oracle_source_hash,
        timestamp=NOW,
        block_number=10,
        block_hash=BH,
        prices=tuple(
            Price(
                asset=a,
                nominal_usd_e8=str(p),
                low_usd_e8=str(p * (10000 - band) // 10000),
                high_usd_e8=str(p * (10000 + band) // 10000),
            )
            for a, p in ((U, 10**8), (W, 20 * 10**8))
        ),
    )
    s = SessionContext(
        session_id=keccak(b"TEST_ONLY_session"),
        policy_hash=H,
        starts_at=NOW - 1,
        expires_at=NOW + 600,
        active=True,
        limit_usd_e8="1000000000",
        used_usd_e8="0",
        global_limit_usd_e8="2000000000",
        global_used_usd_e8="0",
        block_number=10,
        block_hash=BH,
        timestamp=NOW,
    )
    return b, e, policy, registry, oracle, s, NOW


def test_safe_three_unsat_and_upward_debit():
    args = case()
    queries = {}
    proof = PGSProofEngine(query_sink=lambda h, q: queries.setdefault(h, q)).prove(*args)
    assert proof.status == "VERIFIED", proof
    assert (proof.check_mode, proof.compile_mode, proof.risk_bound) == ("UNSAT",) * 3
    assert proof.assumptions_satisfiable and proof.compiled_region_satisfiable
    assert len(queries) == len(proof.query_hashes)
    lower = [int(b.min_delta) for b in proof.phi.balance_bounds]
    for prices in itertools.product(
        *[(int(p.low_usd_e8), int(p.high_usd_e8)) for p in args[4].prices]
    ):
        loss, out = loss_e8(lower, args[3], prices)
        assert loss <= Fraction(300, 10000) * out
        assert loss <= int(proof.risk_debit_usd_e8)
        # Higher deltas never increase relative residual or absolute loss.
        for extra in ((1, 1), (100000, 10**18), (100 * 10**6, 10**20)):
            higher_loss, higher_out = loss_e8(
                [d + x for d, x in zip(lower, extra, strict=True)], args[3], prices
            )
            assert (
                higher_loss - Fraction(300, 10000) * higher_out <= loss - Fraction(300, 10000) * out
            )
            assert higher_loss <= int(proof.risk_debit_usd_e8)
    for h, q in queries.items():
        assert keccak(q) == h
        solver = z3.Solver()
        solver.from_string(q.decode())
        assert solver.check() in (z3.sat, z3.unsat)


def test_sat_witness_independently_violates_policy():
    args = case(output=4 * 10**18)
    p = PGSProofEngine().prove(*args)
    assert p.status == "VIOLATED" and p.check_mode == "SAT"
    prices = [Fraction(p.witness[a.address]) for a in args[3].assets]
    loss, out = loss_e8([x.delta for x in args[1].balances], args[3], prices)
    assert loss > Fraction(300, 10000) * out


def test_compile_loose_retries_zero_tau():
    p = PGSProofEngine().prove(*case(tolerance=1000))
    assert p.status == "VERIFIED" and p.fallback_tau_zero
    assert p.phi.balance_bounds[1].min_delta == str(5 * 10**18)


def test_unknown_never_verified():
    class Unknown:
        def __init__(self):
            self.s = z3.Solver()

        def set(self, **kw):
            pass

        def add(self, *args):
            self.s.add(*args)

        def sexpr(self):
            return self.s.sexpr()

        def check(self):
            return z3.unknown

    p = PGSProofEngine(solver_factory=Unknown).prove(*case())
    assert p.status == "INCONCLUSIVE" and p.phi is None


@pytest.mark.parametrize(
    "mutation",
    [
        "band",
        "stale",
        "registry",
        "allowance",
        "spender",
        "calldata",
        "session",
        "global",
        "future",
        "overflow",
        "reverse",
        "source",
        "mixed_block",
        "wrong_intent",
    ],
)
def test_invalid_or_ineligible_never_verified(mutation):
    a = list(case())
    if mutation == "band":
        a[4] = a[4].model_copy(
            update={
                "prices": (
                    a[4].prices[0].model_copy(update={"low_usd_e8": "200000000"}),
                    a[4].prices[1],
                )
            }
        )
    if mutation == "stale":
        a[6] = NOW + 61
    if mutation == "registry":
        a[1] = a[1].model_copy(update={"registry_hash": keccak(b"other")})
    if mutation == "allowance":
        a[1] = a[1].model_copy(
            update={
                "allowances": (
                    a[1].allowances[0].model_copy(update={"after": "1"}),
                    a[1].allowances[1],
                )
            }
        )
    if mutation == "spender":
        a[1] = a[1].model_copy(
            update={
                "allowances": (
                    a[1].allowances[0].model_copy(update={"spender": V}),
                    a[1].allowances[1],
                )
            }
        )
    if mutation == "calldata":
        a[0] = a[0].model_copy(update={"router_calldata": a[0].router_calldata + "00"})
    if mutation == "session":
        a[5] = a[5].model_copy(update={"active": False})
    if mutation == "global":
        a[5] = a[5].model_copy(update={"global_used_usd_e8": a[5].global_limit_usd_e8})
    if mutation == "future":
        a[4] = a[4].model_copy(update={"timestamp": NOW + 1})
    if mutation == "overflow":
        a[1] = a[1].model_copy(
            update={
                "balances": (
                    a[1].balances[0],
                    a[1].balances[1].model_copy(update={"after": str(2**255)}),
                )
            }
        )
    if mutation == "reverse":
        a[0] = a[0].model_copy(update={"token_in": W, "token_out": U})
    if mutation == "source":
        a[4] = a[4].model_copy(update={"source_hash": keccak(b"untrusted")})
    if mutation == "mixed_block":
        a[5] = a[5].model_copy(update={"block_hash": keccak(b"reorg")})
    if mutation == "wrong_intent":
        a[1] = a[1].model_copy(update={"intent_hash": keccak(b"other")})
    p = PGSProofEngine().prove(*a)
    assert p.status != "VERIFIED" and p.phi is None


def test_schema_rejects_float_duplicates_and_signed_overflow():
    args = case()
    with pytest.raises(ValidationError):
        ProofPolicy.model_validate(args[2].model_dump() | {"tolerance_bps": 1.5})
    with pytest.raises(ValidationError):
        Registry(assets=(args[3].assets[0],) * 2)
    with pytest.raises(ValidationError):
        BalanceBound(asset=U, min_delta=str(2**255))
    with pytest.raises(ValidationError):
        Price(asset=U, low_usd_e8="2", nominal_usd_e8="1", high_usd_e8="3")
    assert ceil_nonnegative(Fraction(1, 10**18)) == 1
    assert ceil_nonnegative(Fraction(-1, 3)) == 0


def test_exact_corner_property_and_zero_debit():
    for relative, band, tau in itertools.product((0, 100, 300, 9999), (0, 10, 100), (0, 40, 1000)):
        args = case(relative=relative, band=band, tolerance=tau)
        p = PGSProofEngine().prove(*args)
        if p.status != "VERIFIED":
            continue
        for corner in itertools.product(
            *[(int(x.low_usd_e8), int(x.high_usd_e8)) for x in args[4].prices]
        ):
            loss, out = loss_e8([int(b.min_delta) for b in p.phi.balance_bounds], args[3], corner)
            assert loss <= Fraction(relative, 10000) * out
            assert loss <= int(p.risk_debit_usd_e8)
    p = PGSProofEngine().prove(*case(output=6 * 10**18))
    assert p.status == "VERIFIED" and p.risk_debit_usd_e8 == "0"


def test_hash_binding_and_roundtrip():
    args = case()
    p = PGSProofEngine().prove(*args)
    assert PGSProofEngine().prove(*args) == p
    assert PostConditionsV2.model_validate_json(p.phi.model_dump_json()) == p.phi
    changes = {
        "solver_version": "tampered",
        "evidence_root": keccak(b"other"),
        "policy_hash": keccak(b"x"),
        "registry_hash": keccak(b"r"),
        "oracle_hash": keccak(b"o"),
        "exact_call_hash": keccak(b"c"),
        "source_hash": keccak(b"s"),
    }
    for name, value in changes.items():
        assert p.model_copy(update={name: value}).context_hash != p.context_hash
    assert (
        p.model_copy(
            update={
                "phi": p.phi.model_copy(
                    update={
                        "balance_bounds": (
                            p.phi.balance_bounds[0],
                            p.phi.balance_bounds[1].model_copy(update={"min_delta": "1"}),
                        )
                    }
                )
            }
        ).context_hash
        != p.context_hash
    )
