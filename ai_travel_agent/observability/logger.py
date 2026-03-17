
from __future__ import annotations

# Telemetry controller for selective logging
class TelemetryController:
    def __init__(self):
        self.mode = "MINIMAL"  # or "DETAILED"

    def set_mode(self, mode: str):
        self.mode = mode.upper()

    def get_mode(self) -> str:
        return self.mode

    def should_log_detailed(self, state: dict) -> bool:
        # Switch to detailed if any failure signal is set
        signals = state.get("signals", {})
        if self.mode == "DETAILED":
            return True
        if any(signals.get(sig) for sig in ["tool_error", "no_results", "memory_unavailable", "timeout_risk"]):
            self.set_mode("DETAILED")
            return True
        return False

TELEMETRY = TelemetryController()

import json
import logging
import os
import re
from dataclasses import replace
from dataclasses import dataclass
from datetime import datetime, timezone
from logging import Handler, LogRecord
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from ai_travel_agent.observability.canonical_schema import build_canonical_record
from ai_travel_agent.observability.detectors import detect_pii

# Redact secret-looking keys, but do not redact common telemetry like `tokens_in`/`prompt_tokens`.
# The previous pattern matched the substring "token" inside "tokens_*" and hid useful metrics.
SENSITIVE_KEY_PATTERN = re.compile(
    r"(?:^|[_-])(?:api[_-]?key|authorization|access[_-]?token|refresh[_-]?token|id[_-]?token|token|secret|password)(?:$|[_-])",
    re.IGNORECASE,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, val in value.items():
            if SENSITIVE_KEY_PATTERN.search(str(key)):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = _sanitize(val)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    return value


@dataclass(frozen=True)
class LogContext:
    run_id: str | None = None
    user_id: str | None = None
    graph_node: str | None = None
    step_type: str | None = None
    step_id: str | None = None
    step_title: str | None = None
    step_index: int | None = None
    iteration_count: int | None = None


class JsonlHandler(Handler):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._run_event_counters: dict[str, int] = {}

    def emit(self, record: LogRecord) -> None:
        try:
            event = getattr(record, "event", "log")
            data = dict(getattr(record, "data", None) or {})
            run_id = getattr(record, "run_id", None)
            counter_key = run_id or "unknown"
            next_index = self._run_event_counters.get(counter_key, 0) + 1
            self._run_event_counters[counter_key] = next_index
            data.setdefault("telemetry_event_index", next_index)
            if event == "run_end":
                data["telemetry_events_total"] = next_index
            payload = build_canonical_record(
                ts=_utc_now_iso(),
                level=record.levelname,
                module=record.name,
                message=record.getMessage(),
                event=event,
                run_id=run_id,
                user_id=getattr(record, "user_id", None),
                node=getattr(record, "graph_node", None),
                step_type=getattr(record, "step_type", None),
                step_id=getattr(record, "step_id", None),
                step_title=getattr(record, "step_title", None),
                kind=getattr(record, "kind", "normal"),
                data=_sanitize(data) if data else None,
            )

            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            self.handleError(record)


class TextFormatter(logging.Formatter):
    def format(self, record: LogRecord) -> str:
        first_line = super().format(record)
        run_id = getattr(record, "run_id", None)
        trace_id = getattr(record, "trace_id", None)
        span_id = getattr(record, "span_id", None)
        node = getattr(record, "graph_node", None) or getattr(record, "node", None)
        event = getattr(record, "event", None)
        step_id = getattr(record, "step_id", None)
        meta_line = (
            f"[run_id={run_id or 'null'} trace_id={trace_id or 'null'} "
            f"span_id={span_id or 'null'} node={node or 'null'} "
            f"event={event or 'null'} step_id={step_id or 'null'}]"
        )
        data_payload = getattr(record, "data", None)
        try:
            data_json = json.dumps(_sanitize(data_payload), ensure_ascii=False)
        except Exception:
            data_json = "null"
        return f"{first_line}\n{meta_line}\ndata={data_json}"


def setup_logging(*, runtime_dir: Path, level: str = "INFO") -> None:
    runtime_dir = runtime_dir.resolve()
    logs_dir = runtime_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = logs_dir / "app.jsonl"
    text_path = logs_dir / "app.log"

    root = logging.getLogger()
    root.handlers.clear()

    log_level = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(log_level)

    jsonl_handler = JsonlHandler(jsonl_path)
    jsonl_handler.setLevel(log_level)
    root.addHandler(jsonl_handler)

    text_handler = logging.FileHandler(text_path, encoding="utf-8")
    text_handler.setLevel(log_level)
    text_handler.setFormatter(TextFormatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
    root.addHandler(text_handler)

    console_level = os.environ.get("CONSOLE_LOG_LEVEL", "WARNING")
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, console_level.upper(), logging.WARNING))
    console_handler.setFormatter(TextFormatter("%(levelname)s %(name)s - %(message)s"))
    root.addHandler(console_handler)

    # Keep third-party noise down even when app log level is INFO.
    for noisy in [
        "httpx",
        "httpcore",
        "chromadb.telemetry",
        "chromadb.telemetry.product.posthog",
        "sentence_transformers",
        "urllib3",
        "asyncio",
    ]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(
    logger: logging.Logger,
    *,
    level: int,
    message: str,
    event: str,
    context: LogContext | None = None,
    data: Mapping[str, Any] | None = None,
) -> None:
    extra: dict[str, Any] = {"event": event}
    payload = dict(data) if data is not None else {}
    if context:
        extra.update(
            {
                "run_id": context.run_id,
                "user_id": context.user_id,
                "graph_node": context.graph_node,
                "step_type": context.step_type,
                "step_id": context.step_id,
                "step_title": context.step_title,
                "step_index": context.step_index,
                "iteration_count": context.iteration_count,
            }
        )
        if context.step_index is not None and payload.get("step_index") is None:
            payload["step_index"] = context.step_index
        if context.iteration_count is not None and payload.get("iteration_count") is None:
            payload["iteration_count"] = context.iteration_count
    run_id = extra.get("run_id") or payload.get("run_id")
    trace_id = payload.get("trace_id") or run_id
    if trace_id is not None and payload.get("trace_id") is None:
        payload["trace_id"] = trace_id
    span_id = payload.get("span_id")
    if not span_id:
        span_id = f"{event}-{uuid4().hex[:12]}"
        payload["span_id"] = span_id
    extra["trace_id"] = trace_id
    extra["span_id"] = span_id
    if payload:
        extra["data"] = payload
    logger.log(level, message, extra=extra)
    _write_combined_log_event(
        level=level,
        module=logger.name,
        message=message,
        event=event,
        context=context,
        data=payload if payload else None,
    )


def _write_combined_log_event(
    *,
    level: int,
    module: str,
    message: str,
    event: str,
    context: LogContext | None,
    data: Mapping[str, Any] | None,
) -> None:
    """Best-effort mirror of normal events into run-level combined log."""
    try:
        # Local import to avoid cross-module import cycles.
        from ai_travel_agent.observability.failure_tracker import get_failure_tracker

        tracker = get_failure_tracker()
        if tracker is None:
            return

        context_run_id = context.run_id if context else None
        if context_run_id and context_run_id != tracker.run_id:
            return

        payload = build_canonical_record(
            ts=_utc_now_iso(),
            level=logging.getLevelName(level),
            module=module,
            message=message,
            event=event,
            run_id=tracker.run_id,
            user_id=tracker.user_id,
            node=context.graph_node if context else None,
            step_type=context.step_type if context else None,
            step_id=context.step_id if context else None,
            step_title=context.step_title if context else None,
            kind="normal",
            data=_sanitize(dict(data)) if data is not None else None,
        )

        with tracker.combined_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        # Telemetry logging must never break application flow.
        return


def log_llm_event(
    node_name,
    llm_input,
    llm_output,
    metadata,
    *,
    logger: logging.Logger | None = None,
    context: LogContext | None = None,
) -> None:
    pii_summary = detect_pii(llm_input, llm_output)
    payload = {
        "node_name": node_name,
        "llm_input": llm_input,
        "llm_output": llm_output,
        "model_name": metadata.get("model_name"),
        "model": metadata.get("model_name") or metadata.get("model"),
        "latency_ms": metadata.get("latency_ms"),
        "tokens_in": metadata.get("tokens_in"),
        "tokens_out": metadata.get("tokens_out"),
        "tokens_total": metadata.get("tokens_total"),
        "tokens_per_request": metadata.get("tokens_per_request"),
        "ttft_ms": metadata.get("ttft_ms"),
        "intent_decision": metadata.get("intent_decision"),
        "validation_decision": metadata.get("validation_decision"),
        "planner_decision": metadata.get("planner_decision"),
        "tool_selected": metadata.get("tool_selected"),
        "synthesis_decision": metadata.get("synthesis_decision"),
        **pii_summary.as_payload(),
    }
    for key, value in metadata.items():
        payload.setdefault(key, value)

    try:
        from ai_travel_agent.observability.metrics import get_current_metrics_collector

        collector = get_current_metrics_collector()
        if collector is not None:
            collector.record_pii_detection(pii_summary)
    except Exception:
        pass

    resolved_context = context
    if resolved_context is None:
        resolved_context = LogContext(graph_node=node_name)
    elif resolved_context.graph_node != node_name:
        resolved_context = replace(resolved_context, graph_node=node_name)

    try:
        log_event(
            logger or get_logger(__name__),
            level=logging.INFO,
            message=f"LLM trace captured for {node_name}",
            event="llm_trace",
            context=resolved_context,
            data=payload,
        )
    except Exception:
        return
