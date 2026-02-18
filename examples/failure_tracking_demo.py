"""
Demonstration of the failure tracking system.
Shows how failures are captured, tagged, and visualized.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock
import tempfile

from ai_travel_agent.observability.failure_tracker import (
    FailureTracker,
    FailureCategory,
    FailureSeverity,
    set_failure_tracker,
)
from ai_travel_agent.observability.failure_visualizer import (
    FailureVisualizer,
    display_failure_report,
)
from ai_travel_agent.tools.tracked_registry import TrackedToolRegistry
from ai_travel_agent.tools import ToolRegistry


def demo_1_basic_failure_tracking():
    """Demo 1: Capture and display a simple tool failure."""
    print("\n" + "="*70)
    print("DEMO 1: Basic Failure Tracking")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        runtime_dir = Path(tmpdir)
        
        # Create failure tracker
        tracker = FailureTracker(
            run_id="demo-run-001",
            user_id="demo-user",
            runtime_dir=runtime_dir
        )
        set_failure_tracker(tracker)
        
        # Simulate a tool timeout
        print("\n1. Recording a network timeout failure...")
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
                "end_date": "2026-03-20",
            },
            tags=["weather", "network_timeout", "paris"],
        )
        
        # Mark as recovered
        print("2. Marking failure as recovered...")
        tracker.mark_recovered(
            failure,
            recovery_action="Step marked as blocked, orchestrator continues with remaining steps"
        )
        
        # Show summary
        print("\n3. Failure Summary:")
        print(json.dumps(tracker.get_summary(), indent=2))
        
        # Print report
        print("\n4. Failure Report:")
        print(tracker.generate_report())


def demo_2_multiple_failures_with_categorization():
    """Demo 2: Track multiple failures with different categories."""
    print("\n" + "="*70)
    print("DEMO 2: Multiple Failures with Categorization")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        runtime_dir = Path(tmpdir)
        tracker = FailureTracker(
            run_id="demo-run-002",
            user_id="demo-user",
            runtime_dir=runtime_dir
        )
        set_failure_tracker(tracker)
        
        # Failure 1: Tool not registered
        print("\n1. Recording 'tool not found' error...")
        f1 = tracker.record_failure(
            category=FailureCategory.TOOL,
            severity=FailureSeverity.HIGH,
            graph_node="executor",
            error_type="KeyError",
            error_message="Tool 'flights_search_links' not registered",
            tool_name="flights_search_links",
            step_title="Search flights",
            latency_ms=1.2,
            context_data={"available_tools": ["weather_summary", "hotels_search_links"]},
            tags=["tool_config", "missing_tool"],
        )
        tracker.mark_recovered(f1, "Tool marked as missing, step blocked")
        
        # Failure 2: Validation error
        print("2. Recording validation error...")
        f2 = tracker.record_failure(
            category=FailureCategory.VALIDATION,
            severity=FailureSeverity.MEDIUM,
            graph_node="intent_parser",
            error_type="ValueError",
            error_message="Invalid date format: expected YYYY-MM-DD, got 'March 15'",
            step_title="Parse intent constraints",
            latency_ms=234.5,
            context_data={"provided_date": "March 15", "expected_format": "YYYY-MM-DD"},
            tags=["validation", "date_format"],
        )
        tracker.mark_recovered(f2, "Agent asked user for clarification")
        
        # Failure 3: LLM timeout (critical)
        print("3. Recording critical LLM failure...")
        f3 = tracker.record_failure(
            category=FailureCategory.LLM,
            severity=FailureSeverity.CRITICAL,
            graph_node="executor",
            error_type="TimeoutError",
            error_message="Ollama model timeout after 30 seconds",
            llm_model="qwen2.5:7b-instruct",
            step_title="Synthesize itinerary",
            latency_ms=30234.0,
            context_data={"prompt_length": 5234},
            tags=["llm", "ollama", "synthesis", "critical"],
        )
        tracker.mark_recovered(f3, "Attempted recovery with empty response")
        
        # Failure 4: Network error
        print("4. Recording connection error...")
        f4 = tracker.record_failure(
            category=FailureCategory.NETWORK,
            severity=FailureSeverity.HIGH,
            graph_node="executor",
            error_type="ConnectionError",
            error_message="Connection refused: 127.0.0.1:11434",
            tool_name="hotels_search_links",
            step_title="Search hotels",
            latency_ms=5001.2,
            context_data={"service": "hotels_api", "host": "127.0.0.1"},
            tags=["network", "connection_refused", "hotels"],
        )
        tracker.mark_recovered(f4, "Retried with backoff")
        
        # Display summary
        print("\n5. Summary Statistics:")
        summary = tracker.get_summary()
        print(f"   Total failures: {summary['total_failures']}")
        print(f"   By severity: {summary['by_severity']}")
        print(f"   By category: {summary['by_category']}")
        print(f"   Recovery rate: {summary['recovery_rate']:.1f}%")
        
        # Display report
        print("\n6. Full Report:")
        print(tracker.generate_report())
        
        # Save to file and visualize
        log_path = runtime_dir / "logs" / f"failures_demo-run-002.jsonl"
        if log_path.exists():
            print(f"\n7. Displaying failures from log file: {log_path}")
            display_failure_report(log_path, verbose=False)


def demo_3_tracked_tool_registry():
    """Demo 3: Track failures at tool registry level."""
    print("\n" + "="*70)
    print("DEMO 3: Tracked Tool Registry")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        runtime_dir = Path(tmpdir)
        tracker = FailureTracker(
            run_id="demo-run-003",
            user_id="demo-user",
            runtime_dir=runtime_dir
        )
        set_failure_tracker(tracker)
        
        # Create base registry
        base_registry = ToolRegistry()
        base_registry.register("hotels_search_links", lambda **kw: {"summary": "Hotels found"})
        
        # Wrap with tracking
        tracked_tools = TrackedToolRegistry(base_registry)
        
        print("\n1. Attempting to call unregistered tool...")
        try:
            tracked_tools.call(
                "flights_search_links",
                run_id="demo-run-003",
                user_id="demo-user",
                origin="NYC",
                destination="Paris"
            )
        except KeyError as e:
            print(f"   Caught error: {e}")
            print("   ✓ Failure automatically tracked in tracker")
        
        print("\n2. Calling registered tool successfully...")
        result = tracked_tools.call(
            "hotels_search_links",
            run_id="demo-run-003",
            user_id="demo-user",
            destination="Paris"
        )
        print(f"   ✓ Tool succeeded: {result}")
        
        print("\n3. Failure Tracker Summary:")
        print(json.dumps(tracker.get_summary(), indent=2))
        
        print("\n4. Failure Report:")
        print(tracker.generate_report())


def demo_4_failure_timeline_and_analysis():
    """Demo 4: Analyze failure timeline across a run."""
    print("\n" + "="*70)
    print("DEMO 4: Failure Timeline Analysis")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        runtime_dir = Path(tmpdir)
        tracker = FailureTracker(
            run_id="demo-run-004",
            user_id="demo-user",
            runtime_dir=runtime_dir
        )
        set_failure_tracker(tracker)
        
        print("\n1. Simulating failures across different stages...")
        
        # Stage 1: Intent parsing
        print("   Stage 1: Intent Parsing")
        f1 = tracker.record_failure(
            category=FailureCategory.VALIDATION,
            severity=FailureSeverity.MEDIUM,
            graph_node="intent_parser",
            error_type="ValueError",
            error_message="Missing required field: destination",
            latency_ms=45.2,
            tags=["validation", "missing_field"],
        )
        tracker.mark_recovered(f1, "Asked user for clarification")
        
        # Stage 2: Tool execution
        print("   Stage 2: Tool Execution")
        f2 = tracker.record_failure(
            category=FailureCategory.NETWORK,
            severity=FailureSeverity.HIGH,
            graph_node="executor",
            error_type="TimeoutError",
            error_message="Weather API timeout",
            tool_name="weather_summary",
            latency_ms=8234.5,
            tags=["network", "timeout"],
        )
        tracker.mark_recovered(f2, "Step blocked, plan continues")
        
        # Stage 3: Synthesis
        print("   Stage 3: Synthesis")
        f3 = tracker.record_failure(
            category=FailureCategory.LLM,
            severity=FailureSeverity.CRITICAL,
            graph_node="executor",
            error_type="TimeoutError",
            error_message="LLM synthesis timeout",
            llm_model="qwen2.5:7b-instruct",
            latency_ms=30001.0,
            tags=["llm", "synthesis"],
        )
        tracker.mark_recovered(f3, "Empty response returned")
        
        # Stage 4: Evaluation
        print("   Stage 4: Evaluation")
        f4 = tracker.record_failure(
            category=FailureCategory.EVALUATION,
            severity=FailureSeverity.MEDIUM,
            graph_node="evaluate_final",
            error_type="AssertionError",
            error_message="Hard gate failed: missing required sections",
            latency_ms=123.4,
            tags=["evaluation", "hard_gate"],
        )
        tracker.mark_recovered(f4, "Evaluation recorded, run marked as failed")
        
        print("\n2. Failure Timeline (in chronological order):")
        chain = tracker.failure_chain
        for i, failure in enumerate(chain.get_failure_timeline(), 1):
            print(f"   {i}. [{failure.graph_node}] {failure.error_type}: {failure.error_message}")
        
        print("\n3. Failures by Node:")
        for node, failures in [
            ("intent_parser", chain.get_failures_by_node("intent_parser")),
            ("executor", chain.get_failures_by_node("executor")),
            ("evaluate_final", chain.get_failures_by_node("evaluate_final")),
        ]:
            print(f"   {node}: {len(failures)} failure(s)")
        
        print("\n4. Critical Failures:")
        critical = chain.get_critical_failures()
        print(f"   Total: {len(critical)}")
        for failure in critical:
            print(f"   - {failure.error_type}: {failure.error_message}")
        
        print("\n5. Full Report:")
        print(tracker.generate_report())


def main():
    """Run all demos."""
    print("\n" + "#"*70)
    print("# FAILURE TRACKING SYSTEM DEMONSTRATION")
    print("#"*70)
    
    demo_1_basic_failure_tracking()
    demo_2_multiple_failures_with_categorization()
    demo_3_tracked_tool_registry()
    demo_4_failure_timeline_and_analysis()
    
    print("\n" + "#"*70)
    print("# DEMONSTRATIONS COMPLETE")
    print("#"*70 + "\n")


if __name__ == "__main__":
    main()
