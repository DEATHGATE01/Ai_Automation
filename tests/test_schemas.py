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


def test_parse_step_accepts_string_null_tool():
    # Live models write pure-reasoning steps as "tool": "null" (the string) even when told
    # to use real null. That is a reasoning step, not an unknown tool.
    raw = '{"thought": "think", "tool": "null", "args": {}}'
    step = parse_step(raw, valid_tools=VALID_TOOLS)
    assert step is None


def test_parse_step_tolerates_prose_around_the_json():
    raw = (
        'Sure! Here is the call:\n'
        '{"thought": "t", "tool": "list_findings", "args": {}}\n'
        "Hope that helps."
    )
    assert parse_step(raw, valid_tools=VALID_TOOLS).tool == "list_findings"


def test_parse_step_takes_the_first_of_several_concatenated_objects():
    # Live: gpt-oss emitted three JSON objects back to back, so json.loads raised
    # "Extra data" and the agent burned a step. One action per turn is the contract;
    # the first object is the one it wants now.
    raw = (
        '{"thought": "a", "tool": "list_findings", "args": {}}'
        '{"thought": "b", "tool": "search_policy", "args": {}}'
    )
    assert parse_step(raw, valid_tools=VALID_TOOLS).tool == "list_findings"


def test_extraction_respects_braces_inside_string_values():
    raw = '{"thought": "close the } brace and { this", "tool": "list_findings", "args": {}}'
    assert parse_step(raw, valid_tools=VALID_TOOLS).thought == "close the } brace and { this"


def test_parse_step_still_rejects_genuinely_bad_input():
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_step("I cannot help with that.", valid_tools=VALID_TOOLS)


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
