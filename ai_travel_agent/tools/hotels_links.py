from __future__ import annotations

from typing import Any, Mapping

import os

from .amadeus import fetch_top_hotels
from .links import airbnb_search_link, booking_hotels_link, google_maps_search_link, site_search_link


def hotels_search_links(
    *,
    destination: str,
    start_date: str | None,
    end_date: str | None,
    neighborhood: str | None = None,
    travelers: int | None = None,
) -> Mapping[str, Any]:
    q = f"Hotels in {destination}"
    if neighborhood:
        q = f"{q} near {neighborhood}"
    top_results: list[dict[str, str]] = []
    note = ""
    if destination and start_date and end_date:
        try:
            top_results = fetch_top_hotels(
                destination=destination,
                start_date=start_date,
                end_date=end_date,
                travelers=travelers or 1,
            )
        except Exception as exc:
            note = f" Live offers unavailable ({exc})."
        if not top_results and not note:
            note = " Live offers unavailable (no results returned)."
    else:
        note = " Live offers unavailable (missing destination/dates)."
    if not os.getenv("AMADEUS_CLIENT_ID") or not os.getenv("AMADEUS_CLIENT_SECRET"):
        if not note:
            note = " Live offers unavailable (Amadeus keys not set)."
    links = [
        {"label": "Booking.com", "url": booking_hotels_link(destination, start_date, end_date)},
        {"label": "Hotels.com", "url": site_search_link("hotels.com", q)},
        {"label": "Expedia", "url": site_search_link("expedia.com", q)},
        {"label": "Airbnb", "url": airbnb_search_link(destination)},
        {"label": "Google Maps (hotels)", "url": google_maps_search_link(q)},
    ]
    return {
        "summary": f"Top 5 hotel results (via Amadeus when configured) + search links.{note}",
        "links": links,
        "top_results": top_results,
    }
