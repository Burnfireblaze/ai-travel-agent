from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage

from ai_travel_agent.agents.nodes.executor import executor
from ai_travel_agent.agents.state import StepType
from ai_travel_agent.llm import LLMClient
from ai_travel_agent.memory.schemas import MemoryHit
from ai_travel_agent.observability.logger import setup_logging
from ai_travel_agent.observability.metrics import MetricsCollector
from ai_travel_agent.tools import ToolRegistry


class MemoryStub:
    def search(self, *, query: str, k: int, include_session: bool, include_user: bool):
        return [
            MemoryHit(id="1", text="Home origin: SFO", metadata={"type": "profile", "created_at": "2026-01-01T00:00:00+00:00"}, distance=0.1)
        ]


class FakeRunnable:
    def __init__(self, content: str):
        self.content = content

    def invoke(self, messages):
        return AIMessage(content=self.content)


def test_executor_retrieve_context_updates_hits(tmp_path: Path):
    metrics = MetricsCollector(runtime_dir=tmp_path, run_id="r1", user_id="u1")
    state = {
        "user_query": "test",
        "plan": [{"id": "s1", "title": "Retrieve", "step_type": StepType.RETRIEVE_CONTEXT, "status": "pending", "tool_args": {"query": "origin"}}],
        "current_step": {"id": "s1", "title": "Retrieve", "step_type": StepType.RETRIEVE_CONTEXT, "status": "pending", "tool_args": {"query": "origin"}},
        "current_step_index": 0,
        "context_hits": [],
    }
    out = executor(state, tools=None, llm=None, metrics=metrics, memory=MemoryStub())  # tools/llm unused in retrieval step
    assert out["plan"][0]["status"] == "done"
    assert len(out.get("context_hits") or []) == 1
    assert metrics.counters.get("rag_retrievals", 0) == 1


def test_executor_logs_synthesis_trace(tmp_path: Path):
    setup_logging(runtime_dir=tmp_path, level="INFO")
    metrics = MetricsCollector(runtime_dir=tmp_path, run_id="r1", user_id="u1")
    llm = LLMClient(
        runnable=FakeRunnable("## High-level summary\n- Tokyo trip\n"),
        metrics=metrics,
        run_id="r1",
        user_id="u1",
        model_name="ollama/qwen2.5:3b-instruct",
    )
    state = {
        "run_id": "r1",
        "user_id": "u1",
        "user_query": "Plan a Japan trip",
        "constraints": {"origin": "SFO", "destinations": ["Tokyo"], "start_date": "2026-04-01", "end_date": "2026-04-05"},
        "context_hits": [{"text": "Home origin: SFO", "metadata": {"type": "profile"}}],
        "tool_results": [{"tool_name": "flights_search_links", "summary": "Flight links", "links": [{"label": "Google Flights", "url": "https://example.com"}]}],
        "plan": [{"id": "s1", "title": "Synthesize", "step_type": StepType.SYNTHESIZE, "status": "pending"}],
        "current_step": {"id": "s1", "title": "Synthesize", "step_type": StepType.SYNTHESIZE, "status": "pending"},
        "current_step_index": 0,
        "planner_decision": {"selected_tools": ["flights_search_links"]},
        "tool_selected": "flights_search_links",
    }

    out = executor(state, tools=ToolRegistry(), llm=llm, metrics=metrics, memory=None)
    assert out["plan"][0]["status"] == "done"
    assert out["synthesis_decision"]["tool_results_used"] == 1

    payloads = [
        json.loads(line)
        for line in (tmp_path / "logs" / "app.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    trace = next(payload for payload in payloads if payload.get("event") == "llm_trace" and payload.get("node_name") == "executor")
    assert trace["model_name"] == "ollama/qwen2.5:3b-instruct"
    assert trace["synthesis_decision"]["tool_results_used"] == 1
