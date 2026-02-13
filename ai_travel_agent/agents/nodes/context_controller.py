from __future__ import annotations

from typing import Any

from ai_travel_agent.memory import MemoryStore
from ai_travel_agent.observability.metrics import MetricsCollector
from ai_travel_agent.agents.state import StepType


def context_controller(state: dict[str, Any], *, memory: MemoryStore, metrics: MetricsCollector | None = None) -> dict[str, Any]:
    state["current_step"] = {"step_type": StepType.RETRIEVE_CONTEXT, "title": "Retrieve memory context"}
    query = state.get("user_query", "")
    hits = memory.search(query=query, k=5, include_session=True, include_user=True)
    if metrics is not None:
        metrics.set("memory_retrieval_k", 5)
        metrics.set("memory_retrieval_hits", len(hits))
    state["context_hits"] = [
        {"id": h.id, "text": h.text, "metadata": dict(h.metadata), "distance": h.distance} for h in hits
    ]
    return state
