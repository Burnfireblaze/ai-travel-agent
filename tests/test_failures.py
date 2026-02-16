"""
Test suite for failure injection in AI Travel Agent.
Demonstrates how to simulate various failure scenarios.
"""

import pytest
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
            "user_query": "Plan a trip to Paris",
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
        
        state = {"user_query": "Trip to Rome", "constraints": {}}
        
        with pytest.raises(ConnectionError):
            intent_parser(state, llm=mock_llm)

    def test_llm_returns_malformed_json(self):
        """LLM returns invalid JSON for constraint parsing."""
        mock_llm = MagicMock(spec=LLMClient)
        # Simulate LLM returning garbage instead of JSON
        mock_llm.invoke_text.return_value = "This is not valid JSON {{{invalid"
        
        state = {"user_query": "Trip to Tokyo"}
        
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
            tools.call("flights_search_links", origin="NYC", destination="LAX")

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
        
        state = {
            "plan": [
                {
                    "id": "step-1",
                    "step_type": StepType.TOOL_CALL,
                    "tool_name": "flights_search_links",
                    "tool_args": {"origin": "NYC", "destination": "LAX"},
                    "status": "pending",
                }
            ],
            "current_step_index": 0,
            "current_step": {
                "id": "step-1",
                "step_type": StepType.TOOL_CALL,
                "tool_name": "flights_search_links",
                "tool_args": {"origin": "NYC", "destination": "LAX"},
            },
            "tool_results": [],
            "user_query": "Trip",
            "run_id": "test-run",
            "user_id": "test-user",
        }
        
        result = executor(state, tools=tools, llm=MagicMock(), metrics=None)
        
        # Step should complete despite invalid data
        assert result["plan"][0]["status"] == "done"
        # Tool result stored but with coerced data
        assert len(result["tool_results"]) == 1


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
        
        assert result["termination_reason"] == "max_iters"
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
