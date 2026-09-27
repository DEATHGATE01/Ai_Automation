# Write-up — secops-agent

**Track:** Agentic AI Engineer Intern · **Domain:** security-operations triage · **Time:** ~10 h

## What I built and why this domain

A two-phase agent that takes a triage goal in plain English, plans it, works it with seven tools
over a findings register and a policy corpus, and finishes with a structured report.

I chose security-operations triage because the assignment says to pick a domain but forbids
hardcoded rules. Triage is the hardest case for that constraint: severity banding, SLA windows and
escalation thresholds all *look* like logic you would put in an `if`. Putting them in the prompt as
policy documents instead — and letting the model apply them — is a real test of whether the
architecture can be genuinely autonomous rather than a rule engine wearing a language model.

The domain is synthetic on purpose. **All findings, assets and policies are authored for this
assignment; no real client data is involved.** The alternatives were hoaxing live scans or borrowing
a public CVE feed, and neither produces defensible evidence about agent behaviour.

## Design decisions

**Two phases, and the plan is a contract.** The model must return a `Plan` that validates before a
single tool runs. A plan that names a tool I do not have is rejected, the reason is fed back, and it
gets one retry — then an explicitly-labelled fallback plan. Planning is 20% of the rubric, so it
does not get to be a paragraph of prose the model ignores the moment it starts acting.

**Own the loop; do not hand it to a framework.** I read `12-factor-agents` and adopted the doctrine
— own your control flow, own your context window, compact errors into short observations — while
re-implementing the mechanics. No LangGraph, no CrewAI, no agent SDK. For a submission that will be
read as a judgement sample, the loop *is* the artifact.

**Tools report facts; the model applies policy.** `list_findings` returns a raw CVSS band, not a
verdict. The business-criticality adjustment and the SLA arithmetic happen in the model, citing the
document it read. I can point at the file where each severity came from. This is also why
`request_human_approval` is a tool rather than a `input()` call: the approval is an event in the
trace, not a side effect in a terminal.

**Exactly one irreversible action, and it is gated in code.** `escalate` raises unless it is handed
an `approver` and `approval_ref` that came from the approval tool. The prompt forbids inventing
them; the code makes inventing them impossible. That asymmetry — prompt for behaviour, code for
guarantees — is the main thing I would defend in a review.

**Deterministic fault injection, not `sleep()` and hope.** `SECOPS_INJECT_FAULT=list_findings:timeout@1`
fails the first call of that tool. Robustness is 20% of the rubric and "watch it break" is worth
more than a paragraph claiming it recovers. All three fault modes (`timeout`, `bad_args`, `empty`)
are demonstrated in the shipped transcripts.

## What running it live taught me

Everything below was found by running the agent against a real model, not by reasoning about it —
and two of these were bugs my own tests were green on.

- **A wrong answer that looked like a right one.** Asked to triage the core database, the model
  invented the id `A-DB01`, `list_findings` returned an empty list, and it reported "no open
  findings". The tool was *too* forgiving: an unknown filter returned `[]` instead of an error. Now
  it fails loudly and lists the real ids, and the prompt forbids concluding from an unverified
  assumption. That run ships as evidence, next to the passing re-run.
- **The parser was stricter than the model.** `gpt-oss` sometimes wraps JSON in prose, and sometimes
  emits three JSON objects back-to-back; both were rejected as "invalid JSON" and cost a step each.
  The response is now parsed by taking the first complete JSON object.
- **One model quirk, measured rather than assumed.** Most runs reported "one response was
  unparseable". A direct API probe showed why: the model returns `content: ""` with the text in a
  separate `reasoning` field, on step 1 in 4 of the first 5 runs. I first "fixed" this by retrying —
  then measured four identical retries returning four identical empties, and removed the retry. The
  effective recovery was already in the loop: a *new* nudge message.
- **The gate, in both directions.** Refusing to escalate without approval is one run; `escalate`
  executing with a recorded approver and reference is another. Both are in the transcripts.

## Limitations

- **Single-threaded.** No parallel tool calls. The loop is one action per turn by design (it keeps
  the trace legible and the budget honest) but it costs latency on independent reads.
- **Keyword retrieval by default.** Chroma is wired up and opt-in via `SECOPS_RETRIEVER=chroma`.
  I defaulted to keyword because a first run that must download an embedding model is a demo that
  can fail on stage — but with 5 policy documents, keyword search is genuinely adequate and I am
  not going to pretend otherwise.
- **No evaluation harness.** 110 tests cover the *mechanics* (recovery, budgets, parsing, gating).
  Nothing measures whether the agent's *security judgements* are right. That is the biggest gap and
  the thing I would do first with more time.
- **Truth is whatever the register says.** The agent has no way to check a finding against the asset
  in reality; it trusts the data it is given and reports it as read.
- **Memory is token-overlap,** not semantic. It surfaces previous runs on similar goals; it does not
  understand that "SLA breaches" and "overdue remediation" are the same question.
- **`create_ticket` is not idempotent.** It appends to a JSONL file. A re-run opens a second ticket.

## What I would do differently with more time

1. **A labelled evaluation set.** ~30 goals with expected findings-and-actions, run on every prompt
   change. Right now prompt edits are unmeasured, which makes them guesswork.
2. **Adversarial robustness.** Feed it a register containing findings that contradict the policy
   corpus and check whether it says so or confidently averages the two. That failure mode is
   untested and, in my judgement, the most likely one.
3. **A policy-as-data layer.** The policy documents should carry structured metadata (windows,
   thresholds) alongside the prose the model reads, generated from one source. Right now a
   threshold change means editing prose in one place and hoping the prompt still matches.
4. **Structured tracing.** Langfuse or OpenTelemetry around the LLM calls, for token cost and
   latency per step. The JSONL trace is enough for a reviewer and not enough for an operator.
5. **Two agents, not one.** A verifier that re-reads a finished report against the raw observations
   would catch the class of error I actually worry about: a confident summary that overstates what
   the tools returned.
