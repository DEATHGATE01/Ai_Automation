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


def test_inline_comment_in_the_env_file_is_not_mistaken_for_a_key(monkeypatch):
    # Found by clean-clone testing: `cp .env.example .env` turned the shipped
    # "SECOPS_LLM_API_KEY=   # required unless ..." line into a 52-char comment STRING,
    # which is truthy, so validate_backend() passed and the run died with a confusing
    # "401 Invalid API Key" instead of telling the user to set a key.
    monkeypatch.setenv("SECOPS_LLM_API_KEY", "# required unless you point BASE_URL at local Ollama")
    s = Settings(_env_file=None)
    assert s.llm_api_key == ""
    with pytest.raises(ValueError, match="SECOPS_LLM_API_KEY"):
        s.validate_backend()


def test_api_key_whitespace_and_quotes_are_stripped(monkeypatch):
    monkeypatch.setenv("SECOPS_LLM_API_KEY", '  "gsk_abc123"  ')
    s = Settings(_env_file=None)
    assert s.llm_api_key == "gsk_abc123"


def test_env_example_keeps_the_key_line_free_of_inline_comments():
    """Regression guard: the file a grader copies must not carry a comment on the key line."""
    from secops_agent.config import PROJECT_ROOT

    text = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("SECOPS_LLM_API_KEY="):
            assert "#" not in line, f"inline comment on the key line: {line!r}"
            assert line.split("=", 1)[1].strip() == ""
