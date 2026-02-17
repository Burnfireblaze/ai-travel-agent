# Failure Tracking: Example Scenarios & Expected Output

Real-world examples showing how the failure tracking system works with actual outputs.

---

## Scenario 1: Network Timeout in Weather Tool

### Setup
```python
from ai_travel_agent.observability.failure_tracker import (
    FailureTracker,
    FailureCategory,
    FailureSeverity,
    set_failure_tracker,
)

tracker = FailureTracker("run-001", "user-1", Path("runtime"))
set_failure_tracker(tracker)
```

### User Action
```
User: "Plan a trip to Paris in March"
```

### System Flow
1. Intent Parser processes query ✓
2. Brain Planner creates outline ✓
3. Planner generates steps ✓
4. Executor tries to fetch weather ✗ **TIMEOUT**

### Failure Capture
```python
# In executor.py (exception handler)
failure = tracker.record_failure(
    category=FailureCategory.NETWORK,
    severity=FailureSeverity.HIGH,
    graph_node="executor",
    error_type="TimeoutError",
    error_message="Weather API timeout after 8.0 seconds",
    tool_name="weather_summary",
    step_id="step-3",
    step_type="TOOL_CALL",
    step_title="Fetch weather for Paris in March",
    latency_ms=8034.5,
    error_traceback="Traceback (most recent call last):\n  ...",
    attempt_number=1,
    context_data={
        "destination": "Paris",
        "start_date": "2026-03-15",
        "end_date": "2026-03-22",
    },
    tags=["weather", "network_timeout", "paris"],
)

# Mark as recovered
tracker.mark_recovered(
    failure,
    "Step marked as blocked, orchestrator continues with remaining steps"
)
```

### Failure Record (in JSONL)
```json
{
  "failure_id": "failure_run-001_000",
  "timestamp": "2026-02-15T10:30:45.123Z",
  "run_id": "run-001",
  "user_id": "user-1",
  "category": "network",
  "severity": "high",
  "graph_node": "executor",
  "step_id": "step-3",
  "step_type": "TOOL_CALL",
  "step_title": "Fetch weather for Paris in March",
  "error_type": "TimeoutError",
  "error_message": "Weather API timeout after 8.0 seconds",
  "error_traceback": "Traceback (most recent call last):\n...",
  "tool_name": "weather_summary",
  "llm_model": null,
  "latency_ms": 8034.5,
  "attempt_number": 1,
  "was_recovered": true,
  "recovery_action": "Step marked as blocked, orchestrator continues with remaining steps",
  "context_data": {
    "destination": "Paris",
    "start_date": "2026-03-15",
    "end_date": "2026-03-22"
  },
  "tags": ["weather", "network_timeout", "paris"]
}
```

### Summary Output
```
Total Failures: 1
Recovery Rate: 100.0%

By Category:
  network: 1

By Severity:
  high: 1

By Node:
  executor: 1
```

### Full Report
```
FAILURE TRACKING REPORT
=======================

Run ID: run-001
User ID: user-1
Timestamp: 2026-02-15T10:30:45Z
Total Failures: 1
Recovery Rate: 100.0%

BY CATEGORY
-----------
Network: 1 (1 high)

BY SEVERITY
-----------
High: 1

BY NODE
-------
executor: 1

FAILURE TIMELINE
----------------
[10:30:45.123] Network (HIGH) @ executor: TimeoutError
  Step: Fetch weather for Paris in March
  Tool: weather_summary
  Latency: 8034.5ms
  Recovered: Yes

DETAILED RECORDS
----------------
[Failure 1/1] Network (HIGH) @ executor
  Failure ID: failure_run-001_000
  Timestamp: 2026-02-15T10:30:45.123Z
  
  Error Information
  -----------------
  Type: TimeoutError
  Message: Weather API timeout after 8.0 seconds
  Latency: 8034.5ms
  Attempt: 1
  
  Location
  --------
  Node: executor
  Step: Fetch weather for Paris in March (step-3)
  Step Type: TOOL_CALL
  
  Tool Information
  ----------------
  Tool: weather_summary
  Arguments: destination=Paris, start_date=2026-03-15, end_date=2026-03-22
  
  Recovery Information
  --------------------
  Was Recovered: Yes
  Recovery Action: Step marked as blocked, orchestrator continues with remaining steps
  
  Tags: weather, network_timeout, paris
```

---

## Scenario 2: Multiple Failures Across Steps

### User Action
```
User: "Plan a trip to NYC for April, budget $5000"
```

### Failures During Execution

**Failure 1: Invalid Date Format** (Validation)
```python
failure_1 = tracker.record_failure(
    category=FailureCategory.VALIDATION,
    severity=FailureSeverity.MEDIUM,
    graph_node="intent_parser",
    error_type="ValueError",
    error_message="Invalid date format in user input: 'April' must be YYYY-MM-DD",
    step_title="Parse user intent and extract constraints",
    latency_ms=145.2,
    context_data={"user_input": "April for April"},
    tags=["validation", "date_format", "user_input"],
)
tracker.mark_recovered(failure_1, "Agent asked user for clarification: 'Please provide date as YYYY-MM-DD'")
```

**Failure 2: Hotel Service Unavailable** (Network)
```python
failure_2 = tracker.record_failure(
    category=FailureCategory.NETWORK,
    severity=FailureSeverity.HIGH,
    graph_node="executor",
    error_type="ConnectionError",
    error_message="Hotels service unavailable (503 Service Unavailable)",
    tool_name="hotels_summary",
    step_title="Find hotels in NYC",
    latency_ms=3456.7,
    context_data={"destination": "NYC", "check_in": "2026-04-15"},
    tags=["hotels", "service_unavailable", "nyc"],
)
tracker.mark_recovered(failure_2, "Step marked as blocked, used backup cache from previous search")
```

**Failure 3: LLM Timeout** (LLM)
```python
failure_3 = tracker.record_failure(
    category=FailureCategory.LLM,
    severity=FailureSeverity.CRITICAL,
    graph_node="executor",
    error_type="TimeoutError",
    error_message="LLM synthesis timeout after 30 seconds",
    llm_model="qwen2.5:7b-instruct",
    step_title="Synthesize itinerary for NYC trip",
    latency_ms=30234.5,
    context_data={"num_days": 5, "num_attractions": 12},
    tags=["llm", "synthesis", "timeout"],
)
tracker.mark_recovered(failure_3, "Used simplified template response")
```

### Summary Output
```
Total Failures: 3
Recovery Rate: 100.0%

By Category:
  network: 1
  validation: 1
  llm: 1

By Severity:
  critical: 1
  high: 1
  medium: 1

By Node:
  executor: 2
  intent_parser: 1
```

### Report Output

```
FAILURE TRACKING REPORT
=======================

Run ID: run-001
User ID: user-1
Timestamp: 2026-02-15T10:30:45Z
Total Failures: 3
Recovery Rate: 100.0%

BY CATEGORY
-----------
Validation: 1 (1 medium)
Network: 1 (1 high)
LLM: 1 (1 critical)

BY SEVERITY
-----------
Critical: 1
High: 1
Medium: 1

BY NODE
-------
executor: 2
intent_parser: 1

FAILURE TIMELINE
----------------
[10:30:45.234] Validation (MEDIUM) @ intent_parser: ValueError
  Step: Parse user intent and extract constraints
  Recovered: Yes
  
[10:30:47.890] Network (HIGH) @ executor: ConnectionError
  Step: Find hotels in NYC
  Tool: hotels_summary
  Recovered: Yes
  
[10:31:18.124] LLM (CRITICAL) @ executor: TimeoutError
  Step: Synthesize itinerary for NYC trip
  Model: qwen2.5:7b-instruct
  Recovered: Yes

DETAILED RECORDS
----------------
[Failure 1/3] Validation (MEDIUM) @ intent_parser
  Timestamp: 2026-02-15T10:30:45.234Z
  Error: ValueError - Invalid date format in user input: 'April' must be YYYY-MM-DD
  Latency: 145.2ms
  Recovered: Yes
  Recovery: Agent asked user for clarification: 'Please provide date as YYYY-MM-DD'
  Tags: validation, date_format, user_input

[Failure 2/3] Network (HIGH) @ executor
  Timestamp: 2026-02-15T10:30:47.890Z
  Error: ConnectionError - Hotels service unavailable (503 Service Unavailable)
  Tool: hotels_summary
  Latency: 3456.7ms
  Recovered: Yes
  Recovery: Step marked as blocked, used backup cache from previous search
  Tags: hotels, service_unavailable, nyc

[Failure 3/3] LLM (CRITICAL) @ executor
  Timestamp: 2026-02-15T10:31:18.124Z
  Error: TimeoutError - LLM synthesis timeout after 30 seconds
  Model: qwen2.5:7b-instruct
  Latency: 30234.5ms
  Recovered: Yes
  Recovery: Used simplified template response
  Tags: llm, synthesis, timeout
```

---

## Scenario 3: Unrecovered Failure (System Halt)

### User Action
```
User: "Plan a trip to Paris"
```

### Critical Failure: State Corruption

**Failure Recorded:**
```python
failure = tracker.record_failure(
    category=FailureCategory.STATE,
    severity=FailureSeverity.CRITICAL,
    graph_node="orchestrator",
    error_type="RuntimeError",
    error_message="State validation failed: inconsistent step references detected",
    step_title="Orchestrate planning loop",
    latency_ms=None,
    error_traceback="Traceback (most recent call last):\n...",
    context_data={
        "invalid_references": ["step-5 references deleted step-2"],
        "inconsistent_states": ["step-3 status both COMPLETED and PENDING"],
    },
    tags=["state_corruption", "critical_error"],
)

# NOT recovered - system halts
tracker.mark_recovered(failure, None)  # No recovery action
```

### Summary Output
```
Total Failures: 1
Recovery Rate: 0.0%  # ← Not recovered!

By Category:
  state: 1

By Severity:
  critical: 1

By Node:
  orchestrator: 1

CRITICAL FAILURES DETECTED: System cannot continue
```

### User Feedback
```
Travel Agent: I encountered a critical system error and cannot continue planning your trip.

Error Details:
- Issue: State validation failed: inconsistent step references detected
- Location: Orchestration step
- Status: NOT RECOVERED
- Time: 2026-02-15T10:35:20Z

Please contact support with error ID: failure_run-001_000
```

---

## Scenario 4: Analyzing Failure Patterns

### Code to Extract Patterns

```python
from ai_travel_agent.observability.failure_tracker import get_failure_tracker

tracker = get_failure_tracker()

# 1. Which tools fail most?
tool_failures = {}
for failure in tracker.failures:
    if failure.tool_name:
        tool_failures[failure.tool_name] = tool_failures.get(failure.tool_name, 0) + 1

print("Tool Failure Counts:")
for tool, count in sorted(tool_failures.items(), key=lambda x: x[1], reverse=True):
    print(f"  {tool}: {count} failures")

# 2. Which nodes are problematic?
node_failures = {}
for failure in tracker.failures:
    node_failures[failure.graph_node] = node_failures.get(failure.graph_node, 0) + 1

print("\nNode Failure Counts:")
for node, count in sorted(node_failures.items(), key=lambda x: x[1], reverse=True):
    print(f"  {node}: {count} failures")

# 3. Time to failure trend
print("\nFailure Timeline:")
timeline = tracker.failure_chain.get_failure_timeline()
for failure in timeline:
    print(f"  {failure.timestamp.isoformat()}: {failure.category} - {failure.error_type}")

# 4. Unrecovered failures (critical!)
unrecovered = tracker.failure_chain.get_unrecovered_failures()
print(f"\nUnrecovered Failures: {len(unrecovered)}")
for failure in unrecovered:
    print(f"  {failure.graph_node}: {failure.error_message}")

# 5. Recovery rate by category
recovery_by_category = {}
category_totals = {}
for failure in tracker.failures:
    category_totals[failure.category] = category_totals.get(failure.category, 0) + 1
    if failure.was_recovered:
        recovery_by_category[failure.category] = recovery_by_category.get(failure.category, 0) + 1

print("\nRecovery Rate by Category:")
for category in sorted(category_totals.keys()):
    recovered = recovery_by_category.get(category, 0)
    total = category_totals[category]
    rate = (recovered / total * 100) if total > 0 else 0
    print(f"  {category}: {recovered}/{total} ({rate:.1f}%)")
```

### Output Example

```
Tool Failure Counts:
  weather_summary: 8 failures
  hotels_summary: 5 failures
  geocoding_service: 3 failures
  flights_links: 2 failures

Node Failure Counts:
  executor: 12 failures
  intent_parser: 3 failures
  planner: 2 failures

Failure Timeline:
  2026-02-15T10:30:45.123Z: network - TimeoutError
  2026-02-15T10:30:47.456Z: validation - ValueError
  2026-02-15T10:30:49.789Z: network - ConnectionError
  2026-02-15T10:31:01.012Z: validation - ValueError
  ...

Unrecovered Failures: 0

Recovery Rate by Category:
  network: 8/8 (100.0%)
  validation: 3/3 (100.0%)
  tool: 2/2 (100.0%)
  memory: 1/1 (100.0%)
  unknown: 1/1 (100.0%)
```

---

## Scenario 5: Live CLI Output

### Terminal Display

```bash
$ python -m ai_travel_agent chat "Plan a trip to Tokyo in May"

Travel Agent: Let me plan a trip to Tokyo for you...

🔍 Processing your request...
   ✓ Intent parsed successfully
   ✓ Initial plan generated
   ⏱️  Fetching weather... (⚠️  timeout, using historical data)
   ✓ Searching flights
   ⚠️  Hotel search temporarily unavailable (using alternatives)
   ✓ Finding attractions
   ✓ Creating itinerary
   ✓ Exporting calendar

Travel Agent: I've planned your Tokyo trip! Here's your 5-day itinerary...
[Full itinerary displayed]

============================================================
FAILURE SUMMARY
============================================================
Total Failures: 2
Recovery Rate: 100.0%

By Category:
  network: 2

By Severity:
  high: 2

By Node:
  executor: 2

FAILURE TIMELINE
================
[10:45:23.234] Network (HIGH) @ executor
  Step: Fetch weather for Tokyo in May
  Tool: weather_summary
  Latency: 8034.5ms
  Recovered: Yes

[10:45:27.567] Network (HIGH) @ executor
  Step: Find hotels in Shibuya
  Tool: hotels_summary
  Latency: 5123.4ms
  Recovered: Yes

Failure log saved to: runtime/logs/failures_run-1708000245.jsonl
```

---

## Scenario 6: Querying Failures Programmatically

```python
from ai_travel_agent.observability.failure_tracker import (
    FailureCategory,
    FailureSeverity,
    get_failure_tracker,
)

tracker = get_failure_tracker()

# 1. Get specific failure type
network_failures = [
    f for f in tracker.failures 
    if f.category == FailureCategory.NETWORK
]
print(f"Network failures: {len(network_failures)}")

# 2. Get failures by tag
weather_failures = [
    f for f in tracker.failures 
    if "weather" in f.tags
]
print(f"Weather-related failures: {len(weather_failures)}")

# 3. Get failures by tool
weather_tool_failures = [
    f for f in tracker.failures 
    if f.tool_name == "weather_summary"
]
print(f"weather_summary failures: {len(weather_tool_failures)}")

# 4. Get by node and time
import datetime
executor_failures_today = [
    f for f in tracker.failures
    if f.graph_node == "executor" and
    f.timestamp.date() == datetime.date.today()
]
print(f"Executor failures today: {len(executor_failures_today)}")

# 5. Get high-severity + unrecovered (critical!)
critical_issues = [
    f for f in tracker.failures
    if f.severity == FailureSeverity.CRITICAL and
    not f.was_recovered
]
print(f"CRITICAL UNRECOVERED: {len(critical_issues)}")
for failure in critical_issues:
    print(f"  {failure.error_message} @ {failure.graph_node}")
```

---

## Scenario 7: Visualization Output

### Rich Terminal Display (if Rich installed)

```
┌─────────────────────────────────────────────────────────────┐
│ FAILURE TRACKING REPORT                                     │
│ Run: run-001  User: user-1  Time: 2026-02-15T10:30:45Z    │
└─────────────────────────────────────────────────────────────┘

Total Failures: 3  |  Recovery Rate: 100.0%

╔═══════════════════════════════════════════════════════════╗
║ BY CATEGORY                                               ║
╠═════════════════╦══════════════════════════════════════╣
║ Network         ║ ████████░ 2 (1 HIGH, 1 MEDIUM)      ║
║ Validation      ║ ██░ 1 (1 MEDIUM)                    ║
╚═════════════════╩══════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════╗
║ BY SEVERITY                                               ║
╠═════════════════╦══════════════════════════════════════╣
║ CRITICAL        ║                                      ║
║ HIGH            ║ ████░ 1                              ║
║ MEDIUM          ║ ██░ 2                                ║
║ LOW             ║                                      ║
╚═════════════════╩══════════════════════════════════════╝

FAILURE TIMELINE
================
executor
├─ [10:30:45.123] Network (HIGH) TimeoutError
│                  └─ Weather API timeout after 8 seconds
│
├─ [10:30:47.456] Network (MEDIUM) ConnectionError
│                  └─ Hotels service unavailable (503)
│
intent_parser
└─ [10:30:50.789] Validation (MEDIUM) ValueError
                   └─ Invalid date format in user input
```

---

## Interpretation Guide

### Recovery Rate

| Rate | Meaning | Action |
|------|---------|--------|
| 100% | All failures handled gracefully | ✓ System is resilient |
| 75-99% | Most failures recovered | ⚠️ Investigate unrecovered |
| 50-74% | Many failures unrecovered | 🔴 Critical issues exist |
| < 50% | System frequently fails | 🔴 Major redesign needed |

### Failure Density

| Failures/Run | Assessment | Action |
|--------------|-----------|--------|
| 0-1 | Excellent | Monitor and improve |
| 2-5 | Good | Log and analyze trends |
| 6-10 | Concerning | Investigate root causes |
| > 10 | Critical | Urgent system review |

### By Category

**LLM failures** → Check model health, network, prompts  
**Tool failures** → Check service health, timeouts, credentials  
**Network failures** → Check connectivity, rate limits, DNS  
**Validation failures** → Improve input validation, user prompts  
**Memory failures** → Check Chroma health, vector DB  
**State failures** → Review orchestration logic, state management  

---

## Summary

The failure tracking system provides:

✓ **Complete visibility** into where, when, and why failures occur  
✓ **Automatic categorization** for easy analysis  
✓ **Recovery tracking** to validate resilience  
✓ **Timeline analysis** to identify patterns  
✓ **Programmatic access** for custom reporting  
✓ **Multiple visualizations** for different audiences  

Use these scenarios and examples to understand system behavior and improve reliability!
