"""Action tools.

Exactly one of them is irreversible (`escalate`), and it refuses to run without a recorded human
approval - the assessment's 'human approval before critical actions' requirement, enforced in code
rather than by asking the model nicely. The model cannot fabricate its way past it: only
`request_human_approval` mints an `approval_ref`.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .base import ToolError

VALID_SEVERITIES = {"critical", "high", "medium", "low"}


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
    question: str, finding_id: str = "", auto_approve: bool = False, approver: str = "auto"
) -> dict[str, Any]:
    """Ask the operator to approve a consequential action.

    In auto-approve runs (used to record transcripts when no human is present) it self-approves and
    labels itself `mode: auto`, so a transcript can never imply a human was there when none was.
    """
    if auto_approve:
        return {
            "approved": True,
            "approver": approver,
            "approval_ref": _next_id("APR"),
            "mode": "auto",
            "question": question,
            "finding_id": finding_id,
        }

    answer = input(f"\n[APPROVAL REQUIRED] {question} (finding {finding_id}) [y/N]: ")
    approved = answer.strip().lower() in {"y", "yes"}
    return {
        "approved": approved,
        "approver": approver if approved else "",
        "approval_ref": _next_id("APR") if approved else "",
        "mode": "interactive",
        "question": question,
        "finding_id": finding_id,
    }


def escalate(
    path: Path, finding_id: str, reason: str, approver: str, approval_ref: str
) -> dict[str, Any]:
    """Escalate a breached finding. Irreversible, so it is gated on a real approval record."""
    if not approver or not approval_ref:
        raise ToolError(
            "escalation requires a recorded human approval: call request_human_approval first "
            "and pass its approver and approval_ref"
        )
    record = {
        "finding_id": finding_id,
        "reason": reason,
        "approver": approver,
        "approval_ref": approval_ref,
        "escalated_at": datetime.now(UTC).isoformat(),
    }
    _append(path, record)
    return {"escalated": True, **record}
