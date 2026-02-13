from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from langgraph.graph import END, StateGraph
try:
    from langchain_ollama import ChatOllama
except Exception:  # pragma: no cover
    from langchain_community.chat_models import ChatOllama

from ai_travel_agent.agents.nodes import (
    context_controller,
    evaluate_final_node,
    evaluate_step,
    executor,
    export_ics,
    intent_parser,
    memory_writer,
    orchestrator,
    planner,
    responder,
)
from ai_travel_agent.agents.nodes.utils import instrument_node
from ai_travel_agent.agents.state import AgentState
from ai_travel_agent.config import Settings
from ai_travel_agent.llm import LLMClient
from ai_travel_agent.memory import MemoryStore
from ai_travel_agent.observability.metrics import MetricsCollector
from ai_travel_agent.tools import ToolRegistry
from ai_travel_agent.tools.distance_time import distance_and_time
from ai_travel_agent.tools.flights_links import flights_search_links
from ai_travel_agent.tools.hotels_links import hotels_search_links
from ai_travel_agent.tools.things_to_do_links import things_to_do_links
from ai_travel_agent.tools.weather import weather_summary


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
) -> Any:
    tools = build_tools()
    chat = ChatOllama(base_url=settings.ollama_base_url, model=settings.ollama_model, temperature=0.2)
    llm = LLMClient(runnable=chat, metrics=metrics, run_id=metrics.run_id, user_id=metrics.user_id)

    graph: StateGraph = StateGraph(AgentState)

    graph.add_node(
        "context_controller",
        instrument_node(
            node_name="context_controller",
            metrics=metrics,
            fn=lambda s: context_controller(s, memory=memory, metrics=metrics),
        ),
    )
    graph.add_node(
        "intent_parser",
        instrument_node(node_name="intent_parser", metrics=metrics, fn=lambda s: intent_parser(s, llm=llm)),
    )
    graph.add_node(
        "planner",
        instrument_node(node_name="planner", metrics=metrics, fn=planner),
    )
    graph.add_node(
        "orchestrator",
        instrument_node(
            node_name="orchestrator",
            metrics=metrics,
            fn=lambda s: orchestrator(s, max_iters=settings.max_graph_iters),
        ),
    )
    graph.add_node(
        "executor",
        instrument_node(
            node_name="executor", metrics=metrics, fn=lambda s: executor(s, tools=tools, llm=llm, metrics=metrics)
        ),
    )
    graph.add_node(
        "evaluate_step",
        instrument_node(node_name="evaluate_step", metrics=metrics, fn=evaluate_step),
    )
    graph.add_node(
        "responder",
        instrument_node(node_name="responder", metrics=metrics, fn=responder),
    )
    graph.add_node(
        "export_ics",
        instrument_node(node_name="export_ics", metrics=metrics, fn=lambda s: export_ics(s, runtime_dir=settings.runtime_dir)),
    )
    graph.add_node(
        "evaluate_final",
        instrument_node(
            node_name="evaluate_final",
            metrics=metrics,
            fn=lambda s: evaluate_final_node(s, eval_threshold=settings.eval_threshold),
        ),
    )
    graph.add_node(
        "memory_writer",
        instrument_node(node_name="memory_writer", metrics=metrics, fn=lambda s: memory_writer(s, memory=memory, metrics=metrics)),
    )

    graph.set_entry_point("context_controller")
    graph.add_edge("context_controller", "intent_parser")

    def _intent_route(state: dict[str, Any]) -> Literal["planner", "__end__"]:
        return "__end__" if state.get("needs_user_input") else "planner"

    graph.add_conditional_edges("intent_parser", _intent_route, {"planner": "planner", "__end__": END})
    graph.add_edge("planner", "orchestrator")

    def _orch_route(state: dict[str, Any]) -> Literal["executor", "responder"]:
        if state.get("termination_reason") in {"finalized", "max_iters"}:
            return "responder"
        return "executor"

    graph.add_conditional_edges("orchestrator", _orch_route, {"executor": "executor", "responder": "responder"})
    graph.add_edge("executor", "evaluate_step")
    graph.add_edge("evaluate_step", "orchestrator")

    graph.add_edge("responder", "export_ics")
    graph.add_edge("export_ics", "evaluate_final")
    graph.add_edge("evaluate_final", "memory_writer")
    graph.add_edge("memory_writer", END)

    app = graph.compile()
    return app
