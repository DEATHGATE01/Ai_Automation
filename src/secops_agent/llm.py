"""One narrow seam between the agent and any LLM provider.

`OpenAICompatLLM` talks to any OpenAI-compatible endpoint (Groq, OpenAI, OpenRouter, Ollama).
`ScriptedLLM` lets the entire test suite run offline and deterministically - that is what makes the
agent loop testable at all, and is the single most important design decision in the tests.
"""

from __future__ import annotations

import time
from typing import Any, Protocol

from openai import OpenAI

from .config import Settings


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    last_usage: dict[str, int]

    def complete(self, *, system: str, messages: list[dict[str, str]]) -> str: ...


class OpenAICompatLLM:
    def __init__(self, settings: Settings, sleep=time.sleep) -> None:
        self._settings = settings
        self._sleep = sleep
        self._client = OpenAI(
            api_key=settings.llm_api_key or "not-needed",
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_s,
        )
        self.last_usage: dict[str, int] = {}

    def complete(self, *, system: str, messages: list[dict[str, str]]) -> str:
        attempts = self._settings.llm_max_retries + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                # the SDK's message param is a union of TypedDicts; dict[str, str] is accepted at
                # runtime by every OpenAI-compatible backend, so the list is widened deliberately.
                payload: list[Any] = [{"role": "system", "content": system}, *messages]
                resp = self._client.chat.completions.create(
                    model=self._settings.llm_model,
                    temperature=self._settings.llm_temperature,
                    messages=payload,
                )
                usage = getattr(resp, "usage", None)
                self.last_usage = (
                    {
                        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                    }
                    if usage is not None
                    else {}
                )
                return resp.choices[0].message.content or ""
            except Exception as exc:  # noqa: BLE001 - provider SDK error types vary by version
                last_error = exc
                if attempt < attempts:
                    self._sleep(min(2 ** (attempt - 1), 8))
        raise LLMError(
            f"LLM call failed after {attempts} attempts: {type(last_error).__name__}: {last_error}"
        )


class ScriptedLLM:
    """Test double: returns canned responses in order and records what it was asked."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.last_usage: dict[str, int] = {}
        self.calls = 0
        self.systems: list[str] = []
        self.message_log: list[list[dict[str, str]]] = []

    def complete(self, *, system: str, messages: list[dict[str, str]]) -> str:
        self.systems.append(system)
        self.message_log.append([dict(m) for m in messages])
        if not self._responses:
            raise LLMError(f"script exhausted after {self.calls} calls")
        self.calls += 1
        return self._responses.pop(0)


def build_llm(settings: Settings) -> LLM:
    settings.validate_backend()
    return OpenAICompatLLM(settings)


def usage_totals(usages: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "prompt_tokens": sum(int(u.get("prompt_tokens", 0)) for u in usages),
        "completion_tokens": sum(int(u.get("completion_tokens", 0)) for u in usages),
    }
