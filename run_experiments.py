"""
Experiment runner for telemetry mode comparison and metrics collection.
"""
import time
import csv
from pathlib import Path
from ai_travel_agent.config import load_settings
from ai_travel_agent.llm import build_chat_model, LLMClient
from ai_travel_agent.observability.logger import TELEMETRY
from ai_travel_agent.agents.nodes.intent_parser import intent_parser
from ai_travel_agent.agents.nodes.executor import executor
from ai_travel_agent.agents.nodes.orchestrator import orchestrator
from ai_travel_agent.tools import ToolRegistry
from ai_travel_agent.observability.metrics import MetricsCollector

TEST_QUERIES = [
    "Plan a trip to Paris for 2 people, $3000 budget, 2026-03-01 to 2026-03-10.",
    "I want to visit Rome and Florence, 1 week, art museums, moderate pace.",
    "Find me a beach vacation in July, 4 travelers, $5000.",
    "Show me a trip to Tokyo with food tours and anime spots.",
]

MODES = ["MINIMAL", "DETAILED", "SELECTIVE"]

RESULTS = []


def run_experiment(mode: str, simulate_tool_timeout=False, simulate_bad_retrieval=False):
    settings = load_settings()
    # Patch config for fault injection
    settings = settings.__class__(**{**settings.__dict__,
        "simulate_tool_timeout": simulate_tool_timeout,
        "simulate_bad_retrieval": simulate_bad_retrieval,
    })
    TELEMETRY.set_mode(mode)
    metrics = MetricsCollector()
    model = build_chat_model(settings=settings, json_mode=False, temperature=0.1)
    llm = LLMClient(runnable=model, metrics=metrics, run_id="exp", user_id="exp-user")
    tools = ToolRegistry()
    for query in TEST_QUERIES:
        state = {"user_query": query, "signals": {}}
        t0 = time.perf_counter()
        try:
            state = intent_parser(state, llm=llm)
            state = orchestrator(state, max_iters=5)
            state = executor(state, tools=tools, llm=llm, metrics=metrics)
            success = not state.get("needs_user_input", False)
        except Exception:
            success = False
        t1 = time.perf_counter()
        log_size = Path("runtime/logs/app.jsonl").stat().st_size if Path("runtime/logs/app.jsonl").exists() else 0
        RESULTS.append({
            "mode": mode,
            "query": query,
            "latency_ms": int((t1-t0)*1000),
            "log_size": log_size,
            "success": success,
        })


def main():
    # Minimal logging, no failures
    run_experiment("MINIMAL", simulate_tool_timeout=False, simulate_bad_retrieval=False)
    # Detailed logging, no failures
    run_experiment("DETAILED", simulate_tool_timeout=False, simulate_bad_retrieval=False)
    # Selective logging, with failures injected
    run_experiment("SELECTIVE", simulate_tool_timeout=True, simulate_bad_retrieval=True)
    # Write results
    with open("runtime/experiment_results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["mode", "query", "latency_ms", "log_size", "success"])
        writer.writeheader()
        for row in RESULTS:
            writer.writerow(row)
    print("Experiment complete. Results saved to runtime/experiment_results.csv")

if __name__ == "__main__":
    main()
