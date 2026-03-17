#!/usr/bin/env python3
"""
Run-level dataset generator for selective telemetry research.

Inputs:
  - runtime/logs/app.jsonl (or a user-specified JSONL log file)

Outputs:
  - run_dataset.csv
  - failure_features.csv
  - telemetry_coverage.csv

Requirements:
  - Python 3.10+
  - pandas, numpy
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


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
                # Skip malformed lines to keep pipeline robust.
                continue
    return pd.DataFrame(rows)


def _ensure_columns(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    for col in cols:
        if col not in df.columns:
            df[col] = np.nan
    return df


def build_run_dataset(df: pd.DataFrame) -> pd.DataFrame:
    # Ensure required columns exist.
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
            "tokens_in",
            "tokens_out",
            "overall_status",
            "step_index",
            "scenario",
            "hard_gate_no_fabricated_real_time_facts",
        ],
    )

    # Filter to rows with a run_id.
    df = df[df["run_id"].notna()].copy()
    if df.empty:
        return pd.DataFrame()

    # Coerce numeric fields.
    for col in ("latency_ms", "tokens_in", "tokens_out", "step_index"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Parse timestamps (if present).
    df["ts_parsed"] = pd.to_datetime(df["ts"], errors="coerce")

    # Base aggregates.
    event_count = df.groupby("run_id").size().rename("event_count")
    total_latency = df.groupby("run_id")["latency_ms"].sum(min_count=1).rename("total_latency")
    tokens_total = (df["tokens_in"].fillna(0) + df["tokens_out"].fillna(0)).groupby(df["run_id"]).sum()
    tokens_total = tokens_total.rename("tokens_total")

    # Tool metrics.
    is_tool = df["event_group"].eq("tool")
    tool_calls = is_tool.groupby(df["run_id"]).sum().rename("tool_calls")
    tool_failures = (
        is_tool
        & (
            df["status"].eq("failed")
            | df["level"].eq("ERROR")
            | df["event"].astype(str).str.contains("tool_error", case=False, na=False)
        )
    ).groupby(df["run_id"]).sum().rename("tool_failures")

    # API error rate (LLM + tool error events / total LLM+tool events).
    is_llm_or_tool = df["event_group"].isin(["llm", "tool"])
    api_errors = (
        is_llm_or_tool
        & (
            df["status"].eq("failed")
            | df["level"].eq("ERROR")
            | df["event"].astype(str).str.contains("error", case=False, na=False)
        )
    ).groupby(df["run_id"]).sum()
    api_total = is_llm_or_tool.groupby(df["run_id"]).sum()
    api_error_rate = (api_errors / api_total.replace(0, np.nan)).fillna(0).rename("api_error_rate")

    # Iteration count: prefer step_selected count, fallback to max step_index + 1.
    step_selected = df["event"].astype(str).eq("step_selected").groupby(df["run_id"]).sum()
    max_step_index = df.groupby("run_id")["step_index"].max(min_count=1)
    iteration_count = step_selected.where(step_selected > 0, max_step_index.fillna(-1) + 1)
    iteration_count = iteration_count.fillna(0).rename("iteration_count")

    # Hallucination detection (hard gate or explicit scenario).
    hallucination = (
        df["hard_gate_no_fabricated_real_time_facts"].eq(False)
        | df["scenario"].astype(str).eq("eval_price_fabrication")
        | df["event"].astype(str).str.contains("price_fabrication", case=False, na=False)
    ).groupby(df["run_id"]).any().rename("hallucination_detected")

    # PII detection (if field exists or event hints).
    if "pii_detected" in df.columns:
        pii = df["pii_detected"].fillna(False).astype(bool)
    else:
        pii = df["event"].astype(str).str.contains("pii", case=False, na=False)
    pii_detected = pii.groupby(df["run_id"]).any().rename("pii_detected")

    # Goal completed: last non-null overall_status == "good".
    df_sorted = df.sort_values(["run_id", "ts_parsed"], kind="stable")
    last_status = (
        df_sorted.groupby("run_id")["overall_status"]
        .apply(lambda s: s.dropna().iloc[-1] if not s.dropna().empty else np.nan)
    )
    goal_completed = last_status.eq("good").rename("goal_completed")

    # Failure definition.
    status_failed = df["status"].eq("failed").groupby(df["run_id"]).any()
    failure_category_present = df["failure_category"].notna().groupby(df["run_id"]).any()
    failure = (status_failed | failure_category_present | ~goal_completed.fillna(False)).rename("failure")

    # Event group coverage (counts per run).
    event_group_counts = (
        df.pivot_table(index="run_id", columns="event_group", values="event", aggfunc="count", fill_value=0)
        .rename(columns=lambda c: f"event_group_{c}")
    )

    # Assemble run-level dataset.
    run_dataset = pd.concat(
        [
            event_count,
            total_latency,
            iteration_count,
            tool_calls,
            tool_failures,
            api_error_rate,
            tokens_total,
            hallucination,
            pii_detected,
            goal_completed,
            failure,
            event_group_counts,
        ],
        axis=1,
    ).reset_index()

    # Fill missing numeric values with 0 for convenience.
    for col in [
        "total_latency",
        "iteration_count",
        "event_count",
        "tool_calls",
        "tool_failures",
        "api_error_rate",
        "tokens_total",
    ]:
        if col in run_dataset.columns:
            run_dataset[col] = run_dataset[col].fillna(0)

    return run_dataset


def compute_telemetry_coverage(dataset: pd.DataFrame) -> pd.DataFrame:
    """
    Summarize event_group coverage by outcome (success vs failure).
    Requires event_group_* columns in the run-level dataset.
    """
    group_cols = [c for c in dataset.columns if c.startswith("event_group_")]
    if not group_cols:
        return pd.DataFrame(columns=["event_group", "events_success", "events_failure"])

    success_mask = ~dataset["failure"].fillna(False)
    events_success = dataset.loc[success_mask, group_cols].sum()
    events_failure = dataset.loc[~success_mask, group_cols].sum()

    coverage = pd.DataFrame(
        {
            "event_group": [c.replace("event_group_", "") for c in group_cols],
            "events_success": events_success.values,
            "events_failure": events_failure.values,
        }
    )
    return coverage


def extract_failure_features(dataset: pd.DataFrame) -> pd.DataFrame:
    """
    Extract a feature matrix suitable for logistic regression.
    """
    cols = [
        "run_id",
        "total_latency",
        "iteration_count",
        "tool_calls",
        "tool_failures",
        "api_error_rate",
        "tokens_total",
        "event_count",
        "failure",
    ]
    return dataset.loc[:, [c for c in cols if c in dataset.columns]].copy()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate run-level dataset from app.jsonl")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("runtime/logs/app.jsonl"),
        help="Path to app.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Output directory for CSV files",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input log not found: {args.input}")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    df = load_jsonl(args.input)
    run_dataset = build_run_dataset(df)
    run_dataset.to_csv(args.output_dir / "run_dataset.csv", index=False)

    failure_features = extract_failure_features(run_dataset)
    failure_features.to_csv(args.output_dir / "failure_features.csv", index=False)

    telemetry_coverage = compute_telemetry_coverage(run_dataset)
    telemetry_coverage.to_csv(args.output_dir / "telemetry_coverage.csv", index=False)

    print(f"Wrote {args.output_dir / 'run_dataset.csv'}")
    print(f"Wrote {args.output_dir / 'failure_features.csv'}")
    print(f"Wrote {args.output_dir / 'telemetry_coverage.csv'}")


if __name__ == "__main__":
    main()
