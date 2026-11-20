from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from treasury_backend.api.app import create_app
from treasury_backend.api.demo import install_demo_routes
from treasury_backend.api.demo_auth import issue_demo_session, valid_demo_session
from treasury_backend.config.control import Settings
from treasury_backend.config.demo import DemoSettings
from treasury_backend.modules.gas_credit import GasCreditLedger


def test_disabled_demo_does_not_expose_or_accept_a_demo_account(tmp_path):
    cfg = replace(Settings(), db=tmp_path / "control.sqlite3")
    with TestClient(create_app(cfg, demo_settings=DemoSettings())) as client:
        assert client.get("/v1/demo/config").json() == {"enabled": False, "accounts": []}
        assert client.get("/v1/demo/account").status_code == 404
        assert client.post("/v1/demo/select", json={"account_id": "demo"}).status_code == 404
        assert (
            client.post(
                "/v1/demo/workflows",
                json={"goal": "Buy WAVAX with 1 USDC"},
                headers={"Idempotency-Key": "test-request"},
            ).status_code
            == 404
        )


def test_demo_requires_live_full_pipeline_and_separate_credential(tmp_path):
    cfg = replace(Settings(), db=tmp_path / "control.sqlite3")
    demo = DemoSettings(True, "0x" + "11" * 20, "d" * 32)
    with pytest.raises(RuntimeError, match="Demo requires live execution"):
        create_app(cfg, demo_settings=demo)
    assert "d" * 32 not in repr(demo)


def test_demo_request_header_is_allowed_for_explicit_frontend_origin(tmp_path):
    cfg = replace(
        Settings(), db=tmp_path / "control.sqlite3", cors_origins=("https://demo.example",)
    )
    with TestClient(create_app(cfg, demo_settings=DemoSettings())) as client:
        response = client.options(
            "/v1/demo/workflows",
            headers={
                "Origin": "https://demo.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type,idempotency-key",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "https://demo.example"


@pytest.mark.parametrize(
    "values",
    [
        {"PACEVANT_DEMO_ENABLED": "yes"},
        {"PACEVANT_DEMO_ENABLED": "1"},
        {"PACEVANT_DEMO_ENABLED": "1", "TREASURY_DEMO_USER_ADDRESS": "invalid"},
    ],
)
def test_invalid_demo_config_never_silently_disables_gate(values):
    with pytest.raises(ValueError):
        DemoSettings.from_values(values)


def test_click_selection_grants_only_demo_scope_without_a_code_or_chain_writes(tmp_path):
    # Install the adapter on a fixture app; account reads have no chain client.
    from fastapi import FastAPI

    from treasury_backend.api.control import error_response
    from treasury_backend.core.errors import ControlError

    cfg = DemoSettings(True, "0x" + "11" * 20, "server-only-signing-secret-123456789")
    app = FastAPI()
    app.state.gas_credit = GasCreditLedger(
        tmp_path / "execution.sqlite3",
        cfg,
        chain_id=43113,
        vault="0x" + "22" * 20,
        relayer="0x" + "33" * 20,
    )
    install_demo_routes(app, cfg)

    @app.exception_handler(ControlError)
    async def errors(request, exc):
        return error_response(request, exc.code, exc.status)

    with TestClient(app) as client:
        assert client.get("/v1/demo/account").status_code == 401
        assert client.post("/v1/demo/select", json={"account_id": "owner"}).status_code == 422
        response = client.post("/v1/demo/select", json={"account_id": "demo"})
        assert response.status_code == 200
        session = response.json()
        assert session["scope"] == "demo"
        assert cfg.access_token not in response.text
        headers = {"Authorization": "Bearer " + session["access_token"]}
        account = client.get("/v1/demo/account", headers=headers).raise_for_status().json()
        assert (
            account["spent_wei"] == "0" and not account["requests"] and not account["transactions"]
        )
        # The former manually entered env token is now exclusively server-side.
        assert (
            client.get(
                "/v1/demo/account", headers={"Authorization": "Bearer " + cfg.access_token}
            ).status_code
            == 401
        )


def test_demo_session_tampering_expiry_and_other_secret_are_rejected():
    secret = "session-secret-test-only-1234567890"
    token, expires = issue_demo_session(secret, now=100)
    assert expires == 86500 and valid_demo_session(token, secret, now=101)
    assert not valid_demo_session(token, secret, now=expires)
    assert not valid_demo_session(token, "another-secret", now=101)
    body, signature = token.split(".")
    assert not valid_demo_session("X" + body + "." + signature, secret, now=101)
    for invalid in ("", "no-session", "x.y.z", "x" * 1025):
        assert not valid_demo_session(invalid, secret, now=101)


def test_automatic_demo_session_cannot_authenticate_operator_routes(tmp_path):
    token, _ = issue_demo_session("s" * 32)
    cfg = replace(
        Settings(),
        db=tmp_path / "control.sqlite3",
        operator_token="o" * 32,
        internal_token="i" * 32,
    )
    with TestClient(create_app(cfg, demo_settings=DemoSettings())) as client:
        headers = {"Authorization": "Bearer " + token}
        assert client.get("/v1/treasury", headers=headers).status_code == 401
        assert (
            client.post(
                "/v1/approvals/attest", headers=headers, json={"decision_id": "test"}
            ).status_code
            == 401
        )
