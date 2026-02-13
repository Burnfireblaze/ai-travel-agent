from __future__ import annotations

from typing import Any, Mapping

from .links import google_maps_directions_link


def distance_and_time(*, origin: str, destination: str, mode: str = "driving") -> Mapping[str, Any]:
    link = google_maps_directions_link(origin, destination, mode=mode)
    return {
        "summary": "Directions link (exact travel time not computed in this MVP).",
        "links": [{"label": "Google Maps directions", "url": link}],
        "mode": mode,
        "origin": origin,
        "destination": destination,
    }

