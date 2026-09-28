import sqlite3

import pytest

from secops_agent.tools import knowledge
from secops_agent.tools.base import ToolError


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "secops.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE assets (asset_id TEXT PRIMARY KEY, hostname TEXT, owner TEXT,"
        " criticality TEXT, environment TEXT, internet_facing TEXT)"
    )
    conn.execute(
        "CREATE TABLE findings (finding_id TEXT PRIMARY KEY, asset_id TEXT,"
        " title TEXT, cve TEXT,"
        " cvss REAL, scanner TEXT, detected_at TEXT, status TEXT, days_open INTEGER)"
    )
    conn.executemany("INSERT INTO assets VALUES (?,?,?,?,?,?)", [
        ("A-001", "web-gateway-prod", "platform-team", "high", "prod", "true"),
        ("A-004", "build-sandbox", "dev-infra", "low", "dev", "false"),
        ("A-003", "core-db-prod", "data-platform", "critical", "prod", "false"),
    ])
    conn.executemany("INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?)", [
        ("F-001", "A-001", "RCE in web framework", "CVE-2026-1188", 9.8, "nessus", "2026-09-20",
         "open", 7),
        ("F-003", "A-003", "Missing security patch", None, None, "nessus", "2026-07-01",
         "open", 88),
        ("F-010", "A-004", "Missing headers", None, None, "burp", "2026-09-24", "closed", 3),
    ])
    conn.commit()
    conn.close()
    # The CVSS bands come from the policy document, so a db without a rubric next to it cannot band
    # findings at all. The fixture writes the real rubric's rules.
    policies = tmp_path / "policies"
    policies.mkdir(exist_ok=True)
    (policies / "severity_rubric.md").write_text(
        "## CVSS bands\n"
        "CVSS 9.0-10.0 is critical. CVSS 7.0-8.9 is high. CVSS 4.0-6.9 is medium. "
        "CVSS 0.1-3.9 is low.\n",
        encoding="utf-8",
    )
    return path


def test_the_bands_are_read_from_the_policy_document(db, tmp_path):
    # Review finding: the thresholds were a constant in this module while the policy corpus claimed
    # to own them, so a policy edit changed nothing. Rewriting the rubric must change behaviour.
    (tmp_path / "policies" / "severity_rubric.md").write_text(
        "## CVSS bands\nCVSS 6.0-10.0 is critical. CVSS 0.0-5.9 is low.\n", encoding="utf-8"
    )
    row = knowledge.get_finding(db, "F-001")  # cvss 9.8
    assert row["cvss_band"] == "critical"
    # a 6.5 finding is 'medium' under the shipped rubric and 'critical' under this one
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?)",
            ("F-099", "A-003", "mid", None, 6.5, "nessus", "2026-09-01", "open", 30),
        )
        conn.commit()
    bands = knowledge.load_severity_bands(tmp_path / "policies" / "severity_rubric.md")
    assert knowledge._cvss_band(6.5, bands) == "critical"
    assert knowledge.get_finding(db, "F-099")["cvss_band"] == "critical"


def test_a_missing_rubric_is_a_loud_error_not_a_fallback(db, tmp_path):
    # No baked-in thresholds: a silent fallback would be the hardcoded-rule bug wearing a hat.
    with pytest.raises(ToolError, match="severity rubric missing"):
        knowledge.list_findings(db, rubric_path=tmp_path / "nope.md")


def test_overlapping_bands_are_rejected(db, tmp_path):
    # A malformed policy must fail loudly rather than let document order silently decide.
    (tmp_path / "policies" / "severity_rubric.md").write_text(
        "## CVSS bands\nCVSS 0.0-10.0 is critical. CVSS 9.0-10.0 is low.\n", encoding="utf-8"
    )
    with pytest.raises(ToolError, match="overlap"):
        knowledge.list_findings(db)


def test_an_inverted_band_is_rejected(db, tmp_path):
    (tmp_path / "policies" / "severity_rubric.md").write_text(
        "## CVSS bands\nCVSS 9.0-1.0 is critical.\n", encoding="utf-8"
    )
    with pytest.raises(ToolError, match="lower bound"):
        knowledge.list_findings(db)


def test_a_zero_cvss_score_is_not_silently_called_low(db):
    # Review finding: the code floored the 'low' band at 0.0, but the rubric defines low as
    # 0.1-3.9 and says nothing about 0.0. A 0.0 score must surface as needs_review, exactly like an
    # unscored finding, rather than being filed as 'low'.
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?)",
                     ("F-098", "A-003", "zero", None, 0.0, "nessus", "2026-09-01", "open", 30))
        conn.commit()
    assert knowledge.get_finding(db, "F-098")["cvss_band"] == "needs_review"


def test_list_findings_filters_by_severity(db):
    rows = knowledge.list_findings(db, severity="critical")
    assert [r["finding_id"] for r in rows] == ["F-001"]


def test_list_findings_fails_loudly_on_unknown_asset_id(db):
    # A filter on an entity that does not exist must be a 404-shaped ToolError, not a
    # silent empty list: "no matches" and "no such asset" are different facts, and the
    # model read a silent [] as 'no open findings' in live run 3.
    with pytest.raises(ToolError) as excinfo:
        knowledge.list_findings(db, asset_id="A-DB01")
    assert "no asset with id 'A-DB01'" in str(excinfo.value)


def test_list_findings_joins_asset_context(db):
    rows = knowledge.list_findings(db, asset_id="A-001")
    assert rows[0]["owner"] == "platform-team"
    assert rows[0]["environment"] == "prod"


def test_list_findings_excludes_closed_by_default(db):
    assert all(r["status"] != "closed" for r in knowledge.list_findings(db))


def test_list_findings_can_include_closed(db):
    rows = knowledge.list_findings(db, status="closed")
    assert [r["finding_id"] for r in rows] == ["F-010"]


def test_get_finding_returns_missing_cvss_as_null(db):
    row = knowledge.get_finding(db, "F-003")
    assert row["cvss"] is None
    assert row["cve"] is None
    assert row["cvss_band"] == "needs_review"


def test_get_asset_reports_unknown_asset(db):
    with pytest.raises(ToolError, match="A-999"):
        knowledge.get_asset(db, "A-999")


def test_severity_filter_is_case_insensitive(db):
    assert knowledge.list_findings(db, severity="CRITICAL")[0]["finding_id"] == "F-001"


def test_cvss_band_is_raw_and_ignores_business_criticality(db):
    """The tool reports the CVSS band as a fact. Adjusting for asset criticality is a policy
    judgement, and policy judgements are the LLM's job, not the tool's."""
    row = knowledge.get_finding(db, "F-001")  # cvss 9.8 on a 'high' criticality asset
    assert row["cvss_band"] == "critical"


def test_missing_database_raises_a_helpful_error(tmp_path):
    with pytest.raises(ToolError, match=r"run `uv run python -m secops_agent\.build_data`"):
        knowledge.list_findings(tmp_path / "nope.db")
