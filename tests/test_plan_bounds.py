"""Failing test first (RED): the plan schema must enforce the documented 3-5 step bounds.

The README ("a `Plan` that validates: 3-5 steps, each naming a real tool") and the planner prompt
("3 to 5 steps") both promise bounds that `Plan` does not enforce: a 1-step and a 9-step plan both
validate today, so a model may ignore the rubric's structure requirement and the docs overclaim.
"""

import pytest
from pydantic import ValidationError

from secops_agent.schemas import Plan


def _plan_with_steps(n: int) -> dict:
    steps = [
        {"index": i, "description": f"step {i}", "tool": None, "rationale": "why"}
        for i in range(1, n + 1)
    ]
    return {"goal": "g", "steps": steps, "assumptions": []}


@pytest.mark.parametrize("n", [1, 2, 6, 9])
def test_plan_step_count_outside_3_to_5_is_rejected(n: int) -> None:
    # the plan contract is the graded "problem decomposition" surface: a plan with the wrong
    # number of steps must be a loud rejection fed back to the model, never a silent accept.
    # Pydantic's own message names the bound ("at least 3 items" / "at most 5 items"), so the
    # model is told exactly what to fix.
    with pytest.raises(ValidationError, match=r"at least 3 items|at most 5 items"):
        Plan.model_validate(_plan_with_steps(n))


def test_plan_step_count_inside_3_to_5_is_accepted() -> None:
    for n in (3, 4, 5):
        plan = Plan.model_validate(_plan_with_steps(n))
        assert len(plan.steps) == n
