# PROGRESS.md

## Current Focus
COMPLETE. The take-home submission is built, tested, run live, and committed on `build/v1`.

## Done (most recent first)
- 2026-09-27 — Phase 9 LIVE RUNS on Groq `openai/gpt-oss-120b` (key merged from the user's root
  .env into `secops-agent/.env`, gitignored, never displayed):
  - Run 1 `run-20260927-152446-844613`: SLA breaches — found F-012 (critical, 200d open vs 7d
    window), ticket T-741cfa2d, escalation REFUSED without human approval (gate works live).
  - Run 2 `run-20260927-153202-899eac`: induced `search_policy:timeout@1` recovered; F-001/F-005
    duplicates of CVE-2026-1188 identified, earlier kept, no-duplicate-rule flagged honestly.
  - Run 3 `run-20260927-154914-11ea1a`: verified asset id A-003, F-012 (raw CVSS 10.0), ticket
    T-6a0f595a with policy citations.
  - Self-eval find: run 3a `run-20260927-154205-wrong-answer` — model assumed id "A-DB01", tool
    returned silent [], model reported "no open findings" (wrong). Root cause fixed in ec36463
    (unknown-entity filters fail loudly with real ids; prompt forbids concluding from assumptions);
    recovery verified by run 3. Shipped as failure+fix evidence.
- 2026-09-27 — all five transcripts archived under `docs/transcripts/` with a labelling README;
  secret scan clean (no key material in any tracked file).
- 2026-09-27 — docs complete: architecture.html (layout verified: 0 overlaps), write-up.md,
  decisions.md, README.md, transcripts/README.md.
- 2026-09-27 — Phases 0-8 complete: 98 tests pass, ruff clean, mypy clean.
- 2026-09-27 — Live-run bug fixed pre-Groq: qwen2.5 writes reasoning steps as the string "null";
  `parse_step` now returns None for no-tool steps (commit a71a417).
- 2026-09-27 — repo bootstrapped; SOUL.md question resolved (workspace copies are inert;
  decision left to the user).

## Remaining (manual, user)
- Create the public GitHub repo (`gh` not installed) and push `build/v1`.
- Submit the form: Engineer track, repo link, architecture diagram upload (docs/architecture.html
  → print to PDF from the browser), transcripts upload (zip docs/transcripts/ or the README plus
  run 1-3 folders), write-up (docs/write-up.md), domain goal text, time spent (~10-12h including
  the live-run debugging), copy declaration.
- Deadline question (48h vs 5-7 days) still unresolved with HR — if 48h applies, submit today.

## Open Decisions / Questions
- Is the 3-option `Agentic AI Assessment.docx` or the 2-track Google Form the real gate?
  Built the superset: Engineer deliverable whose domain satisfies docx Option 3.
- Which LLM produced the submitted transcripts: Groq `openai/gpt-oss-120b` — name it in the form
  and write-up (docs/transcripts/README.md already does).
