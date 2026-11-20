"""Real isolated Anvil receipts, with adversarial read responses. No public writes."""

import json

import httpx
import pytest
from web3 import Web3

from conftest import build_and_simulate, post, sign_pdr
from treasury_contracts.models import BuiltTransaction, SignedPDR
from treasury_contracts.outcomes import verify_outcome
from treasury_contracts.readonly import readonly_web3
from treasury_contracts.token_facts import TRANSFER


@pytest.mark.integration
@pytest.mark.parametrize("mutation", ["none", "pending", "lagging_head", "lagging_transaction", "outage", "chain", "tx_hash", "block_hash", "recipient", "calldata", "missing_event", "malformed_event", "token_delta", "nonce", "policy", "allowance"])
def test_canonical_verifier_rejects_contradictions(plane, mutation):
    client, chain, keys, _ = plane
    b, e = build_and_simulate(client, chain)
    p = sign_pdr(b, e, keys)
    tx = post(client, "/v1/executions", {"build_id": b["build_id"], "signed_pdr": p}).raise_for_status().json()["tx_hash"]
    calls = []

    def transport(request):
        payload = json.loads(request.content)
        method = payload["method"]
        calls.append(method)
        if mutation == "outage":
            return httpx.Response(503)
        raw = httpx.post(chain.settings.rpc_url, json=payload).json()
        value = raw.get("result")
        if mutation == "chain" and method == "eth_chainId":
            raw["result"] = "0x1"
        if method == "eth_getTransactionByHash" and value:
            if mutation == "lagging_transaction":
                value["blockHash"] = value["blockNumber"] = None
            if mutation == "recipient":
                value["to"] = "0x" + "77" * 20
            if mutation == "calldata":
                value["input"] = "0x"
        if method == "eth_getTransactionReceipt" and value:
            if mutation == "pending":
                raw["result"] = None
            if mutation == "tx_hash":
                value["transactionHash"] = "0x" + "88" * 32
            if mutation == "block_hash":
                value["blockHash"] = "0x" + "88" * 32
            swaps = [log for log in value["logs"] if log["address"].lower() == b["vault_address"].lower()]
            if mutation == "missing_event":
                value["logs"] = [log for log in value["logs"] if log not in swaps]
            if mutation == "malformed_event":
                for log in swaps:
                    log["data"] = "0x01"
            if mutation == "policy":
                for log in swaps:
                    log["topics"][2] = "0x" + "88" * 32
            if mutation == "token_delta":
                for log in value["logs"]:
                    if log["topics"][0] == TRANSFER and log["address"].lower() == b["token_out"].lower():
                        log["data"] = "0x" + (1).to_bytes(32, "big").hex()
        if mutation == "lagging_head" and method == "eth_getBlockByNumber" and payload["params"][0] == "latest" and value:
            value["number"] = hex(int(value["number"], 16) - 1)
        if method == "eth_call":
            selector = payload["params"][0]["data"][:10]
            if mutation == "nonce" and selector == Web3.to_hex(Web3.keccak(text="usedNonce(uint256)")[:4]):
                raw["result"] = "0x" + "00" * 32
            if mutation == "allowance" and selector == Web3.to_hex(Web3.keccak(text="allowance(address,address)")[:4]):
                raw["result"] = "0x" + (1).to_bytes(32, "big").hex()
        return httpx.Response(200, json=raw)

    with httpx.Client(transport=httpx.MockTransport(transport)) as http:
        reader = readonly_web3(chain.settings.rpc_url, 31337, client=http)
        report = verify_outcome(reader, BuiltTransaction.model_validate(b), SignedPDR.model_validate(p), tx,
                                expected_relayer=chain.deployment["relayer"], expected_attestor=chain.deployment["attestor"],
                                bytecode_hash=e["bytecode_hash"], evidence_root=e["evidence_root"])
    if mutation == "none":
        assert report.verification_status == "VERIFIED", report
        assert report.gas_verified and report.gas_payer_role == "RELAYER"
        assert report.nonce_used and report.allowances == {"vault_to_adapter": "0"}
        remote = client.get(f"/v1/executions/{tx}/reconciliation").raise_for_status().json()
        assert remote["verification_status"] == "VERIFIED"
        found = client.get(f"/v1/submissions/by-build/{b['build_id']}").raise_for_status().json()
        assert found["tx_hash"] == tx
    elif mutation in {"pending", "lagging_head", "lagging_transaction"}:
        assert report.verification_status == "PENDING"
        assert not report.gas_verified
    elif mutation in {"chain", "outage"}:
        assert report.verification_status == "UNAVAILABLE"
    else:
        assert report.verification_status in {"MISMATCH", "REORGED"}, report
    assert not any("send" in call.lower() or "sign" in call.lower() for call in calls)
