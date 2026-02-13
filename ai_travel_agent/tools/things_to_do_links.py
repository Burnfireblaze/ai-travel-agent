from __future__ import annotations

from typing import Any, Mapping

from .links import google_maps_search_link


def things_to_do_links(*, destination: str, interests: list[str] | None = None) -> Mapping[str, Any]:
    interests = interests or []
    queries = [f"Things to do in {destination}"] + [f"{interest} in {destination}" for interest in interests[:5]]
    links = [{"label": q, "url": google_maps_search_link(q)} for q in queries]
    return {"summary": "Things-to-do discovery links.", "links": links}

