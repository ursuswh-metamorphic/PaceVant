from uuid import uuid4

from app.domain import AssetObservation, PortfolioSnapshot, VerifiedDecisionSnapshot
from app.errors import ControlError
from app.models import ChainBalances, ChainContext, Mandate, OraclePrice

MAX_AGE = 60
MAX_BLOCK_DRIFT = 3


def fresh(timestamp: int, now: int) -> bool:
    return 0 <= now - timestamp <= MAX_AGE


def policy_issues(mandate: Mandate, context: ChainContext, now: int) -> list[str]:
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


def fixture_observation(balances, context, history_version, now):
    from app.orchestration.mock import MockExecutionClient
    from app.portfolio.observations import observed

    assets = [
        AssetObservation(
            asset_id=f"{context.chain_id}:native",
            contract=None,
            symbol="AVAX",
            decimals=18,
            balance_base_units=None,
            verification_status="UNAVAILABLE",
            reason_codes=["MOCK_NATIVE_NOT_MODELED"],
        )
    ]
    for token, symbol, decimals, balance in [
        (context.token_in, "USDC", 6, balances.usdc_base_units),
        (context.token_out, "WAVAX", 18, balances.wavax_base_units),
    ]:
        assets.append(
            AssetObservation(
                asset_id=f"{context.chain_id}:erc20:{token}",
                contract=token,
                symbol=symbol,
                decimals=decimals,
                balance_base_units=balance,
                verification_status="VERIFIED",
            )
        )
    return observed(
        dict(
            mode="MOCK",
            chain_id=context.chain_id,
            vault_address=context.vault_address,
            block_number=balances.block_number,
            block_hash=MockExecutionClient.block_hash(balances.block_number),
            block_timestamp=balances.block_timestamp,
            observed_at=now,
            source_rpc_id="mock://fixture",
            policy_hash=balances.policy_hash,
            policy_version=context.policy_version,
            policy_state={
                "owner": context.owner,
                "attestor": context.attestor,
                "active": context.policy_active,
                "paused": context.paused,
            },
            assets=[a.model_dump() for a in assets],
            history_version=history_version,
            verification_status="INCOMPLETE",
            reason_codes=["MOCK_NATIVE_NOT_MODELED"],
            source_refs=["MOCK_FIXTURE"],
        )
    )


def decision_snapshot(observed, balances, oracle, context, built, now):
    from app.portfolio.observations import content_hash, verify_snapshot_hash

    if observed.mode == "FUJI" or built.adapter_version == "lfj-v1-fuji-v1":
        raise ControlError("ORACLE_TOKEN_IDENTITY_MISMATCH")
    if not fresh(oracle.price_timestamp, now):
        raise ControlError("STALE_PRICE")
    if (observed.chain_id, observed.vault_address, observed.policy_hash) != (
        balances.chain_id,
        balances.vault_address,
        balances.policy_hash,
    ):
        raise ControlError("HASH_MISMATCH")
    if (
        len(observed.assets) != 3
        or observed.assets[1].asset_id != f"{built.chain_id}:erc20:{built.token_in.lower()}"
        or observed.assets[2].asset_id != f"{built.chain_id}:erc20:{built.token_out.lower()}"
        or (observed.assets[1].contract, observed.assets[2].contract)
        != (built.token_in.lower(), built.token_out.lower())
        or (observed.assets[1].decimals, observed.assets[2].decimals) != (6, 18)
    ):
        raise ControlError("TOKEN_IDENTITY_MISMATCH")
    allowed_fixture = observed.mode == "MOCK" and observed.reason_codes == [
        "MOCK_NATIVE_NOT_MODELED"
    ]
    if (
        not verify_snapshot_hash(observed)
        or (observed.verification_status != "VERIFIED" and not allowed_fixture)
        or not fresh(observed.block_timestamp, now)
        or not fresh(oracle.price_timestamp, now)
        or oracle.price_source != "TRUSTED_TEST_ORACLE"
        or min(int(oracle.price_usdc_usd_e8), int(oracle.price_wavax_usd_e8)) <= 0
        or observed.policy_hash != context.policy_hash
        or observed.chain_id != balances.chain_id
        or observed.vault_address != balances.vault_address
        or observed.block_number != balances.block_number
        or observed.assets[1].balance_base_units != balances.usdc_base_units
        or observed.assets[2].balance_base_units != balances.wavax_base_units
    ):
        raise ControlError("UNVERIFIED_DECISION_SNAPSHOT")
    fields = dict(
        block_number=balances.block_number,
        usdc_base_units=balances.usdc_base_units,
        wavax_base_units=balances.wavax_base_units,
        history_version=observed.history_version,
        **oracle.model_dump(),
        observation_snapshot_id=observed.snapshot_id,
        observation_hash=observed.content_hash,
        verification_scope="MOCK_FIXTURE" if observed.mode == "MOCK" else "LOCAL_TEST_ORACLE",
        block_hash=observed.block_hash,
        block_timestamp=observed.block_timestamp,
        observed_at=observed.observed_at,
        source_rpc_id=observed.source_rpc_id,
        policy_hash=observed.policy_hash,
        policy_version=observed.policy_version,
        asset_identities=[a.asset_id for a in observed.assets],
        build_id=built.build_id,
        schema_version="2.0",
        eligible_for_authorization=True,
    )
    digest = content_hash(fields)
    return VerifiedDecisionSnapshot(
        snapshot_id="snapshot_" + digest[2:], content_hash=digest, **fields
    )


def parse_decision_snapshot(value):
    if value.get("schema_version") == "2.0":
        from app.portfolio.observations import verify_snapshot_hash

        snapshot = VerifiedDecisionSnapshot.model_validate(value)
        if not verify_snapshot_hash(snapshot):
            raise ControlError("SNAPSHOT_HASH_MISMATCH")
        return snapshot
    return PortfolioSnapshot.model_validate(value)
