import json

import httpx
import pytest

from treasury_backend.config.planning import PlanningSettings
from treasury_backend.core.errors import ControlError
from treasury_backend.modules.planning.provider import GoalPlanner


def test_deepseek_is_first_with_native_payload_and_exact_amount(tmp_path):
    cfg = PlanningSettings.from_values({
        "PACEVANT_PLANNER_PROVIDER": "rotate",
        "PACEVANT_AI_ROTATION_ORDER": "deepseek,groq,gemini,xingchi",
        "DEEPSEEK_API_KEY": "test-deepseek-credential",
        "GROQ_API_KEY": "gsk_test_credential",
    })
    calls = []

    def handler(request):
        calls.append(request)
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-deepseek-credential"
        body = json.loads(request.content)
        assert body["model"] == "deepseek-flash"
        assert body["thinking"] == {"type": "disabled"}
        assert body["max_tokens"] == 512
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
            "message": {"content": '{"direction":"USDC_TO_WAVAX","amount":"0.000001"}'}}]})

    planner = GoalPlanner(cfg, tmp_path, transport=httpx.MockTransport(handler))
    try:
        assert planner.parse("Buy WAVAX with 0.000001 USDC").amount == 1
        assert planner.provider.last_provider == "deepseek" and len(calls) == 1
    finally:
        planner.close()


def test_deepseek_wrong_amount_does_not_fall_through_to_other_models(tmp_path):
    cfg = PlanningSettings.from_values({"PACEVANT_PLANNER_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "test-key"})
    planner = GoalPlanner(cfg, tmp_path, transport=httpx.MockTransport(lambda _: httpx.Response(
        200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": '{"direction":"USDC_TO_WAVAX","amount":"1"}'}}]})))
    try:
        with pytest.raises(ControlError, match="PLANNER_PLAN_MISMATCH"):
            planner.parse("Buy WAVAX with 0.000001 USDC")
    finally:
        planner.close()
