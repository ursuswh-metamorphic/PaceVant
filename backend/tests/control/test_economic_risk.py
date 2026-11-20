"""Economic boundary tests with explicit LOCAL facts; no RPC, model or transaction."""

import random
from fractions import Fraction

import pytest
from eth_abi import encode
from test_v2_gates import inputs

from treasury_backend.core.domain import PortfolioSnapshot
from treasury_backend.core.models import ChainBalances
from treasury_backend.modules.risk.service import evaluate
from treasury_contracts.v2 import keccak

USDC, AVAX, USD = 10**6, 10**18, 10**8


def scenario(
    *,
    amount=100 * USDC,
    output=5 * AVAX,
    cash=10000 * USDC,
    wavax=0,
    prices=(USD, 20 * USD),
    slippage=40,
    minimum=None,
    reverse=False,
):
    built, mandate, context, sim, proposal, _, _, _, now = inputs()
    # Wider-slippage scenarios use an explicitly wider LOCAL owner mandate.
    # They do not imply the current Fuji mandate permits that slippage.
    if slippage > mandate.max_slippage_bps:
        mandate = mandate.model_copy(update={"max_slippage_bps": slippage})
        context = context.model_copy(update={"max_slippage_bps": slippage})
    if minimum is None:
        numerator = amount * (prices[1] if reverse else prices[0] * 10**12) * (10000 - slippage)
        denominator = (prices[0] * 10**12 if reverse else prices[1]) * 10000
        minimum = numerator // denominator
    token_in, token_out = (
        (mandate.token_out, mandate.token_in) if reverse else (mandate.token_in, mandate.token_out)
    )
    data = bytes.fromhex(
        keccak(b"exactInput(address,address,uint256,uint256,address)")[2:10]
    ) + encode(
        ["address", "address", "uint256", "uint256", "address"],
        [token_in, token_out, amount, minimum, mandate.vault_address],
    )
    fields = {"token_in": token_in, "token_out": token_out, "amount_in_base_units": str(amount)}
    built = built.model_copy(
        update=fields
        | {
            "min_amount_out_base_units": str(minimum),
            "router_calldata": "0x" + data.hex(),
            "calldata_hash": keccak(data),
        }
    )
    proposal = proposal.model_copy(update=fields | {"slippage_bps": slippage})
    before = {mandate.token_in: cash, mandate.token_out: wavax}
    delta = {token_in: -amount, token_out: output}
    effects = sim.effects_v2.model_copy(
        update={
            "calldata_hash": built.calldata_hash,
            "balances": tuple(
                row.model_copy(
                    update={
                        "before": str(before[row.asset]),
                        "after": str(before[row.asset] + delta[row.asset]),
                    }
                )
                for row in sim.effects_v2.balances
            ),
        }
    )
    sim = sim.model_copy(
        update={
            "calldata_hash": built.calldata_hash,
            "effects_v2": effects,
            "evidence_root": effects.hash,
            "baseline": sim.baseline.model_copy(
                update={
                    "token_in_delta_base_units": str(-amount),
                    "token_out_delta_base_units": str(output),
                }
            ),
            "stress_tests": [
                s.model_copy(update={"output_base_units": str(output)}) for s in sim.stress_tests
            ],
        }
    )
    balances = ChainBalances(
        chain_id=built.chain_id,
        vault_address=built.vault_address,
        policy_hash=built.policy_hash,
        block_number=context.block_number,
        block_timestamp=now,
        usdc_base_units=str(cash),
        wavax_base_units=str(wavax),
        utc_day=now // 86400,
        daily_spent_usdc_base_units="0",
        daily_execution_cost_usd_e8="0",
        max_fee_per_gas_wei="1000000000",
    )
    snapshot = PortfolioSnapshot(
        snapshot_id="TEST_ONLY_economic_snapshot",
        chain_id=built.chain_id,
        vault_address=built.vault_address,
        block_number=balances.block_number,
        usdc_base_units=str(cash),
        wavax_base_units=str(wavax),
        price_usdc_usd_e8=str(prices[0]),
        price_wavax_usd_e8=str(prices[1]),
        price_source="TRUSTED_TEST_ORACLE",
        price_timestamp=now,
        history_version=0,
    )
    return [mandate, proposal, built, sim, snapshot, balances, context, now]


def change(args, index, **fields):
    args[index] = args[index].model_copy(update=fields)


def check(args):
    return evaluate(*args)


def test_normal_swap_uses_actual_math_and_binds_identifiers():
    args = scenario()
    result = check(args)
    assert result.risk.result == "PASS" and result.risk.violations == []
    assert result.risk.projected_wavax_exposure_bps == 100
    assert (result.risk.intent_id, result.risk.build_id, result.risk.snapshot_id) == (
        args[2].intent_id,
        args[2].build_id,
        args[4].snapshot_id,
    )


@pytest.mark.parametrize("extra,expected", [(0, "PASS"), (1, "FAIL")])
def test_per_swap_limit_at_one_base_unit(extra, expected):
    amount = 100 * USDC + extra
    args = scenario(amount=amount, output=amount * 10**12 // 20)
    change(args, 0, max_usdc_per_swap_base_units=str(100 * USDC))
    result = check(args)
    assert result.risk.result == expected
    assert ("TRADE_SIZE_LIMIT" in result.risk.violations) == bool(extra)
    assert result.suggested_amount <= 100 * USDC


@pytest.mark.parametrize(
    "remaining,expected", [(100 * USDC, "PASS"), (100 * USDC - 1, "FAIL"), (0, "FAIL")]
)
def test_daily_spend_remaining_is_authoritative(remaining, expected):
    args = scenario()
    used = int(args[0].max_usdc_spend_per_day_base_units) - remaining
    change(args, 5, daily_spent_usdc_base_units=str(used))
    result = check(args)
    assert result.risk.result == expected
    assert result.suggested_amount <= remaining


def test_insufficient_balance_never_recommends_more_than_available():
    # A previously simulated candidate may now face a lower current balance.
    # Keep effect facts internally valid; current snapshot/balance reflect the shortage.
    args = scenario(cash=100 * USDC)
    change(args, 4, usdc_base_units=str(100 * USDC - 1))
    change(args, 5, usdc_base_units=str(100 * USDC - 1))
    result = check(args)
    assert result.risk.result == "FAIL" and "TRADE_SIZE_LIMIT" in result.risk.violations
    assert result.suggested_amount <= 100 * USDC - 1


@pytest.mark.parametrize("extra,expected", [(0, "PASS"), (1, "FAIL")])
def test_exposure_boundary_exact_then_one_wavax_unit_above(extra, expected):
    # 100 USDC -> 5 WAVAX; cash 400 USDC. Post value = 300 cash + 100 WAVAX.
    args = scenario(cash=400 * USDC, output=5 * AVAX + extra)
    result = check(args)
    assert result.risk.result == expected
    assert result.risk.projected_wavax_exposure_bps == (2500 if not extra else 2501)
    assert ("TOKEN_EXPOSURE_LIMIT" in result.risk.violations) == bool(extra)


@pytest.mark.parametrize("offset,expected", [(0, "PASS"), (-1, "FAIL")])
def test_min_output_floor_at_slippage_boundary(offset, expected):
    minimum = 100 * USDC * 10**12 * 9960 // (20 * 10000)
    result = check(scenario(minimum=minimum + offset))
    assert result.risk.result == expected
    assert ("BAD_PRICE_OR_SLIPPAGE" in result.risk.violations) == (offset < 0)


@pytest.mark.parametrize("offset,expected", [(0, "PASS"), (-1, "FAIL")])
def test_nominal_loss_cap_at_exact_rational_boundary(offset, expected):
    # At 20 USD/WAVAX, 4.85 WAVAX is exactly a 3 USD loss on 100 USDC outgoing.
    args = scenario(output=485 * AVAX // 100 + offset, slippage=400)
    result = check(args)
    assert result.risk.result == expected
    assert ("VALUE_POLICY_COUNTEREXAMPLE" in result.risk.violations) == (offset < 0)


def test_fixed_loss_allowance_is_added_not_multiplied_by_notional():
    args = scenario(output=480 * AVAX // 100, slippage=500)
    policy = args[0].proof_policy.model_copy(update={"fixed_loss_usd_e8": str(USD)})
    change(args, 0, proof_policy=policy)
    assert check(args).risk.result == "PASS"  # 4 USD loss <= 3% * 100 USD + 1 USD
    change(args, 0, proof_policy=policy.model_copy(update={"fixed_loss_usd_e8": str(USD - 1)}))
    assert "VALUE_POLICY_COUNTEREXAMPLE" in check(args).risk.violations


@pytest.mark.parametrize("offset,expected", [(0, "PASS"), (-1, "FAIL")])
def test_gas_budget_includes_prior_native_and_usd_costs(offset, expected):
    args = scenario()
    change(args, 5, daily_execution_cost_wei=str(AVAX // 1000), daily_execution_cost_usd_e8="123")
    gas_wei = 200000 * 10**9 + AVAX // 1000
    cost = (gas_wei * 20 * USD + AVAX - 1) // AVAX + 123
    change(args, 0, max_daily_execution_cost_usd_e8=str(cost + offset))
    result = check(args)
    assert result.risk.result == expected
    assert ("EXECUTION_COST_LIMIT" in result.risk.violations) == (offset < 0)


def test_sub_usd_e8_gas_value_rounds_up():
    args = scenario()
    change(args, 5, max_fee_per_gas_wei="1")
    change(args, 0, max_daily_execution_cost_usd_e8="0")
    assert "EXECUTION_COST_LIMIT" in check(args).risk.violations


@pytest.mark.parametrize("age,expected", [(60, "PASS"), (61, "INCONCLUSIVE"), (-1, "INCONCLUSIVE")])
def test_state_and_price_age_boundaries(age, expected):
    args = scenario()
    # Current V2 fixture has max_oracle_age=60; block and price use independent clocks.
    change(args, 5, block_timestamp=args[7] - age)
    change(args, 4, price_timestamp=args[7] - age)
    assert check(args).risk.result == expected


@pytest.mark.parametrize(
    "condition",
    [
        "no_gas_price",
        "zero_price",
        "unsupported_source",
        "future_block",
        "too_old_block",
        "day",
        "deadline_day",
        "different_snapshot",
        "different_balance",
    ],
)
def test_insufficient_or_mismatched_economic_facts_never_pass(condition):
    args = scenario()
    if condition == "no_gas_price":
        change(args, 5, max_fee_per_gas_wei="0")
    if condition == "zero_price":
        change(args, 4, price_wavax_usd_e8="0")
    if condition == "unsupported_source":
        change(args, 4, price_source="UNREVIEWED")
    if condition == "future_block":
        change(args, 6, block_number=args[5].block_number - 1)
    if condition == "too_old_block":
        change(args, 6, block_number=args[5].block_number + args[6].max_block_drift + 1)
    if condition == "day":
        change(args, 5, utc_day=args[5].utc_day - 1)
    if condition == "deadline_day":
        change(args, 2, deadline=(args[7] // 86400 + 1) * 86400)
    if condition == "different_snapshot":
        change(args, 4, vault_address="0x" + "77" * 20)
    if condition == "different_balance":
        change(args, 5, usdc_base_units="1")
    result = check(args)
    assert result.risk.result == "INCONCLUSIVE" and result.risk.violations
    assert result.suggested_amount == 0


@pytest.mark.parametrize("cap,expected", [(0, "FAIL"), (AVAX, "PASS"), (AVAX - 1, "FAIL")])
def test_local_reverse_uses_wavax_cap_and_not_usdc_daily_spend(cap, expected):
    args = scenario(amount=AVAX, output=20 * USDC, wavax=AVAX, cash=1000 * USDC, reverse=True)
    change(
        args,
        0,
        proof_policy=args[0].proof_policy.model_copy(update={"max_wavax_per_swap": str(cap)}),
    )
    change(args, 5, daily_spent_usdc_base_units=args[0].max_usdc_spend_per_day_base_units)
    result = check(args)
    assert result.risk.result == expected
    assert result.risk.projected_wavax_exposure_bps == 0
    assert result.suggested_amount <= cap


def test_exposure_matches_independent_fraction_reference_across_seeded_cases():
    rng = random.Random(20261120)
    for _ in range(150):
        amount = rng.randint(1, 200 * USDC)
        cash = rng.randint(amount + 1, 5000 * USDC)
        wavax = rng.randint(0, 50 * AVAX)
        prices = (rng.randint(95_000_000, 105_000_000), rng.randint(5 * USD, 100 * USD))
        output = max(1, amount * prices[0] * 10**12 // prices[1])
        args = scenario(amount=amount, output=output, cash=cash, wavax=wavax, prices=prices)
        result = check(args)
        cash_value = Fraction((cash - amount) * prices[0], USDC)
        avax_value = Fraction((wavax + output) * prices[1], AVAX)
        ratio = avax_value * 10000 / (cash_value + avax_value)
        expected = (ratio.numerator + ratio.denominator - 1) // ratio.denominator
        assert result.risk.projected_wavax_exposure_bps == expected
        assert ("TOKEN_EXPOSURE_LIMIT" in result.risk.violations) == (ratio > 2500)


@pytest.mark.parametrize("issue", ["size", "exposure", "slippage", "gas", "loss"])
def test_economic_failures_propagate_to_sde_without_an_approval(issue):
    from treasury_backend.core.models import Alignment
    from treasury_backend.modules.decision import decide

    args = scenario()
    if issue == "size":
        change(args, 0, max_usdc_per_swap_base_units="1")
    if issue == "exposure":
        change(args, 0, max_avax_exposure_bps=99)
    if issue == "slippage":
        change(args, 2, min_amount_out_base_units="1")
    if issue == "gas":
        change(args, 0, max_daily_execution_cost_usd_e8="0")
    if issue == "loss":
        args = scenario(output=48 * AVAX // 10, slippage=500)
    evaluation = check(args)
    assert evaluation.risk.result == "FAIL"
    mandate, proposal, built, sim, _, _, context, now = args
    context = context.model_copy(
        update={"max_usdc_per_swap_base_units": mandate.max_usdc_per_swap_base_units}
    )
    decision = decide(
        mandate,
        proposal,
        Alignment(verdict="ALIGNED", reason_codes=[], evidence_refs=[]),
        context,
        now,
        built=built,
        evidence=sim,
        risk=evaluation.risk,
    )
    assert decision.verdict != "APPROVE"
    assert set(evaluation.risk.violations) <= set(decision.reason_codes)


def test_nominal_risk_pass_does_not_override_interval_price_proof_failure():
    from treasury_backend.modules.proof.service import prove

    args = scenario(output=485 * AVAX // 100, slippage=400)
    assert check(args).risk.result == "PASS"  # exactly 3% nominal loss
    mandate, _, built, sim, snapshot, _, context, now = args
    proof = prove(mandate, built, sim, snapshot, context, now)
    assert proof.status == "VIOLATED" and proof.check_mode == "SAT"
    assert proof.phi is None  # independent +/-1% prices reveal a value-policy counterexample


@pytest.mark.parametrize("scope", ["session", "global"])
@pytest.mark.parametrize("extra_room,expected", [(0, "VERIFIED"), (-1, "VIOLATED")])
def test_certified_risk_headroom_at_one_usd_e8_unit(scope, extra_room, expected):
    from treasury_backend.modules.proof.service import prove

    mandate, _, built, sim, snapshot, _, context, now = scenario()
    initial = prove(mandate, built, sim, snapshot, context, now)
    assert initial.status == "VERIFIED"
    debit = int(initial.risk_debit_usd_e8)
    assert debit > 0  # nominal zero loss still carries nonzero interval/Phi risk
    session = context.proof_session
    fields = (
        {"used_usd_e8": str(int(session.limit_usd_e8) - debit - extra_room)}
        if scope == "session"
        else {"global_used_usd_e8": str(int(session.global_limit_usd_e8) - debit - extra_room)}
    )
    context = context.model_copy(update={"proof_session": session.model_copy(update=fields)})
    result = prove(mandate, built, sim, snapshot, context, now)
    assert result.status == expected
    if expected == "VIOLATED":
        assert result.reason in {"SESSION_OR_GLOBAL_RISK_LIMIT", "VALUE_POLICY_COUNTEREXAMPLE"}


def test_positive_current_prices_do_not_prove_actual_profitability():
    args = scenario(output=6 * AVAX)
    result = check(args)
    assert result.risk.result == "PASS"
    # This is reference-value appreciation inside the snapshot/model, not an APR
    # assertion or a claim that Fuji test tokens are redeemable for real USD.
    assert result.risk.projected_wavax_exposure_bps is not None


def test_more_output_can_reduce_value_loss_but_exceed_exposure_cap():
    args = scenario(cash=400 * USDC, output=6 * AVAX)
    result = check(args)
    assert result.risk.result == "FAIL"
    assert "TOKEN_EXPOSURE_LIMIT" in result.risk.violations
    assert "VALUE_POLICY_COUNTEREXAMPLE" not in result.risk.violations


@pytest.mark.parametrize("age,expected", [(300, "PASS"), (301, "INCONCLUSIVE")])
def test_owner_300_second_state_window_keeps_its_boundary(age, expected):
    args = scenario()
    policy = args[0].proof_policy.model_copy(update={"max_oracle_age": 300})
    change(args, 0, proof_policy=policy)
    change(args, 6, proof_policy=policy, block_timestamp=args[7] - age)
    change(args, 5, block_timestamp=args[7] - age)
    change(args, 4, price_timestamp=args[7] - age)
    assert check(args).risk.result == expected
