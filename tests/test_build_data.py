import sqlite3

from secops_agent.build_data import build

ASSETS = (
    "asset_id,hostname,owner,criticality,environment,internet_facing\n"
    "A-1,web-gateway-prod,platform-team,high,prod,true\n"
)
HEADER = "finding_id,asset_id,title,cve,cvss,scanner,detected_at,status,days_open\n"


def _write(tmp_path, findings_row: str):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    (data / "assets.csv").write_text(ASSETS, encoding="utf-8")
    (data / "findings.csv").write_text(HEADER + findings_row, encoding="utf-8")
    return data


def test_build_writes_rows(tmp_path):
    data = _write(tmp_path, "F-1,A-1,rce,CVE-2026-1,9.8,nessus,2026-09-20,open,7\n")
    counts = build(data, tmp_path / "secops.db")
    assert counts == {"assets": 1, "findings": 1, "unscored": 0, "orphans": 0}


def test_empty_numeric_cells_become_sql_nulls(tmp_path):
    data = _write(tmp_path, "F-1,A-1,rce,,,nessus,2026-09-20,open,7\n")
    db = tmp_path / "secops.db"
    build(data, db)
    conn = sqlite3.connect(db)
    try:
        cvss, cve = conn.execute("SELECT cvss, cve FROM findings").fetchone()
        assert cvss is None
        assert cve is None
    finally:
        conn.close()


def test_unscored_count_is_reported(tmp_path):
    data = _write(tmp_path, "F-1,A-1,rce,,,nessus,2026-09-20,open,7\n")
    assert build(data, tmp_path / "secops.db")["unscored"] == 1


def test_orphan_asset_references_are_counted(tmp_path):
    data = _write(tmp_path, "F-1,A-999,rce,,,nessus,2026-09-20,open,7\n")
    assert build(data, tmp_path / "secops.db")["orphans"] == 1


def test_rebuild_is_idempotent(tmp_path):
    data = _write(tmp_path, "F-1,A-1,rce,CVE-2026-1,9.8,nessus,2026-09-20,open,7\n")
    db = tmp_path / "secops.db"
    build(data, db)
    counts = build(data, db)
    assert counts["findings"] == 1


def test_real_data_directory_builds(tmp_path):
    from secops_agent.build_data import REPO_ROOT

    counts = build(REPO_ROOT / "data", tmp_path / "secops.db")
    assert counts["findings"] == 12
    assert counts["assets"] == 6
    assert counts["orphans"] == 0
