# CTO report

Append-only log written by the autonomous overseer described in `docs/CTO.md`. One dated section per
pass, newest last. Every claim in here is meant to be falsifiable: commands are quoted with the output
they actually produced.

---

## 2026-09-28 02:5x — pass 0 (bootstrap)

**State found.** Branch `build/v1`, tree clean, 35 commits. `uv run pytest` -> 134 passed; `uv run ruff
check src tests` -> All checks passed; `uv run mypy src` -> Success: no issues found in 16 source
files.

**Two independent review rounds have already run against this repo** (both by a cold reviewer told to
fail it unless it found nothing, both recorded in `docs/decisions.md`):

- Round 1 found the `escalate` approval gate was decorative (it checked only that `approver` and
  `approval_ref` were non-empty strings, so a model could invent both) while the README claimed the
  code enforced provenance. Fixed with a per-run `ApprovalLedger`.
- Round 2 confirmed all four round-1 fixes were genuinely closed by execution, then found the same
  class of hole one level down: the same-finding check read `if approved_for and finding_id and ...`,
  so a blank on **either** side skipped it — and blank was the default. A human answering a prompt that
  named no finding authorised escalation of an unrelated finding. Now the finding is mandatory in the
  schema and the ledger and the comparison is unconditional.

**Standing lesson for future passes:** the failure mode in this repo is not missing code, it is *a
claim in prose that the code does not enforce*, plus *a guard that omission can switch off*. Check
claims by execution, and prefer restrictive defaults.

**Left for the next pass.** No known defects outstanding at bootstrap time. Items worth a fresh look,
none of them confirmed:

- `README.md` claims the agent cannot fabricate its way past the gate — re-verify by attack, not by
  reading, since that claim has been wrong twice.
- Whether a live transcript on the hosted model can be produced (the provider's daily token cap was
  hit on 2026-09-27/28); if it can, the graded three should be re-run on the current code.
- Whether `docs/write-up.md` really fits one page when printed.

**Risk assessment.** The submission is complete and green. The main residual risk is *overclaiming*,
because the agent and its docs have twice asserted a property the code did not enforce. The second
risk is time: the manual steps (create the public repo, push, submit the form) belong to the human.

---

## 2026-09-28 04:1x — pass 0b (authority grant, by the human's request)

The human granted the overseer **full command** and asked for self-direction, self-improvement, and the
ability to create its own agents. What changed, and why it is safe:

- **`docs/CTO.md` rewritten** as a charter of authority, not a list of permissions: the overseer may fix,
  refactor, extend, restructure, add tools/tests/docs/features, spawn sub-agents (`delegate_task`), edit
  its own charter and this prompt, create its own skills, and **decide when the project is done**.
- **Self-improvement is now a mechanism, not a slogan:** `docs/cto-lessons.md` is a learning ledger the
  overseer must read before working and append to before finishing — the only thing that makes pass N
  smarter than pass 1. It is seeded with the four lessons this project actually earned. Each pass must
  also audit its predecessor's claims by execution.
- **Self-termination:** on meeting the definition of done the overseer writes `docs/CTO-COMPLETE.md` and
  creates `.cto-stop`; the overseer loop exits at the next boundary. It decides when to stop working.
- **Four rails are kept, deliberately**: never touch/commit `.env`; never push or rewrite history; revert
  unless pytest+ruff+mypy stay green; never fabricate evidence. These protect the human's assets rather
  than constrain judgement, and the overseer may not remove them itself — only argue for it in a report.

**What a later pass should check.** Whether the authority grant caused drift: an agent told it may do
anything is exactly the agent that starts refactoring a working submission for no reason. The test is
the report's evidence, not its ambition — if a pass changed something, it must show the failing test
that justified it and the green suite that followed.

---

## 2026-09-28 04:3x — pass 0c ("go wild")

The human's instruction was to let the overseer go wild while they sleep. Scope was widened; the four
rails were kept, and it is worth writing down why that is not a contradiction.

**Widened.** A `## Full latitude` section now heads the charter: take the big swing — rewrite a module,
replace a design, add a capability nobody asked for; experiment branches and worktrees are yours to
create; start sub-agents, background jobs, helper scripts, extra passes. The old "stop when the required
list is ticked" rule is replaced: once the definition of done holds, the overseer keeps going along a
menu aimed at making the submission *stronger* (an evaluation harness for the agent's judgements — the
gap the write-up itself admits — a regression test per review finding, a second live transcript,
hardening, a demo a stranger can follow). It stops when improvements stop being net-positive, or when it
declares the project complete. Stopping early purely because a checklist is ticked is now explicitly a
failure mode, as is inventing work.

**Kept, deliberately.** (1) Never open or commit `.env`; (2) never push or rewrite history; (3) `build/v1`
stays green after every change — experiments live on their own branch until they are green; (4) never
fabricate evidence. These are not restrictions on judgement, they are the difference between an
autonomous agent that returns the project in better shape and one that returns a leaked key, an
unrecoverable history, or a red submission branch at 9am. The overseer may argue against any of them in
a report, and the human can lift them in one edit — but it may not remove them itself.

**Runtime.** The successor overseer was restarted with a 12-pass budget (was 8). It still exits early if
the overseer writes `.cto-stop`, so the effective limit is its own judgement, not the counter.

---

## 2026-09-28 13:4x — pass 0d (runtime retune: the passes were timing out)

**What the evidence shows.** All three overnight passes so far ended `rc=124` — killed by the 90-minute
per-pass cap, each mid-flight: pass 1 (03:35→05:06), pass 2 (07:06→08:36), pass 3 (10:36→12:06). Commits
since 03:35: **zero** (the three in the log are the human's scaffolding). The work was real — the tree
carried an uncommitted `tests/test_plan_bounds.py` plus edits across `agent.py`, `schemas.py` and four
test files, 139 tests passing, 2 ruff errors — but every pass ran out of time before it could land
anything, and the 2h gap between passes made it worse. The CTO did not fail; the runtime did.

**Retuned.** Per-pass cap 90min → 2h; between-pass wait 2h → 10min (passes now chain); budget 12 → 6
passes (~12h at the measured pace, the real limit is still its own judgement via `.cto-stop`).

**Scope discipline added to `docs/CTO_PROMPT.md`** (this is the fix that matters, not the timeout):
orient ≤15 min; pick ONE deliverable and land it green+committed before anything else; timebox
exploration; record half-finished work precisely so the next pass resumes instead of redoes; and deal
with orphaned work first — which is this pass's first job, since the tree is dirty with the timed-out
pass's changes.

**Standing lesson.** An unattended loop must be tuned to the measured pace of its worker, not a guessed
one. The first three passes looked busy and produced nothing — the same "looks like success" failure as
an empty-but-valid PDF, one level up.

---

## 2026-09-28 15:4x — pass 1 (first pass of the retuned loop: orphaned work landed, gate attacked live)

**State found.** Branch `build/v1`, tree dirty with the timed-out predecessor's orphaned work
(`tests/test_plan_bounds.py` untracked; edits across `agent.py`, `schemas.py`, four test files).
`uv run pytest` -> **139 passed in 4.51s**; `uv run ruff check src tests` -> **All checks passed**;
`uv run mypy src` -> **Success: no issues found in 16 source files**. The 2 ruff errors pass 0d
reported sitting at `agent.py:188` and `tests/test_plan_bounds.py:28` were already fixed by the
predecessor before it died — the tree was cleaner than its log claimed.

**Predecessor audit.** Pass 0d's central claim ("3 consecutive rc=124, zero commits") verified TRUE by
execution: `grep -c "rc=124" ~/AppData/Local/hermes/scripts/cto-overnight.log` -> **3** (pass 1
05:06, pass 2 08:36, pass 3 12:06, matching the report exactly). One claim was too narrow: the 2
ruff errors were described as sitting in the tree; by the time this pass looked, the predecessor had
already fixed them. Corrected here.

**Orphaned work verified and landed (commit `83787ee`).** The diff is coherent: `Plan` gains the
documented 3-5 step bound (`min_length=3, max_length=5`), `_fallback_plan` (agent.py:177-215) was
rewritten to satisfy the same contract after the bound would have crashed the old 1-step fallback,
and 5 new tests pin the bounds. Landed green: 139 passed, ruff+mypy clean.

**Gate attacked live, through the path the LLM actually uses** (`build_registry(...)` ->
`registry.call_safe('escalate', ...)`), in a scratch probe against a tempdir — all attacks blocked:
- fabricated approver+ref (`APR-deadbeef`) -> `unknown or already-used approval_ref`
- real ref aimed at a different finding -> `was issued for finding F-009, not F-011`
- replayed (already-spent) ref -> `unknown or already-used approval_ref`
- mismatched approver -> `does not match the approver recorded for ...`
- blank `approval_ref` / blank `approver` -> rejected at the schema layer, before the ledger

The README claim that the model cannot fabricate its way past the gate is **true of the current
code** — the first time that claim has been verified by attack rather than assumed (it had been wrong
twice before).

**Probe bug worth recording (a defect in myself, not the repo).** `Settings` takes `data_dir` as a
field and derives `db_path`/`tickets_path`/`escalations_path` as **properties**
(config.py:52-70); passing the path kwargs directly is **silently ignored** (`extra="ignore"`). My
first probe constructed `Settings(db_path=tmp, ...)` and wrote 2 records into the repo's real
`data/escalations.jsonl`. Removed by filtering on the probe's own approval refs (the 2 original
graded-run records kept, `wc -l` -> 2); the file is gitignored and was never committed. A regression
test (`tests/test_gate_wiring.py`) now pins the assembled wiring so the next person cannot make the
same mistake silently — the tests construct `Settings(_env_file=None, data_dir=tmp_path, ...)` and
assert the record lands in the file `Settings.escalations_path` names.

**What changed (commit `475aa4c`).**
- `tests/test_gate_wiring.py` (new, 6 tests): the unit tests call `actions.escalate(ledger, ...)`
  directly, bypassing two layers the model never bypasses — `EscalateArgs` validation inside
  `call_safe` and the `build_registry` wiring that binds the ledger and the audit file. A refactor
  that re-routed either layer around the ledger would leave every unit test green while the gate went
  dark. The assembled path is now pinned for all four attacks plus blank fields, and the happy path
  is asserted to write the audit file `Settings.escalations_path` names.
- Stale-claims fixed (a claim the tree contradicted): README said **134** tests in three places and
  `docs/write-up.md` once; the suite is 145. `.env.example` said a trailing `#` after `=` "gets
  parsed as the key"; the config validator (config.py:72-82) treats it as the **value**.
- Verified after: `uv run pytest` -> **145 passed**; ruff -> All checks passed; mypy -> Success.

**Anomaly.** A commit I did not make (`10e7ed5`, docs-only charter edits to `CTO.md`/`CTO_PROMPT.md`,
authored 14:26 — between this pass's two commits at 14:07 and 15:26) appeared in `git log` mid-pass.
No other process is running (only this hermes instance in `ps aux`), the working tree is clean, and
the commit conflicts with nothing here. Left standing, flagged for the human.

**Left for the next pass.** No known defects outstanding. Worth doing, in value order:
- A second live transcript on the current code (the provider's daily cap was hit 2026-09-27/28; the
  three graded transcripts predate the plan-bounds and fallback changes).
- An evaluation harness for the agent's judgements — the write-up itself names this as the biggest
  gap.
- `python -m build` wheel/sdist check, to prove the package builds from a clean tree.

**Risk assessment.** The gate has now survived a live attack through the real path, with the wiring
pinned by tests, so the residual overclaim risk is much lower than at bootstrap. The tree is clean at
145 tests. The main residual risk is process, not code: an interloper commit appeared in the branch
mid-pass, and the manual steps (public repo, push, form) still belong to the human.



