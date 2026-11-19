"""The recovery helper uses only the unified HTTP API, never legacy B/signer setup."""

import httpx
import pytest
from tools.operations.recover_submission import recover

TOKEN = "operator-recovery-test-credential"
TX = "0x" + "11" * 32


def test_tool_calls_unified_workflow_endpoint_and_summarizes_response():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.path == "/v1/workflows/workflow_1/recover"
        assert request.headers["Authorization"] == "Bearer " + TOKEN
        assert request.read() == b'{"tx_hash":"' + TX.encode() + b'"}'
        return httpx.Response(200, json={"status": "CONFIRMED", "private_audit": "not printed"})

    result = recover(
        "https://treasury.example", TOKEN, "workflow_1", TX, transport=httpx.MockTransport(handler)
    )
    assert result == {"workflow_id": "workflow_1", "status": "CONFIRMED"}
    assert len(requests) == 1


def test_tool_never_follows_credential_redirect():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(307, headers={"Location": "https://attacker.example"})

    with pytest.raises(httpx.HTTPStatusError):
        recover(
            "https://treasury.example",
            TOKEN,
            "workflow_1",
            TX,
            transport=httpx.MockTransport(handler),
        )
    assert len(requests) == 1


@pytest.mark.parametrize(
    "origin",
    ["http://public.example", "https://user:password@example.com", "https://example.com/path"],
)
def test_tool_rejects_unsafe_api_origin(origin):
    with pytest.raises(ValueError):
        recover(origin, TOKEN, "workflow_1", TX)
