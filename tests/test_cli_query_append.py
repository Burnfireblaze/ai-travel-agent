from __future__ import annotations

from ai_travel_agent.cli import _append_details


def test_append_details_once_and_accumulates():
    base = "Trip to India"
    out1 = _append_details(base, ["Q1 A1", "Q2 A2"])
    assert "Additional details:" in out1
    assert "Q1 A1" in out1 and "Q2 A2" in out1

    out2 = _append_details(out1, ["Q3 A3"])
    assert out2.count("Additional details:") == 1
    assert "Q3 A3" in out2
