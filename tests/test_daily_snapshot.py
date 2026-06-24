"""Tests for daily local card snapshot generation."""
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import daily_snapshot  # noqa: E402


def _data():
    return {
        "tier": {"emoji": "🐵", "name": "齐天大圣", "name_en": "Great Sage"},
        "monthly_tokens": 7_200_000_000,
        "combined_target": 300_000_000,
        "record_day": {"date": "2026-06-23", "total": 895_000_000},
        "rank_self": {"peak_day": {"date": "2026-06-23", "total": 895_000_000}},
        "lifetime": {"lifetime_tokens": 9_700_000_000},
        "badges": [],
        "handles": {"x": "xparkzz"},
        "builder": {"url": "https://example.com/tokenpulse"},
    }


def test_snapshot_cards_writes_both_cards_and_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(daily_snapshot.badges, "card_data", lambda now=None: _data())

    def fake_render(_data, out_path, date_str=""):
        Path(out_path).write_bytes(f"monthly {date_str}".encode())
        return str(out_path)

    def fake_record(_data, out_path, date_str=""):
        Path(out_path).write_bytes(f"record {date_str}".encode())
        return str(out_path)

    monkeypatch.setattr(daily_snapshot.card, "render", fake_render)
    monkeypatch.setattr(daily_snapshot.card, "render_record", fake_record)
    now = datetime(2026, 6, 23, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = daily_snapshot.snapshot_cards(out_root=tmp_path, now=now)

    assert result["ok"] is True
    assert result["date"] == "2026-06-23"
    assert result["timezone"] == "Asia/Shanghai"
    assert result["scheduled_time"] == "12:00"
    assert Path(result["cards"]["monthly"]).read_bytes() == b"monthly 2026-06-23"
    assert Path(result["cards"]["record"]).read_bytes() == b"record 2026-06-23"
    manifest = Path(result["manifest"]).read_text(encoding="utf-8")
    assert "895000000" in manifest


def test_snapshot_cards_skips_existing_snapshot(tmp_path):
    out_dir = tmp_path / "2026-06-23"
    out_dir.mkdir()
    monthly = out_dir / "tokenpulse-card-2026-06-23-1200.png"
    record = out_dir / "tokenpulse-record-card-2026-06-23-1200.png"
    manifest = out_dir / "manifest.json"
    monthly.write_bytes(b"monthly")
    record.write_bytes(b"record")
    manifest.write_text("{}", encoding="utf-8")
    now = datetime(2026, 6, 23, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = daily_snapshot.snapshot_cards(out_root=tmp_path, now=now)

    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["cards"] == {"monthly": str(monthly), "record": str(record)}
