import pytest

from secops_agent.config import Settings


def test_defaults_are_sane(monkeypatch):
    monkeypatch.delenv("SECOPS_MAX_STEPS", raising=False)
    s = Settings(_env_file=None)
    assert s.max_steps == 12
    assert s.auto_approve is False
    assert s.max_observation_chars == 1200


def test_env_override(monkeypatch):
    monkeypatch.setenv("SECOPS_MAX_STEPS", "3")
    monkeypatch.setenv("SECOPS_AUTO_APPROVE", "true")
    s = Settings(_env_file=None)
    assert s.max_steps == 3
    assert s.auto_approve is True


def test_fault_string_parsed(monkeypatch):
    monkeypatch.setenv("SECOPS_INJECT_FAULT", "list_findings:timeout@1")
    s = Settings(_env_file=None)
    assert s.inject_fault == "list_findings:timeout@1"


def test_requires_api_key_when_remote(monkeypatch):
    monkeypatch.setenv("SECOPS_LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.delenv("SECOPS_LLM_API_KEY", raising=False)
    s = Settings(_env_file=None)
    with pytest.raises(ValueError, match="SECOPS_LLM_API_KEY"):
        s.validate_backend()
