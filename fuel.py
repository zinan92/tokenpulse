"""Fuel providers for the TokenPulse furnace — where token-burning work comes from.

Two layers, pluggable behind a common interface:
  - FileQueue:     directed one-off prompts you drop in `queue.txt` (highest
                   priority — what you specifically want done).
  - RecurringJobs: your baseline pipeline work from `jobs.json` (never runs
                   dry; runs when the queue is empty and respects per-job
                   cooldowns so the same job doesn't repeat constantly).

Adding Lark / GitHub later = another provider with the same `next_job()` /
`mark_done()` shape; nothing else changes.

Pure stdlib. Immutable Job values.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, replace
from pathlib import Path

HERE = Path(__file__).parent

# Safe defaults for autonomous jobs (no Bash -> can't run destructive shell).
DEFAULT_ALLOWED_TOOLS = "Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,TodoWrite"
DEFAULT_SANDBOX = "workspace-write"  # codex: write only in cwd, no system access


@dataclass(frozen=True)
class Job:
    prompt: str
    source: str                       # "queue" or "recurring:<name>"
    id: str
    cwd: str
    tool: str | None = None           # preferred tool; else dispatcher decides
    allowed_tools: str = DEFAULT_ALLOWED_TOOLS
    sandbox: str = DEFAULT_SANDBOX

    def for_tool(self, tool: str) -> "Job":
        return replace(self, tool=tool)


# --------------------------------------------------------------- file queue

class FileQueue:
    """One prompt per line in `queue.txt`. Blank lines and #comments ignored.

    A line may be prefixed `claude:` or `codex:` to pin the tool, e.g.
    `codex: refactor the parser in ~/work/foo`.
    """

    def __init__(self, path: str | None = None):
        self.path = Path(path) if path else HERE / "queue.txt"

    def _lines(self) -> list[str]:
        if not self.path.exists():
            return []
        return self.path.read_text(encoding="utf-8").splitlines()

    def next_job(self, default_cwd: str) -> Job | None:
        for raw in self._lines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            tool = None
            for t in ("claude", "codex"):
                if line.lower().startswith(t + ":"):
                    tool = t
                    line = line[len(t) + 1:].strip()
                    break
            return Job(prompt=line, source="queue", id=str(abs(hash(raw)) % 10**8),
                       cwd=default_cwd, tool=tool)
        return None

    def mark_done(self, job: Job) -> None:
        """Remove the first queue line whose prompt matches (idempotent)."""
        if not self.path.exists():
            return
        kept = []
        removed = False
        for raw in self._lines():
            line = raw.strip()
            stripped = line
            for t in ("claude", "codex"):
                if stripped.lower().startswith(t + ":"):
                    stripped = stripped[len(t) + 1:].strip()
            if not removed and stripped == job.prompt:
                removed = True
                continue
            kept.append(raw)
        self.path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


# ------------------------------------------------------------ recurring jobs

class RecurringJobs:
    """Baseline pipeline jobs from `jobs.json`, with per-job cooldowns.

    jobs.json:
      [
        {"name": "market-scan", "tool": "claude", "cooldown_hours": 6,
         "cwd": "~/work/trading-co", "allowed_tools": "Read,Write,Glob,Grep,Bash",
         "prompt": "Run the daily market breadth scan and write a summary to ..."},
        ...
      ]
    State (last-run times) lives in `furnace-state.json`.
    """

    def __init__(self, jobs_path: str | None = None, state_path: str | None = None):
        self.jobs_path = Path(jobs_path) if jobs_path else HERE / "jobs.json"
        self.state_path = Path(state_path) if state_path else HERE / "furnace-state.json"

    def _load_jobs(self) -> list[dict]:
        if not self.jobs_path.exists():
            return []
        try:
            data = json.loads(self.jobs_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (ValueError, OSError):
            return []

    def _load_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}

    def next_job(self, default_cwd: str, now: float | None = None) -> Job | None:
        now = now if now is not None else time.time()
        state = self._load_state().get("recurring_last_run", {})
        eligible = []
        for j in self._load_jobs():
            name = j.get("name")
            prompt = j.get("prompt")
            if not name or not prompt:
                continue
            cooldown = float(j.get("cooldown_hours", 6)) * 3600
            last = state.get(name, 0)
            if now - last < cooldown:
                continue
            eligible.append((last, j))
        if not eligible:
            return None
        eligible.sort(key=lambda x: x[0])  # least-recently-run first
        j = eligible[0][1]
        cwd = os.path.expanduser(j.get("cwd") or default_cwd)
        return Job(
            prompt=j["prompt"],
            source=f"recurring:{j['name']}",
            id=j["name"],
            cwd=cwd,
            tool=j.get("tool"),
            allowed_tools=j.get("allowed_tools", DEFAULT_ALLOWED_TOOLS),
            sandbox=j.get("sandbox", DEFAULT_SANDBOX),
        )

    def mark_done(self, job: Job, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        state = self._load_state()
        runs = state.setdefault("recurring_last_run", {})
        runs[job.id] = now
        try:
            self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except OSError:
            pass


def next_job(default_cwd: str, queue_path=None, jobs_path=None, state_path=None,
             tool: str | None = None, now: float | None = None):
    """Fetch the next job: directed queue first, then recurring baseline.

    If `tool` is given, only return a job runnable by that tool (no tool pin, or
    pinned to it). Returns (job, provider) or (None, None).
    """
    fq = FileQueue(queue_path)
    rj = RecurringJobs(jobs_path, state_path)
    for provider in (fq, rj):
        job = provider.next_job(default_cwd) if provider is fq else provider.next_job(default_cwd, now)
        if job is None:
            continue
        if tool and job.tool and job.tool != tool:
            continue  # pinned to the other tool; skip (v1: simple, don't scan deeper)
        return job.for_tool(job.tool or tool), provider
    return None, None
