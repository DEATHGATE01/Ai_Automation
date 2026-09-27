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

