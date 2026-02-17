from __future__ import annotations

import csv
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any
import random

from ai_travel_agent.config import load_settings, Settings
from ai_travel_agent.graph import build_app
from ai_travel_agent.memory import MemoryStore
from ai_travel_agent.observability.metrics import MetricsCollector
from ai_travel_agent.observability.telemetry import TelemetryController
from ai_travel_agent.observability.fault_injection import FaultInjector


def _read_experiment_prompts(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    prompts: list[str] = []
    in_section = False
    for line in lines:
        if line.strip().lower().startswith("## experiment queries"):
            in_section = True
            continue
        if in_section and line.strip().startswith("## "):
            break
        if in_section:
            if line.strip().startswith("- "):
                prompts.append(line.strip()[2:].strip())
    if prompts:
        return prompts
    # Fallback: take quoted examples
    for line in lines:
        if line.strip().startswith("> "):
            prompts.append(line.strip()[2:].strip())
    return prompts


def _fault_flags_for_index(i: int) -> dict[str, bool]:
    return {
        "simulate_tool_timeout": i % 3 == 0,
        "simulate_tool_error": i % 5 == 0,
        "simulate_bad_retrieval": i % 4 == 0,
        "simulate_llm_error": i % 7 == 0,
    }


def _run_single(
    prompt: str,
    *,
    settings: Settings,
    telemetry_mode: str,
    memory: MemoryStore,
    fault_flags: dict[str, bool],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    metrics = MetricsCollector(runtime_dir=settings.runtime_dir, run_id=run_id, user_id=settings.user_id)
    if any(fault_flags.values()):
        random.seed(settings.failure_seed)
    telemetry = TelemetryController(
        runtime_dir=settings.runtime_dir,
        run_id=run_id,
        user_id=settings.user_id,
        mode=telemetry_mode,
        max_chars=settings.trace_max_chars,
    )
    fault_injector = FaultInjector(
        simulate_tool_timeout=fault_flags.get("simulate_tool_timeout", False),
        simulate_tool_error=fault_flags.get("simulate_tool_error", False),
        simulate_bad_retrieval=fault_flags.get("simulate_bad_retrieval", False),
        simulate_llm_error=fault_flags.get("simulate_llm_error", False),
        failure_seed=settings.failure_seed,
        probability=settings.fault_probability,
        sleep_seconds=settings.fault_sleep_seconds,
        bad_retrieval_mode=settings.bad_retrieval_mode,
    )
    graph_app = build_app(
        settings=replace(settings, telemetry_mode=telemetry_mode),
        memory=memory,
        metrics=metrics,
        telemetry=telemetry,
        fault_injector=fault_injector,
    )
    state: dict[str, Any] = {
        "run_id": run_id,
        "user_id": settings.user_id,
        "user_query": prompt,
        "signals": {},
    }
    recursion_limit = max(200, settings.max_graph_iters * 10)
    try:
        state = graph_app.invoke(state, config={"recursion_limit": recursion_limit})
    except Exception as e:
        state.setdefault("signals", {})["node_error"] = True
        state["termination_reason"] = "error"
        state["error"] = str(e)

    metrics.set("signals", state.get("signals", {}))
    term = state.get("termination_reason")
    if term == "asked_user":
        run_status = "asked_user"
    elif term == "error":
        run_status = "error"
    elif state.get("final_answer") and term in {"finalized", "max_iters"}:
        run_status = "ok"
    else:
        run_status = "unknown"
    record = metrics.finalize_record(status=run_status, termination_reason=term)
    metrics_path = metrics.write(record)
    return {
        "run_id": run_id,
        "status": run_status,
        "termination_reason": term,
        "signals": state.get("signals", {}),
        "metrics_path": str(metrics_path),
        "metrics": record,
    }


def main() -> None:
    settings = load_settings()
    prompts_path = Path("docs/PROMPTS.md")
    prompts = _read_experiment_prompts(prompts_path)
    if not prompts:
        raise SystemExit("No prompts found in docs/PROMPTS.md")

    memory = MemoryStore(user_id=settings.user_id, persist_dir=settings.chroma_persist_dir, embedding_model=settings.embedding_model)

    runtime_dir = settings.runtime_dir
    logs_dir = (runtime_dir / "logs").resolve()
    metrics_dir = (runtime_dir / "metrics").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []

    for mode in ["minimal", "detailed", "selective"]:
        for i, prompt in enumerate(prompts):
            fault_flags = _fault_flags_for_index(i)
            before_app = (logs_dir / "app.jsonl").stat().st_size if (logs_dir / "app.jsonl").exists() else 0
            before_trace = (logs_dir / "trace.jsonl").stat().st_size if (logs_dir / "trace.jsonl").exists() else 0
            res = _run_single(prompt, settings=settings, telemetry_mode=mode, memory=memory, fault_flags=fault_flags)
            after_app = (logs_dir / "app.jsonl").stat().st_size if (logs_dir / "app.jsonl").exists() else 0
            after_trace = (logs_dir / "trace.jsonl").stat().st_size if (logs_dir / "trace.jsonl").exists() else 0
            log_bytes = max(0, after_app - before_app) + max(0, after_trace - before_trace)

            expected_failure = any(fault_flags.values())
            detected = bool(res.get("signals")) and any(bool(v) for v in (res.get("signals") or {}).values())

            results.append(
                {
                    "mode": mode,
                    "prompt": prompt[:80],
                    "run_id": res["run_id"],
                    "status": res["status"],
                    "termination_reason": res["termination_reason"],
                    "log_bytes": log_bytes,
                    "expected_failure": expected_failure,
                    "failure_detected": detected,
                    "total_latency_ms": res["metrics"].get("total_latency_ms"),
                }
            )

    out_dir = (runtime_dir / "experiments").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "results.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "mode",
                "prompt",
                "run_id",
                "status",
                "termination_reason",
                "log_bytes",
                "expected_failure",
                "failure_detected",
                "total_latency_ms",
            ],
        )
        writer.writeheader()
        writer.writerows(results)

    # Summary table
    summary: dict[str, dict[str, float]] = {}
    for r in results:
        mode = r["mode"]
        summary.setdefault(mode, {"lat_ms": 0.0, "log_bytes": 0.0, "count": 0.0, "detected": 0.0, "expected": 0.0})
        summary[mode]["lat_ms"] += float(r.get("total_latency_ms") or 0.0)
        summary[mode]["log_bytes"] += float(r.get("log_bytes") or 0.0)
        summary[mode]["count"] += 1.0
        if r.get("expected_failure"):
            summary[mode]["expected"] += 1.0
            if r.get("failure_detected"):
                summary[mode]["detected"] += 1.0

    lines = ["Mode,Avg Latency (ms),Avg Log Size (KB),Failures Detected (%)"]
    for mode, vals in summary.items():
        count = max(1.0, vals["count"])
        avg_lat = vals["lat_ms"] / count
        avg_log = vals["log_bytes"] / count / 1024.0
        expected = max(1.0, vals["expected"])
        detect_pct = (vals["detected"] / expected) * 100.0 if vals["expected"] > 0 else 0.0
        lines.append(f"{mode},{avg_lat:.1f},{avg_log:.1f},{detect_pct:.1f}")

    summary_path = out_dir / "summary.csv"
    summary_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {csv_path}")
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()
