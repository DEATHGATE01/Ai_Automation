# Run transcripts — secops-agent

Live runs of the real agent (`uv run secops-agent run "..."`), unedited. Each folder carries the four
artifacts a run produces: `trace.jsonl` (append-only event log), `transcript.md` (human-readable
rendering), `report.md`, `report.json`.

## The three graded runs

| # | Run | Goal | Backend | Outcome |
| --- | --- | --- | --- | --- |
| 1 | `run-20260927-152446-844613` | SLA breaches on production assets | Groq `openai/gpt-oss-120b` | Found F-012 (critical, 200 days open vs 7-day window), opened ticket `T-741cfa2d`, **refused to escalate** because no human approved — the gate working live |
| 2 | `run-20260927-153202-899eac` | Duplicate report on the web gateway | Groq, with `SECOPS_INJECT_FAULT=search_policy:timeout@1` | Induced tool failure recovered; identified F-001/F-005 as duplicates of CVE-2026-1188, kept the earlier record, and **flagged that no duplicate-handling rule exists in the policy corpus** instead of inventing one |
| 3 | `run-20260927-154914-11ea1a` | Triage the core database, ticket per policy | Groq | Verified the asset id after an initial wrong assumption, found F-012 (raw CVSS 10.0), opened ticket `T-6a0f595a` with policy citations |

## The failure evidence (not a graded run — it is the interesting one)

`run-20260927-154205-wrong-answer/` — the same goal as run 3, **before** a fix. The model assumed
the core database's id was `A-DB01` (never verified), `list_findings` silently returned an empty
list, and the model reported "no open findings" — an artifact of its own assumption. This run was
found during self-evaluation, its root cause fixed (unknown-entity filters now fail loudly with the
real ids, and the executor prompt forbids concluding from an unverified assumption — commit
`ec36463`), and the recovery verified by re-running (graded run 3). Both runs are shipped because
"here is my agent failing, here is the fix, here is it passing" is stronger evidence than three
clean runs.

`run-20260927-001829-bd9528/` — the very first live attempt on a 4096-token local model
(`codellama:7b-instruct`): both planner attempts overflowed and returned unparseable output, and the
fallback plan engaged correctly (labelled, no fake plan). Kept as evidence that the planner fallback
works under a model failure, and as the reason the README documents the ~8K-context model
requirement.

## How these were generated and labelled

- All runs are of the unmodified agent on the synthetic knowledge base in `data/` — no findings,
  assets or policies are real. Every report carries the synthetic-data notice.
- The one deliberate fault is injected by the documented mechanism
  (`SECOPS_INJECT_FAULT=search_policy:timeout@1`) and is visible in run 2's transcript and in its
  `trace.jsonl` as an `error` event followed by a recovery.
- Transcript files are rendered by `secops_agent.trace.render_transcript` from the JSONL trace; they
  are not hand-edited. Total cost of the four live runs: ~76K prompt + ~13K completion tokens.
