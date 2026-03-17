from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ai_travel_agent.agents.state import Issue, IssueKind, IssueSeverity, StepType
from ai_travel_agent.llm import LLMClient
from ai_travel_agent.observability.logger import get_logger, log_event, log_llm_event

from .utils import log_context_from_state


logger = get_logger(__name__)

_ALLOWED_TOOLS = {
    "flights_search_links",
    "hotels_search_links",
    "things_to_do_links",
    "weather_summary",
    "distance_and_time",
}


class ToolRationale(BaseModel):
    tool_name: str
    reason: str


class ReasoningSummary(BaseModel):
    summary: str
    key_points: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    planner_guidance: list[str] = Field(default_factory=list)
    tool_rationale: list[ToolRationale] = Field(default_factory=list)


SYSTEM = """You are the reasoning engine for a travel-planning workflow.

Return ONLY valid JSON matching this schema:
{
  "summary": "1-2 sentence shareable reasoning summary",
  "key_points": ["short bullet", "..."],
  "risks": ["short bullet", "..."],
  "planner_guidance": ["short instruction", "..."],
  "tool_rationale": [
    {"tool_name": "flights_search_links|hotels_search_links|things_to_do_links|weather_summary|distance_and_time", "reason": "short reason"}
  ]
}

Rules:
- Do NOT reveal hidden chain-of-thought.
- Keep every string concise and operational.
- Mention only externally shareable reasoning.
- Respect links-only and no-live-prices policy.
- If inputs are already validated, focus on planning tradeoffs and constraints.
"""


def _parse_reasoning(raw: str) -> ReasoningSummary | None:
    try:
        data = json.loads(raw)
    except Exception:
        return None
    try:
        parsed = ReasoningSummary.model_validate(data)
    except ValidationError:
        return None

    filtered = [
        ToolRationale(tool_name=entry.tool_name, reason=entry.reason)
        for entry in parsed.tool_rationale
        if entry.tool_name in _ALLOWED_TOOLS and entry.reason.strip()
    ]
    parsed.tool_rationale = filtered[:5]
    parsed.key_points = [item.strip() for item in parsed.key_points if item.strip()][:5]
    parsed.risks = [item.strip() for item in parsed.risks if item.strip()][:4]
    parsed.planner_guidance = [item.strip() for item in parsed.planner_guidance if item.strip()][:5]
    parsed.summary = parsed.summary.strip()
    return parsed if parsed.summary else None


def _build_fallback_reasoning(state: dict[str, Any]) -> ReasoningSummary:
    constraints = state.get("constraints") or {}
    grounded_places = state.get("grounded_places") or {}
    warnings = [w for w in (state.get("validation_warnings") or []) if isinstance(w, str)]

    dests = [d for d in (constraints.get("destinations") or []) if isinstance(d, str) and d.strip()]
    origin = constraints.get("origin")
    travelers = constraints.get("travelers")
    pace = constraints.get("pace")
    start_date = constraints.get("start_date")
    end_date = constraints.get("end_date")
    budget = constraints.get("budget_usd")

    trip_scope = ", ".join(dests[:3]) if dests else "the requested destination"
    summary_parts = [f"Plan a {pace or 'balanced'} trip covering {trip_scope}."]
    if origin:
        summary_parts.append(f"Use {origin} as the departure point.")
    if start_date and end_date:
        summary_parts.append(f"Keep recommendations aligned to {start_date} through {end_date}.")

    key_points: list[str] = []
    if travelers:
        key_points.append(f"Optimize for {travelers} traveler(s), not a solo itinerary.")
    if budget is not None:
        key_points.append("Keep budget guidance heuristic and avoid quoting live prices.")
    if grounded_places.get("origin") or grounded_places.get("destinations"):
        key_points.append("Use grounded place names for destination-specific links and routing.")
    if constraints.get("interests"):
        interests = ", ".join(str(item) for item in constraints.get("interests", [])[:4])
        key_points.append(f"Bias the itinerary toward {interests}.")

    risks: list[str] = warnings[:3]
    if not risks and len(dests) > 1:
        risks.append("Multi-destination trip needs destination-specific links and realistic transit pacing.")
    if not risks and not grounded_places:
        risks.append("Place grounding is limited, so generated links may need manual verification.")

    planner_guidance = [
        "Prefer one tool call per destination when flights or hotels differ by city.",
        "Keep itinerary pacing relaxed unless the user explicitly asks for a packed schedule.",
        "Surface assumptions instead of inventing missing operational details.",
        "Use tool outputs as sources for links and weather notes before final synthesis.",
    ]
    if budget is not None:
        planner_guidance.append("Budget section should use percentages or user-provided totals only.")

    tool_rationale: list[ToolRationale] = []
    if origin and dests and start_date:
        tool_rationale.append(
            ToolRationale(
                tool_name="flights_search_links",
                reason="Flight search links anchor the trip around the requested departure city and start date.",
            )
        )
    if dests and start_date and end_date:
        tool_rationale.append(
            ToolRationale(
                tool_name="hotels_search_links",
                reason="Hotel links should match the destination and travel window.",
            )
        )
        tool_rationale.append(
            ToolRationale(
                tool_name="weather_summary",
                reason="Weather context helps shape packing guidance and daily activity choices.",
            )
        )
    if dests:
        tool_rationale.append(
            ToolRationale(
                tool_name="things_to_do_links",
                reason="Discovery links should reflect the traveler interests and destination.",
            )
        )

    return ReasoningSummary(
        summary=" ".join(summary_parts),
        key_points=key_points,
        risks=risks,
        planner_guidance=planner_guidance[:5],
        tool_rationale=tool_rationale[:5],
    )


def _reasoning_lines(reasoning: ReasoningSummary) -> list[str]:
    lines: list[str] = [reasoning.summary]
    lines.extend(reasoning.key_points[:3])
    lines.extend(f"Risk: {item}" for item in reasoning.risks[:2])
    lines.extend(f"Plan: {item}" for item in reasoning.planner_guidance[:2])
    lines.extend(
        f"Tool {entry.tool_name}: {entry.reason}"
        for entry in reasoning.tool_rationale[:3]
    )
    deduped: list[str] = []
    seen: set[str] = set()
    for line in lines:
        text = line.strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped[:8]


def reasoning_engine(state: dict[str, Any], *, llm: LLMClient) -> dict[str, Any]:
    state["current_step"] = {"step_type": StepType.REASONING, "title": "Reason about constraints and planning strategy"}
    state.setdefault("issues", [])

    prompt = {
        "user_query": state.get("user_query", ""),
        "constraints": state.get("constraints") or {},
        "grounded_places": state.get("grounded_places") or {},
        "validation_warnings": state.get("validation_warnings") or [],
        "context_hits": [
            {
                "text": (hit or {}).get("text"),
                "type": ((hit or {}).get("metadata") or {}).get("type"),
            }
            for hit in (state.get("context_hits") or [])[:3]
        ],
        "policy": {
            "links_only": True,
            "no_live_prices": True,
        },
    }

    reasoning: ReasoningSummary | None = None
    used_fallback = False
    llm_input = json.dumps(prompt, ensure_ascii=False)
    raw = ""
    try:
        raw = llm.invoke_text(
            system=SYSTEM,
            user=llm_input,
            tags={"node": "reasoning_engine"},
            state=state,
            context=log_context_from_state(state, graph_node="reasoning_engine"),
        )
        reasoning = _parse_reasoning(raw)
    except Exception as exc:
        state["issues"].append(
            Issue(
                kind=IssueKind.PLANNING_ERROR,
                severity=IssueSeverity.MINOR,
                node="reasoning_engine",
                message=f"Reasoning engine failed; using deterministic reasoning summary. {exc}",
                suggested_actions=["fallback_reasoning_summary"],
            ).model_dump()
        )

    if reasoning is None:
        used_fallback = True
        reasoning = _build_fallback_reasoning(state)
        state["issues"].append(
            Issue(
                kind=IssueKind.PLANNING_ERROR,
                severity=IssueSeverity.MINOR,
                node="reasoning_engine",
                message="Reasoning engine returned invalid output; using deterministic reasoning summary.",
                suggested_actions=["fallback_reasoning_summary"],
            ).model_dump()
        )

    payload = reasoning.model_dump()
    payload["used_fallback"] = used_fallback
    lines = _reasoning_lines(reasoning)
    state["reasoning_summary"] = payload
    state["reasoning_log_lines"] = lines
    log_llm_event(
        "reasoning_engine",
        {"system": SYSTEM, "user": llm_input},
        raw,
        {
            **llm.telemetry_metadata(),
            "intent_decision": state.get("intent_decision"),
            "validation_decision": state.get("validation_decision"),
            "planner_decision": {
                "reasoning_summary": reasoning.summary,
                "tool_rationale": [item.model_dump() for item in reasoning.tool_rationale],
                "used_fallback": used_fallback,
            },
            "tool_selected": [item.tool_name for item in reasoning.tool_rationale],
            "synthesis_decision": state.get("synthesis_decision"),
        },
        logger=logger,
        context=log_context_from_state(state, graph_node="reasoning_engine"),
    )

    log_event(
        logger,
        level=logging.INFO,
        message=f"Reasoning summary: {reasoning.summary}",
        event="reasoning_summary",
        context=log_context_from_state(state, graph_node="reasoning_engine"),
        data={
            "summary": reasoning.summary,
            "key_points": reasoning.key_points,
            "risks": reasoning.risks,
            "planner_guidance": reasoning.planner_guidance,
            "tool_rationale": [item.model_dump() for item in reasoning.tool_rationale],
            "used_fallback": used_fallback,
        },
    )
    return state
