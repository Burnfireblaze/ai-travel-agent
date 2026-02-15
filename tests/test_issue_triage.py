from __future__ import annotations

from pathlib import Path

from langchain_core.messages import AIMessage

from ai_travel_agent.agents.nodes.issue_triage import issue_triage
from ai_travel_agent.llm import LLMClient
from ai_travel_agent.observability.metrics import MetricsCollector


class FakeRunnable:
    def __init__(self, content: str):
        self.content = content

    def invoke(self, messages):
        return AIMessage(content=self.content)


def test_issue_triage_minor_skips(tmp_path: Path):
    metrics = MetricsCollector(runtime_dir=tmp_path, run_id="r1", user_id="u1")
    llm = LLMClient(runnable=FakeRunnable('{"action":"skip","note":"weather offline","user_question":null}'), metrics=metrics, run_id="r1", user_id="u1")
    state = {
        "plan": [{"id": "s1", "status": "blocked", "notes": ""}],
        "pending_issue": {"kind": "tool_error", "severity": "minor", "node": "executor", "step_id": "s1", "tool_name": "weather_summary", "message": "offline", "suggested_actions": []},
        "needs_triage": True,
        "validation_warnings": [],
    }
    out = issue_triage(state, llm=llm)
    assert out["plan"][0]["status"] == "done"
    assert out.get("needs_user_input") is not True


def test_issue_triage_major_also_skips(tmp_path: Path):
    metrics = MetricsCollector(runtime_dir=tmp_path, run_id="r1", user_id="u1")
    llm = LLMClient(runnable=FakeRunnable('{"action":"skip","note":"skip anyway","user_question":null}'), metrics=metrics, run_id="r1", user_id="u1")
    state = {
        "plan": [{"id": "s1", "status": "blocked", "notes": ""}],
        "pending_issue": {"kind": "tool_error", "severity": "major", "node": "executor", "step_id": "s1", "tool_name": "flights_search_links", "message": "failed", "suggested_actions": []},
        "needs_triage": True,
    }
    out = issue_triage(state, llm=llm)
    assert out["plan"][0]["status"] == "done"
    assert out.get("needs_user_input") is not True
