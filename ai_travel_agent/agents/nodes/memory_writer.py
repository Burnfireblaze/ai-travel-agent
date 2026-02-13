from __future__ import annotations

import json
from typing import Any

from ai_travel_agent.memory import MemoryStore
from ai_travel_agent.observability.metrics import MetricsCollector
from ai_travel_agent.agents.state import StepType


def memory_writer(
    state: dict[str, Any],
    *,
    memory: MemoryStore,
    metrics: MetricsCollector | None = None,
) -> dict[str, Any]:
    state["current_step"] = {"step_type": StepType.WRITE_MEMORY, "title": "Write memory summaries"}
    run_id = state.get("run_id", "")
    constraints = state.get("constraints") or {}
    tool_results = state.get("tool_results") or []

    # Persistent: store stable preferences + trip summary
    interests = constraints.get("interests") or []
    if interests:
        memory.add_user(text=f"User interests: {', '.join(interests)}", run_id=run_id, doc_type="preference")
        if metrics is not None:
            metrics.inc("memory_written_user_docs", 1)
    if constraints.get("origin"):
        memory.add_user(text=f"Home origin: {constraints.get('origin')}", run_id=run_id, doc_type="profile")
        if metrics is not None:
            metrics.inc("memory_written_user_docs", 1)

    summary = {
        "query": state.get("user_query", ""),
        "constraints": constraints,
        "evaluation": state.get("evaluation"),
    }
    memory.add_user(text="Trip summary: " + json.dumps(summary, ensure_ascii=False), run_id=run_id, doc_type="trip_summary")
    if metrics is not None:
        metrics.inc("memory_written_user_docs", 1)

    # Session: store tool outputs
    for tr in tool_results:
        memory.add_session(text="Tool output: " + json.dumps(tr, ensure_ascii=False), run_id=run_id, doc_type="tool_output")
        if metrics is not None:
            metrics.inc("memory_written_session_docs", 1)
    return state
