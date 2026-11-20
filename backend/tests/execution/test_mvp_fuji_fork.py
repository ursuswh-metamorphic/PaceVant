"""Opt-in real LFJ routing on Anvil. No private keys and NO PUBLIC WRITES.

Route compatibility is distinct from full PACE/PGS authorization (covered locally).
The public pool's reverse quote is expected to fail the unchanged economic policy.
"""

import json
import os
from fractions import Fraction

import pytest
from web3 import Web3
from web3.exceptions import ContractLogicError

from treasury_backend.config.execution import Settings
from treasury_backend.core.errors import ControlError
from treasury_backend.modules.execution.chain import artifact, contract
from treasury_backend.modules.execution.dex.lfj import LFJClient
from treasury_backend.modules.execution.errors import PlaneError
from treasury_backend.modules.execution.simulation.runner import fork_node, rpc
from treasury_backend.modules.oracle.chainlink import ChainlinkPriceProvider
from treasury_backend.paths import ROOT
from treasury_contracts.rpc import evm_web3

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("PACEVANT_MVP_FORK") != "1",
        reason="Opt-in public reads; writes only to isolated Anvil fork",
    ),
]


@pytest.fixture(scope="module")
def real_route():
    url = "https://api.avax-test.network/ext/bc/C/rpc"
    source = Settings(_env_file=None, mode="fuji", rpc_url=url)
    public = evm_web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 20}))
    height = public.eth.block_number
    manifest = json.loads((ROOT / "deployments/treasury-fuji-v2.json").read_text())
    results = []
    with fork_node(source, height, 43113) as w3:
        assert (
            w3.client_version.lower().startswith("anvil")
            and "127.0.0.1" in w3.provider.endpoint_uri
        )
        rpc(w3, "anvil_setBlockTimestampInterval", [0])
        owner = Web3.to_checksum_address(manifest["owner"])
        rpc(w3, "anvil_impersonateAccount", [owner])
        rpc(w3, "anvil_setBalance", [owner, hex(10**18)])

        def deploy(name, *args):
            a = artifact(name)
            f = w3.eth.contract(abi=a["abi"], bytecode=a["bytecode"]["object"])
            receipt = w3.eth.wait_for_transaction_receipt(
                f.constructor(*args).transact({"from": owner})
            )
            assert receipt.status == 1
            return w3.eth.contract(address=receipt.contractAddress, abi=a["abi"])

        u = contract(w3, "MockUSDC", manifest["token_in"])
        w = contract(w3, "MockWAVAX", manifest["token_out"])
        vault = deploy("PolicyVaultMVP", owner, manifest["attestor"], u.address, w.address)
        route = LFJClient(w3, u.address).v1_route(height)
        adapter = deploy(
            "LFJSwapAdapterV3",
            vault.address,
            route["lfj_router"],
            route["pair"],
            u.address,
            w.address,
        )
        receipt = w3.eth.wait_for_transaction_receipt(
            u.functions.transfer(vault.address, 2 * 10**6).transact({"from": owner})
        )
        assert receipt.status == 1
        rpc(w3, "anvil_impersonateAccount", [vault.address])
        rpc(w3, "anvil_setBalance", [vault.address, hex(10**18)])
        yield w3, vault, adapter, u, w, route, results
    output = {
        "environment": "ANVIL_FORK",
        "source_block": height,
        "public_writes": False,
        "scope": "Real LFJ route compatibility and independent economic rejection; not a new public Fuji execution",
        "results": results,
    }
    path = ROOT / "docs/audit/mvp-fork-route-results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")


@pytest.fixture
def route_case(real_route):
    w3, *_ = real_route
    snap = rpc(w3, "evm_snapshot", [])
    yield real_route
    assert rpc(w3, "evm_revert", [snap])


def swap(case, reverse=False, amount=1000):
    w3, vault, adapter, u, w, route, results = case
    token_in, token_out = (w, u) if reverse else (u, w)
    quote = adapter.functions.quote(token_in.address, token_out.address, amount).call()
    current = LFJClient(w3, u.address).v1_route(w3.eth.block_number)
    dex = LFJClient(w3, u.address)
    selected = dex.quote(amount, w3.eth.block_number, reverse=reverse)
    matches = (
        selected["pairs"][0].lower() == current["pair"].lower()
        and selected["versions"] == [0]
        and selected["bin_steps"] == [0]
    )
    if matches:
        official = dex.verified_quote(amount, w3.eth.block_number, current, reverse=reverse)
        assert int(official["amount_out_base_units"]) == quote
    else:
        with pytest.raises(PlaneError) as error:
            dex.verified_quote(amount, w3.eth.block_number, current, reverse=reverse)
        assert error.value.code == "LFJ_UNSUPPORTED_ROUTE"
    results.append(
        {
            "case": "REVERSE_QUOTER" if reverse else "FORWARD_QUOTER",
            "status": "MATCHES_APPROVED_V1" if matches else "REJECTED_BEFORE_BROADCAST",
            "selected_pairs": selected["pairs"],
            "selected_versions": selected["versions"],
            "scope": "Route-only adapter experiment below does not override the MVP authorization gate",
        }
    )
    r0, r1 = map(int, current["reserves"])
    ri, ro = (r0, r1) if current["token0"].lower() == token_in.address.lower() else (r1, r0)
    assert quote == amount * 997 * ro // (ri * 1000 + amount * 997)
    before_in = token_in.functions.balanceOf(vault.address).call()
    before_out = token_out.functions.balanceOf(vault.address).call()
    receipt = w3.eth.wait_for_transaction_receipt(
        token_in.functions.approve(adapter.address, amount).transact({"from": vault.address})
    )
    assert receipt.status == 1
    tx = adapter.functions.exactInput(
        token_in.address, token_out.address, amount, quote * 99 // 100, vault.address
    ).transact({"from": vault.address})
    receipt = w3.eth.wait_for_transaction_receipt(tx)
    assert receipt.status == 1
    assert before_in - token_in.functions.balanceOf(vault.address).call() == amount
    assert token_out.functions.balanceOf(vault.address).call() - before_out == quote
    assert (
        token_in.functions.allowance(
            adapter.address, Web3.to_checksum_address(route["lfj_router"])
        ).call()
        == 0
    )
    # Route-only setup grants exact input; clean it up like the PolicyVault wrapper does.
    token_in.functions.approve(adapter.address, 0).transact({"from": vault.address})
    assert token_in.functions.allowance(vault.address, adapter.address).call() == 0
    return quote, Web3.to_hex(tx)


def test_mvp_real_forward_lfj_route(route_case):
    quote, tx = swap(route_case)
    route_case[-1].append(
        {
            "case": "USDC_TO_WAVAX",
            "status": "PASS",
            "input": "1000",
            "output": str(quote),
            "fork_tx_hash": tx,
        }
    )


def test_mvp_real_reverse_lfj_route(route_case):
    swap(route_case)
    quote, tx = swap(route_case, True, 10**15)
    route_case[-1].append(
        {
            "case": "WAVAX_TO_USDC",
            "status": "PASS",
            "input": str(10**15),
            "output": str(quote),
            "fork_tx_hash": tx,
        }
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_mvp_real_routes_reject_bad_recipient_and_slippage(route_case, reverse):
    w3, vault, adapter, u, w, _, results = route_case
    if reverse:
        swap(route_case)
    ti, to = (w, u) if reverse else (u, w)
    size = 10**15 if reverse else 1000
    q = adapter.functions.quote(ti.address, to.address, size).call()
    with pytest.raises(ContractLogicError):
        adapter.functions.exactInput(
            ti.address, to.address, size, 1, route_case[1].functions.owner().call()
        ).call({"from": vault.address})
    with pytest.raises(ContractLogicError):
        adapter.functions.exactInput(ti.address, to.address, size, q + 1, vault.address).call(
            {"from": vault.address}
        )
    with pytest.raises(ContractLogicError):
        adapter.functions.quote(ti.address, ti.address, size).call()
    results.append(
        {"case": "REVERSE_ADVERSARIAL" if reverse else "FORWARD_ADVERSARIAL", "status": "PASS"}
    )


def test_mvp_real_reverse_economic_divergence_rejected(route_case):
    w3, vault, adapter, u, w, _, results = route_case
    try:
        price = ChainlinkPriceProvider(w3.provider.endpoint_uri, vault.address).read()
    except ControlError as exc:
        results.append({"case": "REVERSE_ECONOMICS", "status": "NOT_VERIFIED", "reason": exc.code})
        pytest.skip("Fresh independent Chainlink evidence unavailable; no price fallback")
    size = 10**15
    quote = adapter.functions.quote(w.address, u.address, size).call()
    fair = Fraction(
        size * int(price.price_wavax_usd_e8) * 10**6, 10**18 * int(price.price_usdc_usd_e8)
    )
    existing = json.loads((ROOT / "deployments/treasury-fuji-v2.json").read_text())
    policy = contract(w3, "PolicyVault", existing["vault_address"]).functions.proofPolicy().call()
    assert quote * 10000 < fair * (10000 - policy[1])
    results.append(
        {
            "case": "REVERSE_ECONOMICS",
            "status": "REJECTED_BEFORE_BROADCAST",
            "loss_bps_floor": str(int((1 - Fraction(quote, 1) / fair) * 10000)),
            "owner_max_relative_loss_bps": policy[1],
            "oracle_block_hash": price.oracle_block_hash,
        }
    )
