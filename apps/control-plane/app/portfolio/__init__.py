from uuid import uuid4

from app.models import ChainBalances, ChainContext, Mandate, OraclePrice
from treasury_contract.wire import PortfolioSnapshot

MAX_AGE = 60
MAX_BLOCK_DRIFT = 3


def fresh(timestamp: int, now: int) -> bool:
    return 0 <= now - timestamp <= MAX_AGE


def policy_issues(mandate: Mandate, context: ChainContext, now: int) -> list[str]:
    if (
        mandate.status != "ACTIVE"
        or mandate.expires_at <= now
        or context.paused
        or context.policy_hash != mandate.policy_hash
        or context.policy_version != mandate.version
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
    if not fresh(context.block_timestamp, now):
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
