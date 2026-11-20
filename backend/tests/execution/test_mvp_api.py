"""Canonical FastAPI composition, authorization, owner preparation, and browser resources."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_v3_execution import intent
from v3_provider import ProtocolFixture

from treasury_backend.api.app import create_app
from treasury_backend.config.control import Settings
from treasury_backend.modules.alignment.provider import ShieldConfig
from treasury_backend.operations.execution import send


def test_mvp_operator_startup_does_not_require_retired_session(mvp, tmp_path, monkeypatch):
    import importlib

    from treasury_backend.operations import services as start_services

    serving = importlib.import_module("treasury_backend.operations.services")
    calls = []

    def obsolete_prepare(*args):
        pytest.fail("The paused/revoked legacy session must not gate MVP serving")

    monkeypatch.setattr(serving, "prepare", obsolete_prepare)
    monkeypatch.setattr(serving, "refresh_oracle", obsolete_prepare)
    monkeypatch.setattr(serving, "check_port", lambda *_: None)
    monkeypatch.setattr(serving, "backend_environment", lambda *_: {})
    monkeypatch.setattr(serving, "wait_ready", lambda *_: calls.append("ready"))
    monkeypatch.setattr(serving, "stop_process", lambda *_: calls.append("stopped"))
    child = SimpleNamespace()
    monkeypatch.setattr(serving.subprocess, "Popen", lambda *args, **kwargs: child)
    p = SimpleNamespace(
        values={"PACEVANT_MVP_MANIFEST_FILE": str(tmp_path / "mvp-manifest.json")},
        credentials=lambda: (mvp["attestor"].key.hex(), mvp["relayer"].key.hex()),
        control_data=tmp_path / "new-control",
        root=tmp_path,
        a_port=18030,
        network="fuji",
    )
    with start_services(p) as children:
        assert children == [child] and calls == ["ready"]
    assert calls == ["ready", "stopped"]


@pytest.fixture
def api(mvp, tmp_path, monkeypatch):
    v3 = mvp
    monkeypatch.setattr(
        "treasury_backend.modules.alignment.engine.ChatProvider", lambda *_: ProtocolFixture()
    )
    config = replace(
        Settings(),
        mode="LOCAL",
        db=tmp_path / "api-control.sqlite3",
        require_itag=True,
        attestor_key=v3["attestor"].key.hex(),
        chain_rpc_url=v3["settings"].rpc_url,
        relayer_address=v3["manifest"].relayer,
        operator_token="operator-v3-" + "o" * 30,
        internal_token="internal-v3-" + "i" * 30,
        shield=ShieldConfig(mode="wallet_pipeline", context_chars=100000, max_calls=300),
    )
    execution = v3["settings"].model_copy(update={"api_key": SecretStr("execution-v3-" + "e" * 30)})
    with TestClient(create_app(config, execution, treasury_execution=v3["execution"])) as client:
        yield client, {"Authorization": "Bearer " + config.operator_token}


def test_mvp_api_requires_operator_and_preserves_legacy(api, mvp):
    v3 = mvp
    client, auth = api
    assert client.get("/mvp/capabilities").json()["enabled"]
    assert client.get("/health").json()["execution_transport"] == "in-process"
    assert client.get("/mvp/treasury/" + v3["session_id"]).status_code == 401
    body = intent(v3, "TOKEN_PAYMENT", "1000000").model_dump(mode="json")
    body["operation"] = "USDC_PAYMENT"
    for credentials in (
        {},
        {"Authorization": "Bearer demo-session"},
        {"X-API-Key": "execution-v3-" + "e" * 30},
    ):
        assert client.post("/mvp/workflows", json=body, headers=credentials).status_code == 401
    accepted = client.post(
        "/mvp/workflows", json=body, headers=auth | {"Idempotency-Key": "api-payment"}
    )
    assert accepted.status_code == 200
    result = accepted.json()
    assert result["status"] == "CONFIRMED", result
    assert "signed_approval" not in result
    assert v3["attestor"].key.hex() not in accepted.text
    assert v3["owner"].key.hex() not in accepted.text
    assert client.get("/treasury-mvp.html").status_code == 200
    assert client.get("/src/features/mvp/index.js").status_code == 200
    legacy = client.get(
        "/execution/v1/chain/context", headers={"X-API-Key": "execution-v3-" + "e" * 30}
    )
    assert legacy.status_code == 200


def test_owner_pause_is_prepared_unsigned_and_dashboard_reads_when_paused(api, mvp):
    v3 = mvp
    client, auth = api
    prepared = client.post("/mvp/admin/prepare", json={"action": "PAUSE"}, headers=auth).json()
    assert prepared["broadcast"] is False and prepared["requires_owner_wallet"]
    assert prepared["owner_transaction"]["from"].lower() == v3["manifest"].owner
    assert not v3["contracts"][0].functions.paused().call()
    send(v3["execution"].chain.w3, v3["owner"], v3["contracts"][0].functions.pause())
    dashboard = client.get("/mvp/treasury/" + v3["session_id"], headers=auth)
    assert dashboard.status_code == 200 and dashboard.json()["context"]["paused"]
    body = intent(v3).model_dump(mode="json") | {"operation": "SWAP_EXACT_IN"}
    rejected = client.post(
        "/mvp/workflows", json=body, headers=auth | {"Idempotency-Key": "paused"}
    ).json()
    assert rejected["status"] == "REJECTED" and rejected["reason_code"] == "POLICY_REVOKED"


def test_owner_signed_manifest_tampering_fails(mvp):
    v3 = mvp
    from treasury_backend.modules.execution.mvp import MvpExecution

    changed = v3["manifest"].model_copy(update={"local_wavax_price_e8": "1000000000000"})
    with pytest.raises(ValueError, match="OWNER_MANIFEST_SIGNATURE_INVALID"):
        MvpExecution(v3["settings"], changed)


def test_request_recovery_by_key_requires_auth_and_does_not_repeat_payment(api, mvp):
    client, auth = api
    body = intent(mvp, "TOKEN_PAYMENT", "10000").model_dump(mode="json") | {"operation":"USDC_PAYMENT"}
    first = client.post("/mvp/workflows", json=body, headers=auth | {"Idempotency-Key":"lost-response"}).json()
    assert first["status"] == "CONFIRMED"
    spent = mvp["contracts"][0].functions.spendScopes(mvp["session_id"]).call()[3]
    assert client.get("/mvp/requests/lost-response").status_code == 401
    recovered = client.get("/mvp/requests/lost-response", headers=auth).json()
    assert recovered["workflow_id"] == first["workflow_id"] and recovered["status"] == "CONFIRMED"
    assert "signed_approval" not in recovered
    assert mvp["contracts"][0].functions.spendScopes(mvp["session_id"]).call()[3] == spent
    assert client.get("/mvp/requests/not-accepted", headers=auth).status_code == 404


def test_readiness_separate_from_process_liveness_when_paused(api, mvp):
    client, _ = api
    send(mvp["execution"].chain.w3, mvp["owner"], mvp["contracts"][0].functions.pause())
    assert client.get("/healthz").status_code == 200
    ready = client.get("/readyz")
    assert ready.status_code == 503 and not ready.json()["ready"]
    assert any(c["code"] == "VAULT_PAUSED" and not c["ready"] for c in ready.json()["checks"])


def test_busy_vault_does_not_queue_http_workers_or_create_a_payment(api, mvp):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    client, auth = api
    acquired, release = Event(), Event()

    def hold():
        with mvp["execution"].exclusive():
            acquired.set()
            release.wait(10)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(hold)
        assert acquired.wait(5)
        try:
            body = intent(mvp, "TOKEN_PAYMENT", "10000").model_dump(mode="json") | {"operation":"USDC_PAYMENT"}
            response = client.post("/mvp/workflows", json=body, headers=auth | {"Idempotency-Key":"busy"})
            assert response.status_code == 429
            assert response.json()["error"]["code"] == "MVP_EXECUTION_BUSY_RESUME_REQUEST"
            assert client.get("/healthz").status_code == 200
        finally:
            release.set()
        future.result()
    assert client.get("/mvp/requests/busy", headers=auth).status_code == 404


@pytest.mark.parametrize(
    "operation",
    [
        "VAULT_DEPOSIT",
        "VAULT_WITHDRAW",
        "NATIVE_PAYMENT",
        "TOKEN_PAYMENT",
        "LENDING",
        "STAKING",
        "BRIDGE",
        "ARBITRARY_CALL",
    ],
)
def test_unsupported_mvp_operations_rejected_at_api(api, mvp, operation):
    client, auth = api
    body = intent(mvp).model_dump(mode="json") | {"operation": operation}
    response = client.post(
        "/mvp/workflows", json=body, headers=auth | {"Idempotency-Key": "disabled"}
    )
    assert response.status_code == 400
    assert client.get("/v3/capabilities").status_code == 404
    assert client.post("/v1/workflows/start", json={}, headers=auth).status_code == 410
