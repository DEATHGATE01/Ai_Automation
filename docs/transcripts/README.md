# Run transcripts — secops-agent

Live runs of the real agent (`uv run secops-agent run "..."`), unedited. Each folder carries the
artifacts that run actually produced — `trace.jsonl` (append-only event log) always, plus
`transcript.md`, `report.md` and `report.json` when the run finished. Transcript files are rendered
by `secops_agent.trace.render_transcript` from the JSONL trace; they are not hand-edited.

There are **two cohorts**, labelled rather than blended: the three graded runs were captured on the
revision described below, and six further runs were added after the agent was hardened. Every
outcome below is read out of that run's own `report.json`.

## Cohort 1 — the three graded runs

| # | Run | Goal | Backend | Outcome |
| --- | --- | --- | --- | --- |
| 1 | `run-20260927-152446-844613` | SLA breaches on production assets | Groq `openai/gpt-oss-120b` | Found F-012 (critical, 200 days open vs 7-day window), opened ticket `T-741cfa2d`, **refused to escalate** because no human approved — the gate working live |
| 2 | `run-20260927-153202-899eac` | Duplicate report on the web gateway | Groq, with `SECOPS_INJECT_FAULT=search_policy:timeout@1` | Induced tool failure recovered; identified F-001/F-005 as duplicates of CVE-2026-1188, kept the earlier record, and **flagged that no duplicate-handling rule exists in the policy corpus** instead of inventing one |
| 3 | `run-20260927-154914-11ea1a` | Triage the core database, ticket per policy | Groq | Verified the asset id after an initial wrong assumption, found F-012 (raw CVSS 10.0), opened ticket `T-6a0f595a` with policy citations |

These three ran before the parsing and grounding fixes in cohort 2. Their reports carry the
limitation line *"One model response was unparseable"*, which is accurate for that revision: the
model occasionally returned JSON the parser then rejected, and the run recovered by re-prompting.
Re-running the three goals on the hardened agent was attempted and blocked by the provider's daily
token cap (HTTP 429, `TPD`); the agent handled that error cleanly and exited with a labelled failure
rather than hanging. Those attempts were deleted rather than shipped as transcripts. Cohort 2 is
the honest substitute: the same agent, on the same data, covering ground these three do not.

## Cohort 2 — added after hardening (current code)

| Run | What it demonstrates |
| --- | --- |
| `run-20260927-192511-sla-hardened-code` | The graded run-1 goal re-run on hardened code: F-012 on `A-003`, approval obtained, ticket `T-1fd370b0`. Independent confirmation of run 1 |
| `run-20260927-192722-escalation-approved` | **The approval gate working live, open.** `request_human_approval` → `escalate` for F-012 with approver `auto` and ref `APR-8e46dcb9`, recorded in `data/escalations.jsonl`. Run 1 shows the gate refusing; this shows it letting an approved irreversible action through |
| `run-20260927-191702-unknown-asset-selfcorrected` | **Assumption → fail loudly → self-correct.** The model asked for `A-VPN-EDGE`; `list_findings` refused and listed the real ids; the final report correctly names `A-005` (`vpn-edge-prod`) with F-009 and F-004 and their due dates. This is the failure mode from the wrong-answer run below, on the fixed code |
| `run-20260927-192234-budget-exhausted` | `--max-steps 1`: an honest "not fully answered within the step budget" report, with nothing invented to fill the gap |
| `run-20260927-192118-fault-empty` | `SECOPS_INJECT_FAULT=list_findings:empty@1` recovered; the run then hit its own step budget and said so |
| `run-20260927-191954-fault-badargs` | `SECOPS_INJECT_FAULT=list_findings:bad_args@1` recovered and still produced the full open-findings list |
| `run-20260927-203147-local-qwen-budget` | The **fixed** code end to end on a local 7B model (Ollama `qwen2.5:7b-instruct`, free of the Groq daily cap): `list_findings(severity="critical")` banded from the parsed rubric, `get_asset`, then ticket `T-90250d7b` — and the run then hit its own 5-step budget and said so, listing `create_ticket` as its only source rather than naming a table it never read |

The two `fault-*` rows are two of the three fault modes the injector supports; cohort 1 run 2 covers
the third (`timeout`), so all three are demonstrated live. The `local-qwen` row is there because the
provider's daily cap blocked further runs on the hosted model: it is the same agent on a smaller
local model, which is a weaker model but an honest end-to-end run of the fixed code.

## A model quirk, measured

Most runs in both cohorts record *"The model returned an empty response once; the agent
re-prompted it"* as a limitation. That is one behaviour, not flakiness: in 4 of the first 5 runs it
occurred on **step 1**, and a direct API probe showed why — Groq's `gpt-oss` returns `content: ""`
and puts the text in a separate `reasoning` field. The agent names it, nudges with a new message and
continues; the wasted step is visible in every trace. Retrying the identical call was tried and then
removed, because four identical retries produced four identical empties — the new message is the
effective recovery, so the client now spends exactly one call on it.

## The failure evidence (not graded runs — they are the interesting ones)

`run-20260927-154205-wrong-answer/` — the same goal as run 3, **before** a fix. The model assumed
the core database's id was `A-DB01` (never verified), `list_findings` silently returned an empty
list, and the model reported "no open findings" — an artifact of its own assumption. This run was
found during self-evaluation, its root cause fixed (unknown-entity filters now fail loudly with the
real ids, and the executor prompt forbids concluding from an unverified assumption — commit
`ec36463`), and the recovery verified by re-running (graded run 3, and again in cohort 2 as
`...191702-unknown-asset-selfcorrected`). Both runs are shipped because "here is my agent failing,
here is the fix, here is it passing" is stronger evidence than nine clean runs.

`run-20260927-001829-bd9528/` — the very first live attempt on a 4096-token local model
(`codellama:7b-instruct`): both planner attempts overflowed and returned unparseable output, and the
fallback plan engaged correctly (labelled, no fake plan). Kept as evidence that the planner fallback
works under a model failure, and as the reason the README documents the ~8K-context model
requirement.

## How these were generated and labelled

- All runs are of the unmodified agent on the synthetic knowledge base in `data/` — no findings,
  assets or policies are real. Every report carries the synthetic-data notice.
- Deliberate faults are injected only through the documented mechanism
  (`SECOPS_INJECT_FAULT=<tool>:<mode>@<n>`) and appear in the trace as an `error` event followed by
  the recovery. All three modes (`timeout`, `bad_args`, `empty`) are demonstrated across the runs
  above.
- Token totals are printed by the CLI at run time but are **not** persisted into the run artifacts,
  so no per-run cost figure is claimed here. Per-run token accounting is listed in
  `docs/write-up.md` as missing work.
