from __future__ import annotations

from typing import Any, Mapping

from .links import google_flights_link, skyscanner_link


def flights_search_links(*, origin: str | None, destination: str, start_date: str | None) -> Mapping[str, Any]:
    links = [
        {"label": "Google Flights", "url": google_flights_link(origin, destination, start_date)},
        {"label": "Skyscanner", "url": skyscanner_link(origin, destination, start_date)},
    ]
    return {
        "summary": "Flight search links (prices/availability not fetched in this MVP).",
        "links": links,
    }

