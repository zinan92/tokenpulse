"""Deterministic tests for the TokenPulse core engine.

Extractors are tested against synthetic JSONL fixtures (no dependence on live
logs), so the dedup / per-turn-delta logic is pinned exactly.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402

CFG = core.DEFAULT_CONFIG


# ------------------------------------------------------------------ fixtures


def _write(path, records):
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _claude_msg(ts, mid, rid, inp=0, cc=0, cr=0, out=0):
    return {
        "timestamp": ts,
        "requestId": rid,
        "message": {
            "id": mid,
            "usage": {
                "input_tokens": inp,
                "cache_creation_input_tokens": cc,
                "cache_read_input_tokens": cr,
                "output_tokens": out,
            },
        },
    }


def _codex_turn(ts, total):
    return {
        "timestamp": ts,
        "type": "event",
        "payload": {"info": {"last_token_usage": {"total_tokens": total}}},
    }


# ------------------------------------------------------------- claude extractor


def test_claude_dedup_and_sum(tmp_path, monkeypatch):
    d = tmp_path / "proj"
    d.mkdir()
    f1 = d / "a.jsonl"
    f2 = d / "b.jsonl"  # duplicate of msg1 (resumed session)
    ts = "2026-06-02T05:00:00.000Z"  # 13:00 local (UTC+8) -> June 2 local
    _write(f1, [
        _claude_msg(ts, "m1", "r1", inp=100, cc=200, cr=300, out=400),  # 1000
        _claude_msg(ts, "m2", "r2", inp=10, cc=0, cr=0, out=5),         # 15
    ])
    _write(f2, [
        _claude_msg(ts, "m1", "r1", inp=100, cc=200, cr=300, out=400),  # dup -> skipped
        _claude_msg(ts, "m3", "r3", inp=1, cc=1, cr=1, out=1),          # 4
    ])
    monkeypatch.setattr(core, "CLAUDE_GLOB", str(d / "*.jsonl"))
    day = datetime(2026, 6, 2).date()
    res = core.claude_today(day, "local")
    assert res["total"] == 1000 + 15 + 4, res
    assert res["duplicates_skipped"] == 1
    assert res["messages"] == 3


def test_claude_excludes_other_days(tmp_path, monkeypatch):
    d = tmp_path / "proj"
    d.mkdir()
    _write(d / "a.jsonl", [
        _claude_msg("2026-06-02T05:00:00Z", "m1", "r1", out=100),
        _claude_msg("2026-05-30T05:00:00Z", "old", "ro", out=999),
    ])
    monkeypatch.setattr(core, "CLAUDE_GLOB", str(d / "*.jsonl"))
    res = core.claude_today(datetime(2026, 6, 2).date(), "local")
    assert res["total"] == 100


# -------------------------------------------------------------- codex extractor


def test_codex_sums_per_turn_deltas(tmp_path, monkeypatch):
    d = tmp_path / "2026" / "06" / "02"
    d.mkdir(parents=True)
    f = d / "rollout-2026-06-02T13-00-00-aaaa-bbbb-cccc-dddd-eeee.jsonl"
    _write(f, [
        _codex_turn("2026-06-02T05:00:00Z", 100),
        _codex_turn("2026-06-02T05:05:00Z", 250),  # per-turn delta, not cumulative
        _codex_turn("2026-05-30T05:00:00Z", 9999),  # other day
    ])
    monkeypatch.setattr(core, "CODEX_GLOBS", (str(tmp_path / "**" / "*.jsonl"),))
    res = core.codex_today(datetime(2026, 6, 2).date(), "local")
    assert res["total"] == 350, res
    assert res["turns"] == 2
    assert res["sessions"] == 1


def test_codex_dedupes_same_session_uuid(tmp_path, monkeypatch):
    """Same session present in sessions/ and archived_sessions/ counts once."""
    a = tmp_path / "sessions"
    b = tmp_path / "archived"
    a.mkdir()
    b.mkdir()
    name = "rollout-2026-06-02T13-00-00-aaaa-bbbb-cccc-dddd-eeee.jsonl"
    rec = [_codex_turn("2026-06-02T05:00:00Z", 500)]
    _write(a / name, rec)
    _write(b / name, rec)
    monkeypatch.setattr(core, "CODEX_GLOBS", (str(a / "*.jsonl"), str(b / "*.jsonl")))
    res = core.codex_today(datetime(2026, 6, 2).date(), "local")
    assert res["total"] == 500  # not 1000
    assert res["sessions"] == 1


def test_codex_today_uses_local_codexbar_scanner_for_live_default_globs(monkeypatch):
    now = datetime.now().astimezone()
    monkeypatch.setattr(core, "CODEX_GLOBS", core.DEFAULT_CODEX_GLOBS)
    monkeypatch.setattr(core.codexbar, "usage", lambda **_: {
        "available": True, "source": "codexbar", "tokens_today": 825_620_085,
    })
    res = core.codex_today(core.reference_day(now), "local")
    assert res == {"total": 825_620_085, "turns": 0, "sessions": 0, "source": "codexbar"}


# --------------------------------------------------------------- targets & pace


def test_weekday_vs_weekend_target():
    weekday = datetime(2026, 6, 2).date()  # Tuesday
    weekend = datetime(2026, 6, 6).date()  # Saturday
    # default config: flat 150M every day (no weekend reduction)
    assert core.target_for(weekday, CFG, "claude") == 150 * core.MILLION
    assert core.target_for(weekend, CFG, "claude") == 150 * core.MILLION
    # mechanism still supports a different weekend target when configured
    custom = {"targets": {"claude": {"weekday": 100, "weekend": 50}}}
    assert core.target_for(weekday, custom, "claude") == 100 * core.MILLION
    assert core.target_for(weekend, custom, "claude") == 50 * core.MILLION


def test_pace_behind_and_ahead():
    cfg = CFG
    now = datetime(2026, 6, 2, 17, 0).astimezone()  # mid-window
    target = 100 * core.MILLION
    behind = core.pace(now, cfg, 1 * core.MILLION, target)
    assert behind["mood"] == "behind"
    assert behind["deficit_vs_pace"] > 0
    ahead = core.pace(now, cfg, 99 * core.MILLION, target)
    assert ahead["mood"] in ("ahead", "done")


def test_pace_hit_and_rocket():
    now = datetime(2026, 6, 2, 12, 0).astimezone()
    target = 100 * core.MILLION
    assert core.pace(now, CFG, 100 * core.MILLION, target)["mood"] == "done"
    assert core.pace(now, CFG, 210 * core.MILLION, target)["mood"] == "rocket"
    assert core.pace(now, CFG, 100 * core.MILLION, target)["remaining"] == 0


def test_active_fraction_bounds():
    cfg = {"active_window": {"start": "09:00", "end": "23:59"}}  # explicit window
    before = datetime(2026, 6, 2, 8, 0).astimezone()
    assert core._active_fraction(before, cfg) == 0.0
    late = datetime(2026, 6, 2, 23, 58).astimezone()
    assert core._active_fraction(late, cfg) > 0.9
    mid = datetime(2026, 6, 2, 17, 0).astimezone()
    assert 0.0 < core._active_fraction(mid, cfg) < 1.0


def test_active_fraction_full_day_is_default():
    cfg = CFG  # default is the full local 24h day (00:00 -> 00:00)
    # 06:00 -> 6/24 = 0.25 ; 18:00 -> 18/24 = 0.75
    assert abs(core._active_fraction(datetime(2026, 6, 2, 6, 0).astimezone(), cfg) - 0.25) < 0.01
    assert abs(core._active_fraction(datetime(2026, 6, 2, 18, 0).astimezone(), cfg) - 0.75) < 0.01


def test_active_fraction_midnight_end():
    cfg = {"active_window": {"start": "09:00", "end": "00:00"}}  # end = midnight
    assert core._active_fraction(datetime(2026, 6, 2, 8, 0).astimezone(), cfg) == 0.0
    # 18:00 over a 09:00->24:00 (15h) window -> 9/15 = 0.6
    f = core._active_fraction(datetime(2026, 6, 2, 18, 0).astimezone(), cfg)
    assert abs(f - 0.6) < 0.01


def test_humanize():
    assert core.humanize(225_000_000) == "225.0M"
    assert core.humanize(12_000) == "12K"
    assert core.humanize(500) == "500"


def test_status_shape(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "CLAUDE_GLOB", str(tmp_path / "none*.jsonl"))
    monkeypatch.setattr(core, "CODEX_GLOBS", (str(tmp_path / "none*.jsonl"),))
    s = core.status(config=CFG)
    assert set(s["tools"]) == {"claude", "codex"}
    assert "combined" in s
    for t in s["tools"].values():
        assert {"today", "target", "mood", "remaining", "percent"} <= set(t)
