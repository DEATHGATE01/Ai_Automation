from pydantic import BaseModel

from secops_agent.agent import Agent
from secops_agent.config import Settings
from secops_agent.llm import ScriptedLLM
from secops_agent.retrieval import KeywordRetriever
from secops_agent.schemas import Plan
from secops_agent.tools.base import ToolRegistry, ToolSpec


class NoopArgs(BaseModel):
    pass


def _registry(*names):
    reg = ToolRegistry()
    for name in names:
        reg.register(
            ToolSpec(
                name=name,
                description=f"{name} tool",
                args_model=NoopArgs,
                fn=lambda: {"ok": 1},
            )
        )
    return reg


def _agent(responses, tmp_path, *tool_names):
    settings = Settings(_env_file=None, data_dir=tmp_path, runs_dir=tmp_path / "runs")
    return Agent(
        settings=settings,
        llm=ScriptedLLM(responses),
        registry=_registry(*tool_names),
        retriever=KeywordRetriever([]),
    )


VALID = (
    '{"goal": "triage vpn findings", "steps": ['
    '{"index": 1, "description": "list findings", "tool": "list_findings",'
    ' "rationale": "need the register"},'
    '{"index": 2, "description": "read the SLA policy", "tool": null,'
    ' "rationale": "the windows come from policy"},'
    '{"index": 3, "description": "decide", "tool": null, "rationale": "r"}], "assumptions": []}'
)


def test_plan_parses_valid_json(tmp_path):
    agent = _agent([VALID], tmp_path, "list_findings")
    plan = agent.plan("triage vpn findings")
    assert isinstance(plan, Plan)
    assert plan.steps[0].tool == "list_findings"


def test_plan_retries_once_and_feeds_the_error_back(tmp_path):
    bad = "sorry, I cannot produce JSON"
    good = (
        '{"goal": "g", "steps": ['
        '{"index": 1, "description": "d", "tool": null, "rationale": "r"},'
        '{"index": 2, "description": "e", "tool": null, "rationale": "r"},'
        '{"index": 3, "description": "f", "tool": null, "rationale": "r"}], "assumptions": []}'
    )
    agent = _agent([bad, good], tmp_path)
    plan = agent.plan("g")
    assert len(plan.steps) == 3
    assert not any("fallback" in a.lower() for a in plan.assumptions)
    second_prompt = agent.llm.message_log[1]
    assert any("not valid JSON" in m["content"] for m in second_prompt)


def test_plan_falls_back_after_two_bad_responses(tmp_path):
    agent = _agent(["nope", "still nope"], tmp_path)
    plan = agent.plan("g")
    assert plan.steps[0].tool is None
    assert any("fallback" in a.lower() for a in plan.assumptions)


def test_plan_rejects_unknown_tool_then_recovers(tmp_path):
    bad = (
        '{"goal": "g", "steps": ['
        '{"index": 1, "description": "d", "tool": "web_search", "rationale": "r"},'
        '{"index": 2, "description": "e", "tool": null, "rationale": "r"},'
        '{"index": 3, "description": "f", "tool": null, "rationale": "r"}], "assumptions": []}'
    )
    good = (
        '{"goal": "g", "steps": ['
        '{"index": 1, "description": "d", "tool": null, "rationale": "r"},'
        '{"index": 2, "description": "e", "tool": null, "rationale": "r"},'
        '{"index": 3, "description": "f", "tool": null, "rationale": "r"}], "assumptions": []}'
    )
    agent = _agent([bad, good], tmp_path, "list_findings")
    plan = agent.plan("g")
    assert plan.steps[0].tool is None
    assert not any("fallback" in a.lower() for a in plan.assumptions)


def test_fallback_plan_uses_an_available_tool_when_one_exists(tmp_path):
    agent = _agent(["nope", "still nope"], tmp_path, "list_findings")
    assert agent.plan("g").steps[0].tool == "list_findings"


def test_plan_emits_a_single_trace_event(tmp_path):
    agent = _agent([VALID], tmp_path, "list_findings")
    agent.plan("g")
    events = agent.trace_events()
    assert len(events) == 1
    assert events[0].kind.value == "plan"
    assert events[0].payload["goal"] == "triage vpn findings"


def test_plan_retry_is_visible_in_the_trace(tmp_path):
    from secops_agent.schemas import StepKind

    agent = _agent(["nope", "still nope"], tmp_path)
    agent.plan("g")
    kinds = [e.kind for e in agent.trace_events()]
    assert StepKind.error in kinds
    assert StepKind.recovery in kinds  # the fallback is announced
