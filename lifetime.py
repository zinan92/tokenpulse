"""Lifetime monotonic usage accumulator — the never-resets trophy.

history.py's daily cache prunes at 120 days, so it cannot back a true "since day
one" total. This module keeps a SEPARATE store (.lifetime.json) that only ever
GROWS: a one-time full backfill from ALL local logs, then a cheap daily fold-in
of settled (pre-today) days. Today's live tokens are added at read time, so the
figure is current without ever double-counting.

The heavy backfill is gated behind `allow_backfill` so the UI never blocks on it
— the widget's warm thread does it once in the background; reads are always fast.

Pure stdlib.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta

import history
import peaks

LIFETIME_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".lifetime.json")
SCHEMA_VERSION = 2
BACKFILL_DAYS = 400  # wider than any plausible local-log retention


def _empty() -> dict:
    return {"version": SCHEMA_VERSION, "first_use_date": None, "counted_through": None,
            "total_tokens": 0, "days_active": 0, "by_tool": {"claude": 0, "codex": 0},
            "peak_day": None, "peak_session": None,
            "backfill_complete": False, "backfilled_at": None}


def _load() -> dict:
    try:
        d = json.load(open(LIFETIME_PATH, encoding="utf-8"))
    except (OSError, ValueError):
        return _empty()
    base = _empty()
    base.update(d)
    if not isinstance(base.get("by_tool"), dict):
        base["by_tool"] = {"claude": 0, "codex": 0}
    return base


def _save(d: dict) -> None:
    try:
        json.dump(d, open(LIFETIME_PATH, "w", encoding="utf-8"))
    except OSError:
        pass


def _fold_day(acc: dict, r: dict) -> None:
    """Fold one daily-series row {date,claude,codex,total} into acc (grow-only)."""
    acc["total_tokens"] += r["total"]
    acc["by_tool"]["claude"] += r["claude"]
    acc["by_tool"]["codex"] += r["codex"]
    if r["total"] > 0:
        acc["days_active"] += 1
        if acc["first_use_date"] is None or r["date"] < acc["first_use_date"]:
            acc["first_use_date"] = r["date"]
    if not acc["peak_day"] or r["total"] > acc["peak_day"]["total"]:
        acc["peak_day"] = {"date": r["date"], "total": r["total"]}


def _backfill(now: datetime) -> dict:
    """One-time FULL scan of all logs (no window). Heavy; runs exactly once."""
    today = now.astimezone().date()
    dt = history.daily_tokens(now, days=BACKFILL_DAYS, use_disk_cache=False)
    acc = _empty()
    for r in dt["series"]:
        if date.fromisoformat(r["date"]) >= today:
            continue  # today still accruing — counted live at read time
        _fold_day(acc, r)
    acc["counted_through"] = (today - timedelta(days=1)).isoformat()
    acc["peak_session"] = peaks.scan_session_peak()  # full one-time peak scan
    acc["backfill_complete"] = True
    acc["backfilled_at"] = now.astimezone().isoformat()
    return acc


def update(now: datetime | None = None, allow_backfill: bool = False,
           refresh_peak: bool = False) -> dict:
    """Keep the store current through yesterday. The one-time backfill only runs
    when allow_backfill=True (the warm thread); otherwise an un-backfilled store
    is returned as-is so reads never block on the full scan. refresh_peak (warm
    thread only) re-derives the peak-session via an idempotent max — full scan the
    first time (migrating a v1 store with no peak_session), recent files after."""
    now = now or datetime.now().astimezone()
    today = now.astimezone().date()
    d = _load()
    if not d.get("backfill_complete"):
        if not allow_backfill:
            return d  # pending — don't block the UI
        d = _backfill(now)
        _save(d)
        return d
    changed = False
    last = date.fromisoformat(d["counted_through"]) if d.get("counted_through") else None
    yesterday = today - timedelta(days=1)
    if not (last and last >= yesterday):
        gap = (yesterday - last).days if last else BACKFILL_DAYS
        dt = history.daily_tokens(now, days=min(BACKFILL_DAYS, gap + 2))
        for r in dt["series"]:
            rd = date.fromisoformat(r["date"])
            if (last and rd <= last) or rd >= today:
                continue
            _fold_day(d, r)
        d["counted_through"] = yesterday.isoformat()
        changed = True
    if refresh_peak:
        floor = 0.0 if d.get("peak_session") is None else history._floor_mtime(today - timedelta(days=2))
        newpeak = peaks.pick_larger(d.get("peak_session"), peaks.scan_session_peak(floor))
        if newpeak != d.get("peak_session"):
            d["peak_session"] = newpeak
            changed = True
    if changed:
        _save(d)
    return d


def summary(now: datetime | None = None, today_tokens: int = 0,
            today_claude: int = 0, today_codex: int = 0) -> dict:
    """Lifetime figures INCLUDING today's live tokens (never double-counted).
    Fast: never triggers the backfill (warm thread owns that)."""
    now = now or datetime.now().astimezone()
    today = now.astimezone().date()
    d = update(now, allow_backfill=False)
    total = d["total_tokens"] + max(0, today_tokens)
    cl = d["by_tool"]["claude"] + max(0, today_claude)
    cx = d["by_tool"]["codex"] + max(0, today_codex)
    days = d["days_active"] + (1 if today_tokens > 0 else 0)
    peak = d["peak_day"]
    if today_tokens > 0 and (not peak or today_tokens > peak["total"]):
        peak = {"date": today.isoformat(), "total": today_tokens}
    return {"lifetime_tokens": total, "by_tool": {"claude": cl, "codex": cx},
            "days_active": days, "first_use_date": d["first_use_date"],
            "peak_day": peak, "peak_session": d.get("peak_session"),
            "pending": not d.get("backfill_complete", False)}


def ensure_backfill(now: datetime | None = None) -> dict:
    """Warm-thread entry point: do the heavy one-time scan + keep current."""
    return update(now, allow_backfill=True, refresh_peak=True)


if __name__ == "__main__":
    import json as _j
    s = summary()
    print("backfill pending:", s["pending"])
    if s["pending"]:
        print("running backfill (full log scan)...")
        ensure_backfill()
        s = summary()
    print(_j.dumps(s, indent=2, default=str))
