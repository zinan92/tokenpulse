"""TokenPulse terminal view — quick status without opening the widget.

  python3 cli.py            # human summary
  python3 cli.py --json     # status blob plus operator/impact summaries
  python3 cli.py --sessions # recent sessions to resume
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime

import core
import limits
import sessions

MOOD = {"behind": "😴", "ontrack": "🙂", "ahead": "🔥", "done": "✅", "rocket": "🚀"}
BAR_W = 24
SESSION_FRAME = (
    "Sessions: before raw Claude/Codex logs, after a resume shortlist for choosing "
    "the next AI-work session."
)
SESSION_EMPTY = (
    "Sessions: no recent Claude/Codex sessions found; nothing to resume from the "
    "last 5 days, so choose by priority."
)


def _bar(frac: float) -> str:
    fill = int(round(min(1.0, frac) * BAR_W))
    return "█" * fill + "░" * (BAR_W - fill)


def _win_label(wm) -> str:
    if not wm:
        return "?"
    return f"{wm // 60}h" if wm < 1440 else f"{wm // 1440}d"


def _print_limits(info: dict):
    if not info.get("available"):
        print(f"      plan: (CodexBar 未运行/无数据 — {info.get('reason', '?')})")
        return
    stale = " ⚠stale" if info.get("stale") else ""
    parts = []
    for w in info["windows"]:
        rin = f" {w['reset_in']}" if w["reset_in"] else ""
        seg = f"{w['name']} {w['left_percent']}%left{rin}"
        p = w.get("pace")
        if p and not p["on_pace"] and p["behind_by"] >= 5:
            seg += f" ⚠落后{p['behind_by']:.0f}%"
        parts.append(seg)
    print(f"      plan{stale}: " + "  ·  ".join(parts))


def _operator_summary(st: dict) -> str:
    tools = list(st["tools"].values())
    remaining = core.humanize(st["combined"]["remaining"])
    if all(t["hit"] for t in tools):
        return "Operator: complete - daily target is done; choose the next AI-work session by priority, not quota pressure."
    if any(t["mood"] == "behind" for t in tools):
        return f"Operator: behind - choose the next AI-work session now to catch up; {remaining} tokens remain today."
    return f"Operator: on track - keep the next AI-work session aligned to priority; {remaining} tokens remain today."


def _impact_summary(st: dict) -> str:
    tools = list(st["tools"].values())
    if all(t["hit"] for t in tools):
        return "Impact: raw quota and pace become a next-session choice: priority decides because today's token target is done."
    if any(t["mood"] == "behind" for t in tools):
        return "Impact: raw quota and pace become a next-session choice: start now to turn lag into useful AI-work."
    return "Impact: raw quota and pace become a next-session choice: stay on the priority session while runway is healthy."


def _product_impact(st: dict) -> dict:
    tools = list(st["tools"].values())
    if all(t["hit"] for t in tools):
        return {
            "before": "Quota completion was visible, but the next operating move still had to be inferred from counters.",
            "after": "TokenPulse states the daily target is complete and priority should choose the next AI-work session.",
            "user_benefit": "Wendy can move from quota checking to priority selection without rereading technical run logs.",
            "visibility": "operator-visible",
        }
    if any(t["mood"] == "behind" for t in tools):
        return {
            "before": "Lag was visible as quota and pace numbers, but the operator action was easy to lose in logs.",
            "after": "TokenPulse turns behind status into a clear prompt to start the next AI-work session now.",
            "user_benefit": "Wendy can see the catch-up action immediately and recover useful AI-work before the day slips.",
            "visibility": "operator-visible",
        }
    return {
        "before": "Healthy runway was visible as quota and pace numbers, but the product value was implicit.",
        "after": "TokenPulse states that runway is healthy and the next session should stay aligned to priority.",
        "user_benefit": "Wendy can keep work focused on the highest-priority session without treating quota as the bottleneck.",
        "visibility": "operator-visible",
    }


def _product_impact_line(st: dict) -> str:
    impact = _product_impact(st)
    return (
        "Product impact: "
        f"before: {impact['before']} "
        f"after: {impact['after']} "
        f"benefit: {impact['user_benefit']}"
    )


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sessions", action="store_true")
    args = ap.parse_args(argv)

    if args.sessions:
        rows = sessions.recent_sessions()
        if not rows:
            print(SESSION_EMPTY)
            return 0
        print(SESSION_FRAME)
        for r in rows:
            snip = f"  — {r['snippet']}" if r["snippet"] else ""
            print(f"[{r['tool']:6}] {r['age']:>8}  {r['name']}{snip}")
        return 0

    st = core.status()
    pl = limits.plan_limits()
    if args.json:
        print(json.dumps({
            "status": st,
            "limits": pl,
            "operator_summary": _operator_summary(st),
            "impact_summary": _impact_summary(st),
            "product_impact": _product_impact(st),
        }, indent=2, default=str))
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
        _print_limits(pl.get(tool, {}))
    c = st["combined"]
    print(f"\nΣ  {core.humanize(c['today'])}/{core.humanize(c['target'])}  ({c['percent']:.0f}%)  "
          f"remaining {core.humanize(c['remaining'])}")
    print(_operator_summary(st))
    print(_impact_summary(st))
    print(_product_impact_line(st))
    sug = sessions.suggestion()
    if sug and not all(t["hit"] for t in st["tools"].values()):
        print(f"\n▶  resume [{sug['tool']}] {sug['name']} · {sug['age']}")
        if sug.get("snippet"):
            print(f"   {sug['snippet']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
