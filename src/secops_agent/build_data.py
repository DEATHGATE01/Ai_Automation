"""Build the SQLite knowledge base from the CSV files in data/.

Kept as a module rather than a loose script so it is importable and testable. `python -m
secops_agent.build_data` is the entry point; `make data` wraps it.

An empty CVSS cell becomes a real SQL NULL, not an empty string. That distinction is load-bearing:
"no score available" must be visibly different from "score of 0", because the rubric tells the agent
to treat an unscored finding as needs_review rather than as harmless.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

from .config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]

ASSET_COLS = ["asset_id", "hostname", "owner", "criticality", "environment", "internet_facing"]
FINDING_COLS = [
    "finding_id",
    "asset_id",
    "title",
    "cve",
    "cvss",
    "scanner",
    "detected_at",
    "status",
    "days_open",
]

SCHEMA = """
DROP TABLE IF EXISTS findings;
DROP TABLE IF EXISTS assets;

CREATE TABLE assets (
    asset_id        TEXT PRIMARY KEY,
    hostname        TEXT NOT NULL,
    owner           TEXT NOT NULL,
    criticality     TEXT NOT NULL,
    environment     TEXT NOT NULL,
    internet_facing TEXT NOT NULL
);

CREATE TABLE findings (
    finding_id  TEXT PRIMARY KEY,
    asset_id    TEXT NOT NULL REFERENCES assets(asset_id),
    title       TEXT NOT NULL,
    cve         TEXT,
    cvss        REAL,
    scanner     TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    status      TEXT NOT NULL,
    days_open   INTEGER NOT NULL
);

CREATE INDEX idx_findings_asset ON findings(asset_id);
"""


def _blank_to_none(value: str) -> str | None:
    value = (value or "").strip()
    return value or None


def _finding_row(row: dict[str, str]) -> tuple:
    cvss_text = (row.get("cvss") or "").strip()
    return (
        row["finding_id"],
        row["asset_id"],
        row["title"],
        _blank_to_none(row.get("cve", "")),
        float(cvss_text) if cvss_text else None,
        row["scanner"],
        row["detected_at"],
        row["status"],
        int(row["days_open"]),
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"missing input file: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build(data_dir: Path, db_path: Path) -> dict[str, int]:
    assets = _read_csv(Path(data_dir) / "assets.csv")
    findings = _read_csv(Path(data_dir) / "findings.csv")

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO assets VALUES (?,?,?,?,?,?)",
            [tuple(row[col] for col in ASSET_COLS) for row in assets],
        )
        conn.executemany(
            "INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?)",
            [_finding_row(row) for row in findings],
        )
        conn.commit()
        orphans = conn.execute(
            "SELECT COUNT(*) FROM findings f LEFT JOIN assets a ON f.asset_id = a.asset_id"
            " WHERE a.asset_id IS NULL"
        ).fetchone()[0]
        unscored = conn.execute("SELECT COUNT(*) FROM findings WHERE cvss IS NULL").fetchone()[0]
    finally:
        conn.close()

    return {
        "assets": len(assets),
        "findings": len(findings),
        "unscored": int(unscored),
        "orphans": int(orphans),
    }


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        prog="python -m secops_agent.build_data",
        description="Rebuild the SQLite knowledge base from the CSV files in data/.",
    )
    parser.add_argument("--data-dir", type=Path, default=settings.data_dir)
    parser.add_argument("--db", type=Path, default=settings.db_path)
    args = parser.parse_args(argv)

    counts = build(args.data_dir, args.db)
    print(f"wrote {args.db}")
    print(f"assets:   {counts['assets']}")
    print(f"findings: {counts['findings']}")
    print(f"unscored findings (cvss NULL): {counts['unscored']}")
    print(f"orphan asset references: {counts['orphans']}")
    if counts["orphans"]:
        print("ERROR: findings reference assets that do not exist", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
