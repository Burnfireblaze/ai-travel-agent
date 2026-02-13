from __future__ import annotations

from ai_travel_agent.evaluation import evaluate_final
from ai_travel_agent.tools.calendar_ics import create_itinerary_ics


def test_evaluation_rejects_prices():
    constraints = {"destinations": ["Tokyo"], "start_date": "2026-03-01", "end_date": "2026-03-03"}
    ics = create_itinerary_ics(trip_name="Tokyo", start_date="2026-03-01", end_date="2026-03-03")
    answer = """
## Summary
Trip to Tokyo.
## Assumptions
Budget: budget
Travelers: travelers
Origin: origin
## Flights
$499 flight found
Note: Visa/health requirements vary; verify with official sources (this is not legal advice).
"""
    result = evaluate_final(constraints=constraints, final_answer=answer, ics_bytes=ics["ics_bytes"], eval_threshold=3.5)
    assert result.hard_gates["no_fabricated_real_time_facts"] is False


def test_evaluation_accepts_links_only():
    constraints = {
        "origin": "SFO",
        "destinations": ["Bangkok"],
        "start_date": "2026-03-01",
        "end_date": "2026-03-03",
        "budget_usd": None,
        "travelers": None,
    }
    ics = create_itinerary_ics(trip_name="Bangkok", start_date="2026-03-01", end_date="2026-03-03")
    answer = """
# Trip plan
## Summary
Trip to Bangkok.
## Assumptions
budget travelers
## Flights
Links only: https://www.google.com/travel/flights?q=Flights+to+Bangkok
## Lodging
https://www.booking.com/searchresults.html?ss=Hotels+in+Bangkok
## Day-by-day
- Day 1: Arrival
## Transit
Use public transit.
## Weather
Check weather.
## Budget
Estimate only.
## Calendar
ICS exported.
Note: Visa/health requirements vary; verify with official sources (this is not legal advice).
"""
    result = evaluate_final(constraints=constraints, final_answer=answer, ics_bytes=ics["ics_bytes"], eval_threshold=1.0)
    assert all(result.hard_gates.values())

