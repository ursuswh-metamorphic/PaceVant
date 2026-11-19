"""Small bounded chat-completion provider; no agent, tools, wallet keys or auth forwarding."""

import json
import os
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from urllib.parse import urlsplit

import httpx

from app.errors import ControlError

SECRET_FIELD = re.compile(
    r"private.?key|attestor.?key|signature|authorization|api.?key|password|mnemonic|secret|raw.?tx|signed.?pdr",
    re.I,
)
SECRET_TEXT = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{8,}|Bearer\s+\S+|0x[0-9a-fA-F]{64})\b", re.I)


def safe_text(value):
    # Redact secret-labelled lines even when a key is not a known vendor format.
    value = re.sub(
        r"(?im)(private[_ ]?key|api[_ ]?key|password|mnemonic|secret|authorization)\s*[:=]\s*[^\n,}]+",
        r"\1=[REDACTED]",
        value,
    )
    return SECRET_TEXT.sub("[REDACTED_256BIT_OR_CREDENTIAL]", value)


def safe_value(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {
            str(k): "[REDACTED]" if SECRET_FIELD.search(str(k)) else safe_value(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [safe_value(v) for v in value]
    if isinstance(value, bytes):
        return {
            "binary_bytes": len(value),
            "content": safe_text(value.decode("utf-8", errors="replace")),
        }
    if isinstance(value, str):
        return safe_text(value)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return "[UNSUPPORTED_VALUE]"


@dataclass(frozen=True, repr=False)
class ShieldConfig:
    mode: str = "legacy_fixture"
    provider: str = "openai"
    model: str = "gpt-4o-2024-05-13"
    base_url: str = "https://api.openai.com/v1"
    api_key: str | None = field(default=None, repr=False)
    temperature: float | None = 0.0
    timeout: float = 20
    retries: int = 1
    context_chars: int = 24000
    epsilon: Decimal = Decimal("0")
    max_replans: int = 2
    max_instructions: int = 16
    max_tasks: int = 32
    max_calls: int = 160

    def __post_init__(self):
        if (
            self.mode not in {"disabled", "legacy_fixture", "paper", "wallet_hardened"}
            or self.provider not in {"openai", "openai_compatible"}
            or not self.epsilon.is_finite()
            or not 0 <= self.epsilon <= 32
            or not 0 <= self.retries <= 2
            or not 0 <= self.max_replans <= 2
            or not 1000 <= self.context_chars <= 100000
            or not 1 <= self.timeout <= 60
            or not 1 <= self.max_instructions <= 32
            or not 1 <= self.max_tasks <= 32
            or not 1 <= self.max_calls <= 500
            or not self.model
            or len(self.model) > 100
            or (self.temperature is not None and not 0 <= self.temperature <= 2)
        ):
            raise ValueError("Invalid Task Shield configuration")
        parsed = urlsplit(self.base_url)
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not (
                parsed.scheme == "https"
                or (
                    parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                )
            )
            or (self.provider == "openai" and self.base_url != "https://api.openai.com/v1")
        ):
            raise ValueError("Invalid Task Shield provider endpoint")

    @classmethod
    def from_env(cls, mode):
        selected = os.environ.get(
            "PACEVANT_SHIELD_MODE", "legacy_fixture" if mode == "MOCK" else "paper"
        )
        temp = os.environ.get("PACEVANT_SHIELD_TEMPERATURE", "0")
        return cls(
            mode=selected,
            provider=os.environ.get("PACEVANT_SHIELD_PROVIDER", "openai"),
            model=os.environ.get("PACEVANT_SHIELD_MODEL", "gpt-4o-2024-05-13"),
            base_url=os.environ.get("PACEVANT_SHIELD_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.environ.get("PACEVANT_SHIELD_API_KEY"),
            temperature=None if temp == "omit" else float(temp),
            timeout=float(os.environ.get("PACEVANT_SHIELD_TIMEOUT", "20")),
            retries=int(os.environ.get("PACEVANT_SHIELD_RETRIES", "1")),
            context_chars=int(os.environ.get("PACEVANT_SHIELD_CONTEXT_CHARS", "24000")),
            epsilon=Decimal(os.environ.get("PACEVANT_SHIELD_EPSILON", "0")),
            max_replans=int(os.environ.get("PACEVANT_SHIELD_MAX_REPLANS", "2")),
        )

    def public(self):
        return {
            "mode": self.mode,
            "provider": self.provider,
            "model": self.model,
            "temperature": self.temperature,
            "timeout": self.timeout,
            "retries": self.retries,
            "context_chars": self.context_chars,
            "epsilon": str(self.epsilon),
            "max_replans": self.max_replans,
            "max_instructions": self.max_instructions,
            "max_tasks": self.max_tasks,
            "max_calls": self.max_calls,
        }


@dataclass
class Completion:
    content: str
    latency_ms: int = 0
    usage: dict[str, int] = field(default_factory=dict)


class ChatProvider:
    evaluation_scope = "CONFIGURED_LLM_NOT_BENCHMARK_REPRODUCTION"

    def __init__(self, config, client=None):
        self.config = config
        self.http = client or httpx.Client(trust_env=False, follow_redirects=False)
        self.owned = client is None

    def close(self):
        if self.owned:
            self.http.close()

    def complete(self, messages):
        if not self.config.api_key:
            raise ControlError("TASK_SHIELD_PROVIDER_NOT_CONFIGURED", 503)
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_completion_tokens": 4096,
            "stream": False,
        }
        if self.config.temperature is not None:
            payload["temperature"] = self.config.temperature
        started = time.monotonic()
        try:
            with self.http.stream(
                "POST",
                self.config.base_url + "/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer " + self.config.api_key},
                timeout=self.config.timeout,
                follow_redirects=False,
            ) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes():
                    if (
                        len(data) + len(chunk) > 262144
                        or time.monotonic() - started > self.config.timeout
                    ):
                        raise ControlError("TASK_SHIELD_PROVIDER_LIMIT", 503)
                    data.extend(chunk)
                raw = json.loads(data)
            choice = raw["choices"][0]
            if choice.get("finish_reason") != "stop" or choice["message"].get("tool_calls"):
                raise ValueError("Incomplete or tool response")
            content = choice["message"]["content"]
            if not isinstance(content, str) or len(content) > 32000:
                raise ValueError("Invalid content")
            usage = {
                k: v
                for k, v in raw.get("usage", {}).items()
                if k in {"prompt_tokens", "completion_tokens", "total_tokens"}
                and type(v) is int
                and v >= 0
            }
            return Completion(content, int((time.monotonic() - started) * 1000), usage)
        except ControlError:
            raise
        except Exception:
            raise ControlError("TASK_SHIELD_PROVIDER_UNAVAILABLE", 503, retryable=True) from None
