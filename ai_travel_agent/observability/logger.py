
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
from dataclasses import dataclass
from datetime import datetime, timezone
from logging import Handler, LogRecord
from pathlib import Path
from typing import Any, Mapping


SENSITIVE_KEY_PATTERN = re.compile(r"(api[_-]?key|authorization|token|secret|password)", re.IGNORECASE)


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


class JsonlHandler(Handler):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, record: LogRecord) -> None:
        try:
            payload: dict[str, Any] = {
                "timestamp": _utc_now_iso(),
                "level": record.levelname,
                "module": record.name,
                "message": record.getMessage(),
            }

            for key in ("run_id", "user_id", "graph_node", "step_type", "step_id", "step_title", "event", "data"):
                if hasattr(record, key):
                    payload[key] = getattr(record, key)

            if "data" in payload:
                payload["data"] = _sanitize(payload["data"])

            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            self.handleError(record)


class TextFormatter(logging.Formatter):
    def format(self, record: LogRecord) -> str:
        base = super().format(record)
        extras: list[str] = []
        for key in ("run_id", "graph_node", "step_type", "step_id"):
            if hasattr(record, key) and getattr(record, key):
                extras.append(f"{key}={getattr(record, key)}")
        if hasattr(record, "event") and getattr(record, "event"):
            extras.append(f"event={getattr(record, 'event')}")
        if extras:
            return f"{base} [{' '.join(extras)}]"
        return base


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

    # Add a handler for all normal logs (INFO and above) to a separate file
    normal_log_path = logs_dir / "normal.log"
    normal_handler = logging.FileHandler(normal_log_path, encoding="utf-8")
    normal_handler.setLevel(logging.INFO)
    normal_handler.setFormatter(TextFormatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
    root.addHandler(normal_handler)

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
    if context:
        extra.update(
            {
                "run_id": context.run_id,
                "user_id": context.user_id,
                "graph_node": context.graph_node,
                "step_type": context.step_type,
                "step_id": context.step_id,
                "step_title": context.step_title,
            }
        )
    if data is not None:
        extra["data"] = dict(data)
    logger.log(level, message, extra=extra)
    _write_combined_log_event(
        level=level,
        module=logger.name,
        message=message,
        event=event,
        context=context,
        data=data,
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

        payload: dict[str, Any] = {
            "timestamp": _utc_now_iso(),
            "level": logging.getLevelName(level),
            "module": module,
            "message": message,
            "run_id": tracker.run_id,
            "user_id": tracker.user_id,
            "event": event,
            "kind": "normal",
        }
        if context:
            payload.update(
                {
                    "graph_node": context.graph_node,
                    "step_type": context.step_type,
                    "step_id": context.step_id,
                    "step_title": context.step_title,
                }
            )
        if data is not None:
            payload["data"] = _sanitize(dict(data))

        with tracker.combined_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        # Telemetry logging must never break application flow.
        return
