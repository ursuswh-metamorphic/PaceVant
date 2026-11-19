"""Provenance/freshness regressions for the real Fuji reference-price path."""

import pytest

from treasury_backend.core.errors import ControlError
from treasury_backend.modules.oracle.chainlink import validate_price
from treasury_backend.modules.oracle.models import OraclePrice, source_hash
from treasury_backend.modules.oracle.service import JsonFilePriceProvider
from treasury_backend.modules.portfolio import price_fresh
from treasury_contracts.oracle import CHAINLINK_SOURCE, CIRCLE_USDC, FEEDS, SOURCE_HASH, WAVAX
from treasury_contracts.v2 import FeedObservation, OracleEvidence, Price

NOW = 2_000_000_000


def price():
    feeds = [FeedObservation(
        asset=asset, feed=feed, description=description, max_age_seconds=age,
        decimals=8, answer_raw="100000000" if asset == CIRCLE_USDC else "700000000",
        round_id="44", answered_in_round="44", started_at=NOW - (60000 if asset == CIRCLE_USDC else 200),
        updated_at=NOW - (60000 if asset == CIRCLE_USDC else 200), bytecode_hash="0x" + "ab" * 32,
    ) for asset, (feed, description, age) in sorted(FEEDS.items())]
    return OraclePrice(chain_id=43113, vault_address="0x" + "12" * 20,
        price_usdc_usd_e8="100000000", price_wavax_usd_e8="700000000",
        price_source=CHAINLINK_SOURCE, price_timestamp=NOW - 60000,
        oracle_observed_at=NOW - 2, oracle_block_number=100,
        oracle_block_hash="0x" + "cd" * 32, oracle_feeds=feeds)


def test_real_feed_ages_do_not_become_fresh_timestamps():
    value = price()
    validate_price(value, NOW)
    assert price_fresh(value, NOW)
    assert value.price_timestamp == NOW - 60000
    assert source_hash(CHAINLINK_SOURCE) == SOURCE_HASH
    assert not price_fresh(value, NOW + 60)


@pytest.mark.parametrize("update", [
    {"price_timestamp": NOW}, {"chain_id": 31337}, {"price_wavax_usd_e8": "800000000"},
    {"oracle_observed_at": NOW + 1}, {"oracle_feeds": []},
])
def test_forged_or_incomplete_provenance_fails(update):
    with pytest.raises(ControlError):
        validate_price(price().model_copy(update=update), NOW)


@pytest.mark.parametrize("update", [
    {"updated_at": NOW - 86401}, {"round_id": "0"}, {"answered_in_round": "1"},
    {"max_age_seconds": 99999}, {"feed": "0x" + "00" * 20}, {"decimals": 6},
])
def test_source_identity_and_original_round_are_enforced(update):
    value = price()
    value.oracle_feeds[0] = value.oracle_feeds[0].model_copy(update=update)
    with pytest.raises(ControlError):
        validate_price(value, NOW)


def test_oracle_commitment_binds_round_and_heartbeat():
    value = price()
    evidence = OracleEvidence(chain_id=43113, vault=value.vault_address, source_hash=SOURCE_HASH,
        timestamp=value.oracle_observed_at, block_number=100, block_hash=value.oracle_block_hash,
        prices=tuple(Price(asset=asset, low_usd_e8=p, nominal_usd_e8=p, high_usd_e8=p)
            for asset, p in [(CIRCLE_USDC, "100000000"), (WAVAX, "700000000")]),
        feeds=tuple(value.oracle_feeds))
    altered = evidence.model_copy(update={"feeds": (evidence.feeds[0].model_copy(update={"round_id": "45"}), evidence.feeds[1])})
    assert evidence.hash != altered.hash


def test_json_writer_cannot_claim_to_be_direct_chainlink(tmp_path):
    path = tmp_path / "oracle.json"
    path.write_text(price().model_dump_json())
    with pytest.raises(ControlError, match="UNVERIFIED_PRICE"):
        JsonFilePriceProvider(path).read()
