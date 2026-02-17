# Telemetry & Experiments Report

This report describes how to collect telemetry and run experiments for the AI Travel Agent.

## How to Run Experiments

```
python run_experiments.py
```

The script reads prompts from `docs/PROMPTS.md` (section **Experiment Queries**) and writes:

- `runtime/experiments/results.csv`
- `runtime/experiments/summary.csv`

## Example Trace Output (JSONL)

Below is a **sample** trace entry (sanitized + truncated):

```json
{"timestamp":"2026-02-16T12:00:00Z","event":"tool_call","run_id":"...","user_id":"...","data":{"tool_name":"flights_search_links","tool_args":{"origin":"SFO","destination":"DEL","start_date":"2026-02-17"},"attempt":1}}
```

## Example Summary Table

```
Mode,Avg Latency (ms),Avg Log Size (KB),Failures Detected (%)
minimal,1200.0,2.4,40.0
detailed,1350.0,18.7,90.0
selective,1280.0,6.9,80.0
```

> Replace the example values above with the actual numbers from `runtime/experiments/summary.csv` after running the experiment script.
