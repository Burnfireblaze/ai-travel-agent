"""
Chaos engineering utilities for AI Travel Agent.
Provides decorators and context managers to inject failures for resilience testing.
Integrated with failure tracking for comprehensive observability during chaos tests.
"""

import random
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, Type

# Import failure tracker for automatic tracking of chaos-injected failures
try:
    from ai_travel_agent.observability.failure_tracker import (
        FailureTracker,
        FailureCategory,
        FailureSeverity,
        get_failure_tracker,
    )
    FAILURE_TRACKING_AVAILABLE = True
except ImportError:
    FAILURE_TRACKING_AVAILABLE = False


class FailureMode(Enum):
    """Types of failures that can be injected."""
    TIMEOUT = "timeout"
    EXCEPTION = "exception"
    INVALID_DATA = "invalid_data"
    PARTIAL_DATA = "partial_data"
    SLOW_RESPONSE = "slow_response"
    MALFORMED_RESPONSE = "malformed_response"


@dataclass
class ChaosConfig:
    """Configuration for chaos injection."""
    enabled: bool = False
    failure_probability: float = 0.0  # 0.0-1.0
    failure_mode: FailureMode = FailureMode.EXCEPTION
    exception_type: Type[Exception] = RuntimeError
    exception_message: str = "Injected failure"
    latency_multiplier: float = 1.0  # For SLOW_RESPONSE
    track_failures: bool = True  # Auto-track injected failures
    
    def should_fail(self) -> bool:
        """Determine if failure should be injected."""
        if not self.enabled:
            return False
        return random.random() < self.failure_probability
    
    def should_track(self) -> bool:
        """Determine if failure should be tracked."""
        return self.track_failures and FAILURE_TRACKING_AVAILABLE


# Global chaos config (can be set per test)
_global_chaos_config: Optional[ChaosConfig] = None


def set_chaos_config(config: Optional[ChaosConfig]) -> None:
    """Set global chaos configuration."""
    global _global_chaos_config
    _global_chaos_config = config


def get_chaos_config() -> ChaosConfig:
    """Get current chaos configuration."""
    return _global_chaos_config or ChaosConfig(enabled=False)


@contextmanager
def chaos_mode(
    failure_probability: float = 0.5,
    failure_mode: FailureMode = FailureMode.EXCEPTION,
    exception_type: Type[Exception] = RuntimeError,
    exception_message: str = "Chaos-injected failure",
):
    """
    Context manager for chaos injection.
    
    Example:
        with chaos_mode(failure_probability=0.5, failure_mode=FailureMode.TIMEOUT):
            result = agent.run(query)  # 50% chance of timeout
    """
    config = ChaosConfig(
        enabled=True,
        failure_probability=failure_probability,
        failure_mode=failure_mode,
        exception_type=exception_type,
        exception_message=exception_message,
    )
    old_config = get_chaos_config()
    set_chaos_config(config)
    try:
        yield config
    finally:
        set_chaos_config(old_config)


def inject_failure(
    failure_probability: float = 0.5,
    failure_mode: FailureMode = FailureMode.EXCEPTION,
    exception_type: Type[Exception] = RuntimeError,
    exception_message: str = "Injected failure",
    latency_multiplier: float = 1.0,
    track_failure: bool = True,
    node_name: str = "chaos_injection",
    tool_name: Optional[str] = None,
):
    """
    Decorator to inject failures into a function.
    Automatically tracks injected failures for observability.
    
    Example:
        @inject_failure(
            failure_probability=0.1,
            failure_mode=FailureMode.TIMEOUT,
            exception_type=TimeoutError,
            track_failure=True
        )
        def fetch_flights(origin, destination):
            return {"flights": [...]}
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            config = get_chaos_config()
            if config.enabled and config.should_fail():
                _execute_failure(
                    failure_mode=config.failure_mode,
                    exception_type=config.exception_type,
                    exception_message=config.exception_message,
                    latency_multiplier=config.latency_multiplier,
                    node_name=node_name,
                    tool_name=tool_name,
                    track=config.should_track() and track_failure,
                )
            
            # Also check local config
            if failure_probability > 0 and random.random() < failure_probability:
                _execute_failure(
                    failure_mode=failure_mode,
                    exception_type=exception_type,
                    exception_message=exception_message,
                    latency_multiplier=latency_multiplier,
                    node_name=node_name,
                    tool_name=tool_name,
                    track=track_failure and FAILURE_TRACKING_AVAILABLE,
                )
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def _execute_failure(
    failure_mode: FailureMode,
    exception_type: Type[Exception],
    exception_message: str,
    latency_multiplier: float,
    node_name: str = "chaos_injection",
    tool_name: Optional[str] = None,
    track: bool = True,
) -> None:
    """Execute the actual failure injection and optionally track it."""
    
    # Determine the error type and message
    error_type = exception_type.__name__
    error_msg = exception_message or f"{failure_mode.value} failure"
    
    # Track failure if available and requested
    if track and FAILURE_TRACKING_AVAILABLE:
        tracker = get_failure_tracker()
        if tracker:
            try:
                # Determine category based on failure mode
                if failure_mode == FailureMode.TIMEOUT:
                    category = FailureCategory.NETWORK
                    severity = FailureSeverity.HIGH
                elif failure_mode in [FailureMode.INVALID_DATA, FailureMode.PARTIAL_DATA, FailureMode.MALFORMED_RESPONSE]:
                    category = FailureCategory.VALIDATION
                    severity = FailureSeverity.MEDIUM
                else:
                    category = FailureCategory.UNKNOWN
                    severity = FailureSeverity.HIGH
                
                # Record the injected failure
                tracker.record_failure(
                    category=category,
                    severity=severity,
                    graph_node=node_name,
                    error_type=error_type,
                    error_message=error_msg,
                    step_title=f"Chaos-injected {failure_mode.value}",
                    tool_name=tool_name,
                    error_traceback=traceback.format_exc(),
                    context_data={
                        "failure_mode": failure_mode.value,
                        "injection_type": "chaos_engineering",
                    },
                    tags=["chaos-injected", failure_mode.value, "testing"],
                )
            except Exception:
                pass  # Silently ignore tracking errors
    
    # Execute the actual failure
    if failure_mode == FailureMode.TIMEOUT:
        raise TimeoutError(exception_message or "Request timeout")
    
    elif failure_mode == FailureMode.EXCEPTION:
        raise exception_type(exception_message)
    
    elif failure_mode == FailureMode.SLOW_RESPONSE:
        time.sleep(latency_multiplier)  # Block for specified seconds
    
    elif failure_mode == FailureMode.INVALID_DATA:
        raise ValueError(f"Invalid data received: {exception_message}")
    
    elif failure_mode == FailureMode.PARTIAL_DATA:
        raise ValueError(f"Incomplete data: {exception_message}")
    
    elif failure_mode == FailureMode.MALFORMED_RESPONSE:
        raise ValueError(f"Malformed response: {exception_message}")


class ChaosToolRegistry:
    """
    Wrapper around ToolRegistry that can inject failures.
    Useful for testing tool failure scenarios.
    Automatically tracks injected failures for observability.
    """
    
    def __init__(self, base_registry, chaos_config: Optional[ChaosConfig] = None):
        self.base_registry = base_registry
        self.chaos_config = chaos_config or ChaosConfig(enabled=False)
        self.failure_map: dict[str, ChaosConfig] = {}
    
    def set_tool_failure(self, tool_name: str, config: ChaosConfig) -> None:
        """Configure specific tool to fail."""
        self.failure_map[tool_name] = config
    
    def call(self, name: str, **kwargs) -> Any:
        """Call tool with potential chaos injection and tracking."""
        # Check if specific tool has chaos config
        if name in self.failure_map:
            config = self.failure_map[name]
            if config.enabled and config.should_fail():
                _execute_failure(
                    failure_mode=config.failure_mode,
                    exception_type=config.exception_type,
                    exception_message=config.exception_message,
                    latency_multiplier=config.latency_multiplier,
                    node_name="tool_execution",
                    tool_name=name,
                    track=config.should_track(),
                )
        
        # Check global config
        if self.chaos_config.enabled and self.chaos_config.should_fail():
            _execute_failure(
                failure_mode=self.chaos_config.failure_mode,
                exception_type=self.chaos_config.exception_type,
                exception_message=self.chaos_config.exception_message,
                latency_multiplier=self.chaos_config.latency_multiplier,
                node_name="tool_execution",
                tool_name=name,
                track=self.chaos_config.should_track(),
            )
        
        # Call actual tool
        return self.base_registry.call(name, **kwargs)


class DataCorruptor:
    """Utility to corrupt/transform data for testing."""
    
    @staticmethod
    def corrupt_links(links: list[dict[str, str]]) -> Any:
        """Corrupt links structure (invalid format)."""
        return "not_a_list"  # Wrong type
    
    @staticmethod
    def remove_links(data: dict) -> dict:
        """Remove links from tool result."""
        data.pop("links", None)
        return data
    
    @staticmethod
    def add_price_claims(data: dict) -> dict:
        """Inject price claims (should be stripped by responder)."""
        data["summary"] = data.get("summary", "") + " Flights cost $599."
        return data
    
    @staticmethod
    def truncate_response(data: dict, truncate_at: int = 50) -> dict:
        """Truncate response to test partial data handling."""
        if "summary" in data:
            data["summary"] = data["summary"][:truncate_at]
        return data
    
    @staticmethod
    def inject_invalid_dates(constraints: dict) -> dict:
        """Inject non-ISO date formats."""
        constraints["start_date"] = "March 1, 2026"
        constraints["end_date"] = "tomorrow"
        return constraints
    
    @staticmethod
    def remove_required_fields(constraints: dict) -> dict:
        """Remove required constraint fields."""
        constraints.pop("destination", None)
        constraints.pop("start_date", None)
        return constraints


class MemoryFaultInjector:
    """Inject failures in memory operations."""
    
    def __init__(self, memory_store):
        self.memory_store = memory_store
        self.search_failure_enabled = False
        self.write_failure_enabled = False
        self.retrieval_delay_seconds = 0.0
    
    def enable_search_failure(self, enabled: bool = True) -> None:
        """Make memory.search() raise exception."""
        self.search_failure_enabled = enabled
    
    def enable_write_failure(self, enabled: bool = True) -> None:
        """Make memory.add_*() raise exception."""
        self.write_failure_enabled = enabled
    
    def set_retrieval_delay(self, seconds: float) -> None:
        """Add artificial delay to memory retrieval."""
        self.retrieval_delay_seconds = seconds
    
    def search(self, *args, **kwargs):
        """Wrapped search with fault injection."""
        if self.retrieval_delay_seconds > 0:
            time.sleep(self.retrieval_delay_seconds)
        
        if self.search_failure_enabled:
            raise RuntimeError("Memory search failed (injected)")
        
        return self.memory_store.search(*args, **kwargs)


class StateValidator:
    """Validate state consistency and inject corruptions."""
    
    @staticmethod
    def validate_state_consistency(state: dict) -> list[str]:
        """Check state for inconsistencies."""
        errors = []
        
        # Plan consistency
        plan = state.get("plan", [])
        current_idx = state.get("current_step_index")
        if current_idx is not None and current_idx >= len(plan):
            errors.append(f"current_step_index {current_idx} out of range [0, {len(plan)-1}]")
        
        # Step status validity
        valid_statuses = {"pending", "done", "blocked"}
        for step in plan:
            if step.get("status") not in valid_statuses:
                errors.append(f"Invalid step status: {step.get('status')}")
        
        # Current step matches plan
        current_step = state.get("current_step")
        if current_step and current_idx is not None:
            if current_step.get("id") != plan[current_idx].get("id"):
                errors.append("current_step does not match plan[current_step_index]")
        
        # Tool results reference valid steps
        for result in state.get("tool_results", []):
            step_id = result.get("step_id")
            if not any(s.get("id") == step_id for s in plan):
                errors.append(f"Tool result references unknown step: {step_id}")
        
        return errors
    
    @staticmethod
    def corrupt_state() -> dict:
        """Create a deliberately corrupted state for testing."""
        return {
            "plan": [
                {"id": "step-1", "status": "pending", "title": "Step 1"},
                {"id": "step-2", "status": "invalid_status", "title": "Step 2"},
            ],
            "current_step_index": 10,  # Out of range
            "current_step": {"id": "step-999"},  # Doesn't exist in plan
            "tool_results": [
                {"step_id": "unknown-step", "tool_name": "test"}  # References non-existent step
            ],
        }


# ============================================================================
# Example usage functions
# ============================================================================

def demo_chaos_mode():
    """Demonstrate chaos mode usage."""
    print("=== Chaos Mode Demo ===\n")
    
    @inject_failure(failure_probability=0.5, exception_type=TimeoutError)
    def flaky_api_call():
        return {"result": "success"}
    
    print("Calling flaky API 10 times...")
    for i in range(10):
        try:
            result = flaky_api_call()
            print(f"  Call {i+1}: Success - {result}")
        except TimeoutError as e:
            print(f"  Call {i+1}: Failed - {e}")


def demo_tool_chaos():
    """Demonstrate tool chaos injection."""
    print("\n=== Tool Chaos Demo ===\n")
    
    from ai_travel_agent.tools import ToolRegistry
    
    base_registry = ToolRegistry()
    base_registry.register("test_tool", lambda: {"data": "test"})
    
    chaos_registry = ChaosToolRegistry(base_registry)
    
    # Configure test_tool to fail 50% of the time
    chaos_registry.set_tool_failure(
        "test_tool",
        ChaosConfig(
            enabled=True,
            failure_probability=0.5,
            failure_mode=FailureMode.TIMEOUT,
        )
    )
    
    print("Calling tool 10 times with 50% timeout injection...")
    for i in range(10):
        try:
            result = chaos_registry.call("test_tool")
            print(f"  Call {i+1}: Success - {result}")
        except Exception as e:
            print(f"  Call {i+1}: Failed - {type(e).__name__}")


def demo_state_validation():
    """Demonstrate state validation and corruption detection."""
    print("\n=== State Validation Demo ===\n")
    
    corrupted = StateValidator.corrupt_state()
    errors = StateValidator.validate_state_consistency(corrupted)
    
    print(f"Found {len(errors)} validation errors:")
    for error in errors:
        print(f"  - {error}")


if __name__ == "__main__":
    demo_chaos_mode()
    demo_tool_chaos()
    demo_state_validation()
