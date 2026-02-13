from __future__ import annotations

from icalendar import Calendar

from ai_travel_agent.tools.calendar_ics import create_itinerary_ics


def test_ics_parses():
    out = create_itinerary_ics(trip_name="Test", start_date="2026-01-01", end_date="2026-01-02")
    cal = Calendar.from_ical(out["ics_bytes"])
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    assert len(events) >= 2

