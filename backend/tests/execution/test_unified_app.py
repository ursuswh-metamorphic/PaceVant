"""Security/lifecycle regressions for one-app module composition."""

from dataclasses import replace

import pytest
from eth_account import Account
from fastapi.testclient import TestClient

from treasury_backend.api.app import create_app
from treasury_backend.api.local_execution import LocalExecutionSDK
from treasury_backend.config.control import Settings
from treasury_backend.config.execution import Settings as ExecutionSettings
from treasury_backend.core.errors import ControlError
from treasury_backend.modules.execution.service import ExecutionService
from treasury_backend.modules.workflows.client import VerifiedExecutionClient
from treasury_contracts.models import TransactionProposal

from conftest import proposal


def test_unified_routes_and_internal_client_share_one_execution_runtime(plane, tmp_path):
    _, chain, keys, _ = plane
    config = replace(
        Settings(), mode="LOCAL", db=tmp_path / "control.sqlite3",
        attestor_key=keys["attestor"], chain_rpc_url=chain.settings.rpc_url,
        relayer_address=Account.from_key(keys["relayer"]).address,
        operator_token="operator-token-for-unified-test", internal_token="signer-token-for-unified-test",
    )
    execution_config = ExecutionSettings(**{**chain.settings.model_dump(), "api_key": "execution-key-for-unified-tests"})
    runtime = ExecutionService(execution_config, chain)
    app = create_app(config, execution_config, execution_service=runtime)
    with TestClient(app) as client:
        assert client.get("/health").json()["execution_transport"] == "in-process"
        assert client.get("/execution/v1/chain/context").status_code == 401
        assert client.get("/execution/v1/chain/context", headers={"Authorization": "Bearer " + config.operator_token}).status_code == 401
        headers = {"X-API-Key": execution_config.api_key.get_secret_value()}
        assert client.get("/execution/v1/chain/context", headers=headers).status_code == 200
        assert client.get("/v1/treasury", headers=headers).status_code == 401
        paths = client.get("/openapi.json").json()["paths"]
        assert "/v1/workflows/start" in paths and "/execution/v1/simulations" in paths
        assert "/execution/v2/simulations/preflight" in paths
        assert app.state.control.http is None
        internal = app.state.control.client("workflow-test", None)
        assert isinstance(internal, VerifiedExecutionClient)
        assert isinstance(internal.sdk, LocalExecutionSDK)
        assert internal.sdk.service is app.state.execution is runtime
        assert internal.context().chain_id == 31337

        typed = TransactionProposal.model_validate(proposal(chain))
        first = internal.build(typed)
        again = internal.build(typed)
        assert again == first
        assert runtime.store.get("build", first.build_id) == first.model_dump()
        poisoned = typed.model_copy(update={"recipient": "0x" + "02" * 20})
        with pytest.raises(ControlError):
            internal.build(poisoned)


def test_unified_mock_needs_no_execution_service(tmp_path):
    app = create_app(replace(Settings(), db=tmp_path / "mock.sqlite3"))
    with TestClient(app) as client:
        assert client.get("/health").json()["execution_enabled"] is False
        assert app.state.control.http is None
        assert client.get("/").status_code == 200
