"""The gate must hold through the path the LLM actually uses: build_registry -> call_safe.

The unit tests in test_action_tools.py call `actions.escalate(ledger, ...)` directly, which
bypasses two layers the model never bypasses: the `EscalateArgs` validation inside `call_safe`
and the `build_registry` wiring that decides which ledger and which audit file the gate uses.
If a refactor re-routed either layer around the ledger, the unit tests would still pass. These
tests pin the assembled path: every attack is answered with ok=False and no escalation record,
and the happy path writes to the file `Settings.escalations_path` names.
"""

from pathlib import Path

from secops_agent.config import Settings
from secops_agent.tools import build_registry


class _NoRetriever:
    """search_policy is not under attack here; build_registry only needs a .search."""

    def search(self, query: str, k: int = 4) -> list:
        return []


def _registry(tmp_path: Path) -> tuple:
    # data_dir is the field; db_path/tickets_path/escalations_path are derived properties.
    # Passing the path kwargs instead is silently ignored (extra="ignore") and the audit
    # record lands in the repo's real data/ - the exact trap a CTO probe fell into.
    settings = Settings(_env_file=None, data_dir=tmp_path, auto_approve=True)
    return build_registry(settings, _NoRetriever()), settings


def _escalate_args(**overrides):
    args = {
        "finding_id": "F-009",
        "reason": "breached SLA",
        "approver": "auto",
        "approval_ref": "APR-deadbeef",
    }
    args.update(overrides)
    return args


def _refuse(registry, args, tmp_path, match: str) -> None:
    out = registry.call_safe("escalate", args)
    assert out["ok"] is False, f"gate let the attack through: {out}"
    assert match in str(out["error"])
    assert not (tmp_path / "escalations.jsonl").exists(), "a refused escalation wrote a record"


def test_the_wiring_routes_escalate_through_the_settings_paths(tmp_path):
    registry, _ = _registry(tmp_path)
    approval = registry.call_safe(
        "request_human_approval", {"question": "Escalate F-009?", "finding_id": "F-009"}
    )["result"]
    out = registry.call_safe("escalate", _escalate_args(**{
        "approver": approval["approver"], "approval_ref": approval["approval_ref"],
    }))
    assert out["ok"] is True and out["result"]["escalated"] is True
    # the record is in the file Settings.escalations_path names - nowhere else
    audit_file = tmp_path / "escalations.jsonl"
    assert audit_file.exists()
    lines = audit_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert '"approval_mode": "auto"' in lines[0]
    assert '"approval_question": "Escalate F-009?"' in lines[0]


def test_fabricated_credentials_are_refused_through_the_registry(tmp_path):
    registry, _ = _registry(tmp_path)
    _refuse(registry, _escalate_args(), tmp_path, "unknown or already-used approval_ref")


def test_a_real_ref_cannot_escalate_a_different_finding_through_the_registry(tmp_path):
    registry, _ = _registry(tmp_path)
    approval = registry.call_safe(
        "request_human_approval", {"question": "Escalate F-009?", "finding_id": "F-009"}
    )["result"]
    _refuse(
        registry,
        _escalate_args(finding_id="F-011", approver=approval["approver"],
                       approval_ref=approval["approval_ref"]),
        tmp_path,
        "was issued for finding F-009",
    )


def test_a_spent_ref_cannot_be_replayed_through_the_registry(tmp_path):
    registry, _ = _registry(tmp_path)
    approval = registry.call_safe(
        "request_human_approval", {"question": "Escalate F-009?", "finding_id": "F-009"}
    )["result"]
    kwargs = _escalate_args(approver=approval["approver"], approval_ref=approval["approval_ref"])
    first = registry.call_safe("escalate", kwargs)
    assert first["ok"] is True
    out = registry.call_safe("escalate", kwargs)
    assert out["ok"] is False and "unknown or already-used approval_ref" in str(out["error"])


def test_a_mismatched_approver_is_refused_through_the_registry(tmp_path):
    registry, _ = _registry(tmp_path)
    approval = registry.call_safe(
        "request_human_approval", {"question": "Escalate F-012?", "finding_id": "F-012"}
    )["result"]
    _refuse(
        registry,
        _escalate_args(finding_id="F-012", approver="someone-else",
                       approval_ref=approval["approval_ref"]),
        tmp_path,
        "does not match the approver",
    )


def test_blank_credentials_never_reach_the_ledger(tmp_path):
    # Schema layer: EscalateArgs requires both strings, so call_safe rejects before the ledger
    # is consulted - the omission attack is stopped one layer earlier than in the unit tests.
    registry, _ = _registry(tmp_path)
    _refuse(registry, _escalate_args(approver="", approval_ref="APR-1"), tmp_path, "approver")
    _refuse(registry, _escalate_args(approver="auto", approval_ref=""), tmp_path, "approval_ref")
