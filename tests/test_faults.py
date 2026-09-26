import pytest

from secops_agent.tools.base import ToolError
from secops_agent.tools.faults import FaultInjector, parse_fault_spec


def test_parse_spec():
    assert parse_fault_spec("list_findings:timeout@1") == ("list_findings", "timeout", 1)
    assert parse_fault_spec("") is None
    assert parse_fault_spec(None) is None


def test_parse_spec_rejects_garbage():
    with pytest.raises(ValueError, match="SECOPS_INJECT_FAULT"):
        parse_fault_spec("nonsense")


def test_parse_spec_rejects_unknown_mode():
    with pytest.raises(ValueError, match="mode must be one of"):
        parse_fault_spec("list_findings:explode@1")


def test_injector_fails_only_the_nth_call():
    inj = FaultInjector("list_findings:timeout@1")
    with pytest.raises(ToolError):
        inj.before_call("list_findings")        # 1st -> raises
    inj.before_call("list_findings")            # 2nd -> passes
    inj.before_call("get_asset")                # other tool -> untouched
    assert inj.fired == 1


def test_injector_raises_toolerror():
    inj = FaultInjector("list_findings:timeout@1")
    with pytest.raises(ToolError, match="injected timeout"):
        inj.before_call("list_findings")


def test_injector_bad_args_mode():
    inj = FaultInjector("get_asset:bad_args@1")
    with pytest.raises(ToolError, match="injected malformed arguments"):
        inj.before_call("get_asset")


def test_injector_empty_mode():
    inj = FaultInjector("list_findings:empty@1")
    with pytest.raises(ToolError, match="injected empty response"):
        inj.before_call("list_findings")


def test_injector_records_history():
    inj = FaultInjector("list_findings:timeout@2")
    inj.before_call("list_findings")            # 1st -> passes
    with pytest.raises(ToolError):
        inj.before_call("list_findings")        # 2nd -> raises
    assert inj.fired == 1


def test_injector_is_inert_when_unconfigured():
    inj = FaultInjector(None)
    inj.before_call("anything")
    assert inj.fired == 0
