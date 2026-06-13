"""Tests for stable TokenPulse CLI rendering contracts."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cli  # noqa: E402


def _status():
    return {
        "generated_at": "2026-06-13T18:45:00+08:00",
        "is_weekend": True,
        "tools": {
            "claude": {
                "today": 25_000_000,
                "target": 100_000_000,
                "mood": "behind",
                "hit": False,
                "percent": 25.0,
                "remaining": 75_000_000,
                "expected_by_now": 40_000_000,
            },
            "codex": {
                "today": 150_000_000,
                "target": 100_000_000,
                "mood": "done",
                "hit": True,
                "percent": 150.0,
                "remaining": 0,
                "expected_by_now": 40_000_000,
            },
        },
        "combined": {
            "today": 175_000_000,
            "target": 200_000_000,
            "percent": 87.5,
            "remaining": 25_000_000,
        },
    }


def _unavailable_limits(reason="codexbar-not-found"):
    return {
        "claude": {"available": False, "reason": reason, "windows": []},
        "codex": {"available": False, "reason": reason, "windows": []},
    }


def test_json_emits_parseable_status_and_limits(monkeypatch, capsys):
    monkeypatch.setattr(cli.core, "status", _status)
    monkeypatch.setattr(cli.limits, "plan_limits", _unavailable_limits)

    assert cli.main(["--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"]["combined"]["today"] == 175_000_000
    assert payload["limits"]["claude"]["available"] is False
    assert set(payload) == {"status", "limits"}


def test_sessions_prints_recent_sessions_without_status(monkeypatch, capsys):
    def fail_status():
        raise AssertionError("core.status should not be called for --sessions")

    monkeypatch.setattr(cli.core, "status", fail_status)
    monkeypatch.setattr(cli.sessions, "recent_sessions", lambda: [
        {"tool": "codex", "age": "5m ago", "name": "TokenPulse CLI", "snippet": "pin contract"},
        {"tool": "claude", "age": "2h ago", "name": "tokenpulse", "snippet": ""},
    ])

    assert cli.main(["--sessions"]) == 0

    out = capsys.readouterr().out
    assert "[codex ]   5m ago  TokenPulse CLI  — pin contract" in out
    assert "[claude]   2h ago  tokenpulse" in out


def test_default_output_contract_with_unavailable_plan(monkeypatch, capsys):
    monkeypatch.setattr(cli.core, "status", _status)
    monkeypatch.setattr(cli.limits, "plan_limits", lambda: _unavailable_limits("no-history"))
    monkeypatch.setattr(cli.sessions, "suggestion", lambda: None)

    assert cli.main([]) == 0

    out = capsys.readouterr().out
    assert "TokenPulse · 2026-06-13 18:45 · weekend" in out
    assert "Claude" in out
    assert "Codex" in out
    assert "Σ  175.0M/200.0M  (88%)  remaining 25.0M" in out
    assert "plan: (CodexBar 未运行/无数据 — no-history)" in out
