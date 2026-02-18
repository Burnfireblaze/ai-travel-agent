from __future__ import annotations

import logging
from ai_travel_agent.observability.logger import get_logger, log_event
from ai_travel_agent.agents.nodes.utils import log_context_from_state
from typing import Any

from typing import Any


def orchestrator(state: dict[str, Any], *, max_iters: int = 20) -> dict[str, Any]:
    logger = get_logger(__name__)
    state["loop_iterations"] = int(state.get("loop_iterations") or 0) + 1
    # Signal timeout risk if approaching max_iters
    if "signals" not in state:
        state["signals"] = {}
    if state["loop_iterations"] > int(0.8 * max_iters):
        state["signals"]["timeout_risk"] = True
    if state["loop_iterations"] > max_iters:
        plan = state.get("plan") or []
        state["current_step"] = {}
        state["current_step_index"] = len(plan)
        state["termination_reason"] = "max_iters"
        log_event(
            logger,
            level=logging.INFO,
            message="Plan terminated: max iterations exceeded",
            event="plan_terminated",
            context=log_context_from_state(state, graph_node="orchestrator"),
            data={"loop_iterations": state["loop_iterations"]},
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
        log_event(
            logger,
            level=logging.INFO,
            message="Plan finalized: all steps complete or blocked",
            event="plan_finalized",
            context=log_context_from_state(state, graph_node="orchestrator"),
            data={"loop_iterations": state["loop_iterations"]},
        )
        return state

    state["current_step_index"] = idx
    state["current_step"] = dict(plan[idx])
    log_event(
        logger,
        level=logging.INFO,
        message=f"Step selected: {plan[idx].get('title', plan[idx].get('id', ''))}",
        event="step_selected",
        context=log_context_from_state(state, graph_node="orchestrator"),
        data={"step": plan[idx]},
    )
    return state
