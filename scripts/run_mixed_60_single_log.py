#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import random
import re
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_travel_agent.config import load_settings
import ai_travel_agent.graph as graph_mod
from ai_travel_agent.graph import build_app
from ai_travel_agent.llm import build_chat_model as original_build_chat_model
from ai_travel_agent.observability.failure_tracker import (
    FailureCategory,
    FailureSeverity,
    FailureTracker,
    set_failure_tracker,
)
from ai_travel_agent.observability.canonical_schema import build_canonical_record
from ai_travel_agent.observability.logger import LogContext, get_logger, log_event
from ai_travel_agent.observability.metrics import MetricsCollector


PROMPTS_FILE = ROOT / "data/prompts/test_failures_prompts_200.txt"
RUNTIME_DIR = ROOT / "runtime"
LOG_DIR = RUNTIME_DIR / "logs"
SINGLE_LOG = LOG_DIR / "mixed_200_runs.jsonl"

SEED = 20260217
TOTAL_RUNS = 200
SUCCESS_RUNS = 100
FAILURE_RUNS = 100
USER_ID = "mixed-user"
TOOLS_ALL = ["flights_search_links", "hotels_search_links", "things_to_do_links", "weather_summary"]

FAILURE_SCENARIOS = [
    "tool_timeout",
    "bad_retrieval",
    "both_env",
    "tool_not_registered",
    "llm_timeout_intent",
    "llm_connection_intent",
    "llm_malformed_intent",
    "memory_search_error",
    "orchestrator_max_iters",
    "eval_price_fabrication",
    "eval_invalid_link",
    "eval_calendar_fail",
]

logger = get_logger(__name__)
ORIGINAL_EXPORT_ICS = graph_mod.export_ics


def _extract_marker(text: str, key: str) -> str | None:
    m = re.search(rf"\[\[{re.escape(key)}:([^\]]+)\]\]", text or "")
    if not m:
        return None
    return m.group(1).strip()


def _extract_scenario(text: str) -> str:
    return _extract_marker(text, "SCENARIO") or "none"


def _extract_tools(text: str) -> list[str]:
    raw = _extract_marker(text, "TOOLS")
    if not raw:
        return TOOLS_ALL[:]
    items = [x.strip() for x in raw.split(",") if x.strip()]
    out = [x for x in items if x in TOOLS_ALL]
    return out or TOOLS_ALL[:]


class InMemoryStore:
    def __init__(self) -> None:
        self._session: list[dict[str, Any]] = []
        self._user: list[dict[str, Any]] = []

    def add_session(self, *, text: str, run_id: str, doc_type: str, metadata: dict[str, Any] | None = None) -> str:
        self._session.append({"id": f"s-{len(self._session)+1}", "text": text, "metadata": metadata or {"type": doc_type}})
        return self._session[-1]["id"]

    def add_user(self, *, text: str, run_id: str, doc_type: str, metadata: dict[str, Any] | None = None) -> str:
        self._user.append({"id": f"u-{len(self._user)+1}", "text": text, "metadata": metadata or {"type": doc_type}})
        return self._user[-1]["id"]

    def search(self, *, query: str, k: int = 5, include_session: bool = True, include_user: bool = True):
        if _extract_scenario(query) == "memory_search_error":
            raise RuntimeError("Injected memory search failure")
        docs: list[dict[str, Any]] = []
        if include_user:
            docs.extend(self._user)
        if include_session:
            docs.extend(self._session)
        out = []
        for d in docs[:k]:
            out.append(type("Hit", (), {"id": d["id"], "text": d["text"], "metadata": d["metadata"], "distance": 0.1})())
        return out


def stable_geocode(name: str) -> dict[str, Any]:
    cleaned = (name or "").strip()
    if not cleaned:
        return {"best": None, "candidates": [], "ambiguous": False}
    return {
        "best": {"name": cleaned, "country": "Unknown", "lat": 0.0, "lon": 0.0},
        "candidates": [{"name": cleaned, "country": "Unknown", "lat": 0.0, "lon": 0.0}],
        "ambiguous": False,
    }


def _extract_origin(text: str) -> str | None:
    m = re.search(r"from ([A-Za-z .'-]+)", text, flags=re.IGNORECASE)
    return m.group(1).strip(" ,.") if m else None


def _extract_destination(text: str) -> str | None:
    m = re.search(r"to ([A-Za-z .'-]+)", text, flags=re.IGNORECASE)
    return m.group(1).strip(" ,.") if m else None


class DeterministicRunnable:
    def invoke(self, messages):
        system = str(messages[0].content) if messages else ""
        user = str(messages[1].content) if len(messages) > 1 else ""
        scenario = _extract_scenario(user)

        if "Extract trip constraints" in system:
            if scenario == "llm_timeout_intent":
                raise TimeoutError("Injected LLM timeout (intent)")
            if scenario == "llm_connection_intent":
                raise ConnectionError("Injected LLM connection failure (intent)")
            if scenario == "llm_malformed_intent":
                return AIMessage(content="{")
            payload = {
                "origin": _extract_origin(user) or "New Delhi",
                "destinations": [_extract_destination(user) or "Paris"],
                "start_date": "2026-03-01",
                "end_date": "2026-03-05",
                "budget_usd": 2200,
                "travelers": 2,
                "interests": ["food", "culture"],
                "pace": "balanced",
                "notes": [],
            }
            return AIMessage(content=json.dumps(payload))

        if "planning brain for a links-only travel agent" in system:
            destination = _extract_destination(user) or "Paris"
            origin = _extract_origin(user) or "New Delhi"
            selected = _extract_tools(user)

            plan: list[dict[str, Any]] = []
            if scenario == "tool_not_registered":
                plan.append(
                    {
                        "title": "Call unknown tool",
                        "step_type": "TOOL_CALL",
                        "tool_name": "unknown_tool_xyz",
                        "tool_args": {"destination": destination},
                        "notes": "Injected unknown tool failure.",
                    }
                )
            for tool in selected:
                if tool == "flights_search_links":
                    plan.append(
                        {
                            "title": "Get flight search links",
                            "step_type": "TOOL_CALL",
                            "tool_name": tool,
                            "tool_args": {"origin": origin, "destination": destination, "start_date": "2026-03-01"},
                            "notes": "Flight links",
                        }
                    )
                elif tool == "hotels_search_links":
                    plan.append(
                        {
                            "title": "Get hotel search links",
                            "step_type": "TOOL_CALL",
                            "tool_name": tool,
                            "tool_args": {"destination": destination, "start_date": "2026-03-01", "end_date": "2026-03-05"},
                            "notes": "Hotel links",
                        }
                    )
                elif tool == "things_to_do_links":
                    plan.append(
                        {
                            "title": "Get things-to-do discovery links",
                            "step_type": "TOOL_CALL",
                            "tool_name": tool,
                            "tool_args": {"destination": destination, "interests": ["food", "culture"]},
                            "notes": "Activity links",
                        }
                    )
                elif tool == "weather_summary":
                    plan.append(
                        {
                            "title": "Get weather summary",
                            "step_type": "TOOL_CALL",
                            "tool_name": tool,
                            "tool_args": {"destination": destination, "start_date": "2026-03-01", "end_date": "2026-03-05"},
                            "notes": "Weather",
                        }
                    )

            plan.append(
                {
                    "title": "Synthesize itinerary and recommendations",
                    "step_type": "SYNTHESIZE",
                    "tool_name": None,
                    "tool_args": None,
                    "notes": "Produce final plan.",
                }
            )
            return AIMessage(content=json.dumps({"plan": plan}))

        # synthesis answer
        answer = (
            "# Trip Plan\n\n"
            "## Summary\nBalanced trip with practical links.\n\n"
            "## Assumptions\n- Timings and availability may vary.\n\n"
            "## Flights\n- [Google Flights](https://www.google.com/travel/flights)\n\n"
            "## Lodging\n- [Booking.com](https://www.booking.com)\n\n"
            "## Day-by-day\n### Day 1: Arrival and orientation\n### Day 2: Main attractions\n### Day 3: Flexible exploration\n\n"
            "## Transit\nUse public transit and short taxi hops.\n\n"
            "## Weather\nCheck local forecast daily.\n\n"
            "## Budget\nModerate total spend expected.\n\n"
            "## Calendar\nCalendar export is available.\n\n"
            'Note: Visa/health requirements vary; verify with official sources (this is not legal advice).'
        )
        if scenario == "eval_price_fabrication":
            answer += "\n\nEstimated flight cost is $999 per person."
        if scenario == "eval_invalid_link":
            answer += "\n\nBroken booking link: https://"
        return AIMessage(content=answer)


def load_prompts(path: Path) -> list[str]:
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def choose_tools(rng: random.Random) -> list[str]:
    n = rng.choice([1, 1, 2, 2, 3, 4])
    return rng.sample(TOOLS_ALL, n)


def set_env_for_scenario(scenario: str, run_mode: str) -> dict[str, str]:
    prev = {
        "SIMULATE_TOOL_TIMEOUT": os.environ.get("SIMULATE_TOOL_TIMEOUT", ""),
        "SIMULATE_BAD_RETRIEVAL": os.environ.get("SIMULATE_BAD_RETRIEVAL", ""),
        "FAILURE_SEVERITY_OVERRIDE": os.environ.get("FAILURE_SEVERITY_OVERRIDE", ""),
    }
    os.environ["SIMULATE_TOOL_TIMEOUT"] = "true" if scenario in {"tool_timeout", "both_env"} else "false"
    os.environ["SIMULATE_BAD_RETRIEVAL"] = "true" if scenario in {"bad_retrieval", "both_env"} else "false"
    os.environ["FAILURE_SEVERITY_OVERRIDE"] = "critical" if run_mode == "failure" else ""
    return prev


def restore_env(prev: dict[str, str]) -> None:
    for k, v in prev.items():
        if v == "":
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def patch_graph_components() -> None:
    graph_mod.geocode_place = stable_geocode
    graph_mod.build_chat_model = lambda **kwargs: DeterministicRunnable()

    def export_ics_wrapper(state: dict[str, Any], *, runtime_dir):
        scenario = _extract_scenario(state.get("user_query", ""))
        if scenario == "eval_calendar_fail":
            state["ics_path"] = ""
            state["ics_event_count"] = 0
            return state
        return ORIGINAL_EXPORT_ICS(state, runtime_dir=runtime_dir)

    graph_mod.export_ics = export_ics_wrapper


def restore_graph_components() -> None:
    graph_mod.build_chat_model = original_build_chat_model
    graph_mod.export_ics = ORIGINAL_EXPORT_ICS


def run_one(prompt: str, run_id: str, run_mode: str, scenario: str, tools: list[str], base_settings) -> dict[str, Any]:
    prev_env = set_env_for_scenario(scenario, run_mode)
    tracker = FailureTracker(run_id=run_id, user_id=USER_ID, runtime_dir=RUNTIME_DIR)
    tracker.combined_log_path = SINGLE_LOG
    set_failure_tracker(tracker)

    settings = base_settings
    if run_mode == "failure":
        settings = replace(settings, max_tool_retries=3)
    if scenario == "orchestrator_max_iters":
        settings = replace(settings, max_graph_iters=1)
    metrics = MetricsCollector(runtime_dir=RUNTIME_DIR, run_id=run_id, user_id=USER_ID)
    memory = InMemoryStore()
    app = build_app(settings=settings, memory=memory, metrics=metrics)

    tagged_prompt = f"{prompt} [[TOOLS:{','.join(tools)}]] [[SCENARIO:{scenario}]]"
    state: dict[str, Any] = {"run_id": run_id, "user_id": USER_ID, "user_query": tagged_prompt}
    ctx = LogContext(run_id=run_id, user_id=USER_ID)

    log_event(
        logger,
        level=20,
        message="Mixed run started",
        event="mixed_run_start",
        context=ctx,
        data={"run_mode": run_mode, "scenario": scenario, "selected_tools": tools},
    )

    out: dict[str, Any] = {}
    runtime_error = None
    try:
        out = app.invoke(state, config={"recursion_limit": 200})
    except Exception as e:
        runtime_error = f"{type(e).__name__}: {e}"
        try:
            tracker.record_failure(
                category=FailureCategory.UNKNOWN,
                severity=FailureSeverity.HIGH,
                graph_node="runner",
                error_type=type(e).__name__,
                error_message=str(e),
                step_type="RUN",
                step_title="Mixed campaign run",
                context_data={"scenario": scenario, "run_mode": run_mode},
                tags=["runner-exception"],
            )
        except Exception:
            pass

    eval_data = (out.get("evaluation") or {}) if isinstance(out, dict) else {}
    log_event(
        logger,
        level=20,
        message="Mixed run ended",
        event="mixed_run_end",
        context=ctx,
        data={
            "run_mode": run_mode,
            "scenario": scenario,
            "termination_reason": out.get("termination_reason") if isinstance(out, dict) else None,
            "overall_status": eval_data.get("overall_status"),
            "has_hard_gates": bool(eval_data.get("hard_gates")),
            "failure_count": len(tracker.failures),
            "runtime_error": runtime_error,
        },
    )

    if tracker.failure_log_path.exists():
        tracker.failure_log_path.unlink()
    set_failure_tracker(None)
    restore_env(prev_env)

    return {
        "run_id": run_id,
        "run_mode": run_mode,
        "scenario": scenario,
        "selected_tools": tools,
        "termination_reason": out.get("termination_reason") if isinstance(out, dict) else None,
        "overall_status": eval_data.get("overall_status"),
        "failure_count": len(tracker.failures),
        "runtime_error": runtime_error,
    }


def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if SINGLE_LOG.exists():
        SINGLE_LOG.unlink()

    patch_graph_components()

    rng = random.Random(SEED)
    prompts = load_prompts(PROMPTS_FILE)
    chosen_prompts = rng.sample(prompts, TOTAL_RUNS)
    run_modes = (["success"] * SUCCESS_RUNS) + (["failure"] * FAILURE_RUNS)
    rng.shuffle(run_modes)

    failure_scenarios: list[str] = []
    while len(failure_scenarios) < FAILURE_RUNS:
        failure_scenarios.extend(FAILURE_SCENARIOS)
    failure_scenarios = failure_scenarios[:FAILURE_RUNS]
    rng.shuffle(failure_scenarios)

    base_settings = replace(load_settings(), user_id=USER_ID, runtime_dir=RUNTIME_DIR)

    results: list[dict[str, Any]] = []
    fail_idx = 0
    for i in range(TOTAL_RUNS):
        run_id = f"mix-{i+1:03d}"
        mode = run_modes[i]
        scenario = "none"
        if mode == "failure":
            scenario = failure_scenarios[fail_idx]
            fail_idx += 1
        tools = choose_tools(rng)
        res = run_one(chosen_prompts[i], run_id, mode, scenario, tools, base_settings)
        results.append(res)
        print(
            f"[{i+1}/{TOTAL_RUNS}] {run_id} mode={mode} scenario={scenario} "
            f"tools={len(tools)} failures={res['failure_count']} eval={res['overall_status']} "
            f"error={bool(res['runtime_error'])}"
        )

    with SINGLE_LOG.open("a", encoding="utf-8") as f:
        summary_data = {
            "seed": SEED,
            "total_runs": TOTAL_RUNS,
            "success_runs": SUCCESS_RUNS,
            "failure_runs": FAILURE_RUNS,
            "failure_scenarios": FAILURE_SCENARIOS,
            "results": results,
        }
        payload = build_canonical_record(
            ts="summary",
            level="INFO",
            module="scripts.run_mixed_60_single_log",
            message="Mixed campaign summary",
            event="mixed_campaign_summary",
            run_id=None,
            user_id=USER_ID,
            node="runner",
            step_type=None,
            step_id=None,
            step_title="Mixed campaign summary",
            kind="normal",
            data=summary_data,
        )
        f.write(
            json.dumps(payload, ensure_ascii=False)
            + "\n"
        )

    restore_graph_components()
    print(f"Single log: {SINGLE_LOG}")


if __name__ == "__main__":
    main()
