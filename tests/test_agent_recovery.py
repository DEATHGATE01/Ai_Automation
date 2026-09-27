from pydantic import BaseModel, Field

from secops_agent.agent import Agent
from secops_agent.config import Settings
from secops_agent.llm import ScriptedLLM
from secops_agent.retrieval import KeywordRetriever
from secops_agent.schemas import StepKind
from secops_agent.tools.base import ToolError, ToolRegistry, ToolSpec

PLAN = (
    '{"goal": "g", "steps": [{"index": 1, "description": "look", "tool": "flaky",'
    ' "rationale": "r"}], "assumptions": []}'
)
FINISH = (
    '{"thought": "done", "done": true, "summary": "Recovered and answered.",'
    ' "key_findings": ["k"], "decisions": [], "sources": ["fallback"]}'
)


class Args(BaseModel):
    key: str = Field(description="k")


def _write_prompts(tmp_path):
    d = tmp_path / "prompts"
    d.mkdir(exist_ok=True)
    (d / "planner.md").write_text("p {tool_schema}", encoding="utf-8")
    (d / "executor.md").write_text("e {tool_schema}", encoding="utf-8")


def _agent(tmp_path, responses, fail_forever: bool):
    calls = {"n": 0}

    def flaky(key: str):
        calls["n"] += 1
        if fail_forever or calls["n"] == 1:
            raise ToolError("injected timeout: flaky service did not respond within 30s")
        return {"rows": ["recovered"]}

    reg = ToolRegistry()
    reg.register(ToolSpec(name="flaky", description="d", args_model=Args, fn=flaky))
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        runs_dir=tmp_path / "runs",
        prompts_dir=tmp_path / "prompts",
        max_steps=6,
        max_tool_failures=4,
    )
    return Agent(settings=settings, llm=ScriptedLLM(responses), registry=reg,
                 retriever=KeywordRetriever([]))


STEP = '{"thought": "t", "tool": "flaky", "args": {"key": "k"}}'


def _scripted_agent(tmp_path, outcomes, max_tool_failures, max_steps=8):
    """A tool whose behaviour follows a script, so fail/succeed interleaving can be driven."""
    seq = iter(outcomes)

    def flaky(key: str):
        if next(seq):
            raise ToolError("injected: boom")
        return {"rows": ["ok"]}

    reg = ToolRegistry()
    reg.register(ToolSpec(name="flaky", description="d", args_model=Args, fn=flaky))
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        runs_dir=tmp_path / "runs",
        prompts_dir=tmp_path / "prompts",
        max_steps=max_steps,
        max_tool_failures=max_tool_failures,
    )
    responses = [PLAN, *[STEP] * max_steps, FINISH]
    return Agent(settings=settings, llm=ScriptedLLM(responses), registry=reg,
                 retriever=KeywordRetriever([]))


def test_total_tool_failures_trip_the_budget_even_when_successes_interleave(tmp_path):
    # Review finding: the gate summed a per-argument counter that is cleared on any success, so
    # fail/succeed/fail/succeed never tripped it, contradicting the README's "total failures".
    _write_prompts(tmp_path)
    agent = _scripted_agent(tmp_path, [True, False, True, False, True], max_tool_failures=2)
    report = agent.run("g")
    assert any("failure budget" in limitation for limitation in report.limitations)


def test_the_repeat_failure_limitation_describes_what_actually_happens(tmp_path):
    # Review finding: the report claimed the agent "re-planned around" the failing tool. No
    # re-planning happens - the loop injects a hint and keeps going. The report must not assert a
    # recovery behaviour that did not occur.
    _write_prompts(tmp_path)
    agent = _scripted_agent(tmp_path, [True] * 8, max_tool_failures=99)
    report = agent.run("g")
    joined = " ".join(report.limitations).lower()
    assert "re-plan" not in joined and "replanned" not in joined
    assert "change approach" in joined


def test_a_stopped_run_does_not_name_a_source_it_never_read(tmp_path):
    _write_prompts(tmp_path)
    agent = _scripted_agent(tmp_path, [True], max_tool_failures=1, max_steps=1)
    report = agent.run("g")
    assert not any("findings table" in source for source in report.sources)


def test_a_tool_failure_stop_does_not_claim_the_step_budget(tmp_path):
    # Re-review finding: both stop paths shared one summary, so a run stopped by the tool failure
    # budget claimed it had hit the *step* budget - the report contradicted its own limitations.
    _write_prompts(tmp_path)
    agent = _scripted_agent(tmp_path, [True, False, True], max_tool_failures=2)
    report = agent.run("g")
    assert any("failure budget" in limitation for limitation in report.limitations)
    assert "step budget" not in report.summary.lower()


def test_a_step_budget_stop_still_says_step_budget(tmp_path):
    _write_prompts(tmp_path)
    agent = _scripted_agent(tmp_path, [False] * 8, max_tool_failures=99, max_steps=2)
    report = agent.run("g")
    assert "step budget" in report.summary.lower()


def test_agent_retries_a_failed_tool_and_succeeds(tmp_path):
    _write_prompts(tmp_path)
    agent = _agent(
        tmp_path,
        [
            PLAN,
            '{"thought": "t", "tool": "flaky", "args": {"key": "x"}}',
            '{"thought": "retrying", "tool": "flaky", "args": {"key": "x"}}',
            FINISH,
        ],
        fail_forever=False,
    )
    report = agent.run("g")
    kinds = [e.kind for e in agent.trace_events()]
    assert StepKind.error in kinds
    assert StepKind.tool_result in kinds
    assert report.summary == "Recovered and answered."


def test_repeat_failure_triggers_a_recovery_event_with_a_strategy_hint(tmp_path):
    _write_prompts(tmp_path)
    repeat = '{"thought": "t", "tool": "flaky", "args": {"key": "x"}}'
    agent = _agent(tmp_path, [PLAN, repeat, repeat, FINISH], fail_forever=True)
    agent.run("g")
    recoveries = [e for e in agent.trace_events() if e.kind is StepKind.recovery]
    assert recoveries, "expected a recovery event after a repeated identical failure"
    assert "Do not repeat it" in recoveries[0].payload["message"]


def test_recovery_hint_reaches_the_model(tmp_path):
    _write_prompts(tmp_path)
    repeat = '{"thought": "t", "tool": "flaky", "args": {"key": "x"}}'
    agent = _agent(tmp_path, [PLAN, repeat, repeat, FINISH], fail_forever=True)
    agent.run("g")
    last_prompt = agent.llm.message_log[-1]
    assert any("Do not repeat it" in m["content"] for m in last_prompt)


def test_failure_budget_ends_the_run_with_a_limitation(tmp_path):
    _write_prompts(tmp_path)
    repeat = '{"thought": "t", "tool": "flaky", "args": {"key": "x"}}'
    agent = _agent(tmp_path, [PLAN, repeat, repeat, repeat, repeat], fail_forever=True)
    agent.settings.max_tool_failures = 2
    report = agent.run("g")
    assert any("failure budget" in lim.lower() for lim in report.limitations)


def test_failed_tool_is_named_in_the_limitations(tmp_path):
    _write_prompts(tmp_path)
    repeat = '{"thought": "t", "tool": "flaky", "args": {"key": "x"}}'
    agent = _agent(tmp_path, [PLAN, repeat, repeat, FINISH], fail_forever=True)
    report = agent.run("g")
    assert any("flaky" in lim for lim in report.limitations)


def test_recovery_is_visible_in_the_transcript(tmp_path):
    from secops_agent.trace import render_transcript

    _write_prompts(tmp_path)
    repeat = '{"thought": "t", "tool": "flaky", "args": {"key": "x"}}'
    agent = _agent(tmp_path, [PLAN, repeat, repeat, FINISH], fail_forever=True)
    agent.run("g")
    md = render_transcript(agent.trace_events())
    assert "**Recovery:**" in md
    assert "injected timeout" in md


def test_different_arguments_do_not_count_as_a_repeat(tmp_path):
    _write_prompts(tmp_path)
    a = '{"thought": "t", "tool": "flaky", "args": {"key": "x"}}'
    b = '{"thought": "t", "tool": "flaky", "args": {"key": "y"}}'
    agent = _agent(tmp_path, [PLAN, a, b, FINISH], fail_forever=True)
    agent.run("g")
    recoveries = [e for e in agent.trace_events() if e.kind is StepKind.recovery]
    assert recoveries == [], "differing arguments must not trigger the repeat-failure branch"
