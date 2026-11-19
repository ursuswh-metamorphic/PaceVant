"""Transport-level failover and independent safety validation, no paid calls."""

import json

import httpx
import pytest

from treasury_backend.config.planning import PlanningSettings
from treasury_backend.core.errors import ControlError
from treasury_backend.modules.planning.provider import GoalPlanner

GOAL = "Buy WAVAX with 200 USDC"
DRAFT = {"direction": "USDC_TO_WAVAX", "amount": "200"}


def settings(**overrides):
    return PlanningSettings.from_values({
        "PACEVANT_PLANNER_PROVIDER": "rotate", "GEMINI_API_KEY": "test-google-key",
        "GROQ_API_KEY": "gsk_test_only_not_real", "XINGCHI_API_KEY": "test-xingchi-key",
        "XINGCHI_BASE_URL": "https://xingchiapi.com/v1", **overrides,
    })


def ok_gemini(draft=DRAFT):
    return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {
        "parts": [{"text": json.dumps(draft)}]}}]})


def test_gemini_success_cache_headers_and_isolation(tmp_path):
    calls = []

    def handler(req):
        calls.append(str(req.url))
        assert req.headers["x-goog-api-key"] == "test-google-key"
        assert "authorization" not in req.headers
        assert "test-xingchi-key" not in str(req.headers)
        assert "test-google-key" not in str(req.url)
        body = json.loads(req.content)
        assert body["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "minimal"
        return ok_gemini()

    planner = GoalPlanner(settings(), tmp_path, transport=httpx.MockTransport(handler), clock=lambda: 1000)
    try:
        assert planner.parse(GOAL).amount == 200_000_000
        assert planner.parse(GOAL).amount == 200_000_000
        assert len(calls) == 1
        assert planner.provider.last_provider == "gemini"
    finally:
        planner.close()


def test_429_503_rotate_to_responses_and_remember_cooldown(tmp_path):
    calls = []

    def handler(req):
        calls.append(req.url.host)
        if req.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(429, headers={"Retry-After": "120"})
        if req.url.host == "api.groq.com":
            return httpx.Response(503)
        assert str(req.url) == "https://xingchiapi.com/v1/responses"
        assert req.headers["Authorization"] == "Bearer test-xingchi-key"
        assert "x-goog-api-key" not in req.headers
        assert json.loads(req.content)["model"] == "gpt-6.1-sol"
        return httpx.Response(200, json={"status": "completed", "output": [
            {"type": "message", "status": "completed", "role": "assistant",
             "content": [{"type": "output_text", "text": json.dumps(DRAFT)}]}]})

    kwargs = {"transport": httpx.MockTransport(handler), "clock": lambda: 1000}
    planner = GoalPlanner(settings(), tmp_path, **kwargs)
    assert planner.parse(GOAL).amount == 200_000_000
    assert planner.provider.last_provider == "xingchi"
    planner.close()
    restarted = GoalPlanner(settings(), tmp_path, **kwargs)
    try:
        assert restarted.parse(GOAL).amount == 200_000_000
        assert calls == ["generativelanguage.googleapis.com", "api.groq.com", "xingchiapi.com"]
    finally:
        restarted.close()


def test_plan_mismatch_does_not_try_other_providers(tmp_path):
    calls = []

    def handler(req):
        calls.append(req.url.host)
        return ok_gemini({"direction": "USDC_TO_WAVAX", "amount": "201"})

    planner = GoalPlanner(settings(), tmp_path, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ControlError, match="PLANNER_PLAN_MISMATCH"):
            planner.parse(GOAL)
        assert calls == ["generativelanguage.googleapis.com"]
    finally:
        planner.close()


def test_all_errors_fail_closed_with_bounded_attempts(tmp_path):
    calls = []

    def handler(req):
        calls.append(req.url.host)
        return httpx.Response(401)

    planner = GoalPlanner(settings(), tmp_path, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ControlError, match="PLANNER_ALL_PROVIDERS_UNAVAILABLE"):
            planner.parse(GOAL)
        assert len(calls) == 3
        assert len(planner.provider.last_attempts) == 3
        assert all(x["error"] == "PLANNER_AUTH_FAILED" for x in planner.provider.last_attempts)
    finally:
        planner.close()


def test_unknown_endpoint_not_called_and_model_allowlist(tmp_path):
    configured = settings(XINGCHI_BASE_URL="")
    planner = GoalPlanner(configured, tmp_path)
    assert [name for name, _ in planner.provider.clients] == ["gemini", "groq"]
    planner.close()
    with pytest.raises(RuntimeError, match="GEMINI_MODEL"):
        settings(GEMINI_MODEL="expensive-unreviewed-model")
    with pytest.raises(RuntimeError, match="XINGCHI_BASE_URL"):
        settings(XINGCHI_BASE_URL="http://xingchiapi.com/v1")
