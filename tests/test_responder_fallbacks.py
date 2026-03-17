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


def test_responder_keeps_budget_numbers_and_sanitizes_other_prices():
    state = {
        "constraints": {
            "origin": "NYC",
            "destinations": ["Japan"],
            "start_date": "2026-04-05",
            "end_date": "2026-04-14",
            "budget_usd": 3500,
            "travelers": 2,
        },
        "final_answer": """
# Trip plan
## Summary
Budget is $3,500 for 2 travelers.
## Flights
- One route was $1,200.
## Lodging
- Search links only.
## Day-by-day
- Day 1: Arrival.
## Transit
- Narita Express costs ¥3,000.
## Weather
- Mild weather.
## Budget
- Flights: ~$1,400
## Calendar
- .ics export pending.
""",
        "tool_results": [],
    }
    out = responder(state)
    answer = out["final_answer"]
    budget_section = answer.split("## Budget", 1)[1].split("## Calendar", 1)[0]
    assert "~$3,500" in budget_section
    assert "~$1,400" in budget_section
    assert "Budget is [price omitted]" in answer
    assert "costs [price omitted]" in answer
    assert "~,000" not in answer
