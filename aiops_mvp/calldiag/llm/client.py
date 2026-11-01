"""Provider-neutral LLM client used only to reword report summaries (plan 10).

Configuration comes from the environment:
  CALLDIAG_LLM_PROVIDER  provider name (default "openai"; the only one implemented)
  CALLDIAG_LLM_MODEL     model ID (required; never hard-coded)
  OPENAI_API_KEY         read by the OpenAI SDK itself (OPENAI_BASE_URL is honoured too)
"""

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from calldiag import config


class LLMClient(Protocol):
    model: str

    def complete(self, system: str, user: str) -> str: ...


@dataclass
class FakeLLM:
    """Deterministic stand-in for tests: returns `response`, or raises `error` if set."""

    response: str = ""
    error: Exception | None = None
    model: str = "fake-llm"
    calls: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self.error is not None:
            raise self.error
        return self.response


class OpenAIClient:
    def __init__(self, model: str, *, sdk_client: Any | None = None) -> None:
        if sdk_client is None:
            from openai import OpenAI  # lazy: the SDK is an optional extra

            sdk_client = OpenAI(timeout=config.LLM_TIMEOUT_SEC, max_retries=config.LLM_MAX_RETRIES)
        self.model = model
        self._client = sdk_client

    def complete(self, system: str, user: str) -> str:
        # No temperature: some OpenAI models reject non-default sampling; determinism comes from the cache.
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
        )
        choice = response.choices[0]
        if choice.message.refusal:
            raise RuntimeError(f"model refused: {choice.message.refusal}")
        if choice.finish_reason == "length":
            raise RuntimeError("response cut off at the token limit")
        return choice.message.content or ""


def resolve_client() -> tuple[LLMClient | None, str | None]:
    """Return (client, None) when usable, else (None, reason). Never raises."""
    provider = os.environ.get("CALLDIAG_LLM_PROVIDER", config.LLM_DEFAULT_PROVIDER).strip().lower()
    if provider not in config.LLM_PROVIDERS:
        return None, f"CALLDIAG_LLM_PROVIDER={provider!r} chưa được hỗ trợ (hỗ trợ: {', '.join(config.LLM_PROVIDERS)})"
    model = os.environ.get("CALLDIAG_LLM_MODEL", "").strip()
    if not model:
        return None, "chưa đặt CALLDIAG_LLM_MODEL (ID model của OpenAI)"
    if not os.environ.get("OPENAI_API_KEY"):
        return None, "chưa đặt OPENAI_API_KEY"
    try:
        return OpenAIClient(model), None
    except ImportError:
        return None, 'chưa cài SDK openai: pip install -e ".[llm]"'
    except Exception as exc:  # misconfiguration must never break the pipeline
        return None, f"không khởi tạo được OpenAI client: {type(exc).__name__}: {exc}"


def get_client() -> LLMClient | None:
    return resolve_client()[0]
