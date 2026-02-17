"""
Failure Tracking & Visualization System
Captures, tags, and displays failures with full context and trace information.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import defaultdict


class FailureSeverity(Enum):
    """Severity levels for failures."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FailureCategory(Enum):
    """Categories of failures."""
    LLM = "llm"
    TOOL = "tool"
    MEMORY = "memory"
    NETWORK = "network"
    VALIDATION = "validation"
    STATE = "state"
    EXPORT = "export"
    EVALUATION = "evaluation"
    UNKNOWN = "unknown"


@dataclass
class FailureRecord:
    """Complete failure information with context."""
    failure_id: str
    timestamp: str
    run_id: str
    user_id: str
    category: str  # FailureCategory enum value
    severity: str  # FailureSeverity enum value
    
    # Where it occurred
    graph_node: str  # Which node (executor, intent_parser, etc.)
    step_id: Optional[str] = None
    step_type: Optional[str] = None
    step_title: Optional[str] = None
    
    # What happened
    error_type: str = ""  # Exception class name
    error_message: str = ""
    error_traceback: Optional[str] = None
    
    # Tool/LLM specific
    tool_name: Optional[str] = None
    llm_model: Optional[str] = None
    
    # Metrics
    latency_ms: float = 0.0
    attempt_number: int = 1
    
    # Recovery info
    was_recovered: bool = False
    recovery_action: Optional[str] = None
    
    # Context at time of failure
    context_data: Dict[str, Any] = field(default_factory=dict)
    
    # Tags for searching/filtering
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


@dataclass
class FailureChain:
    """Chain of related failures in a single run."""
    run_id: str
    failures: List[FailureRecord] = field(default_factory=list)
    
    def add_failure(self, failure: FailureRecord) -> None:
        """Add failure to chain."""
        self.failures.append(failure)
    
    def get_critical_failures(self) -> List[FailureRecord]:
        """Get all critical failures."""
        return [f for f in self.failures if f.severity == FailureSeverity.CRITICAL.value]
    
    def get_failures_by_node(self, node_name: str) -> List[FailureRecord]:
        """Get failures from specific node."""
        return [f for f in self.failures if f.graph_node == node_name]
    
    def get_failure_timeline(self) -> List[FailureRecord]:
        """Get failures in chronological order."""
        return sorted(self.failures, key=lambda f: f.timestamp)
    
    def summary(self) -> Dict[str, Any]:
        """Get summary of failure chain."""
        return {
            "run_id": self.run_id,
            "total_failures": len(self.failures),
            "critical_count": len(self.get_critical_failures()),
            "failures_by_category": self._count_by_category(),
            "failures_by_node": self._count_by_node(),
            "recovery_rate": self._calculate_recovery_rate(),
            "timeline": [f.timestamp for f in self.get_failure_timeline()],
        }
    
    def _count_by_category(self) -> Dict[str, int]:
        """Count failures by category."""
        counts: Dict[str, int] = defaultdict(int)
        for f in self.failures:
            counts[f.category] += 1
        return dict(counts)
    
    def _count_by_node(self) -> Dict[str, int]:
        """Count failures by node."""
        counts: Dict[str, int] = defaultdict(int)
        for f in self.failures:
            counts[f.graph_node] += 1
        return dict(counts)
    
    def _calculate_recovery_rate(self) -> float:
        """Calculate percentage of failures that were recovered."""
        if not self.failures:
            return 0.0
        recovered = sum(1 for f in self.failures if f.was_recovered)
        return (recovered / len(self.failures)) * 100


class FailureTracker:
    """
    Central registry for all failures in a run.
    Tracks, logs, and provides analytics on failures.
    """
    
    def __init__(self, run_id: str, user_id: str, runtime_dir: Path):
        self.run_id = run_id
        self.user_id = user_id
        self.runtime_dir = runtime_dir
        self.failure_count = 0
        self.failures: List[FailureRecord] = []
        self.failure_chain = FailureChain(run_id=run_id)
        self.failure_log_path = runtime_dir / "logs" / f"failures_{run_id}.jsonl"
        self.combined_log_path = runtime_dir / "logs" / f"combined_{run_id}.jsonl"
        self.failure_log_path.parent.mkdir(parents=True, exist_ok=True)
    
    def record_failure(
        self,
        *,
        category: FailureCategory,
        severity: FailureSeverity,
        graph_node: str,
        error_type: str,
        error_message: str,
        step_id: Optional[str] = None,
        step_type: Optional[str] = None,
        step_title: Optional[str] = None,
        tool_name: Optional[str] = None,
        llm_model: Optional[str] = None,
        latency_ms: float = 0.0,
        error_traceback: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> FailureRecord:
        """
        Record a failure with full context.
        
        Returns the FailureRecord for further updates.
        """
        failure_id = f"failure_{self.run_id}_{self.failure_count:03d}"
        self.failure_count += 1
        
        failure = FailureRecord(
            failure_id=failure_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            run_id=self.run_id,
            user_id=self.user_id,
            category=category.value,
            severity=severity.value,
            graph_node=graph_node,
            step_id=step_id,
            step_type=step_type,
            step_title=step_title,
            error_type=error_type,
            error_message=error_message,
            error_traceback=error_traceback,
            tool_name=tool_name,
            llm_model=llm_model,
            latency_ms=latency_ms,
            context_data=context_data or {},
            tags=tags or [],
        )
        
        self.failures.append(failure)
        self.failure_chain.add_failure(failure)
        self._write_failure_log(failure, event="failure_recorded")
        
        return failure
    
    def mark_recovered(
        self,
        failure: FailureRecord,
        recovery_action: str
    ) -> None:
        """Mark a failure as recovered with recovery action."""
        failure.was_recovered = True
        failure.recovery_action = recovery_action
        self._write_failure_log(failure, event="failure_recovered")

    def _write_failure_log(self, failure: FailureRecord, *, event: str) -> None:
        """Write failure to JSONL log file."""
        try:
            with self.failure_log_path.open("a", encoding="utf-8") as f:
                f.write(failure.to_json() + "\n")
            self._write_combined_log(
                event=event,
                data={
                    "failure_id": failure.failure_id,
                    "category": failure.category,
                    "severity": failure.severity,
                    "error_type": failure.error_type,
                    "error_message": failure.error_message,
                    "tool_name": failure.tool_name,
                    "step_id": failure.step_id,
                    "step_type": failure.step_type,
                    "step_title": failure.step_title,
                    "latency_ms": failure.latency_ms,
                    "was_recovered": failure.was_recovered,
                    "recovery_action": failure.recovery_action,
                    "tags": list(failure.tags),
                },
                graph_node=failure.graph_node,
                step_id=failure.step_id,
                step_type=failure.step_type,
                step_title=failure.step_title,
            )
        except Exception as e:
            print(f"Warning: Failed to write failure log: {e}")

    def _write_combined_log(
        self,
        *,
        event: str,
        data: Dict[str, Any],
        graph_node: str,
        step_id: Optional[str],
        step_type: Optional[str],
        step_title: Optional[str],
    ) -> None:
        """Write a failure event into the run-level combined log."""
        try:
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "ERROR",
                "module": "ai_travel_agent.observability.failure_tracker",
                "message": "Failure tracker event",
                "run_id": self.run_id,
                "user_id": self.user_id,
                "graph_node": graph_node,
                "step_id": step_id,
                "step_type": step_type,
                "step_title": step_title,
                "event": event,
                "kind": "failure",
                "data": data,
            }
            with self.combined_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        except Exception:
            # Never fail main flow due to telemetry I/O errors.
            pass
    
    def get_summary(self) -> Dict[str, Any]:
        """Get comprehensive failure summary."""
        return {
            "run_id": self.run_id,
            "total_failures": len(self.failures),
            "by_severity": self._count_by_severity(),
            "by_category": self._count_by_category(),
            "by_node": self._count_by_node(),
            "recovery_rate": self._calculate_recovery_rate(),
            "log_file": str(self.failure_log_path),
        }
    
    def _count_by_severity(self) -> Dict[str, int]:
        """Count failures by severity."""
        counts: Dict[str, int] = defaultdict(int)
        for f in self.failures:
            counts[f.severity] += 1
        return dict(counts)
    
    def _count_by_category(self) -> Dict[str, int]:
        """Count failures by category."""
        counts: Dict[str, int] = defaultdict(int)
        for f in self.failures:
            counts[f.category] += 1
        return dict(counts)
    
    def _count_by_node(self) -> Dict[str, int]:
        """Count failures by node."""
        counts: Dict[str, int] = defaultdict(int)
        for f in self.failures:
            counts[f.graph_node] += 1
        return dict(counts)
    
    def _calculate_recovery_rate(self) -> float:
        """Calculate recovery rate."""
        if not self.failures:
            return 0.0
        recovered = sum(1 for f in self.failures if f.was_recovered)
        return (recovered / len(self.failures)) * 100
    
    def generate_report(self) -> str:
        """Generate human-readable failure report."""
        lines = [
            "\n" + "="*70,
            "FAILURE REPORT",
            "="*70,
            f"Run ID: {self.run_id}",
            f"User ID: {self.user_id}",
            f"Total Failures: {len(self.failures)}",
            "",
        ]
        
        summary = self.get_summary()
        
        lines.append("SUMMARY BY SEVERITY:")
        for severity, count in sorted(summary["by_severity"].items()):
            lines.append(f"  {severity.upper()}: {count}")
        
        lines.append("\nSUMMARY BY CATEGORY:")
        for category, count in sorted(summary["by_category"].items()):
            lines.append(f"  {category.upper()}: {count}")
        
        lines.append("\nSUMMARY BY NODE:")
        for node, count in sorted(summary["by_node"].items()):
            lines.append(f"  {node}: {count}")
        
        lines.append(f"\nRECOVERY RATE: {summary['recovery_rate']:.1f}%")
        
        lines.append("\nFAILURES IN TIMELINE ORDER:")
        lines.append("-" * 70)
        
        for i, failure in enumerate(self.failure_chain.get_failure_timeline(), 1):
            lines.append(f"\n{i}. [{failure.failure_id}]")
            lines.append(f"   Time: {failure.timestamp}")
            lines.append(f"   Severity: {failure.severity.upper()}")
            lines.append(f"   Category: {failure.category}")
            lines.append(f"   Node: {failure.graph_node}")
            if failure.step_title:
                lines.append(f"   Step: {failure.step_title}")
            lines.append(f"   Error: {failure.error_type}")
            lines.append(f"   Message: {failure.error_message}")
            if failure.tool_name:
                lines.append(f"   Tool: {failure.tool_name}")
            lines.append(f"   Latency: {failure.latency_ms:.2f}ms")
            if failure.was_recovered:
                lines.append(f"   Recovery: {failure.recovery_action}")
            if failure.tags:
                lines.append(f"   Tags: {', '.join(failure.tags)}")
        
        lines.append("\n" + "="*70)
        lines.append(f"Log file: {self.failure_log_path}")
        lines.append("="*70 + "\n")
        
        return "\n".join(lines)


# Global tracker (set by CLI)
_global_failure_tracker: Optional[FailureTracker] = None


def set_failure_tracker(tracker: Optional[FailureTracker]) -> None:
    """Set global failure tracker."""
    global _global_failure_tracker
    _global_failure_tracker = tracker


def get_failure_tracker() -> Optional[FailureTracker]:
    """Get global failure tracker."""
    return _global_failure_tracker
