# Failure Tracking System: Reference Card & Visual Guide

Quick visual reference for the entire failure tracking system.

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AI TRAVEL AGENT                             │
│                    (10 Connected Graph Nodes)                       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
            │   TOOLS      │  │     LLM      │  │   MEMORY     │
            │   CALLS      │  │ SYNTHESIS    │  │   STORE      │
            └──────────────┘  └──────────────┘  └──────────────┘
                    │               │               │
                    └───────────────┼───────────────┘
                                    ▼
        ┌───────────────────────────────────────────────────────┐
        │         FAILURE CAPTURE LAYER                         │
        │                                                       │
        │  ┌────────────────────────────────────────────────┐  │
        │  │ TrackedToolRegistry (Tool-level)              │  │
        │  │  • Intercepts tool.call()                     │  │
        │  │  • Records: timeout, connection, invalid args │  │
        │  │  • Re-raises exception                        │  │
        │  └────────────────────────────────────────────────┘  │
        │                                                       │
        │  ┌────────────────────────────────────────────────┐  │
        │  │ executor_with_tracking (Node-level)           │  │
        │  │  • Wraps tool calls                           │  │
        │  │  • Wraps LLM synthesis                        │  │
        │  │  • Records all failures                       │  │
        │  │  • Marks as recovered                         │  │
        │  └────────────────────────────────────────────────┘  │
        └───────────────────────────────────────────────────────┘
                                    │
                                    ▼
        ┌───────────────────────────────────────────────────────┐
        │           FAILURE TRACKER (CENTRAL)                   │
        │                                                       │
        │  • Receives failure records                          │
        │  • Categorizes (9 types)                            │
        │  • Assigns severity (4 levels)                      │
        │  • Builds timeline (FailureChain)                   │
        │  • Calculates analytics                             │
        │  • Writes JSONL log                                 │
        │                                                       │
        │  Global Instance: set_failure_tracker() / get_failure_tracker()
        └───────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
        ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
        │  JSONL LOG FILE  │ │  FAILURE CHAIN   │ │  SUMMARY STATS   │
        │  (Persistent)    │ │  (Timeline)      │ │  (Analytics)     │
        │                  │ │                  │ │                  │
        │  failures_       │ │ get_failures_by_ │ │ get_summary()    │
        │  run-001.jsonl   │ │ node()           │ │ recovery_rate    │
        │                  │ │ get_critical_()  │ │ by_category      │
        │  Full context:   │ │ get_timeline()   │ │ by_severity      │
        │  • Error details │ │                  │ │ by_node          │
        │  • Location      │ │                  │ │                  │
        │  • Tool/LLM info │ │                  │ │                  │
        │  • Recovery      │ │                  │ │                  │
        └──────────────────┘ └──────────────────┘ └──────────────────┘
                                    │
                                    ▼
        ┌───────────────────────────────────────────────────────┐
        │       FAILURE VISUALIZER (Display Layer)              │
        │                                                       │
        │  • Load JSONL log                                    │
        │  • Format records (Rich or plain text)              │
        │  • Timeline tree view                                │
        │  • Summary statistics table                          │
        │  • Full detailed report                              │
        │                                                       │
        │  Output: Console display, HTML, text file            │
        └───────────────────────────────────────────────────────┘
```

---

## Failure Categories Hierarchy

```
FAILURES
├─ LLM (Large Language Model Issues)
│  ├─ TimeoutError: Synthesis took too long
│  ├─ ConnectionError: Model service unavailable
│  └─ ValueError: Invalid response format
│
├─ TOOL (External Tools)
│  ├─ KeyError: Tool not registered
│  ├─ TimeoutError: Tool call timeout
│  ├─ ConnectionError: Service unavailable
│  └─ ValueError: Invalid arguments
│
├─ NETWORK (Connectivity Issues)
│  ├─ TimeoutError: Request timeout
│  ├─ ConnectionError: Service unreachable
│  └─ DNSError: Domain lookup failed
│
├─ MEMORY (Vector Database)
│  ├─ Chroma unavailable
│  ├─ Retrieval failed
│  └─ Vector index corruption
│
├─ VALIDATION (Data Validation)
│  ├─ ValueError: Invalid date format
│  ├─ KeyError: Missing required field
│  └─ TypeError: Wrong data type
│
├─ STATE (Graph State)
│  ├─ Inconsistent step references
│  ├─ Invalid transition
│  └─ Corrupted state data
│
├─ EXPORT (Calendar Export)
│  ├─ ICS generation failure
│  ├─ File write error
│  └─ Invalid calendar format
│
├─ EVALUATION (Hard Gates & Rubrics)
│  ├─ Gate failure
│  ├─ Rubric scoring error
│  └─ Constraint violation
│
└─ UNKNOWN (Unexpected)
   └─ Any other exception type
```

---

## Severity Escalation Matrix

```
┌──────────────┬──────────────────────────────────────┬──────────────┐
│ Severity     │ Definition                           │ Recovery     │
├──────────────┼──────────────────────────────────────┼──────────────┤
│              │                                      │              │
│ LOW 🟢       │ Minor issue, system continues       │ Automatic    │
│              │ • Slow response time                 │ (re-attempt) │
│              │ • Sub-optimal path chosen            │              │
│              │ • Warning-level error                │              │
│              │                                      │              │
│ MEDIUM 🟡    │ Quality affected, plan adapts        │ Fallback     │
│              │ • Tool timeout (uses cache)          │ (use backup) │
│              │ • Optional data unavailable          │              │
│              │ • Graceful degradation applies       │              │
│              │                                      │              │
│ HIGH 🟠      │ Critical step affected               │ Skip step    │
│              │ • LLM timeout (empty synthesis)      │ (mark        │
│              │ • Primary tool unavailable           │  blocked)    │
│              │ • Core constraint violated           │              │
│              │                                      │              │
│ CRITICAL 🔴  │ Core flow broken, run may fail       │ System halt  │
│              │ • State corruption                   │ (error)      │
│              │ • Synthesis completely failed        │              │
│              │ • Memory system down                 │              │
│              │                                      │              │
└──────────────┴──────────────────────────────────────┴──────────────┘
```

---

## Failure Lifecycle Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                     FAILURE LIFECYCLE                               │
└─────────────────────────────────────────────────────────────────────┘

NORMAL EXECUTION
│
├─ Step executes successfully ✓
│  └─ Continue to next step
│
└─ Exception occurs ✗
   │
   ├─ Exception caught in try/except
   │  │
   │  ├─ Call tracker.record_failure()
   │  │  │
   │  │  ├─ Determine category (LLM, TOOL, NETWORK, etc.)
   │  │  ├─ Determine severity (LOW, MEDIUM, HIGH, CRITICAL)
   │  │  ├─ Capture complete context
   │  │  ├─ Create FailureRecord
   │  │  ├─ Add to failure_chain timeline
   │  │  └─ Write to JSONL log
   │  │
   │  └─ Handle failure
   │     │
   │     ├─ Attempt recovery (retry, fallback, cache, etc.)
   │     │  │
   │     │  ├─ Recovery succeeds ✓
   │     │  │  └─ Call tracker.mark_recovered(failure, "Recovery action")
   │     │  │     └─ Continue execution
   │     │  │
   │     │  └─ Recovery fails ✗
   │     │     └─ Mark as unrecovered
   │     │        └─ Choose: skip step, halt, use fallback
   │     │
   │     └─ Update step status
   │        ├─ COMPLETED (if recovered)
   │        ├─ BLOCKED (if skipped)
   │        ├─ FAILED (if unrecovered)
   │        └─ RETRYING (if attempting again)
   │
   └─ REPORT GENERATION
      │
      ├─ Calculate summary stats
      │  ├─ total_failures
      │  ├─ recovery_rate
      │  ├─ by_severity
      │  ├─ by_category
      │  └─ by_node
      │
      ├─ Generate formatted report
      │  ├─ Summary table
      │  ├─ Timeline view
      │  └─ Detailed records
      │
      └─ Display to user/log
         ├─ Console output (Rich formatted)
         ├─ JSONL persistence
         └─ Optional HTML report
```

---

## Core Classes & Relationships

```
┌─────────────────────────────────────┐
│      FailureTracker                 │
├─────────────────────────────────────┤
│ Properties:                         │
│  • run_id: str                      │
│  • user_id: str                     │
│  • failures: List[FailureRecord]   │
│  • failure_chain: FailureChain     │
│                                    │
│ Methods:                           │
│  • record_failure(...) → Record    │
│  • mark_recovered(...)             │
│  • get_summary() → dict            │
│  • generate_report() → str         │
└─────────────────────────────────────┘
           │ contains many
           ▼
┌─────────────────────────────────────┐
│      FailureRecord                  │
├─────────────────────────────────────┤
│ Properties (read-only):            │
│  • failure_id: str                 │
│  • timestamp: datetime             │
│  • category: str                   │
│  • severity: str                   │
│  • graph_node: str                 │
│  • error_type: str                 │
│  • error_message: str              │
│  • tool_name: str (optional)       │
│  • llm_model: str (optional)       │
│  • latency_ms: float               │
│  • was_recovered: bool             │
│  • recovery_action: str (optional) │
│  • tags: List[str]                │
│                                    │
│ Methods:                           │
│  • to_dict() → dict               │
└─────────────────────────────────────┘
           │ referenced by
           ▼
┌─────────────────────────────────────┐
│      FailureChain                   │
├─────────────────────────────────────┤
│ Methods:                           │
│  • add_failure(record)             │
│  • get_failure_timeline()          │
│  • get_failures_by_node(name)      │
│  • get_failures_by_category(cat)   │
│  • get_critical_failures()         │
│  • get_unrecovered_failures()      │
└─────────────────────────────────────┘

Other Classes:
│
├─ FailureSeverity (Enum)
│  ├─ LOW = "low"
│  ├─ MEDIUM = "medium"
│  ├─ HIGH = "high"
│  └─ CRITICAL = "critical"
│
├─ FailureCategory (Enum)
│  ├─ LLM = "llm"
│  ├─ TOOL = "tool"
│  ├─ NETWORK = "network"
│  ├─ MEMORY = "memory"
│  ├─ VALIDATION = "validation"
│  ├─ STATE = "state"
│  ├─ EXPORT = "export"
│  ├─ EVALUATION = "evaluation"
│  └─ UNKNOWN = "unknown"
│
├─ FailureVisualizer
│  ├─ print_failure_record(dict)
│  ├─ print_failure_timeline(list)
│  └─ print_summary(dict)
│
├─ TrackedToolRegistry
│  ├─ call(name, run_id, user_id, step_id, **kwargs)
│  └─ [wraps base registry]
│
└─ executor_with_tracking()
   ├─ function(state, tools, llm, metrics)
   └─ returns: updated state dict
```

---

## API Quick Reference

### Create & Setup
```python
# Create tracker
tracker = FailureTracker("run-id", "user-id", Path("runtime"))

# Make globally available
set_failure_tracker(tracker)

# Get tracker anywhere
tracker = get_failure_tracker()
```

### Record Failures
```python
failure = tracker.record_failure(
    category=FailureCategory.NETWORK,    # Required
    severity=FailureSeverity.HIGH,       # Required
    graph_node="executor",               # Required
    error_type="TimeoutError",           # Required
    error_message="API timeout",         # Required
    step_title="Fetch data",             # Required
    tool_name="weather" or None,         # Optional
    llm_model="qwen2.5" or None,         # Optional
    latency_ms=8034.5,                   # Optional
    error_traceback="...",               # Optional
    context_data={...},                  # Optional
    tags=["timeout", "weather"],         # Optional
)
```

### Mark Recovery
```python
tracker.mark_recovered(failure, "Step skipped, continuing")
```

### Query Failures
```python
# All failures
all_failures = tracker.failures

# Timeline (sorted by time)
timeline = tracker.failure_chain.get_failure_timeline()

# By node
executor_failures = tracker.failure_chain.get_failures_by_node("executor")

# By category
network_failures = tracker.failure_chain.get_failures_by_category("network")

# By severity
high_severity = tracker.failure_chain.get_failures_by_severity("high")

# Critical only
critical = tracker.failure_chain.get_critical_failures()

# Unrecovered
unrecovered = tracker.failure_chain.get_unrecovered_failures()

# By tag
weather_failures = [f for f in tracker.failures if "weather" in f.tags]
```

### Analytics
```python
# Summary statistics
summary = tracker.get_summary()
# → dict with: total_failures, by_severity, by_category, by_node, recovery_rate

# Full report (text)
report = tracker.generate_report()
print(report)

# Detailed text format
text = format_failure_record(failure.to_dict())
```

### Visualization
```python
# Create visualizer
visualizer = FailureVisualizer()

# Display single failure
visualizer.print_failure_record(failure.to_dict())

# Display timeline
visualizer.print_failure_timeline([f.to_dict() for f in tracker.failures])

# Display summary
visualizer.print_summary(tracker.get_summary())

# Full report from file
display_failure_report(Path("runtime/logs/failures_run-001.jsonl"), verbose=True)
```

---

## File Location Reference

```
ai-travel-agent/
├─ Documentation
│  ├─ FAILURE_TRACKING_GUIDE.md        (User guide)
│  ├─ INTEGRATION_GUIDE.md             (Setup instructions)
│  ├─ API_REFERENCE.md                 (API documentation)
│  ├─ EXAMPLE_SCENARIOS.md             (Real examples)
│  ├─ CHAOS_ENGINEERING.md             (Failure injection)
│  ├─ FAILURE_INJECTION_GUIDE.md       (How to test)
│  ├─ FAILURE_INJECTION_QUICK_REFERENCE.md (Cheat sheet)
│  └─ DOCUMENTATION_INDEX.md           (This index)
│
├─ Implementation
│  ├─ ai_travel_agent/
│  │  ├─ observability/
│  │  │  ├─ failure_tracker.py         (Core tracking)
│  │  │  └─ failure_visualizer.py      (Display)
│  │  ├─ agents/nodes/
│  │  │  └─ executor_tracked.py        (Instrumented executor)
│  │  └─ tools/
│  │     └─ tracked_registry.py        (Tool-level tracking)
│  │
│  ├─ chaos.py                         (Failure injection framework)
│  └─ examples/
│     └─ failure_tracking_demo.py      (4 demo scenarios)
│
├─ Tests
│  └─ tests/
│     └─ test_failures.py              (30+ test cases)
│
└─ Runtime Output
   └─ runtime/logs/
      └─ failures_run-001.jsonl        (JSONL failure log)
```

---

## Typical Integration Sequence

```
Step 1: CLI Setup (in cli.py)
  ├─ Create FailureTracker
  ├─ Set globally
  └─ Display report on completion

Step 2: Graph Integration (in graph.py)
  ├─ Import executor_with_tracking
  ├─ Use in graph instead of executor
  └─ Tool calls auto-tracked

Step 3: Tool Integration (optional)
  ├─ Wrap with TrackedToolRegistry
  ├─ Tool errors auto-tracked
  └─ Re-raises for executor to catch

Step 4: Visualization
  ├─ Generate report
  ├─ Display timeline
  └─ Save to JSONL

Result: Complete visibility into failures!
```

---

## Common Queries

| Goal | Query |
|------|-------|
| How many failures? | `len(tracker.failures)` |
| Recovery rate? | `tracker.get_summary()['recovery_rate']` |
| Most common category? | `max(summary['by_category'].items(), key=lambda x: x[1])[0]` |
| Failures in executor? | `tracker.failure_chain.get_failures_by_node('executor')` |
| Network failures? | `tracker.failure_chain.get_failures_by_category('network')` |
| Critical failures? | `tracker.failure_chain.get_critical_failures()` |
| Unrecovered? | `tracker.failure_chain.get_unrecovered_failures()` |
| Weather-related? | `[f for f in tracker.failures if 'weather' in f.tags]` |
| Failure timeline? | `tracker.failure_chain.get_failure_timeline()` |

---

## Success Indicators

| Metric | Target | Meaning |
|--------|--------|---------|
| Total Failures | 0-5 per run | Low error rate |
| Recovery Rate | > 90% | Most failures handled |
| Unrecovered | 0 | No critical issues |
| High/Critical | < 2 | Few severe problems |
| Network issues | < 20% | Good connectivity |
| LLM timeouts | < 10% | Fast synthesis |

---

## Summary

The Failure Tracking System provides:

✅ **Automatic capture** of all failures  
✅ **Categorization** into 9 types  
✅ **Severity levels** for prioritization  
✅ **Timeline analysis** for pattern detection  
✅ **Recovery tracking** for resilience measurement  
✅ **Rich visualization** for human-readable reports  
✅ **JSONL persistence** for programmatic analysis  
✅ **Integration hooks** at multiple levels  

**Start with**: INTEGRATION_GUIDE.md → Implement → EXAMPLE_SCENARIOS.md → Monitor with visualizations!
