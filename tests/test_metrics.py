from __future__ import annotations

import json
from pathlib import Path

from ai_travel_agent.observability.metrics import MetricsCollector


def test_metrics_jsonl_written(tmp_path: Path):
    m = MetricsCollector(runtime_dir=tmp_path, run_id="r1", user_id="u1")
    m.inc("tool_calls", 2)
    m.set("ics_path", "x.ics")
    record = m.finalize_record(status="good", termination_reason="finalized")
    path = m.write(record)

    assert path.exists()
    last = path.read_text(encoding="utf-8").strip().splitlines()[-1]
    payload = json.loads(last)
    assert payload["run_id"] == "r1"
    assert payload["user_id"] == "u1"
    assert payload["status"] == "good"
    assert payload["termination_reason"] == "finalized"
    assert payload["counters"]["tool_calls"] == 2

