"""Reviewed Fuji reference-price policy. Test tokens have no mainnet redemption claim."""

import json

from eth_utils import keccak

CIRCLE_USDC = "0x5425890298aed601595a70ab815c96711a31bc65"
WAVAX = "0xd00ae08403b9bbb9124bb305c09058e32c39a48c"
CHAINLINK_SOURCE = "CHAINLINK_FUJI_CIRCLE_USDC_AVAX_V1"
# This exact configuration is committed by the owner policy's oracleSourceHash.
FEEDS = {
    CIRCLE_USDC: ("0x97fe42a7e96640d932bbc0e1580c73e705a8eb73", "USDC/USD", 86400),
    WAVAX: ("0x5498bb86bc934c8d34fda08e81d444153d0d06ad", "AVAX/USD", 600),
}

SOURCE_HASH = "0x" + keccak(json.dumps(
    {"source": CHAINLINK_SOURCE, "chain_id": 43113, "feeds": FEEDS,
     "valuation": "TESTNET_REFERENCE_USD_NOT_REDEEMABLE", "version": 1},
    sort_keys=True, separators=(",", ":"),
).encode()).hex()


def validate_rounds(feeds, prices, now, observed_at, chain_id, source_hash):
    """Validate original observations, exact asset/feed identities and per-feed age."""
    if chain_id != 43113 or source_hash != SOURCE_HASH or len(feeds) != 2:
        raise ValueError("untrusted Chainlink configuration")
    if [f.asset for f in feeds] != sorted(FEEDS) or set(prices) != set(FEEDS):
        raise ValueError("incomplete/duplicate oracle assets")
    for f in feeds:
        address, description, max_age = FEEDS[f.asset]
        if (f.feed, f.description, f.max_age_seconds, f.decimals) != (address, description, max_age, 8):
            raise ValueError("oracle feed policy mismatch")
        if (not 0 < f.started_at <= f.updated_at <= observed_at <= now
                or now - f.updated_at > max_age or int(f.round_id) == 0
                or int(f.answered_in_round) < int(f.round_id)
                or int(f.answer_raw) <= 0 or f.bytecode_hash == "0x" + "00" * 32):
            raise ValueError("invalid/stale Chainlink round")
        if int(prices[f.asset]) != int(f.answer_raw) * 10**8 // 10**f.decimals:
            raise ValueError("oracle price does not match raw round")
