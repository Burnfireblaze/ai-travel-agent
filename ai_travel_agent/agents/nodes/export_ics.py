from __future__ import annotations

import re
from typing import Any

from ai_travel_agent.agents.state import StepType
from ai_travel_agent.observability.telemetry import TelemetryController
from .utils import log_context_from_state
from ai_travel_agent.tools.calendar_ics import create_itinerary_ics, write_ics_bytes


def _slug(s: str) -> str:
    s = (s or "trip").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60] or "trip"


def export_ics(state: dict[str, Any], *, runtime_dir, telemetry: TelemetryController | None = None) -> dict[str, Any]:
    state["current_step"] = {"step_type": StepType.EXPORT_ICS, "title": "Export itinerary calendar (.ics)"}
    constraints = state.get("constraints") or {}
    start_date = constraints.get("start_date")
    end_date = constraints.get("end_date")
    dests = constraints.get("destinations") or []
    destination = dests[0] if dests else "Trip"
    if not start_date or not end_date:
        state["ics_path"] = ""
        if telemetry is not None:
            telemetry.trace(
                event="export_ics",
                context=log_context_from_state(state, graph_node="export_ics"),
                data={"skipped": True, "reason": "missing_dates"},
            )
        return state
    day_titles = state.get("itinerary_day_titles") or None
    ics = create_itinerary_ics(
        trip_name=f"{destination} trip",
        start_date=start_date,
        end_date=end_date,
        day_titles=day_titles,
    )
    filename = f"{_slug(destination)}-{start_date}-itinerary.ics"
    path = write_ics_bytes(ics_bytes=ics["ics_bytes"], runtime_dir=runtime_dir, filename=filename)
    state["ics_path"] = str(path)
    try:
        state["ics_event_count"] = int(ics.get("event_count") or 0)
    except Exception:
        state["ics_event_count"] = 0
    if telemetry is not None:
        telemetry.trace(
            event="export_ics",
            context=log_context_from_state(state, graph_node="export_ics"),
            data={"path": state.get("ics_path"), "event_count": state.get("ics_event_count")},
        )
    return state
