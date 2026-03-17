from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable

from ai_travel_agent.config import Settings
from ai_travel_agent.observability.logger import LogContext, get_logger, log_event
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


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _mapping_candidates(value: Any) -> list[Mapping[str, Any]]:
    candidates: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        candidates.append(value)
        for nested in value.values():
            if isinstance(nested, Mapping):
                candidates.append(nested)
    return candidates


def _extract_usage_metadata(message: Any) -> dict[str, Any]:
    candidates: list[Mapping[str, Any]] = []
    for attr in ("usage_metadata", "response_metadata"):
        candidates.extend(_mapping_candidates(getattr(message, attr, None)))
    if isinstance(message, Mapping):
        candidates.extend(_mapping_candidates(message))

    def pick_int(*keys: str) -> int | None:
        for candidate in candidates:
            for key in keys:
                coerced = _coerce_int(candidate.get(key))
                if coerced is not None:
                    return coerced
        return None

    def pick_float(*keys: str) -> float | None:
        for candidate in candidates:
            for key in keys:
                coerced = _coerce_float(candidate.get(key))
                if coerced is not None:
                    return coerced
        return None

    tokens_in = pick_int("input_tokens", "prompt_tokens", "prompt_eval_count", "input_token_count")
    tokens_out = pick_int("output_tokens", "completion_tokens", "eval_count", "output_token_count")
    tokens_total = pick_int("total_tokens", "total_token_count")
    if tokens_total is None and tokens_in is not None and tokens_out is not None:
        tokens_total = tokens_in + tokens_out
    ttft_ms = pick_float(
        "ttft_ms",
        "time_to_first_token_ms",
        "first_token_latency_ms",
        "latency_to_first_token_ms",
    )
    return {
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_total": tokens_total,
        "tokens_per_request": tokens_total,
        "ttft_ms": round(ttft_ms, 2) if ttft_ms is not None else None,
    }


@dataclass
class LLMClient:
    runnable: Runnable
    metrics: MetricsCollector
    run_id: str
    user_id: str
    model_name: str | None = None
    last_call: dict[str, Any] = field(default_factory=dict)

    def resolve_model_name(self) -> str:
        if self.model_name:
            return self.model_name
        for attr in ("model", "model_name"):
            value = getattr(self.runnable, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "unknown"

    def telemetry_metadata(self) -> dict[str, Any]:
        return {
            "model_name": self.last_call.get("model_name", self.resolve_model_name()),
            "model": self.last_call.get("model_name", self.resolve_model_name()),
            "latency_ms": self.last_call.get("latency_ms"),
            "tokens_in": self.last_call.get("tokens_in"),
            "tokens_out": self.last_call.get("tokens_out"),
            "tokens_total": self.last_call.get("tokens_total"),
            "tokens_per_request": self.last_call.get("tokens_per_request"),
            "ttft_ms": self.last_call.get("ttft_ms"),
        }

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
        try:
            msg = self.runnable.invoke([SystemMessage(content=system), HumanMessage(content=user)])
            usage = _extract_usage_metadata(msg)
            if isinstance(msg, AIMessage):
                out = msg.content or ""
            else:
                out = getattr(msg, "content", None) or str(msg)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self.metrics.observe_ms("llm_latency_ms", elapsed_ms)
            api_snapshot = self.metrics.record_api_request(success=True)
            self.metrics.record_llm_usage(
                tokens_in=usage["tokens_in"],
                tokens_out=usage["tokens_out"],
                tokens_total=usage["tokens_total"],
                ttft_ms=usage["ttft_ms"],
            )
            self.last_call = {
                "system": system,
                "user": user,
                "output": out,
                "latency_ms": round(elapsed_ms, 2),
                "tags": dict(tags or {}),
                "model_name": self.resolve_model_name(),
                **usage,
            }
            log_event(
                logger,
                level=20,
                message="LLM call completed",
                event="llm_call",
                context=context or LogContext(run_id=self.run_id, user_id=self.user_id),
                data={
                    "latency_ms": round(elapsed_ms, 2),
                    "tags": dict(tags or {}),
                    "model_name": self.resolve_model_name(),
                    **usage,
                    **api_snapshot,
                },
            )
            return out
        except Exception as e:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self.metrics.observe_ms("llm_latency_ms", elapsed_ms)
            self.metrics.inc("llm_errors", 1)
            api_snapshot = self.metrics.record_api_request(success=False)
            self.last_call = {
                "system": system,
                "user": user,
                "output": "",
                "latency_ms": round(elapsed_ms, 2),
                "tags": dict(tags or {}),
                "model_name": self.resolve_model_name(),
                "error": str(e),
            }
            log_event(
                logger,
                level=40,
                message="LLM call failed",
                event="llm_error",
                context=context or LogContext(run_id=self.run_id, user_id=self.user_id),
                data={
                    "latency_ms": round(elapsed_ms, 2),
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "tags": dict(tags or {}),
                    "model_name": self.resolve_model_name(),
                    **api_snapshot,
                },
            )
            self.last_call.update(
                {
                    "api_requests_total": api_snapshot.get("api_requests_total"),
                    "api_errors_total": api_snapshot.get("api_errors_total"),
                    "api_error_rate": api_snapshot.get("api_error_rate"),
                }
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
        reasoning_format = None
        model_kwargs: dict[str, Any] = {}
        groq_model = settings.groq_model.strip().lower()
        if groq_model.startswith("openai/gpt-oss"):
            model_kwargs["include_reasoning"] = True
        return ChatGroq(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            temperature=temperature,
            reasoning_format=reasoning_format,
            model_kwargs=model_kwargs,
        )

    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider!r}")
