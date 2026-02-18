from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error
from typing import Any


_TOKEN_CACHE: dict[str, Any] = {"access_token": None, "expires_at": 0.0}

_CODE_FALLBACKS: dict[str, list[str]] = {
    "japan": ["TYO", "HND", "NRT", "OSA", "KIX"],
    "tokyo": ["TYO", "HND", "NRT"],
    "osaka": ["OSA", "KIX"],
    "united states": ["NYC", "LAX", "CHI"],
    "usa": ["NYC", "LAX", "CHI"],
    "nyc": ["NYC", "JFK", "EWR", "LGA"],
    "new york": ["NYC", "JFK", "EWR", "LGA"],
    "india": ["DEL", "BOM"],
    "france": ["PAR"],
    "united kingdom": ["LON"],
    "uk": ["LON"],
    "spain": ["MAD", "BCN"],
    "italy": ["ROM", "MIL"],
    "germany": ["BER", "MUC"],
    "thailand": ["BKK", "HKT"],
    "singapore": ["SIN"],
    "australia": ["SYD", "MEL"],
    "canada": ["YTO", "YVR"],
    "mexico": ["MEX"],
    "brazil": ["RIO", "SAO"],
    "argentina": ["BUE"],
    "portugal": ["LIS"],
    "lisbon": ["LIS"],
    "netherlands": ["AMS"],
    "uae": ["DXB"],
    "united arab emirates": ["DXB"],
    "turkey": ["IST"],
    "indonesia": ["JKT", "DPS"],
    "philippines": ["MNL"],
    "vietnam": ["SGN", "HAN"],
    "south korea": ["SEL"],
    "china": ["BJS", "SHA"],
}


def _amadeus_base_url() -> str:
    return os.getenv("AMADEUS_BASE_URL", "https://test.api.amadeus.com").rstrip("/")


def _http_post_form(url: str, data: dict[str, str], timeout_s: float = 10.0) -> dict[str, Any]:
    payload = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "ai-travel-agent/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = ""
        try:
            body = err.read().decode("utf-8")
        except Exception:
            body = ""
        if body:
            try:
                return json.loads(body)
            except Exception:
                return {"errors": [{"title": f"HTTP {err.code}", "detail": body[:200]}]}
        raise


def _http_get_json(url: str, headers: dict[str, str], timeout_s: float = 10.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={**headers, "User-Agent": "ai-travel-agent/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = ""
        try:
            body = err.read().decode("utf-8")
        except Exception:
            body = ""
        if body:
            try:
                return json.loads(body)
            except Exception:
                return {"errors": [{"title": f"HTTP {err.code}", "detail": body[:200]}]}
        raise


def _get_access_token() -> str | None:
    client_id = os.getenv("AMADEUS_CLIENT_ID", "").strip()
    client_secret = os.getenv("AMADEUS_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None

    now = time.time()
    token = _TOKEN_CACHE.get("access_token")
    expires_at = float(_TOKEN_CACHE.get("expires_at") or 0.0)
    if token and now < (expires_at - 30):
        return token

    url = f"{_amadeus_base_url()}/v1/security/oauth2/token"
    data = _http_post_form(
        url,
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    token = data.get("access_token")
    expires_in = int(data.get("expires_in") or 0)
    if not token:
        return None
    _TOKEN_CACHE["access_token"] = token
    _TOKEN_CACHE["expires_at"] = now + max(0, expires_in)
    return token


def _amadeus_get(endpoint: str, params: dict[str, str]) -> dict[str, Any] | None:
    token = _get_access_token()
    if not token:
        return None
    url = f"{_amadeus_base_url()}{endpoint}?{urllib.parse.urlencode(params)}"
    data = _http_get_json(url, headers={"Authorization": f"Bearer {token}"})
    if isinstance(data, dict) and data.get("errors"):
        err = (data.get("errors") or [{}])[0]
        title = str(err.get("title") or "Amadeus error")
        detail = str(err.get("detail") or err.get("code") or "")
        code = str(err.get("code") or "")
        lowered = f"{title} {detail}".lower()
        if code in {"141", "179"} or "no data" in lowered or "not found" in lowered or "no results" in lowered:
            return {"data": []}
        raise RuntimeError(f"{title}: {detail}".strip(": "))
    return data


def _dedupe_codes(codes: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for c in codes:
        code = c.strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def resolve_location_codes(query: str) -> list[str]:
    q = (query or "").strip()
    if not q:
        return []
    codes: list[str] = []
    if len(q) == 3 and q.isalpha():
        codes.append(q.upper())
    data = None
    try:
        data = _amadeus_get(
            "/v1/reference-data/locations",
            {
                "keyword": q,
                "subType": "AIRPORT,CITY",
                "view": "LIGHT",
                "sort": "analytics.travelers.score",
                "page[limit]": "5",
            },
        )
    except Exception:
        data = None
    if data:
        items = data.get("data") or []
        if isinstance(items, list) and items:
            for it in items:
                if (it or {}).get("subType") == "CITY" and it.get("iataCode"):
                    codes.append(it["iataCode"])
            for it in items:
                if it.get("iataCode"):
                    codes.append(it["iataCode"])
    norm = q.lower()
    if norm in _CODE_FALLBACKS:
        codes.extend(_CODE_FALLBACKS[norm])
    parts = [p.strip() for p in norm.split(",") if p.strip()]
    for part in parts:
        if part in _CODE_FALLBACKS:
            codes.extend(_CODE_FALLBACKS[part])
    return _dedupe_codes(codes)


def resolve_location_code(query: str) -> str | None:
    codes = resolve_location_codes(query)
    return codes[0] if codes else None


def _fetch_hotels_by_city(city_code: str, limit: int = 20) -> list[dict[str, Any]]:
    if not city_code:
        return []
    try:
        data = _amadeus_get(
            "/v1/reference-data/locations/hotels/by-city",
            {
                "cityCode": city_code,
            },
        )
    except Exception:
        return []
    if not data:
        return []
    items = data.get("data") or []
    if not isinstance(items, list):
        return []
    hotels: list[dict[str, Any]] = []
    for it in items:
        hotel_id = (it or {}).get("hotelId")
        if not isinstance(hotel_id, str) or not hotel_id.strip():
            continue
        name = (it or {}).get("name") or (it or {}).get("hotelName") or ""
        address = (it or {}).get("address") or {}
        country_code = address.get("countryCode") or address.get("country") or ""
        city_name = address.get("cityName") or ""
        geo = (it or {}).get("geoCode") or {}
        hotels.append(
            {
                "hotelId": hotel_id.strip(),
                "name": str(name).strip(),
                "countryCode": str(country_code).strip().upper() if country_code else "",
                "cityName": str(city_name).strip(),
                "latitude": geo.get("latitude"),
                "longitude": geo.get("longitude"),
            }
        )
        if len(hotels) >= limit:
            break
    return hotels


def _resolve_city_meta(city_code: str) -> dict[str, Any]:
    if not city_code:
        return {}
    try:
        data = _amadeus_get(
            "/v1/reference-data/locations",
            {
                "keyword": city_code,
                "subType": "CITY",
                "view": "LIGHT",
                "page[limit]": "5",
            },
        )
    except Exception:
        return {}
    if not data:
        return {}
    items = data.get("data") or []
    if not isinstance(items, list):
        return {}
    for it in items:
        if not isinstance(it, dict):
            continue
        if (it.get("iataCode") or "").upper() != city_code.upper():
            continue
        address = it.get("address") or {}
        geo = it.get("geoCode") or {}
        return {
            "name": it.get("name") or "",
            "countryCode": (address.get("countryCode") or "").upper(),
            "latitude": geo.get("latitude"),
            "longitude": geo.get("longitude"),
        }
    return {}


def fetch_top_flights(
    *,
    origin: str,
    destination: str,
    start_date: str,
    travelers: int = 1,
    currency: str = "USD",
    limit: int = 5,
) -> list[dict[str, str]]:
    origin_codes = resolve_location_codes(origin)
    dest_codes = resolve_location_codes(destination)
    if not origin_codes or not dest_codes:
        return []

    for origin_code in origin_codes:
        for dest_code in dest_codes:
            data = _amadeus_get(
                "/v2/shopping/flight-offers",
                {
                    "originLocationCode": origin_code,
                    "destinationLocationCode": dest_code,
                    "departureDate": start_date,
                    "adults": str(max(1, travelers)),
                    "currencyCode": currency,
                    "max": str(limit),
                },
            )
            if not data:
                continue
            offers = data.get("data") or []
            if not offers:
                continue
            carriers = (data.get("dictionaries") or {}).get("carriers") or {}
            results: list[dict[str, str]] = []
            seen: set[str] = set()
            for offer in offers:
                itineraries = offer.get("itineraries") or []
                segments = []
                if itineraries:
                    segments = itineraries[0].get("segments") or []
                carrier_codes = [seg.get("carrierCode") for seg in segments if seg.get("carrierCode")]
                carrier_names = [carriers.get(c, c) for c in carrier_codes]
                carrier_label = ", ".join(dict.fromkeys([c for c in carrier_names if c])) or "Airline"
                stops = max(0, len(segments) - 1)
                depart_time = ""
                if segments:
                    dep = (segments[0].get("departure") or {}).get("at")
                    if isinstance(dep, str) and "T" in dep:
                        depart_time = dep.split("T", 1)[1][:5]
                label = f"{origin_code}→{dest_code} · {carrier_label} · {stops} stop(s)"
                if depart_time:
                    label = f"{label} · dep {depart_time}"
                key = f"{origin_code}|{dest_code}|{carrier_label}|{stops}|{depart_time}"
                if key in seen:
                    continue
                seen.add(key)
                results.append(
                    {
                        "label": label,
                        "url": f"https://www.google.com/travel/flights?q={urllib.parse.quote_plus(f'Flights from {origin_code} to {dest_code} on {start_date}')}",  # noqa: E501
                    }
                )
                if len(results) >= limit:
                    break
            if results:
                return results
    return []


def fetch_top_hotels(
    *,
    destination: str,
    start_date: str,
    end_date: str,
    travelers: int = 1,
    currency: str = "USD",
    limit: int = 5,
) -> list[dict[str, str]]:
    city_codes = resolve_location_codes(destination)
    if not city_codes:
        return []
    for city_code in city_codes:
        city_meta = _resolve_city_meta(city_code)
        hotel_dir = _fetch_hotels_by_city(city_code, limit=max(10, limit * 2))
        if city_meta.get("countryCode"):
            cc = str(city_meta.get("countryCode") or "").upper()
            if cc:
                hotel_dir = [
                    h for h in hotel_dir if not h.get("countryCode") or str(h.get("countryCode")).upper() == cc
                ]
        hotel_ids = [h.get("hotelId") for h in hotel_dir if h.get("hotelId")]
        if not hotel_ids:
            continue
        params: dict[str, str] = {
            "hotelIds": ",".join(hotel_ids),
            "adults": str(max(1, travelers)),
            "checkInDate": start_date,
            "roomQuantity": "1",
            "currency": currency,
        }
        if end_date:
            params["checkOutDate"] = end_date
        try:
            data = _amadeus_get(
                "/v3/shopping/hotel-offers",
                params,
            )
        except Exception:
            continue
        if not data:
            continue
        hotels = data.get("data") or []
        if not hotels:
            continue
        results: list[dict[str, str]] = []
        seen: set[str] = set()
        for h in hotels:
            hotel = h.get("hotel") or {}
            name = hotel.get("name") or "Hotel"
            key = str(name).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            label = name
            results.append(
                {
                    "label": label,
                    "url": f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(f'{name} {destination}')}",  # noqa: E501
                }
            )
            if len(results) >= limit:
                break
        if results:
            return results

        # Fallback: directory list (no live rates) if offers are empty.
        if hotel_dir:
            results = []
            seen: set[str] = set()
            for h in hotel_dir:
                name = (h.get("name") or "").strip() or f"Hotel {h.get('hotelId')}"
                key = name.lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                loc_hint = (city_meta.get("name") or destination or "").strip()
                if city_meta.get("countryCode"):
                    loc_hint = f"{loc_hint} {city_meta.get('countryCode')}".strip()
                results.append(
                    {
                        "label": name,
                        "url": f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(f'{name} {loc_hint}')}",  # noqa: E501
                    }
                )
                if len(results) >= limit:
                    break
            if results:
                return results
    return []
