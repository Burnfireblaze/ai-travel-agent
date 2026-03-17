from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\d)")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
ADDRESS_RE = re.compile(
    r"\b\d{1,5}\s+[A-Z0-9][A-Z0-9.\- ]+\s(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Way)\b",
    re.IGNORECASE,
)
PASSPORT_RE = re.compile(r"\bpassport(?:\s+number|\s+no\.?)?[:\s#-]*([A-Z0-9]{6,9})\b", re.IGNORECASE)
CARD_CANDIDATE_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")


@dataclass(frozen=True)
class PIISummary:
    detected: bool
    leak_count: int
    types: tuple[str, ...]

    def as_payload(self) -> dict[str, Any]:
        return {
            "pii_detected": self.detected,
            "pii_leak_count": self.leak_count,
            "pii_types": list(self.types),
        }


def _iter_text(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        out: list[str] = []
        for key, item in value.items():
            out.append(str(key))
            out.extend(_iter_text(item))
        return out
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            out.extend(_iter_text(item))
        return out
    return [str(value)]


def _luhn_valid(candidate: str) -> bool:
    digits = [int(ch) for ch in candidate if ch.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for idx, digit in enumerate(digits):
        value = digit
        if idx % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        checksum += value
    return checksum % 10 == 0


def detect_pii(*values: Any) -> PIISummary:
    matches: set[tuple[str, str]] = set()
    for value in values:
        for text in _iter_text(value):
            for match in EMAIL_RE.findall(text):
                matches.add(("email", match.lower()))
            for match in PHONE_RE.findall(text):
                digits = re.sub(r"\D+", "", match)
                matches.add(("phone", digits))
            for match in SSN_RE.findall(text):
                matches.add(("ssn", match))
            for match in ADDRESS_RE.findall(text):
                matches.add(("address", " ".join(match.split()).lower()))
            for match in PASSPORT_RE.findall(text):
                matches.add(("passport", match.upper()))
            for raw in CARD_CANDIDATE_RE.findall(text):
                digits = re.sub(r"\D+", "", raw)
                if _luhn_valid(digits):
                    matches.add(("credit_card", digits))
    pii_types = tuple(sorted({kind for kind, _ in matches}))
    return PIISummary(detected=bool(matches), leak_count=len(matches), types=pii_types)
