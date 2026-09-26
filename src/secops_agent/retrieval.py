"""Policy-document retrieval behind a small protocol.

Two implementations:
  * KeywordRetriever  - pure stdlib, deterministic, used by every test and as the default.
  * ChromaRetriever   - real embedding-based RAG, opt-in via SECOPS_RETRIEVER=chroma.
Having both is deliberate: the tests and the demo run stay fast and network-free, and the tool
degrades gracefully if the local embedding model is unavailable.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Protocol

from .config import Settings

_TOKEN_RE = re.compile(r"[a-z0-9_]+")
_STOP = {
    "the", "a", "an", "is", "are", "of", "to", "in", "on", "for", "and", "or", "if", "it",
    "this", "that", "with", "should", "must", "be", "do", "does", "how", "what", "when",
    "which", "i", "we", "you", "my", "our", "its", "as", "at", "by", "from", "any",
}


def _norm(token: str) -> str:
    """Crude plural stripping so 'findings' and 'finding' are the same term.

    Deliberately minimal: the goal is consistent matching, not linguistics.
    """
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    return [_norm(t) for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP]


def chunk_markdown(text: str, source: str) -> list[dict[str, Any]]:
    """Split on '## ' headings. A heading starts a new chunk and stays attached to its body."""
    chunks: list[dict[str, Any]] = []
    current: list[str] = []

    def flush() -> None:
        body = "\n".join(current).strip()
        if body:
            chunks.append({"text": body, "source": source})

    for line in text.splitlines():
        if line.startswith("## ") and current:
            flush()
            current = [line]
        else:
            current.append(line)
    flush()
    return chunks


class Retriever(Protocol):
    def search(self, query: str, k: int = 4) -> list[dict[str, Any]]: ...


class KeywordRetriever:
    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self._chunks = chunks

    def search(self, query: str, k: int = 4) -> list[dict[str, Any]]:
        q = set(tokenize(query))
        if not q:
            return []
        scored: list[tuple[float, dict[str, Any]]] = []
        for chunk in self._chunks:
            body = set(tokenize(chunk["text"]))
            overlap = q & body
            if not overlap:
                continue
            scored.append((len(overlap) / len(q), chunk))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            {**chunk, "score": round(score, 4), "retriever": "keyword"}
            for score, chunk in scored[:k]
        ]


class ChromaRetriever:
    """Embedding search over policy chunks, persisted under data/chroma."""

    COLLECTION = "secops_policies"

    def __init__(self, chunks: list[dict[str, Any]], persist_dir: Path) -> None:
        import chromadb  # imported lazily so tests never touch it

        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(name=self.COLLECTION)
        if self._collection.count() < len(chunks):
            self._collection.upsert(
                ids=[f"{c['source']}::{i}" for i, c in enumerate(chunks)],
                documents=[c["text"] for c in chunks],
                metadatas=[{"source": c["source"]} for c in chunks],
            )

    def search(self, query: str, k: int = 4) -> list[dict[str, Any]]:
        res = self._collection.query(query_texts=[query], n_results=k)
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        out = []
        for text, meta, dist in zip(docs, metas, dists, strict=False):
            out.append(
                {
                    "text": text,
                    "source": (meta or {}).get("source", "unknown"),
                    "score": round(1.0 - float(dist), 4),
                    "retriever": "chroma",
                }
            )
        return out


def load_policy_chunks(policies_dir: Path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for path in sorted(Path(policies_dir).glob("*.md")):
        chunks.extend(chunk_markdown(path.read_text(encoding="utf-8"), source=path.name))
    return chunks


def build_retriever(settings: Settings) -> Retriever:
    """Keyword by default: deterministic, offline, no model download.

    SECOPS_RETRIEVER=chroma opts into real embeddings. Chroma is the upgrade path, not the
    default, because a first run that has to download a model is a demo that can fail on stage.
    """
    chunks = load_policy_chunks(settings.data_dir / "policies")
    if settings.retriever == "chroma":
        try:
            return ChromaRetriever(chunks, persist_dir=settings.chroma_dir)
        except Exception as exc:  # noqa: BLE001 - degrade instead of crashing the run
            print(f"chroma unavailable ({exc}); falling back to keyword retrieval", file=sys.stderr)
    return KeywordRetriever(chunks)
