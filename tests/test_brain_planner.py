from __future__ import annotations

from pathlib import Path

from langchain_core.messages import AIMessage

from ai_travel_agent.agents.nodes.brain_planner import brain_planner
from ai_travel_agent.observability.metrics import MetricsCollector
from ai_travel_agent.llm import LLMClient


class FakeRunnable:
    def __init__(self, content: str):
        self.content = content

    def invoke(self, messages):
        return AIMessage(content=self.content)


def test_brain_planner_valid_json_plan(tmp_path: Path):
    content = """{
      "plan": [
        {"title": "Flight links", "step_type": "TOOL_CALL", "tool_name": "flights_search_links", "tool_args": {"origin":"SFO","destination":"Tokyo","start_date":"2026-04-01"}, "notes": "Get flight links"},
        {"title": "Synthesize", "step_type": "SYNTHESIZE", "tool_name": null, "tool_args": null, "notes": "Write plan"}
      ]
    }"""
    metrics = MetricsCollector(runtime_dir=tmp_path, run_id="r1", user_id="u1")
    llm = LLMClient(runnable=FakeRunnable(content), metrics=metrics, run_id="r1", user_id="u1")
    state = {"user_query": "x", "constraints": {"origin": "SFO", "destinations": ["Tokyo"], "start_date": "2026-04-01", "end_date": "2026-04-05"}}
    out = brain_planner(state, llm=llm)
    assert len(out.get("plan") or []) == 2
    assert (out["plan"][0]["tool_name"]) == "flights_search_links"


def test_brain_planner_invalid_json_falls_back(tmp_path: Path):
    metrics = MetricsCollector(runtime_dir=tmp_path, run_id="r1", user_id="u1")
    llm = LLMClient(runnable=FakeRunnable("not json"), metrics=metrics, run_id="r1", user_id="u1")
    state = {"user_query": "x", "constraints": {"origin": "SFO", "destinations": ["Tokyo"], "start_date": "2026-04-01", "end_date": "2026-04-05"}}
    out = brain_planner(state, llm=llm)
    # deterministic planner should create at least a synthesize step
    assert any(s.get("step_type") == "SYNTHESIZE" for s in (out.get("plan") or []))

