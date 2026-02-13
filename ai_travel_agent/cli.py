from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from datetime import date
import re

from ai_travel_agent.config import load_settings
from ai_travel_agent.graph import build_app
from ai_travel_agent.agents.state import StepType
from ai_travel_agent.memory import MemoryStore
from ai_travel_agent.observability.logger import LogContext, get_logger, log_event, setup_logging
from ai_travel_agent.observability.metrics import MetricsCollector


app = typer.Typer(add_completion=False)
console = Console()
logger = get_logger(__name__)


def _render_status(state: dict[str, Any]) -> Panel:
    node = state.get("current_node") or "-"
    plan = state.get("plan") or []
    idx = state.get("current_step_index")
    step = state.get("current_step") or {}
    step_type = step.get("step_type") or "-"
    title = step.get("title") or ""
    progress = "-"
    if isinstance(idx, int) and plan:
        progress = f"{min(idx + 1, len(plan))}/{len(plan)}"
    text = f"Node: {node}\nStep: {step_type} | {progress}\n{title}"
    return Panel(text, title="AI Travel Agent", expand=False)


def _metrics_table(record: dict[str, Any]) -> Table:
    t = Table(title="Run summary", show_header=False)
    t.add_row("status", str(record.get("status")))
    t.add_row("termination_reason", str(record.get("termination_reason")))
    t.add_row("total_latency_ms", str(record.get("total_latency_ms")))
    counters = record.get("counters", {})
    t.add_row("llm_calls", str(counters.get("llm_calls", 0)))
    t.add_row("tool_calls", str(counters.get("tool_calls", 0)))
    t.add_row("memory_hits", str(record.get("memory_retrieval_hits", 0)))
    t.add_row("ics_path", str(record.get("ics_path", "")))
    t.add_row("eval_status", str(record.get("eval_overall_status", "")))
    return t


def _stream_or_invoke(app_graph, state: dict[str, Any], *, recursion_limit: int, live: Live | None = None) -> dict[str, Any]:
    latest: dict[str, Any] = dict(state)

    node_step_defaults: dict[str, dict[str, Any]] = {
        "context_controller": {"step_type": StepType.RETRIEVE_CONTEXT, "title": "Retrieve memory context"},
        "intent_parser": {"step_type": StepType.INTENT_PARSE, "title": "Parse intent and constraints"},
        "planner": {"step_type": StepType.PLAN_DRAFT, "title": "Draft plan steps"},
        "evaluate_step": {"step_type": StepType.EVALUATE_STEP, "title": "Evaluate step"},
        "responder": {"step_type": StepType.RESPOND, "title": "Format final response"},
        "export_ics": {"step_type": StepType.EXPORT_ICS, "title": "Export itinerary calendar (.ics)"},
        "evaluate_final": {"step_type": StepType.EVALUATE_FINAL, "title": "Evaluate final response"},
        "memory_writer": {"step_type": StepType.WRITE_MEMORY, "title": "Write memory summaries"},
    }

    def unwrap_result(result: Any) -> Any:
        if isinstance(result, dict) and "__root__" in result and isinstance(result["__root__"], dict):
            return result["__root__"]
        return result

    # Use debug stream so we can show node/step as soon as it starts (before long LLM/tool calls finish).
    try:
        for ev in app_graph.stream(state, config={"recursion_limit": recursion_limit}, stream_mode="debug"):
            if not isinstance(ev, dict):
                continue
            ev_type = ev.get("type")
            payload = ev.get("payload") or {}

            if ev_type == "task":
                node_name = payload.get("name")
                inp = payload.get("input") or {}
                display = dict(latest)
                if node_name:
                    display["current_node"] = node_name
                    display.setdefault("current_step", node_step_defaults.get(node_name, {}))
                if isinstance(inp, dict):
                    # Show the most recent known step context while the node is running.
                    for k in ("plan", "current_step", "current_step_index"):
                        if k in inp:
                            display[k] = inp.get(k)
                latest = display
                if live is not None:
                    live.update(_render_status(latest))
            elif ev_type == "task_result":
                result = unwrap_result(payload.get("result"))
                if isinstance(result, dict):
                    latest = result
                    if live is not None:
                        live.update(_render_status(latest))
            elif ev_type == "task_error":
                # Keep latest; error will likely propagate
                pass
    except TypeError:
        latest = app_graph.invoke(state, config={"recursion_limit": recursion_limit})
        if live is not None:
            live.update(_render_status(latest))

    return latest


@app.command()
def chat(
    log_level: str = typer.Option(None, "--log-level", help="INFO or DEBUG"),
    runtime_dir: Path = typer.Option(None, "--runtime-dir", help="Runtime folder for logs/metrics/artifacts"),
    verbose: bool = typer.Option(False, "--verbose", help="Print more node/step information to the console"),
):
    settings = load_settings()
    if log_level:
        settings = replace(settings, log_level=log_level)
    if runtime_dir:
        settings = replace(settings, runtime_dir=runtime_dir)

    setup_logging(runtime_dir=settings.runtime_dir, level=settings.log_level)

    memory = MemoryStore(user_id=settings.user_id, persist_dir=settings.chroma_persist_dir, embedding_model=settings.embedding_model)

    console.print("Enter your travel request (or 'quit'):")
    messages: list[dict[str, str]] = []

    while True:
        user_query = console.input("> ").strip()
        if not user_query:
            continue
        if user_query.lower() in {"quit", "exit"}:
            break

        run_id = str(uuid.uuid4())
        metrics = MetricsCollector(runtime_dir=settings.runtime_dir, run_id=run_id, user_id=settings.user_id)
        graph_app = build_app(settings=settings, memory=memory, metrics=metrics)

        log_event(
            logger,
            level=logging.INFO,
            message="Run started",
            event="run_start",
            context=LogContext(run_id=run_id, user_id=settings.user_id),
            data={"ollama_model": settings.ollama_model},
        )

        state: dict[str, Any] = {
            "run_id": run_id,
            "user_id": settings.user_id,
            "messages": messages,
            "user_query": user_query,
        }

        # LangGraph recursion_limit counts node transitions, not “plan steps”.
        # Keep this comfortably above the maximum expected transitions.
        recursion_limit = max(200, settings.max_graph_iters * 10)

        with Live(_render_status(state), refresh_per_second=8, console=console) as live:
            while True:
                latest = _stream_or_invoke(graph_app, state, recursion_limit=recursion_limit, live=live)
                state = latest

                if state.get("needs_user_input"):
                    qs = state.get("clarifying_questions") or []
                    console.print("\nI need a few details:")
                    answers: list[str] = []
                    for q in qs:
                        a = console.input(f"- {q} ").strip()
                        if a:
                            answers.append(f"{q} {a}")
                    if not answers:
                        console.print("No answers provided; stopping.")
                        break
                    state["user_query"] = user_query + "\n\nAdditional details:\n" + "\n".join(answers)
                    state["needs_user_input"] = False
                    state["clarifying_questions"] = []
                    continue

                break

        final_answer = state.get("final_answer", "").strip()
        if final_answer:
            console.print("\n" + final_answer)

        messages.append({"role": "user", "content": user_query})
        if final_answer:
            messages.append({"role": "assistant", "content": final_answer})

        evaluation = state.get("evaluation") or {}
        counters = metrics.counters
        link_count = len(re.findall(r"https?://[^\s)>\"]+", final_answer)) if final_answer else 0
        metrics.set("output_link_count", link_count)
        constraints = state.get("constraints") or {}
        if constraints.get("start_date") and constraints.get("end_date"):
            try:
                ds = date.fromisoformat(constraints["start_date"])
                de = date.fromisoformat(constraints["end_date"])
                metrics.set("output_itinerary_days", abs((de - ds).days) + 1)
            except Exception:
                pass
        metrics.set("ics_path", state.get("ics_path", ""))
        metrics.set("ics_event_count", state.get("ics_event_count"))
        metrics.set("eval_overall_status", evaluation.get("overall_status"))
        metrics.set("eval_hard_gates", evaluation.get("hard_gates"))
        metrics.set("eval_rubric_scores", evaluation.get("rubric_scores"))

        record = metrics.finalize_record(
            status=evaluation.get("overall_status") or "unknown",
            termination_reason=state.get("termination_reason"),
        )
        metrics_path = metrics.write(record)

        console.print()
        console.print(_metrics_table(record))
        console.print(f"Metrics appended to: {metrics_path}")
        if state.get("ics_path"):
            console.print(f"Calendar exported: {state['ics_path']}")

        if verbose:
            console.print(f"Graph node transitions: {counters.get('graph_node_transitions', 0)}")

        log_event(
            logger,
            level=logging.INFO,
            message="Run ended",
            event="run_end",
            context=LogContext(run_id=run_id, user_id=settings.user_id),
        )


if __name__ == "__main__":
    app()
