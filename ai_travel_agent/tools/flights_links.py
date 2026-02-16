from __future__ import annotations

from typing import Any, Mapping

import os

from .amadeus import fetch_top_flights
from .links import google_flights_link, skyscanner_link, site_search_link


def flights_search_links(
    *,
    origin: str | None,
    destination: str,
    start_date: str | None,
    travelers: int | None = None,
) -> Mapping[str, Any]:
    query = " ".join([p for p in ["flights", f"from {origin}" if origin else None, f"to {destination}", start_date] if p])
    top_results: list[dict[str, str]] = []
    note = ""
    if origin and destination and start_date:
        try:
            top_results = fetch_top_flights(
                origin=origin,
                destination=destination,
                start_date=start_date,
                travelers=travelers or 1,
            )
        except Exception as exc:
            note = f" Live offers unavailable ({exc})."
        if not top_results and not note:
            note = " Live offers unavailable (no results returned)."
    else:
        note = " Live offers unavailable (missing origin/destination/date)."
    if not os.getenv("AMADEUS_CLIENT_ID") or not os.getenv("AMADEUS_CLIENT_SECRET"):
        if not note:
            note = " Live offers unavailable (Amadeus keys not set)."
    links = [
        {"label": "Google Flights", "url": google_flights_link(origin, destination, start_date)},
        {"label": "Skyscanner", "url": skyscanner_link(origin, destination, start_date)},
        {"label": "Kayak", "url": site_search_link("kayak.com", query)},
        {"label": "Expedia", "url": site_search_link("expedia.com", query)},
        {"label": "Momondo", "url": site_search_link("momondo.com", query)},
    ]
    return {
        "summary": f"Top 5 flight results (via Amadeus when configured) + search links.{note}",
        "links": links,
        "top_results": top_results,
    }
