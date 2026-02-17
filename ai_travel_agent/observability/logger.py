from __future__ import annotations

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
                "run_id": None,
                "user_id": None,
                "graph_node": None,
                "step_type": None,
                "step_id": None,
                "step_title": None,
                "event": None,
                "data": None,
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
