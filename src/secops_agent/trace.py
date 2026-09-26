"""The audit trail: every agent event, in order, one JSON object per line.

It is the substrate for three graded deliverables: the run transcripts, the recovery evidence, and
the 'what did it actually do' section of the report.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schemas import StepKind, TraceEvent


class TraceWriter:
    def __init__(self, run_id: str, runs_dir: Path) -> None:
        self.run_id = run_id
        self.dir = Path(runs_dir) / run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "trace.jsonl"
        self._seq = 0
        self.tool_calls = 0
        self.errors = 0

    def emit(
        self,
        kind: StepKind,
        *,
        step: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> TraceEvent:
        event = TraceEvent(
            run_id=self.run_id, seq=self._seq, kind=kind, step=step, payload=payload or {}
        )
        if kind is StepKind.tool_call:
            self.tool_calls += 1
        if kind is StepKind.error:
            self.errors += 1
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.model_dump(mode="json")) + "\n")
        self._seq += 1
        return event


def load_trace(path: Path) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(TraceEvent.model_validate(json.loads(line)))
    return events


def render_transcript(events: list[TraceEvent]) -> str:
    """Human-readable replay. This is what gets committed under docs/transcripts/ and uploaded."""
    if not events:
        return "# Run transcript\n\n_(empty run)_\n"

    run_id = events[0].run_id
    out: list[str] = [
        f"# Run transcript — `{run_id}`",
        "",
        f"Events: **{len(events)}**  ·  tool calls: "
        f"**{sum(1 for e in events if e.kind is StepKind.tool_call)}**  ·  errors: "
        f"**{sum(1 for e in events if e.kind is StepKind.error)}**",
        "",
    ]
    for event in events:
        stamp = event.ts.strftime("%H:%M:%S")
        payload = event.payload

        if event.kind is StepKind.plan:
            out.append("## Plan")
            out.append("")
            out.append(f"**Goal:** {payload.get('goal', '')}")
            out.append("")
            for item in payload.get("steps", []):
                out.append(f"- {item}")
            out.append("")
            continue

        where = f"step {event.step}" if event.step is not None else "setup"
        out.append(f"## `{event.seq:02d}` · {event.kind.value} · _{where}_ · {stamp}Z")
        out.append("")

        if event.kind is StepKind.llm:
            out.append(f"**Thought:** {payload.get('thought', '')}")
        elif event.kind is StepKind.tool_call:
            out.append(f"**Tool:** `{payload.get('tool')}`")
            out.append("")
            out.append("```json")
            out.append(json.dumps(payload.get("args", {}), indent=2, default=str))
            out.append("```")
        elif event.kind is StepKind.tool_result:
            out.append(f"**Tool:** `{payload.get('tool')}`")
            if payload.get("truncated"):
                out.append("")
                out.append("_(observation truncated before being shown to the model)_")
            out.append("")
            out.append("```json")
            out.append(json.dumps(payload.get("result", payload), indent=2, default=str)[:2000])
            out.append("```")
        elif event.kind is StepKind.finish:
            out.append("```json")
            out.append(json.dumps(payload, indent=2, default=str)[:2000])
            out.append("```")
        elif event.kind is StepKind.error:
            out.append(f"**Error:** {payload.get('reason', '')}")
            out.append("")
            out.append(f"**Agent sees:** `{payload.get('compacted', '')}`")
        elif event.kind is StepKind.recovery:
            out.append(f"**Recovery:** {payload.get('message', '')}")
        out.append("")
    return "\n".join(out)
