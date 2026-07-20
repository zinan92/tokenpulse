"""Tests for Telegram nudge configuration helpers."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import nudge  # noqa: E402


def test_load_secret_prefers_env(monkeypatch, tmp_path):
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir()
    (secret_dir / "token").write_text("from-file", encoding="utf-8")
    monkeypatch.setattr(nudge, "SECRET_DIRS", (secret_dir,))
    monkeypatch.setenv("TOKENPULSE_TEST_SECRET", "from-env")

    assert nudge._load_secret("TOKENPULSE_TEST_SECRET", "token") == "from-env"


def test_load_secret_checks_underscore_secret_dir(monkeypatch, tmp_path):
    missing_dir = tmp_path / "secrets"
    underscore_dir = tmp_path / "_secrets"
    underscore_dir.mkdir()
    (underscore_dir / "token").write_text("from-underscore", encoding="utf-8")
    monkeypatch.setattr(nudge, "SECRET_DIRS", (missing_dir, underscore_dir))
    monkeypatch.delenv("TOKENPULSE_TEST_SECRET", raising=False)

    assert nudge._load_secret("TOKENPULSE_TEST_SECRET", "token") == "from-underscore"
