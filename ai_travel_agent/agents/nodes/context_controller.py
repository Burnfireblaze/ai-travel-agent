from __future__ import annotations

import logging
from typing import Any

from ai_travel_agent.memory import MemoryStore
from ai_travel_agent.observability.logger import get_logger, log_event
from ai_travel_agent.observability.metrics import MetricsCollector
from ai_travel_agent.agents.state import StepType
from .utils import log_context_from_state


logger = get_logger(__name__)


def context_controller(state: dict[str, Any], *, memory: MemoryStore, metrics: MetricsCollector | None = None) -> dict[str, Any]:
    state["current_step"] = {"step_type": StepType.RETRIEVE_CONTEXT, "title": "Retrieve memory context"}
    query = state.get("user_query", "")
    log_event(
        logger,
        level=logging.INFO,
        message="RAG retrieval started",
        event="rag_retrieve_start",
        context=log_context_from_state(state, graph_node="context_controller"),
        data={"query_chars": len(query), "k": 5, "include_session": True, "include_user": True},
    )
    hits = memory.search(query=query, k=5, include_session=True, include_user=True)
    if metrics is not None:
        metrics.set("memory_retrieval_k", 5)
        metrics.set("memory_retrieval_hits", len(hits))
    log_event(
        logger,
        level=logging.INFO,
        message="RAG retrieval completed",
        event="rag_retrieve",
        context=log_context_from_state(state, graph_node="context_controller"),
        data={"hits": len(hits)},
    )
    state["context_hits"] = [
        {"id": h.id, "text": h.text, "metadata": dict(h.metadata), "distance": h.distance} for h in hits
    ]
    log_event(
        logger,
        level=logging.INFO,
        message="RAG context hits stored",
        event="rag_context_stored",
        context=log_context_from_state(state, graph_node="context_controller"),
        data={"stored_hits": len(state["context_hits"])},
    )
    return state
