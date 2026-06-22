"""Tests for the monotonic lifetime accumulator."""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lifetime  # noqa: E402

M = 1_000_000


def _series(rows):
    return {"series": [{"date": d, "claude": c, "codex": x, "total": c + x} for d, c, x in rows]}


def test_backfill_excludes_today_and_sums(monkeypatch, tmp_path):
    monkeypatch.setattr(lifetime, "LIFETIME_PATH", str(tmp_path / ".lifetime.json"))
    rows = [("2026-06-20", 100 * M, 50 * M), ("2026-06-21", 200 * M, 0),
            ("2026-06-22", 999 * M, 999 * M)]  # 06-22 is "today" -> excluded
    monkeypatch.setattr(lifetime.history, "daily_tokens", lambda now, days, use_disk_cache=True: _series(rows))
    now = datetime(2026, 6, 22, 12, tzinfo=timezone.utc)
    d = lifetime.update(now, allow_backfill=True)
    assert d["backfill_complete"] is True
    assert d["total_tokens"] == 350 * M               # 150M + 200M, today excluded
    assert d["first_use_date"] == "2026-06-20"
    assert d["days_active"] == 2
    assert d["counted_through"] == "2026-06-21"
    assert d["peak_day"]["total"] == 200 * M


def test_pending_when_not_backfilled(monkeypatch, tmp_path):
    monkeypatch.setattr(lifetime, "LIFETIME_PATH", str(tmp_path / ".nope.json"))
    s = lifetime.summary(datetime(2026, 6, 22, tzinfo=timezone.utc), today_tokens=5 * M)
    assert s["pending"] is True
    assert s["lifetime_tokens"] == 5 * M              # only today's live, no blocking scan


def test_summary_adds_today_live_no_double_count(monkeypatch, tmp_path):
    monkeypatch.setattr(lifetime, "LIFETIME_PATH", str(tmp_path / ".lifetime.json"))
    rows = [("2026-06-20", 100 * M, 50 * M), ("2026-06-21", 200 * M, 0)]
    monkeypatch.setattr(lifetime.history, "daily_tokens", lambda now, days, use_disk_cache=True: _series(rows))
    now = datetime(2026, 6, 22, 12, tzinfo=timezone.utc)
    lifetime.update(now, allow_backfill=True)         # settle through 06-21 = 350M
    s = lifetime.summary(now, today_tokens=80 * M, today_claude=80 * M, today_codex=0)
    assert s["lifetime_tokens"] == 430 * M            # 350M settled + 80M today
    assert s["days_active"] == 3                       # 2 settled + today
    assert s["pending"] is False


def test_increment_is_monotonic_and_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(lifetime, "LIFETIME_PATH", str(tmp_path / ".lifetime.json"))
    rows = [("2026-06-20", 100 * M, 0)]
    monkeypatch.setattr(lifetime.history, "daily_tokens", lambda now, days, use_disk_cache=True: _series(rows))
    lifetime.update(datetime(2026, 6, 21, 12, tzinfo=timezone.utc), allow_backfill=True)  # through 06-20
    # next day: a new settled day appears; re-running same day must not double count
    rows2 = [("2026-06-20", 100 * M, 0), ("2026-06-21", 300 * M, 0)]
    monkeypatch.setattr(lifetime.history, "daily_tokens", lambda now, days, use_disk_cache=True: _series(rows2))
    now = datetime(2026, 6, 22, 12, tzinfo=timezone.utc)
    a = lifetime.update(now)
    b = lifetime.update(now)
    assert a["total_tokens"] == b["total_tokens"] == 400 * M   # 100M + 300M, counted once
