from __future__ import annotations

import json
import logging
from pathlib import Path

from ai_travel_agent.observability.logger import LogContext, get_logger, log_event, log_llm_event, setup_logging
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
        "ts",
        "level",
        "run_id",
        "node",
        "step_id",
        "event",
        "span_payload",
        "tokens_total",
        "tokens_per_request",
        "avg_tokens_per_request",
        "ttft_ms",
        "task_completed",
        "goal_completed",
        "task_completion_rate",
        "goal_completion_rate",
        "pii_detected",
        "pii_leak_count",
        "pii_types",
        "api_requests_total",
        "api_errors_total",
        "api_error_rate",
        "process_uptime_ms",
        "system_uptime_seconds",
        "hallucination_detected",
        "hallucination_ratio",
        "hallucination_rate",
    ]:
        assert key in payload
    assert payload["span_payload"]["message"] == "hello"
    assert payload["span_payload"]["user_id"] == "user123"
    assert payload["span_payload"]["data"] == {"x": 1}


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
    assert any(r.get("span_payload", {}).get("kind") == "normal" and r.get("event") == "normal_event" for r in records)
    assert any(r.get("span_payload", {}).get("kind") == "failure" and r.get("event") == "failure_recorded" for r in records)

    set_failure_tracker(None)


def test_log_llm_event_writes_trace_fields(tmp_path: Path):
    setup_logging(runtime_dir=tmp_path, level="INFO")
    logger = get_logger("test")

    log_llm_event(
        "planner",
        {"system": "system prompt", "user": "user prompt"},
        "{\"plan\": []}",
        {
            "model_name": "ollama/qwen2.5:3b-instruct",
            "latency_ms": 12.5,
            "tokens_in": 42,
            "tokens_out": 18,
            "tokens_total": 60,
            "tokens_per_request": 60,
            "ttft_ms": 321.0,
            "intent_decision": {"constraints": {"destination": "Japan"}},
            "validation_decision": {"decision": "passed"},
            "planner_decision": {"step_count": 1},
            "tool_selected": "flights_search_links",
            "synthesis_decision": None,
        },
        logger=logger,
        context=LogContext(run_id="run-llm", user_id="user-llm", graph_node="planner", step_type="PLAN_DRAFT"),
    )

    jsonl = tmp_path / "logs" / "app.jsonl"
    payloads = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    trace = next(payload for payload in payloads if payload.get("event") == "llm_trace")
    assert trace["node_name"] == "planner"
    assert trace["model_name"] == "ollama/qwen2.5:3b-instruct"
    assert trace["llm_input"] == {"system": "system prompt", "user": "user prompt"}
    assert trace["llm_output"] == "{\"plan\": []}"
    assert trace["planner_decision"] == {"step_count": 1}
    assert trace["tool_selected"] == "flights_search_links"
    assert trace["tokens_total"] == 60
    assert trace["tokens_per_request"] == 60
    assert trace["ttft_ms"] == 321.0
    assert trace["pii_detected"] is False

    log_llm_event(
        "planner",
        {"system": "system prompt", "user": "Contact me at test@example.com"},
        "Call +1 (415) 555-1212",
        {"model_name": "ollama/qwen2.5:3b-instruct"},
        logger=logger,
        context=LogContext(run_id="run-llm", user_id="user-llm", graph_node="planner", step_type="PLAN_DRAFT"),
    )
    payloads = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    pii_trace = payloads[-1]
    assert pii_trace["event"] == "llm_trace"
    assert pii_trace["pii_detected"] is True
    assert pii_trace["pii_leak_count"] >= 2
    assert set(pii_trace["pii_types"]) >= {"email", "phone"}

    text_log = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "LLM trace captured for planner" in text_log
    assert "\"model_name\": \"ollama/qwen2.5:3b-instruct\"" in text_log
