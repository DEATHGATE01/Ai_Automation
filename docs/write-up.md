# Write-up — secops-agent

**Track:** Agentic AI Engineer Intern · **Domain:** security-operations triage · **Time:** ~12 h

## What I built and why this domain

A two-phase agent: a triage goal in plain English becomes a validated plan, the plan is worked by a
bounded act/observe loop over seven tools (a findings register and a policy corpus), and the run ends
in a structured report.

I chose security-operations triage because the assignment forbids hardcoded rules, and triage is the
hardest case for that constraint: severity banding, SLA windows and escalation thresholds all *look*
like logic you would put in an `if`. Putting them in policy documents the model reads — instead of in
code — is a real test of whether the architecture is autonomous rather than a rule engine wearing a
language model. The one place I had duplicated a policy value in code (the CVSS bands) was caught in
independent review and is now parsed out of the rubric itself.

All findings, assets and policies are synthetic and authored for this assignment; no real client data
is involved.

## Design decisions

**The plan is a validated contract.** The model must return a `Plan` that validates before a single
tool runs; a plan naming a tool I do not have is rejected, the reason is fed back, and it gets one
retry. Planning is 20% of the rubric, so it does not get to be a paragraph of prose the model ignores
the moment it starts acting.

**Own the loop; do not hand it to a framework.** I read `12-factor-agents` and adopted the doctrine —
own your control flow, own your context window, compact errors into short observations — while
re-implementing the mechanics. No LangGraph, no CrewAI, no agent SDK. For a submission that will be
read as a judgement sample, the loop *is* the artifact.

**Tools report facts; the model applies policy.** `list_findings` returns a raw CVSS band, not a
verdict: the business-criticality adjustment and the SLA arithmetic happen in the model, citing the
document it read. Even the band thresholds come from `severity_rubric.md` rather than from code.
`request_human_approval` is a tool rather than an `input()` call for the same reason — the approval is
an event in the trace, not a side effect in a terminal.

**Exactly one irreversible action, gated in code.** `escalate` accepts only an `approval_ref` that
`request_human_approval` minted for that same finding, in that run, once. Prompt for behaviour; code
for guarantees.

**Deterministic fault injection, not `sleep()` and hope.** `SECOPS_INJECT_FAULT=list_findings:timeout@1`
fails the first call of that tool, so a reviewer can reproduce the failure exactly. Robustness is 20%
of the rubric, and all three fault modes (`timeout`, `bad_args`, `empty`) are demonstrated in the
shipped transcripts.

## What testing it taught me

Everything here was found by running the agent against a real model or by a reviewer reading the repo
cold — not by reasoning about it. Four of them were bugs my own test suite was green on: an unknown
asset id returned `[]` and the model reported "no open findings" as fact (now a loud error listing the
real ids); the parser rejected prose and back-to-back JSON objects (now takes the first complete
object); `max_tool_failures` summed a counter that any success cleared, so it never tripped; and the
approval gate only checked that two strings were non-empty while my README claimed the code enforced
provenance — a real bypass, now a per-run ledger of single-use references. That last one is the lesson
I am keeping: **I wrote the claim before the control.** Each fix has a failing test behind it, and the
detail is in `docs/decisions.md`.

## Limitations

- **No evaluation harness.** 124 tests cover the *mechanics* (recovery, budgets, parsing, gating), not
  whether the agent's security *judgements* are right. That is the biggest gap.
- **Keyword retrieval by default.** Chroma is wired and opt-in via `SECOPS_RETRIEVER=chroma`; with five
  policy documents keyword search is genuinely adequate, and I am not going to pretend otherwise.
- **Truth is whatever the register says.** The agent cannot check a finding against reality.
- **Memory is token-overlap,** not semantic. **`create_ticket` is not idempotent.** One action per turn
  by design, which keeps the trace legible and costs latency on independent reads.

## What I would do differently with more time

1. **A labelled evaluation set** — ~30 goals with expected findings and actions, run on every prompt
   change. Right now a prompt edit is unmeasured, which makes it guesswork.
2. **A verifier agent** that re-reads a finished report against the raw observations, to catch the
   error I actually worry about: a confident summary that overstates what the tools returned.
3. **Adversarial robustness** — a register that contradicts the policy corpus, and whether the agent
   says so rather than confidently averaging the two.
4. **Policy-as-data for the remaining thresholds.** The severity bands now parse from the rubric; SLA
   windows and escalation thresholds are still prose, and should get the same treatment.
5. **Structured tracing** (Langfuse or OpenTelemetry) for token cost and latency per step. The JSONL
   trace is enough for a reviewer and not enough for an operator.
