"""Read-only tools over the findings register and asset inventory (SQLite).

These tools report FACTS - the raw CVSS band, the asset's owner, the days a finding has been open.
They deliberately do not apply policy: the business-criticality adjustment and the SLA arithmetic
are policy judgements, and every judgement in this agent is made by the LLM and validated against
the policy corpus. A tool that quietly applied the policy would be the hardcoded rule engine the
assessment forbids.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .base import ToolError

_SEVERITY_BANDS = (("critical", 9.0), ("high", 7.0), ("medium", 4.0), ("low", 0.0))


@contextmanager
def _connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    if not Path(db_path).exists():
        raise ToolError(f"knowledge base missing at {db_path}; run `make data`")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _cvss_band(cvss: float | None) -> str:
    if cvss is None:
        return "needs_review"
    for name, floor in _SEVERITY_BANDS:
        if float(cvss) >= floor:
            return name
    return "needs_review"


def _known_asset_ids(db_path: Path) -> list[str]:
    """The real asset ids, surfaced in the unknown-entity error so the model can self-correct."""
    with _connect(db_path) as conn:
        return [r[0] for r in conn.execute("SELECT asset_id FROM assets ORDER BY asset_id")]


def list_findings(
    db_path: Path,
    severity: str | None = None,
    asset_id: str | None = None,
    status: str | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Return findings joined to their asset. status defaults to every non-closed finding."""
    where: list[str] = []
    params: list[Any] = []
    if status:
        where.append("LOWER(f.status) = ?")
        params.append(status.lower())
    else:
        where.append("f.status != 'closed'")
    if asset_id:
        where.append("f.asset_id = ?")
        params.append(asset_id)

    if asset_id is not None:
        with _connect(db_path) as conn:
            exists = conn.execute(
                "SELECT 1 FROM assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
        if exists is None:
            known = _known_asset_ids(db_path)
            raise ToolError(
                f"no asset with id {asset_id!r} exists in the inventory; "
                f"known asset ids: {known}. Call get_asset or re-run list_findings without "
                "the asset filter instead of concluding from an assumption."
            )

    sql = (
        "SELECT f.*, a.hostname, a.owner, a.criticality, a.environment, a.internet_facing "
        "FROM findings f JOIN assets a ON a.asset_id = f.asset_id"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY COALESCE(f.cvss, 0) DESC, f.days_open DESC LIMIT ?"
    params.append(int(limit))

    with _connect(db_path) as conn:
        rows = [dict(r) for r in conn.execute(sql, params)]

    for row in rows:
        row["cvss_band"] = _cvss_band(row["cvss"])

    if severity:
        wanted = severity.strip().lower()
        rows = [r for r in rows if r["cvss_band"] == wanted]
    return rows


def get_finding(db_path: Path, finding_id: str) -> dict[str, Any]:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT f.*, a.hostname, a.owner, a.criticality, a.environment, a.internet_facing "
            "FROM findings f JOIN assets a ON a.asset_id = f.asset_id WHERE f.finding_id = ?",
            (finding_id,),
        ).fetchone()
    if row is None:
        raise ToolError(f"no finding with id {finding_id}")
    out = dict(row)
    out["cvss_band"] = _cvss_band(out["cvss"])
    return out


def get_asset(db_path: Path, asset_id: str) -> dict[str, Any]:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
    if row is None:
        raise ToolError(f"no asset with id {asset_id}")
    return dict(row)
