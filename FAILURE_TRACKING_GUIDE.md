# Failure Tracking & Visualization System

A comprehensive system for capturing, categorizing, tracking, and visualizing failures with full context and recovery information.

## Overview

### What It Does

1. **Captures Failures**: Records every failure with complete context
2. **Categorizes**: Classifies failures by type (LLM, Tool, Network, Validation, etc.)
3. **Assigns Severity**: Rates impact (Low, Medium, High, Critical)
4. **Tags**: Marks failures for filtering and analysis
5. **Tracks Recovery**: Records how each failure was handled
6. **Visualizes**: Displays failures in human-readable formats with timeline

### Key Components

| Component | Purpose |
|-----------|---------|
| `FailureTracker` | Central registry for all failures in a run |
| `FailureRecord` | Complete information about a single failure |
| `TrackedToolRegistry` | Wraps tool calls with automatic failure tracking |
| `executor_tracked` | Instrumented executor with failure logging |
| `FailureVisualizer` | Display failures with rich formatting |

---

## Failure Categories

Each failure falls into one category:

| Category | Examples |
|----------|----------|
| `LLM` | LLM timeout, invalid response, connection error |
| `TOOL` | Tool not found, invalid arguments, execution error |
| `NETWORK` | Timeout, connection refused, DNS error |
| `MEMORY` | Chroma unavailable, retrieval failure |
| `VALIDATION` | Invalid date format, missing fields, schema error |
| `STATE` | Corrupted state, invalid step, circular reference |
| `EXPORT` | ICS generation failure, disk write error |
| `EVALUATION` | Hard gate failure, rubric scoring error |
| `UNKNOWN` | Unexpected error type |

---

## Failure Severity

Each failure has a severity level:

| Severity | Impact | Examples |
|----------|--------|----------|
| `LOW` | Minor, system continues | Slow response |
| `MEDIUM` | Affects quality, plan adapts | Tool timeout |
| `HIGH` | Critical step affected | LLM timeout |
| `CRITICAL` | Core flow broken | Synthesis failure |

---

## Usage

### 1. Initialize Tracker

```python
from ai_travel_agent.observability.failure_tracker import (
    FailureTracker,
    set_failure_tracker,
)
from pathlib import Path

# Create tracker
tracker = FailureTracker(
    run_id="run-001",
    user_id="user-1",
    runtime_dir=Path("./runtime")
)

# Set globally (for all nodes to access)
set_failure_tracker(tracker)
```

### 2. Record a Failure

```python
from ai_travel_agent.observability.failure_tracker import (
    FailureCategory,
    FailureSeverity,
)

failure = tracker.record_failure(
    category=FailureCategory.NETWORK,
    severity=FailureSeverity.HIGH,
    graph_node="executor",
    error_type="TimeoutError",
    error_message="Weather API timeout after 8 seconds",
    tool_name="weather_summary",
    step_title="Fetch weather for Paris",
    latency_ms=8034.5,
    error_traceback="... full traceback ...",
    context_data={
        "destination": "Paris",
        "start_date": "2026-03-15",
        "timeout_seconds": 8,
    },
    tags=["weather", "network_timeout", "paris"],
)
```

### 3. Mark as Recovered

```python
tracker.mark_recovered(
    failure,
    recovery_action="Step marked as blocked, orchestrator continues"
)
```

### 4. Generate Report

```python
# Get summary
summary = tracker.get_summary()
# {
#     "run_id": "run-001",
#     "total_failures": 4,
#     "by_severity": {"high": 2, "medium": 2},
#     "by_category": {"network": 2, "validation": 2},
#     "by_node": {"executor": 2, "intent_parser": 2},
#     "recovery_rate": 75.0,
# }

# Generate full report
report = tracker.generate_report()
print(report)
```

### 5. View Failures

```python
from ai_travel_agent.observability.failure_visualizer import (
    display_failure_report,
)

display_failure_report(
    log_path=Path("runtime/logs/failures_run-001.jsonl"),
    verbose=True  # Show detailed records
)
```

---

## How Failures Are Logged

### Failure Log File

Location: `runtime/logs/failures_{run_id}.jsonl`

Each line is a JSON failure record:

```json
{
  "failure_id": "failure_run-001_000",
  "timestamp": "2026-02-15T10:30:45.123Z",
  "run_id": "run-001",
  "user_id": "user-1",
  "category": "network",
  "severity": "high",
  "graph_node": "executor",
  "step_id": "step-1",
  "step_type": "TOOL_CALL",
  "step_title": "Fetch weather for Paris",
  "error_type": "TimeoutError",
  "error_message": "Weather API timeout after 8 seconds",
  "error_traceback": "Traceback (most recent call last):\n...",
  "tool_name": "weather_summary",
  "llm_model": null,
  "latency_ms": 8034.5,
  "attempt_number": 1,
  "was_recovered": true,
  "recovery_action": "Step marked as blocked, orchestrator continues",
  "context_data": {
    "destination": "Paris",
    "start_date": "2026-03-15"
  },
  "tags": ["weather", "network_timeout", "paris"]
}
```

---

## Integration Points

### In executor.py (executor_tracked.py)

```python
def executor_with_tracking(state, *, tools, llm, metrics):
    failure_tracker = get_failure_tracker()
    
    try:
        result = tools.call(tool_name, **tool_args)
    except TimeoutError as e:
        failure = failure_tracker.record_failure(
            category=FailureCategory.NETWORK,
            severity=FailureSeverity.HIGH,
            graph_node="executor",
            error_type="TimeoutError",
            error_message=str(e),
            tool_name=tool_name,
            latency_ms=elapsed_ms,
            error_traceback=traceback.format_exc(),
            context_data={...},
            tags=[...],
        )
        failure_tracker.mark_recovered(failure, "Step marked as blocked")
        plan[idx]["status"] = "blocked"
```

### In Tools (tracked_registry.py)

```python
class TrackedToolRegistry:
    def call(self, name, run_id, user_id, step_id, **kwargs):
        try:
            return self.base_registry.call(name, **kwargs)
        except TimeoutError as e:
            failure_tracker.record_failure(
                category=FailureCategory.NETWORK,
                severity=FailureSeverity.HIGH,
                error_type="TimeoutError",
                tool_name=name,
                ...
            )
            raise
```

---

## Failure Timeline Analysis

### Get Timeline

```python
failures_timeline = tracker.failure_chain.get_failure_timeline()
# Returns failures sorted by timestamp

for failure in failures_timeline:
    print(f"{failure.timestamp}: {failure.error_type} @ {failure.graph_node}")
```

### Get Failures by Node

```python
executor_failures = tracker.failure_chain.get_failures_by_node("executor")
parser_failures = tracker.failure_chain.get_failures_by_node("intent_parser")
```

### Get Critical Only

```python
critical = tracker.failure_chain.get_critical_failures()
```

---

## Visualization

### With Rich (if installed)

```python
from ai_travel_agent.observability.failure_visualizer import FailureVisualizer

visualizer = FailureVisualizer()

# Display single failure
visualizer.print_failure_record(failure_dict)

# Display timeline
visualizer.print_failure_timeline(failures_list)

# Display summary
visualizer.print_summary(summary_dict)
```

### Plain Text

If Rich is not installed, falls back to plain text formatting:

```python
from ai_travel_agent.observability.failure_visualizer import (
    format_failure_record
)

text = format_failure_record(failure_dict)
print(text)
```

---

## Example: Full Failure Tracking Flow

### Setup (in cli.py)

```python
from ai_travel_agent.observability.failure_tracker import (
    FailureTracker,
    set_failure_tracker,
)

# Create tracker
failure_tracker = FailureTracker(
    run_id=run_id,
    user_id=settings.user_id,
    runtime_dir=settings.runtime_dir
)

# Make globally available
set_failure_tracker(failure_tracker)
```

### During Execution

```python
# In executor_tracked.py
from ai_travel_agent.observability.failure_tracker import get_failure_tracker

try:
    result = tools.call("weather_summary", destination="Paris", ...)
except TimeoutError as e:
    tracker = get_failure_tracker()
    failure = tracker.record_failure(
        category=FailureCategory.NETWORK,
        severity=FailureSeverity.HIGH,
        graph_node="executor",
        error_type="TimeoutError",
        error_message=str(e),
        tool_name="weather_summary",
        latency_ms=8034.5,
        context_data={"destination": "Paris"},
        tags=["weather", "timeout"],
    )
    tracker.mark_recovered(failure, "Step blocked, plan continues")
```

### Visualization

```python
# After run completes
summary = failure_tracker.get_summary()
print(failure_tracker.generate_report())

# View in browser/file
display_failure_report(
    Path("runtime/logs/failures_{run_id}.jsonl"),
    verbose=True
)
```

---

## Recovery Actions

Each failure records how it was handled:

| Failure Type | Recovery Action |
|--------------|-----------------|
| Tool timeout | "Step marked as blocked, orchestrator continues" |
| Tool missing | "Tool marked as missing from registry" |
| LLM timeout | "Empty response returned, evaluation marks run failed" |
| Validation error | "Agent asked user for clarification" |
| Network error | "Retried with exponential backoff" |
| State corruption | "State validated, inconsistencies logged" |

---

## Analytics

### Recovery Rate

```python
summary = tracker.get_summary()
recovery_rate = summary["recovery_rate"]  # 0.0 to 100.0
```

**Interpretation**:
- 100% = All failures were handled gracefully
- < 100% = Some failures prevented recovery
- 0% = No failures were recovered from

### Failure Distribution

```python
summary["by_severity"]  # {"high": 2, "medium": 1, "critical": 1}
summary["by_category"]  # {"network": 2, "validation": 2}
summary["by_node"]      # {"executor": 3, "intent_parser": 1}
```

---

## Querying Failures

### By Severity

```python
critical_failures = [f for f in tracker.failures if f.severity == "critical"]
```

### By Category

```python
network_failures = [f for f in tracker.failures if f.category == "network"]
```

### By Tag

```python
timeout_failures = [f for f in tracker.failures if "timeout" in f.tags]
```

### Unrecovered

```python
unrecovered = [f for f in tracker.failures if not f.was_recovered]
```

---

## Demo

Run the demonstration:

```bash
python examples/failure_tracking_demo.py
```

This shows:
1. Basic failure capture
2. Multiple failures with categorization
3. Tool registry tracking
4. Failure timeline analysis

---

## Files

| File | Purpose |
|------|---------|
| `ai_travel_agent/observability/failure_tracker.py` | Core tracking system |
| `ai_travel_agent/observability/failure_visualizer.py` | Visualization utilities |
| `ai_travel_agent/agents/nodes/executor_tracked.py` | Example integration in executor |
| `ai_travel_agent/tools/tracked_registry.py` | Tool-level tracking |
| `examples/failure_tracking_demo.py` | Demo with 4 scenarios |

---

## Best Practices

1. **Set Global Tracker Early**: Initialize and set tracker in CLI before running agent
2. **Tag Strategically**: Use tags for filtering (tool names, error types, components)
3. **Include Context**: Capture state, arguments, and other relevant data
4. **Mark Recovery**: Always mark when a failure is recovered
5. **Regular Analysis**: Review failure reports to identify patterns
6. **Monitor Timeline**: Check if failures cluster at specific stages

---

## Integration Checklist

- [ ] Import FailureTracker in cli.py
- [ ] Create tracker with run_id, user_id, runtime_dir
- [ ] Call set_failure_tracker(tracker)
- [ ] In nodes/tools, import get_failure_tracker()
- [ ] Wrap critical sections with try/except
- [ ] Call tracker.record_failure() in exception handlers
- [ ] Call tracker.mark_recovered() with recovery action
- [ ] Display report after run: tracker.generate_report()
- [ ] View detailed failures: display_failure_report(log_path)

---

## Summary

This system provides:

✓ **Complete visibility** into where failures occur  
✓ **Automatic categorization** of failure types  
✓ **Tagged tracking** for easy filtering  
✓ **Recovery tracking** to see how failures are handled  
✓ **Timeline analysis** to identify patterns  
✓ **Rich visualization** for human-readable reports  
✓ **JSONL logging** for programmatic analysis  

Use this to understand system resilience and identify improvement areas!
