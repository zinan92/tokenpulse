"""TokenPulse core engine.

Computes today's total token throughput for Claude Code and Codex from local
logs, applies daily targets (weekday / weekend), and derives pace + mood.

Validated against CodexBar: Claude dedup-by-(message.id, requestId) total and
Codex per-turn last_token_usage deltas reproduce the numbers CodexBar shows.

Pure stdlib. No mutation of inputs; every function returns fresh data.
"""
from __future__ import annotations

import glob
import json
import os
from datetime import datetime, time, timedelta
from pathlib import Path

CLAUDE_GLOB = os.path.expanduser("~/.claude/projects/**/*.jsonl")
CODEX_GLOBS = (
    os.path.expanduser("~/.codex/sessions/**/*.jsonl"),
    os.path.expanduser("~/.codex/archived_sessions/**/*.jsonl"),
)

# ---------------------------------------------------------------- time helpers


def _parse_ts(ts: str) -> datetime | None:
    """Parse an ISO-8601 timestamp (possibly 'Z'-suffixed) to a tz-aware dt."""
    if not ts or not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _date_in_zone(dt: datetime, day_boundary: str):
    """Calendar date of a tz-aware datetime in the chosen zone."""
    if day_boundary == "utc":
        from datetime import timezone

        return dt.astimezone(timezone.utc).date()
    return dt.astimezone().date()


def reference_day(now: datetime, day_boundary: str = "local"):
    """The calendar date that counts as 'today' under the given boundary."""
    return _date_in_zone(now, day_boundary)


def _is_on_day(ts: str, day, day_boundary: str) -> bool:
    dt = _parse_ts(ts)
    if dt is None:
        return False
    return _date_in_zone(dt, day_boundary) == day


def _day_start_mtime(day) -> float:
    """Conservative file-mtime floor for prefiltering: local midnight of the day
    BEFORE `day`. The one-day margin guarantees no event whose in-zone date is
    `day` (max tz offset < 24h) is excluded by mtime; the exact line-level date
    filter does the real work."""
    midnight = datetime.combine(day, time(0, 0)).astimezone() - timedelta(days=1)
    return midnight.timestamp()


# ------------------------------------------------------------------- extractors


def claude_today(day, day_boundary: str = "local") -> dict:
    """Total Claude tokens for `day`, deduped by (message.id, requestId).

    Returns {'total', 'input', 'cache_creation', 'cache_read', 'output',
             'messages', 'duplicates_skipped'}.
    """
    floor = _day_start_mtime(day)
    seen: set[tuple] = set()
    agg = {"input": 0, "cache_creation": 0, "cache_read": 0, "output": 0}
    messages = 0
    dups = 0
    for f in glob.glob(CLAUDE_GLOB, recursive=True):
        try:
            if os.path.getmtime(f) < floor:
                continue
        except OSError:
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if not _is_on_day(d.get("timestamp"), day, day_boundary):
                        continue
                    msg = d.get("message")
                    if not isinstance(msg, dict):
                        continue
                    usage = msg.get("usage")
                    if not isinstance(usage, dict):
                        continue
                    mid = msg.get("id")
                    key = (mid, d.get("requestId"))
                    if mid and key in seen:
                        dups += 1
                        continue
                    if mid:
                        seen.add(key)
                    agg["input"] += usage.get("input_tokens", 0) or 0
                    agg["cache_creation"] += usage.get("cache_creation_input_tokens", 0) or 0
                    agg["cache_read"] += usage.get("cache_read_input_tokens", 0) or 0
                    agg["output"] += usage.get("output_tokens", 0) or 0
                    messages += 1
        except OSError:
            continue
    total = sum(agg.values())
    return {"total": total, **agg, "messages": messages, "duplicates_skipped": dups}


def _codex_session_uuid(path: str) -> str:
    """Extract the trailing UUID from a rollout-...-<uuid>.jsonl filename."""
    base = os.path.basename(path)
    stem = base[:-6] if base.endswith(".jsonl") else base
    parts = stem.split("-")
    return "-".join(parts[-5:]) if len(parts) >= 5 else stem


def codex_today(day, day_boundary: str = "local") -> dict:
    """Total Codex tokens for `day`, summed from per-turn last_token_usage.

    Sessions duplicated across sessions/ and archived_sessions/ are counted
    once (deduped by session UUID, keeping the most-recently-modified file).
    Returns {'total', 'turns', 'sessions'}.
    """
    floor = _day_start_mtime(day)
    # uuid -> chosen file (max mtime)
    chosen: dict[str, str] = {}
    mtimes: dict[str, float] = {}
    for pattern in CODEX_GLOBS:
        for f in glob.glob(pattern, recursive=True):
            try:
                m = os.path.getmtime(f)
            except OSError:
                continue
            if m < floor:
                continue
            uid = _codex_session_uuid(f)
            if uid not in mtimes or m > mtimes[uid]:
                mtimes[uid] = m
                chosen[uid] = f

    total = 0
    turns = 0
    sessions: set[str] = set()
    for uid, f in chosen.items():
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if not _is_on_day(d.get("timestamp"), day, day_boundary):
                        continue
                    payload = d.get("payload")
                    info = payload.get("info") if isinstance(payload, dict) else None
                    if not isinstance(info, dict):
                        continue
                    last = info.get("last_token_usage")
                    if not isinstance(last, dict):
                        continue
                    total += last.get("total_tokens", 0) or 0
                    turns += 1
                    sessions.add(uid)
        except OSError:
            continue
    return {"total": total, "turns": turns, "sessions": len(sessions)}


# ----------------------------------------------------------------- targets/pace

MILLION = 1_000_000


def target_for(day, config: dict, tool: str) -> int:
    """Daily token target for a tool, weekday vs weekend aware."""
    weekend = day.weekday() >= 5  # 5=Sat, 6=Sun
    key = "weekend" if weekend else "weekday"
    targets = config.get("targets", {})
    per_tool = targets.get(tool, targets.get("default", {}))
    millions = per_tool.get(key, 75 if weekend else 150)
    return int(millions * MILLION)


def _active_fraction(now: datetime, config: dict) -> float:
    """Fraction (0..1) of the active earning window elapsed by `now`.

    The window lives inside one local day (daily targets reset at local
    midnight, so late-night work counts toward the new day, not a wrapped
    window). '00:00'/'24:00' as the end means local midnight (end of day).
    Pace ramps from 0 at `start` to 1.0 at `end`.
    """
    win = config.get("active_window", {"start": "09:00", "end": "23:59"})
    sh, sm = (int(x) for x in win["start"].split(":"))
    eh, em = (int(x) for x in win["end"].split(":"))
    start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    if (eh, em) in ((0, 0), (24, 0)) or (eh, em) <= (sh, sm):
        # end at (or wrapping to) midnight -> clamp to end of this local day
        end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    else:
        end = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    if now <= start:
        return 0.0
    if now >= end:
        return 1.0
    return (now - start).total_seconds() / (end - start).total_seconds()


def pace(now: datetime, config: dict, actual: int, target: int) -> dict:
    """Pace assessment: expected-by-now, ahead/behind, percent, mood."""
    frac = _active_fraction(now, config)
    expected = int(target * frac)
    pct = (actual / target) if target else 1.0
    hit = actual >= target
    if hit:
        ratio = actual / target if target else 1.0
        mood = "rocket" if ratio >= 2 else "done"
    elif actual >= expected:
        mood = "ahead"
    elif actual >= expected * 0.6:
        mood = "ontrack"
    else:
        mood = "behind"
    return {
        "expected_by_now": expected,
        "remaining": max(0, target - actual),
        "deficit_vs_pace": max(0, expected - actual),
        "percent": round(pct * 100, 1),
        "active_fraction": round(frac, 3),
        "hit": hit,
        "mood": mood,
    }


def status(now: datetime | None = None, config: dict | None = None) -> dict:
    """Full status blob for both tools — the single source skins render from."""
    if now is None:
        now = datetime.now().astimezone()
    if config is None:
        config = load_config()
    boundary = config.get("day_boundary", "local")
    day = reference_day(now, boundary)
    out = {
        "generated_at": now.isoformat(),
        "day": day.isoformat(),
        "is_weekend": day.weekday() >= 5,
        "tools": {},
    }
    raw = {"claude": claude_today(day, boundary), "codex": codex_today(day, boundary)}
    for tool, data in raw.items():
        target = target_for(day, config, tool)
        p = pace(now, config, data["total"], target)
        out["tools"][tool] = {
            "today": data["total"],
            "target": target,
            "breakdown": data,
            **p,
        }
    combined_today = sum(t["today"] for t in out["tools"].values())
    combined_target = sum(t["target"] for t in out["tools"].values())
    out["combined"] = {
        "today": combined_today,
        "target": combined_target,
        "remaining": max(0, combined_target - combined_today),
        "percent": round((combined_today / combined_target * 100) if combined_target else 100.0, 1),
    }
    return out


DEFAULT_CONFIG = {
    "day_boundary": "local",
    "active_window": {"start": "09:00", "end": "23:59"},
    "targets": {
        "claude": {"weekday": 150, "weekend": 75},
        "codex": {"weekday": 150, "weekend": 75},
    },
    "checkpoints": ["15:00", "20:00", "23:00"],
    "telegram": {"enabled": True},
}


def load_config() -> dict:
    """Load config.json next to this module, falling back to DEFAULT_CONFIG."""
    path = Path(__file__).with_name("config.json")
    if path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
            merged = {**DEFAULT_CONFIG, **user}
            return merged
        except (ValueError, OSError):
            pass
    return dict(DEFAULT_CONFIG)


def humanize(n: int) -> str:
    """Compact token count: 1_234_567 -> '1.2M'."""
    if n >= MILLION:
        return f"{n / MILLION:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.0f}K"
    return str(n)
