from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Mapping


def _http_get_json(url: str, timeout_s: float = 8.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "ai-travel-agent/0.1"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def weather_summary(*, destination: str, start_date: str | None, end_date: str | None) -> Mapping[str, Any]:
    if not start_date or not end_date:
        return {
            "summary": "Weather requires dates; providing seasonal guidance instead.",
            "details": f"Search: '{destination} weather by month' for seasonal norms.",
            "links": [
                {
                    "label": "Weather search",
                    "url": f"https://www.google.com/search?q={urllib.parse.quote_plus(destination + ' weather')}",
                }
            ],
        }

    try:
        geo_url = (
            "https://geocoding-api.open-meteo.com/v1/search?"
            + urllib.parse.urlencode({"name": destination, "count": 1, "language": "en", "format": "json"})
        )
        geo = _http_get_json(geo_url)
        results = geo.get("results") or []
        if not results:
            raise RuntimeError("No geocoding results")
        lat = results[0]["latitude"]
        lon = results[0]["longitude"]

        fc_url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
            {
                "latitude": lat,
                "longitude": lon,
                "start_date": start_date,
                "end_date": end_date,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
                "timezone": "auto",
            }
        )
        fc = _http_get_json(fc_url)
        daily = fc.get("daily", {})
        if not daily:
            raise RuntimeError("No forecast data")
        temps_max = daily.get("temperature_2m_max", [])
        temps_min = daily.get("temperature_2m_min", [])
        precip = daily.get("precipitation_sum", [])
        if temps_max and temps_min:
            summary = f"Forecast highs ~{min(temps_max):.0f}–{max(temps_max):.0f}°C; lows ~{min(temps_min):.0f}–{max(temps_min):.0f}°C."
        else:
            summary = "Weather forecast fetched."
        if precip:
            summary += f" Total precipitation over range ~{sum(precip):.0f}mm."
        return {"summary": summary, "daily": daily, "source": "open-meteo"}
    except Exception:
        return {
            "summary": "Unable to fetch live weather; providing seasonal guidance links instead.",
            "details": "Network may be unavailable or the provider could not be reached.",
            "links": [
                {
                    "label": "Weather search",
                    "url": f"https://www.google.com/search?q={urllib.parse.quote_plus(destination + ' weather ' + start_date)}",
                }
            ],
        }

