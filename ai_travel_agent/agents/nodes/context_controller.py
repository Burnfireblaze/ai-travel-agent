from __future__ import annotations

from typing import Any

from ai_travel_agent.memory import MemoryStore
from ai_travel_agent.observability.metrics import MetricsCollector
from ai_travel_agent.observability.telemetry import TelemetryController, set_signal
from ai_travel_agent.observability.fault_injection import FaultInjector
from ai_travel_agent.agents.state import StepType
from .utils import log_context_from_state


def context_controller(
    state: dict[str, Any],
    *,
    memory: MemoryStore,
    metrics: MetricsCollector | None = None,
    telemetry: TelemetryController | None = None,
    fault_injector: FaultInjector | None = None,
) -> dict[str, Any]:
    state["current_step"] = {"step_type": StepType.RETRIEVE_CONTEXT, "title": "Retrieve memory context"}
    state.setdefault("signals", {})
    query = state.get("user_query", "")
    injected = False
    injected_hits = fault_injector.maybe_inject_bad_retrieval(query) if fault_injector else None
    if injected_hits is not None:
        injected = True
        hits = injected_hits
        set_signal(state, "bad_retrieval", True, telemetry)
    else:
        hits = memory.search(query=query, k=5, include_session=True, include_user=True)
    if metrics is not None:
        metrics.set("memory_retrieval_k", 5)
        metrics.set("memory_retrieval_hits", len(hits))
    if not hits:
        set_signal(state, "no_results", True, telemetry)
    if injected:
        state["context_hits"] = hits  # already dict-like
    else:
        state["context_hits"] = [
            {"id": h.id, "text": h.text, "metadata": dict(h.metadata), "distance": h.distance} for h in hits
        ]
    if telemetry is not None:
        telemetry.trace(
            event="context_retrieval",
            context=log_context_from_state(state, graph_node="context_controller"),
            data={
                "query": query,
                "hits": len(hits),
                "injected": injected,
            },
        )
    return state
