# Integration Guide: Failure Tracking in Main System

This guide shows how to integrate the failure tracking system into the main AI Travel Agent codebase.

## Overview

The integration involves 4 main steps:

1. **CLI Integration**: Create tracker in cli.py
2. **Graph Integration**: Use executor_with_tracking
3. **Tool Integration**: Wrap tools with TrackedToolRegistry
4. **Visualization**: Display failures after run

---

## Step 1: CLI Integration (cli.py)

### Current Code (simplified)

```python
def chat(query: str, ...):
    # Build app
    app = build_app(...)
    
    # Run agent
    result = app.invoke(input_data)
    
    # Display results
    print(result)
```

### Updated Code

```python
from pathlib import Path
from ai_travel_agent.observability.failure_tracker import (
    FailureTracker,
    set_failure_tracker,
)
from ai_travel_agent.observability.failure_visualizer import (
    display_failure_report,
)

def chat(query: str, ...):
    # 1. Create failure tracker
    run_id = f"run-{int(time.time())}"
    failure_tracker = FailureTracker(
        run_id=run_id,
        user_id=settings.user_id,
        runtime_dir=settings.runtime_dir
    )
    
    # 2. Make it globally available
    set_failure_tracker(failure_tracker)
    
    try:
        # 3. Build and run app
        app = build_app(...)
        result = app.invoke(input_data)
        
        # 4. Display results
        print(result)
    
    finally:
        # 5. Display failure summary
        summary = failure_tracker.get_summary()
        if summary["total_failures"] > 0:
            print("\n" + "="*60)
            print("FAILURE REPORT")
            print("="*60)
            print(failure_tracker.generate_report())
            
            # Optional: Display full details
            log_path = settings.runtime_dir / "logs" / f"failures_{run_id}.jsonl"
            if log_path.exists():
                display_failure_report(log_path, verbose=True)
```

### Key Changes

1. Create `FailureTracker` with `run_id`, `user_id`, `runtime_dir`
2. Call `set_failure_tracker()` to make it globally available
3. Always display report (in finally block) so it shows even if run fails
4. Optional: Display detailed failures if failures occurred

---

## Step 2: Graph Integration (graph.py)

### Current Executor Usage (simplified)

```python
from ai_travel_agent.agents.nodes.executor import executor

def build_app(tools, llm, metrics):
    # ... other nodes ...
    
    graph.add_node("executor", executor)
```

### Updated Graph Usage

```python
from ai_travel_agent.agents.nodes.executor_tracked import executor_with_tracking
from ai_travel_agent.agents.nodes.executor import executor

def build_app(tools, llm, metrics, use_tracking=True):
    # ... other nodes ...
    
    if use_tracking:
        # Use instrumented executor with failure tracking
        graph.add_node("executor", 
            lambda state: executor_with_tracking(
                state, 
                tools=tools, 
                llm=llm, 
                metrics=metrics
            )
        )
    else:
        # Use original executor (for debugging)
        graph.add_node("executor", executor)
```

### Alternative: Direct Replacement

If you want to always use tracking, simply replace the import:

```python
# Replace:
# from ai_travel_agent.agents.nodes.executor import executor

# With:
from ai_travel_agent.agents.nodes.executor_tracked import executor_with_tracking as executor

# Then use normally:
graph.add_node("executor", executor)
```

### What executor_with_tracking Does

1. Wraps each tool call in try/except
2. Records failures with category/severity/context
3. Marks failures as recovered when handled
4. Captures latency and error details
5. Continues execution (failures don't stop the run)

---

## Step 3: Tool Integration (Optional)

### Current Tool Usage (simplified)

```python
def build_tools():
    registry = ToolRegistry()
    return registry
```

### Enhanced Tool Usage with Tracking

```python
from ai_travel_agent.tools.tracked_registry import TrackedToolRegistry

def build_tools(use_tracking=True):
    base_registry = ToolRegistry()
    
    if use_tracking:
        # Wrap with tracking
        return TrackedToolRegistry(base_registry)
    else:
        # Use base (for debugging)
        return base_registry
```

### Alternative: Always Wrapped

If you want tracking always active:

```python
def build_tools():
    from ai_travel_agent.tools.tracked_registry import TrackedToolRegistry
    
    base_registry = ToolRegistry()
    return TrackedToolRegistry(base_registry)
```

### What TrackedToolRegistry Does

1. Intercepts all tool calls
2. Records tool-specific failures:
   - `KeyError`: Tool not found
   - `TimeoutError`: Network timeout
   - `ConnectionError`: Service unavailable
   - `ValueError`: Invalid arguments
   - Generic Exception: Unknown errors
3. Automatic severity/category assignment
4. Continues execution (re-raises after recording)

---

## Step 4: Display Failures

### In CLI (after run)

```python
# Show summary
summary = failure_tracker.get_summary()
if summary["total_failures"] > 0:
    print(f"\n{summary['total_failures']} failures occurred:")
    print(f"  By severity: {summary['by_severity']}")
    print(f"  By category: {summary['by_category']}")
    print(f"  By node: {summary['by_node']}")
    print(f"  Recovery rate: {summary['recovery_rate']:.1f}%")
```

### Full Report

```python
print(failure_tracker.generate_report())
```

Output example:

```
FAILURE TRACKING REPORT
=======================

Run ID: run-1708000245
User ID: user-1
Total Failures: 4
Recovery Rate: 75.0%

BY CATEGORY
-----------
Network: 2 (1 high, 1 medium)
Validation: 2 (2 medium)

BY SEVERITY
-----------
High: 2
Medium: 2
Low: 0
Critical: 0

BY NODE
-------
executor: 3
intent_parser: 1

FAILURE TIMELINE
----------------
[10:30:45.123] Network (HIGH) @ executor: TimeoutError - Weather API timeout
[10:30:47.456] Validation (MEDIUM) @ intent_parser: Invalid date format
[10:30:49.789] Network (MEDIUM) @ executor: ConnectionError - Hotel service unavailable
[10:31:01.012] Validation (MEDIUM) @ executor: Missing required field 'destination'

DETAILED RECORDS
----------------
[Failure 1] Network (HIGH) @ executor
  Error: TimeoutError - Weather API timeout after 8 seconds
  Tool: weather_summary
  Latency: 8034.5ms
  Recovered: Yes
  Recovery: Step marked as blocked, orchestrator continues
  Tags: weather, timeout, paris
  Time: 2026-02-15T10:30:45.123Z
...
```

### Detailed Visualization

```python
from ai_travel_agent.observability.failure_visualizer import (
    display_failure_report,
)

display_failure_report(
    log_path=settings.runtime_dir / "logs" / f"failures_{run_id}.jsonl",
    verbose=True
)
```

---

## Complete Integration Example

Here's a complete example of all integrations together:

### cli.py

```python
import time
from pathlib import Path
from ai_travel_agent.observability.failure_tracker import (
    FailureTracker,
    set_failure_tracker,
    get_failure_tracker,
)
from ai_travel_agent.observability.failure_visualizer import (
    display_failure_report,
)
from ai_travel_agent.graph import build_app

def chat(
    query: str,
    disambiguate: bool = True,
    append_to_current: bool = False,
    include_reasoning: bool = False,
):
    """Chat with the travel agent"""
    
    # 1. Initialize tracker
    run_id = f"run-{int(time.time() * 1000)}"
    failure_tracker = FailureTracker(
        run_id=run_id,
        user_id=settings.user_id,
        runtime_dir=settings.runtime_dir,
    )
    set_failure_tracker(failure_tracker)
    
    try:
        # 2. Build app (now uses executor_with_tracking automatically)
        app = build_app(
            use_tracking=True,  # Enable failure tracking
            tools_use_tracking=True,  # Enable tool tracking
        )
        
        # 3. Run agent
        result = app.invoke({...}, ...)
        
        # 4. Display results
        print(result)
    
    finally:
        # 5. Always display failure report
        failure_tracker = get_failure_tracker()
        summary = failure_tracker.get_summary()
        
        if summary["total_failures"] > 0:
            # Summary table
            print("\n" + "="*60)
            print("FAILURE SUMMARY")
            print("="*60)
            print(f"Total Failures: {summary['total_failures']}")
            print(f"Recovery Rate: {summary['recovery_rate']:.1f}%")
            print(f"\nBy Category: {summary['by_category']}")
            print(f"By Severity: {summary['by_severity']}")
            print(f"By Node: {summary['by_node']}")
            
            # Detailed report
            if len(failure_tracker.failures) > 0:
                print("\n" + "="*60)
                print("FAILURE DETAILS")
                print("="*60)
                print(failure_tracker.generate_report())
            
            # Save to file
            log_path = settings.runtime_dir / "logs" / f"failures_{run_id}.jsonl"
            print(f"\nFailure log saved to: {log_path}")
```

### graph.py

```python
from ai_travel_agent.agents.nodes.executor_tracked import executor_with_tracking
from ai_travel_agent.tools.tracked_registry import TrackedToolRegistry

def build_app(use_tracking=True, tools_use_tracking=True):
    # ... existing code ...
    
    # Build tools
    base_tools = build_tools()
    if tools_use_tracking:
        tools = TrackedToolRegistry(base_tools)
    else:
        tools = base_tools
    
    # ... add other nodes ...
    
    # Add executor
    if use_tracking:
        graph.add_node(
            "executor",
            lambda state: executor_with_tracking(
                state,
                tools=tools,
                llm=llm,
                metrics=metrics,
            ),
        )
    else:
        from ai_travel_agent.agents.nodes.executor import executor
        graph.add_node("executor", executor)
    
    # ... rest of graph ...
```

---

## Testing the Integration

### Simple Test

```python
# Run agent with intentional failure
python -m ai_travel_agent chat "Plan a trip" --chaos-mode

# Should show failure report at end
# FAILURE SUMMARY
# Total Failures: X
# Recovery Rate: Y%
```

### Check Logs

```bash
# View failure log file
cat runtime/logs/failures_run-*.jsonl

# Pretty-print JSON
cat runtime/logs/failures_run-*.jsonl | jq .
```

### Inspect Failures Programmatically

```python
from ai_travel_agent.observability.failure_tracker import get_failure_tracker

tracker = get_failure_tracker()

# List all failures
for failure in tracker.failures:
    print(f"{failure.graph_node}: {failure.error_type} - {failure.error_message}")

# Get by category
network_failures = [f for f in tracker.failures if f.category == "network"]
print(f"Network failures: {len(network_failures)}")

# Get recovery rate
summary = tracker.get_summary()
print(f"Recovery rate: {summary['recovery_rate']:.1f}%")
```

---

## Configuration

### Settings (in config.py or settings)

```python
class Settings:
    # Failure tracking
    track_failures: bool = True
    track_tools: bool = True
    failure_log_dir: Path = Path("runtime/logs")
    failure_log_format: str = "jsonl"  # jsonl or json
    
    # Visualization
    show_failure_summary: bool = True
    show_failure_details: bool = True
    verbose_failures: bool = False
```

### CLI Flags

```python
@app.command()
def chat(
    query: str,
    # ... existing flags ...
    
    # New failure tracking flags
    track_failures: bool = typer.Option(True, "--track-failures"),
    track_tools: bool = typer.Option(True, "--track-tools"),
    show_failures: bool = typer.Option(True, "--show-failures"),
):
    """Chat with travel agent"""
    failure_tracker = FailureTracker(...) if track_failures else None
    # ... rest of chat ...
```

---

## Troubleshooting

### Failures Not Being Captured

1. Check that `set_failure_tracker()` was called
2. Verify nodes are importing `get_failure_tracker()`
3. Check that try/except blocks exist around critical code
4. Review `tracker.failures` list for content

### No Failures Showing in Report

1. Run with `--chaos-mode` to inject failures
2. Check that you're accessing the right `failure_tracker` instance
3. Verify recovery actions are being marked

### Report Not Displaying

1. Check that `show_failure_summary` is True
2. Verify failures were actually recorded
3. Test with: `print(failure_tracker.generate_report())`

### JSONL File Not Created

1. Check `runtime_dir` path exists
2. Verify `logs/` subdirectory is created
3. Ensure write permissions on runtime directory
4. Check that `total_failures > 0`

---

## Integration Checklist

### Phase 1: CLI Setup
- [ ] Import FailureTracker and set_failure_tracker
- [ ] Create tracker instance in chat() command
- [ ] Call set_failure_tracker(tracker)
- [ ] Add finally block to display report
- [ ] Test: Run agent, check for failure summary

### Phase 2: Graph Integration
- [ ] Import executor_with_tracking
- [ ] Update build_app to use executor_with_tracking
- [ ] Test: Run agent, verify executor tracks failures

### Phase 3: Tool Integration (Optional)
- [ ] Import TrackedToolRegistry
- [ ] Update build_tools to wrap with TrackedToolRegistry
- [ ] Test: Run agent with tool failures, verify tracking

### Phase 4: Visualization
- [ ] Import display_failure_report
- [ ] Add verbose failure display in CLI
- [ ] Test: Run agent, view detailed failure report
- [ ] Verify JSONL log is created

### Phase 5: Configuration (Optional)
- [ ] Add tracking flags to CLI
- [ ] Add tracking settings to config
- [ ] Test: Run with --no-track-failures, verify no tracking

---

## Next Steps

1. Integrate CLI setup (Step 1)
2. Update graph to use executor_with_tracking (Step 2)
3. Run agent and verify failures are tracked
4. Add detailed visualization display
5. Create dashboard or analysis scripts

---

## Support

For questions about specific integration steps:

1. Check `FAILURE_TRACKING_GUIDE.md` for usage examples
2. Review example code in `examples/failure_tracking_demo.py`
3. Inspect source code in:
   - `ai_travel_agent/observability/failure_tracker.py`
   - `ai_travel_agent/agents/nodes/executor_tracked.py`
   - `ai_travel_agent/tools/tracked_registry.py`
   - `ai_travel_agent/observability/failure_visualizer.py`
