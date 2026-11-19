"""Provider-specific wire adapters with shared validation, quotas and cache."""

import json

from treasury_backend.core.errors import ControlError

from .groq import GroqPlanner, PlanDraft


class GeminiPlanner(GroqPlanner):
    version = "gemini-gemma-bounded-v1"

    def request_spec(self, messages):
        # Prompt JSON, not an assumed Gemma structured-output capability.
        prompt = messages[0]["content"] + "\nJSON schema: " + json.dumps(PlanDraft.model_json_schema())
        return (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + self.settings.model + ":generateContent",
            {"x-goog-api-key": self.settings.api_key},
            {"contents": [{"role": "user", "parts": [{"text": prompt + "\nGoal: " + messages[1]["content"]}]}],
             "generationConfig": {"temperature": 0, "maxOutputTokens": self.settings.max_completion_tokens,
                                  "thinkingConfig": {"thinkingLevel": "minimal"}}},
        )

    def extract_content(self, data):
        candidates = data["candidates"]
        if len(candidates) != 1 or candidates[0].get("finishReason") != "STOP":
            raise ControlError("PLANNER_INVALID_RESPONSE", 503)
        parts = candidates[0]["content"]["parts"]
        return "".join(part["text"] for part in parts if not part.get("thought"))


class XingchiPlanner(GroqPlanner):
    version = "xingchi-bounded-v1"

    def request_spec(self, messages):
        return (
            self.settings.xingchi_base_url + "/responses",
            {"Authorization": "Bearer " + self.settings.api_key,
             "User-Agent": "Cursor/0.45.0"},
            {"model": self.settings.model,
             "input": messages[0]["content"] + "\nReturn only JSON matching "
                      + json.dumps(PlanDraft.model_json_schema()) + "\nGoal: " + messages[1]["content"],
             "max_output_tokens": self.settings.max_completion_tokens},
        )

    def extract_content(self, data):
        if data.get("status") != "completed" or data.get("error"):
            raise ControlError("PLANNER_INVALID_RESPONSE", 503)
        texts = []
        for item in data["output"]:
            if item.get("type") != "message":
                continue
            if item.get("role") != "assistant" or item.get("status") != "completed":
                raise ControlError("PLANNER_INVALID_RESPONSE", 503)
            for content in item["content"]:
                if content.get("type") != "output_text":
                    raise ControlError("PLANNER_INVALID_RESPONSE", 503)
                texts.append(content["text"])
        return "".join(texts)
