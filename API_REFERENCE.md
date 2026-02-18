# Failure Tracking API Reference

Complete API documentation for the failure tracking and visualization system.

## Table of Contents

1. [FailureTracker](#failuretracker) - Central tracking registry
2. [FailureRecord](#failurerecord) - Single failure information
3. [FailureChain](#failurechain) - Chain of related failures
4. [Enums](#enums) - Category and Severity definitions
5. [FailureVisualizer](#failurevisualizer) - Visualization utilities
6. [TrackedToolRegistry](#trackedtoolregistry) - Tool-level tracking
7. [executor_with_tracking](#executor_with_tracking) - Node-level tracking

---

## FailureTracker

Central registry for all failures in a run.

### Location
```python
from ai_travel_agent.observability.failure_tracker import FailureTracker
```

### Constructor

```python
FailureTracker(
    run_id: str,
    user_id: str,
    runtime_dir: Path = Path("runtime"),
) -> FailureTracker
```

**Parameters:**
- `run_id` (str): Unique identifier for this run
- `user_id` (str): User who initiated the run
- `runtime_dir` (Path): Directory for storing logs

**Example:**
```python
from pathlib import Path
tracker = FailureTracker(
    run_id="run-1708000245",
    user_id="user-1",
    runtime_dir=Path("runtime"),
)
```

### Methods

#### record_failure

Records a single failure with full context.

```python
def record_failure(
    category: FailureCategory,
    severity: FailureSeverity,
    graph_node: str,
    error_type: str,
    error_message: str,
    step_title: str,
    step_id: str | None = None,
    step_type: str | None = None,
    tool_name: str | None = None,
    llm_model: str | None = None,
    latency_ms: float | None = None,
    error_traceback: str | None = None,
    attempt_number: int = 1,
    context_data: dict | None = None,
    tags: list[str] | None = None,
) -> FailureRecord
```

**Parameters:**
- `category`: One of `FailureCategory` enum values
- `severity`: One of `FailureSeverity` enum values
- `graph_node`: Name of the node where failure occurred
- `error_type`: Type of exception (e.g., "TimeoutError")
- `error_message`: Error message text
- `step_title`: Human-readable title of step that failed
- `step_id`: Optional unique step identifier
- `step_type`: Optional step type (TOOL_CALL, LLM_SYNTHESIS, etc.)
- `tool_name`: Name of tool if failure is tool-related
- `llm_model`: Name of LLM if failure is LLM-related
- `latency_ms`: How long operation took before failing
- `error_traceback`: Full exception traceback
- `attempt_number`: Retry attempt number
- `context_data`: Additional context (dict)
- `tags`: List of tags for filtering

**Returns:**
- `FailureRecord`: The recorded failure object

**Example:**
```python
failure = tracker.record_failure(
    category=FailureCategory.NETWORK,
    severity=FailureSeverity.HIGH,
    graph_node="executor",
    error_type="TimeoutError",
    error_message="Weather API timeout after 8 seconds",
    tool_name="weather_summary",
    step_title="Fetch weather for Paris",
    latency_ms=8034.5,
    context_data={
        "destination": "Paris",
        "start_date": "2026-03-15",
    },
    tags=["weather", "timeout", "paris"],
)
```

#### mark_recovered

Mark a failure as recovered with recovery action.

```python
def mark_recovered(
    failure: FailureRecord,
    recovery_action: str,
) -> None
```

**Parameters:**
- `failure`: FailureRecord to mark
- `recovery_action`: Description of how failure was handled

**Example:**
```python
tracker.mark_recovered(
    failure,
    "Step marked as blocked, orchestrator continues"
)
```

#### get_summary

Get analytics summary of all failures.

```python
def get_summary() -> dict
```

**Returns:**
```python
{
    "run_id": str,
    "user_id": str,
    "total_failures": int,
    "by_severity": dict[str, int],  # {"high": 2, "medium": 1, ...}
    "by_category": dict[str, int],  # {"network": 2, "validation": 1, ...}
    "by_node": dict[str, int],      # {"executor": 3, "intent_parser": 1, ...}
    "recovery_rate": float,          # 0.0 to 100.0
}
```

**Example:**
```python
summary = tracker.get_summary()
print(f"Total failures: {summary['total_failures']}")
print(f"Recovery rate: {summary['recovery_rate']:.1f}%")
```

#### generate_report

Generate human-readable failure report.

```python
def generate_report() -> str
```

**Returns:**
- str: Formatted report text

**Example:**
```python
report = tracker.generate_report()
print(report)
```

Output:
```
FAILURE TRACKING REPORT
=======================
...
```

#### Properties

```python
tracker.run_id: str                    # Run identifier
tracker.user_id: str                   # User identifier
tracker.failures: list[FailureRecord]  # All recorded failures
tracker.failure_chain: FailureChain    # Linked failures for timeline
tracker.runtime_dir: Path              # Log directory
```

---

## FailureRecord

Immutable record of a single failure.

### Location
```python
from ai_travel_agent.observability.failure_tracker import FailureRecord
```

### Properties

All properties are read-only:

```python
failure.failure_id: str                # Unique ID (e.g., "failure_run-001_000")
failure.timestamp: datetime            # When failure occurred
failure.run_id: str                    # Run ID
failure.user_id: str                   # User ID
failure.category: str                  # Failure category
failure.severity: str                  # Failure severity
failure.graph_node: str                # Node where it occurred
failure.step_id: str | None            # Step identifier
failure.step_type: str | None          # Step type (TOOL_CALL, etc.)
failure.step_title: str                # Human-readable step title
failure.error_type: str                # Exception type
failure.error_message: str             # Error message
failure.error_traceback: str | None    # Full traceback
failure.tool_name: str | None          # Tool name if tool failure
failure.llm_model: str | None          # LLM name if LLM failure
failure.latency_ms: float | None       # Time to failure (ms)
failure.attempt_number: int            # Retry attempt
failure.was_recovered: bool            # Whether recovered
failure.recovery_action: str | None    # How it was recovered
failure.context_data: dict             # Additional context
failure.tags: list[str]                # Filter tags
```

### Methods

#### to_dict

Convert to dictionary (for JSON serialization).

```python
def to_dict() -> dict
```

**Returns:**
- dict: JSON-serializable dictionary

**Example:**
```python
failure_dict = failure.to_dict()
json_str = json.dumps(failure_dict)
```

---

## FailureChain

Container for all failures in a run with analysis methods.

### Location
```python
from ai_travel_agent.observability.failure_tracker import FailureChain
```

### Constructor

```python
FailureChain() -> FailureChain
```

### Methods

#### add_failure

Add failure to chain.

```python
def add_failure(failure: FailureRecord) -> None
```

#### get_failure_timeline

Get failures sorted by timestamp.

```python
def get_failure_timeline() -> list[FailureRecord]
```

**Returns:**
- list[FailureRecord]: Failures ordered chronologically

**Example:**
```python
timeline = tracker.failure_chain.get_failure_timeline()
for failure in timeline:
    print(f"{failure.timestamp}: {failure.error_type}")
```

#### get_failures_by_node

Get all failures in a specific node.

```python
def get_failures_by_node(node_name: str) -> list[FailureRecord]
```

**Parameters:**
- `node_name`: Name of node (e.g., "executor", "intent_parser")

**Returns:**
- list[FailureRecord]: Failures in that node

**Example:**
```python
executor_failures = tracker.failure_chain.get_failures_by_node("executor")
print(f"Executor failures: {len(executor_failures)}")
```

#### get_failures_by_category

Get all failures in a category.

```python
def get_failures_by_category(category: str) -> list[FailureRecord]
```

**Parameters:**
- `category`: Category name (e.g., "network", "validation")

**Returns:**
- list[FailureRecord]: Failures in that category

#### get_failures_by_severity

Get all failures of a severity level.

```python
def get_failures_by_severity(severity: str) -> list[FailureRecord]
```

**Parameters:**
- `severity`: Severity level (e.g., "high", "critical")

**Returns:**
- list[FailureRecord]: Failures with that severity

#### get_critical_failures

Get all critical failures.

```python
def get_critical_failures() -> list[FailureRecord]
```

**Returns:**
- list[FailureRecord]: All failures with severity="critical"

#### get_unrecovered_failures

Get failures that weren't recovered.

```python
def get_unrecovered_failures() -> list[FailureRecord]
```

**Returns:**
- list[FailureRecord]: Failures where was_recovered=False

---

## Enums

### FailureCategory

```python
from ai_travel_agent.observability.failure_tracker import FailureCategory

class FailureCategory(str, Enum):
    LLM = "llm"
    TOOL = "tool"
    NETWORK = "network"
    MEMORY = "memory"
    VALIDATION = "validation"
    STATE = "state"
    EXPORT = "export"
    EVALUATION = "evaluation"
    UNKNOWN = "unknown"
```

**Usage:**
```python
category = FailureCategory.NETWORK
# or
category = "network"  # String also works
```

### FailureSeverity

```python
from ai_travel_agent.observability.failure_tracker import FailureSeverity

class FailureSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
```

**Usage:**
```python
severity = FailureSeverity.HIGH
# or
severity = "high"  # String also works
```

---

## FailureVisualizer

Visualization and reporting utilities.

### Location
```python
from ai_travel_agent.observability.failure_visualizer import FailureVisualizer
```

### Constructor

```python
FailureVisualizer() -> FailureVisualizer
```

### Methods

#### print_failure_record

Display single failure with rich formatting.

```python
def print_failure_record(failure_dict: dict) -> None
```

**Parameters:**
- `failure_dict`: Failure as dictionary (from `failure.to_dict()`)

**Example:**
```python
visualizer = FailureVisualizer()
visualizer.print_failure_record(failure.to_dict())
```

#### print_failure_timeline

Display failures as tree with timeline.

```python
def print_failure_timeline(failures: list[dict]) -> None
```

**Parameters:**
- `failures`: List of failure dictionaries

**Example:**
```python
failure_dicts = [f.to_dict() for f in tracker.failures]
visualizer.print_failure_timeline(failure_dicts)
```

#### print_summary

Display summary statistics table.

```python
def print_summary(summary: dict) -> None
```

**Parameters:**
- `summary`: Dictionary from `tracker.get_summary()`

**Example:**
```python
visualizer.print_summary(tracker.get_summary())
```

### Functions

#### format_failure_record

Format single failure as text (no Rich required).

```python
def format_failure_record(failure_dict: dict) -> str
```

**Returns:**
- str: Formatted text

**Example:**
```python
from ai_travel_agent.observability.failure_visualizer import format_failure_record
text = format_failure_record(failure.to_dict())
print(text)
```

#### load_failure_log

Load failures from JSONL log file.

```python
def load_failure_log(log_path: Path) -> list[dict]
```

**Parameters:**
- `log_path`: Path to JSONL failure log

**Returns:**
- list[dict]: List of failure records

**Example:**
```python
from ai_travel_agent.observability.failure_visualizer import load_failure_log
failures = load_failure_log(Path("runtime/logs/failures_run-001.jsonl"))
```

#### display_failure_report

Generate and display complete report.

```python
def display_failure_report(
    log_path: Path,
    verbose: bool = False,
) -> None
```

**Parameters:**
- `log_path`: Path to JSONL failure log
- `verbose`: Show detailed records if True

**Example:**
```python
from ai_travel_agent.observability.failure_visualizer import display_failure_report
display_failure_report(
    Path("runtime/logs/failures_run-001.jsonl"),
    verbose=True
)
```

---

## TrackedToolRegistry

Tool-level failure tracking wrapper.

### Location
```python
from ai_travel_agent.tools.tracked_registry import TrackedToolRegistry
```

### Constructor

```python
TrackedToolRegistry(base_registry: ToolRegistry) -> TrackedToolRegistry
```

**Parameters:**
- `base_registry`: Base ToolRegistry to wrap

**Example:**
```python
from ai_travel_agent.tools.registry import ToolRegistry
from ai_travel_agent.tools.tracked_registry import TrackedToolRegistry

base = ToolRegistry()
tracked = TrackedToolRegistry(base)
```

### Methods

#### call

Call a tool with automatic failure tracking.

```python
def call(
    name: str,
    run_id: str,
    user_id: str,
    step_id: str,
    **kwargs,
) -> Any
```

**Parameters:**
- `name`: Tool name
- `run_id`: Run identifier
- `user_id`: User identifier
- `step_id`: Step identifier
- `**kwargs`: Tool arguments

**Returns:**
- Tool result

**Raises:**
- Original exception (after recording failure)

**Example:**
```python
try:
    result = tracked.call(
        "weather_summary",
        run_id="run-001",
        user_id="user-1",
        step_id="step-1",
        destination="Paris",
        date="2026-03-15",
    )
except Exception as e:
    # Failure was already recorded
    print(f"Tool call failed: {e}")
```

**Tracked Failures:**
- `KeyError`: Tool not found → FailureCategory.TOOL
- `TimeoutError`: Network timeout → FailureCategory.NETWORK
- `ConnectionError`: Service unavailable → FailureCategory.NETWORK
- `ValueError`: Invalid arguments → FailureCategory.VALIDATION
- `Exception`: Unknown error → FailureCategory.UNKNOWN

---

## executor_with_tracking

Instrumented executor node with failure tracking.

### Location
```python
from ai_travel_agent.agents.nodes.executor_tracked import executor_with_tracking
```

### Function Signature

```python
def executor_with_tracking(
    state: AgentState,
    *,
    tools: ToolRegistry | TrackedToolRegistry,
    llm: LLMClient,
    metrics: MetricsCollector,
) -> dict
```

**Parameters:**
- `state`: Current agent state
- `tools`: Tool registry (can be tracked or not)
- `llm`: LLM client for synthesis
- `metrics`: Metrics collector

**Returns:**
- dict: Updated state with execution results

### Tracked Failures

The executor automatically tracks and recovers from:

#### Tool Failures
- **Timeout** (TimeoutError) → Marked BLOCKED
- **Connection Error** (ConnectionError) → Marked BLOCKED
- **Not Found** (KeyError) → Marked MISSING
- **Invalid Args** (ValueError) → Marked INVALID

#### LLM Failures
- **Timeout** (TimeoutError) → Empty response
- **Connection Error** (ConnectionError) → Empty response
- **Invalid Response** (ValueError) → Empty response
- **Unknown** (Exception) → Empty response

#### State Failures
- Invalid step → Marked ERROR
- Corrupted plan → Logged with HIGH severity

### Example

```python
from ai_travel_agent.agents.nodes.executor_tracked import executor_with_tracking
from ai_travel_agent.tools.tracked_registry import TrackedToolRegistry

# Use in graph
def build_app(tools, llm, metrics):
    # Wrap tools
    tracked_tools = TrackedToolRegistry(tools)
    
    # Create executor node
    def executor_node(state):
        return executor_with_tracking(
            state,
            tools=tracked_tools,
            llm=llm,
            metrics=metrics,
        )
    
    graph.add_node("executor", executor_node)
```

---

## Module Functions

### Global Tracker Management

#### set_failure_tracker

Set global failure tracker instance.

```python
from ai_travel_agent.observability.failure_tracker import set_failure_tracker

def set_failure_tracker(tracker: FailureTracker | None) -> None
```

**Example:**
```python
tracker = FailureTracker(...)
set_failure_tracker(tracker)
```

#### get_failure_tracker

Get global failure tracker instance.

```python
from ai_travel_agent.observability.failure_tracker import get_failure_tracker

def get_failure_tracker() -> FailureTracker | None
```

**Returns:**
- FailureTracker or None if not set

**Example:**
```python
tracker = get_failure_tracker()
if tracker:
    summary = tracker.get_summary()
```

---

## Complete Example

```python
from pathlib import Path
from ai_travel_agent.observability.failure_tracker import (
    FailureTracker,
    FailureCategory,
    FailureSeverity,
    set_failure_tracker,
    get_failure_tracker,
)
from ai_travel_agent.observability.failure_visualizer import (
    display_failure_report,
    FailureVisualizer,
)
from ai_travel_agent.tools.tracked_registry import TrackedToolRegistry

# Setup
run_id = "run-001"
tracker = FailureTracker(
    run_id=run_id,
    user_id="user-1",
    runtime_dir=Path("runtime"),
)
set_failure_tracker(tracker)

# Wrap tools
base_tools = build_tools()
tracked_tools = TrackedToolRegistry(base_tools)

# Simulate failure
try:
    # This will fail and be tracked
    result = tracked_tools.call(
        "weather_summary",
        run_id=run_id,
        user_id="user-1",
        step_id="step-1",
        destination="Paris",
    )
except Exception as e:
    pass  # Already recorded

# View results
tracker = get_failure_tracker()
summary = tracker.get_summary()
print(f"Failures: {summary['total_failures']}")
print(f"Recovery rate: {summary['recovery_rate']:.1f}%")

# Display report
visualizer = FailureVisualizer()
visualizer.print_summary(summary)
visualizer.print_failure_timeline([f.to_dict() for f in tracker.failures])

# Save detailed report
display_failure_report(
    Path(f"runtime/logs/failures_{run_id}.jsonl"),
    verbose=True,
)
```

---

## Quick Reference

| Task | Code |
|------|------|
| Create tracker | `FailureTracker(run_id, user_id, runtime_dir)` |
| Set global | `set_failure_tracker(tracker)` |
| Get global | `get_failure_tracker()` |
| Record failure | `tracker.record_failure(category, severity, ...)` |
| Mark recovered | `tracker.mark_recovered(failure, action)` |
| Get summary | `tracker.get_summary()` |
| Generate report | `tracker.generate_report()` |
| Display single | `visualizer.print_failure_record(dict)` |
| Display timeline | `visualizer.print_failure_timeline(list)` |
| Display summary | `visualizer.print_summary(dict)` |
| Load JSONL log | `load_failure_log(path)` |
| Full report | `display_failure_report(path, verbose=True)` |

---

For more information, see:
- `FAILURE_TRACKING_GUIDE.md` - Usage guide
- `INTEGRATION_GUIDE.md` - Integration instructions
- Source code files for implementation details
