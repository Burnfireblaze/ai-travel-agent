from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from ai_travel_agent.agents.state import StepType, TripConstraints
from ai_travel_agent.llm import LLMClient


SYSTEM = """You are a travel assistant. Extract trip constraints from the user's request.
Return ONLY valid JSON matching this schema:
{
  "origin": string|null,
  "destinations": string[],
  "start_date": "YYYY-MM-DD"|null,
  "end_date": "YYYY-MM-DD"|null,
  "budget_usd": number|null,
  "travelers": integer|null,
  "interests": string[],
  "pace": "relaxed"|"balanced"|"packed"|null,
  "notes": string[]
}
If a field is unknown, use null or empty list.
"""


def _clarifying_questions(constraints: TripConstraints) -> list[str]:
    qs: list[str] = []
    if not constraints.destinations:
        qs.append("Where do you want to travel (destination city/country)?")
    if not constraints.start_date:
        qs.append("What is your start date? (YYYY-MM-DD)")
    if not constraints.end_date:
        qs.append("What is your end date? (YYYY-MM-DD)")
    if not constraints.origin:
        qs.append("What city/airport are you departing from?")
    if constraints.travelers is None:
        qs.append("How many travelers?")
    if constraints.budget_usd is None:
        qs.append("What is your approximate budget in USD (flight + lodging + activities)?")
    return qs


def intent_parser(state: dict[str, Any], *, llm: LLMClient) -> dict[str, Any]:
    state["current_step"] = {"step_type": StepType.INTENT_PARSE, "title": "Parse intent and constraints"}
    user = state.get("user_query", "")
    raw = llm.invoke_text(system=SYSTEM, user=user, tags={"node": "intent_parser"})

    parsed: dict[str, Any] | None = None
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None

    if parsed is None:
        constraints = TripConstraints()
    else:
        try:
            constraints = TripConstraints.model_validate(parsed)
        except ValidationError:
            constraints = TripConstraints()

    state["constraints"] = constraints.model_dump()
    qs = _clarifying_questions(constraints)
    if qs and len(qs) >= 2:
        state["needs_user_input"] = True
        state["clarifying_questions"] = qs[:4]
        state["termination_reason"] = "asked_user"
    else:
        state["needs_user_input"] = False
        state["clarifying_questions"] = []
    return state
