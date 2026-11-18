import json

import httpx
import pytest
from eth_abi import encode

from app.fuji_data import (
    FUJI_RPC,
    FUJI_USDC,
    FUJI_WAVAX,
    WITNET_FUJI_ROUTER,
    FujiReadError,
    FujiReader,
)

WALLET = "0x" + "ab" * 20
NOW = 2_000_000_000


def fake_client(*, chain_id="0xa869", oracle_age=300, oracle_status=200):
    observed = []

    def handler(request):
        if request.method == "GET":
            assert str(request.url).startswith("https://api.coingecko.com/api/v3/simple/price")
            return httpx.Response(200, json={
                "avalanche-2": {"usd": 23.50, "last_updated_at": NOW - 30}
            })
        assert request.method == "POST"
        assert str(request.url) == FUJI_RPC
        req = json.loads(request.content)
        method, params = req["method"], req["params"]
        observed.append(method)
        result = None
        if method == "eth_chainId":
            result = chain_id
        elif method == "eth_getBlockByNumber":
            result = {
                "number": "0x10",
                "hash": "0x" + "a1" * 32,
                "timestamp": hex(NOW),
            }
        elif method == "eth_getBalance":
            result = hex(10**18)
        elif method == "eth_getCode":
            assert params[0].lower() in {
                FUJI_USDC.lower(),
                FUJI_WAVAX.lower(),
                WITNET_FUJI_ROUTER.lower(),
            }
            result = "0x60006000"
        elif method == "eth_call":
            call = params[0]
            selector = call["data"][:10]
            if selector == "0x313ce567":
                decimals = 6 if call["to"].lower() == FUJI_USDC.lower() else 18
                result = "0x" + (decimals).to_bytes(32, "big").hex()
            elif selector == "0x70a08231":
                amount = 12 * 10**6 if call["to"].lower() == FUJI_USDC.lower() else 3 * 10**18
                result = "0x" + amount.to_bytes(32, "big").hex()
            else:
                assert call["to"].lower() == WITNET_FUJI_ROUTER.lower()
                result = "0x" + encode(
                    ["int256", "uint256", "uint256"],
                    [23_400_000, NOW - oracle_age, oracle_status],
                ).hex()
        else:
            raise AssertionError("Unexpected unsafe RPC method: " + method)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": req["id"], "result": result})

    return httpx.Client(transport=httpx.MockTransport(handler)), observed


def test_same_block_wallet_balances_and_oracle_provenance():
    http, observed = fake_client()
    with http:
        out = FujiReader(http, now=NOW).snapshot(WALLET)
    assert out["chain_id"] == 43113
    assert out["block_number"] == 16
    assert [v["balance_base_units"] for v in out["assets"]] == [
        str(10**18), str(12 * 10**6), str(3 * 10**18)
    ]
    assert out["oracle"]["price_usd_e8"] == "2340000000"
    assert out["oracle"]["status"] == "FRESH"
    assert out["oracle"]["usable_for_decisions"] is False
    assert out["used_for_sde_or_attestation"] is False
    assert all(m in {"eth_chainId", "eth_getBlockByNumber", "eth_getBalance", "eth_getCode", "eth_call"} for m in observed)


@pytest.mark.parametrize("age,status,expected", [
    (31 * 60 * 60, 200, "STALE"),
    (100, 404, "UNVERIFIED"),
])
def test_untrusted_oracle_never_authorizes(age, status, expected):
    http, _ = fake_client(oracle_age=age, oracle_status=status)
    with http:
        out = FujiReader(http, now=NOW).snapshot(WALLET)
    assert out["oracle"]["status"] == expected
    assert not out["oracle"]["usable_for_decisions"]


def test_wrong_network_fails_closed():
    http, observed = fake_client(chain_id="0xa86a")
    with http, pytest.raises(FujiReadError, match="FUJI_CHAIN_MISMATCH"):
        FujiReader(http, now=NOW).snapshot(WALLET)
    assert observed == ["eth_chainId"]


def test_invalid_wallet_does_not_hit_network():
    http, observed = fake_client()
    with http, pytest.raises(FujiReadError, match="INVALID_WALLET_ADDRESS"):
        FujiReader(http, now=NOW).snapshot("not-a-wallet")
    assert observed == []


def test_unsafe_method_is_never_forwarded():
    http, observed = fake_client()
    with http, pytest.raises(FujiReadError, match="UNSAFE_RPC_METHOD"):
        FujiReader(http).rpc("eth_sendRawTransaction", ["0xdeadbeef"])
    assert observed == []


def test_optional_coingecko_is_real_api_shape_but_never_authorizes(monkeypatch):
    monkeypatch.setenv("PACEVANT_COINGECKO_DEMO_KEY", "test-only-key")
    http, observed = fake_client()
    with http:
        out = FujiReader(http, now=NOW).snapshot(WALLET)
    assert out["market"]["price_usd_e8"] == "2350000000"
    assert out["market"]["status"] == "FRESH"
    assert out["market"]["usable_for_decisions"] is False
    assert "eth_sendRawTransaction" not in observed
