"""Tests for the settings read/validate/merge/write layer."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import configio  # noqa: E402


def test_validate_accepts_good_partial():
    p = {"targets": {"claude": {"weekday": 200, "weekend": 100}}}
    assert configio.validate_partial(p) == []


def test_validate_rejects_bad_target():
    errs = configio.validate_partial({"targets": {"claude": {"weekday": 0}}})  # must be > 0
    assert any("目标" in e for e in errs)


def test_deep_merge_preserves_siblings():
    base = {"targets": {"claude": {"weekday": 150, "weekend": 150}, "codex": {"weekday": 150}},
            "other": 1}
    patch = {"targets": {"claude": {"weekday": 250}}}
    out = configio.deep_merge(base, patch)
    assert out["targets"]["claude"]["weekday"] == 250
    assert out["targets"]["claude"]["weekend"] == 150   # sibling kept
    assert out["targets"]["codex"]["weekday"] == 150     # sibling tool kept
    assert out["other"] == 1


def test_save_partial_writes_and_strips_noneditable(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"targets": {"claude": {"weekday": 150, "weekend": 150}},
                               "furnace": {"enabled": False}}))
    monkeypatch.setattr(configio, "CONFIG_PATH", cfg)

    # includes non-editable keys (furnace, plan_monthly_price) that must be ignored
    res = configio.save_partial({"targets": {"claude": {"weekday": 300}},
                                 "plan_monthly_price": {"claude": 250},
                                 "furnace": {"enabled": True}})
    assert res["ok"] is True
    written = json.loads(cfg.read_text())
    assert written["targets"]["claude"]["weekday"] == 300
    assert written["targets"]["claude"]["weekend"] == 150        # sibling preserved
    assert "plan_monthly_price" not in written                   # non-editable, stripped
    assert written["furnace"]["enabled"] is False                # UI cannot flip furnace


def test_save_partial_rejects_invalid(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text("{}")
    monkeypatch.setattr(configio, "CONFIG_PATH", cfg)
    res = configio.save_partial({"targets": {"claude": {"weekday": -5}}})
    assert res["ok"] is False and res["errors"]
    assert cfg.read_text() == "{}"   # nothing written on failure


def test_validate_ranking_consent():
    assert configio.validate_partial({"ranking": {"enabled": True}}) == []
    assert configio.validate_partial({"ranking": {"enabled": False}}) == []
    assert "ranking.enabled" in configio.validate_partial({"ranking": {"enabled": "yes"}})
    assert "ranking" in configio.validate_partial({"ranking": "nope"})


def test_display_accepts_compact_and_menu_bar_only():
    assert configio.validate_partial({"display": {"mode": "compact", "placement": "menu_bar"}}) == []
    assert "display.mode" in configio.validate_partial({"display": {"mode": "tiny"}})
    assert "display.placement" in configio.validate_partial({"display": {"placement": "dock"}})


def test_save_partial_ranking_consent_preserves_url(tmp_path, monkeypatch):
    """Toggling consent must flip enabled but KEEP the shipped board url (the UI
    only sends {ranking:{enabled:...}}; the deep-merge preserves url)."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"ranking": {"enabled": False, "url": "https://board.dev"}}))
    monkeypatch.setattr(configio, "CONFIG_PATH", cfg)

    res = configio.save_partial({"ranking": {"enabled": True}})
    assert res["ok"] is True
    written = json.loads(cfg.read_text())
    assert written["ranking"] == {"enabled": True, "url": "https://board.dev"}
