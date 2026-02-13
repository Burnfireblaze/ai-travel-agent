from __future__ import annotations

import logging
import re
import time
from typing import Any

from ai_travel_agent.agents.state import StepType, ToolResult
from ai_travel_agent.llm import LLMClient
from ai_travel_agent.observability.logger import get_logger, log_event
from ai_travel_agent.observability.metrics import MetricsCollector
from ai_travel_agent.tools import ToolRegistry

from .utils import log_context_from_state


logger = get_logger(__name__)


SYNTH_SYSTEM = """You are a travel planner. Using the constraints and tool results, produce a structured plan:
- High-level summary
- Assumptions (explicitly list missing constraints)
- Flights (links-only)
- Lodging (links-only)
- Day-by-day itinerary
- Transit notes
- Weather
- Budget estimate (heuristic; do not claim live prices)
- Calendar export note
Include this disclaimer line exactly once:
"Note: Visa/health requirements vary; verify with official sources (this is not legal advice)."
"""


def executor(
    state: dict[str, Any],
    *,
    tools: ToolRegistry,
    llm: LLMClient,
    metrics: MetricsCollector | None = None,
) -> dict[str, Any]:
    step = state.get("current_step") or {}
    plan = state.get("plan") or []
    idx = state.get("current_step_index", 0)
    if not step:
        return state

    if step.get("step_type") == StepType.TOOL_CALL and step.get("tool_name"):
        tool_name = step["tool_name"]
        tool_args = step.get("tool_args") or {}

        started = time.perf_counter()
        try:
            if metrics is not None:
                metrics.inc("tool_calls", 1)
            out = tools.call(tool_name, **tool_args)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if metrics is not None:
                metrics.observe_ms(f"tool_latency_ms.{tool_name}", elapsed_ms)
            log_event(
                logger,
                level=logging.INFO,
                message="Tool call completed",
                event="tool_result",
                context=log_context_from_state(state, graph_node="executor"),
                data={"tool_name": tool_name, "latency_ms": round(elapsed_ms, 2)},
            )
            state.setdefault("tool_results", []).append(
                ToolResult(
                    step_id=step["id"],
                    tool_name=tool_name,
                    data=dict(out),
                    summary=str(out.get("summary", "")),
                    links=list(out.get("links", [])) if isinstance(out.get("links"), list) else [],
                ).model_dump()
            )
            plan[idx]["status"] = "done"
        except Exception as e:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if metrics is not None:
                metrics.inc("tool_errors", 1)
                metrics.observe_ms(f"tool_latency_ms.{tool_name}", elapsed_ms)
            log_event(
                logger,
                level=logging.ERROR,
                message="Tool call failed",
                event="tool_error",
                context=log_context_from_state(state, graph_node="executor"),
                data={"tool_name": tool_name, "latency_ms": round(elapsed_ms, 2), "error": str(e)},
            )
            plan[idx]["status"] = "blocked"
        state["plan"] = plan
        return state

    # synthesize
    constraints = state.get("constraints") or {}
    tool_results = state.get("tool_results") or []
    context_hits = state.get("context_hits") or []
    prompt = (
        f"User query: {state.get('user_query','')}\n\n"
        f"Constraints (JSON): {constraints}\n\n"
        f"Context hits: {context_hits}\n\n"
        f"Tool results: {tool_results}\n\n"
        "Write the final response in Markdown with the required sections."
    )
    answer = llm.invoke_text(system=SYNTH_SYSTEM, user=prompt, tags={"node": "executor", "kind": "synthesize"})
    state["final_answer"] = answer
    # Best-effort extract day titles for ICS.
    day_titles: list[str] = []
    for m in re.finditer(r"^#+\s*Day\s*(\d+)\s*[:\-]?\s*(.*)$", answer, flags=re.IGNORECASE | re.MULTILINE):
        title = (m.group(2) or "").strip()
        day_titles.append(title or f"Day {m.group(1)}")
    state["itinerary_day_titles"] = day_titles[:21]
    plan[idx]["status"] = "done"
    state["plan"] = plan
    return state
