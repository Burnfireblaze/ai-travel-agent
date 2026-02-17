from __future__ import annotations

import json
import logging
from pathlib import Path

from ai_travel_agent.observability.logger import LogContext, get_logger, log_event, setup_logging
from ai_travel_agent.observability.failure_tracker import (
    FailureCategory,
    FailureSeverity,
    FailureTracker,
    set_failure_tracker,
)


def test_jsonl_logging_schema(tmp_path: Path):
    setup_logging(runtime_dir=tmp_path, level="INFO")
    logger = get_logger("test")

    log_event(
        logger,
        level=logging.INFO,
        message="hello",
        event="node_enter",
        context=LogContext(
            run_id="run123",
            user_id="user123",
            graph_node="context_controller",
            step_type="RETRIEVE_CONTEXT",
            step_id="s1",
            step_title="Retrieve",
        ),
        data={"x": 1},
    )

    jsonl = tmp_path / "logs" / "app.jsonl"
    assert jsonl.exists()
    line = jsonl.read_text(encoding="utf-8").strip().splitlines()[-1]
    payload = json.loads(line)

    for key in [
        "timestamp",
        "level",
        "module",
        "message",
        "run_id",
        "user_id",
        "graph_node",
        "step_type",
        "step_id",
        "step_title",
        "event",
        "data",
    ]:
        assert key in payload


def test_combined_log_contains_normal_and_failure_entries(tmp_path: Path):
    setup_logging(runtime_dir=tmp_path, level="INFO")
    tracker = FailureTracker(run_id="run-combined", user_id="user-combined", runtime_dir=tmp_path)
    set_failure_tracker(tracker)
    logger = get_logger("test")

    log_event(
        logger,
        level=logging.INFO,
        message="normal event",
        event="normal_event",
        context=LogContext(
            run_id="run-combined",
            user_id="user-combined",
            graph_node="executor",
            step_type="RETRIEVE_CONTEXT",
            step_id="s1",
            step_title="Retrieve",
        ),
        data={"ok": True},
    )

    tracker.record_failure(
        category=FailureCategory.TOOL,
        severity=FailureSeverity.HIGH,
        graph_node="executor",
        error_type="RuntimeError",
        error_message="simulated failure",
        step_id="s2",
        step_type="TOOL_CALL",
        step_title="Call tool",
    )

    combined = tmp_path / "logs" / "combined_run-combined.jsonl"
    assert combined.exists()
    records = [json.loads(line) for line in combined.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(r.get("kind") == "normal" and r.get("event") == "normal_event" for r in records)
    assert any(r.get("kind") == "failure" and r.get("event") == "failure_recorded" for r in records)

    set_failure_tracker(None)
