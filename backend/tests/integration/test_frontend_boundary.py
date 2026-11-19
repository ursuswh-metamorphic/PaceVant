from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from treasury_backend.api.control import create_app
from treasury_backend.config.control import Settings


def test_separate_frontend_cors_does_not_bypass_operator_auth(tmp_path):
    settings = replace(
        Settings(),
        db=tmp_path / "state.sqlite3",
        operator_token="operator-test-token",
        cors_origins=("https://dashboard.example",),
        serve_frontend=False,
    )
    with TestClient(create_app(settings)) as client:
        response = client.options(
            "/v1/workflows/start",
            headers={
                "Origin": "https://dashboard.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "https://dashboard.example"
        assert (
            client.post(
                "/v1/workflows/start",
                json={"goal": "Buy WAVAX with 200 USDC", "mandate_id": "mandate_demo"},
                headers={"Origin": "https://dashboard.example"},
            ).status_code
            == 401
        )
        denied = client.options(
            "/v1/workflows/start",
            headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "POST"},
        )
        assert denied.status_code == 400
        assert "access-control-allow-origin" not in denied.headers
        assert client.get("/").json()["service"] == "treasury-control"
        assert client.get("/src/app.js").status_code == 404


def test_bundled_frontend_serves_module_graph(tmp_path):
    with TestClient(create_app(replace(Settings(), db=tmp_path / "state.sqlite3"))) as client:
        assert 'type="module"' in client.get("/").text
        for path in (
            "/assets/config.js",
            "/assets/style.css",
            "/src/app.js",
            "/src/api/client.js",
            "/src/features/treasury/index.js",
            "/src/features/workflows/index.js",
        ):
            assert client.get(path).status_code == 200, path


@pytest.mark.parametrize(
    "origin", ["*", "https://example.com/path", "https://user:password@example.com"]
)
def test_cors_requires_explicit_origins(monkeypatch, origin):
    monkeypatch.setenv("PACEVANT_CORS_ORIGINS", origin)
    with pytest.raises(RuntimeError, match="explicit HTTP"):
        Settings.from_env()
