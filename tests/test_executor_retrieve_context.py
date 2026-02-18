from __future__ import annotations

from pathlib import Path

from ai_travel_agent.agents.nodes.executor import executor
from ai_travel_agent.agents.state import StepType
from ai_travel_agent.memory.schemas import MemoryHit
from ai_travel_agent.observability.metrics import MetricsCollector


class MemoryStub:
    def search(self, *, query: str, k: int, include_session: bool, include_user: bool):
        return [
            MemoryHit(id="1", text="Home origin: SFO", metadata={"type": "profile", "created_at": "2026-01-01T00:00:00+00:00"}, distance=0.1)
        ]


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

