import pytest
from pydantic import ValidationError

from secops_agent.schemas import (
    Decision,
    FinishRequest,
    Plan,
    PlanStep,
    ToolCallRequest,
    parse_step,
)

VALID_TOOLS = {"list_findings", "search_policy"}


def test_plan_requires_at_least_one_step():
    with pytest.raises(ValidationError):
        Plan(goal="g", steps=[])


def test_plan_step_index_must_be_positive():
    with pytest.raises(ValidationError):
        PlanStep(index=0, description="d", rationale="r")


def test_parse_step_reads_tool_call():
    raw = '{"thought": "look it up", "tool": "list_findings", "args": {"severity": "critical"}}'
    step = parse_step(raw, valid_tools=VALID_TOOLS)
    assert isinstance(step, ToolCallRequest)
    assert step.tool == "list_findings"
    assert step.args["severity"] == "critical"


def test_parse_step_reads_finish():
    raw = '{"thought": "enough", "done": true, "summary": "s", "key_findings": ["a"]}'
    step = parse_step(raw, valid_tools=VALID_TOOLS)
    assert isinstance(step, FinishRequest)
    assert step.key_findings == ["a"]


def test_parse_step_strips_markdown_fence():
    raw = '```json\n{"thought": "t", "tool": "get_asset", "args": {"asset_id": "A-001"}}\n```'
    step = parse_step(raw, valid_tools={"get_asset"})
    assert step.tool == "get_asset"


def test_parse_step_rejects_unknown_tool():
    raw = '{"thought": "t", "tool": "rm_rf", "args": {}}'
    with pytest.raises(ValueError, match="unknown tool"):
        parse_step(raw, valid_tools=VALID_TOOLS)


def test_parse_step_rejects_non_json():
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_step("I will now call the tool", valid_tools=VALID_TOOLS)


def test_decision_requires_explanation():
    with pytest.raises(ValidationError):
        Decision(action="escalate", explanation="")
