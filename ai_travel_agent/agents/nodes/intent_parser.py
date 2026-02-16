from __future__ import annotations

import json
import re
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

_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_PACE_RE = re.compile(r"\b(relaxed|balanced|packed)\b", re.IGNORECASE)
_TRAVELERS_RE = re.compile(r"\b(\d+)\s*(?:travelers?|people|persons|pax)\b", re.IGNORECASE)
_BUDGET_RE = re.compile(r"budget[^0-9$]*\$?\s*([0-9][0-9,]*)", re.IGNORECASE)


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = _CODE_BLOCK_RE.search(raw)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    start = raw.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(raw[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = raw[start : i + 1]
                try:
                    return json.loads(candidate)
                except Exception:
                    return None
    return None


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[.\n]", text or "") if s.strip()]


def _trim_fragment(fragment: str) -> str:
    frag = (fragment or "").strip()
    if not frag:
        return frag
    lower = frag.lower()
    stop_tokens = [
        " dates",
        " date",
        " budget",
        " for ",
        " with ",
        " interests",
        " pace",
        " please",
        " include",
        " give ",
        " and ",
    ]
    cut = len(frag)
    for token in stop_tokens:
        idx = lower.find(token)
        if idx != -1:
            cut = min(cut, idx)
    frag = frag[:cut]
    frag = frag.strip(" ,;:-")
    return frag


def _heuristic_extract(user_query: str) -> TripConstraints:
    text = user_query or ""
    constraints = TripConstraints()

    # Dates
    dates = _ISO_DATE_RE.findall(text)
    if dates:
        constraints.start_date = dates[0]
        if len(dates) >= 2:
            constraints.end_date = dates[1]

    # Origin/Destination
    for s in _split_sentences(text):
        lower = s.lower()
        if ("travel" in lower or "trip" in lower or "going" in lower or "visit" in lower) and " to " in lower:
            idx = lower.find(" to ")
            frag = _trim_fragment(s[idx + 4 :])
            if frag:
                constraints.destinations = [frag]
        if "flying from" in lower:
            idx = lower.find("flying from")
            frag = _trim_fragment(s[idx + len("flying from") :])
            if frag:
                constraints.origin = frag
        elif "departing from" in lower:
            idx = lower.find("departing from")
            frag = _trim_fragment(s[idx + len("departing from") :])
            if frag:
                constraints.origin = frag
        elif "from " in lower:
            idx = lower.find("from ")
            frag = _trim_fragment(s[idx + len("from ") :])
            if frag and not constraints.origin:
                constraints.origin = frag

        if "interests:" in lower:
            parts = s.split(":", 1)
            if len(parts) == 2:
                raw = parts[1]
                items = [p.strip() for p in re.split(r"[,\n;]+| and ", raw) if p.strip()]
                if items:
                    constraints.interests = items
        if "i like" in lower:
            idx = lower.find("i like")
            raw = s[idx + len("i like") :]
            items = [p.strip() for p in re.split(r"[,\n;]+| and ", raw) if p.strip()]
            if items:
                constraints.interests = items

        if "pace" in lower:
            m = _PACE_RE.search(lower)
            if m:
                constraints.pace = m.group(1).lower()  # type: ignore[assignment]

    # Travelers
    m = _TRAVELERS_RE.search(text)
    if m:
        try:
            constraints.travelers = int(m.group(1))
        except Exception:
            pass

    # Budget
    m = _BUDGET_RE.search(text)
    if m:
        try:
            constraints.budget_usd = float(m.group(1).replace(",", ""))
        except Exception:
            pass

    return constraints


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

    parsed = _extract_json_object(raw)

    if parsed is None:
        constraints = TripConstraints()
    else:
        try:
            constraints = TripConstraints.model_validate(parsed)
        except ValidationError:
            constraints = TripConstraints()

    # Heuristic fill if model returned partial/missing fields.
    heur = _heuristic_extract(user)
    if not constraints.destinations and heur.destinations:
        constraints.destinations = heur.destinations
        constraints.notes.append("Filled destination from user text (heuristic).")
    if not constraints.origin and heur.origin:
        constraints.origin = heur.origin
        constraints.notes.append("Filled origin from user text (heuristic).")
    if not constraints.start_date and heur.start_date:
        constraints.start_date = heur.start_date
        constraints.notes.append("Filled start_date from user text (heuristic).")
    if not constraints.end_date and heur.end_date:
        constraints.end_date = heur.end_date
        constraints.notes.append("Filled end_date from user text (heuristic).")
    if constraints.budget_usd is None and heur.budget_usd is not None:
        constraints.budget_usd = heur.budget_usd
        constraints.notes.append("Filled budget from user text (heuristic).")
    if constraints.travelers is None and heur.travelers is not None:
        constraints.travelers = heur.travelers
        constraints.notes.append("Filled travelers from user text (heuristic).")
    if not constraints.interests and heur.interests:
        constraints.interests = heur.interests
        constraints.notes.append("Filled interests from user text (heuristic).")
    if constraints.pace is None and heur.pace is not None:
        constraints.pace = heur.pace
        constraints.notes.append("Filled pace from user text (heuristic).")

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
