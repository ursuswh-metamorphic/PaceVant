"""Bounded provider failover. No same-project key rotation or rules fallback."""

from contextvars import ContextVar
from dataclasses import replace

from filelock import Timeout

from treasury_backend.core.errors import ControlError

from .groq import GroqPlanner
from .remote import DeepSeekPlanner, GeminiPlanner, XingchiPlanner

FAILOVER_ERRORS = {
    "PLANNER_AUTH_FAILED", "PLANNER_UNAVAILABLE", "PLANNER_RATE_LIMITED",
    "PLANNER_LOCAL_QUOTA", "PLANNER_INVALID_RESPONSE",
}


class RotatingPlanner:
    version = "provider-failover-bounded-v1"

    def __init__(self, settings, directory, **kwargs):
        self.settings = settings
        self.clients = []
        self._trace = ContextVar("planner_trace", default=([], None, None))
        selected = settings.rotation_order if settings.provider == "rotate" else (settings.provider,)
        for name in selected:
            key, model, cls = {
                "groq": (settings.api_key, settings.model, GroqPlanner),
                "gemini": (settings.gemini_api_key, settings.gemini_model, GeminiPlanner),
                "xingchi": (settings.xingchi_api_key, settings.xingchi_model, XingchiPlanner),
                "deepseek": (settings.deepseek_api_key, settings.deepseek_model, DeepSeekPlanner),
            }[name]
            if not key or (name == "xingchi" and not settings.xingchi_base_url):
                continue
            child = replace(settings, provider=name, api_key=key, model=model)
            # Keep legacy Groq quotas/cache when switching from groq to rotate.
            path = directory if name == "groq" else directory / name
            self.clients.append((name, cls(child, path, **kwargs)))
        if not self.clients:
            raise RuntimeError("No configured AI provider available")

    def plan(self, goal):
        attempts = []
        for name, client in self.clients:
            try:
                draft = client.plan(goal)
            except Timeout:
                attempts.append({"provider": name, "model": client.settings.model, "error": "PLANNER_BUSY"})
                continue
            except ControlError as exc:
                attempts.append({"provider": name, "model": client.settings.model, "error": exc.code})
                self._trace.set((attempts, None, None))
                # Semantic mismatches/injection/unsupported goals are not availability errors.
                if exc.code not in FAILOVER_ERRORS:
                    raise
                if exc.code == "PLANNER_INVALID_RESPONSE":
                    client._cooldown(30)
                continue
            attempts.append({"provider": name, "model": client.settings.model, "status": "VALIDATED"})
            self._trace.set((attempts, name, client.settings.model))
            return draft
        self._trace.set((attempts, None, None))
        raise ControlError("PLANNER_ALL_PROVIDERS_UNAVAILABLE", 503, retryable=True)

    @property
    def last_attempts(self):
        return self._trace.get()[0]

    @property
    def last_provider(self):
        return self._trace.get()[1]

    @property
    def last_model(self):
        return self._trace.get()[2]

    def close(self):
        for _, client in self.clients:
            client.close()
