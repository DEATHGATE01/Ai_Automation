"""Action tools.

Exactly one of them is irreversible (`escalate`), and it refuses to run without a recorded human
approval - the assessment's 'human approval before critical actions' requirement, enforced in code
rather than by asking the model nicely. The model cannot fabricate its way past it: `escalate`
accepts only an `approval_ref` that `request_human_approval` minted in this same run, once, for the
same finding.

(An earlier version checked only that `approver` and `approval_ref` were non-empty strings, which an
independent review correctly called decorative: a model could invent both. The claims in this
docstring and in the README are true of the ledger below, and the tests pin each of them.)
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .base import ToolError

VALID_SEVERITIES = {"critical", "high", "medium", "low"}


class ApprovalLedger:
    """Approvals minted by `request_human_approval` and consumed exactly once by `escalate`.

    One instance per run (`build_registry` creates it), so an approval cannot leak between runs, and
    a reference is removed from the ledger only when it is fully validly used, so it cannot be
    replayed. Rejections leave the reference intact: an honest retry with the right arguments still
    works, a fabricated one never does.
    """

    def __init__(self) -> None:
        self._open: dict[str, dict[str, Any]] = {}

    def mint(self, finding_id: str, approver: str, mode: str) -> str:
        """Record a granted approval and return its single-use reference."""
        ref = _next_id("APR")
        self._open[ref] = {"finding_id": finding_id, "approver": approver, "mode": mode}
        return ref

    def consume(self, approval_ref: str, finding_id: str, approver: str) -> dict[str, Any]:
        """Validate and burn a reference. Raises ToolError, leaving the ledger unchanged."""
        record = self._open.get(approval_ref)
        if record is None:
            raise ToolError(
                f"unknown or already-used approval_ref {approval_ref!r}. An approval_ref must come "
                "from request_human_approval in this run, and each one is valid exactly once."
            )
        approved_for = record["finding_id"]
        if approved_for and finding_id and approved_for != finding_id:
            raise ToolError(
                f"approval_ref {approval_ref} was issued for finding {approved_for}, "
                f"not {finding_id}. Ask for approval for the finding you are escalating."
            )
        if str(record["approver"]).strip().lower() != (approver or "").strip().lower():
            raise ToolError(
                f"approver {approver!r} does not match the approver recorded for {approval_ref}; "
                f"pass the approver exactly as request_human_approval returned it"
            )
        self._open.pop(approval_ref, None)
        return record


def _next_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _append(path: Path, record: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def create_ticket(
    path: Path, finding_id: str, owner: str, severity: str, due_date: str, summary: str
) -> dict[str, Any]:
    """Open a remediation ticket. Validates the severity and the ISO due date before writing."""
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"severity must be one of {sorted(VALID_SEVERITIES)}, got {severity!r}")
    try:
        due = datetime.strptime(due_date, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"due_date must be ISO YYYY-MM-DD, got {due_date!r}") from exc

    record = {
        "ticket_id": _next_id("T"),
        "finding_id": finding_id,
        "owner": owner,
        "severity": severity,
        "due_date": due,
        "summary": summary,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "open",
    }
    _append(path, record)
    return record


def request_human_approval(
    ledger: ApprovalLedger,
    question: str,
    finding_id: str = "",
    auto_approve: bool = False,
    approver: str = "auto",
) -> dict[str, Any]:
    """Ask the operator to approve consequential action; mint a single-use reference if granted.

    In auto-approve runs (used to record transcripts when no human is present) it self-approves and
    labels itself `mode: auto`, so a transcript can never imply a human was there when none was.
    A declined request mints nothing, which is what makes the refusal meaningful downstream.
    """
    if auto_approve:
        return {
            "approved": True,
            "approver": approver,
            "approval_ref": ledger.mint(finding_id, approver, "auto"),
            "mode": "auto",
            "question": question,
            "finding_id": finding_id,
        }

    answer = input(f"\n[APPROVAL REQUIRED] {question} (finding {finding_id}) [y/N]: ")
    approved = answer.strip().lower() in {"y", "yes"}
    return {
        "approved": approved,
        "approver": approver if approved else "",
        "approval_ref": ledger.mint(finding_id, approver, "interactive") if approved else "",
        "mode": "interactive",
        "question": question,
        "finding_id": finding_id,
    }


def escalate(
    ledger: ApprovalLedger,
    path: Path,
    finding_id: str,
    reason: str,
    approver: str,
    approval_ref: str,
) -> dict[str, Any]:
    """Escalate a breached finding. Irreversible, so it is gated on a real approval record."""
    if not approver or not approval_ref:
        raise ToolError(
            "escalation requires a recorded human approval: call request_human_approval first "
            "and pass its approver and approval_ref"
        )
    # The ledger is the source of truth for who approved: the model's copy of `approver` is only
    # checked against it, never written to the audit record on trust.
    approval = ledger.consume(approval_ref, finding_id, approver)
    record = {
        "finding_id": finding_id,
        "reason": reason,
        "approver": approval["approver"],
        "approval_ref": approval_ref,
        "approval_mode": approval["mode"],
        "escalated_at": datetime.now(UTC).isoformat(),
    }
    _append(path, record)
    return {"escalated": True, **record}
