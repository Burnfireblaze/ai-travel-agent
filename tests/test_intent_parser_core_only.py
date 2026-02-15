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

