from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from icalendar import Calendar, Event


def _parse_date(d: str) -> date:
    return date.fromisoformat(d)


def create_itinerary_ics(
    *,
    trip_name: str,
    start_date: str,
    end_date: str,
    day_titles: list[str] | None = None,
) -> Mapping[str, Any]:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if end < start:
        start, end = end, start

    days = (end - start).days + 1
    titles = day_titles or [f"Trip day {i+1}" for i in range(days)]
    titles = (titles + [titles[-1]] * days)[:days]

    cal = Calendar()
    cal.add("prodid", "-//AI Travel Agent//")
    cal.add("version", "2.0")

    for i in range(days):
        d = start + timedelta(days=i)
        ev = Event()
        ev.add("summary", f"{trip_name}: {titles[i]}")
        ev.add("dtstart", d)
        ev.add("dtend", d + timedelta(days=1))
        ev.add("dtstamp", datetime.now(timezone.utc))
        cal.add_component(ev)

    return {
        "summary": "ICS calendar generated.",
        "ics_bytes": cal.to_ical(),
        "event_count": days,
    }


def write_ics_bytes(*, ics_bytes: bytes, runtime_dir: Path, filename: str) -> Path:
    artifacts_dir = (runtime_dir / "artifacts").resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    path = artifacts_dir / filename
    path.write_bytes(ics_bytes)
    return path

