import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from jsonschema import validate
from pydantic import ValidationError
from app.crypto import canonical, content_hash, digest, keccak, recover
from app.models import Approval, Domain, TransactionProposal
from app.settings import ROOT
from app.store import Store
from conftest import proposal, post


def test_python_golden():
    path = ROOT / "fixtures/eip712_golden"
    v = json.loads((path / "vector.json").read_text())
    a, d = Approval.model_validate(v["approval"]), Domain.model_validate(v["domain"])
    assert digest(d, a) == v["typed_data_hash"]
    assert recover(d, a, v["signature"]) == v["signer"]
    assert keccak(bytes.fromhex(v["router_calldata"][2:])) == a.calldataHash
    data = (path / "manifest.canonical.json").read_bytes()
    assert canonical(json.loads(data)) == data
    assert keccak(data) == a.evidenceRoot


def test_schema_files_match_models():
    from app import models

    for path in (ROOT / "packages/contracts-api").glob("*.schema.json"):
        assert (
            json.loads(path.read_text())
            == getattr(models, path.name.split(".")[0]).model_json_schema()
        )


def test_shared_mock_fixtures_validate_and_fail_closed():
    from app.models import BuiltTransaction, SimulationEvidence, ExecutionResult

    for name in ["normal_swap", "exposure_limit", "injection"]:
        TransactionProposal.model_validate_json(
            (ROOT / f"fixtures/{name}.json").read_bytes()
        )
    for name, model in [
        ("built_transaction", BuiltTransaction),
        ("simulation_evidence", SimulationEvidence),
        ("execution_result", ExecutionResult),
    ]:
        value = json.loads((ROOT / f"fixtures/mock/{name}.json").read_text())
        model.model_validate(value)
        validate(
            value,
            json.loads(
                (
                    ROOT / f"packages/contracts-api/{model.__name__}.schema.json"
                ).read_text()
            ),
        )
    e = json.loads((ROOT / "fixtures/mock/simulation_evidence.json").read_text())
    assert e["source"] == "MOCK_FIXTURE" and e["verification_status"] != "COMPLETE"
    assert (
        content_hash(json.loads((ROOT / "fixtures/mock/manifest.json").read_text()))
        == e["evidence_root"]
    )


def test_uint256_and_strict_wire(plane):
    _, chain, _, _ = plane
    for change in [
        {"amount_in_base_units": 1.5},
        {"amount_in_base_units": "1.5"},
        {"amount_in_base_units": str(2**256)},
        {"chain_id": 31337.0},
        {"amount_in_base_units": "0001"},
        {"slippage_bps": True},
        {"raw_calldata": "0x"},
    ]:
        with pytest.raises(ValidationError):
            TransactionProposal.model_validate(proposal(chain, **change))


def test_nonce_allocation_concurrent(tmp_path):
    store = Store(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda _: store.nonce("vault:chain"), range(50)))
    assert len(set(values)) == 50


def test_artifact_corruption_detected(tmp_path):
    store = Store(tmp_path)
    a = store.artifact({"a": "Việt Nam", "amount": "10000000000000000000000"})
    h = a["content_hash"][2:]
    assert keccak(store.read_artifact(h)) == a["content_hash"]
    (tmp_path / "artifacts" / (h + ".json")).write_bytes(b"corrupt")
    with pytest.raises(Exception, match="corrupted"):
        store.read_artifact(h)


def test_auth_and_error_envelope(plane):
    client, chain, _, _ = plane
    r = client.get(
        "/v1/chain/context",
        headers={"X-API-Key": "wrong", "X-Request-Id": "workflow_001"},
    )
    assert r.status_code == 401
    assert set(r.json()["error"]) == {"code", "message", "retryable", "correlation_id"}
    assert r.json()["error"]["correlation_id"] == "workflow_001"
    assert client.get("/unknown").json()["error"]["code"] == "NOT_FOUND"
    assert (
        post(client, "/v1/build", proposal(chain, amount_in_base_units=0.1)).status_code
        == 400
    )
    assert client.post("/v1/build", json=proposal(chain)).status_code == 400


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"recipient": "0x" + "ab" * 20}, "BAD_RECIPIENT"),
        ({"router": "0x" + "ab" * 20}, "ROUTER_NOT_ALLOWED"),
        ({"token_out": "0x" + "ab" * 20}, "TOKEN_NOT_ALLOWED"),
        ({"chain_id": 43113}, "CHAIN_MISMATCH"),
        ({"amount_in_base_units": "500000001"}, "TRADE_SIZE_LIMIT"),
        ({"slippage_bps": 101}, "BAD_PRICE_OR_SLIPPAGE"),
        ({"deadline": 1}, "EXPIRED_APPROVAL"),
    ],
)
def test_builder_denies_unauthorized_inputs(plane, changes, code):
    client, chain, _, _ = plane
    r = post(client, "/v1/build", proposal(chain, **changes))
    assert r.status_code in {409, 422}, r.text
    assert r.json()["error"]["code"] == code


def test_build_idempotency_and_nonce(plane):
    client, chain, _, _ = plane
    p = proposal(chain)
    a = post(client, "/v1/build", p)
    assert a.status_code == 200, a.text
    assert post(client, "/v1/build", p).json() == a.json()
    b = post(client, "/v1/build", p, key="different")
    assert b.status_code == 200, b.text
    assert a.json()["nonce"] != b.json()["nonce"]
    assert a.json()["calldata_hash"] == b.json()["calldata_hash"]
    assert (
        post(
            client, "/v1/build", {**p, "amount_in_base_units": "201000000"}
        ).status_code
        == 409
    )
    validate(
        a.json(),
        json.loads(
            (ROOT / "packages/contracts-api/BuiltTransaction.schema.json").read_text()
        ),
    )


def test_onchain_snapshot_no_invented_prices(plane):
    client, chain, _, _ = plane
    s = client.get("/v1/portfolio/onchain-snapshot").json()
    assert s["usdc_base_units"] == "7700000000"
    assert "price_wavax_usd_e8" not in s
    assert s["block_number"] == chain.w3.eth.block_number
