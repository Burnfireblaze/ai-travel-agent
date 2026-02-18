"""
Instrumented tool registry with failure tracking.
Captures failures at the tool invocation level with full context.
"""

import time
import traceback
from typing import Any, Mapping

from ai_travel_agent.observability.failure_tracker import (
    get_failure_tracker,
    FailureCategory,
    FailureSeverity,
)


class TrackedToolRegistry:
    """
    Wrapper around ToolRegistry that tracks all tool calls and failures.
    Automatically records failures with categorization and severity assessment.
    """
    
    def __init__(self, base_registry):
        self.base_registry = base_registry
        self.call_count = 0
        self.failure_count = 0
    
    def call(
        self,
        name: str,
        run_id: str = "unknown",
        user_id: str = "unknown",
        step_id: str = "",
        **kwargs: Any
    ) -> Mapping[str, Any]:
        """
        Call a tool with automatic failure tracking.
        
        Args:
            name: Tool name (e.g., "weather_summary")
            run_id: Current run ID (for failure tracking)
            user_id: Current user ID (for failure tracking)
            step_id: Step ID (for failure tracking)
            **kwargs: Tool arguments
        
        Returns:
            Tool result (dict)
        
        Raises:
            Tracked exceptions (original behavior preserved)
        """
        failure_tracker = get_failure_tracker()
        self.call_count += 1
        
        started = time.perf_counter()
        
        try:
            # Attempt tool call
            result = self.base_registry.call(name, **kwargs)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            
            return result
        
        except KeyError as e:
            # Tool not registered
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self.failure_count += 1
            
            if failure_tracker:
                failure = failure_tracker.record_failure(
                    category=FailureCategory.TOOL,
                    severity=FailureSeverity.HIGH,
                    graph_node="executor",
                    error_type="KeyError",
                    error_message=f"Tool not registered: {name}",
                    tool_name=name,
                    latency_ms=elapsed_ms,
                    error_traceback=traceback.format_exc(),
                    context_data={
                        "tool_call_count": self.call_count,
                        "available_tools": list(self.base_registry.tools.keys()),
                        "kwargs": kwargs,
                    },
                    tags=["tool_not_found", name, "configuration_error"],
                )
                failure_tracker.mark_recovered(
                    failure,
                    recovery_action="Tool marked as missing - step will be blocked"
                )
            
            raise
        
        except TimeoutError as e:
            # Network timeout
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self.failure_count += 1
            
            if failure_tracker:
                failure = failure_tracker.record_failure(
                    category=FailureCategory.NETWORK,
                    severity=FailureSeverity.HIGH,
                    graph_node="executor",
                    error_type="TimeoutError",
                    error_message=f"Tool timeout: {str(e)}",
                    tool_name=name,
                    latency_ms=elapsed_ms,
                    error_traceback=traceback.format_exc(),
                    context_data={
                        "timeout_after_ms": elapsed_ms,
                        "tool_args_keys": list(kwargs.keys()),
                    },
                    tags=["network_timeout", name, f"timeout_{name}"],
                )
                failure_tracker.mark_recovered(
                    failure,
                    recovery_action="Timeout caught - step marked as blocked, plan continues"
                )
            
            raise
        
        except ConnectionError as e:
            # Connection refused/unavailable
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self.failure_count += 1
            
            if failure_tracker:
                failure = failure_tracker.record_failure(
                    category=FailureCategory.NETWORK,
                    severity=FailureSeverity.HIGH,
                    graph_node="executor",
                    error_type="ConnectionError",
                    error_message=f"Service unavailable: {str(e)}",
                    tool_name=name,
                    latency_ms=elapsed_ms,
                    error_traceback=traceback.format_exc(),
                    context_data={
                        "connection_error_details": str(e),
                        "tool_call_number": self.call_count,
                    },
                    tags=["connection_error", name, "service_unavailable"],
                )
                failure_tracker.mark_recovered(
                    failure,
                    recovery_action="Service unavailable - step marked as blocked, plan continues"
                )
            
            raise
        
        except ValueError as e:
            # Invalid data/arguments
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self.failure_count += 1
            
            if failure_tracker:
                failure = failure_tracker.record_failure(
                    category=FailureCategory.VALIDATION,
                    severity=FailureSeverity.MEDIUM,
                    graph_node="executor",
                    error_type="ValueError",
                    error_message=f"Invalid data: {str(e)}",
                    tool_name=name,
                    latency_ms=elapsed_ms,
                    error_traceback=traceback.format_exc(),
                    context_data={
                        "tool_args": kwargs,
                        "validation_error": str(e),
                    },
                    tags=["validation_error", name, "invalid_arguments"],
                )
                failure_tracker.mark_recovered(
                    failure,
                    recovery_action="Validation error - executor will handle gracefully"
                )
            
            raise
        
        except Exception as e:
            # Unknown/unexpected error
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self.failure_count += 1
            
            if failure_tracker:
                failure = failure_tracker.record_failure(
                    category=FailureCategory.UNKNOWN,
                    severity=FailureSeverity.CRITICAL,
                    graph_node="executor",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    tool_name=name,
                    latency_ms=elapsed_ms,
                    error_traceback=traceback.format_exc(),
                    context_data={
                        "exception_type": type(e).__name__,
                        "tool_call_number": self.call_count,
                        "kwargs": kwargs,
                    },
                    tags=["unknown_error", name, "unexpected"],
                )
                failure_tracker.mark_recovered(
                    failure,
                    recovery_action="Unknown error - attempting recovery through executor exception handler"
                )
            
            raise
