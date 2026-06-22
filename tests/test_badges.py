"""Tests for the 西游记 tier ladder + badge logic."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import badges  # noqa: E402

B = 1_000_000_000
M = 1_000_000


def test_tier_boundaries():
    assert badges._tier(0)["name"] == "石猴"
    assert badges._tier(99 * M)["name"] == "石猴"
    assert badges._tier(100 * M)["name"] == "美猴王"
    assert badges._tier(500 * M)["name"] == "地仙"
    assert badges._tier(6300 * M)["name"] == "齐天大圣"      # the reference user
    assert badges._tier(8 * B)["name"] == "斗战胜佛"
    assert badges._tier(10 * B)["name"] == "如来佛祖"
    assert badges._tier(10 * B)["next"] is None             # summit
    assert badges._tier(6300 * M)["name_en"] == "Great Sage"


def test_user_lands_second_from_top():
    """6.3B must sit one rung below the ladder summit (斗战胜佛 8B), 如来 10B above."""
    t = badges._tier(6300 * M)
    assert t["next"]["name"] == "斗战胜佛"
    assert t["next"]["at"] == 8 * B


def test_tier_progress_to_next():
    t = badges._tier(6500 * M)  # 齐天大圣 (5B..8B), 1.5/3 = 0.5
    assert abs(t["progress_to_next"] - 0.5) < 0.01


def test_best_window():
    assert badges._best_window([1, 2, 3, 4, 5], 2) == 9       # 4+5
    assert badges._best_window([5, 1, 1, 1], 2) == 6          # 5+1
    assert badges._best_window([3], 30) == 3                  # shorter than window


def test_best_streak_and_highest():
    tgt = 300 * M
    series = [{"total": v * M} for v in (320, 310, 90, 305, 301, 400, 50, 350)]
    assert badges._best_streak(series, tgt) == 3
    assert badges._highest(badges.COST_MILESTONES, 5729) == "$5k"


def test_card_data_shape(monkeypatch):
    monkeypatch.setattr(badges.history, "panel_data", lambda now=None, config=None: {
        "series": [{"date": "2026-06-13", "total": 6 * B}],
        "streak": 4, "hit_days": 20, "total_days": 30, "avg": 200 * M,
        "best": {"date": "2026-05-26", "total": 746 * M}, "active_today": {"claude": 60, "codex": 90},
        "combined_target": 300 * M,
    })
    monkeypatch.setattr(badges.history, "lifetime_records", lambda now=None, config=None: {
        "record_day": {"date": "2026-05-26", "total": 980 * M}, "best_streak": 9,
        "days_tracked": 42, "lifetime_tokens": 12 * B,
    })
    monkeypatch.setattr(badges.history, "daily_tokens", lambda now=None, days=30: {
        "series": [{"date": f"d{i}", "total": 200 * M} for i in range(days)]})
    monkeypatch.setattr(badges.lifetime, "summary", lambda now=None, **kw: {
        "lifetime_tokens": 12 * B, "by_tool": {"claude": 6 * B, "codex": 6 * B},
        "days_active": 80, "first_use_date": "2026-02-14",
        "peak_day": {"date": "2026-05-26", "total": 980 * M}, "pending": False})
    monkeypatch.setattr(badges.cost, "usage_summary",
                        lambda t, **kw: {"tokens_30d": 3 * B, "cost_30d": 2800.0, "tokens_today": 50 * M})
    monkeypatch.setattr(badges.core, "load_config", lambda: {"handle": "zinan92", "xhs_id": "redz"})

    d = badges.card_data()
    assert d["tier"]["name"] == "齐天大圣"                    # 6B combined
    assert d["monthly_tokens"] == 6 * B
    assert d["lifetime"]["lifetime_tokens"] == 12 * B
    assert d["handles"] == {"x": "zinan92", "xhs": "redz"}
    labels = [b["name"] for b in d["badges"]]
    assert any("五亿日" in l for l in labels)                 # record 980M in [500M,1B)
    assert any("双机手" in l for l in labels)                 # both tools 3B >= 1B
    assert any("百亿级" in l for l in labels)                 # lifetime 12B in [10B,100B)
    assert d["badges"][0]["hero"] is True                     # hero sorted first
