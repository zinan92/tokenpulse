"""Tests for the plan-limits reader (piggybacks on CodexBar's history files)."""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import limits  # noqa: E402

NOW = datetime(2026, 6, 3, 4, 30, tzinfo=timezone.utc)


def _hist(windows):
    return {
        "preferredAccountKey": "acct1",
        "accounts": {"acct1": windows},
    }


def test_reset_in_formats():
    assert limits.reset_in("2026-06-09T07:00:00Z", NOW).endswith("d2h") or "d" in limits.reset_in("2026-06-09T07:00:00Z", NOW)
    assert limits.reset_in("2026-06-03T09:26:00Z", NOW) == "4h56m"
    assert limits.reset_in("2026-06-03T04:42:00Z", NOW) == "12m"
    assert limits.reset_in("2026-06-03T04:00:00Z", NOW) == "due"
    assert limits.reset_in(None, NOW) == ""


def test_parses_windows_and_picks_latest_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(limits, "HIST_DIR", str(tmp_path))
    claude = _hist([
        {"name": "session", "windowMinutes": 300, "entries": [
            {"capturedAt": "2026-06-03T03:00:00Z", "resetsAt": "2026-06-03T04:00:00Z", "usedPercent": 80},
            {"capturedAt": "2026-06-03T04:26:00Z", "resetsAt": "2026-06-03T09:26:00Z", "usedPercent": 30},
        ]},
        {"name": "weekly", "windowMinutes": 10080, "entries": [
            {"capturedAt": "2026-06-03T04:26:00Z", "resetsAt": "2026-06-09T07:00:00Z", "usedPercent": 12},
        ]},
    ])
    (tmp_path / "claude.json").write_text(json.dumps(claude))
    (tmp_path / "codex.json").write_text(json.dumps(_hist([])))

    pl = limits.plan_limits(now=NOW)
    c = pl["claude"]
    assert c["available"] is True
    assert c["stale"] is False  # newest sample is "now"
    session = limits.window(c, "session")
    assert session["used_percent"] == 30  # latest entry, not the 80
    assert session["left_percent"] == 70
    weekly = limits.window(c, "weekly")
    assert weekly["left_percent"] == 88
    assert "d" in weekly["reset_in"]
    # window ordering: session before weekly
    assert [w["name"] for w in c["windows"]] == ["session", "weekly"]


def test_stale_detection(tmp_path, monkeypatch):
    monkeypatch.setattr(limits, "HIST_DIR", str(tmp_path))
    old = _hist([{"name": "session", "windowMinutes": 300, "entries": [
        {"capturedAt": "2026-06-02T20:00:00Z", "resetsAt": "2026-06-03T01:00:00Z", "usedPercent": 10},
    ]}])  # 8.5h before NOW (> 6h threshold)
    (tmp_path / "claude.json").write_text(json.dumps(old))
    (tmp_path / "codex.json").write_text(json.dumps(_hist([])))
    pl = limits.plan_limits(now=NOW)
    assert pl["claude"]["stale"] is True


def test_window_pace_weekly_behind_and_skip_short():
    now = datetime(2026, 6, 3, 4, 30, tzinfo=timezone.utc)
    # weekly window (7d) ending 5 days out -> ~2d/7d ≈ 28.6% elapsed
    resets = "2026-06-08T04:30:00Z"
    p = limits.window_pace(10080, resets, 5, now)
    assert p is not None
    assert p["on_pace"] is False
    assert 25 < p["expected_used_percent"] < 32
    assert p["behind_by"] == round(p["expected_used_percent"] - 5, 1)
    # on pace when used exceeds expected
    assert limits.window_pace(10080, resets, 90, now)["on_pace"] is True
    # short (5h session) window -> no pace
    assert limits.window_pace(300, "2026-06-03T09:00:00Z", 5, now) is None
    # missing inputs
    assert limits.window_pace(10080, None, 5, now) is None


def test_missing_codexbar(tmp_path, monkeypatch):
    monkeypatch.setattr(limits, "HIST_DIR", str(tmp_path / "nope"))
    pl = limits.plan_limits(now=NOW)
    assert pl["claude"]["available"] is False
    assert pl["claude"]["reason"] == "codexbar-not-found"
    assert pl["claude"]["windows"] == []


def test_preferred_account_selected(tmp_path, monkeypatch):
    monkeypatch.setattr(limits, "HIST_DIR", str(tmp_path))
    data = {
        "preferredAccountKey": "B",
        "accounts": {
            "A": [{"name": "weekly", "windowMinutes": 10080, "entries": [
                {"capturedAt": "2026-06-03T04:00:00Z", "resetsAt": "2026-06-09T07:00:00Z", "usedPercent": 99}]}],
            "B": [{"name": "weekly", "windowMinutes": 10080, "entries": [
                {"capturedAt": "2026-06-03T04:00:00Z", "resetsAt": "2026-06-09T07:00:00Z", "usedPercent": 12}]}],
        },
    }
    (tmp_path / "claude.json").write_text(json.dumps(data))
    (tmp_path / "codex.json").write_text(json.dumps(_hist([])))
    pl = limits.plan_limits(now=NOW)
    assert limits.window(pl["claude"], "weekly")["used_percent"] == 12  # account B
