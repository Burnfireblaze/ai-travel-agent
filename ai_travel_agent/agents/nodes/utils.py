from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from ai_travel_agent.observability.logger import LogContext, get_logger, log_event
from ai_travel_agent.observability.metrics import MetricsCollector


logger = get_logger(__name__)


def log_context_from_state(state: dict[str, Any], *, graph_node: str) -> LogContext:
    step = state.get("current_step") or {}
    return LogContext(
        run_id=state.get("run_id"),
        user_id=state.get("user_id"),
        graph_node=graph_node,
        step_type=step.get("step_type"),
        step_id=step.get("id"),
        step_title=step.get("title"),
    )


def instrument_node(
    *,
    node_name: str,
    metrics: MetricsCollector,
    fn: Callable[[dict[str, Any]], dict[str, Any]],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def wrapped(state: dict[str, Any]) -> dict[str, Any]:
        state["current_node"] = node_name
        ctx = log_context_from_state(state, graph_node=node_name)
        log_event(logger, level=logging.INFO, message="Node enter", event="node_enter", context=ctx)
        metrics.inc("graph_node_transitions", 1)

        started = time.perf_counter()
        try:
            out = fn(state)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            metrics.observe_ms(f"node_latency_ms.{node_name}", elapsed_ms)
            log_event(
                logger,
                level=logging.INFO,
                message="Node exit",
                event="node_exit",
                context=log_context_from_state(out or state, graph_node=node_name),
                data={"latency_ms": round(elapsed_ms, 2)},
            )
            return out
        except Exception as e:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            metrics.observe_ms(f"node_latency_ms.{node_name}", elapsed_ms)
            metrics.inc("graph_node_errors", 1)
            log_event(
                logger,
                level=logging.ERROR,
                message="Node error",
                event="node_error",
                context=ctx,
                data={"latency_ms": round(elapsed_ms, 2), "error": str(e)},
            )
            raise

    return wrapped
