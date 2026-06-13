"""Deterministic tests for recent-session suggestions.

All session data is synthetic and rooted in pytest tmp_path fixtures so these
tests never inspect live Claude or Codex logs from the current machine.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sessions  # noqa: E402


NOW = 1_800_000_000.0


def _write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")


def _patch_session_paths(monkeypatch, tmp_path):
    claude_projects = tmp_path / "claude" / "projects"
    codex_index = tmp_path / "codex" / "session_index.jsonl"
    codex_sessions = str(tmp_path / "codex" / "sessions" / "**" / "*.jsonl")
    monkeypatch.setattr(sessions, "CLAUDE_PROJECTS", str(claude_projects))
    monkeypatch.setattr(sessions, "CODEX_INDEX", str(codex_index))
    monkeypatch.setattr(sessions, "CODEX_SESSIONS", codex_sessions)
    return claude_projects, codex_index


def test_age_str_formats_minutes_hours_and_days():
    assert sessions._age_str(NOW - 59, now=NOW) == "0m ago"
    assert sessions._age_str(NOW - 30 * 60, now=NOW) == "30m ago"
    assert sessions._age_str(NOW - 3 * 3600, now=NOW) == "3h ago"
    assert sessions._age_str(NOW - 2 * 86400, now=NOW) == "2d ago"
    assert sessions._age_str(NOW + 60, now=NOW) == "0m ago"


def test_project_name_uses_last_claude_path_segment():
    assert sessions._project_name("-Users-wendy-work-tokenpulse") == "tokenpulse"
    assert sessions._project_name("tokenpulse") == "tokenpulse"
    assert sessions._project_name("----") == "----"


def test_last_user_snippet_normalizes_skips_wrappers_and_truncates(tmp_path):
    transcript = tmp_path / "session.jsonl"
    long_text = " ".join(["alpha"] * 30)
    _write_jsonl(transcript, [
        {"type": "assistant", "message": {"content": "ignore me"}},
        {"type": "user", "message": {"content": "<system-reminder>skip wrapper</system-reminder>"}},
        {"type": "user", "message": {"content": [{"type": "text", "text": " keep \n this\t snippet "}] }},
        {"type": "user", "message": {"content": long_text}},
    ])

    assert sessions._last_user_snippet(str(transcript), limit=20) == "alpha alpha alpha al\u2026"


def test_last_user_snippet_keeps_latest_valid_human_text(tmp_path):
    transcript = tmp_path / "session.jsonl"
    _write_jsonl(transcript, [
        {"type": "user", "message": {"content": "first prompt"}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "skip"}, {"type": "text", "text": " second   prompt "}] }},
        {"type": "user", "message": {"content": "<local-command-stdout>skip</local-command-stdout>"}},
    ])

    assert sessions._last_user_snippet(str(transcript)) == "second prompt"


def test_recent_sessions_merges_claude_and_codex_newest_first(tmp_path, monkeypatch):
    claude_projects, codex_index = _patch_session_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(sessions.time, "time", lambda: NOW)

    claude_project = claude_projects / "-Users-wendy-work-tokenpulse"
    claude_project.mkdir(parents=True)
    claude_file = claude_project / "claude.jsonl"
    _write_jsonl(claude_file, [
        {"type": "user", "message": {"content": "resume claude work"}},
    ])
    os.utime(claude_file, (NOW - 900, NOW - 900))

    codex_index.parent.mkdir(parents=True)
    _write_jsonl(codex_index, [
        {"id": "older", "thread_name": "Older Codex", "updated_at": NOW - 1800},
        {"id": "newer", "thread_name": "Newer Codex", "updated_at": NOW - 300},
    ])

    rows = sessions.recent_sessions(days=1, limit=5)

    assert [(row["tool"], row["name"]) for row in rows] == [
        ("codex", "Newer Codex"),
        ("claude", "tokenpulse"),
        ("codex", "Older Codex"),
    ]
    assert rows[1]["snippet"] == "resume claude work"
    assert rows[0]["age"] == "5m ago"


def test_suggestion_skips_active_session_when_settled_available(monkeypatch):
    rows = [
        {"name": "active", "last_touched": NOW - 120},
        {"name": "settled", "last_touched": NOW - 900},
        {"name": "old", "last_touched": NOW - 1800},
    ]
    monkeypatch.setattr(sessions, "recent_sessions", lambda days, limit: rows)
    monkeypatch.setattr(sessions.time, "time", lambda: NOW)

    assert sessions.suggestion(days=1, min_age_seconds=600)["name"] == "settled"


def test_suggestion_falls_back_to_newest_when_all_rows_active(monkeypatch):
    rows = [
        {"name": "newest", "last_touched": NOW - 60},
        {"name": "also-active", "last_touched": NOW - 300},
    ]
    monkeypatch.setattr(sessions, "recent_sessions", lambda days, limit: rows)
    monkeypatch.setattr(sessions.time, "time", lambda: NOW)

    assert sessions.suggestion(days=1, min_age_seconds=600)["name"] == "newest"
