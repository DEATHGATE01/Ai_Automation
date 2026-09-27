"""Every LLM output that matters is validated against one of these models.

If a model cannot be built from the LLM's text, the error is fed back to the LLM
(see agent.py) rather than crashing the run.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


class Severity(StrEnum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class PlanStep(BaseModel):
    index: int = Field(ge=1, description="1-based position in the plan")
    description: str = Field(min_length=1)
    tool: str | None = Field(default=None, description="Tool this step will use, if any")
    rationale: str = Field(min_length=1, description="Why this step is needed")


class Plan(BaseModel):
    goal: str = Field(min_length=1)
    steps: list[PlanStep] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)


class ToolCallRequest(BaseModel):
    thought: str = ""
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class Decision(BaseModel):
    action: str = Field(min_length=1)
    finding_id: str | None = None
    severity: Severity | None = None
    explanation: str = Field(min_length=1, description="Why this action, in the agent's words")


class FinishRequest(BaseModel):
    thought: str = ""
    done: bool = True
    summary: str = Field(min_length=1)
    key_findings: list[str] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class StepKind(StrEnum):
    plan = "plan"
    llm = "llm"
    tool_call = "tool_call"
    tool_result = "tool_result"
    error = "error"
    recovery = "recovery"
    finish = "finish"


class TraceEvent(BaseModel):
    """One line of runs/<id>/trace.jsonl. Vocabulary kept close to OTel GenAI conventions."""

    run_id: str
    seq: int = Field(ge=0)
    kind: StepKind
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    step: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class FinalReport(BaseModel):
    run_id: str
    goal: str
    summary: str
    key_findings: list[str]
    decisions: list[Decision]
    actions_taken: list[str]
    sources: list[str]
    assumptions: list[str]
    limitations: list[str]
    steps_used: int
    tool_calls: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def strip_code_fence(text: str) -> str:
    """Models love wrapping JSON in ``` fences even when told not to."""
    return _FENCE_RE.sub("", text.strip()).strip()


def parse_step(raw: str, valid_tools: set[str]) -> ToolCallRequest | FinishRequest | None:
    """Turn one LLM message into a validated request, or raise ValueError with a compact reason.

    Returns None for a pure-reasoning step (no tool), which the caller advances without a call.
    """
    try:
        obj = json.loads(strip_code_fence(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(f"response was not valid JSON: {exc.msg}") from exc

    if not isinstance(obj, dict):
        raise ValueError("response must be a JSON object")

    if obj.get("done") is True:
        try:
            return FinishRequest.model_validate(obj)
        except Exception as exc:  # re-raised as a model-readable reason
            raise ValueError(f"finish payload invalid: {exc}") from exc

    if "tool" not in obj:
        raise ValueError("response needs either a 'tool' field or 'done': true")

    tool = obj["tool"]
    if tool is None or tool == "null":
        # Live models write pure-reasoning steps as the STRING "null" even when told to use
        # real null; treat both spellings as "no tool", not as an unknown tool name.
        return None
    if tool not in valid_tools:
        raise ValueError(f"unknown tool {tool!r}; available: {sorted(valid_tools)}")

    args = obj.get("args") or {}
    if not isinstance(args, dict):
        raise ValueError("'args' must be a JSON object")

    return ToolCallRequest(thought=obj.get("thought", ""), tool=tool, args=args)
