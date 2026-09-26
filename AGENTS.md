# AGENTS.md — secops-agent

Agentic AI Engineer Intern take-home (Xiarch Bharat). Read PROGRESS.md before editing.

## What this is
An autonomous security-operations triage agent: plan -> act -> observe -> report, over a synthetic
internal knowledge base. Python 3.12, uv, pytest, ruff.

## Non-negotiables
- Every decision is made by the LLM and validated by Pydantic. No if/else rule engines, no hardcoded
  answers. (Assessment constraint: "no hardcoded responses, predefined rules, or static outputs".)
- All code is original work. No file copied from a public repo. `data/` is synthetic and must be
  labelled as such everywhere it surfaces.
- TDD: write the failing test, run it, see it fail, implement, run it, see it pass, commit.
- One logical change per commit. Do not commit to `main`; work on `build/v1`.
- Secrets live in `.env` only (gitignored). Never print, commit or paste a key.
- `tests/` must pass offline: no test may make a network call. Use `ScriptedLLM`.

## Commands
- `make setup` — uv sync
- `make data` — build SQLite + retriever index from data/
- `make test` — pytest -q
- `make lint` — ruff check + mypy
- `make run GOAL="..."` — run the agent
