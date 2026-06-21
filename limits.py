"""Real subscription plan limits for Claude and Codex.

- CODEX session/weekly %: read DIRECTLY from local `~/.codex` session logs
  (`payload.rate_limits`) — no CodexBar needed.
- CLAUDE session/weekly/opus %: NOT in any local Claude file — Anthropic exposes
  them only via an OAuth usage endpoint with a token that needs refreshing.
  CodexBar already does that safely, so we read its on-disk feed WHEN PRESENT.
  CodexBar is OPTIONAL: absent → Claude windows show unavailable, everything
  else (Codex limits, tokens, cost) still works.

Pure stdlib. Degrades gracefully.
"""
from __future__ import annotations

import glob
import json
import os
from datetime import datetime, timezone

import core  # CODEX_GLOBS, _codex_session_uuid

HIST_DIR = os.path.expanduser(
    "~/Library/Application Support/com.steipete.codexbar/history"
)
PROVIDER_FILE = {"claude": "claude.json", "codex": "codex.json"}

# How old the newest sample may be before we flag the feed as stale (CodexBar
# samples ~hourly; older than this usually means the app isn't running).
STALE_AFTER_SECONDS = 6 * 3600  # CodexBar samples irregularly (idle/sleep gaps)

# Pace only applies to weekly-scale windows; a 5h session burst limit isn't
# something you pace-fill over time.
PACE_MIN_WINDOW_MINUTES = 1440  # 1 day

# Preferred display order; unknown window names sort after these.
WINDOW_ORDER = {"session": 0, "weekly": 1, "opus": 2, "sonnet": 3}


def _parse(ts: str | None) -> datetime | None:
    if not ts or not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def reset_in(resets_at: str | None, now: datetime | None = None) -> str:
    """Human countdown to a reset timestamp, e.g. '6d2h', '4h56m', '12m', 'due'."""
    now = now or datetime.now(timezone.utc)
    rt = _parse(resets_at)
    if rt is None:
        return ""
    secs = (rt - now).total_seconds()
    if secs <= 0:
        return "due"
    d, rem = divmod(int(secs), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d{h}h"
    if h:
        return f"{h}h{m}m"
    return f"{m}m"


def window_pace(window_minutes, resets_at: str | None, used_percent,
                now: datetime | None = None) -> dict | None:
    """Utilization pace for a quota window, for the "use it all" goal.

    A window of length `window_minutes` ends at `resets_at`; by the fraction of
    it elapsed you'd need to have used that same fraction to fully consume the
    allowance before it resets. Returns elapsed %, the used % you'd expect by
    now, and how many points you're *behind* (unused headroom you're on track
    to waste). None when inputs are insufficient.

    Only meaningful for long (weekly-scale) windows — a 5h session window is a
    burst limit you don't pace-fill, so we skip windows shorter than a day.
    """
    if not window_minutes or resets_at is None or used_percent is None:
        return None
    if window_minutes < PACE_MIN_WINDOW_MINUTES:
        return None
    now = now or datetime.now(timezone.utc)
    end = _parse(resets_at)
    if end is None:
        return None
    total = window_minutes * 60.0
    remaining = (end - now).total_seconds()
    elapsed = max(0.0, min(1.0, 1 - remaining / total))
    expected = round(elapsed * 100, 1)
    behind_by = round(max(0.0, expected - used_percent), 1)
    return {
        "elapsed_percent": expected,          # == expected used% to finish flat
        "expected_used_percent": expected,
        "behind_by": behind_by,               # points of allowance you're trailing
        "on_pace": used_percent >= expected,
    }


def _select_account(data: dict) -> list | None:
    accounts = data.get("accounts")
    if not isinstance(accounts, dict) or not accounts:
        return None
    pref = data.get("preferredAccountKey")
    if pref and pref in accounts:
        return accounts[pref]
    # else the account with the most recent activity
    best = None
    best_ts = ""
    for windows in accounts.values():
        for w in windows if isinstance(windows, list) else []:
            ents = w.get("entries") or []
            if ents:
                ts = ents[-1].get("capturedAt", "")
                if ts > best_ts:
                    best_ts, best = ts, windows
    return best


def _tool_limits(tool: str, now: datetime) -> dict:
    path = os.path.join(HIST_DIR, PROVIDER_FILE[tool])
    if not os.path.exists(path):
        return {"available": False, "reason": "codexbar-not-found", "windows": []}
    try:
        data = json.load(open(path, encoding="utf-8"))
    except (ValueError, OSError):
        return {"available": False, "reason": "unreadable", "windows": []}

    windows_raw = _select_account(data)
    if not windows_raw:
        return {"available": False, "reason": "no-account", "windows": []}

    windows = []
    newest = None
    for w in windows_raw:
        ents = w.get("entries") or []
        if not ents:
            continue
        last = ents[-1]
        used = last.get("usedPercent")
        if used is None:
            continue
        captured = last.get("capturedAt")
        ct = _parse(captured)
        if ct and (newest is None or ct > newest):
            newest = ct
        ra = last.get("resets_at") or last.get("resetsAt")
        wm = w.get("windowMinutes")
        windows.append({
            "name": w.get("name", "?"),
            "window_minutes": wm,
            "used_percent": used,
            "left_percent": 100 - used,
            "resets_at": ra,
            "reset_in": reset_in(ra, now),
            "captured_at": captured,
            "pace": window_pace(wm, ra, used, now),
        })
    windows.sort(key=lambda x: WINDOW_ORDER.get(x["name"], 99))

    stale = True
    age = None
    if newest is not None:
        age = (now - newest).total_seconds()
        stale = age > STALE_AFTER_SECONDS
    return {
        "available": bool(windows),
        "stale": stale,
        "sample_age_seconds": int(age) if age is not None else None,
        "sampled_at": newest.isoformat() if newest else None,
        "windows": windows,
    }


def _codex_local_limits(now: datetime) -> dict:
    """Codex session(5h)/weekly(7d) % straight from local ~/.codex session logs
    (`payload.rate_limits`) — no CodexBar dependency."""
    paths = []
    for pat in core.CODEX_GLOBS:
        paths.extend(glob.glob(pat, recursive=True))
    paths.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)

    rl = None
    rl_ts = None
    for f in paths[:8]:  # most-recently-active sessions carry the freshest limits
        try:
            for line in open(f, encoding="utf-8"):
                if '"rate_limits"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except (ValueError, TypeError):
                    continue
                p = d.get("payload")
                if isinstance(p, dict) and isinstance(p.get("rate_limits"), dict):
                    rl, rl_ts = p["rate_limits"], d.get("timestamp")
        except OSError:
            continue
        if rl:
            break
    if not rl:
        return {"available": False, "reason": "no-codex-rate-limits", "windows": []}

    windows = []
    for key, name in (("primary", "session"), ("secondary", "weekly")):
        w = rl.get(key)
        if not isinstance(w, dict) or w.get("used_percent") is None:
            continue
        used = w["used_percent"]
        wm = w.get("window_minutes")
        epoch = w.get("resets_at")
        ra = (datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
              if isinstance(epoch, (int, float)) else None)
        windows.append({
            "name": name,
            "window_minutes": wm,
            "used_percent": used,
            "left_percent": 100 - used,
            "resets_at": ra,
            "reset_in": reset_in(ra, now),
            "captured_at": rl_ts,
            "pace": window_pace(wm, ra, used, now),
        })
    windows.sort(key=lambda x: WINDOW_ORDER.get(x["name"], 99))

    newest = _parse(rl_ts)
    age = (now - newest).total_seconds() if newest else None
    return {
        "available": bool(windows),
        "stale": bool(age is not None and age > STALE_AFTER_SECONDS),
        "sample_age_seconds": int(age) if age is not None else None,
        "sampled_at": rl_ts,
        "windows": windows,
        "plan_type": rl.get("plan_type"),
    }


def plan_limits(now: datetime | None = None) -> dict:
    """Plan-limit state per tool. Codex is local; Claude uses CodexBar if present."""
    now = now or datetime.now(timezone.utc)
    return {
        "claude": _tool_limits("claude", now),     # CodexBar feed (optional)
        "codex": _codex_local_limits(now),          # local ~/.codex, no CodexBar
    }


def window(limits_for_tool: dict, name: str) -> dict | None:
    """Convenience: pull a named window (e.g. 'weekly') from a tool's limits."""
    for w in limits_for_tool.get("windows", []):
        if w["name"] == name:
            return w
    return None


if __name__ == "__main__":
    pl = plan_limits()
    for tool, info in pl.items():
        if not info["available"]:
            print(f"{tool}: unavailable ({info.get('reason')})")
            continue
        flag = " (STALE)" if info["stale"] else ""
        print(f"{tool}{flag}  sampled {info['sampled_at']}")
        for w in info["windows"]:
            wm = w["window_minutes"]
            win = f"{wm // 60}h" if wm and wm < 1440 else (f"{wm // 1440}d" if wm else "?")
            print(f"   {w['name']:8} {win:4} {w['left_percent']:3}% left  "
                  f"(used {w['used_percent']}%)  resets in {w['reset_in']}")
