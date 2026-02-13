from __future__ import annotations

from typing import Any


def orchestrator(state: dict[str, Any], *, max_iters: int = 20) -> dict[str, Any]:
    state["loop_iterations"] = int(state.get("loop_iterations") or 0) + 1
    if state["loop_iterations"] > max_iters:
        plan = state.get("plan") or []
        state["current_step"] = {}
        state["current_step_index"] = len(plan)
        state["termination_reason"] = "max_iters"
        return state

    plan = state.get("plan") or []
    idx = None
    for i, step in enumerate(plan):
        if step.get("status") == "pending":
            idx = i
            break
    if idx is None:
        state["current_step"] = {}
        state["current_step_index"] = len(plan)
        state["termination_reason"] = "finalized"
        return state

    state["current_step_index"] = idx
    state["current_step"] = dict(plan[idx])
    return state
