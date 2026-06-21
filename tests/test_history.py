"""Tests for the 30-day history + active-time logic."""
import json
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import history  # noqa: E402

NOW = datetime(2026, 6, 13, 20, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def isolated_cache():
    history._CACHE.clear()
    yield
    history._CACHE.clear()


# ---------------------------------------------------------- pure: active mins

def test_active_minutes_sums_only_gaps_under_cap():
    base = 1_000_000.0
    # gaps: 5m, 5m (counted), then 30m idle (dropped), then 2m (counted) = 12m
    ts = [base, base + 300, base + 600, base + 600 + 1800, base + 600 + 1800 + 120]
    assert history._active_minutes(ts, idle_gap_min=10) == 12


def test_active_minutes_empty_or_single():
    assert history._active_minutes([]) == 0
    assert history._active_minutes([123.0]) == 0


# ---------------------------------------------------------- pure: streak/best

def test_streak_counts_trailing_hits_and_finds_best():
    M = 1_000_000
    series = [
        {"date": "2026-06-09", "total": 50 * M},
        {"date": "2026-06-10", "total": 320 * M},   # hit
        {"date": "2026-06-11", "total": 90 * M},    # miss -> breaks streak
        {"date": "2026-06-12", "total": 310 * M},   # hit
        {"date": "2026-06-13", "total": 400 * M},   # hit (trailing)
    ]
    r = history.streak_and_best(series, target=300 * M)
    assert r["streak"] == 2           # last two days
    assert r["hit_days"] == 3
    assert r["total_days"] == 5
    assert r["best"]["date"] == "2026-06-13" and r["best"]["total"] == 400 * M
    assert r["avg"] == round(sum(s["total"] for s in series) / 5)


def test_streak_zero_when_last_day_misses():
    M = 1_000_000
    series = [{"date": "2026-06-12", "total": 320 * M}, {"date": "2026-06-13", "total": 10 * M}]
    assert history.streak_and_best(series, 300 * M)["streak"] == 0


# ------------------------------------------------------- daily bucketing (E2E)

def _claude_row(ts, mid, rid, out):
    return {"timestamp": ts, "requestId": rid,
            "message": {"id": mid, "model": "claude-opus-4-5",
                        "usage": {"input_tokens": 0, "cache_creation_input_tokens": 0,
                                  "cache_read_input_tokens": 0, "output_tokens": out}}}


def test_daily_tokens_buckets_by_local_day_and_dedupes(tmp_path, monkeypatch):
    f = tmp_path / "proj" / "a.jsonl"
    f.parent.mkdir(parents=True)
    rows = [
        _claude_row("2026-06-13T05:00:00+00:00", "m1", "r1", 100),  # June 13 local
        _claude_row("2026-06-13T05:00:00+00:00", "m1", "r1", 100),  # dup -> skipped
        _claude_row("2026-06-12T05:00:00+00:00", "m2", "r2", 40),   # June 12
    ]
    f.write_text("".join(json.dumps(r) + "\n" for r in rows))
    os.utime(f, (NOW.timestamp(), NOW.timestamp()))
    monkeypatch.setattr(history.core, "CLAUDE_GLOB", str(tmp_path / "**" / "*.jsonl"))
    monkeypatch.setattr(history.core, "CODEX_GLOBS", (str(tmp_path / "none" / "*.jsonl"),))

    out = history.daily_tokens(now=NOW, days=30, use_disk_cache=False)
    by = {r["date"]: r for r in out["series"]}
    assert by["2026-06-13"]["claude"] == 100   # dup removed
    assert by["2026-06-12"]["claude"] == 40
    assert len(out["series"]) == 30
    assert out["series"][-1]["date"] == NOW.astimezone().date().isoformat()  # today is last


def test_lifetime_records(monkeypatch):
    """All-time record day + best streak over the full persisted cache."""
    M = 1_000_000
    cache = {
        "claude": {"2026-06-01": 200 * M, "2026-06-02": 200 * M, "2026-06-03": 50 * M,
                   "2026-06-04": 400 * M, "2026-06-05": 200 * M},
        "codex": {"2026-06-01": 200 * M, "2026-06-02": 200 * M, "2026-06-03": 50 * M,
                  "2026-06-04": 400 * M, "2026-06-05": 200 * M},
    }
    monkeypatch.setattr(history, "_load_disk", lambda: cache)
    cfg = {"targets": {"claude": {"weekday": 150, "weekend": 150},
                       "codex": {"weekday": 150, "weekend": 150}}}  # combined 300M
    now = datetime(2026, 6, 6, 12, tzinfo=timezone.utc)
    r = history.lifetime_records(now=now, config=cfg)
    # combined daily: 400,400,100,800,400M ; target 300M -> hits H,H,-,H,H -> best run 2
    assert r["record_day"] == {"date": "2026-06-04", "total": 800 * M}
    assert r["best_streak"] == 2
    assert r["days_tracked"] == 5
    assert r["lifetime_tokens"] == (400 + 400 + 100 + 800 + 400) * M
