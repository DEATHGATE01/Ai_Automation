# secops-agent

An autonomous security-operations triage agent. Give it a goal in plain English; it writes a plan,
reads a findings register and a policy corpus through tools, decides what matters, opens tickets,
and escalates — but it cannot escalate without a recorded human approval, and every step it takes
is written to an append-only JSONL trace you can replay.

Built for the Xiarch Bharat **Agentic AI Engineer Intern** take-home assignment (req XB-AI-2026-09).

```
$ uv run secops-agent run "Which critical findings on production assets have breached or are about to breach their remediation SLA, and what should we do about them?"

PLAN
  1. Read the remediation SLA policy to get the windows. [tool=search_policy]
     why: the SLA numbers must come from policy, not from memory
  2. List the findings with their CVSS scores and days open. [tool=list_findings]
     why: need the register to know what is late
  ...
```

## The 60-second version

The agent runs in two phases, and the split is the whole design.

**Phase 1 — plan.** The LLM must return a `Plan` that validates: 3–5 steps, each naming a real
tool, each with a rationale. If it returns junk or invents a tool, the agent rejects the plan,
tells the model *why*, and asks again — once. If the second attempt also fails, it falls back to an
explicitly-labelled exploratory plan rather than pretending it planned.

**Phase 2 — act and observe.** A bounded loop. Each turn the model returns exactly one JSON object:
either a tool call or a finish. Tool results are compacted into short observations. When a tool
fails, the error is compacted to one line and fed back. When the *same call fails twice*, the agent
stops retrying and emits a recovery event with a specific instruction to change approach — because
retrying a broken call forever is the classic agent failure mode.

Nothing in the code decides anything about security. The severity bands, the SLA arithmetic and the
escalation threshold come out of the policy documents and are applied by the LLM. The tools report
facts — raw CVSS, owner, days open — and the code validates and constrains. That was a deliberate
reading of the assignment's "no predefined rules or static outputs" constraint.

## Quickstart

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo> && cd secops-agent
uv sync                 # create the venv and install dependencies
cp .env.example .env    # then edit .env (see Configuration below)
make data               # build the SQLite knowledge base from data/*.csv
make test               # 124 offline tests, no network, no API key
```

Then run it:

```bash
uv run secops-agent run "Which critical findings on production assets have breached or are about to breach their remediation SLA?"
```

Or with a simulated outage, to watch it recover:

```bash
SECOPS_INJECT_FAULT=list_findings:timeout@1 \
  uv run secops-agent run "Triage the findings on the core database asset."
```

`make run GOAL="..."` is a thin wrapper around the first form.

## Configuration

Everything is environment-driven (`.env`, prefixed `SECOPS_`). Any OpenAI-compatible endpoint works.

| Setting | Default | Notes |
| --- | --- | --- |
| `SECOPS_LLM_BASE_URL` | `https://api.groq.com/openai/v1` | Point at `http://localhost:11434/v1` for Ollama |
| `SECOPS_LLM_MODEL` | `openai/gpt-oss-120b` | Needs to follow strict-JSON instructions well |
| `SECOPS_LLM_API_KEY` | *(empty)* | Required for a remote backend; not required for localhost |
| `SECOPS_MAX_STEPS` | `12` | Hard budget on the act/observe loop |
| `SECOPS_MAX_TOOL_FAILURES` | `3` | Total failures before it stops and reports partial evidence |
| `SECOPS_MAX_OBSERVATION_CHARS` | `1200` | Observations are truncated to this before entering context |
| `SECOPS_AUTO_APPROVE` | `false` | `true` simulates the human tapping approve (used in demos) |
| `SECOPS_INJECT_FAULT` | *(empty)* | `tool:mode@n`, modes `timeout`, `bad_args`, `empty` |
| `SECOPS_RETRIEVER` | `keyword` | `chroma` opts into embedding-based policy retrieval |

**Fully local, no API key:** `SECOPS_LLM_BASE_URL=http://localhost:11434/v1` with
`SECOPS_LLM_MODEL=qwen2.5:7b-instruct`. For a security team, "no finding ever leaves the network" is
a feature, not a fallback.

**Model requirements, learned the hard way.** The planner prompt carries the full tool schema, so
the model needs **at least ~8K tokens of context** and reasonable strict-JSON discipline. A
4096-token model (`codellama:7b-instruct`) overflows, returns unparseable output, and the agent falls
back to its labelled fallback plan — correct behaviour, but not what you want for a demo. Small
local models are also slow enough on CPU that a 12-step run takes tens of minutes. Point it at a
hosted endpoint for the graded runs, or a 7B-class model with a 32K window for a keyless local demo.

## The seven tools

Read-only (`writes=False`):

| Tool | Purpose |
| --- | --- |
| `list_findings` | Findings register, filterable by asset or raw CVSS band |
| `get_asset` | One asset's owner, criticality, environment, internet exposure |
| `search_policy` | Retrieval over the five policy documents |
| `get_finding` | One finding by id, joined to its asset |

Writing:

| Tool | Purpose |
| --- | --- |
| `create_ticket` | Open a remediation ticket (writes `data/tickets.jsonl`) |
| `request_human_approval` | Ask a human; returns an approver and a reference |
| `escalate` | **Irreversible.** Refuses to run without a real `approver` + `approval_ref` |

`escalate` is the only irreversible tool, and it is gated **in code**: `request_human_approval` mints
an `approval_ref` into a per-run ledger, and `escalate` accepts nothing else. The reference must
exist, must have been issued for the *same* finding, must be paired with the approver it was minted
for, and it is burnt on use — while a declined request mints nothing at all. The approver written to
the audit record comes from the ledger, not from the model's argument. An independent review found an
earlier version of this check decorative (it only tested that two strings were non-empty, so a model
could invent both); the ledger is the fix, and `tests/test_action_tools.py` now pins each property.
Set `SECOPS_AUTO_APPROVE=false` (the default) to see the approval step happen in the transcript.

## Where the evidence lives

Every run writes four artifacts to `runs/<run_id>/`:

| File | What it is |
| --- | --- |
| `trace.jsonl` | Append-only event log — the source of truth |
| `transcript.md` | Human-readable rendering of that trace |
| `report.md` | The final structured answer |
| `report.json` | The same answer, machine-readable |

Artifacts can be re-read without touching the model or the tools:

```bash
uv run secops-agent replay <run_id>   # re-print the transcript
uv run secops-agent report <run_id>   # re-render the report markdown
```

## Project layout

```
src/secops_agent/
  config.py       Settings (pydantic-settings), paths, backend validation
  schemas.py      Pydantic contracts: Plan, ToolCallRequest, FinishRequest, FinalReport, TraceEvent
  llm.py          OpenAI-compatible client with retry/backoff; ScriptedLLM for offline tests
  retrieval.py    KeywordRetriever (stdlib) and ChromaRetriever (embeddings) behind one protocol
  trace.py        JSONL trace writer/reader + markdown transcript renderer
  memory.py       Cross-run memory: what the agent did on similar goals before
  report.py       Report assembly and rendering
  build_data.py   CSV -> SQLite knowledge base (`make data`)
  cli.py          run / replay / report
  agent.py        The two-phase loop
  tools/          base.py (registry+validation), knowledge.py, actions.py, faults.py, __init__.py
data/             synthetic assets.csv, findings.csv, policies/*.md
prompts/          planner.md, executor.md
tests/            124 offline tests
docs/             architecture diagram, write-up, decision log, run transcripts
```

## Testing

```bash
make test     # 110 tests, ~2s, no network, no API key
make lint     # ruff + mypy, both clean
```

The whole suite runs offline because the LLM sits behind a one-method protocol. `ScriptedLLM` feeds
canned responses, so every branch — malformed JSON, an invented tool, a repeated tool failure, an
exhausted budget, a rejected finish payload — is tested deterministically. Nothing about the agent's
recovery behaviour is taken on faith.

## Data notice

**All findings, assets and policies in this repository are synthetic.** They were authored for this
assignment; no real client data is involved. See `docs/write-up.md` for why a security-operations
domain was chosen and what the mock data is designed to exercise.

## Limitations

Honest list, expanded in `docs/write-up.md`: single-agent (no parallel tool calls), keyword
retrieval by default rather than embeddings, no structured evaluation harness, memory is
token-overlap rather than semantic, and the tool surface is deliberately narrow. Retries, budget
accounting and the audit trail are real; production concerns like idempotency keys on `create_ticket`
and a durable queue are not.
