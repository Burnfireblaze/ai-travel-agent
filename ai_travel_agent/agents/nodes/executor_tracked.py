"""
Instrumented executor with detailed failure tracking and logging.
Demonstrates how to integrate failure tracking into actual nodes.
"""

import logging
import re
import time
import traceback
from typing import Any

from ai_travel_agent.agents.state import StepType, ToolResult
from ai_travel_agent.llm import LLMClient
from ai_travel_agent.observability.logger import get_logger, log_event
from ai_travel_agent.observability.metrics import MetricsCollector
from ai_travel_agent.observability.failure_tracker import (
    get_failure_tracker,
    FailureCategory,
    FailureSeverity,
)
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
Include this disclaimer line exactly once:
"Note: Visa/health requirements vary; verify with official sources (this is not legal advice)."
"""


def executor_with_tracking(
    state: dict[str, Any],
    *,
    tools: ToolRegistry,
    llm: LLMClient,
    metrics: MetricsCollector | None = None,
) -> dict[str, Any]:
    """
    Executor node with detailed failure tracking.
    Captures every failure with full context for observability.
    """
    failure_tracker = get_failure_tracker()
    step = state.get("current_step") or {}
    plan = state.get("plan") or []
    idx = state.get("current_step_index", 0)
    
    if not step:
        return state

    # ========================================================================
    # TOOL CALL EXECUTION
    # ========================================================================
    if step.get("step_type") == StepType.TOOL_CALL and step.get("tool_name"):
        tool_name = step["tool_name"]
        tool_args = step.get("tool_args") or {}
        
        started = time.perf_counter()
        
        try:
            if metrics is not None:
                metrics.inc("tool_calls", 1)
            
            # Execute tool
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
                data={"tool_name": tool_name, "latency_ms": round(elapsed_ms, 2)},
            )
            
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
        
        except Exception as e:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            error_type = type(e).__name__
            error_msg = str(e)
            
            if metrics is not None:
                metrics.inc("tool_errors", 1)
                metrics.observe_ms(f"tool_latency_ms.{tool_name}", elapsed_ms)
            
            # ================================================================
            # FAILURE TRACKING - TOOL FAILURE
            # ================================================================
            if failure_tracker:
                # Determine severity based on error type
                severity = FailureSeverity.MEDIUM
                if isinstance(e, TimeoutError):
                    severity = FailureSeverity.HIGH
                    category = FailureCategory.NETWORK
                elif isinstance(e, ConnectionError):
                    severity = FailureSeverity.HIGH
                    category = FailureCategory.NETWORK
                elif isinstance(e, KeyError):
                    severity = FailureSeverity.HIGH
                    category = FailureCategory.TOOL
                else:
                    category = FailureCategory.TOOL
                
                failure = failure_tracker.record_failure(
                    category=category,
                    severity=severity,
                    graph_node="executor",
                    error_type=error_type,
                    error_message=error_msg,
                    step_id=step.get("id"),
                    step_type=step.get("step_type"),
                    step_title=step.get("title"),
                    tool_name=tool_name,
                    latency_ms=elapsed_ms,
                    error_traceback=traceback.format_exc(),
                    context_data={
                        "tool_args": tool_args,
                        "user_query": state.get("user_query"),
                        "constraints": state.get("constraints"),
                    },
                    tags=["tool_execution", tool_name, error_type],
                )
                
                # Mark as recovered (step marked as blocked, but plan continues)
                failure_tracker.mark_recovered(
                    failure,
                    recovery_action="Step marked as blocked, orchestrator continues with other steps"
                )
            
            log_event(
                logger,
                level=logging.ERROR,
                message="Tool call failed",
                event="tool_error",
                context=log_context_from_state(state, graph_node="executor"),
                data={
                    "tool_name": tool_name,
                    "latency_ms": round(elapsed_ms, 2),
                    "error": error_msg,
                    "error_type": error_type,
                },
            )
            
            plan[idx]["status"] = "blocked"
        
        state["plan"] = plan
        return state

    # ========================================================================
    # SYNTHESIZE (LLM Call)
    # ========================================================================
    constraints = state.get("constraints") or {}
    tool_results = state.get("tool_results") or []
    context_hits = state.get("context_hits") or []
    prompt = (
        f"User query: {state.get('user_query','')}\n\n"
        f"Constraints: {constraints}\n\n"
        f"Context: {context_hits}\n\n"
        f"Tool results:\n"
    )
    for result in tool_results:
        prompt += f"- {result.get('tool_name')}: {result.get('summary')}\n"
    
    started = time.perf_counter()
    
    try:
        if metrics is not None:
            metrics.inc("llm_calls", 1)
        
        final_answer = llm.invoke_text(
            system=SYNTH_SYSTEM,
            user=prompt,
            context=log_context_from_state(state, graph_node="executor"),
            tags={"step_type": "SYNTHESIZE"},
        )
        
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if metrics is not None:
            metrics.observe_ms("llm_latency_ms", elapsed_ms)
        
        state["final_answer"] = final_answer
        plan[idx]["status"] = "done"
        
        log_event(
            logger,
            level=logging.INFO,
            message="Synthesis completed",
            event="synthesis_result",
            context=log_context_from_state(state, graph_node="executor"),
            data={"latency_ms": round(elapsed_ms, 2), "answer_length": len(final_answer)},
        )
    
    except Exception as e:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        error_type = type(e).__name__
        error_msg = str(e)
        
        if metrics is not None:
            metrics.inc("llm_errors", 1)
            metrics.observe_ms("llm_latency_ms", elapsed_ms)
        
        # ================================================================
        # FAILURE TRACKING - LLM FAILURE
        # ================================================================
        if failure_tracker:
            severity = FailureSeverity.CRITICAL  # Synthesis failure is critical
            
            if isinstance(e, TimeoutError):
                category = FailureCategory.NETWORK
            else:
                category = FailureCategory.LLM
            
            failure = failure_tracker.record_failure(
                category=category,
                severity=severity,
                graph_node="executor",
                error_type=error_type,
                error_message=error_msg,
                step_id=step.get("id"),
                step_type=step.get("step_type"),
                step_title=step.get("title"),
                llm_model=llm.llm_model if hasattr(llm, "llm_model") else "unknown",
                latency_ms=elapsed_ms,
                error_traceback=traceback.format_exc(),
                context_data={
                    "prompt_length": len(prompt),
                    "tool_results_count": len(tool_results),
                    "user_query": state.get("user_query"),
                },
                tags=["llm_synthesis", "critical", error_type],
            )
            
            # Attempt recovery: return empty answer or partial answer
            failure_tracker.mark_recovered(
                failure,
                recovery_action="Attempted synthesis recovery - may return empty answer"
            )
        
        log_event(
            logger,
            level=logging.ERROR,
            message="Synthesis failed",
            event="synthesis_error",
            context=log_context_from_state(state, graph_node="executor"),
            data={
                "latency_ms": round(elapsed_ms, 2),
                "error": error_msg,
                "error_type": error_type,
            },
        )
        
        state["final_answer"] = ""
        plan[idx]["status"] = "blocked"
    
    state["plan"] = plan
    return state
