"""TokenPulse terminal view — quick status without opening the widget.

  python3 cli.py            # human summary
  python3 cli.py --json     # raw status blob
  python3 cli.py --sessions # recent sessions to resume
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime

import core
import sessions

MOOD = {"behind": "😴", "ontrack": "🙂", "ahead": "🔥", "done": "✅", "rocket": "🚀"}
BAR_W = 24


def _bar(frac: float) -> str:
    fill = int(round(min(1.0, frac) * BAR_W))
    return "█" * fill + "░" * (BAR_W - fill)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sessions", action="store_true")
    args = ap.parse_args(argv)

    if args.sessions:
        for r in sessions.recent_sessions():
            snip = f"  — {r['snippet']}" if r["snippet"] else ""
            print(f"[{r['tool']:6}] {r['age']:>8}  {r['name']}{snip}")
        return 0

    st = core.status()
    if args.json:
        print(json.dumps(st, indent=2, default=str))
        return 0

    now = datetime.fromisoformat(st["generated_at"])
    kind = "weekend" if st["is_weekend"] else "weekday"
    print(f"⏱  TokenPulse · {now.strftime('%Y-%m-%d %H:%M')} · {kind}\n")
    for tool, label in (("claude", "Claude"), ("codex", "Codex ")):
        t = st["tools"][tool]
        frac = t["today"] / t["target"] if t["target"] else 1.0
        e = MOOD.get(t["mood"], "•")
        line = f"{label} {e} [{_bar(frac)}] {core.humanize(t['today'])}/{core.humanize(t['target'])}"
        if t["hit"]:
            line += f"  ({t['percent']:.0f}%) ✓"
        else:
            line += f"  need {core.humanize(t['remaining'])} · pace {core.humanize(t['expected_by_now'])}"
        print(line)
    c = st["combined"]
    print(f"\nΣ  {core.humanize(c['today'])}/{core.humanize(c['target'])}  ({c['percent']:.0f}%)  "
          f"remaining {core.humanize(c['remaining'])}")
    sug = sessions.suggestion()
    if sug and not all(t["hit"] for t in st["tools"].values()):
        print(f"\n▶  resume [{sug['tool']}] {sug['name']} · {sug['age']}")
        if sug.get("snippet"):
            print(f"   {sug['snippet']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
