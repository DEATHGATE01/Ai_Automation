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
    return path


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
    with pytest.raises(ToolError, match="run `make data`"):
        knowledge.list_findings(tmp_path / "nope.db")
