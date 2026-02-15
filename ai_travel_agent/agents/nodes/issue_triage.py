from __future__ import annotations

from typing import Any

from ai_travel_agent.agents.state import Issue, IssueKind, IssueSeverity, StepType
from ai_travel_agent.llm import LLMClient


def _find_step_index(plan: list[dict[str, Any]], step_id: str | None) -> int | None:
    if not step_id:
        return None
    for i, s in enumerate(plan or []):
        if s.get("id") == step_id:
            return i
    return None


def issue_triage(state: dict[str, Any], *, llm: LLMClient) -> dict[str, Any]:
    state["current_step"] = {"step_type": StepType.EVALUATE_STEP, "title": "Issue triage: decide skip/ask/retry"}
    state.setdefault("issues", [])
    state.setdefault("validation_warnings", [])

    pending = state.get("pending_issue")
    if not isinstance(pending, dict):
        state["needs_triage"] = False
        return state

    try:
        issue = Issue.model_validate(pending)
    except Exception:
        issue = Issue(
            kind=IssueKind.TOOL_ERROR,
            severity=IssueSeverity.MAJOR,
            node="issue_triage",
            message=str(pending),
        )

    plan = state.get("plan") or []
    idx = _find_step_index(plan, issue.step_id)

    # Core-only clarification policy: never ask the user for tool failures.
    # We always skip the failed step and continue the run with best-effort output.
    if idx is not None and isinstance(plan[idx], dict):
        plan[idx]["status"] = "done"
        plan[idx]["notes"] = (plan[idx].get("notes") or "") + "\nSkipped due to tool failure."
        state["plan"] = plan

    state["needs_triage"] = False
    state["pending_issue"] = {}
    state["validation_warnings"].append(f"Skipped step due to issue ({issue.kind.value}): {issue.message}")
    return state
