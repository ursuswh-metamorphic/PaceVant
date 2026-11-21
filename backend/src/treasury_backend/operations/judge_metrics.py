"""Read-only measurements around real provider calls; never a decision input."""

from time import monotonic


class InferenceMeter:
    def __init__(self, provider, stage):
        self.provider = provider
        self.stage = stage
        self.calls = []

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def complete(self, messages):
        start = monotonic()
        entry = {"stage": self.stage(), "status": "FAILED", "usage": {}}
        try:
            result = self.provider.complete(messages)
            entry.update(status="SUCCESS", usage={
                k: v for k, v in result.usage.items()
                if k in {"prompt_tokens", "completion_tokens", "total_tokens",
                    "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"}
                and isinstance(v, int) and not isinstance(v, bool) and v >= 0
            })
            return result
        finally:
            entry["wall_ms"] = round((monotonic() - start) * 1000, 3)
            # Do not persist prompts, responses, endpoints, credentials or exceptions.
            entry["attempts"] = [{k: row[k] for k in ("provider", "model", "status", "latency_ms") if k in row}
                for row in getattr(self.provider, "last_attempts", [])]
            self.calls.append(entry)

    def summary(self):
        usage = {}
        for entry in self.calls:
            for key, value in entry["usage"].items():
                usage[key] = usage.get(key, 0) + value
        return {"calls": self.calls, "call_count": len(self.calls), "reported_token_usage": usage,
            "token_scope": "Successful responses reported by provider; failed-attempt billing is unknown",
            "billing_usd": None}
