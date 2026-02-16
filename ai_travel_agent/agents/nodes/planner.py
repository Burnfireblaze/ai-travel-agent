from __future__ import annotations

from typing import Any

from ai_travel_agent.agents.state import PlanStep, StepType


def planner(state: dict[str, Any]) -> dict[str, Any]:
    state["current_step"] = {"step_type": StepType.PLAN_DRAFT, "title": "Draft plan steps"}
    constraints = state.get("constraints") or {}
    dests = constraints.get("destinations") or []
    destination = dests[0] if dests else None
    origin = constraints.get("origin")
    start_date = constraints.get("start_date")
    end_date = constraints.get("end_date")
    interests = constraints.get("interests") or []
    travelers = constraints.get("travelers")

    steps: list[PlanStep] = []
    if destination:
        steps.append(
            PlanStep(
                title="Get flight search links",
                step_type=StepType.TOOL_CALL,
                tool_name="flights_search_links",
                tool_args={
                    "origin": origin,
                    "destination": destination,
                    "start_date": start_date,
                    "travelers": travelers,
                },
            )
        )
        steps.append(
            PlanStep(
                title="Get hotel search links",
                step_type=StepType.TOOL_CALL,
                tool_name="hotels_search_links",
                tool_args={
                    "destination": destination,
                    "start_date": start_date,
                    "end_date": end_date,
                    "travelers": travelers,
                },
            )
        )
        steps.append(
            PlanStep(
                title="Get things-to-do discovery links",
                step_type=StepType.TOOL_CALL,
                tool_name="things_to_do_links",
                tool_args={"destination": destination, "interests": interests},
            )
        )
        steps.append(
            PlanStep(
                title="Get weather summary",
                step_type=StepType.TOOL_CALL,
                tool_name="weather_summary",
                tool_args={"destination": destination, "start_date": start_date, "end_date": end_date},
            )
        )
    steps.append(PlanStep(title="Synthesize itinerary and recommendations", step_type=StepType.SYNTHESIZE))

    state["plan"] = [s.model_dump() for s in steps]
    state["tool_results"] = []
    state["current_step_index"] = 0
    return state
