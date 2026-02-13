from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MetricsCollector:
    runtime_dir: Path
    run_id: str
    user_id: str
    started_at: float = field(default_factory=time.perf_counter)
    counters: dict[str, int] = field(default_factory=dict)
    timers_ms: dict[str, list[float]] = field(default_factory=dict)
    fields: dict[str, Any] = field(default_factory=dict)

    def inc(self, key: str, n: int = 1) -> None:
        self.counters[key] = self.counters.get(key, 0) + n

    def observe_ms(self, key: str, ms: float) -> None:
        self.timers_ms.setdefault(key, []).append(ms)

    def set(self, key: str, value: Any) -> None:
        self.fields[key] = value

    def timing(self, key: str):
        return _Timer(self, key)

    def finalize_record(self, *, status: str, termination_reason: str | None = None) -> dict[str, Any]:
        total_ms = (time.perf_counter() - self.started_at) * 1000.0
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

