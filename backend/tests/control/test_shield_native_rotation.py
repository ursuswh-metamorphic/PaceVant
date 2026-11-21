import json
from dataclasses import replace

import httpx
import pytest

from treasury_backend.core.errors import ControlError
from treasury_backend.modules.alignment.provider import ChatProvider, Completion, ShieldConfig


def native_config(**kwargs):
    return ShieldConfig(provider="gemini", api_style="gemini", model="gemma-4-26b-a4b-it",
                        base_url="https://generativelanguage.googleapis.com/v1beta",
                        api_key="test-native-key", **kwargs)


@pytest.mark.parametrize("finish", ["STOP", "MAX_TOKENS"])
def test_native_gemini_credentials_and_complete_output(finish):
    def transport(request):
        assert request.headers["x-goog-api-key"] == "test-native-key"
        assert "authorization" not in request.headers
        body = json.loads(request.content)
        assert body["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "minimal"
        return httpx.Response(200, json={"candidates": [{"finishReason": finish,
            "content": {"parts": [{"text": "private thought", "thought": True}, {"text": "[]"}]}}],
            "usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 1, "totalTokenCount": 3}})
    with httpx.Client(transport=httpx.MockTransport(transport)) as http:
        provider = ChatProvider(native_config(), http)
        if finish == "STOP":
            result = provider.complete([{"role": "user", "content": "Return []"}])
            assert result.content == "[]" and result.usage["total_tokens"] == 3
        else:
            with pytest.raises(ControlError):
                provider.complete([{"role": "user", "content": "Return []"}])


def test_rotation_cooldown_and_actual_provider_trace(monkeypatch):
    calls = []
    def unavailable(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED"}})
    fallback = ShieldConfig(provider="openai_compatible", model="test-groq", api_key="other-key",
                            base_url="https://api.groq.com/openai/v1")
    with httpx.Client(transport=httpx.MockTransport(unavailable)) as http:
        provider = ChatProvider(native_config(fallbacks=(fallback,)), http)
        monkeypatch.setattr(provider.fallbacks[0], "_complete", lambda _: Completion("[]"))
        try:
            assert provider.complete([]).content == "[]"
            assert [a["status"] for a in provider.last_attempts] == ["FAILED", "SUCCESS"]
            assert provider.last_attempts[-1]["model"] == "test-groq"
            assert provider.complete([]).content == "[]"
            assert len(calls) == 1
        finally:
            provider.close()


def test_native_key_cannot_be_forwarded_to_other_host():
    with pytest.raises(ValueError):
        replace(native_config(), base_url="https://unrelated.invalid/v1beta")


def test_official_deepseek_wire_and_endpoint_isolation():
    from treasury_backend.modules.alignment.provider import json_object_response
    config = ShieldConfig(provider="deepseek", model="deepseek-flash",
                          base_url="https://api.deepseek.com", api_key="test-deepseek")

    def handler(request):
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-deepseek"
        body = json.loads(request.content)
        assert body["thinking"] == {"type": "disabled"}
        assert body["max_tokens"] == 4096 and "max_completion_tokens" not in body
        assert body.get('response_format') == ({'type':'json_object'} if request_json else None)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "[]"}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        provider = ChatProvider(config, http)
        request_json=False
        assert provider.complete([{"role": "user", "content": "Return []"}]).content == "[]"
        request_json=True
        with json_object_response():
            provider.complete([{'role':'user','content':'Return a JSON object'}])
        request_json=False
        provider.complete([{'role':'user','content':'Return []'}])
    with pytest.raises(ValueError):
        replace(config, base_url="https://unrelated.invalid")
