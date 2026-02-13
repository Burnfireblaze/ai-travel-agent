from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable

from ai_travel_agent.observability.logger import LogContext, get_logger, log_event
from ai_travel_agent.observability.metrics import MetricsCollector


logger = get_logger(__name__)


@dataclass
class LLMClient:
    runnable: Runnable
    metrics: MetricsCollector
    run_id: str
    user_id: str

    def invoke_text(
        self,
        *,
        system: str,
        user: str,
        context: LogContext | None = None,
        tags: Mapping[str, Any] | None = None,
    ) -> str:
        started = time.perf_counter()
        self.metrics.inc("llm_calls", 1)
        try:
            msg = self.runnable.invoke([SystemMessage(content=system), HumanMessage(content=user)])
            if isinstance(msg, AIMessage):
                out = msg.content or ""
            else:
                out = getattr(msg, "content", None) or str(msg)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self.metrics.observe_ms("llm_latency_ms", elapsed_ms)
            log_event(
                logger,
                level=20,
                message="LLM call completed",
                event="llm_call",
                context=context or LogContext(run_id=self.run_id, user_id=self.user_id),
                data={"latency_ms": round(elapsed_ms, 2), "tags": dict(tags or {})},
            )
            return out
        except Exception as e:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self.metrics.observe_ms("llm_latency_ms", elapsed_ms)
            self.metrics.inc("llm_errors", 1)
            log_event(
                logger,
                level=40,
                message="LLM call failed",
                event="llm_error",
                context=context or LogContext(run_id=self.run_id, user_id=self.user_id),
                data={"latency_ms": round(elapsed_ms, 2), "error": str(e), "tags": dict(tags or {})},
            )
            raise
