"""Tools are just structured outputs plus a dispatch table.

A tool is a validated argument model, a callable, and a flag saying whether calling it is
irreversible. Callers get `call_safe`, which converts failures into compact observations that the
LLM can read and react to - the whole point of owning the loop.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError


class ToolError(RuntimeError):
    """Raised by a tool when the world says no. Always safe to show the model."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    fn: Callable[..., Any]
    writes: bool = False        # mutates state; counted in the report's "actions taken"
    side_effect: bool = False   # irreversible; requires a recorded human approval first


@dataclass
class ToolRegistry:
    _specs: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> None:
        self._specs[spec.name] = spec

    def names(self) -> set[str]:
        return set(self._specs)

    def spec(self, name: str) -> ToolSpec:
        try:
            return self._specs[name]
        except KeyError as exc:
            raise ToolError(f"unknown tool {name!r}; available: {sorted(self._specs)}") from exc

    def call(self, name: str, args: dict[str, Any]) -> Any:
        spec = self.spec(name)
        try:
            validated = spec.args_model.model_validate(args)
        except ValidationError as exc:
            raise ValueError(
                f"invalid arguments for {name!r}: "
                + "; ".join(f"{e['loc'][0]}: {e['msg']}" for e in exc.errors())
            ) from exc
        return spec.fn(**validated.model_dump())

    def call_safe(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            return {"ok": True, "result": self.call(name, args)}
        except Exception as exc:  # noqa: BLE001 - every failure must reach the model, compactly
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def schema_block(self) -> str:
        lines = ["Available tools:", ""]
        for name, spec in sorted(self._specs.items()):
            schema = spec.args_model.model_json_schema()
            props = schema.get("properties", {})
            required = set(schema.get("required", []))
            lines.append(f"- {name}: {spec.description}")
            if props:
                for prop, meta in props.items():
                    mark = " (required)" if prop in required else ""
                    lines.append(
                        f"    - {prop}: {meta.get('type', 'any')}{mark} - "
                        f"{meta.get('description', '')}"
                    )
            else:
                lines.append("    (no arguments)")
            if spec.writes:
                lines.append("    ! writes data")
            if spec.side_effect:
                lines.append("    ! irreversible: request human approval first")
            lines.append("")
        return "\n".join(lines)


def args_schema_json(args_model: type[BaseModel]) -> str:
    return json.dumps(args_model.model_json_schema(), indent=2)
