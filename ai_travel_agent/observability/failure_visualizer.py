"""
Failure visualization and reporting utilities.
Display failures in human-readable formats with rich formatting.
"""

import json
from pathlib import Path
from typing import List, Optional
from datetime import datetime

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.tree import Tree
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


def format_failure_record(failure_dict: dict) -> str:
    """Format a single failure record as readable text."""
    lines = []
    lines.append(f"[FAILURE] {failure_dict.get('failure_id')}")
    lines.append(f"  Time: {failure_dict.get('timestamp')}")
    lines.append(f"  Severity: {failure_dict.get('severity').upper()}")
    lines.append(f"  Category: {failure_dict.get('category').upper()}")
    lines.append(f"  Node: {failure_dict.get('graph_node')}")
    
    if failure_dict.get("step_title"):
        lines.append(f"  Step: {failure_dict.get('step_title')}")
    
    lines.append(f"  Error Type: {failure_dict.get('error_type')}")
    lines.append(f"  Error Message: {failure_dict.get('error_message')}")
    
    if failure_dict.get("tool_name"):
        lines.append(f"  Tool: {failure_dict.get('tool_name')}")
    
    if failure_dict.get("llm_model"):
        lines.append(f"  LLM: {failure_dict.get('llm_model')}")
    
    lines.append(f"  Latency: {failure_dict.get('latency_ms', 0):.2f}ms")
    lines.append(f"  Recovered: {'Yes' if failure_dict.get('was_recovered') else 'No'}")
    
    if failure_dict.get("recovery_action"):
        lines.append(f"  Recovery: {failure_dict.get('recovery_action')}")
    
    if failure_dict.get("tags"):
        lines.append(f"  Tags: {', '.join(failure_dict.get('tags', []))}")
    
    return "\n".join(lines)


class FailureVisualizer:
    """Visualize failures with rich formatting if available."""
    
    def __init__(self, console: Optional['Console'] = None):
        self.console = console or (Console() if RICH_AVAILABLE else None)
    
    def print_failure_record(self, failure_dict: dict) -> None:
        """Print a failure record using rich formatting."""
        if not self.console:
            print(format_failure_record(failure_dict))
            return
        
        # Build color-coded panel based on severity
        severity = failure_dict.get("severity", "unknown").lower()
        color_map = {
            "low": "yellow",
            "medium": "yellow",
            "high": "red",
            "critical": "red",
        }
        border_color = color_map.get(severity, "white")
        
        content = f"""
[bold]{failure_dict.get('failure_id')}[/bold]

[cyan]Timing:[/cyan]
  Timestamp: {failure_dict.get('timestamp')}
  Latency: {failure_dict.get('latency_ms', 0):.2f}ms

[cyan]Classification:[/cyan]
  Severity: [{border_color}]{failure_dict.get('severity').upper()}[/{border_color}]
  Category: {failure_dict.get('category').upper()}

[cyan]Location:[/cyan]
  Node: {failure_dict.get('graph_node')}
  Step: {failure_dict.get('step_title', 'N/A')}
  Step Type: {failure_dict.get('step_type', 'N/A')}

[cyan]Error Details:[/cyan]
  Type: [red]{failure_dict.get('error_type')}[/red]
  Message: {failure_dict.get('error_message')}

[cyan]Component:[/cyan]
  Tool: {failure_dict.get('tool_name', 'N/A')}
  LLM: {failure_dict.get('llm_model', 'N/A')}

[cyan]Recovery:[/cyan]
  Recovered: [green]Yes[/green] if {failure_dict.get('was_recovered')} else [yellow]No[/yellow]
  Action: {failure_dict.get('recovery_action', 'N/A')}

[cyan]Tags:[/cyan]
  {', '.join(failure_dict.get('tags', []))}
"""
        
        self.console.print(Panel(
            content,
            title="Failure Record",
            border_style=border_color,
            expand=False
        ))
    
    def print_failure_timeline(self, failures: List[dict]) -> None:
        """Print failures in timeline format."""
        if not self.console:
            for i, f in enumerate(failures, 1):
                print(f"\n{i}. {format_failure_record(f)}\n")
            return
        
        sorted_failures = sorted(failures, key=lambda f: f.get("timestamp", ""))
        
        tree = Tree("Failure Timeline")
        
        for failure in sorted_failures:
            severity = failure.get("severity", "unknown").lower()
            color = {
                "low": "yellow",
                "medium": "yellow",
                "high": "red",
                "critical": "red",
            }.get(severity, "white")
            
            timestamp = failure.get("timestamp", "")
            error_type = failure.get("error_type", "Unknown")
            node = failure.get("graph_node", "")
            
            label = f"[{color}]{failure.get('severity').upper()}[/{color}] {timestamp} | {error_type} @ {node}"
            
            node_obj = tree.add(label)
            node_obj.add(f"Message: {failure.get('error_message')}")
            
            if failure.get("tool_name"):
                node_obj.add(f"Tool: {failure.get('tool_name')}")
            
            if failure.get("latency_ms"):
                node_obj.add(f"Latency: {failure.get('latency_ms'):.2f}ms")
            
            if failure.get("was_recovered"):
                node_obj.add(f"[green]✓ Recovered[/green]: {failure.get('recovery_action')}")
        
        self.console.print(tree)
    
    def print_summary(self, summary: dict) -> None:
        """Print failure summary statistics."""
        if not self.console:
            print(json.dumps(summary, indent=2))
            return
        
        table = Table(title="Failure Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="magenta")
        
        table.add_row("Run ID", summary.get("run_id", ""))
        table.add_row("Total Failures", str(summary.get("total_failures", 0)))
        table.add_row("Recovery Rate", f"{summary.get('recovery_rate', 0):.1f}%")
        
        # Severity breakdown
        for severity, count in sorted(summary.get("by_severity", {}).items()):
            table.add_row(f"  {severity.capitalize()}", str(count))
        
        # Category breakdown
        for category, count in sorted(summary.get("by_category", {}).items()):
            table.add_row(f"  {category.upper()}", str(count))
        
        # Node breakdown
        for node, count in sorted(summary.get("by_node", {}).items()):
            table.add_row(f"  {node}", str(count))
        
        self.console.print(table)


def load_failure_log(log_path: Path) -> List[dict]:
    """Load failure records from JSONL log file."""
    failures = []
    
    if not log_path.exists():
        return failures
    
    try:
        with log_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        failure = json.loads(line)
                        failures.append(failure)
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        print(f"Error reading failure log: {e}")
    
    return failures


def display_failure_report(log_path: Path, verbose: bool = False) -> None:
    """Load and display complete failure report."""
    failures = load_failure_log(log_path)
    
    if not failures:
        print(f"No failures found in {log_path}")
        return
    
    visualizer = FailureVisualizer()
    
    # Calculate summary
    severity_counts = {}
    category_counts = {}
    node_counts = {}
    recovered_count = 0
    
    for f in failures:
        severity = f.get("severity", "unknown")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        category = f.get("category", "unknown")
        category_counts[category] = category_counts.get(category, 0) + 1
        
        node = f.get("graph_node", "unknown")
        node_counts[node] = node_counts.get(node, 0) + 1
        
        if f.get("was_recovered"):
            recovered_count += 1
    
    summary = {
        "total_failures": len(failures),
        "by_severity": severity_counts,
        "by_category": category_counts,
        "by_node": node_counts,
        "recovery_rate": (recovered_count / len(failures) * 100) if failures else 0,
    }
    
    # Print summary
    print("\n" + "="*70)
    print("FAILURE REPORT")
    print("="*70)
    visualizer.print_summary(summary)
    
    # Print timeline
    print("\n" + "="*70)
    print("FAILURE TIMELINE")
    print("="*70)
    visualizer.print_failure_timeline(failures)
    
    # Print detailed records if verbose
    if verbose:
        print("\n" + "="*70)
        print("DETAILED FAILURE RECORDS")
        print("="*70)
        for failure in failures:
            visualizer.print_failure_record(failure)
            print()
