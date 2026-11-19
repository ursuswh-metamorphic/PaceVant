import pytest
from web3 import Web3
from treasury_backend.operations.execution import send
from treasury_backend.modules.execution.crypto import content_hash, message
from treasury_backend.modules.execution.models import Approval, Domain
from treasury_contracts.client import ExecutionClient
from treasury_contracts.models import BuiltTransaction, SimulationEvidence
from eth_account import Account
from treasury_backend.modules.execution.chain import artifact
from treasury_backend.modules.execution.simulation.runner import rpc
from conftest import build_and_simulate, post, proposal, sign_pdr


@pytest.mark.integration
def test_real_http_e2e_evidence_signature_receipt_and_retry(plane):
    client, chain, keys, app = plane
    before = chain.snapshot()
    b, e = build_and_simulate(client, chain)
    assert e["source"] == "REAL_LOCAL_SIM" and e["verification_status"] == "COMPLETE"
    assert e["baseline"]["token_in_delta_base_units"] == "-200000000"
    assert e["baseline"]["token_out_delta_base_units"] == "10000000000000000000"
    assert [s["status"] for s in e["stress_tests"]] == [
        "SUCCESS_SAFE",
        "PROTECTED_REVERT",
    ]
    assert (
        chain.snapshot() == before
    )  # fork never writes source RPC, including block number.
    manifest_response = client.get(e["evidence_manifest_ref"])
    manifest = manifest_response.json()
    assert content_hash(manifest) == e["evidence_root"]
    sdk = ExecutionClient("http://testserver", "unused")
    sdk.http.close()
    sdk.http = client
    sdk.verify_evidence(
        BuiltTransaction.model_validate(b), SimulationEvidence.model_validate(e)
    )
    repeated = post(
        client,
        "/v1/simulations",
        {"build_id": b["build_id"], "expected_policy_hash": b["policy_hash"]},
        "sim-new-key",
    )
    assert repeated.json() == e
    for a in manifest["scenario_artifacts"]:
        raw = client.get(a["ref"])
        assert raw.status_code == 200
        assert content_hash(raw.json()) == a["content_hash"]
        assert raw.json()["trace"]
        if raw.json()["scenario"]["scenario_id"] == "reserve_shift_adverse":
            assert raw.json()["receipt"]["status"] == 0
            assert raw.json()["before"] == raw.json()["after"]
    p = sign_pdr(b, e, keys)
    assert (
        Web3.to_hex(
            chain.vault.functions.hashApproval(
                tuple(
                    int(p["approval"][n]) if t == "uint256" else p["approval"][n]
                    for n, t in __import__(
                        "treasury_backend.modules.execution.crypto", fromlist=["APPROVAL_FIELDS"]
                    ).APPROVAL_FIELDS
                )
            ).call()
        )
        == p["typed_data_hash"]
    )
    request = {"build_id": b["build_id"], "signed_pdr": p}
    response = post(client, "/v1/executions", request)
    assert response.status_code == 200, response.text
    tx = response.json()["tx_hash"]
    result = client.get("/v1/executions/" + tx).json()
    assert result["status"] == "CONFIRMED"
    assert result["actual_token_in_delta_base_units"] == "-200000000"
    assert result["actual_token_out_delta_base_units"] == "10000000000000000000"
    assert result["event_refs"] == ["SwapExecuted"]
    assert post(client, "/v1/executions", request).json()["tx_hash"] == tx
    assert (
        post(client, "/v1/executions", request, key="retry-new-key").json()["tx_hash"]
        == tx
    )
    assert (
        chain.vault.functions.dailySpentUsdc(
            chain.context()["timestamp"] // 86400
        ).call()
        == 200000000
    )


@pytest.mark.integration
def test_tampered_signature_and_policy_change_denied(plane):
    client, chain, keys, _ = plane
    b, e = build_and_simulate(client, chain)
    p = sign_pdr(b, e, keys)
    changed = {**p, "approval": {**p["approval"], "minAmountOut": "1"}}
    r = post(
        client, "/v1/executions", {"build_id": b["build_id"], "signed_pdr": changed}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "HASH_MISMATCH"
    wrong = Account.create()
    signed = Account.sign_message(
        message(
            Domain.model_validate(p["domain"]), Approval.model_validate(p["approval"])
        ),
        wrong.key,
    )
    changed = {**p, "signature": Web3.to_hex(signed.signature)}
    r = post(
        client,
        "/v1/executions",
        {"build_id": b["build_id"], "signed_pdr": changed},
        "bad-signer",
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "BAD_SIGNATURE"
    send(
        chain.w3, Account.from_key(keys["owner"]), chain.vault.functions.revokePolicy()
    )
    r = post(
        client,
        "/v1/executions",
        {"build_id": b["build_id"], "signed_pdr": p},
        "revoked",
    )
    assert (
        r.status_code == 409
        and r.json()["error"]["code"] == "STALE_REQUIRES_REEVALUATION"
    )


@pytest.mark.integration
def test_missing_simulation_not_accepted(plane):
    client, chain, keys, _ = plane
    b = post(client, "/v1/build", proposal(chain)).json()
    p = sign_pdr(b, {"evidence_root": "0x" + "11" * 32}, keys)
    r = post(client, "/v1/executions", {"build_id": b["build_id"], "signed_pdr": p})
    assert r.status_code == 404
    assert chain.vault.functions.usedNonce(int(b["nonce"])).call() is False


@pytest.mark.integration
def test_simulator_failure_never_returns_complete(plane, monkeypatch):
    client, chain, _, app = plane
    b = post(client, "/v1/build", proposal(chain)).json()
    monkeypatch.setattr(chain.settings, "anvil_binary", "nonexistent-anvil-executable")
    r = post(
        client,
        "/v1/simulations",
        {"build_id": b["build_id"], "expected_policy_hash": b["policy_hash"]},
    )
    assert r.status_code == 503
    assert "verification_status" not in r.json()


@pytest.mark.integration
def test_mismatched_expected_policy_hash(plane):
    client, chain, _, _ = plane
    b = post(client, "/v1/build", proposal(chain)).json()
    r = post(
        client,
        "/v1/simulations",
        {"build_id": b["build_id"], "expected_policy_hash": "0x" + "11" * 32},
    )
    assert r.status_code == 409


@pytest.mark.integration
def test_fuji_refuses_local_sim_evidence(plane, monkeypatch):
    client, chain, keys, _ = plane
    b, e = build_and_simulate(client, chain)
    monkeypatch.setattr(chain.settings, "mode", "fuji")
    r = post(
        client,
        "/v1/executions",
        {"build_id": b["build_id"], "signed_pdr": sign_pdr(b, e, keys)},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "SIMULATION_INCOMPLETE"


@pytest.mark.integration
def test_pending_then_receipt_reverted_has_zero_token_deltas(plane):
    client, chain, keys, _ = plane
    b, e = build_and_simulate(client, chain)
    rpc(chain.w3, "evm_setAutomine", [False])
    try:
        request = {"build_id": b["build_id"], "signed_pdr": sign_pdr(b, e, keys)}
        response = post(client, "/v1/executions", request)
        assert response.status_code == 200, response.text
        tx = response.json()["tx_hash"]
        pending = client.get("/v1/executions/" + tx).json()
        assert pending["status"] == "PENDING"
        assert pending["actual_token_in_delta_base_units"] is None
        # Force local pool drift AFTER submission and before mining, without changing the signed call.
        slot = next(
            x
            for x in artifact("MockSwapAdapter")["storageLayout"]["storage"]
            if x["label"] == "outputPerUsdc"
        )["slot"]
        rpc(
            chain.w3,
            "anvil_setStorageAt",
            [
                chain.router.address,
                hex(int(slot)),
                "0x" + (49 * 10**15).to_bytes(32, "big").hex(),
            ],
        )
        rpc(chain.w3, "evm_mine", [])
        result = client.get("/v1/executions/" + tx).json()
        assert result["status"] == "REVERTED"
        assert result["actual_token_in_delta_base_units"] == "0"
        assert result["actual_token_out_delta_base_units"] == "0"
        assert int(result["gas_used"]) > 0
        assert chain.vault.functions.usedNonce(int(b["nonce"])).call() is False
    finally:
        rpc(chain.w3, "evm_setAutomine", [True])


@pytest.mark.integration
def test_same_idempotency_key_recovers_lost_rpc_broadcast_without_double_send(
    plane, monkeypatch
):
    client, chain, keys, _ = plane
    b, evidence = build_and_simulate(client, chain)
    request = {"build_id": b["build_id"], "signed_pdr": sign_pdr(b, evidence, keys)}
    original = chain.w3.eth.send_raw_transaction
    attempts = []

    def flaky_send(raw):
        attempts.append(bytes(raw))
        if len(attempts) == 1:
            raise TimeoutError("Simulated RPC dropped before accepting signed bytes")
        return original(raw)

    monkeypatch.setattr(chain.w3.eth, "send_raw_transaction", flaky_send)
    first = post(client, "/v1/executions", request, "lost-broadcast")
    assert first.status_code == 200 and first.json()["status"] == "PENDING"
    retried = post(client, "/v1/executions", request, "lost-broadcast")
    assert retried.status_code == 200, retried.text
    assert retried.json()["tx_hash"] == first.json()["tx_hash"]
    assert retried.json()["status"] == "CONFIRMED"
    assert len(attempts) == 2 and attempts[0] == attempts[1]
    assert (
        chain.vault.functions.dailySpentUsdc(
            chain.context()["timestamp"] // 86400
        ).call()
        == 200000000
    )
