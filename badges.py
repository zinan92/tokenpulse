"""Badge / egg-tier system + shareable-card data.

Turns the 30-day usage history + cost into a gamified, brag-worthy state: an
"egg" tier that hatches/evolves with your monthly burn, a streak, and earned
milestone badges. `card_data()` is the single source both the widget panel and
the share-card renderer (card.py) read from.

Pure stdlib.
"""
from __future__ import annotations

from datetime import datetime

import cost
import history

MILLION = 1_000_000
BILLION = 1_000_000_000

# Egg ladder — hatches/evolves with this-month (rolling 30d) combined tokens.
EGG_TIERS = [  # (min_monthly_tokens, emoji, name)
    (25 * BILLION, "🐉", "Dragon"),
    (10 * BILLION, "🔥", "Inferno"),
    (5 * BILLION, "🦅", "Raptor"),
    (2 * BILLION, "🐥", "Fledgling"),
    (500 * MILLION, "🐣", "Hatchling"),
    (0, "🥚", "Egg"),
]
TOKEN_MILESTONES = [(100 * BILLION, "100B"), (50 * BILLION, "50B"),
                    (10 * BILLION, "10B"), (1 * BILLION, "1B")]
COST_MILESTONES = [(50000, "$50k"), (10000, "$10k"), (5000, "$5k"), (1000, "$1k")]
STREAK_MILESTONES = [(100, 100), (30, 30), (7, 7)]


def _tier(monthly_tokens: int) -> dict:
    for i, (thr, emoji, name) in enumerate(EGG_TIERS):
        if monthly_tokens >= thr:
            nxt = EGG_TIERS[i - 1] if i > 0 else None
            progress = None
            if nxt:
                span = nxt[0] - thr
                progress = round((monthly_tokens - thr) / span, 3) if span else 1.0
            return {
                "emoji": emoji, "name": name, "min": thr,
                "next": ({"emoji": nxt[1], "name": nxt[2], "at": nxt[0]} if nxt else None),
                "progress_to_next": progress,
            }
    return {"emoji": "🥚", "name": "Egg", "min": 0, "next": None, "progress_to_next": None}


def _best_streak(series: list, target: int) -> int:
    best = cur = 0
    for r in series:
        cur = cur + 1 if r["total"] >= target else 0
        best = max(best, cur)
    return best


def _highest(thresholds, value):
    """Highest (threshold, label) whose threshold <= value, else None."""
    for thr, label in thresholds:
        if value >= thr:
            return label
    return None


def card_data(now: datetime | None = None, config: dict | None = None) -> dict:
    """Everything the egg/badge UI and the share card render from."""
    p = history.panel_data(now=now, config=config)
    rec = history.lifetime_records(now=now, config=config)
    costs = {t: cost.usage_summary(t) for t in ("claude", "codex")}
    monthly_tokens = costs["claude"]["tokens_30d"] + costs["codex"]["tokens_30d"]
    monthly_cost = round(costs["claude"]["cost_30d"] + costs["codex"]["cost_30d"], 2)
    streak = p["streak"]
    best_streak = rec["best_streak"]          # all-time, from the persisted cache
    record_day = rec["record_day"]            # all-time single-day high

    # badge pool (the card prepends the current-streak chip and caps at 4)
    badges = []
    if best_streak >= 3 and best_streak > streak:  # only when it beats the current run
        badges.append({"icon": "🏆", "label": f"best {best_streak}d"})
    if record_day and record_day["total"] > 0:
        badges.append({"icon": "💥", "label": f"record {cost.humanize_tokens(record_day['total'])}"})
    cm = _highest(COST_MILESTONES, monthly_cost)
    if cm:
        badges.append({"icon": "💰", "label": f"{cm}/mo"})
    tm = _highest(TOKEN_MILESTONES, monthly_tokens)
    if tm:
        badges.append({"icon": "⚡", "label": f"{tm} tok/mo"})

    return {
        "tier": _tier(monthly_tokens),
        "monthly_tokens": monthly_tokens,
        "monthly_cost": monthly_cost,
        "streak": streak,
        "best_streak": best_streak,
        "record_day": record_day,
        "best_day": p.get("best"),          # 30-day best (for the panel)
        "days_tracked": rec["days_tracked"],
        "avg": p["avg"],
        "hit_days": p["hit_days"],
        "total_days": p["total_days"],
        "active_today": p.get("active_today"),
        "series": [r["total"] for r in p["series"]],
        "combined_target": p["combined_target"],
        "badges": badges,
        "per_tool": {t: {"tokens_30d": costs[t]["tokens_30d"],
                         "cost_30d": round(costs[t]["cost_30d"], 2)} for t in ("claude", "codex")},
    }


if __name__ == "__main__":
    import json
    d = card_data()
    t = d["tier"]
    print(f"{t['emoji']} {t['name']}  ({d['monthly_tokens']/1e9:.1f}B/mo, ${d['monthly_cost']:.0f})")
    print(f"streak {d['streak']} (best {d['best_streak']})  badges: {[b['label'] for b in d['badges']]}")
    if t["next"]:
        print(f"next: {t['next']['emoji']} {t['next']['name']} at {t['next']['at']/1e9:.0f}B "
              f"({d['tier']['progress_to_next']*100:.0f}% there)")
