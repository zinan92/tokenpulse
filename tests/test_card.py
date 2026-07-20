"""Smoke tests for share-card rendering."""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import card  # noqa: E402


def test_render_card_with_builder_cta(tmp_path):
    out = tmp_path / "tokenpulse-card.png"
    data = {
        "tier": {"emoji": "🐵", "name": "齐天大圣", "name_en": "Great Sage"},
        "monthly_tokens": 6_100_000_000,
        "monthly_cost": 5613,
        "rank_self": {"peak_day": {"total": 746_000_000}, "best_30d": 6_100_000_000},
        "lifetime": {"lifetime_tokens": 8_500_000_000, "first_use_date": "2026-02-01", "days_active": 99},
        "badges": [{"icon": "🏆", "name": "单会话 1B", "hero": True}],
        "handles": {"x": "owner", "xhs": "owner-red"},
        "builder": {
            "handle": "zinan92",
            "xhs_id": "337506137",
            "douyin_id": "douyin-demo",
            "url": "https://example.com/tokenpulse",
        },
    }

    path = card.render(data, out_path=str(out), date_str="2026-06-22")

    assert path == str(out)
    with Image.open(out) as img:
        assert img.size == (card.W, card.H)


def test_render_record_card(tmp_path):
    out = tmp_path / "tokenpulse-record-card.png"
    data = {
        "tier": {"emoji": "🐵", "name": "齐天大圣", "name_en": "Great Sage"},
        "monthly_tokens": 6_100_000_000,
        "monthly_cost": 5613,
        "combined_target": 300_000_000,
        "record_day": {"date": "2026-06-23", "total": 980_000_000},
        "rank_self": {"peak_day": {"date": "2026-06-23", "total": 980_000_000}, "best_30d": 6_100_000_000},
        "lifetime": {"lifetime_tokens": 8_500_000_000, "first_use_date": "2026-02-01", "days_active": 99},
        "badges": [{"icon": "💥", "name": "爆燃日", "hero": True}],
        "handles": {"x": "owner", "xhs": "owner-red"},
        "builder": {
            "handle": "zinan92",
            "xhs_id": "337506137",
            "douyin_id": "douyin-demo",
            "url": "https://example.com/tokenpulse",
        },
    }

    path = card.render_record(data, out_path=str(out), date_str="2026-06-23")

    assert path == str(out)
    with Image.open(out) as img:
        assert img.size == (card.W, card.H)
