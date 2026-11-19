"""Bridge existing V1 evidence/risk into the single shared PGS proof engine."""

from app.errors import ControlError
from treasury_contracts.proof import PGSProofEngine
from treasury_contracts.v2 import OracleEvidence, Price, keccak


def prove(mandate, built, simulation, snapshot, context, now, query_sink=None):
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
        or snapshot.price_source != "TRUSTED_TEST_ORACLE"
        or p.oracle_source_hash != keccak(snapshot.price_source.encode())
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
        timestamp=snapshot.price_timestamp,
        block_number=effects.block_number,
        block_hash=effects.block_hash,
        prices=tuple(
            Price(
                asset=a.address,
                nominal_usd_e8=str(by_decimals[a.decimals]),
                low_usd_e8=str(
                    (by_decimals[a.decimals] * (10000 - p.oracle_band_bps) + 9999) // 10000
                ),
                high_usd_e8=str(by_decimals[a.decimals] * (10000 + p.oracle_band_bps) // 10000),
            )
            for a in registry.assets
        ),
    )
    return PGSProofEngine(query_sink=query_sink).prove(
        built, effects, p, registry, oracle, session, now
    )
