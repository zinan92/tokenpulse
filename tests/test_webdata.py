"""Tests for the stable web widget data bridge contract."""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import webdata  # noqa: E402


NOW = datetime(2026, 6, 13, 18, 45, tzinfo=timezone.utc)
CONFIG = {"active_window": {"start": "09:00", "end": "23:59"}}


def _tool(today, expected, mood, *, hit=False):
    target = 500
    return {
        "today": today,
        "target": target,
        "percent": round(today / target * 100, 1),
        "expected_by_now": expected,
        "deficit_vs_pace": max(0, expected - today),
        "remaining": max(0, target - today),
        "active_fraction": 0.5,
        "hit": hit,
        "mood": mood,
    }


def _status():
    return {
        "tools": {
            "claude": _tool(120, 100, "ahead"),
            "codex": _tool(50, 200, "behind"),
        },
        "combined": {
            "today": 170,
            "target": 1000,
            "percent": 17.0,
            "remaining": 830,
        },
    }


def _patch_core(monkeypatch, *, active_fraction=0.5, combined_mood="ontrack", combined_hit=False):
    monkeypatch.setattr(webdata.core, "status", lambda now, config: _status())
    monkeypatch.setattr(
        webdata.core,
        "pace",
        lambda now, config, actual, target: {"mood": combined_mood, "hit": combined_hit},
    )
    monkeypatch.setattr(webdata.core, "_active_fraction", lambda now, config: active_fraction)


def test_state_maps_core_moods_to_widget_states():
    assert webdata._state("behind") == "behind"
    assert webdata._state("ontrack") == "ontrack"
    assert webdata._state("ahead") == "ahead"
    assert webdata._state("done") == "hit"
    assert webdata._state("rocket") == "rocket"
    assert webdata._state("unknown") == "ontrack"


def test_core_payload_shape_and_available_plan_fields(monkeypatch):
    _patch_core(monkeypatch)
    monkeypatch.setattr(
        webdata.limits,
        "plan_limits",
        lambda: {
            "claude": {
                "available": True,
                "stale": False,
                "windows": [
                    {"name": "session", "left_percent": 80, "reset_in": "2h"},
                    {"name": "weekly", "left_percent": 44, "reset_in": "4d"},
                ],
            },
            "codex": {
                "available": True,
                "stale": True,
                "windows": [
                    {"name": "session", "left_percent": 12, "reset_in": "30m"},
                    {"name": "weekly", "left_percent": 91, "reset_in": "6d"},
                ],
            },
        },
    )

    payload = webdata.core_payload(now=NOW, config=CONFIG)

    assert set(payload) == {"generated_at", "clock", "active_fraction", "combined", "tools"}
    assert payload["generated_at"] == NOW.isoformat()
    assert payload["clock"] == "18:45"
    assert payload["active_fraction"] == 0.5

    assert set(payload["tools"]) == {"claude", "codex"}
    assert set(payload["tools"]["claude"]) == {
        "today",
        "target",
        "percent",
        "expected",
        "deficit",
        "remaining",
        "active_fraction",
        "hit",
        "state",
        "pace_ratio",
        "session",
        "weekly",
        "plan_available",
        "plan_stale",
    }
    assert payload["tools"]["claude"]["state"] == "ahead"
    assert payload["tools"]["claude"]["pace_ratio"] == 1.2
    assert payload["tools"]["claude"]["session"] == {"left": 80, "reset": "2h"}
    assert payload["tools"]["claude"]["weekly"] == {"left": 44, "reset": "4d"}
    assert payload["tools"]["claude"]["plan_available"] is True
    assert payload["tools"]["claude"]["plan_stale"] is False

    assert payload["tools"]["codex"]["state"] == "behind"
    assert payload["tools"]["codex"]["pace_ratio"] == 0.25
    assert payload["tools"]["codex"]["session"] == {"left": 12, "reset": "30m"}
    assert payload["tools"]["codex"]["weekly"] == {"left": 91, "reset": "6d"}
    assert payload["tools"]["codex"]["plan_available"] is True
    assert payload["tools"]["codex"]["plan_stale"] is True

    assert payload["combined"] == {
        "today": 170,
        "target": 1000,
        "percent": 17.0,
        "remaining": 830,
        "expected": 300,
        "deficit": 130,
        "state": "ontrack",
        "hit": False,
        "pace_ratio": 0.57,
    }


def test_core_payload_unavailable_plan_fields_are_null(monkeypatch):
    _patch_core(monkeypatch)
    monkeypatch.setattr(
        webdata.limits,
        "plan_limits",
        lambda: {
            "claude": {"available": False, "reason": "codexbar-not-found", "windows": []},
            "codex": {"available": False, "reason": "codexbar-not-found", "windows": []},
        },
    )

    payload = webdata.core_payload(now=NOW, config=CONFIG)

    for tool in ("claude", "codex"):
        assert payload["tools"][tool]["session"] is None
        assert payload["tools"][tool]["weekly"] is None
        assert payload["tools"][tool]["plan_available"] is False
        assert payload["tools"][tool]["plan_stale"] is False


def test_core_payload_combined_state_is_early_before_active_window(monkeypatch):
    _patch_core(monkeypatch, active_fraction=0, combined_mood="ahead", combined_hit=False)
    monkeypatch.setattr(
        webdata.limits,
        "plan_limits",
        lambda: {
            "claude": {"available": False, "windows": []},
            "codex": {"available": False, "windows": []},
        },
    )

    payload = webdata.core_payload(now=NOW, config=CONFIG)

    assert payload["active_fraction"] == 0
    assert payload["combined"]["hit"] is False
    assert payload["combined"]["state"] == "early"


def test_cost_payload_rounds_costs_and_preserves_token_counts(monkeypatch):
    summaries = {
        "claude": {
            "cost_today": 12.345,
            "cost_30d": 456.789,
            "tokens_30d": 987654321,
            "tokens_today": 12345,
        },
        "codex": {
            "cost_today": 0.004,
            "cost_30d": 1.005,
            "tokens_30d": 42,
            "tokens_today": 7,
        },
    }
    monkeypatch.setattr(webdata.cost, "usage_summary", lambda tool: summaries[tool])

    assert webdata.cost_payload() == {
        "claude": {
            "cost_today": 12.35,
            "cost_30d": 456.79,
            "tokens_30d": 987654321,
            "tokens_today": 12345,
        },
        "codex": {
            "cost_today": 0.0,
            "cost_30d": 1.0,
            "tokens_30d": 42,
            "tokens_today": 7,
        },
        "combined": {"cost_30d": 457.79},   # 456.789 + 1.005, the headline spend
    }
