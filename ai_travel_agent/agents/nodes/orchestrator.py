from __future__ import annotations

from typing import Any

from ai_travel_agent.observability.telemetry import TelemetryController, set_signal
from .utils import log_context_from_state


def orchestrator(state: dict[str, Any], *, max_iters: int = 20, telemetry: TelemetryController | None = None) -> dict[str, Any]:
    state["loop_iterations"] = int(state.get("loop_iterations") or 0) + 1
    state.setdefault("signals", {})
    if state["loop_iterations"] >= max(1, max_iters - 2):
        set_signal(state, "timeout_risk", True, telemetry)
    if state["loop_iterations"] > max_iters:
        plan = state.get("plan") or []
        state["current_step"] = {}
        state["current_step_index"] = len(plan)
        state["termination_reason"] = "max_iters"
        if telemetry is not None:
            telemetry.trace(
                event="orchestrator_terminate",
                context=log_context_from_state(state, graph_node="orchestrator"),
                data={"reason": "max_iters", "loop_iterations": state["loop_iterations"]},
            )
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
        if telemetry is not None:
            telemetry.trace(
                event="orchestrator_terminate",
                context=log_context_from_state(state, graph_node="orchestrator"),
                data={"reason": "finalized", "loop_iterations": state["loop_iterations"]},
            )
        return state

    state["current_step_index"] = idx
    state["current_step"] = dict(plan[idx])
    if telemetry is not None:
        telemetry.trace(
            event="orchestrator_step",
            context=log_context_from_state(state, graph_node="orchestrator"),
            data={"step_index": idx, "step": dict(plan[idx])},
        )
    return state
