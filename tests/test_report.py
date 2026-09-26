from secops_agent.report import build_report, render_markdown
from secops_agent.schemas import FinishRequest, Plan

PLAN = Plan(
    goal="g",
    steps=[{"index": 1, "description": "look", "tool": "list_findings", "rationale": "r"}],
)
FINISH = FinishRequest(
    thought="t", summary="Answer.", key_findings=["k1"], sources=["sla_policy.md"]
)


def _report(**overrides):
    kwargs = dict(
        run_id="run-1",
        plan=PLAN,
        finish=FINISH,
        actions_taken=[],
        limitations=[],
        steps_used=1,
        tool_calls=0,
    )
    kwargs.update(overrides)
    return build_report(**kwargs)


def test_report_carries_counts_and_decisions():
    report = _report(actions_taken=["create_ticket(...)"], steps_used=3, tool_calls=2)
    assert report.steps_used == 3
    assert report.tool_calls == 2
    assert report.actions_taken == ["create_ticket(...)"]
    assert report.goal == "g"


def test_markdown_has_the_required_sections():
    md = render_markdown(_report(limitations=["none"]))
    for heading in (
        "## Summary",
        "## Key findings",
        "## Decisions",
        "## Actions taken",
        "## Sources",
        "## Assumptions",
        "## Limitations",
        "## Run metadata",
    ):
        assert heading in md


def test_markdown_labels_synthetic_data():
    assert "synthetic" in render_markdown(_report()).lower()


def test_markdown_renders_decisions_with_finding_and_severity():
    from secops_agent.schemas import Decision

    finish = FinishRequest(
        thought="t",
        summary="s",
        decisions=[
            Decision(
                action="escalated",
                finding_id="F-009",
                severity="critical",
                explanation="sla_policy.md: critical = 7 days, days_open = 9",
            )
        ],
    )
    md = render_markdown(_report(finish=finish))
    assert "**escalated**" in md
    assert "`F-009`" in md
    assert "critical" in md


def test_write_report_creates_both_files(tmp_path):
    from secops_agent.report import write_report

    json_path, md_path = write_report(_report(), tmp_path)
    assert json_path.exists() and md_path.exists()
    assert json_path.parent.name == "run-1"
    assert "Answer." in md_path.read_text(encoding="utf-8")
