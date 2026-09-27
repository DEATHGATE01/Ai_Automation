from pydantic import BaseModel, Field

from secops_agent.agent import Agent
from secops_agent.config import Settings
from secops_agent.llm import ScriptedLLM
from secops_agent.retrieval import KeywordRetriever
from secops_agent.schemas import StepKind
from secops_agent.tools.base import ToolRegistry, ToolSpec

PLAN = (
    '{"goal": "g", "steps": [{"index": 1, "description": "look", "tool": "lookup",'
    ' "rationale": "r"}], "assumptions": []}'
)
FINISH = (
    '{"thought": "done", "done": true, "summary": "F-001 is critical and breached.",'
    ' "key_findings": ["F-001 is critical"], "decisions": '
    '[{"action": "opened ticket", "finding_id": "F-001", "severity": "critical",'
    ' "explanation": "sla_policy.md: critical = 7 days, days_open = 7"}],'
    ' "sources": ["sla_policy.md"]}'
)


class LookupArgs(BaseModel):
    key: str = Field(description="which row")


def _write_prompts(tmp_path):
    d = tmp_path / "prompts"
    d.mkdir(exist_ok=True)
    (d / "planner.md").write_text("plan it {tool_schema}", encoding="utf-8")
    (d / "executor.md").write_text("execute it {tool_schema}", encoding="utf-8")


def _agent(responses, tmp_path, calls=None):
    calls = calls if calls is not None else []
    reg = ToolRegistry()

    def lookup(key: str):
        calls.append(key)
        return {"rows": [{"finding_id": "F-001", "days_open": 7, "cvss": 9.8}]}

    reg.register(
        ToolSpec(name="lookup", description="look things up", args_model=LookupArgs, fn=lookup)
    )
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        runs_dir=tmp_path / "runs",
        prompts_dir=tmp_path / "prompts",
    )
    return Agent(settings=settings, llm=ScriptedLLM(responses), registry=reg,
                 retriever=KeywordRetriever([]))


def test_loop_calls_tool_then_finishes(tmp_path):
    _write_prompts(tmp_path)
    calls = []
    agent = _agent(
        [PLAN, '{"thought": "need data", "tool": "lookup", "args": {"key": "F-001"}}', FINISH],
        tmp_path,
        calls,
    )
    report = agent.run("g")
    assert calls == ["F-001"]
    assert report.summary.startswith("F-001 is critical")
    assert report.actions_taken == []  # no action tool was called
    assert report.tool_calls == 1


def test_loop_emits_expected_event_sequence(tmp_path):
    _write_prompts(tmp_path)
    agent = _agent(
        [PLAN, '{"thought": "t", "tool": "lookup", "args": {"key": "x"}}', FINISH], tmp_path
    )
    agent.run("g")
    kinds = [e.kind for e in agent.trace_events()]
    assert StepKind.plan in kinds
    assert StepKind.tool_call in kinds
    assert StepKind.tool_result in kinds
    assert kinds[-1] is StepKind.finish


def test_loop_stops_at_max_steps(tmp_path):
    _write_prompts(tmp_path)
    endless = ['{"thought": "t", "tool": "lookup", "args": {"key": "x"}}' for _ in range(10)]
    agent = _agent([PLAN, *endless], tmp_path)
    agent.settings.max_steps = 3
    report = agent.run("g")
    assert report.steps_used == 3
    assert any("step budget" in lim.lower() for lim in report.limitations)


def test_observations_are_truncated(tmp_path):
    _write_prompts(tmp_path)
    agent = _agent(
        [PLAN, '{"thought": "t", "tool": "lookup", "args": {"key": "x"}}', FINISH], tmp_path
    )
    agent.settings.max_observation_chars = 40
    agent.run("g")
    results = [e for e in agent.trace_events() if e.kind is StepKind.tool_result]
    assert results[0].payload["truncated"] is True
    assert len(results[0].payload["text"]) == 40


def test_a_wrongly_typed_tool_value_is_compacted_not_fatal(tmp_path):
    # Review finding: this payload used to raise TypeError out of parse_step, which nothing caught,
    # so the run died with a traceback and produced no report at all.
    _write_prompts(tmp_path)
    bad = '{"thought": "t", "tool": {"name": "lookup"}, "args": {"key": "F-001"}}'
    good = '{"thought": "t", "tool": "lookup", "args": {"key": "F-001"}}'
    agent = _agent([PLAN, bad, good, FINISH], tmp_path)
    report = agent.run("g")
    assert report.summary.startswith("F-001")
    assert any(e.kind is StepKind.error for e in agent.trace_events())


def test_finish_requires_valid_schema_and_recovers(tmp_path):
    _write_prompts(tmp_path)
    bad_finish = '{"done": true}'  # summary missing -> rejected
    agent = _agent([PLAN, bad_finish, FINISH], tmp_path)
    report = agent.run("g")
    assert report.summary.startswith("F-001")
    assert any(e.kind is StepKind.error for e in agent.trace_events())


def test_empty_response_is_reported_as_empty_not_as_bad_json(tmp_path):
    # Live: gpt-oss sometimes returns no content at all. "Expecting value" is a useless
    # thing to tell a reader, and the nudge sent back to the model should be specific.
    _write_prompts(tmp_path)
    agent = _agent([PLAN, "", FINISH], tmp_path)
    report = agent.run("g")
    reasons = [
        e.payload.get("reason", "") for e in agent.trace_events() if e.kind is StepKind.error
    ]
    assert any("empty" in r for r in reasons)
    assert any("empty" in str(lim).lower() for lim in report.limitations)
    assert report.summary.startswith("F-001")


def test_bad_tool_arguments_are_fed_back_not_crashed(tmp_path):
    _write_prompts(tmp_path)
    # 'key' is required; this call omits it -> ValueError -> compacted, then recover
    agent = _agent([PLAN, '{"thought": "t", "tool": "lookup", "args": {}}', FINISH], tmp_path)
    report = agent.run("g")
    assert report.summary.startswith("F-001")
    assert any(e.kind is StepKind.error for e in agent.trace_events())


def test_memory_is_written_after_a_run(tmp_path):
    _write_prompts(tmp_path)
    agent = _agent([PLAN, FINISH], tmp_path)
    agent.run("g")
    assert agent.memory.recall("g")[0]["run_id"] == agent.run_id


def test_initial_context_carries_the_date_and_the_plan(tmp_path):
    _write_prompts(tmp_path)
    agent = _agent([PLAN, FINISH], tmp_path)
    agent.run("g")
    first_prompt = agent.llm.message_log[1][0]["content"]
    assert "Today is" in first_prompt
    assert "Approved plan" in first_prompt
