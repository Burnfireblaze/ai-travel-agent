from __future__ import annotations

import json
from typing import Any

from ai_travel_agent.agents.state import Issue, IssueKind, IssueSeverity, PlanStep, StepType
from ai_travel_agent.llm import LLMClient


ALLOWED_STEP_TYPES = {StepType.RETRIEVE_CONTEXT, StepType.TOOL_CALL, StepType.SYNTHESIZE}
ALLOWED_TOOLS = {
    "flights_search_links",
    "hotels_search_links",
    "things_to_do_links",
    "weather_summary",
    "distance_and_time",
}


SYSTEM = """You are the planning brain for a links-only travel agent.

You MUST:
1) Decompose the user's travel request into steps.
2) Select tools (from the allowlist) and their arguments.
3) Optionally add RETRIEVE_CONTEXT steps if additional memory retrieval is needed.

MVP RULES:
- No booking. No live prices/availability. Provide search links and an itinerary.
- Output MUST be only valid JSON matching the schema.
- Keep the plan short (<= 12 steps).

Allowed step types: RETRIEVE_CONTEXT, TOOL_CALL, SYNTHESIZE
Allowed tools:
- flights_search_links(origin, destination, start_date)
- hotels_search_links(destination, start_date, end_date, neighborhood=null)
- things_to_do_links(destination, interests=list)
- weather_summary(destination, start_date, end_date)
- distance_and_time(origin, destination, mode="driving")

Schema:
{
  "plan": [
    {
      "title": "string",
      "step_type": "RETRIEVE_CONTEXT|TOOL_CALL|SYNTHESIZE",
      "tool_name": "string|null",
      "tool_args": { ... } | null,
      "notes": "short rationale (1-2 sentences)"
    }
  ]
}
"""


def _safe_json(raw: str) -> dict[str, Any] | None:
    try:
        return json.loads(raw)
    except Exception:
        return None


def _steps_from_plan_items(items: list[Any]) -> list[PlanStep]:
    steps: list[PlanStep] = []
    for it in items[:12]:
        if not isinstance(it, dict):
            continue
        step_type = it.get("step_type")
        if step_type not in {st.value for st in ALLOWED_STEP_TYPES}:
            continue
        st = StepType(step_type)
        tool_name = it.get("tool_name")
        if st == StepType.TOOL_CALL:
            if not tool_name or tool_name not in ALLOWED_TOOLS:
                continue
        else:
            tool_name = None
        tool_args = it.get("tool_args") if isinstance(it.get("tool_args"), dict) else None
        steps.append(
            PlanStep(
                title=str(it.get("title") or "Step"),
                step_type=st,
                tool_name=tool_name,
                tool_args=tool_args,
                notes=str(it.get("notes") or ""),
            )
        )
    return steps


def brain_planner(state: dict[str, Any], *, llm: LLMClient) -> dict[str, Any]:
    state["current_step"] = {"step_type": StepType.PLAN_DRAFT, "title": "Brain planner: decompose and select tools"}
    state.setdefault("issues", [])

    prompt = {
        "user_query": state.get("user_query", ""),
        "constraints": state.get("constraints") or {},
        "grounded_places": state.get("grounded_places") or {},
        "context_hits_count": len(state.get("context_hits") or []),
        "policy": {
            "links_only": True,
            "no_live_prices": True,
        },
    }
    raw = llm.invoke_text(system=SYSTEM, user=json.dumps(prompt, ensure_ascii=False), tags={"node": "brain_planner"})
    data = _safe_json(raw) or {}
    items = data.get("plan") if isinstance(data.get("plan"), list) else None

    steps: list[PlanStep] = _steps_from_plan_items(items) if items else []

    if not steps:
        state["issues"].append(
            Issue(
                kind=IssueKind.PLANNING_ERROR,
                severity=IssueSeverity.MAJOR,
                node="brain_planner",
                message="Brain planner returned invalid or empty plan JSON; falling back to deterministic planner.",
                suggested_actions=["fallback_planner"],
            ).model_dump()
        )
        from ai_travel_agent.agents.nodes.planner import planner as fallback_planner

        return fallback_planner(state)

    state["plan"] = [s.model_dump() for s in steps]
    state.setdefault("tool_results", [])
    state["current_step_index"] = 0
    return state

