from __future__ import annotations

import pytest

from ai_travel_agent.observability.fault_injection import FaultInjector


def test_fault_injector_tool_error():
    fi = FaultInjector(simulate_tool_error=True, probability=1.0, failure_seed=1)
    with pytest.raises(RuntimeError):
        fi.maybe_inject_tool_error("flights_search_links")


def test_fault_injector_bad_retrieval_empty():
    fi = FaultInjector(simulate_bad_retrieval=True, probability=1.0, bad_retrieval_mode="empty")
    hits = fi.maybe_inject_bad_retrieval("test query")
    assert hits == []


def test_fault_injector_bad_retrieval_garbage():
    fi = FaultInjector(simulate_bad_retrieval=True, probability=1.0, bad_retrieval_mode="garbage")
    hits = fi.maybe_inject_bad_retrieval("test query")
    assert isinstance(hits, list)
    assert hits and "Injected unrelated content" in hits[0]["text"]
