"""The agent: own the control flow, own the context window, compact the errors.

Two phases. `plan()` must return a validated Plan before anything else happens. `run()` then drives
a bounded act/observe loop. Nothing in this file decides anything about the security domain - every
domain judgement comes from the LLM and is only *validated* here. That split is deliberate: the
assessment forbids predefined rules, so the code's job is to constrain and observe, never to decide.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .config import Settings
from .llm import LLM, LLMError
from .memory import MemoryStore
from .report import build_report
from .retrieval import Retriever
from .schemas import (
    FinalReport,
    FinishRequest,
    Plan,
    PlanStep,
    StepKind,
    extract_first_json_object,
    parse_step,
)
from .tools.base import ToolRegistry
from .trace import TraceWriter, load_trace

REPEAT_FAILURE_HINT = (
    "{tool} has now failed {count} time(s) with the same arguments. Do not repeat it. Change your "
    "approach: call a different tool, loosen the arguments, or proceed with the evidence you "
    "already have and state the gap in your final answer."
)

FALLBACK_REASON = (
    "The planner did not return a usable plan. This is a fallback plan: one exploratory step that "
    "inspects the findings register and the policy corpus before deciding anything."
)


class AgentError(RuntimeError):
    pass


class Agent:
    def __init__(
        self,
        *,
        settings: Settings,
        llm: LLM,
        registry: ToolRegistry,
        retriever: Retriever,
        run_id: str | None = None,
    ) -> None:
        self.settings = settings
        self.llm = llm
        self.registry = registry
        self.retriever = retriever
        self.run_id = run_id or f"run-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        self.trace = TraceWriter(self.run_id, settings.runs_dir)
        self.memory = MemoryStore(settings.memory_path)
        self.usage: list[dict[str, Any]] = []
        self.goal: str | None = None

    # ------------------------------------------------------------------ prompts
    def _load_prompt(self, name: str) -> str:
        path = Path(self.settings.prompts_dir) / f"{name}.md"
        if not path.exists():
            raise AgentError(f"prompt file missing: {path}")
        return path.read_text(encoding="utf-8")

    def _planner_prompt(self) -> str:
        return self._load_prompt("planner").replace("{tool_schema}", self.registry.schema_block())

    def _executor_prompt(self) -> str:
        base = self._load_prompt("executor").replace("{tool_schema}", self.registry.schema_block())
        recalled = self.memory.recall(self.goal) if self.goal else []
        if recalled:
            lines = ["", "Previous runs on similar goals (context only, not evidence):"]
            lines.extend(
                f"- {item['at'][:10]}: {item['goal']} -> {item['summary']}" for item in recalled
            )
            base += "\n".join(lines)
        return base

    # ----------------------------------------------------------------- planning
    def plan(self, goal: str) -> Plan:
        self.goal = goal
        system = self._planner_prompt()
        messages: list[dict[str, str]] = [{"role": "user", "content": f"Goal: {goal}"}]
        last_error = ""

        for attempt in (1, 2):
            raw = self._complete(system, messages)
            if not raw.strip():
                last_error = "the planner returned an empty response"
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"{last_error}. Reply with exactly one JSON object and nothing else."
                        ),
                    }
                )
                self.trace.emit(
                    StepKind.error,
                    payload={
                        "where": "planner",
                        "attempt": attempt,
                        "reason": last_error,
                        "raw": "",
                    },
                )
                continue
            try:
                plan = self._validate_plan(raw)
            except ValueError as exc:
                last_error = str(exc)
                compacted = f"Your plan was rejected: {last_error}. Return corrected JSON only."
                self.trace.emit(
                    StepKind.error,
                    payload={
                        "where": "planner",
                        "attempt": attempt,
                        "reason": last_error,
                        "compacted": compacted,
                        "raw": raw[:400],
                    },
                )
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": compacted})
                continue

            self.trace.emit(
                StepKind.plan,
                payload={
                    "goal": plan.goal,
                    "steps": [
                        f"{s.index}. {s.description} [tool={s.tool or 'none'}] - {s.rationale}"
                        for s in plan.steps
                    ],
                    "assumptions": plan.assumptions,
                    "attempt": attempt,
                },
            )
            return plan

        plan = self._fallback_plan(goal, last_error)
        self.trace.emit(
            StepKind.recovery, payload={"where": "planner", "message": FALLBACK_REASON}
        )
        return plan

    def _validate_plan(self, raw: str) -> Plan:
        try:
            obj = json.loads(extract_first_json_object(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(f"response was not valid JSON ({exc.msg})") from exc
        try:
            plan = Plan.model_validate(obj)
        except Exception as exc:  # re-raised as a model-readable reason
            raise ValueError(f"plan failed schema validation: {exc}") from exc

        valid = self.registry.names()
        for step in plan.steps:
            if step.tool is not None and step.tool not in valid:
                raise ValueError(
                    f"unknown tool {step.tool!r} in step {step.index}; valid: {sorted(valid)}"
                )
        return plan

    def _fallback_plan(self, goal: str, reason: str) -> Plan:
        names = sorted(self.registry.names())
        tool = "list_findings" if "list_findings" in names else (names[0] if names else None)
        return Plan(
            goal=goal,
            steps=[
                PlanStep(
                    index=1,
                    description="Inspect the findings register and the policy corpus, then decide.",
                    tool=tool,
                    rationale="Exploratory fallback after two planner failures.",
                )
            ],
            assumptions=[FALLBACK_REASON, f"Planner errors: {reason}"],
        )

    # --------------------------------------------------------------- act/observe
    def run(self, goal: str, *, max_steps: int | None = None, on_plan=None) -> FinalReport:
        plan = self.plan(goal)
        if on_plan is not None:
            on_plan(plan)

        budget = max_steps or self.settings.max_steps
        system = self._executor_prompt()
        messages: list[dict[str, str]] = [
            {"role": "user", "content": self._initial_context(plan)}
        ]
        actions_taken: list[str] = []
        failures: dict[str, int] = {}
        # cumulative, never cleared: this is what `max_tool_failures` counts, so interleaved
        # successes cannot reset the budget back to zero
        total_tool_failures = 0
        limitations: list[str] = []
        steps_used = 0
        finish: FinishRequest | None = None

        while steps_used < budget:
            steps_used += 1
            raw = self._complete(system, messages)
            if not raw.strip():
                # Live: gpt-oss sometimes returns no content at all, and reporting that as
                # "Expecting value" tells the reader nothing. Name it, and nudge specifically.
                self._compact_response_error(
                    messages,
                    raw,
                    "the model returned an empty response",
                    step=steps_used,
                    nudge=(
                        "Reply with exactly one JSON object: a tool call, "
                        "or done:true to finish."
                    ),
                )
                limitations.append(
                    "The model returned an empty response once; the agent re-prompted it."
                )
                continue
            try:
                step = parse_step(raw, valid_tools=self.registry.names())
            except ValueError as exc:
                self._compact_response_error(messages, raw, str(exc), step=steps_used)
                limitations.append(f"One model response was unparseable ({exc}).")
                continue

            if isinstance(step, FinishRequest):
                self.trace.emit(
                    StepKind.finish, step=steps_used, payload=step.model_dump(mode="json")
                )
                finish = step
                break

            if step is None:
                # A pure-reasoning step: no tool to run, the model just narrated its thinking.
                # Advance without a call; one trace event keeps the step visible.
                self.trace.emit(
                    StepKind.llm, step=steps_used, payload={"reasoning": True}
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Noted. If you are done, reply with done: true; otherwise call a tool "
                            "to continue."
                        ),
                    }
                )
                continue

            spec = self.registry.spec(step.tool)
            self.trace.emit(StepKind.llm, step=steps_used, payload={"thought": step.thought})
            self.trace.emit(
                StepKind.tool_call,
                step=steps_used,
                payload={
                    "tool": step.tool,
                    "args": step.args,
                    "writes": spec.writes,
                    "irreversible": spec.side_effect,
                },
            )

            outcome = self.registry.call_safe(step.tool, step.args)
            fingerprint = f"{step.tool}:{json.dumps(step.args, sort_keys=True, default=str)}"

            if outcome["ok"]:
                # cleared per fingerprint: this counter drives the repeat-failure hint, so it must
                # mean "consecutive failures of this exact call", not "ever"
                failures.pop(fingerprint, None)
                observation = self._compact_observation(step.tool, outcome["result"])
                if spec.writes:
                    actions_taken.append(fingerprint)
                self.trace.emit(StepKind.tool_result, step=steps_used, payload=observation)
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": f"observation: {observation['text']}"})
            else:
                failures[fingerprint] = failures.get(fingerprint, 0) + 1
                total_tool_failures += 1
                count = failures[fingerprint]
                compacted = f"{step.tool} failed: {outcome['error']}"
                self.trace.emit(
                    StepKind.error,
                    step=steps_used,
                    payload={
                        "where": "tool",
                        "tool": step.tool,
                        "args": step.args,
                        "reason": outcome["error"],
                        "compacted": compacted,
                    },
                )
                messages.append({"role": "assistant", "content": raw})
                if count >= 2:
                    hint = REPEAT_FAILURE_HINT.format(tool=step.tool, count=count)
                    self.trace.emit(
                        StepKind.recovery,
                        step=steps_used,
                        payload={"tool": step.tool, "failures": count, "message": hint},
                    )
                    limitations.append(
                        f"{step.tool} failed {count} times running; the agent was told to change "
                        "approach."
                    )
                    messages.append({"role": "user", "content": hint})
                else:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"observation: {step.tool} failed with: {outcome['error']}. "
                                "Adjust and try a different approach."
                            ),
                        }
                    )

            if total_tool_failures >= self.settings.max_tool_failures:
                limitations.append(
                    "Tool failure budget exhausted; finishing with partial evidence."
                )
                break
        else:
            limitations.append(
                f"Stopped at the step budget ({budget}) without an explicit finish."
            )
            self.trace.emit(StepKind.recovery, payload={"message": "step budget exhausted"})

        if finish is None:
            finish = self._budget_finish(actions_taken, steps_used)
            self.trace.emit(StepKind.finish, payload=finish.model_dump(mode="json"))

        return self._finalise(plan, finish, actions_taken, steps_used, limitations)

    # ------------------------------------------------------------------- helpers
    def _budget_finish(self, actions_taken: list[str], steps_used: int) -> FinishRequest:
        sources = sorted({action.split(":", 1)[0] for action in actions_taken})
        return FinishRequest(
            thought="budget exhausted",
            summary=(
                f"The goal was not fully answered within the step budget ({steps_used} steps). "
                "The evidence gathered so far is recorded in the run transcript."
            ),
            key_findings=[f"Actions taken before stopping: {len(actions_taken)}"],
            decisions=[],
            sources=sources,
        )

    def _initial_context(self, plan: Plan) -> str:
        lines = [
            f"Today is {date.today().isoformat()}.",
            "",
            f"Goal: {plan.goal}",
            "",
            "Approved plan:",
        ]
        lines.extend(
            f"{step.index}. {step.description} [tool={step.tool or 'none'}] - {step.rationale}"
            for step in plan.steps
        )
        if plan.assumptions:
            lines += ["", "Assumptions made while planning:"]
            lines += [f"- {a}" for a in plan.assumptions]
        lines += ["", "Begin. Respond with one JSON object."]
        return "\n".join(lines)

    def _compact_observation(self, tool: str, result: Any) -> dict[str, Any]:
        text = json.dumps(result, default=str)
        limit = self.settings.max_observation_chars
        truncated = len(text) > limit
        return {"tool": tool, "text": text[:limit], "truncated": truncated, "result": result}

    def _compact_response_error(
        self,
        messages: list[dict[str, str]],
        raw: str,
        reason: str,
        *,
        step: int,
        nudge: str | None = None,
    ) -> None:
        instruction = nudge or "Return corrected JSON only."
        compacted = f"Your response was rejected: {reason}. {instruction}"
        self.trace.emit(
            StepKind.error,
            step=step,
            payload={
                "where": "executor",
                "reason": reason,
                "compacted": compacted,
                # keep what the model actually said (truncated) so a failure can be diagnosed
                # after the fact instead of guessed at
                "raw": raw[:400],
                "provider_reasoning": (
                    getattr(self.llm, "last_reasoning", "") or ""
                )[:300],
            },
        )
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": compacted})

    def _complete(self, system: str, messages: list[dict[str, str]]) -> str:
        try:
            text = self.llm.complete(system=system, messages=messages)
        except LLMError as exc:
            self.trace.emit(StepKind.error, payload={"where": "llm", "reason": str(exc)})
            raise AgentError(str(exc)) from exc
        if self.llm.last_usage:
            self.usage.append(dict(self.llm.last_usage))
        return text

    def _finalise(
        self,
        plan: Plan,
        finish: FinishRequest,
        actions_taken: list[str],
        steps_used: int,
        limitations: list[str],
    ) -> FinalReport:
        report = build_report(
            run_id=self.run_id,
            plan=plan,
            finish=finish,
            actions_taken=actions_taken,
            limitations=limitations,
            steps_used=steps_used,
            tool_calls=self.trace.tool_calls,
        )
        self.memory.record(self.run_id, goal=plan.goal, summary=finish.summary)
        return report

    def trace_events(self):
        return load_trace(self.trace.path)
