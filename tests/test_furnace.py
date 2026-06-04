"""Tests for the furnace fuel providers and dispatch decision logic.

Real headless dispatch is NOT tested here (it consumes tokens / launches CLIs);
it's validated by a manual measured round-trip. These cover the pure logic:
fuel selection, cooldowns, lock staleness, behind-detection, and the decision
tree (disabled / off-hours / cap / on-pace / dispatch).
"""
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fuel  # noqa: E402
import furnace  # noqa: E402


# --------------------------------------------------------------- file queue

def test_filequeue_parses_tool_prefix_and_skips_comments(tmp_path):
    q = tmp_path / "queue.txt"
    q.write_text("# comment\n\ncodex: refactor foo\nplain claude job\n")
    fq = fuel.FileQueue(str(q))
    job = fq.next_job(default_cwd="/work")
    assert job.tool == "codex"
    assert job.prompt == "refactor foo"
    assert job.source == "queue"
    assert job.allowed_tools == fuel.DEFAULT_ALLOWED_TOOLS


def test_filequeue_mark_done_removes_line(tmp_path):
    q = tmp_path / "queue.txt"
    q.write_text("codex: a\nplain b\n")
    fq = fuel.FileQueue(str(q))
    job = fq.next_job("/w")  # "a", pinned codex
    fq.mark_done(job)
    remaining = [l for l in q.read_text().splitlines() if l.strip()]
    assert remaining == ["plain b"]
    nxt = fq.next_job("/w")
    assert nxt.prompt == "plain b"


# ------------------------------------------------------------ recurring jobs

def _jobs(tmp_path, items):
    p = tmp_path / "jobs.json"
    p.write_text(json.dumps(items))
    return p


def test_recurring_respects_cooldown_and_picks_oldest(tmp_path):
    jobs = _jobs(tmp_path, [
        {"name": "a", "prompt": "do a", "cooldown_hours": 6},
        {"name": "b", "prompt": "do b", "cooldown_hours": 6},
    ])
    state = tmp_path / "state.json"
    now = 1_000_000.0
    # a ran 1h ago (within cooldown), b ran 10h ago (eligible)
    state.write_text(json.dumps({"recurring_last_run": {"a": now - 3600, "b": now - 36000}}))
    rj = fuel.RecurringJobs(str(jobs), str(state))
    job = rj.next_job("/w", now=now)
    assert job.id == "b"
    assert job.source == "recurring:b"


def test_recurring_none_when_all_cooling_down(tmp_path):
    jobs = _jobs(tmp_path, [{"name": "a", "prompt": "x", "cooldown_hours": 6}])
    state = tmp_path / "state.json"
    now = 1_000_000.0
    state.write_text(json.dumps({"recurring_last_run": {"a": now - 60}}))
    rj = fuel.RecurringJobs(str(jobs), str(state))
    assert rj.next_job("/w", now=now) is None


def test_recurring_mark_done_writes_state(tmp_path):
    jobs = _jobs(tmp_path, [{"name": "a", "prompt": "x", "cooldown_hours": 1}])
    state = tmp_path / "state.json"
    rj = fuel.RecurringJobs(str(jobs), str(state))
    job = rj.next_job("/w", now=1_000_000.0)  # > cooldown, empty state -> eligible
    rj.mark_done(job, now=2_000_000.0)
    saved = json.loads(state.read_text())
    assert saved["recurring_last_run"]["a"] == 2_000_000.0


def test_next_job_prefers_queue_over_recurring(tmp_path):
    q = tmp_path / "queue.txt"
    q.write_text("claude: urgent\n")
    jobs = _jobs(tmp_path, [{"name": "bg", "prompt": "background", "cooldown_hours": 1}])
    state = tmp_path / "s.json"
    job, provider = fuel.next_job("/w", queue_path=str(q), jobs_path=str(jobs),
                                  state_path=str(state))
    assert job.source == "queue"
    assert isinstance(provider, fuel.FileQueue)


# ----------------------------------------------------------------- locks

def test_lock_held_false_when_pid_dead(tmp_path, monkeypatch):
    monkeypatch.setattr(furnace, "HERE", tmp_path)
    furnace._lock_path("claude").write_text(json.dumps({"pid": 999999, "started": time.time()}))
    assert furnace.lock_held("claude", 1800) is False  # pid not alive -> stale


def test_lock_held_true_when_running(tmp_path, monkeypatch):
    monkeypatch.setattr(furnace, "HERE", tmp_path)
    furnace._lock_path("claude").write_text(json.dumps({"pid": os.getpid(), "started": time.time()}))
    assert furnace.lock_held("claude", 1800) is True


def test_lock_held_false_when_overran(tmp_path, monkeypatch):
    monkeypatch.setattr(furnace, "HERE", tmp_path)
    furnace._lock_path("claude").write_text(
        json.dumps({"pid": os.getpid(), "started": time.time() - 99999}))
    assert furnace.lock_held("claude", 1800) is False


# --------------------------------------------------------------- behind logic

def _status(claude_hit, claude_def, codex_hit, codex_def):
    def t(hit, deficit):
        return {"hit": hit, "deficit_vs_pace": deficit, "remaining": deficit}
    return {"tools": {"claude": t(claude_hit, claude_def), "codex": t(codex_hit, codex_def)}}


def test_behind_tools_orders_by_deficit():
    st = _status(False, 30, False, 80)
    pl = {"claude": {"available": False}, "codex": {"available": False}}
    out = furnace._behind_tools(st, pl, {"plan_behind_threshold": 10})
    assert [t for t, _ in out] == ["codex", "claude"]  # codex more behind


def test_behind_tools_triggers_on_weekly_plan_even_if_token_hit():
    st = _status(True, 0, True, 0)  # both hit token target
    pl = {"claude": {"available": True, "windows": [
              {"name": "weekly", "pace": {"on_pace": False, "behind_by": 34}}]},
          "codex": {"available": False}}
    out = furnace._behind_tools(st, pl, {"plan_behind_threshold": 10})
    assert ("claude" in [t for t, _ in out])


# --------------------------------------------------------------- decide tree

BASE = {"furnace": {"enabled": True, "max_jobs_per_day": 12, "max_runtime_minutes": 30,
                    "default_cwd": "/w"},
        "active_window": {"start": "09:00", "end": "23:59"},
        "plan_behind_threshold": 10}
NOON = datetime(2026, 6, 3, 12, 0).astimezone()


def test_decide_skips_when_disabled():
    cfg = {**BASE, "furnace": {**BASE["furnace"], "enabled": False}}
    assert furnace.decide(cfg, NOON)["action"] == "skip"


def test_decide_skips_outside_hours():
    assert furnace.decide(BASE, datetime(2026, 6, 3, 7, 0).astimezone())["action"] == "skip"


def test_decide_dispatches_when_behind_with_job(tmp_path, monkeypatch):
    monkeypatch.setattr(furnace, "HERE", tmp_path)
    monkeypatch.setattr(furnace, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(furnace.core, "status", lambda now=None, config=None: _status(False, 50, False, 20))
    monkeypatch.setattr(furnace.limits, "plan_limits", lambda: {"claude": {"available": False}, "codex": {"available": False}})
    job = fuel.Job(prompt="p", source="queue", id="1", cwd="/w", tool="claude")
    monkeypatch.setattr(furnace.fuel, "next_job", lambda **k: (job, fuel.FileQueue("/nope")))
    plan = furnace.decide(BASE, NOON)
    assert plan["action"] == "dispatch"
    assert plan["tool"] == "claude"  # more behind (deficit 50 > 20)


def test_decide_skips_when_on_pace(monkeypatch, tmp_path):
    monkeypatch.setattr(furnace, "STATE_PATH", tmp_path / "s.json")
    monkeypatch.setattr(furnace.core, "status", lambda now=None, config=None: _status(True, 0, True, 0))
    monkeypatch.setattr(furnace.limits, "plan_limits", lambda: {"claude": {"available": False}, "codex": {"available": False}})
    assert furnace.decide(BASE, NOON)["action"] == "skip"


def test_decide_skips_at_daily_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(furnace, "STATE_PATH", tmp_path / "s.json")
    (tmp_path / "s.json").write_text(json.dumps({"runs_per_day": {NOON.date().isoformat(): 12}}))
    assert furnace.decide(BASE, NOON)["action"] == "skip"


# --------------------------------------------------------------- commands

def test_build_command_claude_sanitizes_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("PATH", "/usr/bin")
    job = fuel.Job(prompt="hi", source="queue", id="1", cwd="/w", tool="claude")
    argv, env = furnace.build_command("claude", job)
    assert argv[:2] == ["claude", "-p"]
    assert "--allowedTools" in argv
    assert "ANTHROPIC_API_KEY" not in env  # stripped
    assert "PATH" in env


def test_build_command_codex_sandbox(monkeypatch):
    job = fuel.Job(prompt="hi", source="queue", id="1", cwd="/w", tool="codex", sandbox="workspace-write")
    argv, env = furnace.build_command("codex", job)
    assert argv[:3] == ["codex", "exec", "--skip-git-repo-check"]
    assert "--sandbox" in argv and "workspace-write" in argv
