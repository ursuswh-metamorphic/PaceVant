"""Deterministic unit/security checks. These are not evidence of live liquidity."""

from types import SimpleNamespace
import pytest
from eth_abi import decode, encode
from web3 import Web3
from app.dex.lfj import LFJClient, QUOTER, QUOTE_TYPE, ROUTER, USDC, WAVAX
from app.errors import PlaneError
from app.evidence.extractor import token_facts, TRANSFER, APPROVAL
from app.execution.relayer import Relayer

PAIR = "0x" + "11" * 20
FACTORY = "0x" + "22" * 20
VAULT = "0x" + "33" * 20
ADAPTER = "0x" + "44" * 20


class FakeEth:
    chain_id = 43113

    def __init__(self, *, version=0, zero=False, invalid_route=False):
        self.version, self.zero, self.invalid_route = version, zero, invalid_route
        self.calls = []

    def get_code(self, address, block):
        self.calls.append(("code", block))
        return b"\x60\x00"

    def get_block(self, block):
        return SimpleNamespace(hash=bytes.fromhex("aa" * 32), number=123, timestamp=2_000_000_000)

    def call(self, transaction, block_identifier):
        self.calls.append(("call", block_identifier))
        data = bytes(transaction["data"])
        sel = data[:4]

        def is_sig(sig):
            return sel == Web3.keccak(text=sig)[:4]

        addresses = {
            "getV1Factory()": FACTORY,
            "getWNATIVE()": WAVAX,
            "getRouterV2_2()": ROUTER,
            "getFactoryV1()": FACTORY,
            "getPair(address,address)": PAIR,
            "token0()": USDC,
            "token1()": WAVAX,
            "factory()": FACTORY,
        }
        for sig, value in addresses.items():
            if is_sig(sig):
                return encode(["address"], [value])
        if is_sig("getReserves()"):
            return encode(
                ["uint112", "uint112", "uint32"], [10_000 * 10**6, 1000 * 10**18, 2_000_000_000]
            )
        if is_sig("findBestPathFromAmountIn(address[],uint128)"):
            path, amount = decode(["address[]", "uint128"], data[4:])
            out = (
                0
                if self.zero
                else amount * 997 * (1000 * 10**18) // ((10_000 * 10**6) * 1000 + amount * 997)
            )
            return encode(
                [QUOTE_TYPE],
                [
                    (
                        [WAVAX, USDC] if self.invalid_route else path,
                        [PAIR],
                        [0],
                        [self.version],
                        [amount, out],
                        [amount, out],
                        [3 * 10**15],
                    )
                ],
            )
        if is_sig("decimals()"):
            return encode(["uint8"], [6])
        if is_sig("symbol()"):
            return encode(["string"], ["USDC"])
        raise AssertionError(transaction)


def client(**options):
    eth = FakeEth(**options)
    return LFJClient(SimpleNamespace(eth=eth)), eth


def test_verified_quote_uses_pinned_real_abi_and_reserve_arithmetic():
    dex, eth = client()
    out = dex.verified_quote(1_000_000, 123)
    assert out["versions"] == [0]
    assert out["route"]["pair"].lower() == PAIR
    assert int(out["amount_out_base_units"]) > 0
    assert out["independent_usd_oracle"] is False
    assert all(block == 123 for _, block in eth.calls)


@pytest.mark.parametrize("amount", [0, -1, 2**128, True])
def test_invalid_quote_amount(amount):
    dex, _ = client()
    with pytest.raises(PlaneError) as exc:
        dex.quote(amount, 123)
    assert exc.value.code == "INVALID_QUOTE_AMOUNT"


@pytest.mark.parametrize(
    "options,code",
    [
        ({"zero": True}, "NO_LIQUIDITY"),
        ({"invalid_route": True}, "LFJ_INVALID_ROUTE"),
        ({"version": 2}, "LFJ_UNSUPPORTED_ROUTE"),
    ],
)
def test_quotes_do_not_fall_back_to_synthetic_routes(options, code):
    dex, _ = client(**options)
    with pytest.raises(PlaneError) as exc:
        dex.verified_quote(1_000_000, 123)
    assert exc.value.code == code


def test_wrong_chain_rejected_before_contract_calls():
    eth = FakeEth()
    eth.chain_id = 43114
    with pytest.raises(PlaneError) as exc:
        LFJClient(SimpleNamespace(eth=eth))
    assert exc.value.code == "CHAIN_MISMATCH" and eth.calls == []


def test_decimals_are_read_and_validated():
    dex, _ = client()
    assert dex.token(USDC, 6, 123)["decimals"] == 6
    with pytest.raises(PlaneError) as exc:
        dex.token(USDC, 18, 123)
    assert exc.value.code == "TOKEN_DECIMALS_MISMATCH"


def log(kind, token, sender, recipient, value):
    return {
        "address": token,
        "topics": [
            Web3.to_bytes(hexstr=kind),
            bytes.fromhex(sender[2:].zfill(64)),
            bytes.fromhex(recipient[2:].zfill(64)),
        ],
        "data": value.to_bytes(32, "big"),
    }


def test_lfj_receipt_allows_exact_downstream_edges_only():
    logs = [
        log(APPROVAL, USDC, VAULT, ADAPTER, 100),
        log(TRANSFER, USDC, VAULT, ADAPTER, 100),
        log(APPROVAL, USDC, ADAPTER, ROUTER, 100),
        log(TRANSFER, USDC, ADAPTER, PAIR, 100),
        log(TRANSFER, WAVAX, PAIR, VAULT, 12345),
        log(APPROVAL, USDC, ADAPTER, ROUTER, 0),
        log(APPROVAL, USDC, VAULT, ADAPTER, 0),
    ]
    route = {"pair": PAIR, "lfj_router": ROUTER}
    facts = token_facts({"status": 1, "logs": logs}, VAULT, ADAPTER, USDC, WAVAX, 100, 12000, route)
    assert not facts["unexpected_transfer"] and not facts["unauthorized_approval"]
    assert facts["token_out_delta_base_units"] == "12345"
    logs.append(log(TRANSFER, WAVAX, PAIR, FACTORY, 1))
    facts = token_facts({"status": 1, "logs": logs}, VAULT, ADAPTER, USDC, WAVAX, 100, 12000, route)
    assert facts["unexpected_transfer"]


def test_disabled_broadcast_does_not_load_or_submit_a_transaction():
    eth = FakeEth()
    settings = SimpleNamespace(mode="fuji", fuji_broadcast_authorized=False)
    chain = SimpleNamespace(w3=SimpleNamespace(eth=eth), chain_id=43113, settings=settings)
    with pytest.raises(PlaneError) as exc:
        Relayer(chain, None).execute(None)
    assert exc.value.code == "BROADCAST_NOT_AUTHORIZED"


@pytest.mark.integration
def test_dry_run_validates_signed_pdr_without_sending_or_consuming_nonce(plane, monkeypatch):
    from app.models import ExecutionRequest
    from conftest import build_and_simulate, sign_pdr

    api, chain, keys, app = plane
    built, evidence = build_and_simulate(api, chain)
    request = ExecutionRequest(
        build_id=built["build_id"], signed_pdr=sign_pdr(built, evidence, keys)
    )
    before = chain.balances()

    def forbidden(*args, **kwargs):
        pytest.fail("dry-run attempted to broadcast")

    monkeypatch.setattr(chain.w3.eth, "send_raw_transaction", forbidden)
    result = app.state.relayer.execute(request, dry_run=True)
    assert result["status"] == "PREFLIGHT_PASSED" and not result["broadcast"]
    assert chain.balances() == before
    assert not chain.vault.functions.usedNonce(int(built["nonce"])).call()
    with app.state.store.db() as db:
        assert db.execute("SELECT count(*) FROM submissions").fetchone()[0] == 0
