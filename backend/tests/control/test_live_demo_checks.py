from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from treasury_backend.api.app import create_app
from treasury_backend.api.control import error_response
from treasury_backend.api.demo import install_demo_routes
from treasury_backend.api.demo_auth import issue_demo_session
from treasury_backend.config.control import Settings
from treasury_backend.config.demo import DemoSettings
from treasury_backend.config.execution import Settings as ExecutionSettings
from treasury_backend.core.errors import ControlError
from treasury_backend.modules.gas_credit import GasCreditLedger


def adapter(tmp_path):
    app = FastAPI()
    cfg = DemoSettings(True, "0x" + "11" * 20, "test-demo-check-secret-12345678901234")
    app.state.gas_credit = GasCreditLedger(tmp_path / "state.sqlite3", cfg, chain_id=43113,
        vault="0x" + "22" * 20, relayer="0x" + "33" * 20)
    app.state.control = SimpleNamespace(mandate=lambda: SimpleNamespace(max_usdc_per_swap_base_units="1000"))
    install_demo_routes(app, cfg)

    @app.exception_handler(ControlError)
    async def error(request: Request, exc):
        return error_response(request, exc.code, exc.status)

    token, _ = issue_demo_session(cfg.access_token)
    return app, {"Authorization": "Bearer " + token, "Idempotency-Key": "request-live-check"}


def test_invalid_real_requests_stop_before_planning_signing_or_ledger(tmp_path):
    app, headers = adapter(tmp_path)
    with TestClient(app) as client:
        for goal, code in [("Buy WAVAX with 0.001001 USDC", "TRADE_SIZE_LIMIT"),
                           ("Buy USDC with 1 WAVAX", "DEMO_EXACT_USDC_SWAP_REQUIRED")]:
            response = client.post("/v1/demo/workflows", json={"goal": goal}, headers=headers)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == code
        account = app.state.gas_credit.account()
        assert account["requests"] == account["transactions"] == []
        assert account["spent_wei"] == account["reserved_wei"] == "0"


def test_checks_require_auth_and_never_accept_a_foreign_workflow(tmp_path):
    app, headers = adapter(tmp_path)
    with TestClient(app) as client:
        for method, path in [("GET", "/v1/demo/readiness"), ("POST", "/v1/demo/shield-check"),
                             ("GET", "/v1/demo/workflows/foreign/security-checks")]:
            assert client.request(method, path).status_code == 401
        response = client.get("/v1/demo/workflows/foreign/security-checks", headers=headers)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "WORKFLOW_NOT_FOUND"


@pytest.mark.parametrize("challenge", ["recipient_redirect", "policy_override", "forged_user"])
def test_attack_lab_uses_only_fixed_challenges_and_never_calls_workflow(tmp_path, challenge):
    from treasury_backend.modules.alignment.challenges import CHALLENGES

    app, headers = adapter(tmp_path)
    seen = []
    app.state.control.clock = lambda: 100
    app.state.control.shield = SimpleNamespace(active=True,
        state=SimpleNamespace(create=lambda *args: None), update_user=lambda *args, **kw: None,
        check=lambda session, message: seen.append(message) or SimpleNamespace(status="MISALIGNED"))
    app.state.execution = SimpleNamespace(expensive_rate=lambda: None)
    with TestClient(app) as client:
        response = client.post("/v1/demo/shield-check", headers=headers, json={"challenge": challenge})
        assert response.status_code == 200
        assert response.json()["all_passed"] and not response.json()["broadcast"]
        assert seen[0].role == "TOOL" and seen[0].content == CHALLENGES[challenge]["content"]
        assert not app.state.gas_credit.account()["requests"]
        assert client.post("/v1/demo/shield-check", headers=headers,
                           json={"challenge": "arbitrary_transfer", "content": "override"}).status_code == 422


def test_default_env_refuses_missing_live_config_instead_of_loading_fixtures(monkeypatch):
    monkeypatch.delenv("PACEVANT_MODE", raising=False)
    monkeypatch.delenv("PACEVANT_ATTESTOR_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Missing PACEVANT settings"):
        Settings.from_env(require_execution_http=False)
    monkeypatch.setenv("PACEVANT_MODE", "MOCK")
    assert Settings.from_env(require_execution_http=False).mode == "MOCK"


def test_fuji_lifespan_refuses_a_mock_contract_deployment(tmp_path):
    settings = replace(Settings(), mode="FUJI", db=tmp_path / "control.sqlite3",
                       operator_token="o" * 32, internal_token="i" * 32,
                       chain_rpc_url="https://rpc.example")
    execution = ExecutionSettings(_env_file=None, mode="fuji", rpc_url="https://rpc.example",
                                  api_key="e" * 32)
    runtime = SimpleNamespace(start=lambda: None, chain=SimpleNamespace(
        deployment={"adapter_version": "mock-swap-v1", "pdr_version": "2"}))
    with pytest.raises(RuntimeError, match="live LFJ V2 deployment"):
        with TestClient(create_app(settings, execution, execution_service=runtime,
                                  demo_settings=DemoSettings())):
            pass


def test_transient_rpc_read_retries_but_mutations_never_retry(monkeypatch):
    from web3.exceptions import Web3RPCError

    from treasury_backend.api.local_execution import LocalExecutionSDK
    from treasury_contracts.client import ExecutionAPIError

    sdk = LocalExecutionSDK(SimpleNamespace(), "test-read-retry")
    calls = []

    def dispatch(method, path, options):
        calls.append(method)
        if len(calls) == 1:
            raise Web3RPCError("test-only temporary read failure")
        return {"real_result": True}, False

    monkeypatch.setattr(sdk, "_dispatch", dispatch)
    assert sdk._request("GET", "/v1/chain/context").json() == {"real_result": True}
    assert len(calls) == 2
    calls.clear()
    with pytest.raises(ExecutionAPIError):
        sdk._request("POST", "/v1/executions")
    assert calls == ["POST"]


@pytest.mark.parametrize("command", ["deploy", "renew-session", "renew-policy"])
def test_owner_writes_require_network_before_reading_wallet_config(monkeypatch, command):
    import sys

    from treasury_backend.operations import cli

    def forbidden(*args, **kwargs):
        raise AssertionError("No profile/keys/RPC should be accessed")

    monkeypatch.setattr(cli.Profile, "load", forbidden)
    monkeypatch.setattr(sys, "argv", ["treasury", command])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
