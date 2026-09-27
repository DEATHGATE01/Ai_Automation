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
canned responses. 96 tests run in ~2 seconds with no network and no API key, which covers malformed
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
