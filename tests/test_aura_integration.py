from __future__ import annotations

import logging
from pathlib import Path

from ai_travel_agent.observability.logger import TELEMETRY, LogContext, get_logger, log_event, setup_logging


def test_log_event_forwards_sanitized_payload_to_aura(tmp_path: Path, monkeypatch):
    setup_logging(runtime_dir=tmp_path, level="INFO")
    logger = get_logger("test.aura")
    forwarded: list[dict] = []

    monkeypatch.setattr(
        "ai_travel_agent.observability.aura_bridge.capture_event",
        lambda payload: forwarded.append(payload) or True,
    )

    log_event(
        logger,
        level=logging.ERROR,
        message="Tool failed",
        event="tool_error",
        context=LogContext(
            run_id="run-aura",
            user_id="user-aura",
            graph_node="executor",
            step_type="TOOL_CALL",
            step_id="step-2",
            step_title="Call weather tool",
        ),
        data={"error": "boom", "api_key": "secret"},
    )

    assert len(forwarded) == 1
    payload = forwarded[0]
    assert payload["event"] == "tool_error"
    assert payload["run_id"] == "run-aura"
    assert payload["node"] == "executor"
    assert payload["status"] == "failed"
    assert payload["span_payload"]["data"]["api_key"] == "[REDACTED]"


def test_telemetry_controller_respects_aura_ruleset(monkeypatch):
    previous_mode = TELEMETRY.get_mode()
    TELEMETRY.set_mode("MINIMAL")
    monkeypatch.setattr(
        "ai_travel_agent.observability.aura_bridge.is_detailed_logging_enabled",
        lambda: True,
    )

    try:
        assert TELEMETRY.should_log_detailed({}) is True
    finally:
        TELEMETRY.set_mode(previous_mode)
