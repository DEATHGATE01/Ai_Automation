"""Read-only tools over the findings register and asset inventory (SQLite).

These tools report FACTS - the raw CVSS band, the asset's owner, the days a finding has been open.
They deliberately do not apply policy: the business-criticality adjustment and the SLA arithmetic
are policy judgements, and every judgement in this agent is made by the LLM and validated against
the policy corpus. A tool that quietly applied the policy would be the hardcoded rule engine the
assessment forbids.

The one policy value these tools do use - the CVSS band boundaries - is read out of
`data/policies/severity_rubric.md` at call time rather than hardcoded here, so the document stays
the single source of truth. (It was a module constant until an independent review pointed out that
a policy edit then changed nothing.)
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .base import ToolError

_RUBRIC_BAND = re.compile(
    r"CVSS\s+(\d+(?:\.\d+)?)\s*[-\u2013]\s*(\d+(?:\.\d+)?)\s+is\s+([a-z_]+)", re.IGNORECASE
)


def load_severity_bands(rubric_path: Path) -> tuple[tuple[str, float, float], ...]:
    """Parse `(name, low, high)` CVSS bands out of the severity rubric itself.

    There is deliberately no fallback: a missing or unparseable rubric is a loud error, because a
    silent fallback to baked-in numbers is exactly the hardcoded-rule bug this avoids.
    """
    path = Path(rubric_path)
    if not path.exists():
        raise ToolError(
            f"severity rubric missing at {path}; the policy corpus is the source of truth and "
            "`make data` restores it"
        )
    bands = tuple(
        (name.lower(), float(low), float(high))
        for low, high, name in _RUBRIC_BAND.findall(path.read_text(encoding="utf-8"))
    )
    if not bands:
        raise ToolError(
            f"no CVSS bands found in {path}; expected a line like 'CVSS 9.0-10.0 is critical'"
        )
    return bands


def _default_rubric_path(db_path: Path) -> Path:
    return Path(db_path).parent / "policies" / "severity_rubric.md"


def _cvss_band(cvss: float | None, bands: tuple[tuple[str, float, float], ...]) -> str:
    if cvss is None:
        return "needs_review"
    score = float(cvss)
    for name, low, high in bands:
        if low <= score <= high:
            return name
    # A score the rubric does not place in any band - 0.0, say, since the rubric defines low as
    # 0.1-3.9 and says nothing about 0.0 - is reported as needing review, never guessed at.
    return "needs_review"


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
    rubric_path: Path | None = None,
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

    bands = load_severity_bands(rubric_path or _default_rubric_path(db_path))
    for row in rows:
        row["cvss_band"] = _cvss_band(row["cvss"], bands)

    if severity:
        wanted = severity.strip().lower()
        rows = [r for r in rows if r["cvss_band"] == wanted]
    return rows


def get_finding(
    db_path: Path, finding_id: str, rubric_path: Path | None = None
) -> dict[str, Any]:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT f.*, a.hostname, a.owner, a.criticality, a.environment, a.internet_facing "
            "FROM findings f JOIN assets a ON a.asset_id = f.asset_id WHERE f.finding_id = ?",
            (finding_id,),
        ).fetchone()
    if row is None:
        raise ToolError(f"no finding with id {finding_id}")
    out = dict(row)
    bands = load_severity_bands(rubric_path or _default_rubric_path(db_path))
    out["cvss_band"] = _cvss_band(out["cvss"], bands)
    return out


def get_asset(db_path: Path, asset_id: str) -> dict[str, Any]:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
    if row is None:
        raise ToolError(f"no asset with id {asset_id}")
    return dict(row)
