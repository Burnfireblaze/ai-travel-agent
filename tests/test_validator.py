from __future__ import annotations

from ai_travel_agent.agents.nodes.validator import validator


def test_validator_invalid_date_asks_user():
    state = {
        "user_query": "Trip to Tokyo",
        "constraints": {"origin": "SFO", "destinations": ["Tokyo"], "start_date": "2026-13-01", "end_date": "2026-03-05"},
        "context_hits": [],
    }
    out = validator(state, geocode_fn=lambda q: {"best": {"name": q}, "candidates": [], "ambiguous": False})
    assert out.get("needs_user_input") is True
    assert "invalid" in (out.get("clarifying_questions") or [""])[0].lower()


def test_validator_memory_origin_conflict_does_not_ask_and_uses_request_when_explicit():
    state = {
        "user_query": "I want to fly from JFK to Tokyo 2026-04-01 to 2026-04-05",
        "constraints": {"origin": "JFK", "destinations": ["Tokyo"], "start_date": "2026-04-01", "end_date": "2026-04-05"},
        "context_hits": [
            {"text": "Home origin: SFO", "metadata": {"type": "profile", "created_at": "2025-01-01T00:00:00+00:00"}}
        ],
    }
    out = validator(state, geocode_fn=lambda q: {"best": {"name": q}, "candidates": [], "ambiguous": False})
    assert out.get("needs_user_input") is False
    assert out["constraints"]["origin"] == "JFK"
    warnings = out.get("validation_warnings") or []
    assert any("saved origin" in w.lower() for w in warnings)


def test_validator_ambiguous_geocode_asks_user():
    def geocode_stub(q: str):
        return {
            "query": q,
            "ambiguous": True,
            "best": {"name": q},
            "candidates": [
                {"name": q, "admin1": "Oregon", "country": "US"},
                {"name": q, "admin1": "Maine", "country": "US"},
            ],
        }

    state = {
        "user_query": "Trip from Portland to Tokyo 2026-04-01 to 2026-04-05",
        "constraints": {"origin": "Portland", "destinations": ["Tokyo"], "start_date": "2026-04-01", "end_date": "2026-04-05"},
        "context_hits": [],
    }
    out = validator(state, geocode_fn=geocode_stub)
    assert out.get("needs_user_input") is True
    assert "ambiguous" in (out.get("clarifying_questions") or [""])[0].lower()


def test_validator_geocode_failure_falls_back_with_warning():
    def geocode_fail(_: str):
        raise RuntimeError("offline")

    state = {
        "user_query": "Trip from SFO to Tokyo 2026-04-01 to 2026-04-05",
        "constraints": {"origin": "SFO", "destinations": ["Tokyo"], "start_date": "2026-04-01", "end_date": "2026-04-05"},
        "context_hits": [],
    }
    out = validator(state, geocode_fn=geocode_fail)
    assert out.get("needs_user_input") is False
    warnings = out.get("validation_warnings") or []
    assert any("geocode" in w.lower() or "unable" in w.lower() for w in warnings)


def test_validator_no_geocode_results_blocks():
    def geocode_none(_: str):
        return {"query": "x", "ambiguous": False, "best": None, "candidates": []}

    state = {
        "user_query": "Trip from LOL to sdjsdkfifdk 2026-04-01 to 2026-04-05",
        "constraints": {"origin": "LOL", "destinations": ["sdjsdkfifdk"], "start_date": "2026-04-01", "end_date": "2026-04-05"},
        "context_hits": [],
    }
    out = validator(state, geocode_fn=geocode_none)
    assert out.get("needs_user_input") is True
    q = (out.get("clarifying_questions") or [""])[0].lower()
    assert "couldn't find" in q or "could not be found" in q


def test_validator_interests_conflict_does_not_ask_and_uses_request_interests():
    state = {
        "user_query": "Trip to Tokyo 2026-04-01 to 2026-04-05 with interests ramen, gardens",
        "constraints": {
            "origin": "SFO",
            "destinations": ["Tokyo"],
            "start_date": "2026-04-01",
            "end_date": "2026-04-05",
            "interests": ["ramen", "gardens"],
        },
        "context_hits": [{"text": "User interests: anime, ramen", "metadata": {"type": "preference"}}],
    }
    out = validator(state, geocode_fn=lambda q: {"best": {"name": q}, "candidates": [], "ambiguous": False})
    assert out.get("needs_user_input") is False
    assert out["constraints"]["interests"] == ["ramen", "gardens"]
    warnings = out.get("validation_warnings") or []
    assert any("saved interests" in w.lower() for w in warnings)


def test_validator_memory_origin_conflict_uses_memory_when_not_explicit():
    state = {
        "user_query": "Plan my trip to Tokyo 2026-04-01 to 2026-04-05",
        "constraints": {"origin": "NYC", "destinations": ["Tokyo"], "start_date": "2026-04-01", "end_date": "2026-04-05"},
        "context_hits": [{"text": "Home origin: JFK", "metadata": {"type": "profile"}}],
    }
    out = validator(state, geocode_fn=lambda q: {"best": {"name": q}, "candidates": [], "ambiguous": False})
    assert out.get("needs_user_input") is False
    assert out["constraints"]["origin"] == "JFK"
