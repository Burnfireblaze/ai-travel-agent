from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from ai_travel_agent.agents.nodes import (
    brain_planner,
    context_controller,
    evaluate_final_node,
    evaluate_step,
    executor,
    export_ics,
    intent_parser,
    issue_triage,
    memory_writer,
    orchestrator,
    planner,
    responder,
    validator,
)
from ai_travel_agent.agents.nodes.utils import instrument_node
from ai_travel_agent.agents.state import AgentState
from ai_travel_agent.config import Settings
from ai_travel_agent.llm import LLMClient, build_chat_model
from ai_travel_agent.memory import MemoryStore
from ai_travel_agent.observability.metrics import MetricsCollector
from ai_travel_agent.observability.telemetry import TelemetryController
from ai_travel_agent.observability.fault_injection import FaultInjector
from ai_travel_agent.tools import ToolRegistry
from ai_travel_agent.tools.distance_time import distance_and_time
from ai_travel_agent.tools.flights_links import flights_search_links
from ai_travel_agent.tools.hotels_links import hotels_search_links
from ai_travel_agent.tools.things_to_do_links import things_to_do_links
from ai_travel_agent.tools.weather import weather_summary
from ai_travel_agent.tools.geocoding import geocode_place


def build_tools() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register("flights_search_links", flights_search_links)
    reg.register("hotels_search_links", hotels_search_links)
    reg.register("things_to_do_links", things_to_do_links)
    reg.register("distance_and_time", distance_and_time)
    reg.register("weather_summary", weather_summary)
    return reg


def build_app(
    *,
    settings: Settings,
    memory: MemoryStore,
    metrics: MetricsCollector,
    telemetry: TelemetryController | None = None,
    fault_injector: FaultInjector | None = None,
) -> Any:
    tools = build_tools()
    # Use a single model (provider-configured) for all stages for predictability.
    chat_intent = build_chat_model(settings=settings, json_mode=True, temperature=0.0)
    chat_planner = build_chat_model(settings=settings, json_mode=True, temperature=0.0)
    chat_triage = build_chat_model(settings=settings, json_mode=True, temperature=0.0)
    chat_synth = build_chat_model(settings=settings, json_mode=False, temperature=0.2)

    llm_intent = LLMClient(
        runnable=chat_intent,
        metrics=metrics,
        run_id=metrics.run_id,
        user_id=metrics.user_id,
        telemetry=telemetry,
        fault_injector=fault_injector,
        name="intent",
    )
    llm_planner = LLMClient(
        runnable=chat_planner,
        metrics=metrics,
        run_id=metrics.run_id,
        user_id=metrics.user_id,
        telemetry=telemetry,
        fault_injector=fault_injector,
        name="planner",
    )
    llm_triage = LLMClient(
        runnable=chat_triage,
        metrics=metrics,
        run_id=metrics.run_id,
        user_id=metrics.user_id,
        telemetry=telemetry,
        fault_injector=fault_injector,
        name="triage",
    )
    llm_synth = LLMClient(
        runnable=chat_synth,
        metrics=metrics,
        run_id=metrics.run_id,
        user_id=metrics.user_id,
        telemetry=telemetry,
        fault_injector=fault_injector,
        name="synth",
    )

    graph: StateGraph = StateGraph(AgentState)

    graph.add_node(
        "context_controller",
        instrument_node(
            node_name="context_controller",
            metrics=metrics,
            fn=lambda s: context_controller(s, memory=memory, metrics=metrics, telemetry=telemetry, fault_injector=fault_injector),
        ),
    )
    graph.add_node(
        "intent_parser",
        instrument_node(node_name="intent_parser", metrics=metrics, fn=lambda s: intent_parser(s, llm=llm_intent, telemetry=telemetry)),
    )
    graph.add_node(
        "validator",
        instrument_node(
            node_name="validator",
            metrics=metrics,
            fn=lambda s: validator(s, geocode_fn=geocode_place, telemetry=telemetry),
        ),
    )
    graph.add_node(
        "brain_planner",
        instrument_node(node_name="brain_planner", metrics=metrics, fn=lambda s: brain_planner(s, llm=llm_planner, telemetry=telemetry)),
    )
    graph.add_node(
        "orchestrator",
        instrument_node(
            node_name="orchestrator",
            metrics=metrics,
            fn=lambda s: orchestrator(s, max_iters=settings.max_graph_iters, telemetry=telemetry),
        ),
    )
    graph.add_node(
        "executor",
        instrument_node(
            node_name="executor",
            metrics=metrics,
            fn=lambda s: executor(
                s,
                tools=tools,
                llm=llm_synth,
                metrics=metrics,
                memory=memory,
                max_tool_retries=settings.max_tool_retries,
                telemetry=telemetry,
                fault_injector=fault_injector,
            ),
        ),
    )
    graph.add_node(
        "issue_triage",
        instrument_node(node_name="issue_triage", metrics=metrics, fn=lambda s: issue_triage(s, llm=llm_triage, telemetry=telemetry)),
    )
    graph.add_node(
        "evaluate_step",
        instrument_node(node_name="evaluate_step", metrics=metrics, fn=lambda s: evaluate_step(s, telemetry=telemetry)),
    )
    graph.add_node(
        "responder",
        instrument_node(node_name="responder", metrics=metrics, fn=lambda s: responder(s, telemetry=telemetry)),
    )
    graph.add_node(
        "export_ics",
        instrument_node(
            node_name="export_ics",
            metrics=metrics,
            fn=lambda s: export_ics(s, runtime_dir=settings.runtime_dir, telemetry=telemetry),
        ),
    )
    graph.add_node(
        "evaluate_final",
        instrument_node(
            node_name="evaluate_final",
            metrics=metrics,
            fn=lambda s: evaluate_final_node(s, eval_threshold=settings.eval_threshold, telemetry=telemetry),
        ),
    )
    graph.add_node(
        "memory_writer",
        instrument_node(node_name="memory_writer", metrics=metrics, fn=lambda s: memory_writer(s, memory=memory, metrics=metrics)),
    )

    graph.set_entry_point("context_controller")
    graph.add_edge("context_controller", "intent_parser")

    def _intent_route(state: dict[str, Any]) -> Literal["validator", "__end__"]:
        return "__end__" if state.get("needs_user_input") else "validator"

    graph.add_conditional_edges("intent_parser", _intent_route, {"validator": "validator", "__end__": END})

    def _validator_route(state: dict[str, Any]) -> Literal["brain_planner", "__end__"]:
        return "__end__" if state.get("needs_user_input") else "brain_planner"

    graph.add_conditional_edges("validator", _validator_route, {"brain_planner": "brain_planner", "__end__": END})
    graph.add_edge("brain_planner", "orchestrator")

    def _orch_route(state: dict[str, Any]) -> Literal["executor", "responder"]:
        if state.get("termination_reason") in {"finalized", "max_iters"}:
            return "responder"
        return "executor"

    graph.add_conditional_edges("orchestrator", _orch_route, {"executor": "executor", "responder": "responder"})

    def _exec_route(state: dict[str, Any]) -> Literal["issue_triage", "evaluate_step"]:
        return "issue_triage" if state.get("needs_triage") else "evaluate_step"

    graph.add_conditional_edges("executor", _exec_route, {"issue_triage": "issue_triage", "evaluate_step": "evaluate_step"})
    graph.add_edge("evaluate_step", "orchestrator")

    def _triage_route(state: dict[str, Any]) -> Literal["orchestrator", "__end__"]:
        return "__end__" if state.get("needs_user_input") else "orchestrator"

    graph.add_conditional_edges("issue_triage", _triage_route, {"orchestrator": "orchestrator", "__end__": END})

    graph.add_edge("responder", "export_ics")
    graph.add_edge("export_ics", "evaluate_final")
    graph.add_edge("evaluate_final", "memory_writer")
    graph.add_edge("memory_writer", END)

    app = graph.compile()
    return app
