from dataclasses import replace

import httpx
import pytest
from dotenv import dotenv_values
from eth_account import Account
from fastapi.testclient import TestClient

import treasury_backend.operations as ops
from treasury_backend.api.app import create_app
from treasury_backend.config.control import Settings
from treasury_backend.config.planning import PlanningSettings
from treasury_backend.paths import ROOT


def test_env_template_matches_initializer_schema(tmp_path):
    template = dotenv_values(ROOT / ".env.example", interpolate=False)
    assert set(template) == set(ops.ENV_DEFAULTS)
    path = tmp_path / "fresh.env"
    ops.init_env(path)
    assert set(dotenv_values(path, interpolate=False)) == set(template)
    assert dotenv_values(path)["PACEVANT_PLANNER_PROVIDER"] == "rules"


def test_groq_key_is_required_only_when_selected():
    assert PlanningSettings.from_values({}).provider == "rules"
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        PlanningSettings.from_values({"PACEVANT_PLANNER_PROVIDER": "groq"})
    with pytest.raises(RuntimeError, match="GROQ_MODEL"):
        PlanningSettings.from_values({"GROQ_MODEL": "unreviewed-auto-fallback"})
    with pytest.raises(RuntimeError, match="GROQ_REQUESTS_PER_MINUTE"):
        PlanningSettings.from_values({"GROQ_REQUESTS_PER_MINUTE": "30"})


def test_profile_only_gives_provider_secret_to_control_or_unified(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_parent_should_not_leak")
    monkeypatch.setenv("GEMINI_API_KEY", "test-parent-google-secret")
    monkeypatch.setenv("XINGCHI_API_KEY", "test-parent-gateway-secret")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-parent-deepseek-secret")
    assert "GROQ_API_KEY" not in ops.safe_environment({})
    assert "GEMINI_API_KEY" not in ops.safe_environment({})
    assert "XINGCHI_API_KEY" not in ops.safe_environment({})
    assert "DEEPSEEK_API_KEY" not in ops.safe_environment({})
    env = tmp_path / "roles.env"
    ops.init_env(env, generate_attestor=True)
    owner, relayer = Account.create(), Account.create()
    ops.update_env(
        env,
        {
            "B_FUJI_OWNER_PRIVATE_KEY": owner.key.hex(),
            "B_FUJI_RELAYER_PRIVATE_KEY": relayer.key.hex(),
            "FUJI_TEST_WALLETS_ONLY": "true",
            "PACEVANT_PLANNER_PROVIDER": "groq",
            "GROQ_API_KEY": "gsk_profile_test_credential",
        },
    )
    monkeypatch.delenv("GROQ_API_KEY")
    p = ops.Profile.load(ROOT, env, "fuji")
    assert ops.a_environment(p)["GROQ_API_KEY"] == "gsk_profile_test_credential"
    assert ops.backend_environment(p)["GROQ_API_KEY"] == "gsk_profile_test_credential"
    assert "GROQ_API_KEY" not in ops.b_environment(p)
    for key in ("GEMINI_API_KEY", "XINGCHI_API_KEY", "DEEPSEEK_API_KEY"):
        assert key not in ops.b_environment(p)
        assert ops.backend_environment(p)[key] == ops.a_environment(p)[key]
    p.values.update(TREASURY_DEMO_USER_PRIVATE_KEY="must-not-reach-runtime",
                    TREASURY_DEMO_USER_ADDRESS=Account.create().address,
                    PACEVANT_DEMO_ENABLED="1", PACEVANT_DEMO_ACCESS_TOKEN="demo-only-test-token")
    unified = ops.backend_environment(p)
    assert "TREASURY_DEMO_USER_PRIVATE_KEY" not in unified
    assert "must-not-reach-runtime" not in unified.values()
    assert unified["PACEVANT_DEMO_ACCESS_TOKEN"] == p.values["PACEVANT_DEMO_ACCESS_TOKEN"]
    assert "PACEVANT_DEMO_ACCESS_TOKEN" not in ops.b_environment(p)
    p.values["TREASURY_RELAYER_ADDRESS"] = owner.address
    with pytest.raises(ops.OpsError, match="TREASURY_RELAYER_ADDRESS"):
        p.credentials()


def test_workflow_uses_groq_plan_but_still_has_all_gates(tmp_path):
    config = replace(
        Settings(),
        db=tmp_path / "control.sqlite3",
        planning=PlanningSettings(
            provider="groq",
            api_key="gsk_mock_transport_only_credential",
        ),
    )
    app = create_app(config, clock=lambda: 2_000_000_000)
    calls = []

    def send(request):
        calls.append(1)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"direction":"USDC_TO_WAVAX","amount":"200"}'},
                    }
                ]
            },
        )

    with TestClient(app) as api:
        service = app.state.control
        service.planner.provider.http.close()
        service.planner.provider.http = httpx.Client(transport=httpx.MockTransport(send))
        result = api.post(
            "/v1/workflows/start",
            json={
                "mandate_id": "mandate_demo",
                "goal": "Buy WAVAX with 200 USDC",
            },
        ).json()
        workflow = api.get("/v1/workflows/" + result["workflow_id"]).json()
        assert workflow["planner_provider"] == "groq"
        assert workflow["planner_model"] == "openai/gpt-oss-20b"
        assert workflow["status"] == "CONFIRMED"
        stages = [event["stage"] for event in workflow["timeline"]]
        assert all(
            stage in stages
            for stage in ["ALIGNED", "SIMULATED", "EVALUATED", "APPROVED", "ATTESTED"]
        )
        assert calls == [1]
        assert "gsk_mock_transport_only_credential" not in str(workflow)


def test_workflow_does_not_fallback_after_provider_failure(tmp_path):
    config = replace(
        Settings(),
        db=tmp_path / "control.sqlite3",
        planning=PlanningSettings(
            provider="groq",
            api_key="gsk_mock_transport_only_credential",
        ),
    )
    app = create_app(config)
    with TestClient(app) as api:
        service = app.state.control
        service.planner.provider.http.close()
        service.planner.provider.http = httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(429, headers={"retry-after": "60"})
            )
        )
        result = api.post(
            "/v1/workflows/start",
            json={
                "mandate_id": "mandate_demo",
                "goal": "Buy WAVAX with 200 USDC",
            },
        ).json()
        workflow = api.get("/v1/workflows/" + result["workflow_id"]).json()
        assert workflow["status"] == "ESCALATED"
        assert workflow["timeline"][-1]["reason_codes"] == ["PLANNER_RATE_LIMITED"]
        assert not any(
            event["stage"] in {"ATTESTED", "SUBMITTED", "CONFIRMED"}
            for event in workflow["timeline"]
        )


def test_rotating_workflow_records_actual_provider_and_keeps_gates(tmp_path):
    planning = PlanningSettings.from_values({"PACEVANT_PLANNER_PROVIDER": "rotate",
        "GEMINI_API_KEY": "test-google-key", "GROQ_API_KEY": "gsk_test_transport_only"})
    config = replace(Settings(), db=tmp_path / "control.sqlite3", planning=planning)
    app = create_app(config, clock=lambda: 2_000_000_000)
    with TestClient(app) as api:
        service = app.state.control
        for name, child in service.planner.provider.clients:
            child.http.close()
            if name == "gemini":
                def handler(_):
                    return httpx.Response(429)
            else:
                def handler(_):
                    return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
                        "message": {"content": '{"direction":"USDC_TO_WAVAX","amount":"200"}'}}]})
            child.http = httpx.Client(transport=httpx.MockTransport(handler))
        result = api.post("/v1/workflows/start", json={"mandate_id": "mandate_demo",
            "goal": "Buy WAVAX with 200 USDC"}).raise_for_status().json()
        workflow = api.get("/v1/workflows/" + result["workflow_id"]).raise_for_status().json()
        planned = next(e for e in workflow["timeline"] if e["stage"] == "PLANNED")
        assert planned["planner_provider"] == "groq"
        assert planned["provider_attempts"][0]["error"] == "PLANNER_RATE_LIMITED"
        assert workflow["status"] == "CONFIRMED"
        assert all(any(e["stage"] == stage for e in workflow["timeline"])
                   for stage in ("ALIGNED", "SIMULATED", "EVALUATED", "APPROVED", "ATTESTED"))
