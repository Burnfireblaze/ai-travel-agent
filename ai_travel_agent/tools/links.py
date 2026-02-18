from __future__ import annotations

import urllib.parse


def _q(s: str) -> str:
    return urllib.parse.quote_plus(s)


def google_flights_link(origin: str | None, destination: str, start_date: str | None = None) -> str:
    parts = ["Flights"]
    if origin:
        parts.append(f"from {origin}")
    parts.append(f"to {destination}")
    if start_date:
        parts.append(f"on {start_date}")
    q = " ".join(parts)
    return f"https://www.google.com/travel/flights?q={_q(q)}"


def skyscanner_link(origin: str | None, destination: str, start_date: str | None = None) -> str:
    parts = ["Skyscanner flights"]
    if origin:
        parts.append(origin)
    parts.append(destination)
    if start_date:
        parts.append(start_date)
    q = " ".join(parts)
    return f"https://www.skyscanner.com/transport/flights/?q={_q(q)}"


def site_search_link(domain: str, query: str) -> str:
    return f"https://www.google.com/search?q={_q(f'site:{domain} {query}')}"


def booking_hotels_link(destination: str, start_date: str | None = None, end_date: str | None = None) -> str:
    parts = [f"Hotels in {destination}"]
    if start_date and end_date:
        parts.append(f"{start_date} to {end_date}")
    q = " ".join(parts)
    return f"https://www.booking.com/searchresults.html?ss={_q(q)}"


def airbnb_search_link(destination: str) -> str:
    return f"https://www.airbnb.com/s/{_q(destination)}/homes"


def google_maps_search_link(query: str) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={_q(query)}"


def google_maps_directions_link(origin: str, destination: str, mode: str | None = None) -> str:
    params = {"api": "1", "origin": origin, "destination": destination}
    if mode:
        params["travelmode"] = mode
    return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(params)
