"""Bridge existing V1 evidence/risk into the single shared PGS proof engine."""

from treasury_backend.core.errors import ControlError
from treasury_backend.modules.oracle import is_supported_source, source_hash
from treasury_contracts.proof import PGSProofEngine, owner_price_interval
from treasury_contracts.v2 import OracleEvidence, Price


def prove(mandate, built, simulation, snapshot, context, now, query_sink=None):
    from treasury_backend.modules.oracle.chainlink import validate_price
    from treasury_contracts.oracle import CHAINLINK_SOURCE, CIRCLE_USDC, WAVAX

    validate_price(snapshot, now)
    if built.adapter_version == "lfj-v1-fuji-v1" and (
        snapshot.price_source != CHAINLINK_SOURCE
        or (built.token_in.lower(), built.token_out.lower()) != (CIRCLE_USDC, WAVAX)
    ):
        raise ControlError("ORACLE_TOKEN_IDENTITY_MISMATCH")
    p, registry, session, effects = (
        mandate.proof_policy,
        mandate.registry,
        context.proof_session,
        simulation.effects_v2,
    )
    if any(v is None for v in (p, registry, session, effects)):
        raise ControlError("PROOF_REQUIRED")
    if (
        snapshot.chain_id != effects.chain_id
        or snapshot.vault_address != effects.vault
        or not is_supported_source(snapshot.price_source)
        or p.oracle_source_hash != source_hash(snapshot.price_source)
        or context.registry != registry
        or context.proof_policy != p
        or session.session_id != mandate.session_id
    ):
        raise ControlError("HASH_MISMATCH")
    by_decimals = {6: int(snapshot.price_usdc_usd_e8), 18: int(snapshot.price_wavax_usd_e8)}
    balances = {6: int(snapshot.usdc_base_units), 18: int(snapshot.wavax_base_units)}
    for a, b in zip(registry.assets, effects.balances, strict=True):
        if a.address != b.asset or int(b.before) != balances[a.decimals]:
            raise ControlError("STALE_SNAPSHOT")
    oracle = OracleEvidence(
        chain_id=effects.chain_id,
        vault=effects.vault,
        source_hash=p.oracle_source_hash,
        timestamp=snapshot.oracle_observed_at if snapshot.oracle_feeds else snapshot.price_timestamp,
        block_number=effects.block_number,
        block_hash=effects.block_hash,
        feeds=tuple(snapshot.oracle_feeds),
        prices=tuple(
            Price(
                asset=a.address,
                nominal_usd_e8=str(by_decimals[a.decimals]),
                low_usd_e8=str(owner_price_interval(by_decimals[a.decimals], p.oracle_band_bps)[0]),
                high_usd_e8=str(owner_price_interval(by_decimals[a.decimals], p.oracle_band_bps)[1]),
            )
            for a in registry.assets
        ),
    )
    if snapshot.oracle_feeds and (snapshot.oracle_block_number, snapshot.oracle_block_hash) != (
        effects.block_number, effects.block_hash
    ):
        raise ControlError("HASH_MISMATCH")
    return PGSProofEngine(query_sink=query_sink).prove(
        built, effects, p, registry, oracle, session, now
    )
