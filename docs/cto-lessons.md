# CTO lessons

Accumulated judgement, written by the overseer for the overseer. Read this before working; append
before finishing. A lesson is a **rule plus the why** — not a log, not narration. If a lesson turns out
to be wrong, correct it in place rather than appending a contradiction.

## Lesson 1 — The failure mode here is a prose claim the code does not enforce

Twice now, the README and docstrings have asserted a security property the code did not implement: the
first `escalate` gate checked only that two strings were non-empty, so the model could invent both. The
fix is not "write more docs", it is: **read the claim, then try to falsify it by execution, through the
path the model actually uses.** Docs that describe intent are the defect surface, not the proof.
Corollary: a stale number in prose (README said 134 tests; the suite was 139) is the same class — after
adding tests, grep for the old count before finishing.

## Lesson 2 — When the failure mode is omission, the default must be restrictive

The second round found the same class one level down: `if approved_for and finding_id and ...` — a blank
on either side skipped the check, and blank was the default, so a generic "yes" authorised anything. A
guard written as `a and b and a != b` can be switched off by leaving something out. Prefer: the field is
mandatory at the schema layer, non-empty at both ends, and the comparison unconditional.

## Lesson 3 — Never leave your own work unverified because the tool said it succeeded

A successful tool call is not a successful task. Re-read the artifact, re-run the query, confirm the
file on disk says what you think it says — especially for anything a later pass or the human will treat
as evidence.

## Lesson 4 — An artifact that overstates what happened is worse than no artifact

Two report strings claimed things that had not occurred (a "re-plan" that was a hint injection; a
source that was never read). If the honest sentence is weaker, use the weaker sentence.

## Lesson 5 — A Settings-style path kwarg that is silently ignored writes real files to real paths

`Settings` takes `data_dir` as a field and derives the paths as properties (config.py:52-70); passing
`Settings(db_path=..., tickets_path=...)` is silently ignored (`extra="ignore"`), so the writes go to
the repo's real data/ — the probe polluted the repo's own audit file. When constructing settings for
a probe or test, pass the **field** (`data_dir`), never a derived path kwarg; a regression test pins
the assembled wiring so the mistake cannot pass silently.

## Lesson 6 — Attack the assembled path, not the unit under test

The gate's unit tests called `actions.escalate(ledger, ...)` directly and were green; the assembled
path (`build_registry` -> `call_safe`) carries two layers the unit never sees (args validation,
wiring), and a refactor could re-route either around the ledger while every unit test stays green.
Pin the path the LLM actually uses (`tests/test_gate_wiring.py`), not only the function.
