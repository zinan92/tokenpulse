"""Real subscription plan limits for Claude and Codex.

The actual rate-limit windows (session/5h, weekly, opus) are NOT in the local
Claude transcripts — Anthropic only exposes them via an OAuth usage endpoint.
CodexBar already does that authentication + probing and writes the computed
results to disk, refreshed roughly hourly. We piggyback on that feed rather than
re-extracting OAuth tokens from the Keychain ourselves.

Source: ~/Library/Application Support/com.steipete.codexbar/history/{claude,codex}.json
Requires CodexBar to be installed and running (it keeps the files fresh).

Pure stdlib. Degrades gracefully when CodexBar is absent or its data is stale.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

HIST_DIR = os.path.expanduser(
    "~/Library/Application Support/com.steipete.codexbar/history"
)
PROVIDER_FILE = {"claude": "claude.json", "codex": "codex.json"}

# How old the newest sample may be before we flag the feed as stale (CodexBar
# samples ~hourly; older than this usually means the app isn't running).
STALE_AFTER_SECONDS = 3 * 3600

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
        windows.append({
            "name": w.get("name", "?"),
            "window_minutes": w.get("windowMinutes"),
            "used_percent": used,
            "left_percent": 100 - used,
            "resets_at": last.get("resets_at") or last.get("resetsAt"),
            "reset_in": reset_in(last.get("resets_at") or last.get("resetsAt"), now),
            "captured_at": captured,
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


def plan_limits(now: datetime | None = None) -> dict:
    """Real plan-limit state for both tools from the CodexBar feed."""
    now = now or datetime.now(timezone.utc)
    return {tool: _tool_limits(tool, now) for tool in PROVIDER_FILE}


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
