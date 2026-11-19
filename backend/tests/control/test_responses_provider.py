import json
from dataclasses import replace

import httpx
import pytest

from treasury_backend.core.errors import ControlError
from treasury_backend.modules.alignment.provider import ChatProvider, ShieldConfig


def config(**overrides):
    return ShieldConfig(
        provider="openai_compatible",
        base_url="https://provider.invalid/v1",
        api_style="responses",
        api_key="provider-test-credential",
        model="gpt-6.1-sol",
        user_agent="Cursor/0.45.0",
        temperature=None,
        **overrides,
    )


def completed():
    return {
        "status": "completed",
        "output": [
            {"type": "reasoning", "summary": []},
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {"type": "output_text", "text": '["Read '},
                    {"type": "output_text", "text": 'balance"]'},
                ],
            },
        ],
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    }


def test_responses_payload_extracts_text_and_normalizes_usage():
    def handler(request):
        payload = json.loads(request.content)
        assert str(request.url) == "https://provider.invalid/v1/responses"
        assert request.headers["User-Agent"] == "Cursor/0.45.0"
        assert request.headers["Authorization"] == "Bearer provider-test-credential"
        assert payload["input"] == [
            {"role": "system", "content": "Extract"},
            {"role": "user", "content": "Read balance"},
        ]
        assert payload["model"] == "gpt-6.1-sol" and payload["store"] is False
        assert "messages" not in payload and "temperature" not in payload
        assert payload["max_output_tokens"] == 4096 and not payload["stream"]
        return httpx.Response(200, json=completed())

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = ChatProvider(config(), http).complete(
            [{"role": "system", "content": "Extract"}, {"role": "user", "content": "Read balance"}]
        )
    assert result.content == '["Read balance"]'
    assert result.usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


@pytest.mark.parametrize(
    "failure",
    [
        "incomplete",
        "error",
        "missing_status",
        "empty",
        "tool",
        "refusal",
        "unfinished_message",
        "not_assistant",
        "not_text",
        "bad_usage",
    ],
)
def test_responses_rejects_incomplete_refusal_and_tool_outputs(failure):
    data = completed()
    if failure == "incomplete":
        data["status"] = "incomplete"
    elif failure == "error":
        data["error"] = {"message": "do not expose internals"}
    elif failure == "missing_status":
        data.pop("status")
    elif failure == "empty":
        data["output"] = []
    elif failure == "tool":
        data["output"].append({"type": "function_call", "name": "send_assets"})
    elif failure == "refusal":
        data["output"][1]["content"] = [{"type": "refusal", "refusal": "refused"}]
    elif failure == "unfinished_message":
        data["output"][1]["status"] = "incomplete"
    elif failure == "not_assistant":
        data["output"][1]["role"] = "user"
    elif failure == "not_text":
        data["output"][1]["content"][0]["text"] = 42
    elif failure == "bad_usage":
        data["usage"] = None
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))
    ) as http:
        with pytest.raises(ControlError, match="TASK_SHIELD_PROVIDER_UNAVAILABLE"):
            ChatProvider(config(), http).complete([])


def test_responses_can_include_configured_temperature_and_never_follows_redirects():
    calls = []

    def handler(request):
        calls.append(request)
        assert json.loads(request.content)["temperature"] == 0
        return httpx.Response(302, headers={"Location": "https://unrelated.invalid"})

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as http:
        with pytest.raises(ControlError):
            ChatProvider(replace(config(), temperature=0.0), http).complete([])
    assert len(calls) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"api_style": "unknown"},
        {"user_agent": "x\r\nAuthorization:bad"},
        {"base_url": "https://provider.invalid/v1/responses"},
    ],
)
def test_invalid_protocol_header_and_double_path_configuration_rejected(change):
    with pytest.raises(ValueError):
        replace(config(), **change)


def test_responses_config_from_environment_and_public_view_never_contains_key(monkeypatch):
    for key, value in {
        "PROVIDER": "openai_compatible",
        "MODEL": "gpt-6.1-sol",
        "BASE_URL": "https://provider.invalid/v1",
        "API_STYLE": "responses",
        "USER_AGENT": "Cursor/0.45.0",
        "API_KEY": "provider-test-credential",
        "TEMPERATURE": "omit",
    }.items():
        monkeypatch.setenv("PACEVANT_SHIELD_" + key, value)
    value = ShieldConfig.from_env("FUJI")
    assert value.api_style == "responses" and value.temperature is None
    assert "provider-test-credential" not in json.dumps(value.public())
