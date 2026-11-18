import json

import httpx
import pytest
import rfc8785
from eth_abi import encode
from eth_utils import keccak
from fastapi.testclient import TestClient

from app.fuji_api import create_readonly_app
from app.fuji_data import FUJI_USDC, FUJI_WAVAX, WITNET_FUJI_ROUTER, FujiReader
from app.fuji_oracles import CHAINLINK_FEEDS, PYTH_FUJI
from app.fuji_rpc import FUJI_RPC, FujiReadError
from app.fuji_service import FujiService

WALLET = "0x" + "ab" * 20
VAULT = "0x" + "11" * 20
OWNER = "0x" + "22" * 20
ATTESTOR = "0x" + "33" * 20
TX = "0x" + "b1" * 32
NOW = 2_000_000_000
BLOCK_HASH = "0x" + "a1" * 32
TOKEN = "observer-test-token-with-at-least-24-characters"


def selector(signature):
    return "0x" + keccak(text=signature)[:4].hex()


def encoded(types, values):
    return "0x" + encode(types, values).hex()


def transport(
    *,
    chain_id="0xa869",
    oracle_age=300,
    oracle_status=200,
    malformed=None,
    reorg=False,
    missing_token=False,
    requests=None,
):
    requests = requests if requests is not None else []
    block_reads = [0]

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            assert request.headers.get("x-cg-demo-api-key") == "test-only-key"
            return httpx.Response(
                200,
                json={
                    "avalanche-2": {"usd": 23.5, "last_updated_at": NOW - 30},
                },
            )
        assert str(request.url) == FUJI_RPC
        assert "x-cg-demo-api-key" not in request.headers
        req = json.loads(request.content)
        method, params = req["method"], req["params"]
        if method == "eth_chainId":
            result = chain_id
        elif method == "eth_getBlockByNumber":
            block_reads[0] += 1
            result = {
                "number": "0x10",
                "hash": BLOCK_HASH,
                "timestamp": hex(NOW),
            }
            if malformed == "timestamp":
                result["timestamp"] = "0xzz"
            elif malformed == "stale_block":
                result["timestamp"] = hex(NOW - 121)
            elif reorg and block_reads[0] > 1:
                result["hash"] = "0x" + "aa" * 32
        elif method == "eth_getBalance":
            assert params[-1] == "0x10"
            result = "0xzz" if malformed == "balance" else hex(10**18)
        elif method == "eth_getCode":
            assert params[-1] == "0x10"
            result = "0x" if missing_token and params[0] == FUJI_USDC.lower() else "0x60006000"
        elif method == "eth_call":
            assert params[-1] == "0x10"
            call = params[0]
            address = call["to"]
            method_id = call["data"][:10]
            if malformed == "abi" and address == WITNET_FUJI_ROUTER.lower():
                result = "0xzz"
            elif method_id == selector("decimals()"):
                decimals = (
                    6
                    if address == FUJI_USDC.lower()
                    else 8
                    if address in {feed[1].lower() for feed in CHAINLINK_FEEDS}
                    else 18
                )
                result = encoded(["uint8"], [decimals])
            elif method_id == selector("balanceOf(address)"):
                result = encoded(
                    ["uint256"], [12 * 10**6 if address == FUJI_USDC.lower() else 3 * 10**18]
                )
            elif method_id == selector("description()"):
                pair = next(feed[0] for feed in CHAINLINK_FEEDS if feed[1].lower() == address)
                result = encoded(["string"], [pair.replace("/", " / ")])
            elif method_id == selector("latestRoundData()"):
                result = encoded(
                    ["uint80", "int256", "uint256", "uint256", "uint80"],
                    [
                        5,
                        -1 if malformed == "negative_price" else 2_340_000_000,
                        NOW - oracle_age,
                        NOW - oracle_age,
                        4 if malformed == "incomplete_round" else 5,
                    ],
                )
            elif method_id == selector("valueFor(bytes32)"):
                result = encoded(
                    ["int256", "uint256", "uint256"], [23_400_000, NOW - oracle_age, oracle_status]
                )
            elif address == PYTH_FUJI.lower():
                result = encoded(
                    ["int64", "uint64", "int32", "uint256"],
                    [2_340_000_000, 1_000_000, -8, NOW - oracle_age],
                )
            else:
                assert address == VAULT
                fields = {
                    "owner()": (["address"], [OWNER]),
                    "attestor()": (["address"], [ATTESTOR]),
                    "usdc()": (["address"], [FUJI_USDC]),
                    "wavax()": (["address"], [FUJI_WAVAX]),
                    "activePolicyHash()": (["bytes32"], [bytes.fromhex("a2" * 32)]),
                    "policyActive()": (["bool"], [True]),
                    "paused()": (["bool"], [False]),
                    "policyVersion()": (["uint256"], [2]),
                    "policyExpiresAt()": (["uint256"], [NOW + 1000]),
                    "maxPerSwap()": (["uint256"], [500_000_000]),
                    "maxSpendPerDay()": (["uint256"], [1_000_000_000]),
                    "dailySpentUsdc(uint256)": (["uint256"], [200_000_000]),
                    "usedNonce(uint256)": (["bool"], [True]),
                }
                abi, values = next(
                    value for name, value in fields.items() if selector(name) == method_id
                )
                result = encoded(abi, values)
        elif method == "eth_getTransactionReceipt":
            result = {
                "transactionHash": TX,
                "blockNumber": "0x10",
                "blockHash": BLOCK_HASH,
                "gasUsed": "0x5208",
                "effectiveGasPrice": "0x1",
                "status": "0x1",
                "to": VAULT,
                "logs": [
                    {
                        "address": VAULT,
                        "topics": [
                            "0x"
                            + keccak(
                                text="SwapExecuted(uint256,bytes32,bytes32,address,address,uint256,uint256)"
                            ).hex(),
                            "0x" + (7).to_bytes(32, "big").hex(),
                            "0x" + "a2" * 32,
                        ],
                        "data": encoded(
                            ["bytes32", "address", "address", "uint256", "uint256"],
                            [
                                bytes.fromhex("a3" * 32),
                                FUJI_USDC,
                                FUJI_WAVAX,
                                200_000_000,
                                10 * 10**18,
                            ],
                        ),
                    }
                ],
            }
            if malformed == "receipt_hash":
                result["blockHash"] = None
            elif malformed == "receipt_recipient":
                result["to"] = 123
            elif malformed == "receipt_event":
                result["logs"][0]["data"] += "00"
        else:
            raise AssertionError(method)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": req["id"], "result": result})

    return httpx.MockTransport(handler), requests


def read(**options):
    mock, requests = transport(**options)
    with httpx.Client(transport=mock) as http:
        result = FujiReader(http, now=NOW).snapshot(WALLET)
    return result, requests


def test_balances_oracle_identity_and_block_binding():
    out, requests = read()
    assert [asset["balance_base_units"] for asset in out["assets"]] == [
        str(10**18),
        str(12 * 10**6),
        str(3 * 10**18),
    ]
    assert out["block_hash"] == BLOCK_HASH
    assert out["block_binding"] == "PINNED_HEIGHT_HASH_RECHECKED"
    assert out["oracle"]["status"] == "WITHIN_HEARTBEAT"
    assert out["oracles"][0]["price_usd_e8"] == "2340000000"
    assert out["oracles"][0]["round_id"] == "5"
    assert out["oracles"][-1]["status"] == "STALE"
    assert not any(item["usable_for_decisions"] for item in out["oracles"])
    assert not out["used_for_sde_or_attestation"]
    assert all(
        json.loads(request.content)["method"] != "eth_sendRawTransaction" for request in requests
    )
    root = out.pop("observation_hash")
    assert root == "0x" + keccak(rfc8785.dumps(out)).hex()


@pytest.mark.parametrize(
    "age,status,expected",
    [
        (86401, 200, "STALE"),
        (100, 404, "UNVERIFIED"),
        (-1, 200, "UNVERIFIED"),
    ],
)
def test_oracle_stale_unresolved_and_future_are_explicit(age, status, expected):
    out, _ = read(oracle_age=age, oracle_status=status)
    assert out["oracle"]["status"] == expected
    assert out["oracle"]["usable_for_decisions"] is False


@pytest.mark.parametrize(
    "malformed,code",
    [
        ("timestamp", "FUJI_BAD_BLOCK"),
        ("balance", "FUJI_BAD_BALANCE"),
        ("stale_block", "FUJI_BLOCK_STALE"),
    ],
)
def test_bad_rpc_quantities_use_domain_errors(malformed, code):
    with pytest.raises(FujiReadError, match=code):
        read(malformed=malformed)


def test_bad_abi_source_does_not_hide_wallet_balances():
    out, _ = read(malformed="abi")
    assert out["oracle"]["status"] == "UNAVAILABLE"
    assert out["oracle"]["reason_code"] == "FUJI_BAD_CALL_RESULT"
    assert out["assets"][0]["balance_base_units"] == str(10**18)


@pytest.mark.parametrize("malformed", ["negative_price", "incomplete_round"])
def test_invalid_chainlink_round_never_displays_a_valid_price(malformed):
    out, _ = read(malformed=malformed)
    assert out["oracles"][0]["status"] == "UNVERIFIED"
    assert "price_usd_e8" not in out["oracles"][0]


@pytest.mark.parametrize("malformed", ["receipt_hash", "receipt_recipient", "receipt_event"])
def test_malformed_receipt_is_a_domain_error(malformed):
    mock, _ = transport(malformed=malformed)
    with httpx.Client(transport=mock) as http:
        with pytest.raises(FujiReadError, match="FUJI_BAD_RECEIPT"):
            FujiReader(http, now=NOW).snapshot(WALLET, vault_address=VAULT, tx_hash=TX)


def test_missing_token_is_partial_without_invented_zero():
    out, _ = read(missing_token=True)
    assert out["snapshot_status"] == "PARTIAL"
    assert out["assets"][1]["status"] == "UNAVAILABLE"
    assert "balance_base_units" not in out["assets"][1]


def test_reorg_refuses_a_mixed_block_snapshot():
    with pytest.raises(FujiReadError, match="FUJI_BLOCK_CHANGED"):
        read(reorg=True)


def test_mainnet_is_rejected_before_reading_assets():
    requests = []
    with pytest.raises(FujiReadError, match="FUJI_CHAIN_MISMATCH"):
        read(chain_id="0xa86a", requests=requests)
    assert len(requests) == 1


def test_invalid_address_and_transaction_rpc_are_rejected():
    mock, requests = transport()
    with httpx.Client(transport=mock) as http:
        reader = FujiReader(http, now=NOW)
        with pytest.raises(FujiReadError, match="INVALID_WALLET_ADDRESS"):
            reader.snapshot("https://invalid.example")
        with pytest.raises(FujiReadError, match="UNSAFE_RPC_METHOD"):
            reader.rpc("eth_sendRawTransaction", ["0xdeadbeef"])
    assert requests == []


def test_optional_market_key_never_reaches_fuji(monkeypatch):
    monkeypatch.setenv("PACEVANT_COINGECKO_DEMO_KEY", "test-only-key")
    out, _ = read()
    assert out["market"]["price_usd_e8"] == "2350000000"
    assert out["market"]["status"] == "FRESH"
    assert not out["market"]["usable_for_decisions"]


def test_vault_budget_and_receipt_event_are_read_from_same_chain():
    mock, _ = transport()
    with httpx.Client(transport=mock) as http:
        out = FujiReader(http, now=NOW).snapshot(WALLET, vault_address=VAULT, tx_hash=TX)
    assert out["vault"]["status"] == "VERIFIED"
    assert out["vault"]["daily_spent_usdc_base_units"] == "200000000"
    assert out["vault"]["remaining_daily_usdc_base_units"] == "800000000"
    assert out["vault"]["assets"][0]["contract"] == FUJI_USDC.lower()
    receipt = out["receipt"]
    assert receipt["status"] == "CONFIRMED" and receipt["vault_match"]
    assert receipt["gas_cost_wei"] == "21000"
    assert receipt["swap_events"][0]["nonce"] == "7"
    assert receipt["swap_events"][0]["nonce_used_at_snapshot"] is True
    assert receipt["swap_events"][0]["amount_out_base_units"] == str(10 * 10**18)


def test_service_cache_rate_limit_and_standalone_auth():
    mock, requests = transport()
    service = FujiService(httpx.Client(transport=mock), clock=lambda: NOW, monotonic=lambda: 0)
    with TestClient(create_readonly_app(TOKEN, service)) as api:
        assert api.get("/fuji-wallet").status_code == 200
        assert api.get("/healthz").json()["mode"] == "FUJI_READONLY"
        assert api.get(f"/v1/fuji/wallet/{WALLET}").status_code == 401
        headers = {"Authorization": f"Bearer {TOKEN}"}
        first = api.get(f"/v1/fuji/wallet/{WALLET}", headers=headers)
        assert first.status_code == 200
        calls = len(requests)
        second = api.get(f"/v1/fuji/wallet/{WALLET}", headers=headers)
        assert second.json()["cached"] and len(requests) == calls
        assert second.json()["observed_at"] == first.json()["observed_at"]
        assert api.get("/v1/fuji/wallet/invalid", headers=headers).status_code == 400
        for _ in range(28):
            assert api.get(f"/v1/fuji/wallet/{WALLET}", headers=headers).status_code == 200
        assert api.get(f"/v1/fuji/wallet/{WALLET}", headers=headers).status_code == 429


def test_concurrency_limit_returns_busy():
    mock, requests = transport()
    service = FujiService(httpx.Client(transport=mock), clock=lambda: NOW)
    service.slots.acquire()
    service.slots.acquire()
    try:
        with pytest.raises(FujiReadError, match="FUJI_READER_BUSY"):
            service.snapshot(WALLET)
        assert not requests
    finally:
        service.slots.release()
        service.slots.release()
        service.close()


def test_total_time_budget_is_bounded():
    elapsed = [0]
    mock, _ = transport()
    original = mock.handler

    def delayed(request):
        result = original(request)
        elapsed[0] += 6
        return result

    with httpx.Client(transport=httpx.MockTransport(delayed)) as http:
        with pytest.raises(FujiReadError, match="FUJI_READ_TIMEOUT"):
            FujiReader(http, now=NOW, monotonic=lambda: elapsed[0]).snapshot(WALLET)
