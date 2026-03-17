#!/usr/bin/env python3
"""
Signal ablation analysis for failure prediction.

Signals:
  - latency_high (total_latency >= percentile threshold)
  - iteration_high (iteration_count >= percentile threshold)
  - hard_gate_violation (any hard_gate_* == False)

Outputs:
  - ablation_signals.csv (per-signal sufficiency/necessity metrics)
  - ablation_summary.json (thresholds + high-level stats)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


HARD_GATE_FIELDS = [
    "hard_gate_constraint_completeness",
    "hard_gate_no_fabricated_real_time_facts",
    "hard_gate_link_validity_format",
    "hard_gate_calendar_export_correctness",
    "hard_gate_safety_clarity_disclaimer",
]


def load_jsonl(path: Path) -> pd.DataFrame:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return pd.DataFrame(rows)


def _ensure_columns(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    for col in cols:
        if col not in df.columns:
            df[col] = np.nan
    return df


def build_run_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = _ensure_columns(
        df,
        [
            "run_id",
            "ts",
            "event",
            "event_group",
            "status",
            "failure_category",
            "level",
            "latency_ms",
            "step_index",
            "overall_status",
        ]
        + HARD_GATE_FIELDS,
    )
    df = df[df["run_id"].notna()].copy()
    if df.empty:
        return pd.DataFrame()

    df["latency_ms"] = pd.to_numeric(df["latency_ms"], errors="coerce")
    df["step_index"] = pd.to_numeric(df["step_index"], errors="coerce")
    df["ts_parsed"] = pd.to_datetime(df["ts"], errors="coerce")

    total_latency = df.groupby("run_id")["latency_ms"].sum(min_count=1).rename("total_latency")

    # Iteration count: count step_selected if present, else max step_index + 1.
    step_selected = df["event"].astype(str).eq("step_selected").groupby(df["run_id"]).sum()
    max_step_index = df.groupby("run_id")["step_index"].max(min_count=1)
    iteration_count = step_selected.where(step_selected > 0, max_step_index.fillna(-1) + 1)
    iteration_count = iteration_count.fillna(0).rename("iteration_count")

    # Hard-gate violation: any hard_gate_* == False.
    hard_gate_violation = None
    for field in HARD_GATE_FIELDS:
        series = df[field].eq(False).groupby(df["run_id"]).any()
        hard_gate_violation = series if hard_gate_violation is None else (hard_gate_violation | series)
    hard_gate_violation = hard_gate_violation.rename("hard_gate_violation")

    # Failure definition.
    status_failed = df["status"].eq("failed").groupby(df["run_id"]).any()
    failure_category_present = df["failure_category"].notna().groupby(df["run_id"]).any()
    df_sorted = df.sort_values(["run_id", "ts_parsed"], kind="stable")
    last_status = (
        df_sorted.groupby("run_id")["overall_status"]
        .apply(lambda s: s.dropna().iloc[-1] if not s.dropna().empty else np.nan)
    )
    goal_completed = last_status.eq("good")
    failure = (status_failed | failure_category_present | ~goal_completed.fillna(False)).rename("failure")

    run_df = pd.concat([total_latency, iteration_count, hard_gate_violation, failure], axis=1).reset_index()
    return run_df


def _metric_frame(run_df: pd.DataFrame, signals: dict[str, pd.Series]) -> pd.DataFrame:
    total_failures = run_df["failure"].sum()
    total_runs = len(run_df)

    rows = []
    for name, signal in signals.items():
        signal = signal.fillna(False)
        support = int(signal.sum())
        failures_with = int((signal & run_df["failure"]).sum())
        failures_without = int((~signal & run_df["failure"]).sum())
        successes_with = int((signal & ~run_df["failure"]).sum())
        successes_without = int((~signal & ~run_df["failure"]).sum())

        precision = failures_with / support if support else 0.0  # sufficiency
        recall = failures_with / total_failures if total_failures else 0.0  # necessity
        fail_rate_without = failures_without / max((total_runs - support), 1)

        rows.append(
            {
                "signal": name,
                "support": support,
                "failures_with_signal": failures_with,
                "successes_with_signal": successes_with,
                "precision_sufficiency": round(precision, 4),
                "recall_necessity": round(recall, 4),
                "failure_rate_without_signal": round(fail_rate_without, 4),
            }
        )

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ablate signals for failure prediction.")
    parser.add_argument("--input", type=Path, required=True, help="Path to app.jsonl or mixed log JSONL")
    parser.add_argument("--out-dir", type=Path, default=Path("runtime/analysis"))
    parser.add_argument("--latency-pctl", type=float, default=0.95)
    parser.add_argument("--iter-pctl", type=float, default=0.90)
    args = parser.parse_args()

    df = load_jsonl(args.input)
    run_df = build_run_frame(df)
    if run_df.empty:
        raise SystemExit("No runs found in input.")

    # Thresholds
    latency_thresh = np.nanquantile(run_df["total_latency"], args.latency_pctl)
    iter_thresh = np.nanquantile(run_df["iteration_count"], args.iter_pctl)

    signals = {
        "latency_high": run_df["total_latency"] >= latency_thresh,
        "iteration_high": run_df["iteration_count"] >= iter_thresh,
        "hard_gate_violation": run_df["hard_gate_violation"].fillna(False),
    }

    # Per-signal metrics.
    metrics = _metric_frame(run_df, signals)

    # Ablation: drop each signal from OR and measure recall loss.
    all_or = signals["latency_high"] | signals["iteration_high"] | signals["hard_gate_violation"]
    total_failures = int(run_df["failure"].sum())
    recall_all = (all_or & run_df["failure"]).sum() / total_failures if total_failures else 0.0
    ablation_rows = []
    for name in signals:
        remaining = [s for n, s in signals.items() if n != name]
        if remaining:
            or_without = remaining[0]
            for s in remaining[1:]:
                or_without = or_without | s
        else:
            or_without = pd.Series([False] * len(run_df))
        recall_without = (or_without & run_df["failure"]).sum() / total_failures if total_failures else 0.0
        ablation_rows.append(
            {
                "signal_removed": name,
                "recall_all_signals": round(recall_all, 4),
                "recall_without_signal": round(recall_without, 4),
                "recall_drop": round(recall_all - recall_without, 4),
            }
        )

    ablation_df = pd.DataFrame(ablation_rows)
    out_df = metrics.merge(ablation_df, left_on="signal", right_on="signal_removed", how="left").drop(
        columns=["signal_removed"]
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = args.out_dir / "ablation_signals.csv"
    out_df.to_csv(out_csv, index=False)

    summary = {
        "total_runs": int(len(run_df)),
        "total_failures": int(run_df["failure"].sum()),
        "latency_threshold_ms": float(latency_thresh),
        "iteration_threshold": float(iter_thresh),
        "latency_percentile": args.latency_pctl,
        "iteration_percentile": args.iter_pctl,
    }
    (args.out_dir / "ablation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote {out_csv}")
    print(f"Wrote {args.out_dir / 'ablation_summary.json'}")


if __name__ == "__main__":
    main()
