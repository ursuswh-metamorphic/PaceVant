from uuid import uuid4

from treasury_backend.core.domain import PortfolioSnapshot
from treasury_backend.core.models import ChainBalances, ChainContext, Mandate
from treasury_backend.modules.oracle.models import OraclePrice

MAX_AGE = 60
MAX_BLOCK_DRIFT = 3


def fresh(timestamp: int, now: int, max_age=MAX_AGE) -> bool:
    return 0 <= now - timestamp <= max_age


def state_age(context):
    return context.proof_policy.max_oracle_age if context.proof_policy else MAX_AGE


def price_fresh(value, now, max_age=MAX_AGE):
    from treasury_backend.modules.oracle.chainlink import validate_price
    from treasury_contracts.oracle import CHAINLINK_SOURCE

    validate_price(value, now)
    timestamp = value.oracle_observed_at if value.price_source == CHAINLINK_SOURCE else value.price_timestamp
    return timestamp is not None and fresh(timestamp, now, max_age)


def policy_issues(mandate: Mandate, context: ChainContext, now: int) -> list[str]:
    if context.proof_policy is not None or mandate.proof_policy is not None:
        if (
            mandate.proof_policy is None
            or mandate.registry is None
            or mandate.session_id is None
            or context.proof_policy != mandate.proof_policy
            or context.registry != mandate.registry
            or context.proof_session is None
            or context.proof_session.session_id != mandate.session_id
        ):
            return ["PROOF_REQUIRED"]
    if (
        mandate.status != "ACTIVE"
        or mandate.expires_at <= now
        or not context.policy_active
        or (context.policy_expires_at is not None and context.policy_expires_at <= now)
        or context.paused
        or context.policy_hash != mandate.policy_hash
    ):
        return ["POLICY_REVOKED"]
    fields = (
        "chain_id",
        "vault_address",
        "owner",
        "router",
        "token_in",
        "token_out",
        "max_usdc_per_swap_base_units",
        "max_usdc_spend_per_day_base_units",
    )
    if any(getattr(mandate, field) != getattr(context, field) for field in fields):
        return ["HASH_MISMATCH"]
    if mandate.max_slippage_bps > context.max_slippage_bps:
        return ["HASH_MISMATCH"]
    if not fresh(context.block_timestamp, now, state_age(context)):
        return ["STALE_SNAPSHOT"]
    return []


def snapshot(
    balances: ChainBalances, oracle: OraclePrice, history_version: int
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        snapshot_id=f"snapshot_{uuid4().hex}",
        block_number=balances.block_number,
        usdc_base_units=balances.usdc_base_units,
        wavax_base_units=balances.wavax_base_units,
        history_version=history_version,
        **oracle.model_dump(),
    )
