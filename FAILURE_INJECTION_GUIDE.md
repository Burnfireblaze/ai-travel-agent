# Failure Injection Guide for AI Travel Agent

This guide explains how to inject failures at various points in the system for testing resilience, error handling, and evaluation criteria.

---

## 1. **LLM Failures** (`ai_travel_agent/llm.py`)

### Scenario: LLM service unavailable
**Impact**: Intent parsing fails, synthesis fails → plan incomplete or unclear

**Injection Methods**:

a) **Network Failure Simulation** (Mock Ollama unavailable)
```python
# In llm.py, modify invoke_text():
import random
if random.random() < 0.5:  # 50% failure rate
    raise ConnectionError("Ollama connection refused (injected)")
```

b) **Timeout Simulation**
```python
# Add to invoke_text():
time.sleep(15)  # Force timeout (default LangChain timeout is 10s)
```

c) **Malformed Response**
```python
# Force LLM to return invalid JSON when parsing constraints
# Modify intent_parser.py to receive garbage response
```

**Expected Outcome**:
- `needs_user_input=True` (ask for clarification)
- If synthesis fails: `final_answer` is empty → evaluation fails hard gate
- Metrics: `llm_errors` counter increments

---

## 2. **Tool Failures** (`ai_travel_agent/tools/` and `ai_travel_agent/agents/nodes/executor.py`)

### Scenario A: Tool network timeout
**Impact**: Step marked as `blocked`, plan incomplete

**Injection**:
```python
# In tools/weather.py, add to _http_get_json():
import socket
socket.timeout("Simulated timeout in weather API")
```

**Expected Outcome**:
- Tool execution catches exception
- `plan[idx]["status"] = "blocked"`
- Run continues with other steps
- Metrics: `tool_errors` and `tool_latency_ms` recorded

### Scenario B: Tool returns invalid data
**Impact**: Downstream synthesis receives garbage

**Injection** (modify any tool return):
```python
def flights_search_links(...) -> Mapping[str, Any]:
    return {
        "summary": "Invalid structure",
        "links": "NOT_A_LIST",  # Violates schema
        "prices": "$999"  # Should be stripped by responder
    }
```

**Expected Outcome**:
- Executor handles gracefully (coerces to list/dict)
- Links validation fails in `evaluation.py`
- `hard_gate["valid_links"]` → False

### Scenario C: Tool missing from registry
**Impact**: Executor crashes during tool call

**Injection** (in `graph.py` `build_tools()`):
```python
# Comment out registration:
# reg.register("flights_search_links", flights_search_links)
```

**Expected Outcome**:
- `executor()` catches `KeyError` from `tools.call()`
- Step marked `blocked`
- Error logged with `event="tool_error"`

### Scenario D: Memory retrieval failure
**Impact**: Context-grounding lost, agent has less information

**Injection** (in `memory/store.py`):
```python
def search(...):
    raise chromadb.errors.ChromaError("Chroma disconnected")
```

**Expected Outcome**:
- `context_controller` catches exception
- `context_hits` remains empty
- Agent proceeds with minimal context
- May affect coherence/relevance scores in evaluation

---

## 3. **Intent Parsing Failures** (`ai_travel_agent/agents/nodes/intent_parser.py`)

### Scenario A: Missing required constraints
**Impact**: Agent asks for clarification, pauses flow

**Injection** (force LLM to return incomplete JSON):
```python
# LLM returns: {"origin": "NYC"}  # Missing destination, dates
# intent_parser detects missing fields → sets needs_user_input=True
```

**Expected Outcome**:
- Graph edge routes to `END` (pause)
- CLI prompts: "Please provide: destination, start_date, end_date"
- Run continues on clarification input

### Scenario B: Invalid date format
**Impact**: Constraints have unparseable dates → downstream nodes fail

**Injection**:
```python
# LLM returns: {"start_date": "tomorrow"}  # Not ISO format
```

**Expected Outcome**:
- Pydantic validation catches it (if strict)
- Or causes issues in weather/ICS export
- Evaluation: `hard_gate["valid_constraints"]` fails

---

## 4. **Plan Orchestration Failures** (`ai_travel_agent/agents/nodes/orchestrator.py`)

### Scenario A: Infinite loop (max iterations exceeded)
**Impact**: Agent loops forever without converging

**Injection** (in `graph.py`):
```python
# Reduce max_iters to trigger boundary condition:
fn=lambda s: orchestrator(s, max_iters=2)  # Too low
```

**Expected Outcome**:
- After 2 iterations, `termination_reason="max_iters"`
- Incomplete plan marked `pending`
- Evaluation: `hard_gate["completeness"]` may fail
- Metrics: `loop_iterations` shows early termination

### Scenario B: Step in invalid state
**Impact**: Orchestrator confused about what to do next

**Injection** (modify state between nodes):
```python
# All steps in plan are "pending" (orchestrator assigns, but executor doesn't update):
# plan = [{"id": "1", "status": "pending"}, ...]
```

**Expected Outcome**:
- Orchestrator selects same step repeatedly
- Max iterations kicks in
- Error logged: "All steps pending after orchestration"

---

## 5. **Evaluation Failures** (`ai_travel_agent/evaluation.py`)

### Hard Gates (must pass):

#### Gate A: No fabricated prices
**Injection** (force responder to miss price cleanup):
```python
# final_answer includes: "Flight costs $599"
# Responder should strip with _PRICE_RE but fails
```

**Expected Outcome**:
- `evaluation.hard_gates["no_fabricated_prices"] = False`
- `overall_status = "failed"` even if output exists
- User sees evaluation warning

#### Gate B: Valid links
**Injection** (executor returns malformed links):
```python
# tool_results = [{"links": [{"url": "not a url"}, ...]}]
```

**Expected Outcome**:
- `_links_valid()` → False
- `hard_gates["valid_links"] = False`
- Run marked failed

#### Gate C: Valid ICS export
**Injection** (in `export_ics.py`):
```python
# Calendar write fails due to disk space:
ics_path.write_text(...)  # PermissionError
```

**Expected Outcome**:
- Exception caught
- `ics_path = ""`, `ics_event_count = 0`
- `hard_gates["valid_ics"] = False`
- Metrics: `ics_export_failed` increments

#### Gate D: Safety disclaimer present
**Injection** (force responder to skip disclaimer):
```python
# final_answer missing disclaimer line
```

**Expected Outcome**:
- `hard_gates["has_disclaimer"] = False`
- `overall_status = "failed"`

### Rubric Scores (0–5):

**Inject low scores** by creating edge cases:

| Rubric | Failure Case | Injection |
|--------|-------------|-----------|
| Relevance | Interests ignored | Remove interests from synthesis prompt |
| Feasibility | Impossible timeline | Set 1-day trip to 5-city tour |
| Completeness | Missing sections | Executor returns synthesis without all required sections |
| Specificity | No times/locations | LLM returns generic summary without details |
| Coherence | Mismatched dates | Dates in constraints don't match final answer |

**Example Injection**:
```python
# Incoherence: Set start_date but answer doesn't include it
state["constraints"]["start_date"] = "2026-03-01"
state["final_answer"] = "Great trip! (no dates mentioned)"
# _coherence_score() subtracts 1.0 per missing date field
```

---

## 6. **Memory Failures** (`ai_travel_agent/memory/store.py`)

### Scenario A: Persistent storage corrupted
**Impact**: User preferences lost

**Injection**:
```bash
# Delete chroma_persistent directory mid-run:
rm -rf ./data/chroma_persistent
```

**Expected Outcome**:
- MemoryStore tries to recover
- Session memory still works (ephemeral)
- `context_hits` only from session
- Next run starts fresh (no user memory)

### Scenario B: Embedding function unavailable
**Impact**: Vector search fails silently

**Injection** (in `memory/embeddings.py`):
```python
def build_embedding_function(...):
    raise ImportError("sentence-transformers not installed")
    # Falls back to deterministic hash embeddings
```

**Expected Outcome**:
- Memory still stores but with weaker embeddings
- Retrieval less accurate
- No hard failure (graceful degradation)

---

## 7. **Export Failures** (`ai_travel_agent/agents/nodes/export_ics.py`)

### Scenario A: Invalid date range
**Impact**: ICS export returns empty calendar

**Injection**:
```python
# state["itinerary_day_titles"] = []  # Empty itinerary
# ICS has no events → hard gate fails
```

### Scenario B: Disk write permission denied
**Impact**: Cannot save artifact

**Injection**:
```bash
chmod 444 ./runtime/artifacts  # Read-only
```

**Expected Outcome**:
- Export node catches `PermissionError`
- `ics_path = ""` (empty)
- Evaluation: `hard_gate["valid_ics"] = False`

---

## 8. **State Corruption Failures** (`ai_travel_agent/agents/state.py`)

### Scenario: Circular state updates
**Impact**: State gets stuck in infinite loop

**Injection** (in a node):
```python
# Orchestrator never marks steps done:
def orchestrator(state):
    # Intentionally never update plan[idx]["status"]
    return state  # State unchanged
```

**Expected Outcome**:
- Same step selected forever
- Max iterations triggers
- `termination_reason = "max_iters"`

---

## 9. **Graph Routing Failures** (`ai_travel_agent/graph.py`)

### Scenario: Conditional edge logic broken
**Impact**: Graph takes wrong path

**Injection**:
```python
def _intent_route(state):
    # Always return "planner" even if needs_user_input=True
    return "planner"  # Should check needs_user_input
```

**Expected Outcome**:
- Agent proceeds without asking clarifying questions
- Partial constraints → plan is incomplete
- Evaluation: `hard_gate["complete_constraints"] = False`

---

## 10. **Logging/Metrics Failures** (`ai_travel_agent/observability/`)

### Scenario: Logging fails silently
**Impact**: No observability into run

**Injection** (in `logger.py`):
```python
def log_event(...):
    raise IOError("Cannot write to log file")
    # Should be caught and re-raised or ignored
```

**Expected Outcome**:
- Run may continue (if caught)
- Or crashes (if uncaught)
- Metrics still collected in memory

### Scenario: Metrics disk full
**Impact**: Metrics not persisted

**Injection**:
```bash
# Fill /tmp (where runtime files go):
dd if=/dev/zero of=/tmp/fillup bs=1M count=5000
```

**Expected Outcome**:
- Metrics collected in memory
- Write to `metrics.jsonl` fails
- Metrics lost after process exits

---

## **Testing Failures Programmatically**

### Using dependency injection:

```python
# tests/test_failures.py
import pytest
from unittest.mock import patch, MagicMock

def test_llm_timeout():
    with patch('ai_travel_agent.llm.LLMClient.invoke_text') as mock_llm:
        mock_llm.side_effect = TimeoutError("LLM timeout")
        # Run agent, verify error handling
        
def test_tool_returns_invalid_json():
    with patch('ai_travel_agent.tools.flights_search_links') as mock_tool:
        mock_tool.return_value = {"links": "not_a_list"}
        # Run agent, verify executor coerces to list

def test_memory_unavailable():
    with patch('ai_travel_agent.memory.MemoryStore.search') as mock_search:
        mock_search.side_effect = Exception("Chroma down")
        # Run agent, verify graceful fallback
```

---

## **Failure Categories & Severity**

| Category | Examples | Severity | Handler |
|----------|----------|----------|---------|
| **Transient** | Network timeout, temporary service down | Medium | Retry logic / graceful degradation |
| **Structural** | Invalid JSON, missing required field | High | Validation + user clarification |
| **Data** | Corrupted memory, invalid dates | High | Evaluation hard gates |
| **Resource** | Disk full, out of memory | Critical | Early termination |
| **Logic** | Wrong routing, infinite loop | Critical | Loop guards + state validation |

---

## **Monitoring Failures**

Check these after injecting failures:

1. **Logs** (`runtime/logs/app.jsonl`):
   - Search for `"level": 40` (ERROR)
   - Check `"event": "tool_error"`, `"llm_error"`

2. **Metrics** (`runtime/metrics/metrics.json`):
   - `counters.tool_errors`, `counters.llm_errors`
   - `evaluation.overall_status` (should be "failed")
   - `termination_reason` (should be "max_iters" or error-based)

3. **Evaluation**:
   - `hard_gates: {key: False}` shows which gates failed
   - `overall_status: "failed"` if any gate fails

4. **CLI Output**:
   - Check `current_node` and `current_step_index`
   - Look for repeated steps (indicates loop)
   - Check `eval_status` at end

---

## **Best Practices for Chaos Testing**

1. **Inject one failure at a time** to isolate behavior
2. **Vary injection probability** (5%, 50%, 100%) to test retries
3. **Monitor logs + metrics** to verify detection + response
4. **Validate evaluation** changes based on failure type
5. **Test with different constraints** (missing dates, unclear destination, etc.)
6. **Use fixtures** to reset state between test runs

