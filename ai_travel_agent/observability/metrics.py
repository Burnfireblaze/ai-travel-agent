from __future__ import annotations

import json
import time
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_travel_agent.observability.detectors import PIISummary


_PROCESS_STARTED_AT = time.perf_counter()
_CURRENT_METRICS_COLLECTOR: ContextVar["MetricsCollector | None"] = ContextVar(
    "current_metrics_collector",
    default=None,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def get_current_metrics_collector() -> "MetricsCollector | None":
    return _CURRENT_METRICS_COLLECTOR.get()


def _best_effort_system_uptime_seconds() -> float | None:
    clock_names = ["CLOCK_BOOTTIME", "CLOCK_UPTIME_RAW"]
    for clock_name in clock_names:
        clock_id = getattr(time, clock_name, None)
        if clock_id is None:
            continue
        try:
            return round(float(time.clock_gettime(clock_id)), 2)
        except Exception:
            continue
    try:
        uptime_text = Path("/proc/uptime").read_text(encoding="utf-8").strip().split()[0]
        return round(float(uptime_text), 2)
    except Exception:
        return None


@dataclass
class MetricsCollector:
    runtime_dir: Path
    run_id: str
    user_id: str
    started_at: float = field(default_factory=time.perf_counter)
    counters: dict[str, int] = field(default_factory=dict)
    timers_ms: dict[str, list[float]] = field(default_factory=dict)
    fields: dict[str, Any] = field(default_factory=dict)
    _tokens_in_sum: int = 0
    _tokens_out_sum: int = 0
    _tokens_total_sum: int = 0
    _tokens_in_observations: int = 0
    _tokens_out_observations: int = 0
    _tokens_total_observations: int = 0
    _ttft_values_ms: list[float] = field(default_factory=list)
    _pii_leak_count: int = 0
    _pii_types: set[str] = field(default_factory=set)
    _activation_token: Token | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._activation_token = _CURRENT_METRICS_COLLECTOR.set(self)

    def inc(self, key: str, n: int = 1) -> None:
        self.counters[key] = self.counters.get(key, 0) + n

    def observe_ms(self, key: str, ms: float) -> None:
        self.timers_ms.setdefault(key, []).append(ms)

    def set(self, key: str, value: Any) -> None:
        self.fields[key] = value

    def record_api_request(self, *, success: bool) -> dict[str, Any]:
        self.inc("api_requests_total", 1)
        if not success:
            self.inc("api_errors_total", 1)
        return self.api_snapshot()

    def api_snapshot(self) -> dict[str, Any]:
        api_requests_total = self.counters.get("api_requests_total", 0)
        api_errors_total = self.counters.get("api_errors_total", 0)
        return {
            "api_requests_total": api_requests_total,
            "api_errors_total": api_errors_total,
            "api_error_rate": round(api_errors_total / max(api_requests_total, 1), 4),
        }

    def record_llm_usage(
        self,
        *,
        tokens_in: int | None,
        tokens_out: int | None,
        tokens_total: int | None,
        ttft_ms: float | None,
    ) -> None:
        if tokens_in is not None:
            self._tokens_in_sum += tokens_in
            self._tokens_in_observations += 1
        if tokens_out is not None:
            self._tokens_out_sum += tokens_out
            self._tokens_out_observations += 1
        if tokens_total is not None:
            self._tokens_total_sum += tokens_total
            self._tokens_total_observations += 1
        if ttft_ms is not None:
            self._ttft_values_ms.append(round(ttft_ms, 2))

    def llm_usage_snapshot(self) -> dict[str, Any]:
        avg_tokens_per_request = None
        if self._tokens_total_observations:
            avg_tokens_per_request = round(self._tokens_total_sum / self._tokens_total_observations, 2)
        avg_ttft_ms = None
        if self._ttft_values_ms:
            avg_ttft_ms = round(sum(self._ttft_values_ms) / len(self._ttft_values_ms), 2)
        return {
            "tokens_in": self._tokens_in_sum if self._tokens_in_observations else None,
            "tokens_out": self._tokens_out_sum if self._tokens_out_observations else None,
            "tokens_total": self._tokens_total_sum if self._tokens_total_observations else None,
            "avg_tokens_per_request": avg_tokens_per_request,
            "ttft_ms": avg_ttft_ms,
        }

    def record_pii_detection(self, summary: PIISummary) -> None:
        if not summary.detected:
            return
        self._pii_leak_count += summary.leak_count
        self._pii_types.update(summary.types)

    def pii_snapshot(self) -> dict[str, Any]:
        return {
            "pii_detected": self._pii_leak_count > 0,
            "pii_leak_count": self._pii_leak_count,
            "pii_types": sorted(self._pii_types),
        }

    def timing(self, key: str):
        return _Timer(self, key)

    def _history_path(self) -> Path:
        return (self.runtime_dir / "metrics" / "metrics.jsonl").resolve()

    def _load_history(self) -> list[dict[str, Any]]:
        path = self._history_path()
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                records.append(payload)
        return records

    def _historic_bool(self, record: dict[str, Any], field_name: str) -> bool | None:
        if field_name in record and isinstance(record.get(field_name), bool):
            return record.get(field_name)
        if field_name == "task_completed":
            return record.get("status") == "ok"
        if field_name == "goal_completed":
            return record.get("eval_overall_status") == "good"
        if field_name == "hallucination_detected":
            if isinstance(record.get("hallucination_detected"), bool):
                return record["hallucination_detected"]
            hard_gates = record.get("eval_hard_gates") or {}
            if isinstance(hard_gates, dict):
                return (
                    hard_gates.get("no_fabricated_real_time_facts") is False
                    or hard_gates.get("link_validity_format") is False
                    or hard_gates.get("calendar_export_correctness") is False
                )
        return None

    def finalize_record(self, *, status: str, termination_reason: str | None = None) -> dict[str, Any]:
        total_ms = (time.perf_counter() - self.started_at) * 1000.0
        task_completed = status == "ok"
        goal_completed = self.fields.get("goal_completed")
        if not isinstance(goal_completed, bool):
            goal_completed = self.fields.get("eval_overall_status") == "good"
        hallucination_detected = self.fields.get("hallucination_detected")
        if not isinstance(hallucination_detected, bool):
            hallucination_detected = False

        history = self._load_history()
        prior_task = [self._historic_bool(item, "task_completed") for item in history]
        prior_goal = [self._historic_bool(item, "goal_completed") for item in history]
        prior_hallucination = [self._historic_bool(item, "hallucination_detected") for item in history]
        task_values = [value for value in prior_task if value is not None] + [task_completed]
        goal_values = [value for value in prior_goal if value is not None] + [goal_completed]
        hallucination_values = [value for value in prior_hallucination if value is not None] + [hallucination_detected]

        usage_snapshot = self.llm_usage_snapshot()
        api_snapshot = self.api_snapshot()
        pii_snapshot = self.pii_snapshot()
        record: dict[str, Any] = {
            "timestamp": _utc_now_iso(),
            "run_id": self.run_id,
            "user_id": self.user_id,
            "status": status,
            "termination_reason": termination_reason,
            "total_latency_ms": round(total_ms, 2),
            "counters": dict(self.counters),
            "timers_ms": {k: [round(v, 2) for v in vals] for k, vals in self.timers_ms.items()},
            **self.fields,
            **usage_snapshot,
            **api_snapshot,
            **pii_snapshot,
            "task_completed": task_completed,
            "goal_completed": goal_completed,
            "task_completion_rate": _rate(sum(1 for value in task_values if value), len(task_values)),
            "goal_completion_rate": _rate(sum(1 for value in goal_values if value), len(goal_values)),
            "hallucination_detected": hallucination_detected,
            "hallucination_rate": _rate(
                sum(1 for value in hallucination_values if value),
                len(hallucination_values),
            ),
            "process_uptime_ms": round((time.perf_counter() - _PROCESS_STARTED_AT) * 1000.0, 2),
            "system_uptime_seconds": _best_effort_system_uptime_seconds(),
        }
        return record

    def write(self, record: dict[str, Any]) -> Path:
        metrics_dir = (self.runtime_dir / "metrics").resolve()
        metrics_dir.mkdir(parents=True, exist_ok=True)
        path = metrics_dir / "metrics.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path


class _Timer:
    def __init__(self, collector: MetricsCollector, key: str) -> None:
        self.collector = collector
        self.key = key
        self.start = 0.0

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        ms = (time.perf_counter() - self.start) * 1000.0
        self.collector.observe_ms(self.key, ms)
