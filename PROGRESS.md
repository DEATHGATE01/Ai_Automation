# PROGRESS.md

## Current Focus
COMPLETE. The take-home submission is built, tested, run live, and committed on `build/v1`.

## Done (most recent first)
- 2026-09-28 (latest) — RE-REVIEW acted on. The re-review confirmed all four earlier fixes genuinely
  closed (verified by execution, including six attack variants on the approval gate) and found the
  same class of defect one level down:
  - **The same-finding check was skippable by omission** (`if approved_for and finding_id and ...`),
    and blank was the default: `ApprovalArgs` had no required `finding_id` and the executor prompt
    never told the model to name the finding. Reproduced end to end — a human answering a prompt that
    named no finding then authorised escalation of an unrelated finding. Fix: the finding is now
    mandatory in the schema (`min_length=1`), at mint time and at consume time, and the comparison is
    unconditional.
  - **Interactive approvals recorded approver "auto"**, because that argument defaulted to "auto" and
    was unreachable from the model-facing schema — a record that contradicted its own
    `approval_mode: interactive`. Interactive approvals now record the OS login (or `SECOPS_APPROVER`,
    now a real Settings field), and the record carries the question the human answered.
  - **A tool-failure stop reported the step budget** in its summary while its limitations said
    otherwise. `_budget_finish` now takes the stop reason.
  - **The rubric parser validates bands**: inverted or overlapping bands are a loud ToolError, so
    document order can never silently decide an overlap.
  - 134 tests pass, ruff clean, mypy clean.
- 2026-09-27/28 — INDEPENDENT REVIEW acted on. A cold reviewer (no context, instructed to
  fail the repo unless it found nothing) returned `passed: false`; every claim I checked was correct:
  - **Security:** the `escalate` gate only checked that `approver`/`approval_ref` were non-empty, so
    a model could invent both — while README + docstrings claimed the code enforced provenance. It
    verified the bypass by execution. Fixed with a per-run `ApprovalLedger` (minted refs, consumed
    under four checks: exists, same finding, matching approver, single use). Four attacks verified
    rejected through the registry path; commit afa3fe8.
  - `parse_step` checked tool NAMES before TYPES, so `{"tool": {...}}` raised `TypeError` from an
    uncaught branch → run died with a traceback, no report. Fixed + agent-level test.
  - `max_tool_failures` summed a counter any success cleared → fail/succeed/fail never tripped it,
    contradicting the README's "total failures". Now two counters (consecutive for the hint,
    cumulative for the budget).
  - CVSS bands were hardcoded in `knowledge.py` while `severity_rubric.md` claimed to own them — the
    "predefined rules" the assessment forbids. Bands are now parsed from the policy at call time,
    with no fallback; a CVSS 0.0 now surfaces as `needs_review`; a test proves a policy edit changes
    behaviour. Verified over the real corpus: identical bands, no behaviour regression.
  - Two report strings asserted what did not happen ("re-planned around it") or named an unread
    source. Both corrected.
  - Removed dead `prompts/reporter.md` (nothing loaded it); corrected stale test counts in README.
  - **Grader-experience bug found by cloning as a grader would:** `make` is NOT installed on this
    Windows box (nor by default on Windows), so the README's first two commands failed with
    `make: command not found`. The quickstart now leads with direct `uv run` commands, with the
    Makefile described as the optional wrapper it is. Verified in a fresh clone.
  - Write-up trimmed from 1,277 to ~850 words to fit the "1-page" requirement; the long-form detail
    lives in `docs/decisions.md`.
  - End-to-end run of the FIXED code on the local model (Groq's daily cap blocked the hosted model):
    `run-20260927-203147-local-qwen-budget` — rubric-banded `list_findings`, `get_asset`, ticket
    `T-90250d7b`, honest budget report, and sources correctly derived from the action taken.
  - 124 tests pass, ruff clean, mypy clean. Findings recorded in `docs/decisions.md` and
    `docs/write-up.md` ("I wrote the claim before the control").
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
- Deadline question RESOLVED by HR (2026-09-28): the email states a strict deadline, but "if you submit
  it as soon as possible and your methodology is found good we can consider it" — so submit ASAP.
  Paste-ready answers and upload files are in ../submission/ (form-answers.txt, architecture.pdf,
  transcripts.zip, synthetic-traces.zip, code.zip).

## Open Decisions / Questions
- Is the 3-option `Agentic AI Assessment.docx` or the 2-track Google Form the real gate?
  Built the superset: Engineer deliverable whose domain satisfies docx Option 3.
- Which LLM produced the submitted transcripts: Groq `openai/gpt-oss-120b` — name it in the form
  and write-up (docs/transcripts/README.md already does).
