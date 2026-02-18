from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


def _http_get_json(url: str, timeout_s: float = 8.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "ai-travel-agent/0.1"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


@dataclass(frozen=True)
class GeocodeCandidate:
    name: str
    country: str | None
    admin1: str | None
    latitude: float
    longitude: float
    timezone: str | None


def geocode_place(query: str, *, count: int = 5, language: str = "en") -> dict[str, Any]:
    """
    Geocode a place string using Open-Meteo's geocoding API.

    Returns:
      {
        "query": str,
        "candidates": [{name,country,admin1,latitude,longitude,timezone}],
        "best": {...} | null,
        "ambiguous": bool
      }
    """
    url = (
        "https://geocoding-api.open-meteo.com/v1/search?"
        + urllib.parse.urlencode({"name": query, "count": count, "language": language, "format": "json"})
    )
    data = _http_get_json(url)
    results = data.get("results") or []

    candidates: list[dict[str, Any]] = []
    for r in results:
        try:
            candidates.append(
                {
                    "name": r.get("name"),
                    "country": r.get("country"),
                    "admin1": r.get("admin1"),
                    "latitude": float(r.get("latitude")),
                    "longitude": float(r.get("longitude")),
                    "timezone": r.get("timezone"),
                }
            )
        except Exception:
            continue

    best = candidates[0] if candidates else None

    def norm(s: Any) -> str:
        return str(s or "").strip().lower()

    # Safe auto-pick heuristic for country queries like "Peru" where results include cities named "Peru".
    country_matches = [
        c
        for c in candidates
        if norm(c.get("name")) == norm(query)
        and norm(c.get("country")) == norm(query)
        and not norm(c.get("admin1"))
    ]
    autopicked_reason: str | None = None
    if len(country_matches) == 1:
        best = country_matches[0]
        autopicked_reason = "country_match"

    # Simple ambiguity heuristic:
    # if top 2 have same name but different country/admin region and query doesn't include a comma (often "City, Country")
    ambiguous = False
    q = (query or "").strip()
    if autopicked_reason is None and len(candidates) >= 2 and "," not in q:
        a, b = candidates[0], candidates[1]
        if (a.get("name") or "").lower() == (b.get("name") or "").lower():
            if (a.get("country") != b.get("country")) or (a.get("admin1") != b.get("admin1")):
                ambiguous = True

    best_similarity = None
    if best is not None:
        best_similarity = round(SequenceMatcher(a=norm(query), b=norm(best.get("name"))).ratio(), 3)

    return {
        "query": query,
        "candidates": candidates,
        "best": best,
        "ambiguous": ambiguous,
        "best_similarity": best_similarity,
        "autopicked_reason": autopicked_reason,
    }
