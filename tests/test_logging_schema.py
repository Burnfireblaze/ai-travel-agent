from __future__ import annotations

import json
import logging
from pathlib import Path

from ai_travel_agent.observability.logger import LogContext, get_logger, log_event, setup_logging


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

