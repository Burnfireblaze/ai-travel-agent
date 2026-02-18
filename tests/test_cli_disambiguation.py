from __future__ import annotations

from ai_travel_agent.cli import _resolve_interests_conflict, _resolve_option_answer, _resolve_origin_conflict


def test_resolve_option_answer_picks_first_option():
    q = "Your destination 'Peru' is ambiguous. Reply with 1-3. Options: 1) Peru, Peru; 2) Peru, Indiana United States; 3) Peru, Illinois United States"
    assert _resolve_option_answer(q, "1") == "Peru, Peru"
    assert _resolve_option_answer(q, "first option") == "Peru, Peru"
    assert _resolve_option_answer(q, "It's the 1st option") == "Peru, Peru"


def test_resolve_option_answer_leaves_non_option_questions_unchanged():
    q = "What is your start date? (YYYY-MM-DD)"
    assert _resolve_option_answer(q, "2026-06-03") == "2026-06-03"


def test_resolve_interests_conflict_numeric_choice():
    pending = {"current": ["day hikes", "ramen"], "memory": ["anime"], "merged": ["day hikes", "ramen", "anime"]}
    assert _resolve_interests_conflict(pending, "1") == ["day hikes", "ramen"]
    assert _resolve_interests_conflict(pending, "2") == ["anime"]
    assert _resolve_interests_conflict(pending, "3") == ["day hikes", "ramen", "anime"]


def test_resolve_interests_conflict_custom_list():
    pending = {"current": ["a"], "memory": ["b"], "merged": ["a", "b"]}
    assert _resolve_interests_conflict(pending, "coffee, museums, coffee") == ["coffee", "museums"]


def test_resolve_origin_conflict_numeric_choice():
    pending = {"current": "NYC", "memory": "JFK"}
    assert _resolve_origin_conflict(pending, "1") == "NYC"
    assert _resolve_origin_conflict(pending, "2") == "JFK"
