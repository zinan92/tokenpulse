"""Share-moments — detect the proud crossings (tier-up, new single-day record,
new lifetime milestone) so the widget can nudge a share at the exact instant it
happens. State persists in .moments.json; the FIRST run only snapshots (never
fires spurious "you just hit X" events on launch). Pure stdlib.
"""
from __future__ import annotations

import json
import os

import badges

STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".moments.json")

LIFE_MILESTONES = [1_000_000_000, 10_000_000_000, 100_000_000_000, 1_000_000_000_000]
LIFE_LABEL = {1_000_000_000: "十亿", 10_000_000_000: "百亿",
              100_000_000_000: "千亿", 1_000_000_000_000: "万亿"}


def _tier_rank(name: str) -> int:
    """SAGA_TIERS is descending (如来=0 … 石猴=last), so a SMALLER index = higher."""
    for i, t in enumerate(badges.SAGA_TIERS):
        if t[2] == name:
            return i
    return 99


def _highest_milestone(tokens: int) -> int:
    hit = 0
    for m in LIFE_MILESTONES:
        if tokens >= m:
            hit = m
    return hit


def _load() -> dict:
    try:
        return json.load(open(STORE, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(d: dict) -> None:
    try:
        json.dump(d, open(STORE, "w", encoding="utf-8"))
    except OSError:
        pass


def check(data: dict | None = None) -> list[dict]:
    """Return the NEW proud events since the last check, and advance the snapshot.
    Idempotent: a crossing fires once, then the snapshot moves past it."""
    data = data or badges.card_data()
    cur = {
        "tier": data["tier"]["name"],
        "record": int((data.get("record_day") or {}).get("total", 0) or 0),
        "life_ms": _highest_milestone(int((data.get("lifetime") or {}).get("lifetime_tokens", 0) or 0)),
    }
    prev = _load()
    events: list[dict] = []
    if prev:  # never fire on the very first run
        if cur["tier"] != prev.get("tier") and _tier_rank(cur["tier"]) < _tier_rank(prev.get("tier", "")):
            events.append({"kind": "tier", "title": f"升上 {cur['tier']}"})
        if cur["record"] > prev.get("record", 0) > 0:
            events.append({"kind": "record", "title": f"刷新单日纪录 {badges._tok(cur['record'])}"})
        if cur["life_ms"] > prev.get("life_ms", 0):
            events.append({"kind": "lifetime", "title": f"生涯破 {LIFE_LABEL.get(cur['life_ms'], '')}"})
    _save(cur)
    return events


if __name__ == "__main__":
    print(check())
