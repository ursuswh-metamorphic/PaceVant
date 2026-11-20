from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from treasury_backend.api.app import create_app
from treasury_backend.config.control import Settings
from treasury_backend.config.demo import DemoSettings


def test_disabled_demo_does_not_expose_or_accept_a_demo_account(tmp_path):
    cfg = replace(Settings(), db=tmp_path / "control.sqlite3")
    with TestClient(create_app(cfg, demo_settings=DemoSettings())) as client:
        assert client.get("/v1/demo/config").json() == {"enabled": False, "accounts": []}
        assert client.get("/v1/demo/account").status_code == 404
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
