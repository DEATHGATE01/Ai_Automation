import json

import pytest

from secops_agent.tools import actions
from secops_agent.tools.base import ToolError


def test_create_ticket_appends_jsonl(tmp_path):
    path = tmp_path / "tickets.jsonl"
    out = actions.create_ticket(path, finding_id="F-001", owner="platform-team",
                               severity="critical", due_date="2026-09-27",
                               summary="Patch the web framework")
    assert out["ticket_id"].startswith("T-")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["finding_id"] == "F-001"
    assert rows[0]["severity"] == "critical"
    assert rows[0]["status"] == "open"


def test_create_ticket_rejects_a_bad_date(tmp_path):
    with pytest.raises(ValueError, match="due_date"):
        actions.create_ticket(tmp_path / "t.jsonl", finding_id="F-001", owner="o",
                              severity="high", due_date="next tuesday", summary="s")


def test_create_ticket_rejects_unknown_severity(tmp_path):
    with pytest.raises(ValueError, match="severity"):
        actions.create_ticket(tmp_path / "t.jsonl", finding_id="F-001", owner="o",
                              severity="catastrophic", due_date="2026-09-27", summary="s")


def test_escalate_refuses_without_a_recorded_approval(tmp_path):
    with pytest.raises(ToolError, match="approval"):
        actions.escalate(tmp_path / "e.jsonl", finding_id="F-004", reason="SLA breach",
                         approver="", approval_ref="")


def test_escalate_records_the_approver(tmp_path):
    path = tmp_path / "e.jsonl"
    out = actions.escalate(path, finding_id="F-004", reason="SLA breach",
                           approver="lead@example.com", approval_ref="APR-1")
    assert out["escalated"] is True
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["approver"] == "lead@example.com"
    assert rows[0]["approval_ref"] == "APR-1"


def test_auto_approve_labels_itself_as_automatic():
    out = actions.request_human_approval("escalate F-004?", finding_id="F-004", auto_approve=True)
    assert out["approved"] is True
    assert out["mode"] == "auto"
    assert out["approval_ref"]


def test_interactive_approval_reads_the_operator(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    out = actions.request_human_approval("escalate F-004?", finding_id="F-004", auto_approve=False)
    assert out["approved"] is True
    assert out["mode"] == "interactive"


def test_interactive_decline_returns_no_reference(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    out = actions.request_human_approval("escalate F-004?", finding_id="F-004", auto_approve=False)
    assert out["approved"] is False
    assert out["approval_ref"] == ""
