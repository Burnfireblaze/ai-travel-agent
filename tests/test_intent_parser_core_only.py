from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage

from ai_travel_agent.agents.nodes.intent_parser import intent_parser
from ai_travel_agent.llm import LLMClient
from ai_travel_agent.observability.logger import setup_logging
from ai_travel_agent.observability.metrics import MetricsCollector


class FakeRunnable:
    def __init__(self, content: str):
        self.content = content

    def invoke(self, messages):
        return AIMessage(content=self.content)


def test_intent_parser_missing_optional_does_not_ask(tmp_path: Path):
    raw = """{
      "origin": "JFK",
      "destinations": ["Tokyo"],
      "start_date": "2026-04-01",
      "end_date": "2026-04-05",
      "budget_usd": null,
      "travelers": null,
      "interests": [],
      "pace": null,
      "notes": []
    }"""
    metrics = MetricsCollector(runtime_dir=tmp_path, run_id="r1", user_id="u1")
    llm = LLMClient(runnable=FakeRunnable(raw), metrics=metrics, run_id="r1", user_id="u1")
    out = intent_parser({"user_query": "x"}, llm=llm)
    assert out.get("needs_user_input") is False


def test_intent_parser_missing_core_asks(tmp_path: Path):
    raw = """{
      "origin": null,
      "destinations": [],
      "start_date": "2026-04-01",
      "end_date": "2026-04-05",
      "budget_usd": null,
      "travelers": null,
      "interests": [],
      "pace": null,
      "notes": []
    }"""
    metrics = MetricsCollector(runtime_dir=tmp_path, run_id="r1", user_id="u1")
    llm = LLMClient(runnable=FakeRunnable(raw), metrics=metrics, run_id="r1", user_id="u1")
    out = intent_parser({"user_query": "x"}, llm=llm)
    assert out.get("needs_user_input") is True
    qs = out.get("clarifying_questions") or []
    assert any("depart" in q.lower() or "destination" in q.lower() for q in qs)


def test_intent_parser_extracts_json_from_code_block(tmp_path: Path):
    raw = """```json
    {
      "origin": "JFK",
      "destinations": ["Tokyo"],
      "start_date": "2026-04-01",
      "end_date": "2026-04-05",
      "budget_usd": 3500,
      "travelers": 2,
      "interests": ["ramen"],
      "pace": "relaxed",
      "notes": []
    }
    ```"""
    metrics = MetricsCollector(runtime_dir=tmp_path, run_id="r1", user_id="u1")
    llm = LLMClient(runnable=FakeRunnable(raw), metrics=metrics, run_id="r1", user_id="u1")
    out = intent_parser({"user_query": "x"}, llm=llm)
    assert out.get("needs_user_input") is False
    assert out["constraints"]["origin"] == "JFK"


def test_intent_parser_heuristic_fills_core_fields(tmp_path: Path):
    raw = "not json"
    metrics = MetricsCollector(runtime_dir=tmp_path, run_id="r1", user_id="u1")
    llm = LLMClient(runnable=FakeRunnable(raw), metrics=metrics, run_id="r1", user_id="u1")
    query = (
        "I’m traveling to Japan. Flying from NYC. Dates: 2026-04-05 to 2026-04-14. "
        "Budget is $3500 for 2 travelers. Interests: ramen, gardens. Pace: relaxed."
    )
    out = intent_parser({"user_query": query}, llm=llm)
    constraints = out["constraints"]
    assert out.get("needs_user_input") is False
    assert constraints["destinations"] == ["Japan"]
    assert constraints["origin"] == "NYC"
    assert constraints["start_date"] == "2026-04-05"
    assert constraints["end_date"] == "2026-04-14"
    assert constraints["budget_usd"] == 3500
    assert constraints["travelers"] == 2


def test_intent_parser_logs_llm_trace(tmp_path: Path):
    setup_logging(runtime_dir=tmp_path, level="INFO")
    raw = """{
      "origin": "JFK",
      "destinations": ["Tokyo"],
      "start_date": "2026-04-01",
      "end_date": "2026-04-05",
      "budget_usd": 3500,
      "travelers": 2,
      "interests": ["ramen"],
      "pace": "relaxed",
      "notes": []
    }"""
    metrics = MetricsCollector(runtime_dir=tmp_path, run_id="r1", user_id="u1")
    llm = LLMClient(
        runnable=FakeRunnable(raw),
        metrics=metrics,
        run_id="r1",
        user_id="u1",
        model_name="ollama/qwen2.5:3b-instruct",
    )
    out = intent_parser({"run_id": "r1", "user_id": "u1", "user_query": "Plan Japan trip"}, llm=llm)
    assert out["intent_decision"]["constraints"]["origin"] == "JFK"

    payloads = [
        json.loads(line)
        for line in (tmp_path / "logs" / "app.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    trace = next(payload for payload in payloads if payload.get("event") == "llm_trace")
    assert trace["node_name"] == "intent_parser"
    assert trace["intent_decision"]["constraints"]["origin"] == "JFK"
