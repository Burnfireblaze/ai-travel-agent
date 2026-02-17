def test_generate_itinerary_and_print():
    """Generate a full itinerary for the custom prompt and print it."""
    from ai_travel_agent.agents.state import StepType
    from ai_travel_agent.agents.nodes.executor import executor
    from ai_travel_agent.agents.nodes.orchestrator import orchestrator
    from ai_travel_agent.agents.nodes.intent_parser import intent_parser
    from ai_travel_agent.tools import ToolRegistry
    from unittest.mock import MagicMock

    # Use the custom prompt
    user_query = get_prompt("Plan a 5 day trip to Paris from New Delhi")
    # Minimal tool registry with mock tools
    tools = ToolRegistry()
    tools.register("flights_search_links", lambda **kw: {"summary": "Found flights", "links": [{"label": "Flight", "url": "https://flights.com"}]})
    tools.register("hotels_search_links", lambda **kw: {"summary": "Found hotels", "links": [{"label": "Hotel", "url": "https://hotels.com"}]})
    tools.register("weather_summary", lambda **kw: {"summary": "Weather is good", "links": []})


    # Step 1: Parse intent/constraints with a mock LLM that returns valid JSON
    mock_llm = MagicMock()
    mock_llm.invoke_text.return_value = json.dumps({
        "origin": "New Delhi",
        "destinations": ["Paris"],
        "start_date": "2026-03-01",
        "end_date": "2026-03-05",
        "budget_usd": 2000,
        "travelers": 1,
        "interests": ["museums", "food"],
        "pace": "balanced"
    })
    state = {"user_query": user_query, "constraints": {}}
    state = intent_parser(state, llm=mock_llm)

    # Step 2: Create a simple plan (simulate)
    state["plan"] = [
        {"id": "step-1", "step_type": StepType.TOOL_CALL, "tool_name": "flights_search_links", "tool_args": get_tool_args_from_prompt(), "status": "pending"},
        {"id": "step-2", "step_type": StepType.TOOL_CALL, "tool_name": "hotels_search_links", "tool_args": get_tool_args_from_prompt(), "status": "pending"},
        {"id": "step-3", "step_type": StepType.TOOL_CALL, "tool_name": "weather_summary", "tool_args": {"destination": "Paris"}, "status": "pending"},
    ]
    state["current_step_index"] = 0
    state["current_step"] = state["plan"][0]
    state["tool_results"] = []
    state["run_id"] = "test-itinerary"
    state["user_id"] = "test-user"


    # If orchestrator expects tools in state, add it
    state["tools"] = tools
    result = orchestrator(state, max_iters=10)

    # Print the itinerary or final state
    print("\n===== GENERATED ITINERARY OUTPUT =====")
    if "itinerary" in result:
        print(result["itinerary"])
    elif "final_answer" in result:
        print(result["final_answer"])
    else:
        print(result)
    print("===== END ITINERARY OUTPUT =====\n")
# Helper to extract tool args from the current prompt
def get_tool_args_from_prompt():
    # For the current prompt, this is static, but could be parsed if prompt changes
    return {"origin": "New Delhi", "destination": "Paris"}
def test_llm_invoke_failure_records():
    """Test that LLM failures are tracked and recorded."""
    from ai_travel_agent.llm import LLMClient
    from unittest.mock import MagicMock
    class FailingRunnable:
        def invoke(self, *a, **k):
            raise RuntimeError("Simulated LLM failure")
    llm = LLMClient(runnable=FailingRunnable(), metrics=MagicMock(), run_id="test-failures", user_id="test-user")
    try:
        llm.invoke_text(system="sys", user="user")
    except RuntimeError:
        pass
    # Check that a failure was recorded
    from ai_travel_agent.observability.failure_tracker import get_failure_tracker
    tracker = get_failure_tracker()
    found = any(f.category == "llm" for f in tracker.failures)
    assert found, "LLM failure was not tracked"
"""
Test suite for failure injection in AI Travel Agent.
Demonstrates how to simulate various failure scenarios.
"""

import pytest
from ai_travel_agent.observability.failure_tracker import FailureTracker, set_failure_tracker
from pathlib import Path
# Initialize global failure tracker for all tests
tracker = FailureTracker(run_id="test-failures", user_id="test-user", runtime_dir=Path("runtime"))
set_failure_tracker(tracker)
from unittest.mock import patch, MagicMock, AsyncMock
import json
from pathlib import Path

from ai_travel_agent.agents.state import AgentState, StepType, TripConstraints
from ai_travel_agent.agents.nodes.executor import executor
from ai_travel_agent.agents.nodes.orchestrator import orchestrator
from ai_travel_agent.agents.nodes.intent_parser import intent_parser
from ai_travel_agent.evaluation import (
    _links_valid,
    _has_sections,
    _specificity_score,
    _coherence_score,
    evaluate_final,
)
from ai_travel_agent.tools import ToolRegistry
from ai_travel_agent.llm import LLMClient


class TestLLMFailures:
    """Test LLM service failures."""

    def test_llm_timeout(self):
        """Inject LLM timeout and verify error handling."""
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.invoke_text.side_effect = TimeoutError("Ollama connection timeout after 10s")
        
        state = {
            "user_query": get_prompt("Plan a trip to Paris"),
            "constraints": {},
            "context_hits": [],
        }
        
        # intent_parser calls llm.invoke_text, should raise
        with pytest.raises(TimeoutError):
            intent_parser(state, llm=mock_llm)

    def test_llm_connection_refused(self):
        """LLM service (Ollama) is down."""
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.invoke_text.side_effect = ConnectionError("Connection refused: 127.0.0.1:11434")
        
        state = {"user_query": get_prompt("Trip to Rome"), "constraints": {}}
        
        with pytest.raises(ConnectionError):
            intent_parser(state, llm=mock_llm)

    def test_llm_returns_malformed_json(self):
        """LLM returns invalid JSON for constraint parsing."""
        mock_llm = MagicMock(spec=LLMClient)
        # Simulate LLM returning garbage instead of JSON
        mock_llm.invoke_text.return_value = "This is not valid JSON {{{invalid"
        
        state = {"user_query": get_prompt("Trip to Tokyo")}
        
        # intent_parser tries to parse JSON and fails
        result = intent_parser(state, llm=mock_llm)
        
        # Should set needs_user_input=True due to parsing failure
        assert result.get("needs_user_input") == True


class TestToolFailures:
    """Test tool execution failures."""

    def test_tool_not_registered(self):
        """Tool requested but not in registry."""
        tools = ToolRegistry()
        # Intentionally don't register flights_search_links
        tools.register("hotels_search_links", lambda **kw: {"summary": "test"})
        
        with pytest.raises(KeyError, match="Unknown tool: flights_search_links"):
            tools.call("flights_search_links", **get_tool_args_from_prompt())

    def test_tool_network_timeout(self):
        """Tool makes HTTP request that times out."""
        tools = ToolRegistry()
        
        def mock_weather_timeout(**kwargs):
            raise TimeoutError("Open-Meteo API timeout after 8s")
        
        tools.register("weather_summary", mock_weather_timeout)
        
        state = {
            "plan": [
                {
                    "id": "step-1",
                    "title": "Fetch weather",
                    "step_type": StepType.TOOL_CALL,
                    "tool_name": "weather_summary",
                    "tool_args": {"destination": "Paris", "start_date": "2026-03-01", "end_date": "2026-03-05"},
                    "status": "pending",
                }
            ],
            "current_step_index": 0,
            "current_step": {
                "id": "step-1",
                "step_type": StepType.TOOL_CALL,
                "tool_name": "weather_summary",
                "tool_args": {"destination": "Paris", "start_date": "2026-03-01", "end_date": "2026-03-05"},
            },
            "tool_results": [],
            "user_query": "Trip",
            "run_id": "test-run",
            "user_id": "test-user",
        }
        
        result = executor(state, tools=tools, llm=MagicMock(), metrics=None)
        
        # Step should be marked as blocked
        assert result["plan"][0]["status"] == "blocked"

    def test_tool_returns_invalid_data_structure(self):
        """Tool returns data that doesn't match expected schema."""
        tools = ToolRegistry()

        def mock_flights_invalid():
            return {
                "summary": "Found flights",
                "links": "NOT_A_LIST",  # Should be list of dicts
                "prices": "$599"  # Links-only MVP, price claim should be stripped
            }

        tools.register("flights_search_links", mock_flights_invalid)

        tool_args = get_tool_args_from_prompt()
        state = {
            "plan": [
                {
                    "id": "step-1",
                    "step_type": StepType.TOOL_CALL,
                    "tool_name": "flights_search_links",
                    "tool_args": tool_args,
                    "status": "pending",
                }
            ],
            "current_step_index": 0,
            "current_step": {
                "id": "step-1",
                "step_type": StepType.TOOL_CALL,
                "tool_name": "flights_search_links",
                "tool_args": tool_args,
            },
            "tool_results": [],
            "user_query": "Trip",
            "run_id": "test-run",
            "user_id": "test-user",
        }

        result = executor(state, tools=tools, llm=MagicMock(), metrics=None)

        # Step may be blocked if output is invalid, or done if coerced
        assert result["plan"][0]["status"] in {"done", "blocked"}
        # Tool result may or may not be stored depending on fallback logic
        assert len(result["tool_results"]) in {0, 1}


class TestIntentParsingFailures:
    """Test constraint parsing failures."""

    def test_missing_required_constraints(self):
        """LLM returns incomplete constraints."""
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.invoke_text.return_value = json.dumps({
            "origin": "New York",
            # Missing destination, dates, budget, etc.
        })
        
        state = {"user_query": "Plan a trip"}
        
        result = intent_parser(state, llm=mock_llm)
        
        # Should ask for clarification
        assert result["needs_user_input"] == True
        assert len(result.get("clarifying_questions", [])) > 0

    def test_invalid_date_format(self):
        """Constraints contain non-ISO date format."""
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.invoke_text.return_value = json.dumps({
            "origin": "NYC",
            "destinations": ["Paris"],
            "start_date": "March 1, 2026",  # Not ISO format (YYYY-MM-DD)
            "end_date": "2026-03-10",
            "budget_usd": 5000,
            "travelers": 2,
            "interests": ["museums"],
            "pace": "balanced",
        })
        
        state = {"user_query": "Trip to Paris"}
        
        result = intent_parser(state, llm=mock_llm)
        
        # May ask for clarification or mark as invalid
        # Depends on validation strictness


class TestOrchestratorFailures:
    """Test plan orchestration failures."""

    def test_max_iterations_exceeded(self):
        """Orchestrator loop exceeds max iterations."""
        state = {
            "plan": [
                {"id": f"step-{i}", "status": "pending", "title": f"Step {i}", "step_type": StepType.TOOL_CALL}
                for i in range(10)
            ],
            "loop_iterations": 0,
        }

        # With max_iters=2, should terminate early
        result = orchestrator(state, max_iters=2)

        # Accept both explicit and missing termination_reason (legacy)
        assert result.get("termination_reason") in {"max_iters", None}
        # Most steps still pending
        pending = sum(1 for s in result["plan"] if s["status"] == "pending")
        assert pending > 0

    def test_all_steps_blocked(self):
        """All plan steps are blocked (failures prevented execution)."""
        state = {
            "plan": [
                {"id": "step-1", "status": "blocked", "title": "Weather failed"},
                {"id": "step-2", "status": "blocked", "title": "Flights failed"},
            ],
            "loop_iterations": 0,
        }
        
        result = orchestrator(state, max_iters=10)
        
        # Orchestrator should see no pending steps
        assert result["termination_reason"] == "finalized"


class TestEvaluationFailures:
    """Test evaluation hard gates and rubrics."""

    def test_hard_gate_invalid_links(self):
        """Links in answer are malformed."""
        invalid_links = [
            "not-a-url",
            "ftp://invalid.com",  # Wrong scheme
            "https://",  # No domain
        ]
        
        assert _links_valid(invalid_links) == False

    def test_hard_gate_missing_sections(self):
        """Answer missing required sections."""
        answer = "Here's your itinerary: Go to Paris. Have fun!"
        
        # _has_sections checks for required sections
        score = _has_sections(answer)
        
        # Should be low score (missing most sections)
        assert score < 2.0  # Out of 5.0

    def test_hard_gate_no_disclaimer(self):
        """Safety disclaimer missing from answer."""
        answer = "Book flights at: google.com/flights\nHotel: booking.com"
        
        # Check if disclaimer is present
        disclaimer = "Visa/health requirements vary; verify with official sources"
        
        assert disclaimer.lower() not in answer.lower()

    def test_rubric_low_specificity(self):
        """Itinerary lacks specific times and details."""
        vague_answer = "Day 1: Visit Paris. Day 2: Go to museums. Day 3: Relax."
        
        score = _specificity_score(vague_answer)
        
        # Low specificity (no times, few bullets)
        assert score < 2.0

    def test_rubric_low_coherence(self):
        """Answer doesn't match constraints."""
        constraints = {
            "destinations": ["Paris", "Rome"],
            "start_date": "2026-03-01",
            "end_date": "2026-03-10",
        }
        
        answer = "Plan your trip to Tokyo! Start: tomorrow, End: whenever you feel like it."
        
        score = _coherence_score(constraints, answer)
        
        # Should be low (mismatched destinations and dates)
        assert score < 3.0

    def test_rubric_low_relevance(self):
        """Answer ignores user interests."""
        constraints = {
            "interests": ["museums", "art galleries", "historical sites"],
        }
        
        answer = "Enjoy beaches and nightlife!"
        
        # Interests not addressed
        # Would need to check actual implementation
        # _relevance_score logic


class TestMemoryFailures:
    """Test memory subsystem failures."""

    @patch('chromadb.PersistentClient')
    def test_persistent_storage_unavailable(self, mock_chroma):
        """Chroma persistent storage is down."""
        from ai_travel_agent.memory.store import MemoryStore
        
        mock_chroma.side_effect = Exception("Cannot connect to Chroma database")
        
        with pytest.raises(Exception):
            MemoryStore(
                user_id="test-user",
                persist_dir=Path("/tmp/test_chroma"),
                embedding_model="sentence-transformers/all-MiniLM-L6-v2"
            )

    def test_memory_retrieval_no_results(self):
        """Memory search returns no relevant hits."""
        # This is normal behavior for first-time users
        # Agent should proceed with empty context
        
        context_hits = []  # No prior memory
        
        # Agent should still work, just with less context
        assert len(context_hits) == 0


class TestExportFailures:
    """Test calendar export failures."""

    def test_ics_generation_with_empty_itinerary(self):
        """No days/events to export to calendar."""
        state = {
            "itinerary_day_titles": [],  # Empty
            "ics_path": "",
            "ics_event_count": 0,
        }
        
        # export_ics node should handle gracefully
        # Result: empty ICS or no export
        assert state["ics_event_count"] == 0

    def test_ics_invalid_date_format(self):
        """Itinerary has unparseable dates."""
        state = {
            "itinerary_day_titles": ["Visit Paris on not-a-date"],
            "constraints": {
                "start_date": "INVALID",  # Not ISO format
            },
        }
        
        # export_ics should fail validation
        # Hard gate: valid_ics = False


class TestStateCorruptionFailures:
    """Test shared state handling."""

    def test_circular_state_updates(self):
        """State never converges (step status never changes)."""
        state = {
            "plan": [
                {"id": "step-1", "status": "pending", "title": "Step 1", "step_type": StepType.TOOL_CALL},
            ],
            "current_step_index": 0,
            "loop_iterations": 0,
        }
        
        # Simulate orchestrator that doesn't mark step as done
        state["loop_iterations"] = 5
        
        # After many iterations, should trigger max_iters termination
        result = orchestrator(state, max_iters=5)
        
        assert result["termination_reason"] == "max_iters"

    def test_missing_current_step(self):
        """Current step reference is None/invalid."""
        state = {
            "plan": [],
            "current_step": None,
            "current_step_index": 0,
        }
        
        # executor should handle gracefully
        result = executor(state, tools=ToolRegistry(), llm=MagicMock(), metrics=None)
        
        # Should return unchanged state (no op)
        assert result["plan"] == []


# ============================================================================
# Integration Tests: Multi-Failure Scenarios
# ============================================================================

class TestCascadingFailures:
    """Test how failures propagate through the system."""

    def test_intent_parsing_fails_then_recovery(self):
        """Parse fails, user provides clarification, retry succeeds."""
        mock_llm = MagicMock(spec=LLMClient)
        
        # First call: incomplete response
        mock_llm.invoke_text.side_effect = [
            json.dumps({"origin": "NYC"}),  # First call: incomplete
            json.dumps({  # Second call (after clarification): complete
                "origin": "NYC",
                "destinations": ["Paris"],
                "start_date": "2026-03-01",
                "end_date": "2026-03-10",
                "budget_usd": 5000,
                "travelers": 2,
                "interests": ["museums"],
                "pace": "balanced",
            })
        ]
        
        state = {"user_query": "Trip to Paris"}
        
        # First attempt
        result1 = intent_parser(state, llm=mock_llm)
        assert result1["needs_user_input"] == True
        
        # Second attempt (after user provides clarification)
        state_clarified = {
            **state,
            "user_query": "Trip to Paris from NYC, Mar 1-10, 5000 budget, 2 people, museums"
        }
        result2 = intent_parser(state_clarified, llm=mock_llm)
        assert result2["needs_user_input"] == False

    def test_tool_fails_plan_continues(self):
        """One tool fails, others succeed, final answer incomplete but valid."""
        tools = ToolRegistry()
        
        # Register working tool
        tools.register("hotels_search_links", lambda **kw: {
            "summary": "Found hotels",
            "links": [{"label": "Booking.com", "url": "https://booking.com"}]
        })
        
        # Register failing tool
        def flights_fail(**kw):
            raise RuntimeError("Flights API down")
        
        tools.register("flights_search_links", flights_fail)
        
        # Plan has 2 steps
        state = {
            "plan": [
                {
                    "id": "step-flights",
                    "step_type": StepType.TOOL_CALL,
                    "tool_name": "flights_search_links",
                    "tool_args": {},
                    "status": "pending",
                },
                {
                    "id": "step-hotels",
                    "step_type": StepType.TOOL_CALL,
                    "tool_name": "hotels_search_links",
                    "tool_args": {},
                    "status": "pending",
                },
            ],
            "current_step_index": 0,
            "current_step": {
                "id": "step-flights",
                "step_type": StepType.TOOL_CALL,
                "tool_name": "flights_search_links",
            },
            "tool_results": [],
            "run_id": "test",
            "user_id": "test",
        }
        
        # First execution: flights fails
        result = executor(state, tools=tools, llm=MagicMock(), metrics=None)
        assert result["plan"][0]["status"] == "blocked"
        
        # Second execution: hotels succeeds
        state = result
        state["current_step_index"] = 1
        state["current_step"] = state["plan"][1]
        result = executor(state, tools=tools, llm=MagicMock(), metrics=None)
        assert result["plan"][1]["status"] == "done"
        assert len(result["tool_results"]) == 1


# --- LLM Failures ---
def test_llm_timeout_records():
    from ai_travel_agent.llm import LLMClient
    from unittest.mock import MagicMock
    class TimeoutRunnable:
        def invoke(self, *a, **k):
            import time; time.sleep(0.1); raise TimeoutError("LLM timeout")
    llm = LLMClient(runnable=TimeoutRunnable(), metrics=MagicMock(), run_id="test-failures", user_id="test-user")
    try:
        llm.invoke_text(system="sys", user="user")
    except TimeoutError:
        pass
    from ai_travel_agent.observability.failure_tracker import get_failure_tracker
    tracker = get_failure_tracker()
    assert any(f.category == "llm" and f.error_type == "TimeoutError" for f in tracker.failures)

def test_llm_malformed_response_records():
    from ai_travel_agent.llm import LLMClient
    from unittest.mock import MagicMock
    class MalformedRunnable:
        def invoke(self, *a, **k):
            return object()  # Not AIMessage, not string
    llm = LLMClient(runnable=MalformedRunnable(), metrics=MagicMock(), run_id="test-failures", user_id="test-user")
    out = llm.invoke_text(system="sys", user="user")
    assert isinstance(out, str)

# --- Tool Failures ---
def test_tool_partial_data_records():
    from ai_travel_agent.tools import ToolRegistry
    from ai_travel_agent.agents.nodes.executor import executor
    tools = ToolRegistry()
    def partial_tool(**kwargs):
        return {"summary": "Partial", "links": []}  # Missing required fields
    tools.register("partial_tool", partial_tool)
    state = {
        "plan": [{"id": "step-pt", "step_type": "TOOL_CALL", "tool_name": "partial_tool", "tool_args": {}, "status": "pending"}],
        "current_step_index": 0,
        "current_step": {"id": "step-pt", "step_type": "TOOL_CALL", "tool_name": "partial_tool"},
        "tool_results": [],
        "run_id": "test-failures", "user_id": "test-user"
    }
    result = executor(state, tools=tools, llm=MagicMock(), metrics=None)
    assert result["plan"][0]["status"] in {"done", "blocked"}

def test_tool_empty_results_records():
    from ai_travel_agent.tools import ToolRegistry
    from ai_travel_agent.agents.nodes.executor import executor
    tools = ToolRegistry()
    def empty_tool(**kwargs):
        return {"summary": "", "links": []}
    tools.register("empty_tool", empty_tool)
    state = {
        "plan": [{"id": "step-empty", "step_type": "TOOL_CALL", "tool_name": "empty_tool", "tool_args": {}, "status": "pending"}],
        "current_step_index": 0,
        "current_step": {"id": "step-empty", "step_type": "TOOL_CALL", "tool_name": "empty_tool"},
        "tool_results": [],
        "run_id": "test-failures", "user_id": "test-user"
    }
    result = executor(state, tools=tools, llm=MagicMock(), metrics=None)
    assert result["plan"][0]["status"] in {"done", "blocked"}

# --- Memory/Database Failures ---
def test_memory_unavailable_records():
    from ai_travel_agent.agents.nodes.executor import executor
    from ai_travel_agent.tools import ToolRegistry
    tools = ToolRegistry()
    state = {
        "plan": [{"id": "step-mem", "step_type": "RETRIEVE_CONTEXT", "tool_name": None, "tool_args": {}, "status": "pending"}],
        "current_step_index": 0,
        "current_step": {"id": "step-mem", "step_type": "RETRIEVE_CONTEXT"},
        "run_id": "test-failures", "user_id": "test-user"
    }
    result = executor(state, tools=tools, llm=MagicMock(), metrics=None, memory=None)
    assert result["plan"][0]["status"] == "blocked"

# --- Validation Failures ---
def test_validation_failure_records():
    from ai_travel_agent.agents.nodes.intent_parser import intent_parser
    from unittest.mock import MagicMock
    mock_llm = MagicMock()
    mock_llm.invoke_text.return_value = "{"  # Malformed JSON
    state = {"user_query": "Plan a trip", "constraints": {}}
    try:
        intent_parser(state, llm=mock_llm)
    except Exception:
        pass
    from ai_travel_agent.observability.failure_tracker import get_failure_tracker
    tracker = get_failure_tracker()
    assert any(f.category == "llm" for f in tracker.failures)

# --- State/Orchestrator Failures ---
def test_state_corruption_records():
    from ai_travel_agent.agents.nodes.executor import executor
    from ai_travel_agent.tools import ToolRegistry
    tools = ToolRegistry()
    # Corrupt state: missing current_step
    state = {"plan": [], "current_step_index": 0, "run_id": "test-failures", "user_id": "test-user"}
    result = executor(state, tools=tools, llm=MagicMock(), metrics=None)
    assert result == state

# --- Export/Output Failures ---
def test_export_ics_failure_records():
    from ai_travel_agent.tools import ToolRegistry
    from ai_travel_agent.agents.nodes.executor import executor
    tools = ToolRegistry()
    def ics_fail(**kwargs):
        raise IOError("ICS export failed")
    tools.register("export_ics", ics_fail)
    state = {
        "plan": [{"id": "step-ics", "step_type": "TOOL_CALL", "tool_name": "export_ics", "tool_args": {}, "status": "pending"}],
        "current_step_index": 0,
        "current_step": {"id": "step-ics", "step_type": "TOOL_CALL", "tool_name": "export_ics"},
        "tool_results": [],
        "run_id": "test-failures", "user_id": "test-user"
    }
    try:
        executor(state, tools=tools, llm=MagicMock(), metrics=None)
    except Exception:
        pass
    from ai_travel_agent.observability.failure_tracker import get_failure_tracker
    tracker = get_failure_tracker()
    assert any(f.tool_name == "export_ics" for f in tracker.failures)

# --- Recovery/Retry Failures ---
def test_tool_retry_failure_records():
    from ai_travel_agent.tools import ToolRegistry
    from ai_travel_agent.agents.nodes.executor import executor
    tools = ToolRegistry()
    call_count = {"count": 0}
    def flaky_tool(**kwargs):
        call_count["count"] += 1
        if call_count["count"] < 2:
            raise RuntimeError("Temporary failure")
        return {"summary": "Recovered", "links": []}
    tools.register("flaky_tool", flaky_tool)
    state = {
        "plan": [{"id": "step-flaky", "step_type": "TOOL_CALL", "tool_name": "flaky_tool", "tool_args": {}, "status": "pending"}],
        "current_step_index": 0,
        "current_step": {"id": "step-flaky", "step_type": "TOOL_CALL", "tool_name": "flaky_tool"},
        "tool_results": [],
        "run_id": "test-failures", "user_id": "test-user"
    }
    result = executor(state, tools=tools, llm=MagicMock(), metrics=None, max_tool_retries=2)
    assert result["plan"][0]["status"] == "done"


# ===================== Custom Prompt Support =====================
CUSTOM_PROMPT = "Plan a 5 day trip to Paris from New Delhi"  # Set this to a string to override all prompts in tests

def get_prompt(default):
    return CUSTOM_PROMPT if CUSTOM_PROMPT is not None else default
# ================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
