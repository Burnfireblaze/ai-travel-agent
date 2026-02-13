from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from icalendar import Calendar

from ai_travel_agent.agents.state import EvaluationResult


_URL_RE = re.compile(r"https?://[^\s)>\"]+")
_PRICE_RE = re.compile(r"(\$\s?\d+|USD\s?\d+|\d+\s?USD)", re.IGNORECASE)


REQUIRED_SECTIONS = [
    "Summary",
    "Assumptions",
    "Flights",
    "Lodging",
    "Day-by-day",
    "Transit",
    "Weather",
    "Budget",
    "Calendar",
]


def _extract_links(text: str) -> list[str]:
    return _URL_RE.findall(text or "")


def _links_valid(links: list[str]) -> bool:
    for link in links:
        p = urlparse(link)
        if p.scheme not in ("http", "https") or not p.netloc:
            return False
    return True


def _has_sections(answer: str) -> float:
    found = 0
    for sec in REQUIRED_SECTIONS:
        if sec.lower() in (answer or "").lower():
            found += 1
    return 5.0 * (found / len(REQUIRED_SECTIONS))


def _specificity_score(answer: str) -> float:
    text = answer or ""
    time_mentions = len(re.findall(r"\b(\d{1,2}:\d{2}|morning|afternoon|evening)\b", text, re.IGNORECASE))
    bullets = len(re.findall(r"^\s*[-*]\s+", text, re.MULTILINE))
    score = 0.0
    score += min(2.5, time_mentions / 6.0 * 2.5)
    score += min(2.5, bullets / 20.0 * 2.5)
    return max(0.0, min(5.0, score))


def _coherence_score(constraints: dict[str, Any], answer: str) -> float:
    score = 5.0
    dests = [d.lower() for d in (constraints.get("destinations") or []) if isinstance(d, str)]
    text = (answer or "").lower()
    if dests and not any(d in text for d in dests):
        score -= 2.0
    start = constraints.get("start_date")
    end = constraints.get("end_date")
    if start and start not in (answer or ""):
        score -= 1.0
    if end and end not in (answer or ""):
        score -= 1.0
    return max(0.0, min(5.0, score))


def _relevance_score(constraints: dict[str, Any], answer: str) -> float:
    interests = [i.lower() for i in (constraints.get("interests") or []) if isinstance(i, str)]
    if not interests:
        return 3.5
    text = (answer or "").lower()
    hits = sum(1 for i in interests if i in text)
    return max(0.0, min(5.0, 2.0 + 3.0 * (hits / max(1, min(5, len(interests))))))


def _feasibility_score(answer: str) -> float:
    text = (answer or "").lower()
    if "travel time" in text or "transit" in text or "distance" in text:
        return 4.0
    return 3.0


def _budget_score(constraints: dict[str, Any], answer: str) -> float:
    if "budget" not in (answer or "").lower():
        return 1.5
    if constraints.get("budget_usd") is not None:
        return 4.0
    return 3.0


def _assumptions_cover_missing(constraints: dict[str, Any], answer: str) -> bool:
    missing = []
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
    if not missing:
        return True
    lower = (answer or "").lower()
    if "assumptions" not in lower:
        return False
    return all(m in lower for m in missing)


def _no_fabricated_prices(answer: str) -> bool:
    text = answer or ""
    if _PRICE_RE.search(text):
        return False
    # Allow generic mentions like "prices may change" or "check prices" as long as we don't
    # claim specific numeric pricing or quote a fare.
    lower = text.lower()
    if re.search(r"\b(price|prices|cost|costs|fare|fares)\b.{0,25}\d", lower):
        return False
    if re.search(r"\d.{0,25}\b(price|prices|cost|costs|fare|fares)\b", lower):
        return False
    return True


def _calendar_ok(ics_bytes: bytes | None, constraints: dict[str, Any]) -> bool:
    if not ics_bytes:
        return False
    try:
        cal = Calendar.from_ical(ics_bytes)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        if not events:
            return False
        start = constraints.get("start_date")
        end = constraints.get("end_date")
        if start and end:
            # inclusive days
            from datetime import date

            ds = date.fromisoformat(start)
            de = date.fromisoformat(end)
            days = abs((de - ds).days) + 1
            return len(events) >= min(1, days)
        return True
    except Exception:
        return False


def _has_safety_disclaimer(answer: str) -> bool:
    lower = (answer or "").lower()
    return "verify with official sources" in lower or "not legal advice" in lower


def evaluate_final(
    *,
    constraints: dict[str, Any],
    final_answer: str,
    ics_bytes: bytes | None,
    eval_threshold: float,
) -> EvaluationResult:
    links = _extract_links(final_answer)

    hard_gates = {
        "constraint_completeness": _assumptions_cover_missing(constraints, final_answer),
        "no_fabricated_real_time_facts": _no_fabricated_prices(final_answer),
        "link_validity_format": _links_valid(links),
        "calendar_export_correctness": _calendar_ok(ics_bytes, constraints),
        "safety_clarity_disclaimer": _has_safety_disclaimer(final_answer),
    }

    rubric_scores = {
        "relevance": _relevance_score(constraints, final_answer),
        "feasibility": _feasibility_score(final_answer),
        "completeness": _has_sections(final_answer),
        "specificity": _specificity_score(final_answer),
        "coherence": _coherence_score(constraints, final_answer),
    }

    avg = sum(rubric_scores.values()) / max(1, len(rubric_scores))
    all_gates = all(hard_gates.values())

    if all_gates and avg >= eval_threshold:
        status = "good"
    elif all_gates:
        status = "needs_work"
    else:
        status = "failed"

    notes: list[str] = []
    if not all_gates:
        notes.append("One or more hard gates failed.")
    notes.append(f"Average rubric score: {avg:.2f} (threshold {eval_threshold:.2f}).")

    return EvaluationResult(hard_gates=hard_gates, rubric_scores=rubric_scores, overall_status=status, notes=notes)
