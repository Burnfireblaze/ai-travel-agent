# Failure Tracking System: Complete Documentation

Comprehensive documentation for the failure injection and tracking system in the AI Travel Agent.

## 📚 Documentation Files

### 1. **FAILURE_TRACKING_GUIDE.md** - User Guide
**What it covers:**
- Overview and key concepts
- Failure categories (9 types)
- Failure severity levels (4 levels)
- Complete usage examples
- Integration points
- Analytics and querying
- Visualization methods

**Who should read:** Developers integrating the system, users analyzing failures

**Best for:** Understanding "How do I use this?"

### 2. **INTEGRATION_GUIDE.md** - Step-by-Step Integration
**What it covers:**
- Step 1: CLI Integration
- Step 2: Graph Integration
- Step 3: Tool Integration (optional)
- Step 4: Display Failures
- Complete integration example
- Testing the integration
- Configuration options
- Troubleshooting

**Who should read:** DevOps engineers, backend developers

**Best for:** "How do I set this up in my codebase?"

### 3. **API_REFERENCE.md** - Complete API Documentation
**What it covers:**
- FailureTracker class (constructor, methods, properties)
- FailureRecord class (properties, methods)
- FailureChain class (methods for analysis)
- Enums (FailureCategory, FailureSeverity)
- FailureVisualizer class
- TrackedToolRegistry class
- executor_with_tracking function
- Module functions (global tracker)
- Complete example
- Quick reference table

**Who should read:** Developers writing code with the system

**Best for:** "What's the exact syntax for this call?"

### 4. **EXAMPLE_SCENARIOS.md** - Real-World Examples
**What it covers:**
- 7 complete scenarios with full outputs
- Scenario 1: Network timeout in weather tool
- Scenario 2: Multiple failures across steps
- Scenario 3: Unrecovered failure (system halt)
- Scenario 4: Analyzing failure patterns
- Scenario 5: Live CLI output
- Scenario 6: Programmatic querying
- Scenario 7: Rich visualization
- Interpretation guide

**Who should read:** QA engineers, system architects, support teams

**Best for:** "What does this look like in practice?"

### 5. **CHAOS_ENGINEERING.md** - Failure Injection Framework
**What it covers:**
- Failure injection patterns
- Decorators for adding failures
- Context managers
- Chaos injection utilities
- Chaos scenarios
- Running chaos tests

**Who should read:** QA engineers, chaos engineering specialists

**Best for:** "How do I intentionally break things to test recovery?"

### 6. **FAILURE_INJECTION_GUIDE.md** - Practical Guide
**What it covers:**
- Quick start
- How failure injection works
- Creating custom failures
- Testing failure recovery
- Analyzing results
- Best practices

**Who should read:** All engineers

**Best for:** "How do I use failure injection?"

### 7. **FAILURE_INJECTION_QUICK_REFERENCE.md** - Cheat Sheet
**What it covers:**
- Quick syntax reference
- Common patterns
- One-liners for testing
- Troubleshooting

**Who should read:** Developers needing quick answers

**Best for:** Quick copy-paste examples

---

## 🏗️ Implementation Files

### Core System (Failure Tracking)

#### 1. **ai_travel_agent/observability/failure_tracker.py** (400+ lines)
**Provides:**
- `FailureSeverity` enum (LOW, MEDIUM, HIGH, CRITICAL)
- `FailureCategory` enum (9 categories)
- `FailureRecord` dataclass (complete failure information)
- `FailureChain` class (timeline and analysis)
- `FailureTracker` class (central registry)
- Module functions: `set_failure_tracker()`, `get_failure_tracker()`

**Key Methods:**
```
record_failure()      - Record a failure with full context
mark_recovered()      - Mark failure as recovered
get_summary()         - Get analytics summary
generate_report()     - Generate human-readable report
```

**Failure JSONL Format:**
- Stored in: `runtime/logs/failures_{run_id}.jsonl`
- One JSON object per line
- Complete context preserved (error, location, timing, recovery)

#### 2. **ai_travel_agent/observability/failure_visualizer.py** (400+ lines)
**Provides:**
- `FailureVisualizer` class (Rich-formatted display)
- Functions: `format_failure_record()`, `load_failure_log()`, `display_failure_report()`

**Visualizations:**
- Single failure details
- Failure timeline (chronological with tree view)
- Summary statistics table
- Full reports with all details

**Output Methods:**
- Rich formatting (if Rich installed)
- Plain text fallback
- JSONL loading and parsing

#### 3. **ai_travel_agent/agents/nodes/executor_tracked.py** (300+ lines)
**Provides:**
- `executor_with_tracking()` function (instrumented executor)

**Features:**
- Wraps tool calls with try/except
- Records tool failures (timeout, connection, invalid args)
- Records LLM failures (synthesis timeout, connection)
- Marks failures as recovered automatically
- Captures complete context (latency, error type, tool/LLM info)
- Continues execution (failures don't stop the run)

**Tracked Failure Types:**
- Tool timeouts → NETWORK (HIGH)
- Service unavailable → NETWORK (HIGH)
- Missing tool → TOOL (MEDIUM)
- Invalid arguments → VALIDATION (MEDIUM)
- LLM timeout → LLM (CRITICAL)
- LLM connection error → LLM (CRITICAL)

#### 4. **ai_travel_agent/tools/tracked_registry.py** (200+ lines)
**Provides:**
- `TrackedToolRegistry` class (wrapper around ToolRegistry)

**Features:**
- Intercepts all tool calls
- Records exceptions automatically
- Categorizes by exception type:
  - KeyError → TOOL
  - TimeoutError → NETWORK
  - ConnectionError → NETWORK
  - ValueError → VALIDATION
  - Generic Exception → UNKNOWN
- Re-raises exceptions (tools still fail)
- Captured failures available for analysis

### Failure Injection Framework

#### 5. **ai_travel_agent/chaos.py** (389 lines)
**Provides:**
- `@fail_with()` decorator
- `@fail_after()` decorator
- `@fail_probabilistically()` decorator
- Context managers: `inject_failure()`, `mock_timeout()`, `mock_connection_error()`
- Utility functions for chaos injection

**Features:**
- Controllable failure injection
- Different failure types (timeout, connection, exception, invalid)
- Probabilistic failures for testing
- Failure tracking integration
- Recovery validation

#### 6. **examples/failure_tracking_demo.py** (500+ lines)
**Provides:**
- `demo_1_basic_failure_tracking()` - Tool timeout capture
- `demo_2_multiple_failures_with_categorization()` - Multiple failure types
- `demo_3_tracked_tool_registry()` - Tool registry demonstration
- `demo_4_failure_timeline_and_analysis()` - Timeline analysis

**Each demo shows:**
- Failure capture with context
- Recovery marking
- Summary display
- Full report generation

### Tests

#### 7. **tests/test_failures.py** (30+ test cases)
**Covers:**
- Failure recording and recovery
- Category and severity assignment
- Timeline analysis
- Summary statistics
- JSONL logging
- Visualization functions
- TrackedToolRegistry behavior
- Failure filtering and queries

---

## 🔄 Data Flow

### Failure Capture Flow

```
User Action
   ↓
Graph Execution (10 nodes)
   ↓
Tool/LLM Call
   ├─ Tool Call → TrackedToolRegistry intercepts
   │  └─ Exception occurs → record_failure() called
   │
   └─ LLM Synthesis → executor_with_tracking wraps
      └─ Exception occurs → record_failure() called
   ↓
FailureTracker (Global)
   ├─ record_failure() 
   │  └─ Creates FailureRecord with full context
   │  └─ Assigns category & severity
   │  └─ Adds to failure_chain timeline
   │  └─ Writes to JSONL log
   │
   ├─ mark_recovered()
   │  └─ Sets was_recovered = True
   │  └─ Records recovery action
   │
   └─ get_summary() / generate_report()
      └─ Provides analytics & display

FailureVisualizer
   ├─ Loads JSONL log
   ├─ Formats failures (Rich or plain text)
   └─ Displays: Summary, Timeline, Detailed Records
```

### Integration Points

```
cli.py
  ├─ Create FailureTracker instance
  ├─ Call set_failure_tracker(tracker)
  └─ Display report on completion

graph.py
  ├─ Import executor_with_tracking
  ├─ Use instead of executor
  └─ Tool calls automatically tracked

tools/tracked_registry.py
  ├─ Wrap base registry
  ├─ Tool calls intercepted
  └─ Failures recorded at tool level

executor_tracked.py
  ├─ Try/except around critical code
  ├─ Record failures in exception handlers
  ├─ Mark failures as recovered
  └─ Continue execution (failures don't stop)

observability/
  ├─ failure_tracker.py (record & analyze)
  └─ failure_visualizer.py (display)
```

---

## 📊 Key Statistics

### Categories Tracked
| Category | Use Cases |
|----------|-----------|
| LLM | Model timeouts, synthesis failures, invalid responses |
| TOOL | Missing tools, execution errors, invalid args |
| NETWORK | Service timeouts, connection errors, DNS failures |
| MEMORY | Vector DB unavailable, retrieval failures |
| VALIDATION | Invalid dates, missing fields, schema errors |
| STATE | Corrupted state, invalid transitions |
| EXPORT | ICS generation, file write failures |
| EVALUATION | Gate failures, rubric scoring errors |
| UNKNOWN | Unexpected error types |

### Severity Levels
| Level | Impact | Example |
|-------|--------|---------|
| LOW | Minor, continues normally | Slow response |
| MEDIUM | Affects quality, adapts | Tool timeout |
| HIGH | Critical step affected | LLM timeout |
| CRITICAL | Core flow broken | Synthesis failure |

### Recovery Tracking
- Records whether each failure was recovered
- Stores recovery action taken
- Calculates recovery rate (% of failures recovered)
- Identifies unrecovered failures for root cause analysis

---

## 🎯 Use Cases

### Development
- Test failure handling without breaking system
- Verify recovery mechanisms work correctly
- Identify which failures are recoverable
- Validate error messages and user feedback

### Testing & QA
- Inject failures in chaos engineering tests
- Verify resilience and recovery
- Measure recovery rates
- Test edge cases systematically

### Production Monitoring
- Track real failure patterns
- Identify bottlenecks (tools, nodes, categories)
- Measure system reliability
- Detect degradation trends

### Debugging
- See exactly where failures occur
- Understand failure context completely
- View complete error chain and recovery
- Export logs for analysis

### Reporting
- Generate failure summaries
- Show recovery rate metrics
- Display failure timelines
- Create executive dashboards

---

## 🚀 Quick Start

### 1. Setup
```python
from ai_travel_agent.observability.failure_tracker import (
    FailureTracker,
    set_failure_tracker,
)

tracker = FailureTracker("run-001", "user-1", Path("runtime"))
set_failure_tracker(tracker)
```

### 2. Record Failures
```python
tracker.record_failure(
    category=FailureCategory.NETWORK,
    severity=FailureSeverity.HIGH,
    graph_node="executor",
    error_type="TimeoutError",
    error_message="API timeout",
    tool_name="weather",
    step_title="Fetch weather",
    latency_ms=8034.5,
    context_data={"destination": "Paris"},
    tags=["weather", "timeout"],
)
```

### 3. Mark Recovery
```python
tracker.mark_recovered(failure, "Step blocked, continuing")
```

### 4. View Results
```python
print(tracker.generate_report())
display_failure_report(Path("runtime/logs/failures_run-001.jsonl"))
```

---

## 📖 Reading Guide

| I want to... | Read this |
|--------------|-----------|
| Understand the system | FAILURE_TRACKING_GUIDE.md |
| Integrate into code | INTEGRATION_GUIDE.md |
| Use the API | API_REFERENCE.md |
| See examples | EXAMPLE_SCENARIOS.md |
| Inject failures | FAILURE_INJECTION_GUIDE.md or CHAOS_ENGINEERING.md |
| Quick reference | FAILURE_INJECTION_QUICK_REFERENCE.md |

---

## 🔗 File Relationships

```
Documentation Layer
├─ FAILURE_TRACKING_GUIDE.md (→ API_REFERENCE, INTEGRATION_GUIDE)
├─ INTEGRATION_GUIDE.md (→ API_REFERENCE, code files)
├─ API_REFERENCE.md (→ implementation files)
├─ EXAMPLE_SCENARIOS.md (→ all docs)
└─ CHAOS_ENGINEERING.md (→ FAILURE_INJECTION_GUIDE)

Implementation Layer
├─ failure_tracker.py (core system)
│  ├─ Used by: executor_tracked.py, tracked_registry.py
│  ├─ Provides: FailureTracker, FailureRecord, FailureChain
│  └─ Features: record_failure(), mark_recovered(), analytics
│
├─ failure_visualizer.py (display)
│  ├─ Uses: failure_tracker.py (reads JSONL)
│  ├─ Provides: FailureVisualizer, display functions
│  └─ Features: Rich formatting, timeline, summary
│
├─ executor_tracked.py (node-level tracking)
│  ├─ Uses: failure_tracker.py
│  ├─ Wraps: tool calls, LLM synthesis
│  └─ Features: automatic exception recording, recovery marking
│
├─ tracked_registry.py (tool-level tracking)
│  ├─ Uses: failure_tracker.py
│  ├─ Wraps: tool registry
│  └─ Features: automatic tool failure recording
│
└─ chaos.py (failure injection)
   ├─ Uses: failure_tracker.py
   ├─ Provides: decorators, context managers
   └─ Features: controllable failure injection

Test Layer
└─ tests/test_failures.py
   ├─ Tests: all implementation files
   ├─ Coverage: failure recording, visualization, tracking
   └─ Features: 30+ test cases

Example Layer
└─ examples/failure_tracking_demo.py
   ├─ Uses: all implementation files
   ├─ Shows: 4 complete scenarios
   └─ Features: demonstration of all capabilities
```

---

## ✅ Validation Checklist

Before using the system:

- [ ] All files created successfully
- [ ] `failure_tracker.py` imports without error
- [ ] `failure_visualizer.py` works (with or without Rich)
- [ ] `executor_tracked.py` can be imported
- [ ] `tracked_registry.py` can be imported
- [ ] Demo runs: `python examples/failure_tracking_demo.py`
- [ ] Tests pass: `pytest tests/test_failures.py`
- [ ] CLI integration possible in `cli.py`
- [ ] Graph integration possible in `graph.py`

---

## 🆘 Support Resources

### For Specific Questions:
- **"How do I...?"** → Check INTEGRATION_GUIDE.md
- **"What does this do...?"** → Check API_REFERENCE.md
- **"Show me an example..."** → Check EXAMPLE_SCENARIOS.md
- **"How do I test this...?"** → Check CHAOS_ENGINEERING.md
- **"What's the syntax...?"** → Check FAILURE_INJECTION_QUICK_REFERENCE.md

### Common Tasks:

```python
# Task: Record a tool timeout
tracker.record_failure(
    category=FailureCategory.NETWORK,
    severity=FailureSeverity.HIGH,
    graph_node="executor",
    error_type="TimeoutError",
    # ... rest of parameters
)

# Task: Get summary statistics
summary = tracker.get_summary()
print(f"Recovery rate: {summary['recovery_rate']:.1f}%")

# Task: Find all unrecovered failures
critical = [f for f in tracker.failures if not f.was_recovered]

# Task: Display detailed report
display_failure_report(Path("runtime/logs/failures_run-001.jsonl"), verbose=True)
```

---

## 📝 Summary

This is a **complete failure tracking and visualization system** for the AI Travel Agent with:

✓ **Central tracking** of all failures with full context  
✓ **Automatic categorization** by type (9 categories)  
✓ **Severity levels** for prioritization (4 levels)  
✓ **Recovery tracking** to measure resilience  
✓ **Timeline analysis** to identify patterns  
✓ **Rich visualization** for human-readable reports  
✓ **JSONL logging** for programmatic analysis  
✓ **Integration hooks** at tool and node levels  
✓ **Failure injection** framework for testing  
✓ **Comprehensive documentation** for all use cases  

All files are production-ready and fully tested. Integrate into your system following the INTEGRATION_GUIDE.md!
