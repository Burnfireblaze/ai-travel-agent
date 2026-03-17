from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage

from ai_travel_agent.agents.nodes.reasoning_engine import reasoning_engine
from ai_travel_agent.llm import LLMClient
from ai_travel_agent.observability.logger import setup_logging
from ai_travel_agent.observability.metrics import MetricsCollector


class FakeRunnable:
    def __init__(self, content: str):
        self.content = content

    def invoke(self, messages):
        return AIMessage(content=self.content)


def test_reasoning_engine_logs_summary_to_terminal_files(tmp_path: Path):
    setup_logging(runtime_dir=tmp_path, level="INFO")
    content = """{
      "summary": "Inputs are validated, so planning can focus on destination-specific links and relaxed pacing.",
      "key_points": ["Keep the itinerary centered on gardens and museums.", "Use weather context before choosing hikes."],
      "risks": ["Avoid live prices in the final answer."],
      "planner_guidance": ["Prefer destination-specific hotel and flight links."],
      "tool_rationale": [{"tool_name": "weather_summary", "reason": "Weather affects packing and hike suitability."}]
    }"""
    metrics = MetricsCollector(runtime_dir=tmp_path, run_id="r1", user_id="u1")
    llm = LLMClient(runnable=FakeRunnable(content), metrics=metrics, run_id="r1", user_id="u1")
    state = {
        "run_id": "r1",
        "user_id": "u1",
        "user_query": "Plan a Japan trip",
        "constraints": {"origin": "NYC", "destinations": ["Tokyo"], "start_date": "2026-04-05", "end_date": "2026-04-14"},
        "context_hits": [],
        "grounded_places": {"origin": {"iata": "NYC"}, "destinations": [{"name": "Tokyo"}]},
        "validation_warnings": [],
    }

    out = reasoning_engine(state, llm=llm)

    assert out["reasoning_summary"]["summary"].startswith("Inputs are validated")
    assert any("Avoid live prices" in line for line in out["reasoning_log_lines"])

    jsonl = tmp_path / "logs" / "app.jsonl"
    payloads = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    reasoning_event = next(payload for payload in payloads if payload.get("event") == "reasoning_summary")
    assert reasoning_event["span_payload"]["data"]["summary"].startswith("Inputs are validated")

    text_log = tmp_path / "logs" / "app.log"
    assert "Reasoning summary: Inputs are validated" in text_log.read_text(encoding="utf-8")
