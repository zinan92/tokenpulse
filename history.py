"""30-day usage history + daily active time, for the expand panel.

  - daily_tokens()         : per-day token totals (Claude/Codex/combined) for the
                             last N days → the month bar chart.
  - active_minutes_today() : today's active engagement time per tool, from the
                             merged timeline of session timestamps (sum of gaps
                             ≤ idle threshold). A proxy for "how long I used it",
                             not app wall-clock (we have no app-focus signal).
  - streak_and_best()      : days-hit-target streak + best day, from a daily series.

Heavy 30-day scans are TTL-cached. Pure stdlib.
"""
from __future__ import annotations

import glob
import json
import os
import time
from datetime import datetime, timedelta

import core

_CACHE: dict = {}
DEFAULT_TTL = 600
IDLE_GAP_MIN = 10  # gaps longer than this don't count as continuous active time


def _local_date(ts):
    dt = core._parse_ts(ts)
    return dt.astimezone().date() if dt else None


def _window(now: datetime, days: int):
    today = now.astimezone().date()
    start = today - timedelta(days=days - 1)
    floor_mtime = (datetime.combine(start, datetime.min.time()).astimezone()
                   - timedelta(days=1)).timestamp()
    return today, start, floor_mtime


# ------------------------------------------------------------- per-day tokens

def _claude_daily(start, floor_mtime) -> dict:
    seen: set = set()
    by_day: dict = {}
    for f in glob.glob(core.CLAUDE_GLOB, recursive=True):
        try:
            if os.path.getmtime(f) < floor_mtime:
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
                    msg = d.get("message")
                    if not isinstance(msg, dict):
                        continue
                    u = msg.get("usage")
                    if not isinstance(u, dict):
                        continue
                    mid = msg.get("id")
                    key = (mid, d.get("requestId"))
                    if mid and key in seen:
                        continue
                    if mid:
                        seen.add(key)
                    ld = _local_date(d.get("timestamp"))
                    if ld is None or ld < start:
                        continue
                    toks = ((u.get("input_tokens", 0) or 0)
                            + (u.get("cache_creation_input_tokens", 0) or 0)
                            + (u.get("cache_read_input_tokens", 0) or 0)
                            + (u.get("output_tokens", 0) or 0))
                    by_day[ld] = by_day.get(ld, 0) + toks
        except OSError:
            continue
    return by_day


def _codex_daily(start, floor_mtime) -> dict:
    chosen: dict = {}
    mtimes: dict = {}
    for pat in core.CODEX_GLOBS:
        for f in glob.glob(pat, recursive=True):
            try:
                m = os.path.getmtime(f)
            except OSError:
                continue
            if m < floor_mtime:
                continue
            uid = core._codex_session_uuid(f)
            if uid not in mtimes or m > mtimes[uid]:
                mtimes[uid], chosen[uid] = m, f
    by_day: dict = {}
    for f in chosen.values():
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    info = (d.get("payload") or {}).get("info") if isinstance(d.get("payload"), dict) else None
                    if not isinstance(info, dict):
                        continue
                    lt = info.get("last_token_usage")
                    if not isinstance(lt, dict):
                        continue
                    ld = _local_date(d.get("timestamp"))
                    if ld is None or ld < start:
                        continue
                    by_day[ld] = by_day.get(ld, 0) + (lt.get("total_tokens", 0) or 0)
        except OSError:
            continue
    return by_day


CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".history-cache.json")
PRUNE_DAYS = 120


def _floor_mtime(day):
    return (datetime.combine(day, datetime.min.time()).astimezone() - timedelta(days=1)).timestamp()


def _load_disk() -> dict:
    try:
        d = json.load(open(CACHE_PATH, encoding="utf-8"))
        return {"claude": d.get("claude", {}), "codex": d.get("codex", {})}
    except (OSError, ValueError):
        return {"claude": {}, "codex": {}}


def _save_disk(cache: dict, today):
    keep = (today - timedelta(days=PRUNE_DAYS)).isoformat()
    pruned = {tool: {d: v for d, v in cache[tool].items() if d >= keep} for tool in ("claude", "codex")}
    try:
        json.dump(pruned, open(CACHE_PATH, "w", encoding="utf-8"))
    except OSError:
        pass


def daily_tokens(now: datetime | None = None, days: int = 30, use_disk_cache: bool = True) -> dict:
    """Per-day token totals for the last `days` days (oldest → newest).

    Past days are immutable, so we persist them and only re-scan today + yesterday
    (cheap) on each call — turning a ~45s full scan into a couple seconds after
    the one-time backfill.
    """
    now = now or datetime.now().astimezone()
    today, start, _ = _window(now, days)
    window = [start + timedelta(days=i) for i in range(days)]

    if not use_disk_cache:
        cl = _claude_daily(start, _floor_mtime(start))
        cx = _codex_daily(start, _floor_mtime(start))
        cl = {d.isoformat(): v for d, v in cl.items()}
        cx = {d.isoformat(): v for d, v in cx.items()}
    else:
        cache = _load_disk()
        cl, cx = cache["claude"], cache["codex"]
        recompute_from = today - timedelta(days=1)  # today + yesterday may still accrue
        older = [d for d in window if d < recompute_from]
        missing = any(d.isoformat() not in cl and d.isoformat() not in cx for d in older)
        backfill_from = start if missing else recompute_from
        new_cl = _claude_daily(backfill_from, _floor_mtime(backfill_from))
        new_cx = _codex_daily(backfill_from, _floor_mtime(backfill_from))
        for d in window:
            if d >= backfill_from:
                cl[d.isoformat()] = new_cl.get(d, 0)
                cx[d.isoformat()] = new_cx.get(d, 0)
        _save_disk({"claude": cl, "codex": cx}, today)

    series = []
    for d in window:
        iso = d.isoformat()
        c, x = cl.get(iso, 0), cx.get(iso, 0)
        series.append({"date": iso, "claude": c, "codex": x, "total": c + x})
    return {"days": days, "series": series}


# ----------------------------------------------------------- active minutes

def _claude_timestamps_today(today) -> list:
    floor = (datetime.combine(today, datetime.min.time()).astimezone() - timedelta(days=1)).timestamp()
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
                    i = line.find('"timestamp"')
                    if i < 0:
                        continue
                    try:
                        d = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    dt = core._parse_ts(d.get("timestamp"))
                    if dt and dt.astimezone().date() == today:
                        out.append(dt.timestamp())
        except OSError:
            continue
    return out


def _codex_timestamps_today(today) -> list:
    floor = (datetime.combine(today, datetime.min.time()).astimezone() - timedelta(days=1)).timestamp()
    seen_uid: set = set()
    out = []
    for pat in core.CODEX_GLOBS:
        for f in glob.glob(pat, recursive=True):
            try:
                if os.path.getmtime(f) < floor:
                    continue
            except OSError:
                continue
            uid = core._codex_session_uuid(f)
            if uid in seen_uid:
                continue
            seen_uid.add(uid)
            try:
                with open(f, encoding="utf-8") as fh:
                    for line in fh:
                        i = line.find('"timestamp"')
                        if i < 0:
                            continue
                        try:
                            d = json.loads(line)
                        except (ValueError, TypeError):
                            continue
                        dt = core._parse_ts(d.get("timestamp"))
                        if dt and dt.astimezone().date() == today:
                            out.append(dt.timestamp())
            except OSError:
                continue
    return out


def _active_minutes(timestamps: list, idle_gap_min: int = IDLE_GAP_MIN) -> int:
    if len(timestamps) < 2:
        return 0
    ts = sorted(timestamps)
    gap_cap = idle_gap_min * 60
    total = 0.0
    for a, b in zip(ts, ts[1:]):
        gap = b - a
        if 0 < gap <= gap_cap:
            total += gap
    return int(round(total / 60))


def active_minutes_today(now: datetime | None = None) -> dict:
    now = now or datetime.now().astimezone()
    today = now.astimezone().date()
    return {
        "claude": _active_minutes(_claude_timestamps_today(today)),
        "codex": _active_minutes(_codex_timestamps_today(today)),
    }


# ----------------------------------------------------------- streak / best

def streak_and_best(series: list, target: int) -> dict:
    """Current trailing run of days that hit `target`, plus the best day."""
    best = max(series, key=lambda r: r["total"], default=None)
    streak = 0
    for r in reversed(series):
        if r["total"] >= target:
            streak += 1
        else:
            break
    hit_days = sum(1 for r in series if r["total"] >= target)
    avg = round(sum(r["total"] for r in series) / len(series)) if series else 0
    return {
        "streak": streak,
        "hit_days": hit_days,
        "total_days": len(series),
        "avg": avg,
        "best": {"date": best["date"], "total": best["total"]} if best else None,
    }


def panel_data(now: datetime | None = None, config: dict | None = None,
               days: int = 30, ttl: int = DEFAULT_TTL) -> dict:
    """Everything the expand panel needs (TTL-cached — the 30-day scan is heavy)."""
    now = now or datetime.now().astimezone()
    config = config or core.load_config()
    hit = _CACHE.get("panel")
    if hit and (time.time() - hit[0]) < ttl:
        return hit[1]
    dt = daily_tokens(now, days)
    target = (core.target_for(now.date(), config, "claude")
              + core.target_for(now.date(), config, "codex"))
    val = {
        "series": dt["series"],
        "days": days,
        "combined_target": target,
        "active_today": active_minutes_today(now),
        **streak_and_best(dt["series"], target),
    }
    _CACHE["panel"] = (time.time(), val)
    return val


if __name__ == "__main__":
    import json as _j
    print(_j.dumps(panel_data(), indent=2, default=str))
