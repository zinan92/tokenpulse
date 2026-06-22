"""continuity.py — longest continuous dev stretch (never-resets trophy).

The single longest unbroken run of activity across BOTH tools, measured over the
globally-merged, sorted timestamp stream (every JSONL line is an activity tick).
A stretch spanning midnight / multiple days is exactly what we want, so this is
never computed per-day. Mirrors lifetime.py: one-time gated full backfill + cheap
daily fold of settled days; today's live timestamps are folded at read time on a
COPY so an ongoing marathon shows current without ever double-counting the store.

Persisting run_start/last_ts as ISO VALUES (not log references) makes it pruning-
safe — the open run resumes even after its starting log is archived. Pure stdlib.
"""
from __future__ import annotations

import glob
import json
import os
from datetime import date, datetime, time, timedelta

import core

STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".continuity.json")
SCHEMA_VERSION = 1
GAP_MINUTES = 30  # idle gap that breaks a stretch (> history.IDLE_GAP_MIN so a short pause holds)
BACKFILL_DAYS = 400


def _empty() -> dict:
    return {"version": SCHEMA_VERSION, "gap_minutes": GAP_MINUTES,
            "longest_seconds": 0, "longest_start": None, "longest_end": None,
            "run_start": None, "last_ts": None,
            "scanned_through": None, "backfill_complete": False, "backfilled_at": None}


def _load() -> dict:
    try:
        d = json.load(open(STORE, encoding="utf-8"))
    except (OSError, ValueError):
        return _empty()
    base = _empty()
    base.update(d)
    return base


def _save(d: dict) -> None:
    try:
        json.dump(d, open(STORE, "w", encoding="utf-8"))
    except OSError:
        pass


def _floor_mtime(day) -> float:
    return (datetime.combine(day, time.min).astimezone() - timedelta(days=1)).timestamp()


def _claude_timestamps(since_day) -> list:
    floor = _floor_mtime(since_day)
    out = []
    for f in glob.glob(core.CLAUDE_GLOB, recursive=True):
        try:
            if os.path.getmtime(f) < floor:
                continue
        except OSError:
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    if line.find('"timestamp"') < 0:
                        continue
                    try:
                        d = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    dt = core._parse_ts(d.get("timestamp"))
                    if dt and dt.astimezone().date() >= since_day:
                        out.append(dt.timestamp())
        except OSError:
            continue
    return out


def _codex_timestamps(since_day) -> list:
    floor = _floor_mtime(since_day)
    seen: set = set()
    out = []
    for pat in core.CODEX_GLOBS:
        for f in glob.glob(pat, recursive=True):
            try:
                if os.path.getmtime(f) < floor:
                    continue
            except OSError:
                continue
            uid = core._codex_session_uuid(f)
            if uid in seen:
                continue
            seen.add(uid)
            try:
                with open(f, encoding="utf-8") as fh:
                    for line in fh:
                        if line.find('"timestamp"') < 0:
                            continue
                        try:
                            d = json.loads(line)
                        except (ValueError, TypeError):
                            continue
                        dt = core._parse_ts(d.get("timestamp"))
                        if dt and dt.astimezone().date() >= since_day:
                            out.append(dt.timestamp())
            except OSError:
                continue
    return out


def _merged(since_day) -> list:
    return sorted(_claude_timestamps(since_day) + _codex_timestamps(since_day))


def _fold(state: dict, timestamps: list, upto: float | None = None) -> dict:
    """Streaming max-gap-bounded span. Returns a NEW state (never mutates input)."""
    s = dict(state)
    gap_cap = s["gap_minutes"] * 60
    last = datetime.fromisoformat(s["last_ts"]).timestamp() if s["last_ts"] else None
    run = datetime.fromisoformat(s["run_start"]).timestamp() if s["run_start"] else None
    for ts in timestamps:
        if upto is not None and ts >= upto:
            break  # stop before 'today' for the settled fold
        if last is not None and ts <= last:
            continue  # strictly-greater: don't reprocess boundary lines
        if last is None or ts - last > gap_cap:
            run = ts
        span = ts - run
        if span > s["longest_seconds"]:
            s["longest_seconds"] = int(span)
            s["longest_start"] = datetime.fromtimestamp(run).astimezone().isoformat()
            s["longest_end"] = datetime.fromtimestamp(ts).astimezone().isoformat()
        last = ts
    if last is not None:
        s["run_start"] = datetime.fromtimestamp(run).astimezone().isoformat()
        s["last_ts"] = datetime.fromtimestamp(last).astimezone().isoformat()
    return s


def _today_floor(today) -> float:
    return datetime.combine(today, time.min).astimezone().timestamp()


def _backfill(now: datetime) -> dict:
    today = now.astimezone().date()
    s = _fold(_empty(), _merged(today - timedelta(days=BACKFILL_DAYS)), upto=_today_floor(today))
    s["scanned_through"] = (today - timedelta(days=1)).isoformat()
    s["backfill_complete"] = True
    s["backfilled_at"] = now.astimezone().isoformat()
    return s


def update(now: datetime | None = None, allow_backfill: bool = False) -> dict:
    now = now or datetime.now().astimezone()
    today = now.astimezone().date()
    d = _load()
    if not d.get("backfill_complete"):
        if not allow_backfill:
            return d  # don't block the UI
        d = _backfill(now)
        _save(d)
        return d
    last = date.fromisoformat(d["scanned_through"]) if d.get("scanned_through") else None
    yesterday = today - timedelta(days=1)
    if last and last >= yesterday:
        return d  # already current
    since = (last + timedelta(days=1)) if last else (today - timedelta(days=BACKFILL_DAYS))
    d = _fold(d, _merged(since), upto=_today_floor(today))
    d["scanned_through"] = yesterday.isoformat()
    _save(d)
    return d


def summary(now: datetime | None = None) -> dict:
    """All-time record INCLUDING an in-progress run today (folded on a copy)."""
    now = now or datetime.now().astimezone()
    today = now.astimezone().date()
    d = update(now, allow_backfill=False)
    live = _fold(d, _merged(today))  # copy + today's events; may extend the record
    return {"longest_hours": round(live["longest_seconds"] / 3600, 2),
            "longest_seconds": live["longest_seconds"],
            "longest_start": live["longest_start"], "longest_end": live["longest_end"],
            "gap_minutes": d["gap_minutes"],
            "pending": not d.get("backfill_complete", False)}


def ensure_backfill(now: datetime | None = None) -> dict:
    return update(now, allow_backfill=True)  # warm-thread entry point


if __name__ == "__main__":
    import json as _j
    s = summary()
    if s["pending"]:
        ensure_backfill()
        s = summary()
    print(_j.dumps(s, indent=2, default=str))
