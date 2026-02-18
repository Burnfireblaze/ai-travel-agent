# Chaos Engineering & Failure Injection for AI Travel Agent

This guide provides comprehensive methods to inject failures and test system resilience.

## Quick Start

### 1. Run Chaos Scenarios
```bash
python examples/chaos_scenarios.py
```

This demonstrates 9 real-world failure scenarios with expected outcomes.

### 2. Run Failure Tests
```bash
pytest tests/test_failures.py -v
```

Comprehensive test suite with failure injection examples.

### 3. Use Chaos Module Directly
```python
from ai_travel_agent.chaos import chaos_mode, FailureMode

with chaos_mode(failure_probability=0.5, failure_mode=FailureMode.TIMEOUT):
    result = agent.run(query)  # 50% of calls will timeout
```

---

## Failure Injection Points

### **Level 1: LLM Service**
- **Timeout**: LLM service takes too long to respond
- **Connection Error**: Ollama not running or unreachable
- **Malformed Response**: LLM returns invalid JSON

**Impact**: Intent parsing fails, synthesis incomplete

**Test File**: `tests/test_failures.py::TestLLMFailures`

### **Level 2: Tool Execution**
- **Network Timeout**: Tool API timeout (flights, weather, hotels)
- **Connection Refused**: Service unavailable
- **Invalid Data Structure**: Tool returns malformed JSON
- **Missing Required Field**: Tool omits critical data

**Impact**: Step marked as blocked, plan incomplete

**Test File**: `tests/test_failures.py::TestToolFailures`

### **Level 3: Intent Parsing**
- **Incomplete Constraints**: Missing origin, destination, dates
- **Invalid Date Format**: Non-ISO format dates
- **Invalid Enum Values**: Pace not in [relaxed, balanced, packed]

**Impact**: Agent asks for clarification, flow pauses

**Test File**: `tests/test_failures.py::TestIntentParsingFailures`

### **Level 4: Plan Orchestration**
- **Max Iterations**: Loop exceeds safety limit
- **All Steps Blocked**: No executable steps remain
- **State Corruption**: Step status inconsistencies

**Impact**: Incomplete itinerary, evaluation fails

**Test File**: `tests/test_failures.py::TestOrchestratorFailures`

### **Level 5: Evaluation**
- **Hard Gates**: Missing sections, invalid links, no disclaimer
- **Rubric Scores**: Low relevance, feasibility, specificity

**Impact**: Run marked as "failed" despite output

**Test File**: `tests/test_failures.py::TestEvaluationFailures`

### **Level 6: Memory & Storage**
- **Chroma Unavailable**: Database connection lost
- **Disk Space**: Cannot write artifacts
- **Embedding Failure**: Cannot generate embeddings

**Impact**: Context lost, exports fail

**Test File**: `tests/test_failures.py::TestMemoryFailures`

### **Level 7: Export**
- **Empty Itinerary**: No days to export
- **Invalid Dates**: Unparseable date formats
- **Disk Permission**: Cannot write ICS file

**Impact**: No calendar artifact

**Test File**: `tests/test_failures.py::TestExportFailures`

---

## Chaos Tools & Utilities

### **chaos_mode** Context Manager
Temporarily enable chaos injection with controlled probability.

```python
from ai_travel_agent.chaos import chaos_mode, FailureMode

# 50% timeout failure rate
with chaos_mode(
    failure_probability=0.5,
    failure_mode=FailureMode.TIMEOUT,
    exception_type=TimeoutError
):
    result = run_agent(query)
```

### **inject_failure** Decorator
Add failure injection to any function.

```python
from ai_travel_agent.chaos import inject_failure, FailureMode

@inject_failure(
    failure_probability=0.1,
    failure_mode=FailureMode.SLOW_RESPONSE,
    latency_multiplier=5.0
)
def fetch_weather():
    return {"temp": "70°F"}
```

### **ChaosToolRegistry**
Wrapper around tool registry for per-tool failure injection.

```python
from ai_travel_agent.chaos import ChaosToolRegistry, ChaosConfig, FailureMode

chaos_tools = ChaosToolRegistry(base_registry)

# Make flights tool fail 20% of the time
chaos_tools.set_tool_failure(
    "flights_search_links",
    ChaosConfig(
        enabled=True,
        failure_probability=0.2,
        failure_mode=FailureMode.TIMEOUT,
    )
)

result = chaos_tools.call("flights_search_links", origin="NYC", destination="LAX")
```

### **DataCorruptor**
Generate corrupted data for testing validation.

```python
from ai_travel_agent.chaos import DataCorruptor

# Various corruption methods
DataCorruptor.corrupt_links(links)           # Make links invalid type
DataCorruptor.remove_links(data)             # Remove links entirely
DataCorruptor.add_price_claims(data)         # Inject price claims
DataCorruptor.truncate_response(data)        # Shorten response
DataCorruptor.inject_invalid_dates(constraints)
DataCorruptor.remove_required_fields(constraints)
```

### **MemoryFaultInjector**
Inject failures into memory operations.

```python
from ai_travel_agent.chaos import MemoryFaultInjector

injector = MemoryFaultInjector(memory_store)

# Make all searches fail
injector.enable_search_failure()

# Add retrieval delay
injector.set_retrieval_delay(seconds=2.0)

result = injector.search(query="museums")  # Will fail or be delayed
```

### **StateValidator**
Validate state consistency and detect corruption.

```python
from ai_travel_agent.chaos import StateValidator

# Check for inconsistencies
errors = StateValidator.validate_state_consistency(state)

# Create deliberately corrupted state
bad_state = StateValidator.corrupt_state()
```

---

## Scenario Examples

### Scenario 1: Partial Tool Failure
**What**: One tool fails, others succeed  
**Test**: `scenario_1_partial_tool_failure()`  
**Expected**: Step marked blocked, plan continues partially

```
Flights search: BLOCKED (API timeout)
Hotels search: COMPLETED (got links)
Result: Incomplete itinerary, evaluation flags missing flights
```

### Scenario 2: Max Iterations Loop Guard
**What**: Orchestrator exceeds iteration limit  
**Test**: `scenario_2_max_iterations_loop()`  
**Expected**: Termination early, incomplete plan

```
Plan: 10 steps
Max iterations: 3
Result: After 3 loops, terminate with ~7 steps pending
```

### Scenario 3: Network Timeout Cascade
**What**: Weather API times out  
**Test**: `scenario_3_network_timeout_cascade()`  
**Expected**: Step blocked, orchestrator continues

```
Weather fetch: TimeoutError("API timeout after 8s")
→ Step marked as blocked
→ No weather data in final answer
→ Evaluation: "needs_work" (missing weather section)
```

### Scenario 4: Invalid Data Structures
**What**: Tool returns malformed JSON  
**Test**: `scenario_4_invalid_data_structures()`  
**Expected**: Executor coerces, evaluation catches

```
Tool returns: {"links": "NOT_A_LIST"}
Executor: Coerces to []
Evaluation: Links validation fails
Result: Hard gate "valid_links" = False
```

### Scenario 5: Data Corruption
**What**: Use DataCorruptor to test validation  
**Test**: `scenario_5_data_corruption()`  
**Expected**: Each corruption detected

```
Corrupt links → _links_valid() = False
Remove links → Hard gate fails
Inject prices → Responder should strip
Truncate → Specificity score low
```

### Scenario 6: State Validation
**What**: Detect state inconsistencies  
**Test**: `scenario_6_state_validation()`  
**Expected**: All corruption detected

```
Issues found:
- current_step_index out of range
- Invalid step status
- Current step doesn't match plan
- Tool result references unknown step
```

### Scenario 7: Chaos Context Manager
**What**: Inject failures probabilistically within context  
**Test**: `scenario_7_chaos_context_manager()`  
**Expected**: ~50% failure rate within context

```
Without chaos: 10/10 success
With chaos (50%): ~5/10 success
```

### Scenario 8: Missing Constraints
**What**: LLM returns incomplete constraints  
**Test**: `scenario_8_missing_constraints()`  
**Expected**: needs_user_input=True

```
Parsed: {"origin": "NYC", "interests": [...]}
Missing: destination, dates, budget
Result: Agent asks for clarification
```

### Scenario 9: Evaluation Hard Gates
**What**: Test evaluation hard gates and rubrics  
**Test**: `scenario_9_evaluation_hard_gates()`  
**Expected**: Gates detect failures

```
Gate: invalid_links → FAIL (malformed URLs)
Gate: has_sections → FAIL (missing sections)
Gate: has_disclaimer → FAIL (no disclaimer)
Result: overall_status = "failed"
```

---

## Running Tests

### Run all failure tests
```bash
pytest tests/test_failures.py -v
```

### Run specific test class
```bash
pytest tests/test_failures.py::TestLLMFailures -v
```

### Run specific test
```bash
pytest tests/test_failures.py::TestLLMFailures::test_llm_timeout -v
```

### Run with coverage
```bash
pytest tests/test_failures.py --cov=ai_travel_agent --cov-report=html
```

### Run chaos scenarios
```bash
python examples/chaos_scenarios.py
```

---

## Monitoring & Debugging

### Check Logs
```bash
# View errors
grep '"level": 40' runtime/logs/app.jsonl | jq .

# View tool errors
grep '"event": "tool_error"' runtime/logs/app.jsonl | jq .

# View specific run
grep '"run_id": "chaos-test-1"' runtime/logs/app.jsonl | jq .
```

### Check Metrics
```bash
# View evaluation results
cat runtime/metrics/metrics.jsonl | jq '.evaluation'

# View error counters
cat runtime/metrics/metrics.jsonl | jq '.counters'

# View termination reasons
cat runtime/metrics/metrics.jsonl | jq '.termination_reason'
```

### State Validation
```python
from ai_travel_agent.chaos import StateValidator

errors = StateValidator.validate_state_consistency(state)
print(f"State consistency errors: {errors}")
```

---

## Common Injection Patterns

### Pattern 1: Mock + Patch
```python
from unittest.mock import patch, MagicMock

with patch('ai_travel_agent.tools.flights_search_links') as mock:
    mock.side_effect = TimeoutError("API timeout")
    result = executor(state, tools=tools, llm=mock_llm)
    assert result["plan"][0]["status"] == "blocked"
```

### Pattern 2: Chaos Decorator
```python
@inject_failure(failure_probability=0.3, exception_type=RuntimeError)
def flaky_function():
    return "success"

# 30% of calls will raise RuntimeError
```

### Pattern 3: Context Manager
```python
with chaos_mode(failure_probability=0.5, failure_mode=FailureMode.TIMEOUT):
    for i in range(10):
        try:
            result = agent.run(query)
        except TimeoutError:
            pass  # Expected ~5 times
```

### Pattern 4: Selective Tool Failure
```python
chaos_tools = ChaosToolRegistry(base_registry)
chaos_tools.set_tool_failure("weather_summary", timeout_config)
chaos_tools.set_tool_failure("flights_search_links", error_config)

# Only these tools fail, others work normally
```

### Pattern 5: Data Corruption
```python
data = tools.call("flights_search_links", origin="NYC", destination="LAX")
data = DataCorruptor.add_price_claims(data)  # Inject invalid data
# Executor should handle gracefully
```

---

## Best Practices

1. **Test one failure at a time**: Inject isolated failures to understand system behavior
2. **Vary probability**: Test with 10%, 50%, 100% failure rates
3. **Monitor logs + metrics**: Verify failures are detected and reported
4. **Validate evaluation**: Ensure hard gates catch failures appropriately
5. **Test with different constraints**: Empty optional fields, edge case values
6. **Use fixtures**: Reset state between test runs
7. **Separate unit + integration tests**: Unit tests for components, integration for full flow
8. **Document expected outcomes**: Know what should happen before injecting

---

## Extending Chaos System

### Add New Failure Mode
```python
class FailureMode(Enum):
    CUSTOM_FAILURE = "custom_failure"

# In _execute_failure():
elif failure_mode == FailureMode.CUSTOM_FAILURE:
    raise CustomException("Injected custom failure")
```

### Add Tool-Specific Injection
```python
class ChaosToolRegistry:
    def call(self, name, **kwargs):
        if name == "flights_search_links":
            # Custom logic for flights
            pass
        return super().call(name, **kwargs)
```

### Add State Validation Rules
```python
def validate_state_consistency(state):
    errors = []
    # Add custom validation
    if not state.get("user_id"):
        errors.append("Missing user_id in state")
    return errors
```

---

## Troubleshooting

### Q: Test raises exception but not caught
**A**: Ensure try/except or pytest.raises is used:
```python
with pytest.raises(TimeoutError):
    result = executor(state, tools=tools, llm=mock_llm)
```

### Q: Chaos not injecting failures
**A**: Check if chaos is enabled:
```python
from ai_travel_agent.chaos import get_chaos_config
config = get_chaos_config()
print(f"Chaos enabled: {config.enabled}, Probability: {config.failure_probability}")
```

### Q: Random test failures
**A**: Set random seed for reproducibility:
```python
import random
random.seed(42)
```

### Q: State validation errors
**A**: Use StateValidator to detect corruption:
```python
errors = StateValidator.validate_state_consistency(state)
print(errors)  # See what's wrong
```

---

## Files

| File | Purpose |
|------|---------|
| `FAILURE_INJECTION_GUIDE.md` | Comprehensive failure injection documentation |
| `tests/test_failures.py` | Unit tests for failure scenarios |
| `examples/chaos_scenarios.py` | 9 runnable chaos scenarios |
| `ai_travel_agent/chaos.py` | Chaos utilities (decorators, managers, validators) |

---

## Summary

The AI Travel Agent has **robust failure handling** with **observable, measurable responses**:

✓ **Tools fail gracefully** → Steps marked blocked, plan continues  
✓ **LLM fails** → Agent asks for clarification  
✓ **Memory unavailable** → Works with empty context  
✓ **Evaluation gates** → Catch missing sections, invalid data  
✓ **Loop guards** → Prevent infinite iteration  
✓ **State validation** → Detect corruption early  

Use these tools to ensure production resilience!
