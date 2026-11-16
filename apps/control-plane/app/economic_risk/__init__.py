from dataclasses import dataclass

from app.models import ChainBalances, ChainContext, Mandate
from app.portfolio import MAX_BLOCK_DRIFT, fresh
from treasury_contract.wire import (
    BuiltTransaction,
    EconomicRiskAssessment,
    PortfolioSnapshot,
    SimulationEvidence,
    TransactionProposal,
)

USDC_SCALE = 10**6
WAVAX_SCALE = 10**18
WAVAX_PER_USDC_SCALE = WAVAX_SCALE // USDC_SCALE
BPS = 10_000


@dataclass(frozen=True)
class Evaluation:
    risk: EconomicRiskAssessment
    suggested_amount: int


def evaluate(
    mandate: Mandate,
    proposal: TransactionProposal,
    built: BuiltTransaction,
    evidence: SimulationEvidence,
    snapshot: PortfolioSnapshot,
    balances: ChainBalances,
    context: ChainContext,
    now: int,
) -> Evaluation:
    base = {
        "intent_id": built.intent_id,
        "build_id": built.build_id,
        "snapshot_id": snapshot.snapshot_id,
        "max_wavax_exposure_bps": mandate.max_avax_exposure_bps,
    }
    unknown = []
    if (
        (snapshot.chain_id, snapshot.vault_address) != (mandate.chain_id, mandate.vault_address)
        or (balances.chain_id, balances.vault_address) != (mandate.chain_id, mandate.vault_address)
        or balances.policy_hash != mandate.policy_hash
        or snapshot.block_number != balances.block_number
        or (snapshot.usdc_base_units, snapshot.wavax_base_units)
        != (balances.usdc_base_units, balances.wavax_base_units)
    ):
        unknown.append("HASH_MISMATCH")
    if (
        not fresh(balances.block_timestamp, now)
        or not 0 <= context.block_number - balances.block_number <= MAX_BLOCK_DRIFT
        or abs(evidence.fork_block - balances.block_number) > MAX_BLOCK_DRIFT
        or balances.utc_day != now // 86400
        or balances.block_timestamp // 86400 != balances.utc_day
        or built.deadline // 86400 != balances.utc_day
    ):
        unknown.append("STALE_SNAPSHOT")
    usdc_price, wavax_price = int(snapshot.price_usdc_usd_e8), int(snapshot.price_wavax_usd_e8)
    if not fresh(snapshot.price_timestamp, now):
        unknown.append("STALE_PRICE")
    if snapshot.price_source != "TRUSTED_TEST_ORACLE" or min(usdc_price, wavax_price) <= 0:
        unknown.append("UNVERIFIED_PRICE")
    if int(balances.max_fee_per_gas_wei) == 0:
        unknown.append("UNVERIFIED_EXECUTION_COST")
    if evidence.baseline.execution_status != "SUCCESS":
        unknown.append("SIMULATION_INCOMPLETE")
    if unknown:
        return Evaluation(
            EconomicRiskAssessment(
                result="INCONCLUSIVE", projected_wavax_exposure_bps=None, violations=unknown, **base
            ),
            0,
        )

    amount = int(built.amount_in_base_units)
    available = int(snapshot.usdc_base_units)
    used = int(balances.daily_spent_usdc_base_units)
    max_trade = int(mandate.max_usdc_per_swap_base_units)
    remaining = max(0, int(mandate.max_usdc_spend_per_day_base_units) - used)
    usdc_value_per_unit = usdc_price * WAVAX_PER_USDC_SCALE
    wavax_value = int(snapshot.wavax_base_units) * wavax_price
    total_value = available * usdc_value_per_unit + wavax_value
    out = int(evidence.baseline.token_out_delta_base_units)
    if out <= 0 or not 0 < amount or amount > available or total_value == 0:
        reason = "TRADE_SIZE_LIMIT" if amount > available else "SIMULATION_INCOMPLETE"
        return Evaluation(
            EconomicRiskAssessment(
                result="FAIL" if reason == "TRADE_SIZE_LIMIT" else "INCONCLUSIVE",
                projected_wavax_exposure_bps=None,
                violations=[reason],
                **base,
            ),
            min(available, max_trade, remaining),
        )

    # Use common e8 * 1e18 units to preserve exact comparisons at the exposure boundary.
    projected_wavax = wavax_value + out * wavax_price
    projected_total = projected_wavax + (available - amount) * usdc_value_per_unit
    exposure = (projected_wavax * BPS + projected_total - 1) // projected_total
    fair_min_out = (
        amount * usdc_value_per_unit * (BPS - proposal.slippage_bps) // (wavax_price * BPS)
    )
    gas_cost = (
        int(evidence.baseline.gas_used) * int(balances.max_fee_per_gas_wei) * wavax_price
        + WAVAX_SCALE
        - 1
    ) // WAVAX_SCALE

    violations = []
    if amount > min(max_trade, remaining):
        violations.append("TRADE_SIZE_LIMIT")
    if exposure > mandate.max_avax_exposure_bps:
        violations.append("TOKEN_EXPOSURE_LIMIT")
    if int(built.min_amount_out_base_units) < fair_min_out:
        violations.append("BAD_PRICE_OR_SLIPPAGE")
    if gas_cost + int(balances.daily_execution_cost_usd_e8) > int(
        mandate.max_daily_execution_cost_usd_e8
    ):
        violations.append("EXECUTION_COST_LIMIT")

    # A spot-price ceiling is a planning hint. The new build still needs full simulation.
    exposure_room = max(
        0,
        (total_value * mandate.max_avax_exposure_bps - wavax_value * BPS)
        // (usdc_value_per_unit * BPS),
    )
    return Evaluation(
        EconomicRiskAssessment(
            result="FAIL" if violations else "PASS",
            projected_wavax_exposure_bps=exposure,
            violations=violations,
            **base,
        ),
        min(max_trade, remaining, available, exposure_room),
    )
