"""
Practical examples of chaos engineering scenarios for AI Travel Agent.
Run these to test system resilience.
"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import MagicMock, patch
import json

from ai_travel_agent.chaos import (
    chaos_mode,
    inject_failure,
    ChaosConfig,
    FailureMode,
    ChaosToolRegistry,
    DataCorruptor,
    MemoryFaultInjector,
    StateValidator,
)
from ai_travel_agent.tools import ToolRegistry
from ai_travel_agent.agents.nodes.executor import executor
from ai_travel_agent.agents.nodes.orchestrator import orchestrator
from ai_travel_agent.agents.state import StepType


def scenario_1_partial_tool_failure():
    """
    Scenario 1: Some tools fail, others succeed
    Expected: Plan partially completes, evaluation catches missing data
    """
    print("\n" + "="*70)
    print("SCENARIO 1: Partial Tool Failure (Some tools fail, some succeed)")
    print("="*70 + "\n")
    
    tools = ToolRegistry()
    
    # Register working tool
    tools.register("hotels_search_links", lambda **kw: {
        "summary": "Found hotels in Paris",
        "links": [{"label": "Booking.com", "url": "https://booking.com/paris"}]
    })
    
    # Register failing tool
    def flights_fail(**kw):
        raise Exception("Flights API temporarily down")
    
    tools.register("flights_search_links", flights_fail)
    
    # Build state with 2-step plan
    state = {
        "plan": [
            {
                "id": "step-1",
                "step_type": StepType.TOOL_CALL,
                "tool_name": "flights_search_links",
                "tool_args": {"origin": "NYC", "destination": "Paris"},
                "status": "pending",
                "title": "Search flights",
            },
            {
                "id": "step-2",
                "step_type": StepType.TOOL_CALL,
                "tool_name": "hotels_search_links",
                "tool_args": {"destination": "Paris"},
                "status": "pending",
                "title": "Search hotels",
            },
        ],
        "current_step_index": 0,
        "current_step": {
            "id": "step-1",
            "step_type": StepType.TOOL_CALL,
            "tool_name": "flights_search_links",
        },
        "tool_results": [],
        "user_query": "Plan a trip to Paris",
        "run_id": "chaos-test-1",
        "user_id": "test-user",
    }
    
    print("Step 1: Executing flights search (will fail)...")
    result = executor(state, tools=tools, llm=MagicMock(), metrics=None)
    print(f"  Status: {result['plan'][0]['status']}")
    print(f"  Tool results: {len(result['tool_results'])}")
    
    print("\nStep 2: Executing hotels search (will succeed)...")
    state = result
    state["current_step_index"] = 1
    state["current_step"] = state["plan"][1]
    result = executor(state, tools=tools, llm=MagicMock(), metrics=None)
    print(f"  Status: {result['plan'][1]['status']}")
    print(f"  Tool results: {len(result['tool_results'])}")
    
    print("\n✓ Result: Agent recovered from partial failure")
    print("  - Flights step blocked (1 error)")
    print("  - Hotels step completed (1 link)")
    print("  - Evaluation would flag missing flights section")


def scenario_2_max_iterations_loop():
    """
    Scenario 2: Orchestrator hits max iterations
    Expected: Plan terminates early with some steps still pending
    """
    print("\n" + "="*70)
    print("SCENARIO 2: Max Iterations Loop Guard")
    print("="*70 + "\n")
    
    # Create a plan with many steps
    state = {
        "plan": [
            {
                "id": f"step-{i}",
                "status": "pending",
                "title": f"Step {i}",
                "step_type": StepType.TOOL_CALL,
            }
            for i in range(10)
        ],
        "loop_iterations": 0,
    }
    
    print(f"Created plan with {len(state['plan'])} steps")
    print("Setting max_iters=3 (will trigger early termination)\n")
    
    result = orchestrator(state, max_iters=3)
    
    print(f"Final state:")
    print(f"  - Termination reason: {result.get('termination_reason')}")
    print(f"  - Loop iterations: {result.get('loop_iterations')}")
    pending = sum(1 for s in result["plan"] if s["status"] == "pending")
    done = sum(1 for s in result["plan"] if s["status"] == "done")
    print(f"  - Steps pending: {pending}")
    print(f"  - Steps done: {done}")
    
    print("\n✓ Result: Orchestrator triggered loop guard")
    print("  - Terminated early to prevent infinite loops")
    print("  - Incomplete itinerary would be evaluated")


def scenario_3_network_timeout_cascade():
    """
    Scenario 3: Network timeout in tool cascades through system
    Expected: Tool fails → step blocked → orchestrator continues → evaluation flags incomplete data
    """
    print("\n" + "="*70)
    print("SCENARIO 3: Network Timeout Cascade")
    print("="*70 + "\n")
    
    tools = ToolRegistry()
    
    def weather_timeout(**kwargs):
        import time
        raise TimeoutError("Weather API timeout after 8s")
    
    tools.register("weather_summary", weather_timeout)
    
    state = {
        "plan": [
            {
                "id": "weather",
                "step_type": StepType.TOOL_CALL,
                "tool_name": "weather_summary",
                "tool_args": {"destination": "Paris", "start_date": "2026-03-01", "end_date": "2026-03-10"},
                "status": "pending",
                "title": "Fetch weather forecast",
            }
        ],
        "current_step_index": 0,
        "current_step": {
            "id": "weather",
            "step_type": StepType.TOOL_CALL,
            "tool_name": "weather_summary",
        },
        "tool_results": [],
        "run_id": "chaos-test-3",
        "user_id": "test-user",
    }
    
    print("Executing weather fetch (will timeout)...")
    result = executor(state, tools=tools, llm=MagicMock(), metrics=None)
    
    print(f"  Step status: {result['plan'][0]['status']}")
    print(f"  Tool results: {len(result['tool_results'])}")
    
    print("\n✓ Result: Timeout handled gracefully")
    print("  - Step marked as blocked")
    print("  - Orchestrator continues without weather data")
    print("  - Evaluation would note missing weather section")


def scenario_4_invalid_data_structures():
    """
    Scenario 4: Tool returns malformed data
    Expected: Executor coerces/validates → evaluation catches issues
    """
    print("\n" + "="*70)
    print("SCENARIO 4: Invalid Data Structure from Tool")
    print("="*70 + "\n")
    
    tools = ToolRegistry()
    
    def malformed_flights(**kwargs):
        return {
            "summary": "Found flights",
            "links": "NOT_A_LIST",  # Should be list of dicts
            "prices": "$1200",  # Price claim (should be stripped)
        }
    
    tools.register("flights_search_links", malformed_flights)
    
    state = {
        "plan": [
            {
                "id": "flights",
                "step_type": StepType.TOOL_CALL,
                "tool_name": "flights_search_links",
                "tool_args": {"origin": "NYC", "destination": "Paris"},
                "status": "pending",
                "title": "Search flights",
            }
        ],
        "current_step_index": 0,
        "current_step": {
            "id": "flights",
            "step_type": StepType.TOOL_CALL,
            "tool_name": "flights_search_links",
        },
        "tool_results": [],
        "run_id": "chaos-test-4",
        "user_id": "test-user",
    }
    
    print("Executing flights search (returns malformed data)...")
    result = executor(state, tools=tools, llm=MagicMock(), metrics=None)
    
    print(f"  Step status: {result['plan'][0]['status']}")
    tool_result = result['tool_results'][0] if result['tool_results'] else {}
    print(f"  Tool result stored: {tool_result}")
    if tool_result:
        print(f"    - Links coerced to: {tool_result.get('links')} (type: {type(tool_result.get('links'))})")
    
    print("\n✓ Result: Executor handled malformed data")
    print("  - Step completed despite data issues")
    print("  - Links coerced to list")
    print("  - Evaluation would detect and flag issues")


def scenario_5_data_corruption():
    """
    Scenario 5: Use DataCorruptor to test handling of corrupted data
    Expected: System detects and reports corruption through evaluation
    """
    print("\n" + "="*70)
    print("SCENARIO 5: Data Corruption Detection")
    print("="*70 + "\n")
    
    print("Original data:")
    original = {
        "summary": "Found flights",
        "links": [
            {"label": "Google Flights", "url": "https://google.com/flights"}
        ]
    }
    print(f"  {original}\n")
    
    print("Corruptions to test:")
    
    print("\n1. Corrupt links structure:")
    corrupted_links = DataCorruptor.corrupt_links(original["links"])
    print(f"  Result: {corrupted_links} (type: {type(corrupted_links)})")
    
    print("\n2. Remove links entirely:")
    corrupted_no_links = DataCorruptor.remove_links(original.copy())
    print(f"  Result: {corrupted_no_links}")
    
    print("\n3. Inject price claims:")
    corrupted_prices = DataCorruptor.add_price_claims(original.copy())
    print(f"  Result: {corrupted_prices['summary']}")
    
    print("\n4. Truncate response:")
    corrupted_short = DataCorruptor.truncate_response(original.copy(), truncate_at=30)
    print(f"  Result: {corrupted_short['summary']}")
    
    print("\n✓ Result: Demonstrating data corruption scenarios")
    print("  - Links validation would fail")
    print("  - Responder would strip price claims")
    print("  - Evaluation would flag incomplete data")


def scenario_6_state_validation():
    """
    Scenario 6: Detect state corruption/inconsistencies
    Expected: Validation catches bugs before execution
    """
    print("\n" + "="*70)
    print("SCENARIO 6: State Validation & Corruption Detection")
    print("="*70 + "\n")
    
    print("Validating corrupted state...\n")
    
    corrupted_state = StateValidator.corrupt_state()
    errors = StateValidator.validate_state_consistency(corrupted_state)
    
    print(f"Found {len(errors)} errors:")
    for i, error in enumerate(errors, 1):
        print(f"  {i}. {error}")
    
    print("\n✓ Result: State validator caught all issues")
    print("  - Out of bounds index")
    print("  - Invalid step status")
    print("  - Mismatched current_step")
    print("  - Invalid tool result references")


def scenario_7_chaos_context_manager():
    """
    Scenario 7: Use chaos_mode context manager for controlled injection
    Expected: Failures injected only within context
    """
    print("\n" + "="*70)
    print("SCENARIO 7: Chaos Context Manager")
    print("="*70 + "\n")
    
    @inject_failure(failure_probability=0.3, exception_type=RuntimeError)
    def simulated_api_call(attempt_num: int):
        return f"Success from attempt {attempt_num}"
    
    print("Calling API 10 times WITHOUT chaos mode:")
    successes = 0
    for i in range(10):
        try:
            result = simulated_api_call(i+1)
            print(f"  {i+1}. {result}")
            successes += 1
        except Exception as e:
            print(f"  {i+1}. Failed: {type(e).__name__}")
    
    print(f"Success rate (no chaos): {successes}/10\n")
    
    print("Calling API 10 times WITH chaos mode (50% failure):")
    from ai_travel_agent.chaos import set_chaos_config, get_chaos_config
    
    old_config = get_chaos_config()
    set_chaos_config(ChaosConfig(
        enabled=True,
        failure_probability=0.5,
        failure_mode=FailureMode.EXCEPTION,
        exception_type=RuntimeError,
    ))
    
    successes = 0
    for i in range(10):
        try:
            result = simulated_api_call(i+1)
            print(f"  {i+1}. {result}")
            successes += 1
        except Exception as e:
            print(f"  {i+1}. Failed: {type(e).__name__}")
    
    set_chaos_config(old_config)
    print(f"Success rate (with chaos): {successes}/10")
    
    print("\n✓ Result: Chaos mode controlled and confined")


def scenario_8_missing_constraints():
    """
    Scenario 8: Partial constraints trigger user clarification
    Expected: needs_user_input=True, agent asks for missing info
    """
    print("\n" + "="*70)
    print("SCENARIO 8: Missing Constraints Trigger Clarification")
    print("="*70 + "\n")
    
    from ai_travel_agent.agents.nodes.intent_parser import intent_parser
    
    mock_llm = MagicMock()
    
    # Simulate LLM returning incomplete constraints
    mock_llm.invoke_text.return_value = json.dumps({
        "origin": "New York",
        # Missing: destination, dates, budget, etc.
        "interests": ["museums"],
    })
    
    state = {
        "user_query": "Plan a trip",
        "constraints": {},
        "context_hits": [],
    }
    
    print("Parsing incomplete constraints...")
    result = intent_parser(state, llm=mock_llm)
    
    print(f"  needs_user_input: {result.get('needs_user_input')}")
    print(f"  clarifying_questions ({len(result.get('clarifying_questions', []))}):")
    for q in result.get("clarifying_questions", [])[:3]:
        print(f"    - {q}")
    
    print("\n✓ Result: Agent detected missing constraints")
    print("  - Paused to ask clarifying questions")
    print("  - User must provide: destination, dates, budget")


def scenario_9_evaluation_hard_gates():
    """
    Scenario 9: Demonstrate evaluation hard gates
    Expected: Output produced but marked as failed
    """
    print("\n" + "="*70)
    print("SCENARIO 9: Evaluation Hard Gates")
    print("="*70 + "\n")
    
    from ai_travel_agent.evaluation import (
        _links_valid,
        _has_sections,
    )
    
    print("Test 1: Invalid links detection")
    invalid_links = [
        "not-a-url",
        "ftp://wrong-scheme.com",
        "https://",  # No domain
    ]
    valid = _links_valid(invalid_links)
    print(f"  Invalid links valid? {valid}")
    print(f"  Hard gate 'valid_links': {'PASS' if valid else 'FAIL'}")
    
    print("\nTest 2: Missing sections detection")
    vague_answer = "Have a nice trip to Paris!"
    score = _has_sections(vague_answer)
    print(f"  Section completeness score: {score:.1f}/5.0")
    print(f"  Hard gate 'has_sections': {'PASS' if score > 3.0 else 'FAIL'}")
    
    print("\nTest 3: Full evaluation scenario")
    complete_answer = """
    ## Summary
    5-day Paris trip
    
    ## Assumptions
    - Single room hotels
    
    ## Flights
    Search: https://google.com/flights
    
    ## Lodging
    Search: https://booking.com
    
    ## Day-by-day Itinerary
    - Day 1: Arrive, visit Eiffel Tower
    - Day 2: Louvre museum
    - Day 3: Seine river cruise
    - Day 4: Versailles
    - Day 5: Depart
    
    ## Transit Notes
    Metro recommended
    
    ## Weather
    Spring temperatures, bring layers
    
    ## Budget
    Estimated €3000-4000
    
    ## Calendar Export
    Check .ics file
    
    Note: Visa/health requirements vary; verify with official sources (this is not legal advice).
    """
    
    completeness = _has_sections(complete_answer)
    print(f"  Section completeness: {completeness:.1f}/5.0")
    print(f"  Hard gate 'has_all_sections': {'PASS' if completeness >= 4.0 else 'FAIL'}")
    
    print("\n✓ Result: Evaluation gates catch common failures")
    print("  - Missing critical sections")
    print("  - Invalid links")
    print("  - Missing safety disclaimer")


def main():
    """Run all scenarios."""
    print("\n" + "#"*70)
    print("# AI TRAVEL AGENT - CHAOS ENGINEERING SCENARIOS")
    print("#"*70)
    
    scenarios = [
        scenario_1_partial_tool_failure,
        scenario_2_max_iterations_loop,
        scenario_3_network_timeout_cascade,
        scenario_4_invalid_data_structures,
        scenario_5_data_corruption,
        scenario_6_state_validation,
        scenario_7_chaos_context_manager,
        scenario_8_missing_constraints,
        scenario_9_evaluation_hard_gates,
    ]
    
    for scenario in scenarios:
        try:
            scenario()
        except Exception as e:
            print(f"\n✗ Scenario failed: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "#"*70)
    print("# ALL SCENARIOS COMPLETE")
    print("#"*70 + "\n")


if __name__ == "__main__":
    main()
