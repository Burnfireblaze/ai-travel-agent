from __future__ import annotations

import json
from pathlib import Path

from ai_travel_agent.observability.detectors import PIISummary
from ai_travel_agent.observability.metrics import MetricsCollector


def test_metrics_jsonl_written(tmp_path: Path):
    m = MetricsCollector(runtime_dir=tmp_path, run_id="r1", user_id="u1")
    m.inc("tool_calls", 2)
    m.record_api_request(success=True)
    m.record_llm_usage(tokens_in=10, tokens_out=5, tokens_total=15, ttft_ms=25.0)
    m.record_pii_detection(PIISummary(detected=True, leak_count=2, types=("email", "phone")))
    m.set("ics_path", "x.ics")
    m.set("eval_overall_status", "good")
    m.set("hallucination_detected", False)
    metrics_dir = tmp_path / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    (metrics_dir / "metrics.jsonl").write_text(
        json.dumps(
            {
                "run_id": "prior",
                "status": "ok",
                "task_completed": True,
                "goal_completed": False,
                "hallucination_detected": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
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
    assert payload["api_requests_total"] == 1
    assert payload["api_errors_total"] == 0
    assert payload["api_error_rate"] == 0.0
    assert payload["tokens_in"] == 10
    assert payload["tokens_out"] == 5
    assert payload["tokens_total"] == 15
    assert payload["avg_tokens_per_request"] == 15.0
    assert payload["ttft_ms"] == 25.0
    assert payload["task_completed"] is False
    assert payload["goal_completed"] is True
    assert payload["task_completion_rate"] == 0.5
    assert payload["goal_completion_rate"] == 0.5
    assert payload["hallucination_detected"] is False
    assert payload["hallucination_rate"] == 0.5
    assert payload["pii_detected"] is True
    assert payload["pii_leak_count"] == 2
    assert payload["pii_types"] == ["email", "phone"]
    assert payload["process_uptime_ms"] is not None
