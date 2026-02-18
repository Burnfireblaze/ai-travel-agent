#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_travel_agent.agents.nodes.context_controller import context_controller
from ai_travel_agent.agents.nodes.executor import executor
from ai_travel_agent.agents.nodes.intent_parser import intent_parser
from ai_travel_agent.agents.nodes.orchestrator import orchestrator
from ai_travel_agent.agents.nodes.planner import planner
from ai_travel_agent.agents.nodes.responder import responder
from ai_travel_agent.llm import LLMClient
from ai_travel_agent.observability.failure_tracker import FailureTracker, set_failure_tracker
from ai_travel_agent.observability.logger import setup_logging
from ai_travel_agent.observability.metrics import MetricsCollector
from ai_travel_agent.tools import ToolRegistry


PROMPTS_FILE = ROOT / "data/prompts/test_failures_prompts_100.txt"
RUNTIME_DIR = ROOT / "runtime"
USER_ID = "baseline-user"


class MemoryStub:
    def search(self, *, query: str, k: int, include_session: bool, include_user: bool):
        return []


class DeterministicRunnable:
    def invoke(self, messages):
        system = str(messages[0].content) if messages else ""
        user = str(messages[1].content) if len(messages) > 1 else ""
        if "Extract trip constraints" in system:
            payload = {
                "origin": _extract_origin(user) or "New Delhi",
                "destinations": [_extract_destination(user) or "Paris"],
                "start_date": "2026-03-01",
                "end_date": "2026-03-05",
                "budget_usd": 2500,
                "travelers": 2,
                "interests": ["food", "culture", "walking"],
                "pace": "balanced",
                "notes": [],
            }
            return AIMessage(content=json.dumps(payload))
        return AIMessage(
            content=(
                "# Trip Plan\n\n"
                "## Summary\nA balanced itinerary with practical links and local pacing.\n\n"
                "## Assumptions\n- timings may vary\n\n"
                "## Flights\n- [Google Flights](https://www.google.com/travel/flights)\n\n"
                "## Lodging\n- [Booking.com](https://www.booking.com)\n\n"
                "## Day-by-day\n### Day 1: Arrival and orientation\n### Day 2: City highlights\n### Day 3: Neighborhood exploration\n\n"
                "## Transit\nUse metro and short rideshare hops.\n\n"
                "## Weather\nCheck local forecast before each day.\n\n"
                "## Budget\nEstimate: moderate daily spend.\n\n"
                "## Calendar\nExport is available.\n\n"
                'Note: Visa/health requirements vary; verify with official sources (this is not legal advice).'
            )
        )


def _extract_destination(text: str) -> str | None:
    patterns = [
        r"trip to ([A-Za-z .'-]+)",
        r"visit ([A-Za-z .'-]+)",
        r"itinerary (?:for|to) ([A-Za-z .'-]+)",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip(" ,.")
    return None


def _extract_origin(text: str) -> str | None:
    m = re.search(r"from ([A-Za-z .'-]+)", text, flags=re.IGNORECASE)
    if not m:
        return None
    out = m.group(1).strip(" ,.")
    out = re.split(r"\bwith\b|\bfor\b|\bincluding\b", out, maxsplit=1, flags=re.IGNORECASE)[0].strip(" ,.")
    return out or None


def build_tools() -> ToolRegistry:
    tools = ToolRegistry()
    tools.register(
        "flights_search_links",
        lambda **kw: {
            "summary": "Found flights",
            "links": [{"label": "Google Flights", "url": "https://www.google.com/travel/flights"}],
            "top_results": [{"label": "Flight Option 1", "url": "https://www.google.com/travel/flights"}],
        },
    )
    tools.register(
        "hotels_search_links",
        lambda **kw: {
            "summary": "Found hotels",
            "links": [{"label": "Booking.com", "url": "https://www.booking.com"}],
            "top_results": [{"label": "Hotel Option 1", "url": "https://www.booking.com"}],
        },
    )
    tools.register(
        "things_to_do_links",
        lambda **kw: {
            "summary": "Found activities",
            "links": [{"label": "Google Maps", "url": "https://www.google.com/maps"}],
        },
    )
    tools.register(
        "weather_summary",
        lambda **kw: {
            "summary": "Mild and mostly clear.",
            "links": [{"label": "Weather", "url": "https://www.google.com/search?q=weather"}],
        },
    )
    return tools


def load_prompts(path: Path) -> list[str]:
    prompts: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        prompts.append(s)
    return prompts


def run_one(prompt: str, idx: int) -> dict[str, Any]:
    run_id = f"normal-{idx:03d}"
    metrics = MetricsCollector(runtime_dir=RUNTIME_DIR, run_id=run_id, user_id=USER_ID)
    tracker = FailureTracker(run_id=run_id, user_id=USER_ID, runtime_dir=RUNTIME_DIR)
    set_failure_tracker(tracker)

    llm = LLMClient(runnable=DeterministicRunnable(), metrics=metrics, run_id=run_id, user_id=USER_ID)
    tools = build_tools()
    memory = MemoryStub()

    state: dict[str, Any] = {
        "run_id": run_id,
        "user_id": USER_ID,
        "user_query": prompt,
        "signals": {},
    }

    state = context_controller(state, memory=memory, metrics=metrics)
    state = intent_parser(state, llm=llm)
    state = planner(state)

    max_iters = 20
    while True:
        state = orchestrator(state, max_iters=max_iters)
        if state.get("termination_reason") in {"finalized", "max_iters"}:
            break
        state = executor(state, tools=tools, llm=llm, metrics=metrics, memory=memory, max_tool_retries=0)
        if state.get("needs_triage"):
            # Baseline run should continue; unblock and move on.
            state["needs_triage"] = False

    state = responder(state)
    record = metrics.finalize_record(status="ok", termination_reason=state.get("termination_reason"))
    metrics.write(record)

    failure_count = len(tracker.failures)
    set_failure_tracker(None)
    return {
        "run_id": run_id,
        "termination_reason": state.get("termination_reason"),
        "failure_count": failure_count,
        "final_answer_chars": len((state.get("final_answer") or "")),
    }


def main() -> None:
    setup_logging(runtime_dir=RUNTIME_DIR, level="INFO")
    prompts = load_prompts(PROMPTS_FILE)
    out_dir = RUNTIME_DIR / "logs" / "prompt_runs_normal"
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for idx, prompt in enumerate(prompts, start=1):
        result = run_one(prompt, idx)
        results.append(result)
        (out_dir / f"normal_prompt_{idx}.log").write_text(
            f"prompt={prompt}\nrun_id={result['run_id']}\ntermination={result['termination_reason']}\n"
            f"failure_count={result['failure_count']}\nfinal_answer_chars={result['final_answer_chars']}\n",
            encoding="utf-8",
        )
        print(f"[{idx}/{len(prompts)}] {result['run_id']} failures={result['failure_count']}")

    summary = {
        "prompt_count": len(prompts),
        "runs": results,
        "total_failures": sum(r["failure_count"] for r in results),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Done. Summary: {out_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
