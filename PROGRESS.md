# PROGRESS.md

## Current Focus
Phase 9 — live LLM runs. Phases 0-8 are complete, committed, and green.

## In Progress
- Live run transcripts (the submission needs 2-3). BLOCKED on a usable LLM backend.

## Blocked
- No LLM backend for the graded runs. Local Ollama has only `codellama:7b-instruct`: it has a
  4096-token context, so the planner prompt + full tool schema overflows it and it returns
  unparseable output (both planner attempts failed in the first live run; the fallback plan then
  engaged correctly, but that is not a transcript worth submitting). It is also ~210 s per call on
  this CPU, so a 12-step run would take ~40 minutes. `AGENTROUTER_API_KEY` is exported in the shell
  but the endpoint returns `unauthorized client detected`.
  Needed: either a Groq/OpenAI-compatible key (fast, reliable) or a bigger local model
  (`qwen2.5:7b-instruct`, 32K context — slow but keyless).

## Done (most recent first)
- 2026-09-27 — Phases 4-8 complete: trace, memory, 7 tools, agent loop, report, data builder, CLI.
  96 tests pass, ruff clean, mypy clean. Committed on branch `build/v1`.
- 2026-09-27 — docs/: architecture.html (layout verified: 0 text/box overlaps, no overflow),
  write-up.md, decisions.md, README.md.
- 2026-09-27 — `make data` builds the SQLite KB: 6 assets, 12 findings, 4 unscored, 0 orphan refs.

## Active Claims (do not edit — in progress in another session)
- whole repo — initial build, since 2026-09-27

## Open Decisions / Questions
- Is the 3-option .docx or the 2-track form the real gate? Email pending to HR; building the superset.
- Confirm submission deadline (48h vs 5-7 days).
- Which LLM model produces the submitted transcripts? Must be named in the form and write-up.
