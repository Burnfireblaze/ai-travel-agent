from __future__ import annotations

from pathlib import Path

from ai_travel_agent.observability.telemetry import TelemetryController


def test_selective_telemetry_buffers_until_signal(tmp_path: Path):
    telemetry = TelemetryController(runtime_dir=tmp_path, run_id="r1", user_id="u1", mode="selective", max_chars=200)

    telemetry.trace(event="tool_call", data={"x": "y"})
    trace_path = tmp_path / "logs" / "trace.jsonl"
    assert not trace_path.exists()

    state = {"signals": {}}
    telemetry.set_signal(state, "tool_error", True)
    telemetry.trace(event="tool_result", data={"ok": True})

    assert trace_path.exists()
    lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2
