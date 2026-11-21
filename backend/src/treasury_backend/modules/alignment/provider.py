"""Bounded Chat Completions / Responses adapter; no agent or wallet execution tools."""

import json
import os
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from decimal import Decimal
from urllib.parse import urlsplit

import httpx

from treasury_backend.core.errors import ControlError

_inference_deadline = ContextVar("pacevant_inference_deadline", default=None)
_json_object_response = ContextVar("pacevant_json_object_response", default=False)


@contextmanager
def json_object_response():
    token = _json_object_response.set(True)
    try:
        yield
    finally:
        _json_object_response.reset(token)


@contextmanager
def inference_window(seconds):
    end = time.monotonic() + seconds
    previous = _inference_deadline.get()
    token = _inference_deadline.set(end if previous is None else min(previous, end))
    try:
        yield
    finally:
        _inference_deadline.reset(token)


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
    algorithm: str = "hybrid-v1"
    fallbacks: tuple = field(default=(), repr=False)
    reasoning_effort: str | None = None
    max_output_chars: int = 16000
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
            self.algorithm not in {"hybrid-v1", "legacy-score-v1"}
            or len(self.fallbacks) > 3
            or any(c.fallbacks for c in self.fallbacks)
            or self.reasoning_effort not in {None, "low", "medium", "high"}
            or not 1000 <= self.max_output_chars <= 65536
            or self.mode
            not in {"disabled", "legacy_fixture", "paper", "wallet_hardened", "wallet_pipeline"}
            or self.provider not in {"openai", "openai_compatible", "gemini", "deepseek"}
            or self.api_style not in {"chat_completions", "responses", "gemini"}
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
            or (
                self.provider == "deepseek"
                and (
                    self.base_url != "https://api.deepseek.com"
                    or self.api_style != "chat_completions"
                    or self.model != "deepseek-flash"
                )
            )
            or (
                (self.provider == "gemini" or self.api_style == "gemini")
                and (
                    self.provider != "gemini"
                    or self.api_style != "gemini"
                    or self.base_url != "https://generativelanguage.googleapis.com/v1beta"
                )
            )
        ):
            raise ValueError("Invalid Task Shield provider endpoint")

    @classmethod
    def from_env(cls, mode):
        return cls.from_values(mode, os.environ)

    @classmethod
    def from_values(cls, mode, values):
        selected = values.get(
            "PACEVANT_SHIELD_MODE", "legacy_fixture" if mode == "MOCK" else "disabled"
        )
        temp = values.get("PACEVANT_SHIELD_TEMPERATURE", "0")
        primary = cls(
            reasoning_effort=values.get("PACEVANT_SHIELD_REASONING_EFFORT") or None,
            max_output_chars=int(values.get("PACEVANT_SHIELD_MAX_OUTPUT_CHARS", "16000")),
            mode=selected,
            provider=values.get("PACEVANT_SHIELD_PROVIDER", "openai"),
            model=values.get("PACEVANT_SHIELD_MODEL", "gpt-4o-2024-05-13"),
            base_url=values.get("PACEVANT_SHIELD_BASE_URL", "https://api.openai.com/v1"),
            api_style=values.get("PACEVANT_SHIELD_API_STYLE", "chat_completions"),
            user_agent=values.get("PACEVANT_SHIELD_USER_AGENT", "PaceVant-TaskShield/1.0"),
            api_key=(
                values.get("PACEVANT_SHIELD_API_KEY")
                or (
                    values.get("DEEPSEEK_API_KEY")
                    if values.get("PACEVANT_SHIELD_PROVIDER") == "deepseek"
                    else None
                )
                or (
                    values.get("GEMINI_API_KEY")
                    if values.get("PACEVANT_SHIELD_PROVIDER") == "gemini"
                    else None
                )
                or (
                    values.get("XINGCHI_API_KEY")
                    if values.get("PACEVANT_SHIELD_PROVIDER") == "openai_compatible"
                    and values.get("PACEVANT_SHIELD_BASE_URL", "").rstrip("/")
                    == "https://xingchiapi.com/v1"
                    else None
                )
            ),
            temperature=None if temp == "omit" else float(temp),
            timeout=float(values.get("PACEVANT_SHIELD_TIMEOUT", "20")),
            retries=int(values.get("PACEVANT_SHIELD_RETRIES", "1")),
            context_chars=int(values.get("PACEVANT_SHIELD_CONTEXT_CHARS", "24000")),
            epsilon=Decimal(values.get("PACEVANT_SHIELD_EPSILON", "0")),
            max_replans=int(values.get("PACEVANT_SHIELD_MAX_REPLANS", "2")),
        )
        fallbacks = []
        names = [n for n in values.get("PACEVANT_SHIELD_FALLBACKS", "").split(",") if n]
        for name in names:
            if name == "gemini":
                child = replace(
                    primary,
                    provider="gemini",
                    api_style="gemini",
                    base_url="https://generativelanguage.googleapis.com/v1beta",
                    api_key=values.get("GEMINI_API_KEY"),
                    model=values.get("GEMINI_MODEL", "gemini-3.1-flash-lite"),
                    temperature=0,
                    reasoning_effort=None,
                )
            elif name == "gemini_dense":
                child = replace(
                    primary,
                    provider="gemini",
                    api_style="gemini",
                    base_url="https://generativelanguage.googleapis.com/v1beta",
                    api_key=values.get("GEMINI_API_KEY"),
                    model="gemma-4-31b-it",
                    temperature=0,
                    reasoning_effort=None,
                )
            elif name == "groq":
                child = replace(
                    primary,
                    provider="openai_compatible",
                    api_style="chat_completions",
                    base_url="https://api.groq.com/openai/v1",
                    api_key=values.get("GROQ_API_KEY"),
                    model=values.get("GROQ_MODEL", "openai/gpt-oss-20b"),
                    temperature=None,
                    reasoning_effort=None,
                )
            elif name == "xingchi":
                child = replace(
                    primary,
                    provider="openai_compatible",
                    api_style="responses",
                    base_url="https://xingchiapi.com/v1",
                    api_key=values.get("XINGCHI_API_KEY"),
                    model=values.get("XINGCHI_MODEL", "gpt-6.1-sol"),
                    temperature=None,
                    reasoning_effort="low",
                    user_agent="Cursor/0.45.0",
                )
            else:
                raise ValueError("Unsupported shield fallback provider")
            fallbacks.append(child)
        return replace(primary, fallbacks=tuple(fallbacks))

    def public(self):
        return {
            "algorithm": self.algorithm,
            "fallbacks": [{"endpoint": c.base_url, **c.public()} for c in self.fallbacks],
            "reasoning_effort": self.reasoning_effort,
            "max_output_chars": self.max_output_chars,
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
        self.fallbacks = [ChatProvider(c) for c in config.fallbacks]
        self._attempt_context = ContextVar("shield_provider_attempts", default=None)
        self.last_attempts = []
        self.cooldown_until = 0

    @property
    def last_attempts(self):
        value = self._attempt_context.get()
        return value if value is not None else []

    @last_attempts.setter
    def last_attempts(self, value):
        self._attempt_context.set(value)

    def close(self):
        for provider in self.fallbacks:
            provider.close()
        if self.owned:
            self.http.close()

    def complete(self, messages):
        overall_started = time.monotonic()
        self.last_attempts = []
        for provider in [self, *self.fallbacks]:
            if time.monotonic() < provider.cooldown_until:
                continue
            start = time.monotonic()
            item = {
                "provider": provider.config.provider,
                "model": provider.config.model,
                "endpoint": provider.config.base_url,
            }
            try:
                result = provider._complete(messages)
                self.last_attempts.append(
                    {
                        **item,
                        "status": "SUCCESS",
                        "latency_ms": int((time.monotonic() - start) * 1000),
                    }
                )
                result.latency_ms = int((time.monotonic() - overall_started) * 1000)
                return result
            except ControlError as error:
                self.last_attempts.append(
                    {
                        **item,
                        "status": "FAILED",
                        "code": error.code,
                        "latency_ms": int((time.monotonic() - start) * 1000),
                    }
                )
                if error.code.endswith("429"):
                    provider.cooldown_until = time.monotonic() + 60
                elif error.code.endswith(("500", "502", "503", "504")):
                    provider.cooldown_until = time.monotonic() + 2
                if not self.fallbacks:
                    raise
        raise ControlError("TASK_SHIELD_ALL_PROVIDERS_UNAVAILABLE", 503)

    def _complete(self, messages):
        if not self.config.api_key:
            raise ControlError("TASK_SHIELD_PROVIDER_NOT_CONFIGURED", 503)
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_completion_tokens": 4096,
            "stream": False,
        }
        path = "/chat/completions"
        if self.config.provider == "deepseek":
            payload["max_tokens"] = payload.pop("max_completion_tokens")
            payload["thinking"] = {"type": "disabled"}
            if _json_object_response.get():
                payload['response_format'] = {'type':'json_object'}
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
        if self.config.reasoning_effort and self.config.api_style == "responses":
            payload["reasoning"] = {"effort": self.config.reasoning_effort}
        headers = {
            "Authorization": "Bearer " + self.config.api_key,
            "User-Agent": self.config.user_agent,
        }
        if self.config.api_style == "gemini":
            path = "/models/" + self.config.model + ":generateContent"
            headers = {"x-goog-api-key": self.config.api_key}
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": "\n\n".join(
                                    m["role"].upper() + ": " + m["content"] for m in messages
                                )
                            }
                        ],
                    }
                ],
                "generationConfig": {
                    "temperature": 0,
                    "maxOutputTokens": 4096,
                    "thinkingConfig": {"thinkingLevel": "minimal"},
                },
            }
        started = time.monotonic()
        timeout = self.config.timeout
        deadline = _inference_deadline.get()
        if deadline is not None:
            timeout = min(timeout, deadline - started)
            if timeout <= 0:
                raise ControlError("TASK_SHIELD_INFERENCE_WINDOW_EXPIRED", 409)
        try:
            with self.http.stream(
                "POST",
                self.config.base_url.rstrip("/") + path,
                json=payload,
                headers=headers,
                timeout=timeout,
                follow_redirects=False,
            ) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes():
                    if len(data) + len(chunk) > 262144 or time.monotonic() - started >= timeout:
                        raise ControlError("TASK_SHIELD_PROVIDER_LIMIT", 503)
                    data.extend(chunk)
                raw = json.loads(data)
            if self.config.api_style == "gemini":
                candidates = raw["candidates"]
                if len(candidates) != 1 or candidates[0].get("finishReason") != "STOP":
                    raise ValueError("Incomplete Gemini response")
                content = "".join(
                    p["text"] for p in candidates[0]["content"]["parts"] if not p.get("thought")
                )
                usage = raw.get("usageMetadata", {})
                raw_usage = {
                    "prompt_tokens": usage.get("promptTokenCount"),
                    "completion_tokens": usage.get("candidatesTokenCount"),
                    "total_tokens": usage.get("totalTokenCount"),
                }
            elif self.config.api_style == "responses":
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
        except httpx.HTTPStatusError as error:
            raise ControlError(
                "TASK_SHIELD_PROVIDER_HTTP_" + str(error.response.status_code),
                503,
                retryable=error.response.status_code in {429, 500, 502, 503, 504},
            ) from None
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
