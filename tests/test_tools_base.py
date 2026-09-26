import pytest
from pydantic import BaseModel, Field

from secops_agent.tools.base import ToolError, ToolRegistry, ToolSpec


class AddArgs(BaseModel):
    a: int
    b: int = Field(default=1)


def test_registry_dispatches_and_validates_args():
    reg = ToolRegistry()
    reg.register(ToolSpec(name="add", description="add two ints", args_model=AddArgs,
                          fn=lambda a, b: {"sum": a + b}))
    assert reg.call("add", {"a": 2, "b": 3}) == {"sum": 5}


def test_registry_rejects_bad_args_with_a_compact_message():
    reg = ToolRegistry()
    reg.register(ToolSpec(name="add", description="d", args_model=AddArgs, fn=lambda a, b: a))
    with pytest.raises(ValueError, match="invalid arguments for 'add'"):
        reg.call("add", {"a": "not-an-int"})


def test_registry_rejects_unknown_tool():
    with pytest.raises(ToolError, match="unknown tool"):
        ToolRegistry().call("nope", {})


def test_wrapped_tool_returns_error_instead_of_raising():
    reg = ToolRegistry()

    def boom(a: int, b: int = 1):
        raise ToolError("upstream timeout")

    reg.register(ToolSpec(name="boom", description="d", args_model=AddArgs, fn=boom))
    result = reg.call_safe("boom", {"a": 1})
    assert result["ok"] is False
    assert "upstream timeout" in result["error"]


def test_schema_block_lists_every_tool():
    reg = ToolRegistry()
    reg.register(ToolSpec(name="add", description="add two ints", args_model=AddArgs,
                          fn=lambda a, b: a))
    block = reg.schema_block()
    assert "add" in block and "add two ints" in block and '"a"' not in block
    assert "a: integer" in block


def test_side_effect_flag_marks_irreversible_tools():
    reg = ToolRegistry()
    reg.register(ToolSpec(name="escalate", description="d", args_model=AddArgs,
                          fn=lambda a, b: a, side_effect=True))
    assert reg.spec("escalate").side_effect is True
    assert "irreversible" in reg.schema_block()


def test_names_returns_registered_tools():
    reg = ToolRegistry()
    reg.register(ToolSpec(name="add", description="d", args_model=AddArgs, fn=lambda a, b: a))
    assert reg.names() == {"add"}
