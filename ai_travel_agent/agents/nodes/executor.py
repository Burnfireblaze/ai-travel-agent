from __future__ import annotations

import logging
import re
import time
from typing import Any

from ai_travel_agent.agents.state import Issue, IssueKind, IssueSeverity, StepType, ToolResult
from ai_travel_agent.llm import LLMClient
from ai_travel_agent.observability.logger import get_logger, log_event
from ai_travel_agent.observability.metrics import MetricsCollector
from ai_travel_agent.memory import MemoryStore
from ai_travel_agent.tools import ToolRegistry

from .utils import log_context_from_state


logger = get_logger(__name__)


SYNTH_SYSTEM = """You are a travel planner. Using the constraints and tool results, produce a structured plan:
- High-level summary
- Assumptions (explicitly list missing constraints)
- Flights (links-only)
- Lodging (links-only)
- Day-by-day itinerary
- Transit notes
- Weather
- Budget estimate (heuristic; do not claim live prices)
- Calendar export note
Style: be concise, use bullets, and avoid long paragraphs.
Include this disclaimer line exactly once:
"Note: Visa/health requirements vary; verify with official sources (this is not legal advice)."
"""


def executor(
    state: dict[str, Any],
    *,
    tools: ToolRegistry,
    llm: LLMClient,
    metrics: MetricsCollector | None = None,
    memory: MemoryStore | None = None,
    max_tool_retries: int = 1,
) -> dict[str, Any]:
    step = state.get("current_step") or {}
    plan = state.get("plan") or []
    idx = state.get("current_step_index", 0)
    if not step:
        return state

    if step.get("step_type") == StepType.RETRIEVE_CONTEXT:
        if memory is None:
            state.setdefault("issues", []).append(
                Issue(
                    kind=IssueKind.TOOL_ERROR,
                    severity=IssueSeverity.MAJOR,
                    node="executor",
                    step_id=step.get("id"),
                    message="Memory store not available for RETRIEVE_CONTEXT step.",
                ).model_dump()
            )
            plan[idx]["status"] = "blocked"
            state["plan"] = plan
            state["needs_triage"] = True
            state["pending_issue"] = state["issues"][-1]
            return state

        tool_args = step.get("tool_args") or {}
        query = ""
        if isinstance(tool_args, dict):
            query = str(tool_args.get("query") or state.get("user_query") or "")

        started = time.perf_counter()
        hits = memory.search(query=query, k=5, include_session=True, include_user=True)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if metrics is not None:
            metrics.inc("rag_retrievals", 1)
            metrics.observe_ms("rag_retrieval_latency_ms", elapsed_ms)
            metrics.set("memory_retrieval_hits", len(hits))
        log_event(
            logger,
            level=logging.INFO,
            message="RAG retrieval completed",
            event="rag_retrieve",
            context=log_context_from_state(state, graph_node="executor"),
            data={"latency_ms": round(elapsed_ms, 2), "hits": len(hits)},
        )
        state["context_hits"] = [
            {"id": h.id, "text": h.text, "metadata": dict(h.metadata), "distance": h.distance} for h in hits
        ]
        plan[idx]["status"] = "done"
        state["plan"] = plan
        return state

    if step.get("step_type") == StepType.TOOL_CALL and step.get("tool_name"):
        tool_name = step["tool_name"]
        tool_args = step.get("tool_args") or {}

        attempts = 0
        last_err: Exception | None = None
        out: Any | None = None

        while attempts <= max_tool_retries:
            attempts += 1
            started = time.perf_counter()
            try:
                if metrics is not None:
                    metrics.inc("tool_calls", 1)
                out = tools.call(tool_name, **tool_args)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                if metrics is not None:
                    metrics.observe_ms(f"tool_latency_ms.{tool_name}", elapsed_ms)
                log_event(
                    logger,
                    level=logging.INFO,
                    message="Tool call completed",
                    event="tool_result",
                    context=log_context_from_state(state, graph_node="executor"),
                    data={"tool_name": tool_name, "latency_ms": round(elapsed_ms, 2), "attempt": attempts},
                )
                last_err = None
                break
            except Exception as e:
                last_err = e
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                if metrics is not None:
                    metrics.inc("tool_errors", 1)
                    metrics.observe_ms(f"tool_latency_ms.{tool_name}", elapsed_ms)
                    if attempts <= max_tool_retries:
                        metrics.inc("tool_retries", 1)
                log_event(
                    logger,
                    level=logging.WARNING if attempts <= max_tool_retries else logging.ERROR,
                    message="Tool call failed",
                    event="tool_error",
                    context=log_context_from_state(state, graph_node="executor"),
                    data={
                        "tool_name": tool_name,
                        "latency_ms": round(elapsed_ms, 2),
                        "error": str(e),
                        "attempt": attempts,
                        "will_retry": attempts <= max_tool_retries,
                    },
                )
                continue

        if last_err is None and out is not None:
            state.setdefault("tool_results", []).append(
                ToolResult(
                    step_id=step["id"],
                    tool_name=tool_name,
                    data=dict(out),
                    summary=str(out.get("summary", "")),
                    links=list(out.get("links", [])) if isinstance(out.get("links"), list) else [],
                ).model_dump()
            )
            plan[idx]["status"] = "done"
            state["plan"] = plan
            return state

        # After retries, raise to issue triage.
        severity = IssueSeverity.MINOR
        if tool_name in {"flights_search_links", "hotels_search_links"}:
            severity = IssueSeverity.MAJOR

        issue = Issue(
            kind=IssueKind.TOOL_ERROR,
            severity=severity,
            node="executor",
            step_id=step.get("id"),
            tool_name=tool_name,
            message=f"Tool '{tool_name}' failed after {attempts} attempt(s): {last_err}",
            suggested_actions=["retry", "skip", "modify_inputs"],
            details={"tool_args": dict(tool_args), "attempts": attempts},
        )
        state.setdefault("issues", []).append(issue.model_dump())
        state["pending_issue"] = issue.model_dump()
        state["needs_triage"] = True
        plan[idx]["status"] = "blocked"
        state["plan"] = plan
        return state

    # synthesize
    constraints = state.get("constraints") or {}
    tool_results = state.get("tool_results") or []
    context_hits = state.get("context_hits") or []

    def compact_tool_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compact: list[dict[str, Any]] = []
        for r in results[:12]:
            if not isinstance(r, dict):
                continue
            compact.append(
                {
                    "tool_name": r.get("tool_name"),
                    "summary": r.get("summary"),
                    "links": (r.get("links") or [])[:5] if isinstance(r.get("links"), list) else [],
                }
            )
        return compact

    def compact_context(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for h in hits[:5]:
            if not isinstance(h, dict):
                continue
            text = (h.get("text") or "")
            if isinstance(text, str) and len(text) > 300:
                text = text[:300] + "…"
            out.append({"text": text, "metadata": h.get("metadata")})
        return out

    prompt = (
        f"User query: {state.get('user_query','')}\n\n"
        f"Constraints (JSON): {constraints}\n\n"
        f"Context hits (compact): {compact_context(context_hits)}\n\n"
        f"Tool results (compact): {compact_tool_results(tool_results)}\n\n"
        "Write the final response in Markdown with the required sections."
    )
    answer = llm.invoke_text(system=SYNTH_SYSTEM, user=prompt, tags={"node": "executor", "kind": "synthesize"})
    state["final_answer"] = answer
    # Best-effort extract day titles for ICS.
    day_titles: list[str] = []
    for m in re.finditer(r"^#+\s*Day\s*(\d+)\s*[:\-]?\s*(.*)$", answer, flags=re.IGNORECASE | re.MULTILINE):
        title = (m.group(2) or "").strip()
        day_titles.append(title or f"Day {m.group(1)}")
    state["itinerary_day_titles"] = day_titles[:21]
    plan[idx]["status"] = "done"
    state["plan"] = plan
    return state
