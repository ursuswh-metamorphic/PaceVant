"""Groq settings are independent of chain authority and private wallet keys."""

from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class PlanningSettings:
    provider: str = "rules"
    api_key: str = field(default="", repr=False)
    model: str = "openai/gpt-oss-20b"
    timeout_seconds: int = 20
    max_completion_tokens: int = 512
    requests_per_minute: int = 4
    requests_per_day: int = 200
    tokens_per_minute: int = 4000
    tokens_per_day: int = 80000
    cache_ttl_seconds: int = 300
    gemini_api_key: str = field(default="", repr=False)
    gemini_model: str = "gemma-4-26b-a4b-it"
    xingchi_api_key: str = field(default="", repr=False)
    xingchi_base_url: str = ""
    xingchi_model: str = "gpt-6.1-sol"
    rotation_order: tuple[str, ...] = ("gemini", "groq", "xingchi")

    @classmethod
    def from_values(cls, values):
        def integer(name, default, low, high):
            try:
                value = int(values.get(name, default))
            except (TypeError, ValueError):
                raise RuntimeError("Invalid planner setting: " + name) from None
            if not low <= value <= high:
                raise RuntimeError("Out-of-range planner setting: " + name)
            return value

        provider = values.get("PACEVANT_PLANNER_PROVIDER", "rules")
        if provider not in {"rules", "groq", "gemini", "xingchi", "rotate"}:
            raise RuntimeError("Unsupported PACEVANT_PLANNER_PROVIDER")
        gemini_key = values.get("GEMINI_API_KEY", "")
        gemini_model = values.get("GEMINI_MODEL", "gemma-4-26b-a4b-it")
        if gemini_model != "gemma-4-26b-a4b-it":
            raise RuntimeError("GEMINI_MODEL must be the reviewed Gemma free-tier model")
        xingchi_key = values.get("XINGCHI_API_KEY", "")
        xingchi_url = values.get("XINGCHI_BASE_URL", "").rstrip("/")
        parsed = urlsplit(xingchi_url)
        if xingchi_url and (parsed.scheme != "https" or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path != "/v1"):
            raise RuntimeError("XINGCHI_BASE_URL must be a confirmed HTTPS /v1 endpoint")
        xingchi_model = values.get("XINGCHI_MODEL", "gpt-6.1-sol")
        if xingchi_model != "gpt-6.1-sol":
            raise RuntimeError("XINGCHI_MODEL must be gpt-6.1-sol")
        order = tuple(x.strip() for x in values.get("PACEVANT_AI_ROTATION_ORDER", "gemini,groq,xingchi").split(","))
        if not order or len(set(order)) != len(order) or set(order) - {"gemini", "groq", "xingchi"}:
            raise RuntimeError("Invalid PACEVANT_AI_ROTATION_ORDER")
        if provider == "gemini" and not gemini_key:
            raise RuntimeError("Configure GEMINI_API_KEY")
        if provider == "xingchi" and not (xingchi_key and xingchi_url):
            raise RuntimeError("Configure XINGCHI_API_KEY and confirmed XINGCHI_BASE_URL")
        key = values.get("GROQ_API_KEY", "")
        model = values.get("GROQ_MODEL", "openai/gpt-oss-20b")
        # Explicitly reviewed strict-schema models; no automatic model/tier fallback.
        if model not in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}:
            raise RuntimeError("GROQ_MODEL must be a reviewed GPT-OSS strict-schema model")
        if provider == "groq" and (not key or not key.startswith("gsk_")):
            raise RuntimeError("Configure GROQ_API_KEY for the Groq planner")
        configured = {"gemini": bool(gemini_key), "groq": bool(key), "xingchi": bool(xingchi_key and xingchi_url)}
        if provider == "rotate" and not any(configured[name] for name in order):
            raise RuntimeError("Configure at least one provider in the rotation order")
        return cls(
            provider=provider,
            api_key=key,
            model=model,
            gemini_api_key=gemini_key,
            gemini_model=gemini_model,
            xingchi_api_key=xingchi_key,
            xingchi_base_url=xingchi_url,
            xingchi_model=xingchi_model,
            rotation_order=order,
            timeout_seconds=integer("GROQ_TIMEOUT_SECONDS", 20, 1, 30),
            max_completion_tokens=integer("GROQ_MAX_COMPLETION_TOKENS", 512, 128, 2048),
            requests_per_minute=integer("GROQ_REQUESTS_PER_MINUTE", 4, 1, 20),
            requests_per_day=integer("GROQ_REQUESTS_PER_DAY", 200, 1, 900),
            tokens_per_minute=integer("GROQ_TOKENS_PER_MINUTE", 4000, 512, 7000),
            tokens_per_day=integer("GROQ_TOKENS_PER_DAY", 80000, 1024, 180000),
            cache_ttl_seconds=integer("GROQ_CACHE_TTL_SECONDS", 300, 0, 3600),
        )
