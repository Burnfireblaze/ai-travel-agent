from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .logger import LogContext


_MINIMAL_EVENTS = {
    "intent_parse",
    "validated_constraints",
    "plan",
    "plan_fallback",
    "tool_result",
    "synth_result",
    "final_answer",
    "eval_final",
    "export_ics",
    "issue_triage",
    "run_error",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(value: Any, max_chars: int) -> Any:
    if max_chars <= 0:
        return value
    if isinstance(value, str):
        if len(value) <= max_chars:
            return value
        return value[: max_chars - 1] + "…"
    if isinstance(value, list):
        return [_truncate(v, max_chars) for v in value]
    if isinstance(value, dict):
        return {k: _truncate(v, max_chars) for k, v in value.items()}
    return value


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k).lower()
            if any(tok in key for tok in ["api_key", "apikey", "authorization", "token", "secret", "password"]):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = _sanitize(v)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    return value


@dataclass
class TelemetryController:
    runtime_dir: Path
    run_id: str
    user_id: str
    mode: str = "minimal"
    max_chars: int = 2000
    buffer_size: int = 50
    _buffer: list[dict[str, Any]] = field(default_factory=list)
    _escalated: bool = False
    _trace_path: Path | None = None

    def __post_init__(self) -> None:
        logs_dir = (self.runtime_dir / "logs").resolve()
        logs_dir.mkdir(parents=True, exist_ok=True)
        self._trace_path = logs_dir / "trace.jsonl"

    def set_mode(self, mode: str) -> None:
        self.mode = (mode or "minimal").strip().lower()

    def maybe_escalate(self, signals: Mapping[str, Any] | None) -> None:
        if self.mode != "selective" or self._escalated:
            return
        if signals and any(bool(v) for v in signals.values()):
            self._escalated = True
            for payload in self._buffer:
                self._write(payload)
            self._buffer.clear()

    def set_signal(self, state: dict[str, Any], key: str, value: bool = True) -> None:
        signals = state.setdefault("signals", {})
        signals[key] = value
        self.maybe_escalate(signals)

    def trace(
        self,
        *,
        event: str,
        data: Mapping[str, Any] | None = None,
        context: LogContext | None = None,
    ) -> None:
        level = "ERROR" if "error" in event else "INFO"
        payload: dict[str, Any] = {
            "timestamp": _utc_now_iso(),
            "level": level,
            "module": "telemetry",
            "event": event,
            "message": event,
            "run_id": self.run_id,
            "user_id": self.user_id,
            "component": context.graph_node if context and context.graph_node else "telemetry",
            "graph_node": context.graph_node if context else None,
            "step_type": context.step_type if context else None,
            "step_id": context.step_id if context else None,
            "step_title": context.step_title if context else None,
        }
        if data is not None:
            payload["data"] = _truncate(_sanitize(dict(data)), self.max_chars)
        else:
            payload["data"] = None

        if self.mode == "minimal":
            if event not in _MINIMAL_EVENTS and not event.endswith("_error"):
                return
            self._write(payload)
            return
        if self.mode == "detailed" or self._escalated:
            self._write(payload)
        elif self.mode == "selective":
            self._buffer.append(payload)
            if len(self._buffer) > self.buffer_size:
                self._buffer = self._buffer[-self.buffer_size :]

    def _write(self, payload: Mapping[str, Any]) -> None:
        if not self._trace_path:
            return
        with self._trace_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def trace_path(self) -> Path | None:
        return self._trace_path


def set_signal(state: dict[str, Any], key: str, value: bool = True, telemetry: TelemetryController | None = None) -> None:
    signals = state.setdefault("signals", {})
    signals[key] = value
    if telemetry is not None:
        telemetry.maybe_escalate(signals)
