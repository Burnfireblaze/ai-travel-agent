from __future__ import annotations

import re
from datetime import date
from typing import Any
from urllib.parse import quote_plus

from ai_travel_agent.observability.telemetry import TelemetryController
from .utils import log_context_from_state


def _section_block(answer: str, title: str) -> tuple[int, int] | None:
    """
    Returns (start, end) span of a '## {title}' section including its content.
    """
    pattern = re.compile(rf"(?ms)^##+\s+{re.escape(title)}\s*\n.*?(?=^##+\s+|\Z)")
    m = pattern.search(answer)
    if not m:
        return None
    return (m.start(), m.end())


def _get_section_body(answer: str, title: str) -> str | None:
    span = _section_block(answer, title)
    if not span:
        return None
    block = answer[span[0] : span[1]]
    # strip header line
    lines = block.splitlines()
    if not lines:
        return ""
    return "\n".join(lines[1:]).strip()


def _set_section(answer: str, title: str, body: str) -> str:
    block = f"## {title}\n{body.strip()}\n"
    span = _section_block(answer, title)
    if not span:
        return answer.rstrip() + "\n\n" + block
    return answer[: span[0]] + block + answer[span[1] :]


def _has_url(text: str) -> bool:
    return bool(re.search(r"https?://", text or ""))


def _parse_iso(d: str | None) -> date | None:
    if not d:
        return None
    try:
        return date.fromisoformat(d)
    except Exception:
        return None


def _build_default_links(*, origin: str | None, destination: str | None, start_date: str | None, end_date: str | None) -> dict[str, list[dict[str, str]]]:
    dest = destination or "destination"
    links: dict[str, list[dict[str, str]]] = {"flights": [], "lodging": [], "things": [], "weather": []}
    if origin and destination and start_date:
        query = f"flights from {origin} to {dest} {start_date}"
        links["flights"] = [
            {"label": "Google Flights", "url": f"https://www.google.com/travel/flights?q={quote_plus(f'Flights from {origin} to {dest} on {start_date}')}"},  # noqa: E501
            {"label": "Skyscanner", "url": f"https://www.skyscanner.com/transport/flights/?q={quote_plus(f'Skyscanner flights {origin} {dest} {start_date}')}"},  # noqa: E501
            {"label": "Kayak", "url": f"https://www.google.com/search?q={quote_plus(f'site:kayak.com {query}')}"},  # noqa: E501
            {"label": "Expedia", "url": f"https://www.google.com/search?q={quote_plus(f'site:expedia.com {query}')}"},  # noqa: E501
            {"label": "Momondo", "url": f"https://www.google.com/search?q={quote_plus(f'site:momondo.com {query}')}"},  # noqa: E501
        ]
    if destination and start_date and end_date:
        links["lodging"] = [
            {"label": "Booking.com", "url": f"https://www.booking.com/searchresults.html?ss={quote_plus(f'Hotels in {dest} {start_date} to {end_date}')}"},  # noqa: E501
            {"label": "Hotels.com", "url": f"https://www.google.com/search?q={quote_plus(f'site:hotels.com hotels in {dest} {start_date} to {end_date}')}"},  # noqa: E501
            {"label": "Expedia", "url": f"https://www.google.com/search?q={quote_plus(f'site:expedia.com hotels in {dest} {start_date} to {end_date}')}"},  # noqa: E501
            {"label": "Airbnb", "url": f"https://www.airbnb.com/s/{quote_plus(dest)}/homes"},  # noqa: E501
            {"label": "Google Maps (hotels)", "url": f"https://www.google.com/maps/search/?api=1&query={quote_plus(f'Hotels in {dest}')}"},  # noqa: E501
        ]
    if destination:
        links["things"] = [
            {"label": "Google Maps (things to do)", "url": f"https://www.google.com/maps/search/?api=1&query={quote_plus(f'Things to do in {dest}')}"},  # noqa: E501
        ]
    if destination:
        q = f"{dest} weather {start_date}" if start_date else f"{dest} weather"
        links["weather"] = [{"label": "Weather search", "url": f"https://www.google.com/search?q={quote_plus(q)}"}]
    return links


def _links_md(links: list[dict[str, str]]) -> str:
    out: list[str] = []
    for l in links:
        label = (l or {}).get("label") or "Link"
        url = (l or {}).get("url") or ""
        if url:
            out.append(f"- [{label}]({url})")
    return "\n".join(out)


def _normalize_headings(answer: str) -> str:
    """
    Normalize common Markdown heading variants (bold/setext) into ATX headings (## Title)
    so section matching is consistent.
    """
    lines = (answer or "").splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""

        m = re.match(r"^\s*\*\*(.+?)\*\*\s*$", line)
        if m:
            title = m.group(1).strip()
            if title:
                out.append(f"## {title}")
                if i + 1 < len(lines) and re.match(r"^\s*[-=]{3,}\s*$", next_line):
                    i += 2
                    continue
                i += 1
                continue

        if line.strip() and i + 1 < len(lines) and re.match(r"^\s*[-=]{3,}\s*$", next_line):
            out.append(f"## {line.strip()}")
            i += 2
            continue

        out.append(line)
        i += 1
    return "\n".join(out).strip()


def _extract_unavailable_note(summary: str) -> str | None:
    if not summary:
        return None
    m = re.search(r"(Live offers unavailable[^.]*(?:\.[^.]*)?)", summary, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    if "unavailable" in summary.lower():
        return summary.strip()
    return None


def responder(state: dict[str, Any], *, telemetry: TelemetryController | None = None) -> dict[str, Any]:
    constraints = state.get("constraints") or {}
    answer = (state.get("final_answer") or "").strip()
    dests = constraints.get("destinations") or []
    destination = dests[0] if dests else "your destination"
    origin = constraints.get("origin")
    start_date = constraints.get("start_date")
    end_date = constraints.get("end_date")

    if not answer:
        answer = f"# Trip plan\n\n## Summary\nPlanning trip to {destination}.\n"

    # Enforce disclaimer exactly once.
    disclaimer = "Note: Visa/health requirements vary; verify with official sources (this is not legal advice)."
    answer = re.sub(re.escape(disclaimer) + r"\s*", "", answer)
    answer = answer.strip() + "\n\n" + disclaimer + "\n"
    answer = _normalize_headings(answer)

    # Ensure Assumptions section includes missing constraints as words (for evaluation gate).
    missing: list[str] = []
    if not constraints.get("destinations"):
        missing.append("destination")
    if not constraints.get("start_date"):
        missing.append("start date")
    if not constraints.get("end_date"):
        missing.append("end date")
    if not constraints.get("origin"):
        missing.append("origin")
    if constraints.get("budget_usd") is None:
        missing.append("budget")
    if constraints.get("travelers") is None:
        missing.append("travelers")

    if "assumptions" not in answer.lower():
        answer += "\n## Assumptions\n"
    if missing:
        lower = answer.lower()
        if "## assumptions" in lower:
            # Append missing tokens if not present.
            for token in missing:
                if token not in lower:
                    answer += f"- {token}: not provided\n"

    # Build fallbacks from tool results (preferred) or deterministic links.
    tool_results = state.get("tool_results") or []

    def _collect_tool_entries(name: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        if not isinstance(tool_results, list):
            return entries
        for tr in tool_results:
            if not isinstance(tr, dict):
                continue
            if tr.get("tool_name") != name:
                continue
            data = tr.get("data") if isinstance(tr.get("data"), dict) else {}
            links = tr.get("links") if isinstance(tr.get("links"), list) else []
            summary = str(tr.get("summary") or "").strip()
            top = data.get("top_results") if isinstance(data, dict) else None
            entries.append(
                {
                    "data": data,
                    "links": [l for l in links if isinstance(l, dict)],
                    "summary": summary,
                    "top_results": [t for t in top if isinstance(t, dict)] if isinstance(top, list) else [],
                }
            )
        return entries

    def _dedupe_entries(entries: list[dict[str, Any]], *, kind: str) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for e in entries:
            data = e.get("data") or {}
            dest_val = str((data.get("destination") or destination or "")).strip()
            origin_val = str((data.get("origin") or origin or "")).strip()
            key = f"{kind}|{origin_val.lower()}|{dest_val.lower()}"
            if key in seen:
                continue
            seen.add(key)
            out.append(e)
        return out

    defaults = _build_default_links(origin=origin, destination=destination, start_date=start_date, end_date=end_date)

    # Ensure core sections exist and are not empty.
    required = ["Summary", "Flights", "Lodging", "Day-by-day", "Transit", "Weather", "Budget", "Calendar"]
    for sec in required:
        if sec.lower() not in answer.lower():
            answer += f"\n## {sec}\n"

    # Flights (support multiple destinations)
    flights_body = _get_section_body(answer, "Flights") or ""
    flight_entries = _dedupe_entries(_collect_tool_entries("flights_search_links"), kind="flights")
    if flight_entries:
        blocks: list[str] = []
        for entry in flight_entries:
            data = entry.get("data") or {}
            dest_val = str((data.get("destination") or destination or "")).strip()
            origin_val = str((data.get("origin") or origin or "")).strip()
            heading = ""
            if origin_val and dest_val:
                heading = f"### {origin_val} → {dest_val}"
            elif dest_val:
                heading = f"### {dest_val}"
            if heading:
                blocks.append(heading)
            note = _extract_unavailable_note(entry.get("summary", ""))
            if note and not entry.get("top_results"):
                blocks.append(f"- {note}")
            if entry.get("top_results"):
                blocks.append("Top 5 results:\n" + _links_md(entry["top_results"]))
            if entry.get("links"):
                blocks.append("Search links:\n" + _links_md(entry["links"]))
            blocks.append("")
        body = "\n".join(blocks).strip()
        answer = _set_section(answer, "Flights", body)
    else:
        links = defaults["flights"]
        if links or ("not available" in flights_body.lower()) or (not _has_url(flights_body)):
            pieces: list[str] = []
            if links:
                pieces.append("Search links:\n" + _links_md(links))
            if pieces:
                answer = _set_section(answer, "Flights", "\n\n".join(pieces))
            else:
                answer = _set_section(
                    answer,
                    "Flights",
                    "- Provide `origin` and `start_date` to generate flight search links.",
                )

    # Lodging (support multiple destinations)
    lodging_body = _get_section_body(answer, "Lodging") or ""
    lodging_entries = _dedupe_entries(_collect_tool_entries("hotels_search_links"), kind="lodging")
    if lodging_entries:
        blocks = []
        for entry in lodging_entries:
            data = entry.get("data") or {}
            dest_val = str((data.get("destination") or destination or "")).strip()
            heading = f"### {dest_val}" if dest_val else ""
            if heading:
                blocks.append(heading)
            note = _extract_unavailable_note(entry.get("summary", ""))
            if note and not entry.get("top_results"):
                blocks.append(f"- {note}")
            if entry.get("top_results"):
                blocks.append("Top 5 results:\n" + _links_md(entry["top_results"]))
            if entry.get("links"):
                blocks.append("Search links:\n" + _links_md(entry["links"]))
            blocks.append("")
        body = "\n".join(blocks).strip()
        answer = _set_section(answer, "Lodging", body)
    else:
        links = defaults["lodging"]
        if links or ("not available" in lodging_body.lower()) or (not _has_url(lodging_body)):
            pieces = []
            if links:
                pieces.append("Search links:\n" + _links_md(links))
            if pieces:
                answer = _set_section(answer, "Lodging", "\n\n".join(pieces))
            else:
                answer = _set_section(
                    answer,
                    "Lodging",
                    "- Provide `start_date` and `end_date` to generate lodging search links.",
                )

    # Things to do (optional but helpful)
    things_body = _get_section_body(answer, "Things to do") or ""
    if (not things_body) or ("not available" in things_body.lower()):
        links = []
        things_entries = _collect_tool_entries("things_to_do_links")
        if things_entries:
            links = things_entries[-1].get("links") or []
        if not links:
            links = defaults["things"]
        if links:
            answer = _set_section(answer, "Things to do", _links_md(links))

    # Weather
    weather_body = _get_section_body(answer, "Weather") or ""
    if "not available" in weather_body.lower() or not weather_body:
        summary = ""
        weather_entries = _collect_tool_entries("weather_summary")
        if weather_entries:
            summary = weather_entries[-1].get("summary") or ""
            links = weather_entries[-1].get("links") or []
        else:
            links = defaults["weather"]
        pieces: list[str] = []
        if summary:
            pieces.append(f"- {summary}")
        if links:
            pieces.append(_links_md(links))
        if not pieces:
            pieces.append("- Seasonal guidance: check typical weather for your dates.")
        answer = _set_section(answer, "Weather", "\n".join(pieces))

    # Transit
    transit_body = _get_section_body(answer, "Transit") or ""
    if "not available" in transit_body.lower() or not transit_body:
        answer = _set_section(
            answer,
            "Transit",
            "- Use Google Maps for live routing.\n- Prefer public transit/walking in city centers; rideshare/taxi late night.\n- Build buffer time for traffic and station navigation.",
        )

    # Day-by-day
    day_body = _get_section_body(answer, "Day-by-day") or ""
    if "not available" in day_body.lower() or not day_body:
        ds = _parse_iso(start_date)
        de = _parse_iso(end_date)
        lines: list[str] = []
        if ds and de:
            days = abs((de - ds).days) + 1
            max_days = min(days, 10)
            start = min(ds, de)
            for i in range(max_days):
                cur = start.fromordinal(start.toordinal() + i)
                lines.append(f"- Day {i+1} ({cur.isoformat()}): Morning / Afternoon / Evening activities in {destination}.")
            if days > max_days:
                lines.append(f"- Remaining days: follow a similar pattern (total {days} days).")
        else:
            lines = [
                f"- Day 1: Arrival + neighborhood walk + street food in {destination}.",
                "- Day 2: Top sights + museum/garden + evening market.",
                "- Day 3: Day trip or nature walk + local cuisine.",
                "- Day 4: Cultural highlights + shopping + relax.",
                "- Day 5: Flexible day + departure.",
            ]
        answer = _set_section(answer, "Day-by-day", "\n".join(lines))

    # Budget
    budget_body = _get_section_body(answer, "Budget") or ""
    if "not available" in budget_body.lower() or not budget_body:
        budget = constraints.get("budget_usd")
        travelers = constraints.get("travelers")
        if budget is not None:
            try:
                b = float(budget)
                t = int(travelers) if travelers else 1
                per = b / max(1, t)
                answer = _set_section(
                    answer,
                    "Budget",
                    f"- Total budget (provided): ~${b:,.0f} for {t} traveler(s) (~${per:,.0f} per traveler).\n- Heuristic split: flights 35–55%, lodging 25–40%, food+activities 15–30%, local transit 5–10%.\n- No live prices; use the links above to validate.",
                )
            except Exception:
                answer = _set_section(
                    answer,
                    "Budget",
                    "- Heuristic split: flights 35–55%, lodging 25–40%, food+activities 15–30%, local transit 5–10%.\n- No live prices; use links to validate.",
                )
        else:
            answer = _set_section(
                answer,
                "Budget",
                "- Heuristic split: flights 35–55%, lodging 25–40%, food+activities 15–30%, local transit 5–10%.\n- If you share a budget, I can tailor the itinerary and tradeoffs.",
            )

    # Calendar
    cal_body = _get_section_body(answer, "Calendar") or ""
    if "not available" in cal_body.lower() or not cal_body:
        if start_date and end_date:
            answer = _set_section(answer, "Calendar", "- An `.ics` itinerary calendar will be exported after this response.")
        else:
            answer = _set_section(answer, "Calendar", "- Provide `start_date` and `end_date` to export an `.ics` calendar.")

    # Strip currency claims (links-only MVP).
    answer = re.sub(r"(\$\s?\d+|USD\s?\d+|\d+\s?USD)", "[price omitted]", answer, flags=re.IGNORECASE)

    state["final_answer"] = answer.strip() + "\n"
    if telemetry is not None:
        telemetry.trace(
            event="final_answer",
            context=log_context_from_state(state, graph_node="responder"),
            data={"final_answer": state["final_answer"]},
        )
    return state
