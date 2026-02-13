from __future__ import annotations

from typing import Any, Mapping

from .links import booking_hotels_link, google_maps_search_link


def hotels_search_links(
    *,
    destination: str,
    start_date: str | None,
    end_date: str | None,
    neighborhood: str | None = None,
) -> Mapping[str, Any]:
    q = f"Hotels in {destination}"
    if neighborhood:
        q = f"{q} near {neighborhood}"
    links = [
        {"label": "Booking.com", "url": booking_hotels_link(destination, start_date, end_date)},
        {"label": "Google Maps (hotels)", "url": google_maps_search_link(q)},
    ]
    return {"summary": "Hotel search links (no booking in this MVP).", "links": links}

