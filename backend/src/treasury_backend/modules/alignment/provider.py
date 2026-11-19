"""Bounded Chat Completions / Responses adapter; no agent or wallet execution tools."""

import json
import os
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from urllib.parse import urlsplit

import httpx

from treasury_backend.core.errors import ControlError

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
    api_style: str = "chat_completions"
    user_agent: str = "PaceVant-TaskShield/1.0"
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
            or self.api_style not in {"chat_completions", "responses"}
            or not 1 <= len(self.user_agent) <= 128
            or not all(32 <= ord(c) <= 126 for c in self.user_agent)
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
            or parsed.path.rstrip("/").endswith(("/responses", "/chat/completions"))
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
            "PACEVANT_SHIELD_MODE", "legacy_fixture" if mode == "MOCK" else "disabled"
        )
        temp = os.environ.get("PACEVANT_SHIELD_TEMPERATURE", "0")
        return cls(
            mode=selected,
            provider=os.environ.get("PACEVANT_SHIELD_PROVIDER", "openai"),
            model=os.environ.get("PACEVANT_SHIELD_MODEL", "gpt-4o-2024-05-13"),
            base_url=os.environ.get("PACEVANT_SHIELD_BASE_URL", "https://api.openai.com/v1"),
            api_style=os.environ.get("PACEVANT_SHIELD_API_STYLE", "chat_completions"),
            user_agent=os.environ.get("PACEVANT_SHIELD_USER_AGENT", "PaceVant-TaskShield/1.0"),
            api_key=(os.environ.get("PACEVANT_SHIELD_API_KEY") or
                     (os.environ.get("XINGCHI_API_KEY") if
                      os.environ.get("PACEVANT_SHIELD_PROVIDER") == "openai_compatible" and
                      os.environ.get("PACEVANT_SHIELD_BASE_URL", "").rstrip("/") == "https://xingchiapi.com/v1"
                      else None)),
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
            "api_style": self.api_style,
            "user_agent": self.user_agent,
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
        path = "/chat/completions"
        if self.config.api_style == "responses":
            path = "/responses"
            payload = {
                "model": self.config.model,
                "input": messages,
                "max_output_tokens": 4096,
                "stream": False,
                "store": False,
            }
        if self.config.temperature is not None:
            payload["temperature"] = self.config.temperature
        started = time.monotonic()
        try:
            with self.http.stream(
                "POST",
                self.config.base_url.rstrip("/") + path,
                json=payload,
                headers={
                    "Authorization": "Bearer " + self.config.api_key,
                    "User-Agent": self.config.user_agent,
                },
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
            if self.config.api_style == "responses":
                content = self._response_text(raw)
                raw_usage = raw.get("usage", {})
                raw_usage = {
                    "prompt_tokens": raw_usage.get("input_tokens"),
                    "completion_tokens": raw_usage.get("output_tokens"),
                    "total_tokens": raw_usage.get("total_tokens"),
                }
            else:
                choice = raw["choices"][0]
                if choice.get("finish_reason") != "stop" or choice["message"].get("tool_calls"):
                    raise ValueError("Incomplete or tool response")
                content = choice["message"]["content"]
                raw_usage = raw.get("usage", {})
            if not isinstance(content, str) or len(content) > 32000:
                raise ValueError("Invalid content")
            usage = {
                k: v
                for k, v in raw_usage.items()
                if k in {"prompt_tokens", "completion_tokens", "total_tokens"}
                and type(v) is int
                and v >= 0
            }
            return Completion(content, int((time.monotonic() - started) * 1000), usage)
        except ControlError:
            raise
        except Exception:
            raise ControlError("TASK_SHIELD_PROVIDER_UNAVAILABLE", 503, retryable=True) from None

    @staticmethod
    def _response_text(raw):
        if raw.get("status") != "completed" or raw.get("error") or raw.get("incomplete_details"):
            raise ValueError("Incomplete Responses result")
        output = raw.get("output")
        if not isinstance(output, list):
            raise ValueError("Missing output items")
        parts = []
        for item in output:
            if item.get("type") == "reasoning":
                continue
            if (
                item.get("type") != "message"
                or item.get("role") != "assistant"
                or item.get("status") != "completed"
                or not isinstance(item.get("content"), list)
            ):
                raise ValueError("Unexpected output item or tool call")
            for part in item["content"]:
                if part.get("type") != "output_text" or not isinstance(part.get("text"), str):
                    raise ValueError("Refusal or invalid text part")
                parts.append(part["text"])
        content = "".join(parts)
        if not content.strip():
            raise ValueError("No completed text output")
        return content
