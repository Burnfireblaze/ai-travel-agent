from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict


MemoryDocType = Literal["profile", "preference", "trip_summary", "tool_output", "note"]


class MemoryMetadata(TypedDict, total=False):
    type: MemoryDocType
    user_id: str
    run_id: str
    created_at: str
    tags: list[str]


@dataclass(frozen=True)
class MemoryHit:
    id: str
    text: str
    metadata: MemoryMetadata
    distance: float | None = None

