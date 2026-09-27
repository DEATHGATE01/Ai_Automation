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

import getpass
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .base import ToolError

VALID_SEVERITIES = {"critical", "high", "medium", "low"}


def _interactive_approver() -> str:
    """Who is at the keyboard, for the audit record.

    Without this, an interactive approval was recorded as approver "auto" alongside
    `approval_mode: interactive` - a record that cannot say who approved. SECOPS_APPROVER lets an
    operator name themselves explicitly; otherwise the OS login is used.
    """
    for var in ("SECOPS_APPROVER", "USER", "USERNAME", "LOGNAME"):
        value = os.environ.get(var, "").strip()
        if value:
            return value
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - identity lookup can fail on locked-down Windows setups
        return "unknown-interactive-approver"


class ApprovalLedger:
    """Approvals minted by `request_human_approval` and consumed exactly once by `escalate`.

    One instance per run (`build_registry` creates it), so an approval cannot leak between runs, and
    a reference is removed from the ledger only when it is fully validly used, so it cannot be
    replayed. Rejections leave the reference intact: an honest retry with the right arguments still
    works, a fabricated one never does.
    """

    def __init__(self) -> None:
        self._open: dict[str, dict[str, Any]] = {}

    def mint(self, finding_id: str, approver: str, mode: str, question: str) -> str:
        """Record a granted approval and return its single-use reference."""
        ref = _next_id("APR")
        self._open[ref] = {
            "finding_id": finding_id,
            "approver": approver,
            "mode": mode,
            "question": question,
        }
        return ref

    def consume(self, approval_ref: str, finding_id: str, approver: str) -> dict[str, Any]:
        """Validate and burn a reference. Raises ToolError, leaving the ledger unchanged."""
        record = self._open.get(approval_ref)
        if record is None:
            raise ToolError(
                f"unknown or already-used approval_ref {approval_ref!r}. An approval_ref must come "
                "from request_human_approval in this run, and each one is valid exactly once."
            )
        target = str(finding_id or "").strip()
        if not target:
            raise ToolError(
                "escalate needs the finding id it is escalating: an unnamed target cannot be "
                "checked against the approval"
            )
        # Unconditional: an approval is only ever valid for the finding it names. An earlier version
        # wrote `if approved_for and finding_id and ...`, so a blank on either side skipped the
        # check entirely - and blank was the default, so a generic "yes" was spendable on anything.
        if record["finding_id"] != target:
            raise ToolError(
                f"approval_ref {approval_ref} was issued for finding {record['finding_id']}, "
                f"not {target}. Ask for approval for the finding you are escalating."
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
    finding_id: str,
    auto_approve: bool = False,
    approver: str | None = None,
) -> dict[str, Any]:
    """Ask the operator to approve an action; mint a single-use reference if granted.

    In auto-approve runs (used to record transcripts when no human is present) it self-approves and
    labels itself `mode: auto`, so a transcript can never imply a human was there when none was.
    A declined request mints nothing, which is what makes the refusal meaningful downstream.

    The finding is mandatory: an approval that does not name what it approves can be spent on
    anything, which defeats the point of approving it.
    """
    if not str(finding_id or "").strip():
        raise ToolError(
            "request_human_approval needs the finding it concerns. An approval that does not name "
            "its finding could be spent on any of them."
        )
    who = (approver or ("auto" if auto_approve else _interactive_approver())).strip()
    if auto_approve:
        return {
            "approved": True,
            "approver": who,
            "approval_ref": ledger.mint(finding_id, who, "auto", question),
            "mode": "auto",
            "question": question,
            "finding_id": finding_id,
        }

    answer = input(f"\n[APPROVAL REQUIRED] {question} (finding {finding_id}) [y/N]: ")
    approved = answer.strip().lower() in {"y", "yes"}
    return {
        "approved": approved,
        "approver": who if approved else "",
        "approval_ref": (
            ledger.mint(finding_id, who, "interactive", question) if approved else ""
        ),
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
        # what the human actually agreed to, so an auditor can compare it with what was escalated
        "approval_question": approval["question"],
        "escalated_at": datetime.now(UTC).isoformat(),
    }
    _append(path, record)
    return {"escalated": True, **record}
