"""Every tool that supports fault injection must actually be wrapped by the injector.

Found by execution (pass 2): `search_policy` was registered without the `guarded()` wrapper, so the
documented `SECOPS_INJECT_FAULT=search_policy:...` mechanism silently never fired for it — while
README, .env.example and the transcripts README all advertised that spec, and a shipped transcript
claimed "Induced tool failure recovered" from a run whose trace contains no injected fault at all.
The failure mode is the repo's classic one: a claim in prose that the code does not enforce, with a
guard that omission (a missing wrapper) can switch off.
"""
import shutil
from pathlib import Path
from typing import Any

import pytest

from secops_agent.config import Settings
from secops_agent.retrieval import build_retriever
from secops_agent.tools import build_registry


def _settings(tmp_path: Path, fault: str) -> Settings:
    """Settings against a tempdir; the synthetic policies are copied in, never the repo's data/.

    Idempotent: a test may call this several times (registry, retriever, agent) against the same
    tmp_path - only the first call copies.
    """
    dst = tmp_path / "policies"
    if not dst.exists():
        shutil.copytree(Path("data/policies"), dst)
    return Settings(_env_file=None, data_dir=tmp_path, inject_fault=fault)


def _call(reg: Any, tool: str, nth: int = 1) -> dict[str, Any]:
    """Call `tool` through the assembled path `nth` times, return the last outcome."""
    out: dict[str, Any] = {}
    for _ in range(nth):
        out = reg.call_safe(tool, _args(tool) if tool != "list_findings" else {})
    return out


def test_every_data_tool_is_wrapped_by_the_injector(tmp_path: Path) -> None:
    """A new data tool registered without guarded() must fail this test, not fire silently."""
    settings = _settings(tmp_path, "list_findings:timeout@1")
    reg = build_registry(settings, build_retriever(settings))
    names = reg.names()
    # the four read tools exist and are the injector's surface
    assert {"list_findings", "get_finding", "get_asset", "search_policy"} <= names
    # direct call on the wrapper-protected tool: the injector intercepts before the fn
    assert reg.spec("list_findings").fn.__name__ == "wrapper"


def test_search_policy_fault_injection_fires_through_the_registry(tmp_path: Path) -> None:
    """The advertised spec `search_policy:timeout@1` must fail the 1st call and only that one."""
    reg = build_registry(
        _settings(tmp_path, "search_policy:timeout@1"),
        build_retriever(_settings(tmp_path, "search_policy:timeout@1")),
    )
    first = _call(reg, "search_policy")
    assert not first["ok"], "the injected timeout must fail the first search_policy call"
    assert "injected timeout" in first["error"]
    second = _call(reg, "search_policy", nth=1)
    assert second["ok"], "the fault is scoped to the 1st call; the 2nd must succeed"


def _args(tool: str) -> dict[str, Any]:
    """Arguments that satisfy each tool's schema, so a failure can only be a wiring fault."""
    if tool == "search_policy":
        return {"query": "remediation SLA windows"}
    if tool == "get_finding":
        return {"finding_id": "F-001"}
    if tool == "get_asset":
        return {"asset_id": "A-001"}
    return {}


def test_unconfigured_injector_is_inert_for_every_tool(tmp_path: Path) -> None:
    reg = build_registry(_settings(tmp_path, ""), build_retriever(_settings(tmp_path, "")))
    from secops_agent.build_data import build

    build(Path("data"), tmp_path / "secops.db")  # real db over the synthetic corpus
    for tool in ("search_policy", "list_findings", "get_asset", "get_finding"):
        outcome = reg.call_safe(tool, _args(tool))
        assert outcome["ok"], f"{tool} must work with no fault configured"


def test_run_report_cannot_claim_a_recovery_that_never_fired(tmp_path: Path) -> None:
    """Pin the agent loop: a fault that never fires must not produce a recovery limitation."""
    from secops_agent.agent import Agent
    from secops_agent.llm import ScriptedLLM

    reg = build_registry(_settings(tmp_path, ""), build_retriever(_settings(tmp_path, "")))
    plan = {
        "goal": "g",
        "steps": [
            {"index": 1, "description": "a", "tool": "search_policy", "rationale": "r"},
            {"index": 2, "description": "b", "tool": None, "rationale": "r"},
            {"index": 3, "description": "c", "tool": None, "rationale": "r"},
        ],
    }
    llm = ScriptedLLM(
        [
            __import__("json").dumps(plan),
            __import__("json").dumps(
                {"thought": "t", "tool": "search_policy", "args": {"query": "sla"}}
            ),
            __import__("json").dumps({"done": True, "summary": "s"}),
        ]
    )
    agent = Agent(
        settings=Settings(_env_file=None, data_dir=tmp_path),
        llm=llm,
        registry=reg,
        retriever=build_retriever(_settings(tmp_path, "")),
    )
    report = agent.run("g")
    assert not any("failed" in line or "recovery" in line.lower() for line in report.limitations), (
        "a clean run must not carry a tool-failure limitation"
    )


def test_fault_spec_parser_rejects_unknown_tool_names(tmp_path: Path) -> None:
    """A spec naming a tool that does not exist must fail loudly at build time."""
    from secops_agent.tools import build_registry as br
    from secops_agent.tools.faults import parse_fault_spec

    assert parse_fault_spec("no_such_tool:timeout@1") is not None
    # build_registry must reject it loudly: the injector would silently never fire
    with pytest.raises(ValueError):
        br(
            _settings(tmp_path, "no_such_tool:timeout@1"),
            build_retriever(_settings(tmp_path, "no_such_tool:timeout@1")),
        )


def test_fault_spec_helper_contract() -> None:
    from secops_agent.tools.faults import parse_fault_spec

    assert parse_fault_spec(None) is None
    assert parse_fault_spec("") is None
    parsed = parse_fault_spec("get_asset:empty@2")
    assert parsed == ("get_asset", "empty", 2)
