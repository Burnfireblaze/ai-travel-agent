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

    overrides = state.get("constraint_overrides")
    if isinstance(overrides, dict) and overrides:
        if "origin" in overrides and isinstance(overrides.get("origin"), str) and overrides["origin"].strip():
            constraints.origin = overrides["origin"].strip()
            constraints.notes.append("Applied manual override for origin.")
        if "destinations" in overrides:
            ds = overrides.get("destinations")
            if isinstance(ds, list):
                cleaned = [str(x).strip() for x in ds if str(x).strip()]
                if cleaned:
                    constraints.destinations = cleaned
                    constraints.notes.append("Applied manual override for destinations.")
        if "start_date" in overrides and isinstance(overrides.get("start_date"), str) and overrides["start_date"].strip():
            constraints.start_date = overrides["start_date"].strip()
            constraints.notes.append("Applied manual override for start_date.")
        if "end_date" in overrides and isinstance(overrides.get("end_date"), str) and overrides["end_date"].strip():
            constraints.end_date = overrides["end_date"].strip()
            constraints.notes.append("Applied manual override for end_date.")
        if "budget_usd" in overrides:
            try:
                b = float(overrides.get("budget_usd"))
                constraints.budget_usd = b
                constraints.notes.append("Applied manual override for budget_usd.")
            except Exception:
                pass
        if "travelers" in overrides:
            try:
                t = int(overrides.get("travelers"))
                constraints.travelers = t
                constraints.notes.append("Applied manual override for travelers.")
            except Exception:
                pass
        if "pace" in overrides and isinstance(overrides.get("pace"), str) and overrides["pace"].strip():
            p = overrides["pace"].strip().lower()
            if p in {"relaxed", "balanced", "packed"}:
                constraints.pace = p  # type: ignore[assignment]
                constraints.notes.append("Applied manual override for pace.")
        if "interests" in overrides:
            ints = overrides.get("interests")
            if isinstance(ints, list):
                cleaned = [str(x).strip() for x in ints if str(x).strip()]
                if cleaned:
                    constraints.interests = cleaned
                    constraints.notes.append("Applied manual override for interests.")
        # Clear so overrides don't accidentally persist across future turns in the same run.
        state["constraint_overrides"] = {}

    state["constraints"] = constraints.model_dump()
    qs = _clarifying_questions(constraints)
    # Core-only clarification: ask only for missing core fields.
    if qs:
        state["needs_user_input"] = True
        state["clarifying_questions"] = qs[:4]
        state["termination_reason"] = "asked_user"
    else:
        state["needs_user_input"] = False
        state["clarifying_questions"] = []
    return state
