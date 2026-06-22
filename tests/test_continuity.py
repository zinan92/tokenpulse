"""Tests for the longest-continuous-run fold (pure logic, no log scan)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import continuity  # noqa: E402


def test_fold_finds_longest_gap_bounded_span():
    st = continuity._empty()  # gap_minutes=30 -> 1800s cap
    # run A: 0..1200 (1200s) ; >30min gap ; run B: 5000..5600 (600s)
    ts = [0, 600, 1200, 5000, 5600]
    out = continuity._fold(st, ts)
    assert out["longest_seconds"] == 1200
    # a longer second run wins (steps <= 1800s cap so the run never breaks)
    ts2 = [0, 600, 9000, 10800, 12600]   # gap before 9000; run 9000..12600 = 3600s
    out2 = continuity._fold(continuity._empty(), ts2)
    assert out2["longest_seconds"] == 3600


def test_fold_is_immutable_and_resumable():
    st = continuity._empty()
    a = continuity._fold(st, [0, 600, 1200])
    assert st["longest_seconds"] == 0           # input untouched
    # resume from persisted (run_start/last_ts) — the open run continues
    b = continuity._fold(a, [1500, 1800])       # all within 30min of prev
    assert b["longest_seconds"] == 1800         # 0..1800 one continuous run


def test_fold_strictly_greater_no_reprocess():
    a = continuity._fold(continuity._empty(), [0, 600, 1200])
    b = continuity._fold(a, [1200, 1800])        # 1200 == last_ts, must be skipped
    assert b["longest_seconds"] == 1800
