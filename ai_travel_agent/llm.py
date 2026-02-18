from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable

from ai_travel_agent.config import Settings
from ai_travel_agent.observability.logger import LogContext, get_logger, log_event, TELEMETRY
# Failure tracking imports
try:
    from ai_travel_agent.observability.failure_tracker import (
        FailureCategory, FailureSeverity, get_failure_tracker
    )
    FAILURE_TRACKING_AVAILABLE = True
except ImportError:
    FAILURE_TRACKING_AVAILABLE = False
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
        state: dict | None = None,
    ) -> str:
        started = time.perf_counter()
        self.metrics.inc("llm_calls", 1)
        # Full trace logging: always log inputs in detailed mode
        if state is not None and TELEMETRY.should_log_detailed(state):
            log_event(
                logger,
                level=20,
                message="LLM input",
                event="llm_input",
                context=context or LogContext(run_id=self.run_id, user_id=self.user_id),
                data={"system": system, "user": user, "tags": dict(tags or {})},
            )
        try:
            msg = self.runnable.invoke([SystemMessage(content=system), HumanMessage(content=user)])
            if isinstance(msg, AIMessage):
                out = msg.content or ""
            else:
                out = getattr(msg, "content", None) or str(msg)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self.metrics.observe_ms("llm_latency_ms", elapsed_ms)
            # Full trace logging: always log outputs in detailed mode
            if state is not None and TELEMETRY.should_log_detailed(state):
                log_event(
                    logger,
                    level=20,
                    message="LLM output",
                    event="llm_output",
                    context=context or LogContext(run_id=self.run_id, user_id=self.user_id),
                    data={"output": out, "latency_ms": round(elapsed_ms, 2), "tags": dict(tags or {})},
                )
            else:
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
            # In detailed mode, log error as well
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self.metrics.observe_ms("llm_latency_ms", elapsed_ms)
            self.metrics.inc("llm_errors", 1)
            if state is not None and TELEMETRY.should_log_detailed(state):
                log_event(
                    logger,
                    level=40,
                    message="LLM error",
                    event="llm_error",
                    context=context or LogContext(run_id=self.run_id, user_id=self.user_id),
                    data={"latency_ms": round(elapsed_ms, 2), "error": str(e), "tags": dict(tags or {})},
                )
            else:
                log_event(
                    logger,
                    level=40,
                    message="LLM call failed",
                    event="llm_error",
                    context=context or LogContext(run_id=self.run_id, user_id=self.user_id),
                    data={"latency_ms": round(elapsed_ms, 2), "error": str(e), "tags": dict(tags or {})},
                )
            # Track LLM failures
            if FAILURE_TRACKING_AVAILABLE:
                tracker = get_failure_tracker()
                if tracker:
                    try:
                        tracker.record_failure(
                            category=FailureCategory.LLM,
                            severity=FailureSeverity.HIGH,
                            graph_node="llm",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            step_id=None,
                            step_type="LLM_CALL",
                            step_title="LLM invocation",
                            llm_model=getattr(self.runnable, 'model', None),
                            context_data={"system": system, "user": user},
                            tags=["auto-tracked", "llm-failure"],
                        )
                    except Exception:
                        pass
            raise
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
            # Track LLM failures
            if FAILURE_TRACKING_AVAILABLE:
                tracker = get_failure_tracker()
                if tracker:
                    try:
                        tracker.record_failure(
                            category=FailureCategory.LLM,
                            severity=FailureSeverity.HIGH,
                            graph_node="llm",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            step_id=None,
                            step_type="LLM_CALL",
                            step_title="LLM invocation",
                            llm_model=getattr(self.runnable, 'model', None),
                            context_data={"system": system, "user": user},
                            tags=["auto-tracked", "llm-failure"],
                        )
                    except Exception:
                        pass
            raise


def build_chat_model(
    *,
    settings: Settings,
    json_mode: bool,
    temperature: float,
) -> Runnable:
    provider = settings.llm_provider.strip().lower()
    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except Exception:  # pragma: no cover
            from langchain_community.chat_models import ChatOllama

        return ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=temperature,
            format="json" if json_mode else None,
        )

    if provider == "groq":
        try:
            from langchain_groq import ChatGroq
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("Missing dependency: langchain-groq") from exc
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is required when LLM_PROVIDER=groq.")
        return ChatGroq(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            temperature=temperature,
        )

    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider!r}")
