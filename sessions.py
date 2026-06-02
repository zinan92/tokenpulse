"""Recent active sessions across Claude Code and Codex.

Powers the gadget's "go resume this" suggestion: the point isn't a static
to-do list, it's surfacing what you were *actually* working on recently so you
know exactly where to jump back in and keep burning tokens.

Pure stdlib.
"""
from __future__ import annotations

import glob
import json
import os
import time
from datetime import datetime

CLAUDE_PROJECTS = os.path.expanduser("~/.claude/projects")
CODEX_INDEX = os.path.expanduser("~/.codex/session_index.jsonl")
CODEX_SESSIONS = os.path.expanduser("~/.codex/sessions/**/*.jsonl")


def _age_str(epoch: float, now: float | None = None) -> str:
    now = now if now is not None else time.time()
    secs = max(0, now - epoch)
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def _project_name(dir_name: str) -> str:
    """`-Users-wendy-work-trading-co-intel` -> `trading-co-intel`."""
    parts = [p for p in dir_name.split("-") if p]
    return parts[-1] if parts else dir_name


def _last_user_snippet(path: str, limit: int = 80) -> str:
    """Cheap scan for the most recent human prompt in a Claude transcript."""
    snippet = ""
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if d.get("type") != "user":
                    continue
                msg = d.get("message")
                content = msg.get("content") if isinstance(msg, dict) else None
                text = ""
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            break
                text = " ".join(text.split())
                if text and not text.startswith("<"):
                    snippet = text
    except OSError:
        return ""
    return snippet[:limit] + ("…" if len(snippet) > limit else "")


def _claude_recent(days: int) -> list[dict]:
    floor = time.time() - days * 86400
    best: dict[str, dict] = {}  # project name -> newest file info
    if not os.path.isdir(CLAUDE_PROJECTS):
        return []
    for entry in os.listdir(CLAUDE_PROJECTS):
        proj_dir = os.path.join(CLAUDE_PROJECTS, entry)
        if not os.path.isdir(proj_dir):
            continue
        name = _project_name(entry)
        for f in glob.glob(os.path.join(proj_dir, "*.jsonl")):
            try:
                m = os.path.getmtime(f)
            except OSError:
                continue
            if m < floor:
                continue
            if name not in best or m > best[name]["mtime"]:
                best[name] = {"mtime": m, "path": f, "name": name}
    out = []
    for info in best.values():
        out.append({
            "tool": "claude",
            "name": info["name"],
            "last_touched": info["mtime"],
            "age": _age_str(info["mtime"]),
            "snippet": _last_user_snippet(info["path"]),
        })
    return out


def _codex_recent(days: int) -> list[dict]:
    floor = time.time() - days * 86400
    out = []
    if os.path.exists(CODEX_INDEX):
        try:
            with open(CODEX_INDEX, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    upd = d.get("updated_at")
                    dt = None
                    if isinstance(upd, str):
                        try:
                            dt = datetime.fromisoformat(upd.replace("Z", "+00:00")).timestamp()
                        except ValueError:
                            dt = None
                    elif isinstance(upd, (int, float)):
                        dt = float(upd)
                    if dt is None or dt < floor:
                        continue
                    out.append({
                        "tool": "codex",
                        "name": d.get("thread_name") or d.get("id", "codex session"),
                        "last_touched": dt,
                        "age": _age_str(dt),
                        "snippet": "",
                    })
        except OSError:
            pass
    if out:
        return out
    # Fallback: derive from session file mtimes if the index is unavailable
    seen = set()
    for f in glob.glob(CODEX_SESSIONS, recursive=True):
        try:
            m = os.path.getmtime(f)
        except OSError:
            continue
        if m < floor:
            continue
        base = os.path.basename(f)
        if base in seen:
            continue
        seen.add(base)
        out.append({
            "tool": "codex",
            "name": base.replace("rollout-", "").replace(".jsonl", "")[:40],
            "last_touched": m,
            "age": _age_str(m),
            "snippet": "",
        })
    return out


def recent_sessions(days: int = 5, limit: int = 8) -> list[dict]:
    """Most-recently-touched sessions across both tools, newest first."""
    merged = _claude_recent(days) + _codex_recent(days)
    merged.sort(key=lambda x: x["last_touched"], reverse=True)
    return merged[:limit]


def suggestion(days: int = 5, min_age_seconds: int = 300) -> dict | None:
    """A single session to nudge the user back into.

    Skips the currently-active session (anything touched within
    `min_age_seconds`) so the suggestion points at work you stepped away from,
    not the window you're already in. Falls back to the newest if all are live.
    """
    rows = recent_sessions(days=days, limit=12)
    if not rows:
        return None
    now = time.time()
    settled = [r for r in rows if now - r["last_touched"] >= min_age_seconds]
    return settled[0] if settled else rows[0]


if __name__ == "__main__":
    for r in recent_sessions():
        label = r["name"]
        snip = f"  — {r['snippet']}" if r["snippet"] else ""
        print(f"[{r['tool']:6}] {r['age']:>8}  {label}{snip}")
