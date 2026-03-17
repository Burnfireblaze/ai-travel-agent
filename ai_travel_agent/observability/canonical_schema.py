from __future__ import annotations

from typing import Any, Mapping
from uuid import uuid4


def _to_status(*, level: str, event: str) -> str:
    e = (event or "").lower()
    if level == "ERROR":
        return "failed"
    if "fallback" in e:
        return "skipped"
    if level == "WARNING":
        return "degraded"
    return "ok"


def _event_group(event: str) -> str:
    e = (event or "").lower()
    if e.startswith("tool_") or "tool" in e:
        return "tool"
    if e.startswith("llm_"):
        return "llm"
    if e.startswith("reasoning_") or "reasoning" in e:
        return "planning"
    if e.startswith("rag_") or "retriev" in e or "synth" in e:
        return "rag"
    if e.startswith("eval_"):
        return "eval"
    if "guardrail" in e or "fallback" in e or "validation" in e:
        return "guardrail"
    if "plan" in e or "step_selected" in e:
        return "planning"
    if "failure" in e or "node_error" in e:
        return "failure"
    return "workflow"


def _infer_span_type(event: str, node: str | None, step_type: str | None) -> str:
    e = (event or "").lower()
    n = (node or "").lower()
    st = (step_type or "").lower()
    if e.startswith("reasoning_") or st == "reasoning" or n == "reasoning_engine":
        return "reasoning_span"
    if e.startswith("llm_") or st == "llm_call" or n == "llm":
        return "llm_span"
    if e.startswith("eval_"):
        return "evaluation_span"
    if e.startswith("tool_") or st == "tool_call":
        return "tool_span"
    if e.startswith("rag_"):
        return "reasoning_span"
    if "plan" in e or n == "orchestrator":
        return "workflow_span"
    if st == "plan_draft":
        return "planning_span"
    if st:
        return "task_span"
    return "agent_span"


def _extract_step_index(step_id: str | None) -> int | None:
    if not step_id:
        return None
    if step_id.startswith("step-"):
        tail = step_id.split("step-", 1)[1]
        if tail.isdigit():
            return int(tail)
    return None


def _pick_value(data: Mapping[str, Any] | None, *keys: str) -> Any:
    if not data:
        return None
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _extract_error(data: Mapping[str, Any] | None) -> tuple[str | None, str | None]:
    if not data:
        return None, None
    return (
        (data.get("error_type") if isinstance(data.get("error_type"), str) else None),
        (data.get("error") or data.get("error_message") or data.get("runtime_error")),
    )


def _extract_eval(data: Mapping[str, Any] | None) -> dict[str, Any]:
    out = {
        "hard_gate_constraint_completeness": None,
        "hard_gate_no_fabricated_real_time_facts": None,
        "hard_gate_link_validity_format": None,
        "hard_gate_calendar_export_correctness": None,
        "hard_gate_safety_clarity_disclaimer": None,
        "rubric_relevance": None,
        "rubric_feasibility": None,
        "rubric_completeness": None,
        "rubric_specificity": None,
        "rubric_coherence": None,
        "hallucination_detected": None,
        "hallucination_ratio": None,
        "hallucination_rate": None,
    }
    if not data:
        return out
    hg = data.get("hard_gates")
    if isinstance(hg, Mapping):
        out["hard_gate_constraint_completeness"] = hg.get("constraint_completeness")
        out["hard_gate_no_fabricated_real_time_facts"] = hg.get("no_fabricated_real_time_facts")
        out["hard_gate_link_validity_format"] = hg.get("link_validity_format")
        out["hard_gate_calendar_export_correctness"] = hg.get("calendar_export_correctness")
        out["hard_gate_safety_clarity_disclaimer"] = hg.get("safety_clarity_disclaimer")
    rb = data.get("rubric")
    if isinstance(rb, Mapping):
        out["rubric_relevance"] = rb.get("relevance")
        out["rubric_feasibility"] = rb.get("feasibility")
        out["rubric_completeness"] = rb.get("completeness")
        out["rubric_specificity"] = rb.get("specificity")
        out["rubric_coherence"] = rb.get("coherence")
    out["hallucination_detected"] = data.get("hallucination_detected")
    out["hallucination_ratio"] = data.get("hallucination_ratio")
    out["hallucination_rate"] = data.get("hallucination_rate")
    return out


def build_canonical_record(
    *,
    ts: str,
    level: str,
    module: str,
    message: str,
    event: str,
    run_id: str | None,
    user_id: str | None,
    node: str | None,
    step_type: str | None,
    step_id: str | None,
    step_title: str | None,
    kind: str | None,
    data: Mapping[str, Any] | None,
) -> dict[str, Any]:
    span_type = _infer_span_type(event, node, step_type)
    error_type, error_message = _extract_error(data)
    eval_fields = _extract_eval(data)
    data_map = dict(data) if data else None
    if data_map is not None:
        # Remove redundant taxonomy/step markers from payload data.
        for key in (
            "step_type",
            "agentops_span_type",
            "agentops_trace_id",
            "agentops_span_id",
            "agentops_parent_id",
        ):
            data_map.pop(key, None)

    status = _to_status(level=level, event=event)
    step_index = _pick_value(data_map, "step_index")
    if step_index is None:
        step_index = _extract_step_index(step_id)
    tool_name = _pick_value(data_map, "tool_name")
    tool_attempt = _pick_value(data_map, "tool_attempt", "attempt")
    tool_latency_ms = _pick_value(data_map, "tool_latency_ms")
    if tool_latency_ms is None and tool_name is not None:
        tool_latency_ms = _pick_value(data_map, "latency_ms")
    iteration_count = _pick_value(data_map, "iteration_count", "loop_iterations")
    telemetry_event_index = _pick_value(data_map, "telemetry_event_index")
    telemetry_events_total = _pick_value(data_map, "telemetry_events_total")
    trace_id = _pick_value(data_map, "trace_id") or run_id
    span_id = _pick_value(data_map, "span_id") or f"{event}-{uuid4().hex[:12]}"
    parent_id = _pick_value(data_map, "parent_id") or step_id
    out: dict[str, Any] = {
        "ts": ts,
        "timestamp": ts,
        "run_id": run_id,
        "prompt_id": (data_map or {}).get("prompt_id") if data_map else None,
        "run_mode": (data_map or {}).get("run_mode") if data_map else None,
        "scenario": (data_map or {}).get("scenario") if data_map else None,
        "event": event,
        "event_group": _event_group(event),
        "level": level,
        "node": node,
        "node_name": (data_map or {}).get("node_name", node) if data_map else node,
        "span_type": span_type,
        "step_id": step_id,
        "step_index": step_index,
        "tool_name": tool_name,
        "tool_selected": (data_map or {}).get("tool_selected", tool_name) if data_map else None,
        "tool_attempt": tool_attempt,
        "tool_latency_ms": tool_latency_ms,
        "attempt": (data_map or {}).get("attempt") if data_map else None,
        "status": status,
        "overall_status": (data_map or {}).get("overall_status") if data_map else None,
        "termination_reason": (data_map or {}).get("termination_reason") if data_map else None,
        "latency_ms": (data_map or {}).get("latency_ms") if data_map else None,
        "iteration_count": iteration_count,
        "model_name": (data_map or {}).get("model_name", (data_map or {}).get("model") if data_map else None),
        "model": (data_map or {}).get("model", (data_map or {}).get("model_name") if data_map else None),
        "llm_input": (data_map or {}).get("llm_input") if data_map else None,
        "llm_output": (data_map or {}).get("llm_output") if data_map else None,
        "intent_decision": (data_map or {}).get("intent_decision") if data_map else None,
        "validation_decision": (data_map or {}).get("validation_decision") if data_map else None,
        "planner_decision": (data_map or {}).get("planner_decision") if data_map else None,
        "synthesis_decision": (data_map or {}).get("synthesis_decision") if data_map else None,
        "tokens_in": (data_map or {}).get("tokens_in") if data_map else None,
        "tokens_out": (data_map or {}).get("tokens_out") if data_map else None,
        "tokens_total": (data_map or {}).get("tokens_total") if data_map else None,
        "tokens_per_request": (data_map or {}).get("tokens_per_request") if data_map else None,
        "avg_tokens_per_request": (data_map or {}).get("avg_tokens_per_request") if data_map else None,
        "ttft_ms": (data_map or {}).get("ttft_ms") if data_map else None,
        "cost_usd": (data_map or {}).get("cost_usd") if data_map else None,
        "context_hits": (data_map or {}).get("context_hits", (data_map or {}).get("hits") if data_map else None),
        "tool_results_count": (
            len((data_map or {}).get("tool_results"))
            if data_map and isinstance((data_map or {}).get("tool_results"), list)
            else (data_map or {}).get("tool_results_count", (data_map or {}).get("tool_results") if data_map else None)
        ),
        "failure_count_run_so_far": (data_map or {}).get("failure_count") if data_map else None,
        "error_type": error_type,
        "error_message": error_message,
        "failure_category": (data_map or {}).get("category") if data_map else None,
        "failure_severity": (data_map or {}).get("severity") if data_map else None,
        "recovered": (data_map or {}).get("was_recovered") if data_map else None,
        "task_completed": (data_map or {}).get("task_completed") if data_map else None,
        "goal_completed": (data_map or {}).get("goal_completed") if data_map else None,
        "task_completion_rate": (data_map or {}).get("task_completion_rate") if data_map else None,
        "goal_completion_rate": (data_map or {}).get("goal_completion_rate") if data_map else None,
        "pii_detected": (data_map or {}).get("pii_detected") if data_map else None,
        "pii_leak_count": (data_map or {}).get("pii_leak_count") if data_map else None,
        "pii_types": (data_map or {}).get("pii_types") if data_map else None,
        "api_requests_total": (data_map or {}).get("api_requests_total") if data_map else None,
        "api_errors_total": (data_map or {}).get("api_errors_total") if data_map else None,
        "api_error_rate": (data_map or {}).get("api_error_rate") if data_map else None,
        "process_uptime_ms": (data_map or {}).get("process_uptime_ms") if data_map else None,
        "system_uptime_seconds": (data_map or {}).get("system_uptime_seconds") if data_map else None,
        "telemetry_event_index": telemetry_event_index,
        "telemetry_events_total": telemetry_events_total,
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_id": parent_id,
        "span_payload": {
            "module": module,
            "message": message,
            "step_title": step_title,
            "kind": kind,
            "user_id": user_id,
            "data": data_map if data_map else None,
        },
    }
    out.update(eval_fields)
    return out
