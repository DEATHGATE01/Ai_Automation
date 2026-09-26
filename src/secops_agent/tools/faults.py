"""Deterministic fault injection for the graded 'handle a deliberately induced failure' requirement.

Configured entirely by SECOPS_INJECT_FAULT, e.g. "list_findings:timeout@1" makes the first call of
that tool raise a timeout. With no configuration the injector is inert, so normal behaviour is
unaffected - the same mechanism a chaos experiment would use in production.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import ToolError

MODES = {"timeout", "bad_args", "empty"}


def parse_fault_spec(spec: str | None) -> tuple[str, str, int] | None:
    if not spec:
        return None
    try:
        target_mode, nth_text = spec.split("@", 1)
        target, mode = target_mode.split(":", 1)
        nth = int(nth_text)
    except ValueError as exc:
        raise ValueError(
            "SECOPS_INJECT_FAULT must look like 'tool_name:mode@n' "
            "(modes: timeout, bad_args, empty)"
        ) from exc
    if mode not in MODES:
        raise ValueError(f"SECOPS_INJECT_FAULT mode must be one of {sorted(MODES)}, got {mode!r}")
    return target, mode, nth


@dataclass
class FaultInjector:
    spec: str | None = None
    _counts: dict[str, int] = field(default_factory=dict)
    fired: int = 0

    def __post_init__(self) -> None:
        self._parsed = parse_fault_spec(self.spec)

    def before_call(self, tool_name: str) -> None:
        if self._parsed is None:
            return
        target, mode, nth = self._parsed
        if tool_name != target:
            return
        self._counts[tool_name] = self._counts.get(tool_name, 0) + 1
        if self._counts[tool_name] != nth:
            return
        self.fired += 1
        if mode == "timeout":
            raise ToolError(f"injected timeout: {tool_name} did not respond within 30s")
        if mode == "bad_args":
            raise ToolError(f"injected malformed arguments from upstream service for {tool_name}")
        raise ToolError(f"injected empty response from {tool_name}")
