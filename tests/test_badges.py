"""Tests for the egg-tier / badge logic."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import badges  # noqa: E402

B = 1_000_000_000
M = 1_000_000


def test_tier_boundaries():
    assert badges._tier(0)["name"] == "Egg"
    assert badges._tier(499 * M)["name"] == "Egg"
    assert badges._tier(500 * M)["name"] == "Hatchling"
    assert badges._tier(6 * B)["name"] == "Raptor"
    assert badges._tier(30 * B)["name"] == "Dragon"
    assert badges._tier(30 * B)["next"] is None        # top tier


def test_tier_progress_to_next():
    t = badges._tier(7 * B + 500 * M)  # Raptor (5B..10B), halfway = 7.5B
    assert t["next"]["name"] == "Inferno"
    assert abs(t["progress_to_next"] - 0.5) < 0.01


def test_best_streak_finds_longest_run():
    tgt = 300 * M
    series = [{"total": v * M} for v in (320, 310, 90, 305, 301, 400, 50, 350)]
    # runs of >=300: [320,310]=2, [305,301,400]=3, [350]=1 -> best 3
    assert badges._best_streak(series, tgt) == 3
    assert badges._best_streak([{"total": 0}], tgt) == 0


def test_highest_milestone():
    assert badges._highest(badges.COST_MILESTONES, 5729) == "$5k"
    assert badges._highest(badges.COST_MILESTONES, 999) is None
    assert badges._highest(badges.TOKEN_MILESTONES, 6 * B) == "1B"
    assert badges._highest(badges.TOKEN_MILESTONES, 60 * B) == "50B"


def test_card_data_shape(monkeypatch):
    monkeypatch.setattr(badges.history, "panel_data", lambda now=None, config=None: {
        "series": [{"date": "2026-06-13", "total": 6 * B}],
        "streak": 12, "hit_days": 20, "total_days": 30, "avg": 200 * M,
        "best": {"date": "2026-05-26", "total": 746 * M}, "active_today": {"claude": 60, "codex": 90},
        "combined_target": 300 * M,
    })
    monkeypatch.setattr(badges.cost, "usage_summary",
                        lambda t: {"tokens_30d": 3 * B, "cost_30d": 2800.0})
    d = badges.card_data()
    assert d["tier"]["name"] == "Raptor"          # 6B combined
    assert d["monthly_tokens"] == 6 * B
    assert d["monthly_cost"] == 5600.0
    assert any("streak" in b["label"] for b in d["badges"])
    assert d["best_streak"] == 1
