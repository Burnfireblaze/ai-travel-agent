# Failure Injection Quick Reference

## 10-Second Cheat Sheet

### Run Examples
```bash
python examples/chaos_scenarios.py      # 9 scenarios with expected outcomes
pytest tests/test_failures.py -v         # Full test suite
pytest tests/test_failures.py -k "llm"  # Filter by keyword
```

---

## Common Injections

### Inject Tool Timeout
```python
from ai_travel_agent.chaos import ChaosToolRegistry, ChaosConfig, FailureMode

chaos_tools = ChaosToolRegistry(base_registry)
chaos_tools.set_tool_failure("weather_summary", ChaosConfig(
    enabled=True,
    failure_probability=0.5,  # 50% of calls timeout
    failure_mode=FailureMode.TIMEOUT,
    exception_type=TimeoutError,
))

result = chaos_tools.call("weather_summary", destination="Paris", ...)
```

### Inject LLM Failure
```python
from unittest.mock import MagicMock

mock_llm = MagicMock()
mock_llm.invoke_text.side_effect = TimeoutError("LLM timeout")

# Now any node calling llm.invoke_text() will fail
```

### Inject Malformed Data
```python
from ai_travel_agent.chaos import DataCorruptor

tool_result = tools.call("flights_search_links", ...)
corrupted = DataCorruptor.corrupt_links(tool_result["links"])
# Now links is invalid type (string instead of list)
```

### Inject Missing Constraints
```python
constraints = {"origin": "NYC"}  # Missing destination, dates, etc.
# intent_parser will set needs_user_input=True
```

### Inject Max Iterations
```python
result = orchestrator(state, max_iters=2)  # Trigger loop guard early
# Result: termination_reason="max_iters"
```

### Inject Invalid State
```python
from ai_travel_agent.chaos import StateValidator

bad_state = StateValidator.corrupt_state()
errors = StateValidator.validate_state_consistency(bad_state)
# Detects: out of range index, invalid status, mismatched steps
```

---

## Failure Modes

| Mode | Effect | Use Case |
|------|--------|----------|
| `TIMEOUT` | Raise TimeoutError | API/network slowness |
| `EXCEPTION` | Raise any exception | Service errors |
| `SLOW_RESPONSE` | Add delay | Latency testing |
| `INVALID_DATA` | Malformed JSON | Data validation |
| `PARTIAL_DATA` | Incomplete response | Robustness testing |
| `MALFORMED_RESPONSE` | Parsing errors | Edge case handling |

---

## Expected Outcomes

| Injection | Component | Result | Evaluation Impact |
|-----------|-----------|--------|-------------------|
| Tool timeout | Executor | Step blocked | Missing section |
| LLM fail | Intent parser | needs_user_input=True | Paused |
| Invalid links | Tool result | Executor continues | hard_gate["valid_links"]=False |
| Max iterations | Orchestrator | Incomplete plan | Low completeness score |
| Memory unavailable | Context controller | Empty context | Low relevance |
| Missing disclaimer | Responder | No disclaimer | hard_gate["has_disclaimer"]=False |
| Invalid dates | Intent parser | Constraint error | May ask clarification |
| Disk full | Export ICS | No artifact | hard_gate["valid_ics"]=False |

---

## Test Location Quick Map

```
tests/test_failures.py
├── TestLLMFailures
│   ├── test_llm_timeout
│   ├── test_llm_connection_refused
│   └── test_llm_returns_malformed_json
├── TestToolFailures
│   ├── test_tool_not_registered
│   ├── test_tool_network_timeout
│   ├── test_tool_returns_invalid_data_structure
├── TestIntentParsingFailures
│   ├── test_missing_required_constraints
│   └── test_invalid_date_format
├── TestOrchestratorFailures
│   ├── test_max_iterations_exceeded
│   └── test_all_steps_blocked
├── TestEvaluationFailures
│   ├── test_hard_gate_invalid_links
│   ├── test_hard_gate_missing_sections
│   ├── test_hard_gate_no_disclaimer
│   ├── test_rubric_low_specificity
│   ├── test_rubric_low_coherence
│   └── test_rubric_low_relevance
├── TestMemoryFailures
├── TestExportFailures
├── TestStateCorruptionFailures
└── TestCascadingFailures
    └── test_tool_fails_plan_continues
```

---

## Scenario Quick Map

```
examples/chaos_scenarios.py
├── scenario_1_partial_tool_failure()
├── scenario_2_max_iterations_loop()
├── scenario_3_network_timeout_cascade()
├── scenario_4_invalid_data_structures()
├── scenario_5_data_corruption()
├── scenario_6_state_validation()
├── scenario_7_chaos_context_manager()
├── scenario_8_missing_constraints()
└── scenario_9_evaluation_hard_gates()
```

Run all: `python examples/chaos_scenarios.py`

---

## Chaos Utilities in ai_travel_agent/chaos.py

```python
# Decorators & Context Managers
@inject_failure(failure_probability=0.5, ...)
def my_function(): ...

with chaos_mode(failure_probability=0.5, ...):
    result = run_agent(query)

# Classes
ChaosToolRegistry        # Tool-level failure injection
DataCorruptor           # Generate corrupted data
MemoryFaultInjector     # Memory operation failures
StateValidator          # State consistency checks
ChaosConfig             # Configuration dataclass

# Functions
set_chaos_config()      # Set global chaos config
get_chaos_config()      # Get global chaos config
```

---

## Verify Failures in Output

### Logs (runtime/logs/app.jsonl)
```bash
# View all errors
grep '"level": 40' runtime/logs/app.jsonl | jq .

# View tool errors
grep '"event": "tool_error"' runtime/logs/app.jsonl | jq .

# View specific error
grep 'TimeoutError' runtime/logs/app.jsonl | jq .
```

### Metrics (runtime/metrics/metrics.jsonl)
```bash
# View evaluation result
cat runtime/metrics/metrics.jsonl | jq '.evaluation'

# View error counters
cat runtime/metrics/metrics.jsonl | jq '.counters | {llm_errors, tool_errors}'

# View termination reason
cat runtime/metrics/metrics.jsonl | jq '.termination_reason'
```

### CLI Output
```
✓ Check final eval_status at end
✓ Look for repeated steps (indicates loop)
✓ Note current_node and current_step_index
✓ Verify error logs shown
```

---

## One-Liners

### Test timeout handling
```bash
pytest tests/test_failures.py::TestLLMFailures::test_llm_timeout -v
```

### Test tool failures
```bash
pytest tests/test_failures.py::TestToolFailures -v
```

### Test evaluation gates
```bash
pytest tests/test_failures.py::TestEvaluationFailures -v
```

### Run all scenario demos
```bash
python examples/chaos_scenarios.py
```

### Validate state
```python
from ai_travel_agent.chaos import StateValidator
errors = StateValidator.validate_state_consistency(state)
print(errors)  # See all inconsistencies
```

### Corrupt data
```python
from ai_travel_agent.chaos import DataCorruptor
bad_data = DataCorruptor.add_price_claims(tool_result)
```

### Check tool failure
```python
with pytest.raises(TimeoutError):
    chaos_tools.call("weather_summary", ...)
```

---

## Architecture Overview

```
Request
  ↓
context_controller → (failure: empty context)
  ↓
intent_parser → (failure: needs_user_input)
  ↓
planner
  ↓
orchestrator → (failure: max_iters)
  ↓
executor → (failure: step blocked)
  ↓
evaluate_step
  ↓
responder
  ↓
export_ics → (failure: no artifact)
  ↓
evaluate_final → (failure: hard_gates fail)
  ↓
memory_writer → (failure: context lost)
  ↓
Response + Metrics + Evaluation
```

Each node has natural failure points you can inject at.

---

## Common Patterns

### Pattern 1: Mock + Patch
```python
from unittest.mock import patch
with patch('ai_travel_agent.tools.weather_summary') as mock:
    mock.side_effect = TimeoutError()
    result = executor(state, tools, llm)
    assert result["plan"][0]["status"] == "blocked"
```

### Pattern 2: Decorator
```python
@inject_failure(failure_probability=0.5)
def my_function():
    return "success"
```

### Pattern 3: Context
```python
with chaos_mode(failure_probability=0.5, failure_mode=FailureMode.TIMEOUT):
    for i in range(10):
        try:
            result = agent.run(query)
        except TimeoutError:
            pass  # ~50% should fail
```

### Pattern 4: Tool Registry Wrapper
```python
chaos_tools = ChaosToolRegistry(base_registry)
chaos_tools.set_tool_failure("flights_search_links", config)
result = chaos_tools.call("flights_search_links", ...)
```

---

## Debugging Tips

1. **Enable logs**: Set `--log-level DEBUG`
2. **Check metrics**: `cat runtime/metrics/metrics.jsonl | jq .`
3. **Validate state**: `StateValidator.validate_state_consistency(state)`
4. **Print step status**: `print([s["status"] for s in state["plan"]])`
5. **Check evaluation**: `print(state.get("evaluation"))`
6. **Monitor termination**: `print(state.get("termination_reason"))`

---

## Links

- **Full Guide**: `FAILURE_INJECTION_GUIDE.md`
- **Chaos Guide**: `CHAOS_ENGINEERING.md`
- **Tests**: `tests/test_failures.py`
- **Scenarios**: `examples/chaos_scenarios.py`
- **Source**: `ai_travel_agent/chaos.py`

---

## TLDR

1. Run scenarios: `python examples/chaos_scenarios.py`
2. Run tests: `pytest tests/test_failures.py -v`
3. Use chaos mode: `with chaos_mode(...): ...`
4. Check results: Logs + metrics + evaluation

System handles failures gracefully with clear observable impact. ✓
