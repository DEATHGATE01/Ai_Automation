"""Assemble the structured final answer and render it for humans.

The JSON form is the machine-readable artifact; the Markdown form is what a reviewer reads first.
Both carry the synthetic-data notice so the disclosure cannot be lost in a screenshot.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schemas import Decision, FinalReport, FinishRequest, Plan

SYNTHETIC_NOTICE = (
    "> Data notice: the findings register, asset inventory and policy corpus used in this run are "
    "synthetic and exist only to demonstrate the agent. No real client data is involved."
)


def build_report(
    *,
    run_id: str,
    plan: Plan,
    finish: FinishRequest,
    actions_taken: list[str],
    limitations: list[str],
    steps_used: int,
    tool_calls: int,
) -> FinalReport:
    return FinalReport(
        run_id=run_id,
        goal=plan.goal,
        summary=finish.summary,
        key_findings=list(finish.key_findings),
        decisions=list(finish.decisions),
        actions_taken=actions_taken,
        sources=list(finish.sources),
        assumptions=list(plan.assumptions),
        limitations=list(limitations),
        steps_used=steps_used,
        tool_calls=tool_calls,
    )


def _bullets(items: list[str], empty: str = "_none_") -> str:
    return "\n".join(f"- {item}" for item in items) if items else empty


def _decision_line(decision: Decision) -> str:
    line = f"- **{decision.action}**"
    if decision.finding_id:
        line += f" (finding `{decision.finding_id}`)"
    if decision.severity:
        line += f" severity: {decision.severity.value}"
    return f"{line} — {decision.explanation}"


def render_markdown(report: FinalReport) -> str:
    decisions = "\n".join(_decision_line(d) for d in report.decisions) or "_none_"
    return f"""# Triage report - `{report.run_id}`

{SYNTHETIC_NOTICE}

## Summary

{report.summary}

**Goal:** {report.goal}

## Key findings

{_bullets(report.key_findings)}

## Decisions

{decisions}

## Actions taken

{_bullets(report.actions_taken)}

## Sources

{_bullets(report.sources)}

## Assumptions

{_bullets(report.assumptions)}

## Limitations

{_bullets(report.limitations)}

## Run metadata

| field | value |
| --- | --- |
| run id | `{report.run_id}` |
| generated at | {report.generated_at.isoformat()} |
| steps used | {report.steps_used} |
| tool calls | {report.tool_calls} |
"""


def write_report(report: FinalReport, runs_dir: Path) -> tuple[Path, Path]:
    out = Path(runs_dir) / report.run_id
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "report.json"
    md_path = out / "report.md"
    json_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def report_as_dicts(report: FinalReport) -> dict[str, Any]:
    """Escaped JSON view, handy for embedding the report in a larger artifact."""
    return report.model_dump(mode="json")
