# Decision log

Why the build looks the way it does. Kept because the assignment grades judgement, and a diff does
not show the options that were rejected.

## Domain and framing

**Chose a security-operations domain, not a "safe" one like itineraries.** Xiarch is a security firm.
A generic travel-planner agent would have proved nothing about judgement in their context. The risk
was pretending to be a security product; the mitigation is that the data is explicitly synthetic and
the agent is framed as *triage automation*, which is what the role actually involves.

**Folded the docx Option 3 into the Engineer track.** The email pointed at a three-option doc dated
1 July; the PDFs and the form (21 September) describe two roles and say "choose your own
goal/task domain". I treated the docx as a stale template, built the Engineer deliverable, and chose
a knowledge-and-action-execution domain — which is docx Option 3 — so one submission satisfies both
readings.

## Architecture

**Adopted: the doctrine of `humanlayer/12-factor-agents`.** Specifically factors around owning your
own control flow, owning your context window, compacting errors into short observations, and
treating tool failures as prompts rather than exceptions. Six of the twelve factors are
re-implemented here from scratch.

**Rejected: LangGraph, CrewAI, AutoGen, the OpenAI Agents SDK.** All are good, and all would have
been faster. They were rejected because the assignment says the work must be my own and disqualifies
derived submissions, and because hiding the loop inside a framework would hide exactly the thing
being evaluated. No framework code is vendored; there is no `pip install` doing the interesting part.

**Rejected: `instructor` / structured-output libraries.** Pydantic validation plus a hand-written
"reject, explain, retry once" loop is ~30 lines and is itself a graded behaviour. A library would
have done it invisibly.

**Rejected for v1: Langfuse.** Real tracing is the right production answer and is named in the
write-up as the next step. It is not needed to demonstrate the agent, and it would have added a
network dependency to a repo that currently runs offline.

**Adopted partially: `pydantic-ai`'s validate-and-feed-errors-back pattern.** Kept the pattern,
skipped the framework.

**ChromaDB: wired, not default.** Implemented behind the same `Retriever` protocol as the keyword
retriever, opt-in via `SECOPS_RETRIEVER=chroma`. Defaulting to chroma means the first run downloads
an embedding model, and a demo that can fail on stage is worse than one that is slightly less clever.
With five policy documents, keyword search is genuinely sufficient.

## Agent behaviour

**The plan is a validated contract, not prose.** A plan naming a tool that does not exist is
rejected. This was the single highest-leverage decision: "problem decomposition & planning" is 20%
of the rubric and a free-text plan is trivially ignored.

**Repeat-failure detection rather than infinite retry.** The single most common agent failure is
retrying a broken call until the budget dies. The agent fingerprints `(tool, args)`, and on the
second identical failure emits a recovery event containing a concrete instruction to change
approach — different tool, looser arguments, or finish with the gap stated.

**Budgets are hard stops that still produce a report.** Hitting `MAX_STEPS` is not an exception and
not a crash: it appends a limitation, synthesises an honest finish, and writes the normal artifacts.
An agent that dies without output is worse than one that stops and says what it did not finish.

**`writes` and `side_effect` are separate flags.** `create_ticket` writes data but is reversible;
`escalate` is irreversible. Conflating them would either demand approval for opening a ticket or let
escalation run unapproved. The report's "actions taken" list is derived from `writes`, so there is no
hardcoded tool-name list in the agent.

**Approval is a tool call, not `input()`.** Making it a tool means the approval is an event in the
audit trail with an approver and a reference, replayable after the fact. `SECOPS_AUTO_APPROVE=true`
simulates the human for scripted demos; the default is `false`.

## Data and testing

**Hand-authored synthetic data with designed edge cases.** The register is built so that a correct
agent must do more than sort by CVSS: findings with no score at all (must become `needs_review`, not
`low`), a finding in a dev environment on a critical asset, a duplicate report on the same
host, a finding whose severity *changes* once business criticality is applied, and a finding sitting
exactly on its SLA boundary (7 days open, 7-day window — breached or not depends on reading the
policy as "exceeds"). Getting these wrong is visible.

**Offline-first test suite.** The LLM sits behind a one-method protocol and `ScriptedLLM` feeds
canned responses. 110 tests run in ~2 seconds with no network and no API key, which covers malformed
JSON, invented tools, repeated tool failure, exhausted budgets and a rejected finish payload. If the
model is down, the evidence that the agent recovers is still runnable.

**Fixed the assignment's own fault injection.** `SECOPS_INJECT_FAULT=tool:mode@n` makes the induced
failure reproducible instead of staged. A reviewer can reproduce the exact failing run.

## Deviations from my own written plan

Recorded rather than quietly fixed:

- `findings.csv` was planned with hostnames in the `asset_id` column, which would have broken the
  join to `assets.csv`. Corrected to `A-00x` ids.
- Two fault-injection tests in the plan called `before_call` expecting a raise without catching it.
  The tests were wrong, not the implementation.
- `notify_owner` and `today_iso` were planned into `tools/actions.py` and then dropped as
  unregistered dead code.
- The data builder moved from `scripts/build_knowledge_base.py` to
  `src/secops_agent/build_data.py` so it is importable and therefore testable.
- Retrieval default changed from chroma to keyword (reasoning above).
- `ToolSpec.writes` was added mid-build once `actions_taken` needed a definition that was not a
  hardcoded tool-name list.

## Findings from live runs and from an independent review, and what they forced

Each of these was found by running the agent against a real model or by a reviewer reading the repo
cold. Every one has a failing test that preceded the fix, and the runs that exposed the live ones are
in `docs/transcripts/`.

**An unknown entity filter must fail loudly, not return `[]`.** Live run 3 invented the asset id
`A-DB01`, got an empty list, and reported "no open findings" as fact. The silent empty was the bug:
the tool now raises with the known ids in the message, and the executor prompt forbids asserting
anything not observed. Re-verified live (a later run asked for `A-VPN-EDGE`, was corrected by the
error, and landed on `A-005`).

**Take the first complete JSON object.** Live models wrap JSON in prose and emit several objects
back-to-back (violating "one action per response"); both surfaced as "invalid JSON" and cost a step.
`extract_first_json_object` does a string-aware depth scan, used by both the planner and the executor
so the two paths cannot drift. Cheaper and more general than another prompt instruction.

**Do not retry an empty completion at the client.** First fix was a retry; then the trace showed
four identical retries returning four identical empties, so the retry added latency and cost for
nothing. The agent's compaction already sends a *new* message (a specific nudge), which is the actual
recovery. The client now spends exactly one call. Recorded because "we retry" was intuitive and
wrong.

**Capture the provider's `reasoning` field.** A direct API probe showed Groq's `gpt-oss` returns
`content: ""` with the text in `reasoning`, which is why runs reported an unexplained empty turn.
It is prose, so it is never used as an answer — it is recorded in the error event so an empty turn is
diagnosable from the trace instead of being an opaque `raw: ""`.

**Error events record the raw response.**
Found while diagnosing the above: the trace said "invalid JSON" and nothing about what the model
actually sent. Now the truncated raw text (and reasoning) ride along with every rejection, which is
what made all three parser findings above possible.

**A provider's daily token cap is a real failure mode.** Mid-verification, live runs began failing
with HTTP 429 (`TPD`, 200K tokens/day). The agent handled it correctly — retried, then exited with a
labelled failure instead of hanging — but re-running the graded transcripts was not possible that
day. Rather than fake it, the transcripts are shipped as two labelled cohorts and the gap is stated
in `docs/transcripts/README.md`.

### From the cold review

**The approval gate was decorative, and the docs claimed otherwise.** This is the one that stings.
An independent reviewer executed `escalate` with an invented-but-well-formed `approver` and
`approval_ref` and it succeeded — the check was only "are these two strings non-empty", while both
the README and the module docstring asserted that the code enforced provenance. A per-run
`ApprovalLedger` now mints references, and `escalate` consumes one under four checks: it must exist,
it must have been issued for the same finding, it must be paired with the approver it was minted for,
and it is burnt on use. A declined approval mints nothing, and the approver in the audit record comes
from the ledger rather than from the model's argument. Four attacks are now tests. **The lesson:
I wrote the claim before the control.** A security property asserted in prose is not a property, and
a reviewer who reads the docstring and then the code will find the gap — which is the point of
asking for the review.

**`parse_step` crashed the run on a wrongly-typed tool value.** It tested tool *names* before tool
*types*, so `{"tool": {"name": "list_findings"}}` raised `TypeError: unhashable type` out of a branch
nothing catches: no compaction, no report, just a traceback. Types are now validated first, and the
bad response is compacted like every other malformed reply.

**`max_tool_failures` was not the budget the README described.** It summed a per-argument counter
that any success cleared, so fail/succeed/fail/succeed never tripped it while the docs promised
"total failures". Two different questions now have two counters: consecutive failures per call drive
the repeat-failure hint, cumulative failures drive the budget.

**The CVSS bands were hardcoded while the policy claimed to own them.** The reviewer caught the
exact thing the assessment forbids — predefined rules — in the one place I had missed it.
`load_severity_bands()` now parses the rubric at call time, with no fallback (a silent fallback to
baked-in numbers would be the same bug wearing a hat). Two consequences worth noting: a CVSS 0.0,
which the rubric does not place in any band, now surfaces as `needs_review` instead of being filed as
`low`; and a test proves that rewriting the policy document changes the agent's behaviour.

**Two report strings asserted things that did not happen.** A limitation claimed the agent
"re-planned around" a failing tool (it injects a hint and continues), and a run that stopped before
any observation could name "findings table" as a source it never read. An audit artifact that
overstates what happened is worse than no artifact.
