"""Optional, local-only adapter for CodexBar's mature Codex JSONL scanner.

Recent Codex rollouts emit both ``last_token_usage`` and cumulative
``total_token_usage`` snapshots, including forked-agent lineages.  Summing the
former blindly can count one turn several times.  When CodexBar is installed,
reuse its local scanner so TokenPulse and the user's menu-bar ledger agree.

This module never reads credentials, never sends logs anywhere, and degrades
cleanly to TokenPulse's built-in parser when the executable is unavailable.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import datetime


_TTL_SECONDS = 60
_CACHE: dict[int, tuple[float, dict]] = {}
_LAST_TRUSTED: dict[int, dict] = {}


def _number(value) -> int | float:
    return value if isinstance(value, (int, float)) else 0


def _empty(reason: str) -> dict:
    return {"available": False, "reason": reason}


def _parse(payload, day) -> dict:
    """Normalize ``codexbar cost --format json`` without exposing raw logs."""
    root = payload[0] if isinstance(payload, list) and payload else payload
    if not isinstance(root, dict):
        return _empty("bad-output")
    daily = root.get("daily") if isinstance(root.get("daily"), list) else []
    row = next((item for item in daily if isinstance(item, dict) and item.get("date") == day.isoformat()), {})
    totals = root.get("totals") if isinstance(root.get("totals"), dict) else {}
    return {
        "available": True,
        "source": "codexbar",
        "tokens_today": int(_number(row.get("totalTokens"))),
        "tokens_30d": int(_number(totals.get("totalTokens"))),
        "cost_today": float(_number(row.get("totalCost"))),
        "cost_30d": float(_number(totals.get("totalCost"))),
        "cache_read_30d": int(_number(totals.get("cacheReadTokens"))),
        "input_30d": int(_number(totals.get("inputTokens"))),
        "output_30d": int(_number(totals.get("outputTokens"))),
    }


def usage(now: datetime | None = None, days: int = 1, ttl: int = _TTL_SECONDS) -> dict:
    """Return CodexBar's local cost usage, or an unavailable sentinel.

    CodexBar itself keeps the scan cache.  This tiny TTL only avoids spawning a
    process for each widget repaint; it does not persist data or contact a
    service.
    """
    now = now or datetime.now().astimezone()
    cached = _CACHE.get(days)
    if cached and (time.time() - cached[0]) < ttl:
        return cached[1]
    executable = shutil.which("codexbar")
    if not executable:
        parsed = _empty("not-installed")
    else:
        try:
            result = subprocess.run(
                [executable, "cost", "--provider", "codex", "--days", str(days), "--format", "json"],
                check=True,
                capture_output=True,
                text=True,
                timeout=60 if days > 1 else 20,
            )
            parsed = _parse(json.loads(result.stdout), now.date())
        except (OSError, ValueError, subprocess.SubprocessError):
            parsed = _empty("unavailable")
    if parsed.get("available"):
        _LAST_TRUSTED[days] = parsed
    elif days in _LAST_TRUSTED:
        # A transient local CLI failure must not make the widget fall back to
        # the obsolete raw-log sum. Keep the last scanner result and identify
        # it as stale so callers can remain truthful.
        parsed = {**_LAST_TRUSTED[days], "stale": True}
    _CACHE[days] = (time.time(), parsed)
    return parsed


def clear_cache() -> None:
    """Make the next read ask CodexBar for its latest local cached result."""
    _CACHE.clear()
