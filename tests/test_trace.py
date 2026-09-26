import json

from secops_agent.schemas import StepKind
from secops_agent.trace import TraceWriter, load_trace, render_transcript


def test_writer_appends_jsonl_with_increasing_seq(tmp_path):
    w = TraceWriter(run_id="run-1", runs_dir=tmp_path)
    w.emit(StepKind.plan, payload={"goal": "g"})
    w.emit(StepKind.tool_call, step=1, payload={"tool": "list_findings"})

    lines = (tmp_path / "run-1" / "trace.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    events = [json.loads(line) for line in lines]
    assert [e["seq"] for e in events] == [0, 1]
    assert events[1]["kind"] == "tool_call"
    assert events[1]["step"] == 1


def test_load_trace_roundtrips(tmp_path):
    w = TraceWriter(run_id="run-2", runs_dir=tmp_path)
    w.emit(StepKind.error, payload={"reason": "boom"})
    events = load_trace(tmp_path / "run-2" / "trace.jsonl")
    assert len(events) == 1
    assert events[0].payload["reason"] == "boom"


def test_writer_records_cumulative_counters(tmp_path):
    w = TraceWriter(run_id="run-3", runs_dir=tmp_path)
    w.emit(StepKind.tool_call, payload={"tool": "a"})
    w.emit(StepKind.tool_call, payload={"tool": "b"})
    assert w.tool_calls == 2


def test_render_transcript_is_readable_markdown(tmp_path):
    w = TraceWriter(run_id="run-4", runs_dir=tmp_path)
    w.emit(StepKind.plan, payload={"goal": "g", "steps": ["1. look", "2. act"]})
    w.emit(
        StepKind.tool_result, step=1, payload={"tool": "list_findings", "result": [{"id": "F-1"}]}
    )
    w.emit(StepKind.error, step=2, payload={"reason": "timeout"})
    w.emit(StepKind.recovery, step=2, payload={"message": "switching tools"})

    md = render_transcript(load_trace(tmp_path / "run-4" / "trace.jsonl"))
    assert md.startswith("# Run transcript")
    for needle in ("## Plan", "list_findings", "timeout", "switching tools"):
        assert needle in md


def test_render_transcript_handles_an_empty_run(tmp_path):
    assert "empty run" in render_transcript([])
