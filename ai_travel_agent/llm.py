from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable

from ai_travel_agent.config import Settings
from ai_travel_agent.observability.telemetry import TelemetryController
from ai_travel_agent.observability.fault_injection import FaultInjector
from ai_travel_agent.observability.logger import LogContext, get_logger, log_event
from ai_travel_agent.observability.metrics import MetricsCollector


logger = get_logger(__name__)


@dataclass
class LLMClient:
    runnable: Runnable
    metrics: MetricsCollector
    run_id: str
    user_id: str
    telemetry: TelemetryController | None = None
    fault_injector: FaultInjector | None = None
    name: str = "llm"

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
            if self.fault_injector is not None:
                self.fault_injector.maybe_inject_llm_error(self.name)
            if self.telemetry is not None:
                self.telemetry.trace(
                    event="llm_request",
                    context=context or LogContext(run_id=self.run_id, user_id=self.user_id),
                    data={
                        "name": self.name,
                        "system": system,
                        "user": user,
                        "tags": dict(tags or {}),
                    },
                )
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
            if self.telemetry is not None:
                self.telemetry.trace(
                    event="llm_response",
                    context=context or LogContext(run_id=self.run_id, user_id=self.user_id),
                    data={
                        "name": self.name,
                        "output": out,
                        "tags": dict(tags or {}),
                        "latency_ms": round(elapsed_ms, 2),
                    },
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
            if self.telemetry is not None:
                self.telemetry.trace(
                    event="llm_error",
                    context=context or LogContext(run_id=self.run_id, user_id=self.user_id),
                    data={
                        "name": self.name,
                        "error": str(e),
                        "tags": dict(tags or {}),
                        "latency_ms": round(elapsed_ms, 2),
                    },
                )
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
