"""Long-term memory of past runs, persisted as a small JSON list.

Deliberately simple: token-overlap ranking, no embeddings. The point is that the agent can see what
it did before, not that recall is clever.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .retrieval import tokenize


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._items: list[dict[str, Any]] = self._load()

    def _load(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []  # a corrupt or missing store must never break a run

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._items, indent=2), encoding="utf-8")

    def record(self, run_id: str, *, goal: str, summary: str) -> None:
        self._items.append(
            {
                "run_id": run_id,
                "goal": goal,
                "summary": summary,
                "at": datetime.now(UTC).isoformat(),
            }
        )
        self._save()

    def recall(self, goal: str, limit: int = 3) -> list[dict[str, Any]]:
        query = set(tokenize(goal))
        if not query:
            return []
        scored: list[tuple[float, dict[str, Any]]] = []
        for item in self._items:
            overlap = query & set(tokenize(item.get("goal", "")))
            if overlap:
                scored.append((len(overlap) / len(query), item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:limit]]
