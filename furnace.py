"""TokenPulse furnace — autonomously burn idle quota on *valuable* work.

When you're behind pace (token target OR real weekly plan) during work hours,
the furnace dispatches one headless job to the most-behind tool, pulling fuel
from the directed queue first, then your recurring pipeline jobs. Output goes to
a file + a Telegram ping. Verified: headless runs consume the subscription and
their tokens land in core.py's scan, so each job shrinks the deficit — the loop
self-regulates.

Safety rails (the furnace runs unattended):
  - kill switch: config furnace.enabled
  - work-hours gate (reuse active_window)
  - per-tool lock checked BEFORE dispatch (a running job blocks new ones)
  - daily cap on furnace-launched jobs
  - sanitized env for `claude -p` (forces claude.ai subscription, not the
    session's proxy/API env)
  - curated --allowedTools (NO --dangerously-skip-permissions; no Bash by
    default) for Claude; --sandbox workspace-write for Codex (NOT its
    danger-full-access default)
  - per-job runtime timeout

Run from launchd/cron every ~15 min. `--dry-run` to see what it would do.

Pure stdlib.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import core
import fuel
import limits
import nudge

HERE = Path(__file__).parent
STATE_PATH = HERE / "furnace-state.json"
OUTPUT_DIR = HERE / "furnace-output"
LOG_DIR = HERE / "furnace-logs"

# Env vars the current session injects to route through its proxy/API — must be
# stripped so `claude -p` authenticates against the claude.ai subscription.
CLAUDE_SANITIZE = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL", "ANTHROPIC_CUSTOM_HEADERS",
)


# ----------------------------------------------------------------- state

def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {}


def _save_state(state: dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass


def _runs_today(state: dict, day: str) -> int:
    return state.get("runs_per_day", {}).get(day, 0)


def _record_run(state: dict, day: str) -> None:
    state.setdefault("runs_per_day", {})[day] = _runs_today(state, day) + 1


# ----------------------------------------------------------------- locks

def _lock_path(tool: str) -> Path:
    return HERE / f"furnace-{tool}.lock"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def lock_held(tool: str, max_runtime_s: float, now: float | None = None) -> bool:
    """True if a furnace job for `tool` is genuinely still running."""
    now = now if now is not None else time.time()
    p = _lock_path(tool)
    if not p.exists():
        return False
    try:
        info = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    pid, started = info.get("pid"), info.get("started", 0)
    if not pid or not _pid_alive(pid):
        return False  # stale: process gone
    if now - started > max_runtime_s:
        return False  # stale: overran its timeout
    return True


def _acquire_lock(tool: str) -> None:
    _lock_path(tool).write_text(
        json.dumps({"pid": os.getpid(), "started": time.time()}), encoding="utf-8")


def _release_lock(tool: str) -> None:
    try:
        _lock_path(tool).unlink()
    except OSError:
        pass


# ----------------------------------------------------------- behind logic

def _behind_tools(st: dict, pl: dict, config: dict) -> list[tuple]:
    """(tool, deficit) for tools behind on token pace or weekly plan, worst first."""
    thr = config.get("plan_behind_threshold", 10)
    out = []
    for tool, t in st["tools"].items():
        token_behind = (not t["hit"]) and t["deficit_vs_pace"] > 0
        plan_behind = False
        for w in pl.get(tool, {}).get("windows", []) if pl.get(tool, {}).get("available") else []:
            p = w.get("pace")
            if p and not p["on_pace"] and p["behind_by"] >= thr:
                plan_behind = True
        if token_behind or plan_behind:
            out.append((tool, t["deficit_vs_pace"]))
    out.sort(key=lambda x: x[1], reverse=True)
    return out


# ----------------------------------------------------------------- dispatch

def build_command(tool: str, job: fuel.Job) -> tuple[list[str], dict]:
    """(argv, env) for a headless run. env=None means inherit."""
    if tool == "claude":
        env = {k: v for k, v in os.environ.items() if k not in CLAUDE_SANITIZE}
        argv = ["claude", "-p", job.prompt,
                "--allowedTools", job.allowed_tools,
                "--output-format", "text"]
        return argv, env
    # codex
    argv = ["codex", "exec", "--skip-git-repo-check",
            "--sandbox", job.sandbox, job.prompt]
    return argv, dict(os.environ)


def run_job(tool: str, job: fuel.Job, config: dict, day: str) -> dict:
    """Run one job synchronously, holding the tool lock for its duration."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)
    max_runtime = config.get("furnace", {}).get("max_runtime_minutes", 30) * 60
    argv, env = build_command(tool, job)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"{stamp}-{tool}-{job.id}.log"

    before = (core.claude_today if tool == "claude" else core.codex_today)(
        datetime.now().astimezone().date())["total"]

    _acquire_lock(tool)
    rc, timed_out = 0, False
    try:
        with open(log_path, "w", encoding="utf-8") as logf:
            logf.write(f"# {job.source} · {tool}\n# cwd={job.cwd}\n# {job.prompt}\n\n")
            logf.flush()
            proc = subprocess.Popen(
                argv, cwd=job.cwd, env=env,
                stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                rc = proc.wait(timeout=max_runtime)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                rc = -1
    finally:
        _release_lock(tool)

    after = (core.claude_today if tool == "claude" else core.codex_today)(
        datetime.now().astimezone().date())["total"]
    burned = max(0, after - before)
    return {"tool": tool, "rc": rc, "timed_out": timed_out, "burned": burned,
            "log": str(log_path), "source": job.source, "prompt": job.prompt}


# ----------------------------------------------------------------- main

def decide(config: dict, now: datetime) -> dict:
    """Pure-ish decision (no dispatch): what would the furnace do right now?"""
    if not config.get("furnace", {}).get("enabled", False):
        return {"action": "skip", "reason": "furnace disabled"}
    frac = core._active_fraction(now, config)
    if frac <= 0 or frac >= 1:
        return {"action": "skip", "reason": "outside work hours"}
    day = now.date().isoformat()
    state = _load_state()
    cap = config.get("furnace", {}).get("max_jobs_per_day", 12)
    if _runs_today(state, day) >= cap:
        return {"action": "skip", "reason": f"daily cap reached ({cap})"}

    st = core.status(now=now, config=config)
    pl = limits.plan_limits()
    behind = _behind_tools(st, pl, config)
    if not behind:
        return {"action": "skip", "reason": "on pace, nothing to burn"}

    max_runtime = config.get("furnace", {}).get("max_runtime_minutes", 30) * 60
    for tool, deficit in behind:
        if lock_held(tool, max_runtime):
            continue  # a job for this tool is still running
        job, provider = fuel.next_job(
            default_cwd=os.path.expanduser(config.get("furnace", {}).get("default_cwd", str(HERE))),
            tool=tool)
        if job is None:
            continue
        return {"action": "dispatch", "tool": tool, "job": job, "provider": provider,
                "deficit": deficit, "day": day, "state": state}
    return {"action": "skip", "reason": "behind but no eligible job / all locked"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="decide + print, don't dispatch")
    ap.add_argument("--force", action="store_true", help="ignore work-hours/behind gates")
    args = ap.parse_args(argv)

    config = core.load_config()
    now = datetime.now().astimezone()
    plan = decide(config, now)

    if args.force and plan["action"] == "skip":
        # force a job regardless of pace (still respects lock + cap + enabled)
        job, provider = fuel.next_job(
            default_cwd=config.get("furnace", {}).get("default_cwd", str(HERE)))
        if job and config.get("furnace", {}).get("enabled", False):
            plan = {"action": "dispatch", "tool": job.tool or "claude", "job": job,
                    "provider": provider, "deficit": 0, "day": now.date().isoformat(),
                    "state": _load_state()}

    if plan["action"] == "skip":
        print(f"[furnace] skip: {plan['reason']}")
        return 0

    tool, job = plan["tool"], plan["job"]
    print(f"[furnace] dispatch {tool} <- {job.source}: {job.prompt[:70]}")
    if args.dry_run:
        argv_, _ = build_command(tool, job)
        print("[furnace] would run:", " ".join(argv_[:4]), "…  cwd=", job.cwd)
        return 0

    result = run_job(tool, job, config, plan["day"])
    plan["provider"].mark_done(job)
    state = plan["state"]
    _record_run(state, plan["day"])
    _save_state(state)

    status = "✓" if result["rc"] == 0 else ("⏱timeout" if result["timed_out"] else f"rc={result['rc']}")
    msg = (f"🔥 furnace · {tool} · {job.source} {status}\n"
           f"burned ~{core.humanize(result['burned'])} tokens\n"
           f"« {job.prompt[:120]} »\n"
           f"log: {result['log']}")
    print("[furnace]", msg.replace("\n", " | "))
    if config.get("furnace", {}).get("telegram", True):
        nudge.send_telegram(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
