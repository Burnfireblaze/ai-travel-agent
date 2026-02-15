from __future__ import annotations

import logging
from typing import Any

from ai_travel_agent.agents.state import StepType
from ai_travel_agent.agents.state import Issue, IssueKind, IssueSeverity
from ai_travel_agent.evaluation import evaluate_final
from ai_travel_agent.observability.logger import get_logger, log_event

from .utils import log_context_from_state


logger = get_logger(__name__)


def evaluate_step(state: dict[str, Any]) -> dict[str, Any]:
    step = state.get("current_step") or {}
    if not step:
        return state
    # MVP: shallow checks only
    if step.get("step_type") == StepType.TOOL_CALL:
        tool_results = state.get("tool_results") or []
        ok = any(r.get("step_id") == step.get("id") for r in tool_results)
        if not ok:
            state["termination_reason"] = "error"
    log_event(
        logger,
        level=logging.INFO,
        message="Step evaluated",
        event="eval_step",
        context=log_context_from_state(state, graph_node="evaluate_step"),
        data={"ok": state.get("termination_reason") != "error"},
    )
    return state


def evaluate_final_node(state: dict[str, Any], *, eval_threshold: float) -> dict[str, Any]:
    state["current_step"] = {"step_type": StepType.EVALUATE_FINAL, "title": "Evaluate final response"}
    ics_path = state.get("ics_path")
    ics_bytes = None
    if ics_path:
        try:
            from pathlib import Path

            ics_bytes = Path(ics_path).read_bytes()
        except Exception:
            ics_bytes = None
    result = evaluate_final(
        constraints=state.get("constraints") or {},
        final_answer=state.get("final_answer", ""),
        ics_bytes=ics_bytes,
        eval_threshold=eval_threshold,
    )
    state["evaluation"] = result.model_dump()
    state.setdefault("issues", [])
    if result.overall_status == "failed":
        state["issues"].append(
            Issue(
                kind=IssueKind.EVALUATION_FAIL,
                severity=IssueSeverity.MAJOR,
                node="evaluate_final",
                message="Final output failed one or more hard gates.",
                details={"hard_gates": result.hard_gates, "rubric_scores": result.rubric_scores},
            ).model_dump()
        )
    log_event(
        logger,
        level=logging.INFO,
        message="Final evaluation completed",
        event="eval_final",
        context=log_context_from_state(state, graph_node="evaluate_final"),
        data={"overall_status": result.overall_status, "hard_gates": result.hard_gates, "rubric": result.rubric_scores},
    )
    return state
