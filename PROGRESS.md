# PROGRESS.md

## Current Focus
COMPLETE. The take-home submission is built, tested, run live, and committed on `build/v1`.

## Done (most recent first)
- 2026-09-27 (later) — VERIFICATION SWEEP + live-run hardening, all evidence-driven:
  - Clean-clone grader simulation (fresh `git clone` → sync → `make data` → tests) caught a real
    grader-experience bug: the `.env.example` inline comment parsed as a 52-char *API key*, so a
    grader got `401 Invalid API Key` instead of the friendly "key required" message. Fixed with a
    `_clean_api_key` validator + comment-free example (commit 463efda); grader now gets the clear
    message and exit 2.
  - Diagnosed "one model response was unparseable" from raw traces instead of guessing: the model
    wraps JSON in prose AND emits three objects back-to-back. `extract_first_json_object` (string-
    aware depth scan, used by planner and executor) fixes both (164d165).
  - Empty responses are now named and nudged; the client-level retry was REMOVED after measuring
    four identical retries returning four identical empties (79d1cfb). A direct API probe proved the
    cause: gpt-oss returns `content: ""` with the text in `reasoning`. That reasoning is now captured
    so an empty turn is explained rather than an opaque `raw: ""` (60045d6).
  - Error events record the truncated raw response — the change that made the findings above possible.
  - Cohort 2 transcripts added (`docs/transcripts/`): the approval gate OPEN for the first time live
    (`escalate` F-012, approver `auto`, ref `APR-8e46dcb9`, written to `data/escalations.jsonl`); the
    graded run-1 goal on hardened code (ticket T-1fd370b0); the unknown-asset self-correction
    (asked `A-VPN-EDGE` → fail-loud → correctly landed on `A-005`); budget exhaustion; fault modes
    `bad_args` and `empty`. All three fault modes now demonstrated live.
  - Groq's daily token cap (429 `TPD`, 200K/day) blocked re-running the three graded goals; those
    attempts were deleted, and the transcripts ship as two labelled cohorts with the gap stated.
  - 110 tests pass, ruff clean, mypy clean.
- 2026-09-27 — Phases 0-8 complete: 110 tests pass, ruff clean, mypy clean.
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
- 2026-09-27 — Phases 0-8 complete: 110 tests pass, ruff clean, mypy clean.
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
