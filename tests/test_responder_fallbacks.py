from __future__ import annotations

from ai_travel_agent.agents.nodes.responder import responder


def test_responder_replaces_not_available_with_links_and_skeleton():
    state = {
        "constraints": {
            "origin": "SFO",
            "destinations": ["India"],
            "start_date": "2026-02-16",
            "end_date": "2026-02-18",
            "budget_usd": None,
            "travelers": None,
        },
        "final_answer": """
# Trip plan
## Summary
Planning trip to India.
## Flights
- Not available.
## Lodging
- Not available.
## Day-by-day
- Not available.
## Transit
- Not available.
## Weather
- Not available.
## Budget
- Not available.
## Calendar
- Not available.
""",
        "tool_results": [],
    }
    out = responder(state)
    answer = out["final_answer"]
    assert "Not available" not in answer
    assert "http" in answer
    assert "## Day-by-day" in answer
    assert "## Calendar" in answer

