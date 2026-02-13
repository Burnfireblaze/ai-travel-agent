from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any, Literal, NotRequired, TypedDict

from pydantic import BaseModel, Field


class StepType(StrEnum):
    ASK_USER = "ASK_USER"
    INTENT_PARSE = "INTENT_PARSE"
    RETRIEVE_CONTEXT = "RETRIEVE_CONTEXT"
    PLAN_DRAFT = "PLAN_DRAFT"
    PLAN_REFINE = "PLAN_REFINE"
    TOOL_CALL = "TOOL_CALL"
    SYNTHESIZE = "SYNTHESIZE"
    EVALUATE_STEP = "EVALUATE_STEP"
    EVALUATE_FINAL = "EVALUATE_FINAL"
    RESPOND = "RESPOND"
    WRITE_MEMORY = "WRITE_MEMORY"
    EXPORT_ICS = "EXPORT_ICS"


class TripConstraints(BaseModel):
    origin: str | None = None
    destinations: list[str] = Field(default_factory=list)
    start_date: str | None = None  # ISO date YYYY-MM-DD
    end_date: str | None = None
    budget_usd: float | None = None
    travelers: int | None = None
    interests: list[str] = Field(default_factory=list)
    pace: Literal["relaxed", "balanced", "packed"] | None = None
    notes: list[str] = Field(default_factory=list)


class PlanStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    step_type: StepType
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    status: Literal["pending", "done", "blocked"] = "pending"
    notes: str | None = None


class ToolResult(BaseModel):
    step_id: str
    tool_name: str
    data: dict[str, Any]
    summary: str
    links: list[dict[str, str]] = Field(default_factory=list)


class EvaluationResult(BaseModel):
    hard_gates: dict[str, bool]
    rubric_scores: dict[str, float]
    overall_status: Literal["good", "needs_work", "failed"]
    notes: list[str] = Field(default_factory=list)


class AgentState(TypedDict, total=False):
    run_id: str
    user_id: str

    messages: list[dict[str, str]]
    user_query: str
    constraints: dict[str, Any]
    context_hits: list[dict[str, Any]]
    plan: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]

    current_node: str
    current_step: dict[str, Any]
    current_step_index: int

    needs_user_input: bool
    clarifying_questions: list[str]

    final_answer: str
    itinerary_day_titles: list[str]
    ics_path: str
    ics_event_count: int

    loop_iterations: int

    evaluation: dict[str, Any]
    termination_reason: str
    error: str
