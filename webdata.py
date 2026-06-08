"""Data bridge for the web goad-widget.

Merges three sources into one payload the UI renders from:
  - core.status()        → today's tokens vs target + pace + mood (THE GOAD signal)
  - limits.plan_limits() → session / weekly % left + reset (CodexBar feed)
  - cost.usage_summary() → today/30d cost, 30d/today tokens (models.dev rates)

Split into a fast core() (goal+limits, renders the emotional state instantly) and
a slow cost() (30-day scan, TTL-cached) so the widget never blocks on cost.

Pure stdlib.
"""
from __future__ import annotations

from datetime import datetime

import core
import cost
import limits

TOOLS = ("claude", "codex")


def _state(mood: str) -> str:
    """Map core's mood to a UI state name."""
    return {"behind": "behind", "ontrack": "ontrack", "ahead": "ahead",
            "done": "hit", "rocket": "rocket"}.get(mood, "ontrack")


def core_payload(now: datetime | None = None, config: dict | None = None) -> dict:
    now = now or datetime.now().astimezone()
    config = config or core.load_config()
    st = core.status(now=now, config=config)
    pl = limits.plan_limits()

    tools = {}
    for t in TOOLS:
        d = st["tools"][t]
        info = pl.get(t, {})
        sess = limits.window(info, "session") if info.get("available") else None
        week = limits.window(info, "weekly") if info.get("available") else None
        tools[t] = {
            "today": d["today"],
            "target": d["target"],
            "percent": d["percent"],
            "expected": d["expected_by_now"],
            "deficit": d["deficit_vs_pace"],
            "remaining": d["remaining"],
            "active_fraction": d["active_fraction"],
            "hit": d["hit"],
            "state": _state(d["mood"]),
            "pace_ratio": round(d["today"] / d["expected_by_now"], 2) if d["expected_by_now"] else None,
            "session": {"left": sess["left_percent"], "reset": sess["reset_in"]} if sess else None,
            "weekly": {"left": week["left_percent"], "reset": week["reset_in"]} if week else None,
            "plan_available": bool(info.get("available")),
            "plan_stale": bool(info.get("stale")),
        }

    c = st["combined"]
    expected = sum(t["expected"] for t in tools.values())
    p = core.pace(now, config, c["today"], c["target"])
    out = {
        "generated_at": now.isoformat(),
        "clock": now.strftime("%H:%M"),
        "active_fraction": round(core._active_fraction(now, config), 3),
        "combined": {
            "today": c["today"],
            "target": c["target"],
            "percent": c["percent"],
            "remaining": c["remaining"],
            "expected": expected,
            "deficit": max(0, expected - c["today"]),
            "state": _state(p["mood"]),
            "hit": p["hit"],
            "pace_ratio": round(c["today"] / expected, 2) if expected else None,
        },
        "tools": tools,
    }
    return out


def cost_payload() -> dict:
    out = {}
    for t in TOOLS:
        s = cost.usage_summary(t)
        out[t] = {
            "cost_today": round(s["cost_today"], 2),
            "cost_30d": round(s["cost_30d"], 2),
            "tokens_30d": s["tokens_30d"],
            "tokens_today": s["tokens_today"],
        }
    return out


if __name__ == "__main__":
    import json
    print(json.dumps({"core": core_payload(), "cost": cost_payload()}, indent=2, default=str))
