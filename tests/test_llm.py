from types import SimpleNamespace

import pytest

from secops_agent.config import Settings
from secops_agent.llm import LLMError, OpenAICompatLLM, ScriptedLLM


def _settings(**kw):
    base = dict(_env_file=None, llm_api_key="test-key", llm_max_retries=2, llm_timeout_s=5)
    base.update(kw)
    return Settings(**base)


class _FlakyCompletions:
    """Fails twice with a retryable error, then succeeds."""

    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.calls < 3:
            raise RuntimeError("429 rate limited")
        return type(
            "R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": "ok"})()})()]}
        )()


def test_retries_then_succeeds(monkeypatch):
    client = OpenAICompatLLM(_settings(), sleep=lambda _s: None)
    flaky = _FlakyCompletions()
    monkeypatch.setattr(client._client.chat, "completions", flaky)

    assert client.complete(system="s", messages=[{"role": "user", "content": "hi"}]) == "ok"
    assert flaky.calls == 3


def test_raises_after_budget_exhausted(monkeypatch):
    client = OpenAICompatLLM(_settings(llm_max_retries=1), sleep=lambda _s: None)

    def always_fail(**kwargs):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(client._client.chat, "completions", always_fail)
    with pytest.raises(LLMError, match="after 2 attempts"):
        client.complete(system="s", messages=[{"role": "user", "content": "hi"}])


def test_scripted_llm_pops_in_order():
    llm = ScriptedLLM(['{"a": 1}', '{"b": 2}'])
    msgs = [{"role": "user", "content": "x"}]
    assert llm.complete(system="s", messages=msgs) == '{"a": 1}'
    assert llm.complete(system="s", messages=msgs) == '{"b": 2}'
    assert llm.calls == 2


def test_scripted_llm_exhausted_is_loud():
    llm = ScriptedLLM([])
    with pytest.raises(LLMError, match="script exhausted"):
        llm.complete(system="s", messages=[{"role": "user", "content": "x"}])


def test_records_token_usage_when_present(monkeypatch):
    client = OpenAICompatLLM(_settings(), sleep=lambda _s: None)
    resp = type(
        "R",
        (),
        {
            "choices": [type("C", (), {"message": type("M", (), {"content": "hi"})()})()],
            "usage": type("U", (), {"prompt_tokens": 11, "completion_tokens": 7})(),
        },
    )()
    # the stub must expose .create(), because the client calls .completions.create(...)
    stub = SimpleNamespace(create=lambda **k: resp)
    monkeypatch.setattr(client._client.chat, "completions", stub)
    client.complete(system="s", messages=[{"role": "user", "content": "x"}])
    assert client.last_usage == {"prompt_tokens": 11, "completion_tokens": 7}
