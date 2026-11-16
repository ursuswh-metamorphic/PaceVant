import json
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest
from treasury_contracts.client import ExecutionAPIError, ExecutionClient
from treasury_contracts.models import TransactionProposal

from app.settings import ROOT
from conftest import proposal


def test_sdk_structured_errors_and_no_credential_redirect():
    def handler(request):
        assert request.headers["X-API-Key"] == "test-key"
        return httpx.Response(
            409,
            json={
                "error": {
                    "code": "STALE_REQUIRES_REEVALUATION",
                    "message": "Rebuild required",
                    "retryable": False,
                    "correlation_id": "workflow_123",
                }
            },
        )

    with ExecutionClient(
        "http://execution.test", "test-key", transport=httpx.MockTransport(handler)
    ) as sdk:
        with pytest.raises(ExecutionAPIError) as caught:
            sdk.context()
        assert isinstance(caught.value, httpx.HTTPStatusError)
        assert caught.value.code == "STALE_REQUIRES_REEVALUATION"
        assert caught.value.correlation_id == "workflow_123"
        assert not caught.value.retryable
        with pytest.raises(ValueError, match="Untrusted artifact"):
            sdk.artifact("https://untrusted.example/steal-api-key")


def test_numeric_intent_id_is_not_treated_as_money(plane):
    _, chain, _, _ = plane
    p = TransactionProposal.model_validate(proposal(chain, intent_id="9" * 100))
    assert p.intent_id == "9" * 100


def test_openapi_and_exported_abi_match_implementation(plane):
    from app.chain import artifact
    from treasury_contracts.onchain import vault_abi

    _, _, _, app = plane
    expected = json.loads((ROOT / "packages/contracts-api/openapi.json").read_text())
    assert app.openapi() == expected
    assert vault_abi() == artifact("PolicyVault")["abi"]
    for path, method, schema in [
        ("/v1/chain/context", "get", "ChainContext"),
        ("/v1/portfolio/onchain-snapshot", "get", "OnchainSnapshot"),
        ("/v1/executions", "post", "ExecutionSubmission"),
    ]:
        response = expected["paths"][path][method]["responses"]["200"]
        assert response["content"]["application/json"]["schema"]["$ref"].endswith(
            "/" + schema
        )


def test_handoff_manifest_matches_frozen_contract(plane):
    from treasury_contracts.crypto import APPROVAL_FIELDS

    _, _, _, app = plane
    manifest = json.loads((ROOT / "docs/handoff/integration-manifest.json").read_text())
    assert manifest["contract_version"] == "1.1"
    assert (
        manifest["eip712"]["type_string"]
        == "Approval(" + ",".join(t + " " + n for n, t in APPROVAL_FIELDS) + ")"
    )
    for path in manifest["required_paths"]:
        assert (ROOT / path).is_file(), path
    openapi = app.openapi()
    for route in manifest["routes"]:
        operation = openapi["paths"][route["path"]][route["method"].lower()]
        if "response_model" in route:
            response = operation["responses"]["200"]["content"]["application/json"][
                "schema"
            ]
            assert response["$ref"].endswith("/" + route["response_model"])
        if "request_model" in route:
            schema = operation["requestBody"]["content"]["application/json"]["schema"]
            assert schema["$ref"].endswith("/" + route["request_model"])


@pytest.mark.integration
def test_independent_consumer_sdk_over_real_http(plane, tmp_path):
    _, chain, keys, _ = plane
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "B_MODE=local",
                "B_API_KEY=consumer-contract-key",
                f"B_LOCAL_RPC_URL={chain.settings.rpc_url}",
                f"B_LOCAL_DEPLOYMENT_FILE={chain.settings.deployment_file.as_posix()}",
                f"B_LOCAL_DATA_DIR={(tmp_path / 'consumer-db').as_posix()}",
                f"B_LOCAL_RELAYER_PRIVATE_KEY={keys['relayer']}",
            ]
        )
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "app.cli",
            "serve",
            "--env-file",
            str(env_file),
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            if process.poll() is not None:
                pytest.fail(
                    "Execution API process exited before consumer acceptance test"
                )
            try:
                if (
                    httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code
                    == 200
                ):
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.1)
        else:
            pytest.fail("Execution API startup timed out")
        env = {
            **os.environ,
            "CONSUMER_API_URL": f"http://127.0.0.1:{port}",
            "CONSUMER_API_KEY": "consumer-contract-key",
            "CONSUMER_RPC_URL": chain.settings.rpc_url,
            "CONSUMER_TEST_ATTESTOR_KEY": keys["attestor"],
        }
        # -I and a different cwd prove the consumer uses the installed SDK, not sys.path imports of B.
        consumer = subprocess.run(
            [sys.executable, "-I", str(ROOT / "tests/integration/a_consumer_probe.py")],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=25,
        )
        assert consumer.returncode == 0, consumer.stderr
        result = json.loads(consumer.stdout)
        assert result["status"] == "PASS" and not result["backend_app_imported"]
        (ROOT / "evidence/ab-consumer-acceptance.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
    finally:
        process.terminate()
        process.wait(timeout=10)
