from types import SimpleNamespace

import httpx
import pytest

from app.orchestration.client import WorkflowSDK
from app.orchestration.evidence import evidence_issues


@pytest.mark.parametrize("source", ["MOCK_FIXTURE", "REAL_LOCAL_SIM"])
def test_a10_fuji_denies_mock_and_local_evidence(source):
    assert evidence_issues(
        object(),
        "FUJI",
        None,
        SimpleNamespace(source=source),
        SimpleNamespace(deployment="FUJI"),
        0,
    ) == ["UNVERIFIED_SIMULATION_SOURCE"]


def test_execute_retry_reuses_exact_idempotency_and_request():
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ReadTimeout("Submission response was lost", request=request)
        return httpx.Response(200, json={"tx_hash": "0x" + "ab" * 32, "status": "PENDING"})

    with httpx.Client(
        base_url="http://127.0.0.1:8001",
        headers={"X-API-Key": "test-key"},
        transport=httpx.MockTransport(handler),
    ) as http:
        client = WorkflowSDK(http, "workflow_test")
        result = client._post("/v1/executions", {"build_id": "build_test"}, "execute-decision_test")
    assert result["status"] == "PENDING"
    assert len(requests) == 2
    assert requests[0].content == requests[1].content
    for request in requests:
        assert request.headers["X-API-Key"] == "test-key"
        assert request.headers["X-Request-ID"] == "workflow_test"
        assert request.headers["Idempotency-Key"] == "execute-decision_test"
