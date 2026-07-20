"""Tests for share-moment detection (tier-up / record / lifetime milestone)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import moments  # noqa: E402

M = 1_000_000
B = 1_000_000_000


def _d(tier, record, life):
    return {"tier": {"name": tier}, "record_day": {"total": record}, "lifetime": {"lifetime_tokens": life}}


def test_first_run_only_snapshots(monkeypatch, tmp_path):
    monkeypatch.setattr(moments, "STORE", str(tmp_path / ".m.json"))
    assert moments.check(_d("齐天大圣", 500 * M, 8 * B)) == []   # no spurious events on launch


def test_tier_up_fires_once(monkeypatch, tmp_path):
    monkeypatch.setattr(moments, "STORE", str(tmp_path / ".m.json"))
    moments.check(_d("哪吒三太子", 100 * M, 2 * B))               # snapshot
    ev = moments.check(_d("齐天大圣", 100 * M, 2 * B))            # climbed
    assert any(e["kind"] == "tier" for e in ev)
    assert moments.check(_d("齐天大圣", 100 * M, 2 * B)) == []     # idempotent


def test_record_and_lifetime_milestone(monkeypatch, tmp_path):
    monkeypatch.setattr(moments, "STORE", str(tmp_path / ".m.json"))
    moments.check(_d("齐天大圣", 500 * M, 8 * B))
    ev = moments.check(_d("齐天大圣", 900 * M, 11 * B))           # new record + crossed 10B
    kinds = {e["kind"] for e in ev}
    assert "record" in kinds and "lifetime" in kinds


def test_tier_down_does_not_fire(monkeypatch, tmp_path):
    monkeypatch.setattr(moments, "STORE", str(tmp_path / ".m.json"))
    moments.check(_d("齐天大圣", 100 * M, 2 * B))
    assert moments.check(_d("哪吒三太子", 100 * M, 2 * B)) == []   # dropping a tier is not a moment
