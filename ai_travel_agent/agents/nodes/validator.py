from __future__ import annotations

import re
from datetime import date
from typing import Any, Callable

from ai_travel_agent.agents.state import Issue, IssueKind, IssueSeverity, StepType, TripConstraints


ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
IATA_RE = re.compile(r"^[A-Za-z]{3}$")
_CONSONANT_RUN_RE = re.compile(r"[bcdfghjklmnpqrstvwxyz]{6,}", re.IGNORECASE)


def _parse_iso_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def _extract_iso_dates_from_text(text: str) -> list[str]:
    return ISO_DATE_RE.findall(text or "")


def _extract_memory_fields(context_hits: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Best-effort extraction of stable profile/preference fields from memory hits.
    Current memory_writer stores:
      - "Home origin: <...>" as type=profile
      - "User interests: a, b, c" as type=preference
    """
    memory_origin: str | None = None
    memory_interests: list[str] | None = None

    for hit in context_hits or []:
        meta = (hit or {}).get("metadata") or {}
        doc_type = meta.get("type")
        text = (hit or {}).get("text") or ""
        if not isinstance(text, str):
            continue

        if doc_type == "profile" and text.lower().startswith("home origin:") and memory_origin is None:
            memory_origin = text.split(":", 1)[-1].strip() or None
        if doc_type == "preference" and text.lower().startswith("user interests:") and memory_interests is None:
            raw = text.split(":", 1)[-1].strip()
            memory_interests = [x.strip() for x in raw.split(",") if x.strip()]

    return {"origin": memory_origin, "interests": memory_interests or []}


def _looks_explicit(value: str | None, user_query: str) -> bool:
    if not value:
        return False
    uq = (user_query or "").lower()
    return value.lower() in uq


def _normalize_iata(code: str) -> str | None:
    c = (code or "").strip()
    if not IATA_RE.match(c):
        return None
    return c.upper()


def _is_suspicious_place_name(name: str) -> bool:
    """
    Heuristic only. Used *only* when we cannot geocode (e.g. offline) to avoid confidently planning for gibberish inputs.
    """
    s = (name or "").strip()
    if not s:
        return True
    if any(ch.isdigit() for ch in s):
        return True
    # Single-token long strings with very low vowel ratio or long consonant runs are likely gibberish.
    token_like = (" " not in s) and ("," not in s) and ("-" not in s)
    if token_like and len(s) >= 10:
        letters = [c for c in s.lower() if c.isalpha()]
        if letters:
            vowels = sum(1 for c in letters if c in "aeiou")
            if vowels / max(1, len(letters)) < 0.20:
                return True
        if _CONSONANT_RUN_RE.search(s):
            return True
    return False


def validator(
    state: dict[str, Any],
    *,
    geocode_fn: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Pre-planner validator / grounder.
    - Validates and normalizes core inputs (dates, origin, destination)
    - Grounds places via geocoding (online + fallback)
    - Detects conflicts (memory vs user constraints) and asks user to resolve
    """
    state["current_step"] = {"step_type": StepType.VALIDATE_INPUTS, "title": "Validate inputs and resolve conflicts"}
    state.setdefault("validation_warnings", [])
    state.setdefault("conflicts_detected", [])
    state.setdefault("issues", [])
    state.setdefault("resolved_conflicts", [])
    state.pop("pending_disambiguation", None)
    state.pop("pending_conflict", None)
    state.pop("pending_fixup", None)

    user_query = state.get("user_query", "") or ""
    context_hits = state.get("context_hits") or []

    try:
        constraints = TripConstraints.model_validate(state.get("constraints") or {})
    except Exception:
        constraints = TripConstraints()

    # Fill dates from user_query if missing.
    extracted_dates = _extract_iso_dates_from_text(user_query)
    if not constraints.start_date and extracted_dates:
        constraints.start_date = extracted_dates[0]
        constraints.notes.append("Filled start_date from user text.")
    if not constraints.end_date and len(extracted_dates) >= 2:
        constraints.end_date = extracted_dates[1]
        constraints.notes.append("Filled end_date from user text.")

    # Validate date formats.
    ds = _parse_iso_date(constraints.start_date)
    de = _parse_iso_date(constraints.end_date)
    if constraints.start_date and not ds:
        issue = Issue(
            kind=IssueKind.VALIDATION_ERROR,
            severity=IssueSeverity.BLOCKING,
            node="validator",
            message=f"Invalid start_date '{constraints.start_date}'. Expected YYYY-MM-DD.",
            suggested_actions=["provide_start_date_iso"],
        )
        state["issues"].append(issue.model_dump())
        state["needs_user_input"] = True
        state["pending_fixup"] = {"field": "start_date"}
        state["clarifying_questions"] = ["Your start date looks invalid. Please provide start date as YYYY-MM-DD."]
        state["termination_reason"] = "asked_user"
        return state
    if constraints.end_date and not de:
        issue = Issue(
            kind=IssueKind.VALIDATION_ERROR,
            severity=IssueSeverity.BLOCKING,
            node="validator",
            message=f"Invalid end_date '{constraints.end_date}'. Expected YYYY-MM-DD.",
            suggested_actions=["provide_end_date_iso"],
        )
        state["issues"].append(issue.model_dump())
        state["needs_user_input"] = True
        state["pending_fixup"] = {"field": "end_date"}
        state["clarifying_questions"] = ["Your end date looks invalid. Please provide end date as YYYY-MM-DD."]
        state["termination_reason"] = "asked_user"
        return state

    # Normalize swapped dates.
    if ds and de and de < ds:
        constraints.start_date, constraints.end_date = constraints.end_date, constraints.start_date
        constraints.notes.append("Swapped start/end dates because end_date was earlier than start_date.")

    # Memory defaults + conflict detection.
    mem = _extract_memory_fields(context_hits)
    mem_origin = mem.get("origin")
    mem_interests = mem.get("interests") or []

    if mem_origin:
        if not constraints.origin:
            constraints.origin = mem_origin
            constraints.notes.append("Filled origin from memory.")
        elif constraints.origin.strip().lower() != mem_origin.strip().lower():
            # Core-only clarification policy: never ask for memory conflicts.
            # If the origin appears explicitly in the user's request, trust the request; otherwise, prefer memory.
            if _looks_explicit(constraints.origin, user_query):
                state["validation_warnings"].append(
                    f"Saved origin '{mem_origin}' differs from request '{constraints.origin}'; using request origin."
                )
            else:
                state["validation_warnings"].append(
                    f"Saved origin '{mem_origin}' differs from parsed origin '{constraints.origin}'; using saved origin."
                )
                constraints.origin = mem_origin
                constraints.notes.append("Overrode origin with memory (request did not explicitly specify origin).")

    if mem_interests:
        if not constraints.interests:
            constraints.interests = mem_interests
            constraints.notes.append("Filled interests from memory.")
        else:
            # Core-only clarification policy: never ask for memory conflicts.
            cur_list = [x.strip() for x in constraints.interests if isinstance(x, str) and x.strip()]
            mem_list = [x.strip() for x in mem_interests if isinstance(x, str) and x.strip()]
            cur = {x.lower() for x in cur_list}
            mems = {x.lower() for x in mem_list}
            if cur and mems and cur != mems:
                state["validation_warnings"].append(
                    f"Saved interests {sorted(mems)} differ from request {sorted(cur)}; using request interests."
                )

    # Required core fields.
    missing_core: list[str] = []
    if not constraints.destinations:
        missing_core.append("destination")
    if not constraints.origin:
        missing_core.append("origin")
    if not constraints.start_date:
        missing_core.append("start date")
    if not constraints.end_date:
        missing_core.append("end date")

    if missing_core:
        issue = Issue(
            kind=IssueKind.VALIDATION_ERROR,
            severity=IssueSeverity.BLOCKING,
            node="validator",
            message=f"Missing core fields: {', '.join(missing_core)}.",
            suggested_actions=["provide_missing_core_fields"],
            details={"missing": missing_core},
        )
        state["issues"].append(issue.model_dump())
        state["needs_user_input"] = True
        state["pending_fixup"] = {"kind": "missing_core", "missing": missing_core}
        state["clarifying_questions"] = [f"Please provide {m}." for m in missing_core[:4]]
        state["termination_reason"] = "asked_user"
        return state

    # Geocode grounding.
    grounded: dict[str, Any] = {"origin": None, "destinations": []}
    if constraints.origin:
        iata = _normalize_iata(constraints.origin)
        if iata:
            grounded["origin"] = {"iata": iata}
        elif geocode_fn is not None:
            try:
                g = geocode_fn(constraints.origin)
                if g.get("ambiguous"):
                    issue = Issue(
                        kind=IssueKind.VALIDATION_ERROR,
                        severity=IssueSeverity.BLOCKING,
                        node="validator",
                        message=f"Origin '{constraints.origin}' is ambiguous.",
                        suggested_actions=["disambiguate_origin"],
                        details={"candidates": (g.get("candidates") or [])[:3]},
                    )
                    state["issues"].append(issue.model_dump())
                    state["needs_user_input"] = True
                    cands = g.get("candidates") or []
                    options_list = [
                        f"{c.get('name')}, {c.get('admin1') or ''} {c.get('country') or ''}".strip()
                        for c in cands[:3]
                        if isinstance(c, dict)
                    ]
                    options = "; ".join([f"{i+1}) {o}" for i, o in enumerate(options_list)])
                    state["pending_disambiguation"] = {
                        "field": "origin",
                        "raw_value": constraints.origin,
                        "options": options_list,
                        "candidates": (g.get("candidates") or [])[:3],
                    }
                    state["clarifying_questions"] = [
                        f"Your origin '{constraints.origin}' is ambiguous. Reply with 1-{len(options_list)}. Options: {options}",
                    ]
                    state["termination_reason"] = "asked_user"
                    return state
                candidates = g.get("candidates") or []
                if not g.get("best") and not candidates:
                    issue = Issue(
                        kind=IssueKind.VALIDATION_ERROR,
                        severity=IssueSeverity.BLOCKING,
                        node="validator",
                        message=f"Origin '{constraints.origin}' could not be found.",
                        suggested_actions=["provide_valid_origin"],
                        details={"origin": constraints.origin},
                    )
                    state["issues"].append(issue.model_dump())
                    state["needs_user_input"] = True
                    state["pending_fixup"] = {"field": "origin"}
                    state["clarifying_questions"] = [
                        f"I couldn't find your origin '{constraints.origin}'. Please provide a real departure city/airport (ideally an IATA code like SFO/JFK or 'City, Country').",
                    ]
                    state["termination_reason"] = "asked_user"
                    return state
                grounded["origin"] = g.get("best")
            except Exception as e:
                state["validation_warnings"].append(f"Unable to geocode origin '{constraints.origin}': {e}")
                if _is_suspicious_place_name(constraints.origin):
                    issue = Issue(
                        kind=IssueKind.VALIDATION_ERROR,
                        severity=IssueSeverity.BLOCKING,
                        node="validator",
                        message=f"Couldn't validate origin '{constraints.origin}' (geocoding unavailable) and it looks invalid.",
                        suggested_actions=["provide_valid_origin"],
                        details={"origin": constraints.origin, "error": str(e)},
                    )
                    state["issues"].append(issue.model_dump())
                    state["needs_user_input"] = True
                    state["clarifying_questions"] = [
                        f"I couldn't validate your origin '{constraints.origin}'. Please provide a real departure city/airport (e.g. 'San Francisco, US' or IATA like SFO).",
                    ]
                    state["termination_reason"] = "asked_user"
                    return state

    if geocode_fn is not None:
        for dest in constraints.destinations:
            if not isinstance(dest, str) or not dest.strip():
                continue
            iata = _normalize_iata(dest)
            if iata:
                grounded["destinations"].append({"iata": iata})
                continue
            try:
                g = geocode_fn(dest)
                if g.get("ambiguous"):
                    issue = Issue(
                        kind=IssueKind.VALIDATION_ERROR,
                        severity=IssueSeverity.BLOCKING,
                        node="validator",
                        message=f"Destination '{dest}' is ambiguous.",
                        suggested_actions=["disambiguate_destination"],
                        details={"destination": dest, "candidates": (g.get("candidates") or [])[:3]},
                    )
                    state["issues"].append(issue.model_dump())
                    state["needs_user_input"] = True
                    cands = g.get("candidates") or []
                    options_list = [
                        f"{c.get('name')}, {c.get('admin1') or ''} {c.get('country') or ''}".strip()
                        for c in cands[:3]
                        if isinstance(c, dict)
                    ]
                    options = "; ".join([f"{i+1}) {o}" for i, o in enumerate(options_list)])
                    state["pending_disambiguation"] = {
                        "field": "destinations",
                        "raw_value": dest,
                        "options": options_list,
                        "candidates": (g.get("candidates") or [])[:3],
                    }
                    state["clarifying_questions"] = [
                        f"Your destination '{dest}' is ambiguous. Reply with 1-{len(options_list)}. Options: {options}",
                    ]
                    state["termination_reason"] = "asked_user"
                    return state
                candidates = g.get("candidates") or []
                if not g.get("best") and not candidates:
                    issue = Issue(
                        kind=IssueKind.VALIDATION_ERROR,
                        severity=IssueSeverity.BLOCKING,
                        node="validator",
                        message=f"Destination '{dest}' could not be found.",
                        suggested_actions=["provide_valid_destination"],
                        details={"destination": dest},
                    )
                    state["issues"].append(issue.model_dump())
                    state["needs_user_input"] = True
                    state["pending_fixup"] = {"field": "destinations"}
                    state["clarifying_questions"] = [
                        f"I couldn't find your destination '{dest}'. Please provide a real city/country (e.g. 'Bangkok, Thailand').",
                    ]
                    state["termination_reason"] = "asked_user"
                    return state
                grounded["destinations"].append(g.get("best"))
            except Exception as e:
                state["validation_warnings"].append(f"Unable to geocode destination '{dest}': {e}")
                if _is_suspicious_place_name(dest):
                    issue = Issue(
                        kind=IssueKind.VALIDATION_ERROR,
                        severity=IssueSeverity.BLOCKING,
                        node="validator",
                        message=f"Couldn't validate destination '{dest}' (geocoding unavailable) and it looks invalid.",
                        suggested_actions=["provide_valid_destination"],
                        details={"destination": dest, "error": str(e)},
                    )
                    state["issues"].append(issue.model_dump())
                    state["needs_user_input"] = True
                    state["clarifying_questions"] = [
                        f"I couldn't validate your destination '{dest}'. Please provide a real city/country (e.g. 'Bangkok, Thailand') so I can plan accurately.",
                    ]
                    state["termination_reason"] = "asked_user"
                    return state
                grounded["destinations"].append({"name": dest})

    state["constraints"] = constraints.model_dump()
    state["grounded_places"] = grounded
    state["needs_user_input"] = False
    state["clarifying_questions"] = []
    return state
