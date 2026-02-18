from __future__ import annotations

from pathlib import Path

from langchain_core.messages import AIMessage

from ai_travel_agent.agents.nodes.intent_parser import intent_parser
from ai_travel_agent.llm import LLMClient
from ai_travel_agent.observability.metrics import MetricsCollector


class FakeRunnable:
    def __init__(self, content: str):
        self.content = content

    def invoke(self, messages):
        return AIMessage(content=self.content)


def test_intent_parser_applies_destination_override(tmp_path: Path):
    raw = """{
      "origin": "JFK",
      "destinations": ["Peru"],
      "start_date": "2026-06-03",
      "end_date": "2026-06-11",
      "budget_usd": 3200,
      "travelers": 2,
      "interests": ["food"],
      "pace": "balanced",
      "notes": []
    }"""
    metrics = MetricsCollector(runtime_dir=tmp_path, run_id="r1", user_id="u1")
    llm = LLMClient(runnable=FakeRunnable(raw), metrics=metrics, run_id="r1", user_id="u1")
    state = {"user_query": "x", "constraint_overrides": {"destinations": ["Peru, Peru"]}}
    out = intent_parser(state, llm=llm)
    assert out["constraints"]["destinations"] == ["Peru, Peru"]


def test_intent_parser_applies_origin_override(tmp_path: Path):
    raw = """{
      "origin": "JFK",
      "destinations": ["Tokyo"],
      "start_date": "2026-06-03",
      "end_date": "2026-06-11",
      "budget_usd": null,
      "travelers": null,
      "interests": [],
      "pace": null,
      "notes": []
    }"""
    metrics = MetricsCollector(runtime_dir=tmp_path, run_id="r1", user_id="u1")
    llm = LLMClient(runnable=FakeRunnable(raw), metrics=metrics, run_id="r1", user_id="u1")
    state = {"user_query": "x", "constraint_overrides": {"origin": "SFO"}}
    out = intent_parser(state, llm=llm)
    assert out["constraints"]["origin"] == "SFO"


def test_intent_parser_applies_dates_override(tmp_path: Path):
    raw = """{
      "origin": "JFK",
      "destinations": ["Tokyo"],
      "start_date": null,
      "end_date": null,
      "budget_usd": null,
      "travelers": null,
      "interests": [],
      "pace": null,
      "notes": []
    }"""
    metrics = MetricsCollector(runtime_dir=tmp_path, run_id="r1", user_id="u1")
    llm = LLMClient(runnable=FakeRunnable(raw), metrics=metrics, run_id="r1", user_id="u1")
    state = {"user_query": "x", "constraint_overrides": {"start_date": "2026-01-01", "end_date": "2026-01-05"}}
    out = intent_parser(state, llm=llm)
    assert out["constraints"]["start_date"] == "2026-01-01"
    assert out["constraints"]["end_date"] == "2026-01-05"
