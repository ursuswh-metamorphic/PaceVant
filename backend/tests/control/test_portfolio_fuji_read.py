"""Opt-in public Fuji reads only. The fixture account is an LFJ pool, not a user Vault."""

import os

import pytest

from treasury_backend.modules.portfolio.observations import (
    LFJ_USDC,
    WAVAX,
    PortfolioReader,
    verify_snapshot_hash,
)


@pytest.mark.skipif(
    os.environ.get("PACEVANT_PORTFOLIO_FUJI_READ") != "1", reason="opt-in public Fuji reads"
)
def test_real_fuji_lfj_token_observation_without_wallet_or_keys():
    value = PortfolioReader("FUJI", "https://api.avax-test.network/ext/bc/C/rpc").collect(
        "0x9371619c8e2a487d57fb9f8e36bcb0317bff0529"
    )
    assert value.chain_id == 43113 and verify_snapshot_hash(value)
    assert [a.contract for a in value.assets] == [None, LFJ_USDC, WAVAX]
    assert all(a.balance_base_units is not None for a in value.assets)
    assert all(a.verification_status == "VERIFIED" for a in value.assets)
    assert "VAULT_POLICY_UNAVAILABLE" in value.reason_codes
    assert not value.authorization_eligible
    assert all(
        not p.authorization_eligible and not p.valuation_eligible for p in value.price_observations
    )
    assert any("ORACLE_TOKEN_IDENTITY_MISMATCH" in p.reason_codes for p in value.price_observations)
