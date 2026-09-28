"""Command line entry point.

    secops-agent run    "<goal>"      execute the agent, write report + transcript
    secops-agent replay <run_id>      re-print a stored run's transcript (no LLM, no tools)
    secops-agent report <run_id>      re-render a stored run's report.md

`replay` and `report` exist so a reviewer can inspect the evidence without spending tokens or
trusting a screenshot: the trace is the source of truth and it is re-readable forever.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import Agent, AgentError
from .config import Settings, get_settings
from .llm import build_llm, usage_totals
from .report import render_markdown, write_report
from .retrieval import build_retriever
from .schemas import FinalReport, Plan
from .tools import build_registry
from .trace import load_trace, render_transcript


def _run_dir(settings: Settings, run_id: str) -> Path:
    return Path(settings.runs_dir) / run_id


def _print_plan(plan: Plan) -> None:
    print("\nPLAN")
    for step in plan.steps:
        print(f"  {step.index}. {step.description} [tool={step.tool or 'none'}]")
        print(f"     why: {step.rationale}")
    for assumption in plan.assumptions:
        print(f"  ? assumption: {assumption}")


def cmd_run(args: argparse.Namespace, settings: Settings) -> int:
    if not settings.db_path.exists():
        print(
            f"knowledge base missing: {settings.db_path}\n"
            "Run: uv run python -m secops_agent.build_data",
            file=sys.stderr,
        )
        return 2

    retriever = build_retriever(settings)
    agent = Agent(
        settings=settings,
        llm=build_llm(settings),
        registry=build_registry(settings, retriever),
        retriever=retriever,
    )
    print(f"run id:  {agent.run_id}")
    print(f"backend: {settings.llm_model} @ {settings.llm_base_url}")
    print(f"goal:    {args.goal}")
    if settings.inject_fault:
        print(f"fault:   {settings.inject_fault}  (deliberately injected for this run)")

    try:
        report = agent.run(
            args.goal,
            max_steps=args.max_steps,
            on_plan=None if args.quiet else _print_plan,
        )
    except AgentError as exc:
        print(f"agent failed: {exc}", file=sys.stderr)
        return 1

    json_path, md_path = write_report(report, settings.runs_dir)
    transcript_path = _run_dir(settings, report.run_id) / "transcript.md"
    transcript_path.write_text(render_transcript(agent.trace_events()), encoding="utf-8")

    print("\n" + render_markdown(report))
    usage = usage_totals(agent.usage)
    print(f"\ntrace:       {agent.trace.path}")
    print(f"transcript:  {transcript_path}")
    print(f"report md:   {md_path}")
    print(f"report json: {json_path}")
    if usage:
        print(f"tokens:      {usage}")
    return 0


def cmd_replay(args: argparse.Namespace, settings: Settings) -> int:
    path = _run_dir(settings, args.run_id) / "trace.jsonl"
    if not path.exists():
        print(f"no trace at {path}", file=sys.stderr)
        return 2
    print(render_transcript(load_trace(path)))
    return 0


def cmd_report(args: argparse.Namespace, settings: Settings) -> int:
    path = _run_dir(settings, args.run_id) / "report.json"
    if not path.exists():
        print(f"no report at {path}", file=sys.stderr)
        return 2
    report = FinalReport.model_validate(json.loads(path.read_text(encoding="utf-8")))
    markdown = render_markdown(report)
    (path.parent / "report.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="secops-agent",
        description="Autonomous security-operations triage agent.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the agent on a goal")
    run.add_argument("goal", help="the triage goal, in natural language")
    run.add_argument("--max-steps", type=int, default=None, help="override SECOPS_MAX_STEPS")
    run.add_argument("--quiet", action="store_true", help="do not print the plan as it is made")
    run.set_defaults(func=cmd_run)

    replay = sub.add_parser("replay", help="re-print a stored run transcript")
    replay.add_argument("run_id")
    replay.set_defaults(func=cmd_replay)

    report = sub.add_parser("report", help="re-render a stored run's markdown report")
    report.add_argument("run_id")
    report.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    try:
        settings.validate_backend()
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    return args.func(args, settings)


if __name__ == "__main__":
    raise SystemExit(main())
