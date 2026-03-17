from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage

from ai_travel_agent.agents.nodes.brain_planner import brain_planner
from ai_travel_agent.observability.metrics import MetricsCollector
from ai_travel_agent.llm import LLMClient
from ai_travel_agent.observability.logger import setup_logging


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


def test_brain_planner_logs_trace_with_selected_tools(tmp_path: Path):
    setup_logging(runtime_dir=tmp_path, level="INFO")
    content = """{
      "plan": [
        {"title": "Flight links", "step_type": "TOOL_CALL", "tool_name": "flights_search_links", "tool_args": {"origin":"SFO","destination":"Tokyo","start_date":"2026-04-01"}, "notes": "Get flight links"},
        {"title": "Hotel links", "step_type": "TOOL_CALL", "tool_name": "hotels_search_links", "tool_args": {"destination":"Tokyo","start_date":"2026-04-01","end_date":"2026-04-05"}, "notes": "Get hotel links"},
        {"title": "Synthesize", "step_type": "SYNTHESIZE", "tool_name": null, "tool_args": null, "notes": "Write plan"}
      ]
    }"""
    metrics = MetricsCollector(runtime_dir=tmp_path, run_id="r1", user_id="u1")
    llm = LLMClient(
        runnable=FakeRunnable(content),
        metrics=metrics,
        run_id="r1",
        user_id="u1",
        model_name="ollama/qwen2.5:3b-instruct",
    )
    state = {
        "run_id": "r1",
        "user_id": "u1",
        "user_query": "x",
        "constraints": {"origin": "SFO", "destinations": ["Tokyo"], "start_date": "2026-04-01", "end_date": "2026-04-05"},
        "validation_decision": {"decision": "passed"},
    }
    out = brain_planner(state, llm=llm)
    assert out["planner_decision"]["selected_tools"] == ["flights_search_links", "hotels_search_links"]

    payloads = [
        json.loads(line)
        for line in (tmp_path / "logs" / "app.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    trace = next(payload for payload in payloads if payload.get("event") == "llm_trace")
    assert trace["node_name"] == "brain_planner"
    assert trace["tool_selected"] == ["flights_search_links", "hotels_search_links"]
