"""Tests for single-session peak detection."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import peaks  # noqa: E402

M = 1_000_000


def test_pick_larger():
    a = {"total": 100 * M}
    b = {"total": 300 * M}
    assert peaks.pick_larger(a, b)["total"] == 300 * M
    assert peaks.pick_larger(None, a) is a
    assert peaks.pick_larger(a, None) is a


def test_scan_picks_biggest_session_across_tools(tmp_path, monkeypatch):
    cl = tmp_path / "claude"; cl.mkdir()
    cx = tmp_path / "codex"; cx.mkdir()
    # two Claude files (each a session); the bigger is 300M
    (cl / "s1.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [
        {"sessionId": "s1", "timestamp": "2026-06-01T10:00:00Z",
         "message": {"id": "m1", "usage": {"input_tokens": 100 * M, "output_tokens": 0}}}]))
    (cl / "s2.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [
        {"sessionId": "s2", "timestamp": "2026-06-02T10:00:00Z",
         "message": {"id": "m2", "usage": {"input_tokens": 300 * M, "output_tokens": 0}}}]))
    # one Codex session at 500M (the overall peak)
    (cx / "rollout-2026-06-03T10-00-00-aaaa-bbbb-cccc-dddd-eeee.jsonl").write_text(
        json.dumps({"timestamp": "2026-06-03T10:00:00Z",
                    "payload": {"info": {"last_token_usage": {"total_tokens": 500 * M}}}}) + "\n")
    monkeypatch.setattr(peaks.core, "CLAUDE_GLOB", str(cl / "**" / "*.jsonl"))
    monkeypatch.setattr(peaks.core, "CODEX_GLOBS", (str(cx / "**" / "*.jsonl"),))
    peak = peaks.scan_session_peak()
    assert peak["total"] == 500 * M and peak["tool"] == "codex"
