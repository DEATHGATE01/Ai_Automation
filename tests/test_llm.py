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


class _EmptyThenGood:
    """Returns empty content once (reasoning model behaviour), then a real answer."""

    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        content = "" if self.calls == 1 else '{"done": true}'
        msg = type("M", (), {"content": content})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()


def test_empty_content_is_returned_immediately_without_burning_retries(monkeypatch):
    # Live finding: gpt-oss returns an empty `content` on some turns (text lands in
    # `reasoning`). Four identical retries produced four identical empties, so retrying here
    # is pure waste - the agent's nudge (a NEW message) is what recovers the run. The client
    # must therefore spend exactly ONE call and hand "" back.
    client = OpenAICompatLLM(_settings(llm_max_retries=3), sleep=lambda _s: None)
    stub = _EmptyThenGood()
    monkeypatch.setattr(client._client.chat, "completions", stub)

    assert client.complete(system="s", messages=[{"role": "user", "content": "x"}]) == ""
    assert stub.calls == 1


def test_empty_content_never_raises(monkeypatch):
    client = OpenAICompatLLM(_settings(llm_max_retries=1), sleep=lambda _s: None)
    calls = {"n": 0}

    def always_empty(**kwargs):
        calls["n"] += 1
        msg = type("M", (), {"content": ""})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    monkeypatch.setattr(client._client.chat, "completions", SimpleNamespace(create=always_empty))
    # must NOT raise: the agent's own compaction handles an empty response
    assert client.complete(system="s", messages=[{"role": "user", "content": "x"}]) == ""
    assert calls["n"] == 1


def test_provider_reasoning_is_captured_when_content_is_empty(monkeypatch):
    # Groq's gpt-oss returns empty content with the text in a separate `reasoning` field
    # (confirmed by direct API probe). Capturing it turns an opaque empty trace entry into
    # an explained one.
    client = OpenAICompatLLM(_settings(), sleep=lambda _s: None)
    msg = type("M", (), {"content": "", "reasoning": "We need to check the SLA policy first"})()
    resp = type("R", (), {"choices": [type("C", (), {"message": msg})()]})()
    stub = SimpleNamespace(create=lambda **k: resp)
    monkeypatch.setattr(client._client.chat, "completions", stub)

    client.complete(system="s", messages=[{"role": "user", "content": "x"}])
    assert client.last_reasoning == "We need to check the SLA policy first"


def test_missing_reasoning_field_is_empty_not_an_error(monkeypatch):
    client = OpenAICompatLLM(_settings(), sleep=lambda _s: None)
    msg = type("M", (), {"content": '{"done": true}'})()
    resp = type("R", (), {"choices": [type("C", (), {"message": msg})()]})()
    stub = SimpleNamespace(create=lambda **k: resp)
    monkeypatch.setattr(client._client.chat, "completions", stub)

    client.complete(system="s", messages=[{"role": "user", "content": "x"}])
    assert client.last_reasoning == ""
