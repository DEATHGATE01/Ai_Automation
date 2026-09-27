# CTO lessons

Accumulated judgement, written by the overseer for the overseer. Read this before working; append
before finishing. A lesson is a **rule plus the why** — not a log, not narration. If a lesson turns out
to be wrong, correct it in place rather than appending a contradiction.

## Lesson 1 — The failure mode here is a prose claim the code does not enforce

Twice now, the README and docstrings have asserted a security property the code did not implement: the
first `escalate` gate checked only that two strings were non-empty, so the model could invent both. The
fix is not "write more docs", it is: **read the claim, then try to falsify it by execution, through the
path the model actually uses.** Docs that describe intent are the defect surface, not the proof.

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
