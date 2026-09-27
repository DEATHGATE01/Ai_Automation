import json
from pathlib import Path

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


def test_escalate_refuses_without_a_recorded_approval():
    ledger = actions.ApprovalLedger()
    with pytest.raises(ToolError, match="approval"):
        actions.escalate(ledger, Path("e.jsonl"), finding_id="F-004", reason="SLA breach",
                         approver="", approval_ref="")


def test_escalate_rejects_a_fabricated_reference(tmp_path):
    # The bypass an independent reviewer found: well-formed but invented credentials used to be
    # accepted, because escalate only checked that the two strings were non-empty.
    ledger = actions.ApprovalLedger()
    with pytest.raises(ToolError, match="approval_ref"):
        actions.escalate(ledger, tmp_path / "e.jsonl", finding_id="F-004", reason="SLA breach",
                         approver="nobody@nowhere", approval_ref="APR-deadbeef")
    assert not (tmp_path / "e.jsonl").exists()


def test_escalate_accepts_a_reference_that_was_actually_minted(tmp_path):
    ledger = actions.ApprovalLedger()
    path = tmp_path / "e.jsonl"
    approval = actions.request_human_approval(ledger, "escalate F-004?", finding_id="F-004",
                                              auto_approve=True)
    out = actions.escalate(ledger, path, finding_id="F-004", reason="SLA breach",
                           approver=approval["approver"],
                           approval_ref=approval["approval_ref"])
    assert out["escalated"] is True
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    # the approver is taken from the ledger, not from the model's argument
    assert rows[0]["approver"] == "auto"
    assert rows[0]["approval_ref"] == approval["approval_ref"]


def test_an_approval_ref_can_only_be_used_once(tmp_path):
    ledger = actions.ApprovalLedger()
    approval = actions.request_human_approval(ledger, "q", finding_id="F-004", auto_approve=True)
    kwargs = dict(finding_id="F-004", reason="r", approver=approval["approver"],
                  approval_ref=approval["approval_ref"])
    actions.escalate(ledger, tmp_path / "e.jsonl", **kwargs)
    with pytest.raises(ToolError, match="already-used"):
        actions.escalate(ledger, tmp_path / "e.jsonl", **kwargs)


def test_an_approval_for_one_finding_cannot_escalate_another(tmp_path):
    ledger = actions.ApprovalLedger()
    approval = actions.request_human_approval(ledger, "q", finding_id="F-004", auto_approve=True)
    with pytest.raises(ToolError, match="issued for finding F-004"):
        actions.escalate(ledger, tmp_path / "e.jsonl", finding_id="F-009", reason="r",
                         approver=approval["approver"],
                         approval_ref=approval["approval_ref"])


def test_a_wrong_approver_is_rejected_without_burning_the_reference(tmp_path):
    ledger = actions.ApprovalLedger()
    approval = actions.request_human_approval(ledger, "q", finding_id="F-004", auto_approve=True)
    with pytest.raises(ToolError, match="does not match the approver"):
        actions.escalate(ledger, tmp_path / "e.jsonl", finding_id="F-004", reason="r",
                         approver="attacker", approval_ref=approval["approval_ref"])
    # an honest retry with the correct approver must still work
    out = actions.escalate(ledger, tmp_path / "e.jsonl", finding_id="F-004", reason="r",
                           approver=approval["approver"],
                           approval_ref=approval["approval_ref"])
    assert out["escalated"] is True


def test_ledgers_do_not_share_approvals(tmp_path):
    # One ledger per run: an approval minted in one run must not work in another.
    first, second = actions.ApprovalLedger(), actions.ApprovalLedger()
    approval = actions.request_human_approval(first, "q", finding_id="F-004", auto_approve=True)
    with pytest.raises(ToolError, match="approval_ref"):
        actions.escalate(second, tmp_path / "e.jsonl", finding_id="F-004", reason="r",
                         approver=approval["approver"],
                         approval_ref=approval["approval_ref"])


def test_auto_approve_labels_itself_as_automatic():
    out = actions.request_human_approval(actions.ApprovalLedger(), "escalate F-004?",
                                         finding_id="F-004", auto_approve=True)
    assert out["approved"] is True
    assert out["mode"] == "auto"
    assert out["approval_ref"]


def test_interactive_approval_reads_the_operator(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    out = actions.request_human_approval(actions.ApprovalLedger(), "escalate F-004?",
                                         finding_id="F-004", auto_approve=False)
    assert out["approved"] is True
    assert out["mode"] == "interactive"


def test_interactive_decline_returns_no_reference(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    out = actions.request_human_approval(actions.ApprovalLedger(), "escalate F-004?",
                                         finding_id="F-004", auto_approve=False)
    assert out["approved"] is False
    assert out["approval_ref"] == ""


def test_a_declined_approval_cannot_escalate(tmp_path):
    ledger = actions.ApprovalLedger()
    with pytest.raises(ToolError, match="approval"):
        actions.escalate(ledger, tmp_path / "e.jsonl", finding_id="F-004", reason="r",
                         approver="", approval_ref="")
