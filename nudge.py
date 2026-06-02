"""TokenPulse Telegram nudge — actionable, not just informational.

Run from cron at checkpoint times. Sends a card to your Telegram bot when
you're behind pace on either plan, naming a concrete session to resume so the
nudge fights "I'm not using my plan" instead of merely reporting it.

Credentials reuse the existing park-io setup: env vars
PARKIO_TELEGRAM_BOT_TOKEN / PARKIO_TELEGRAM_CHAT_ID, else
~/park-io/secrets/telegram-bot-token / telegram-chat-id.

Usage:
  python3 nudge.py            # send only if behind (or final checkpoint)
  python3 nudge.py --force    # always send (testing)
  python3 nudge.py --dry-run  # print, don't send
"""
from __future__ import annotations

import argparse
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import core
import sessions

SECRETS = Path.home() / "park-io" / "secrets"
WEEKDAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _load_secret(env_name: str, filename: str) -> str:
    import os

    val = os.environ.get(env_name, "").strip()
    if val:
        return val
    f = SECRETS / filename
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    return ""


def send_telegram(text: str) -> bool:
    token = _load_secret("PARKIO_TELEGRAM_BOT_TOKEN", "telegram-bot-token")
    chat = _load_secret("PARKIO_TELEGRAM_CHAT_ID", "telegram-chat-id")
    if not token or not chat:
        print("[nudge] missing telegram token/chat — cannot send", file=sys.stderr)
        return False
    data = urllib.parse.urlencode({
        "chat_id": chat,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=15) as r:
            body = r.read().decode()
            if '"ok":true' not in body:
                print(f"[nudge] telegram api error: {body}", file=sys.stderr)
                return False
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[nudge] send failed: {exc}", file=sys.stderr)
        return False


def is_final_checkpoint(now: datetime, config: dict) -> bool:
    cps = config.get("checkpoints", [])
    if not cps:
        return False
    last = max(cps)
    lh, lm = (int(x) for x in last.split(":"))
    return (now.hour, now.minute) >= (lh, lm)


def should_send(st: dict, now: datetime, config: dict, force: bool) -> bool:
    if force:
        return True
    behind = any(t["mood"] in ("behind", "ontrack") for t in st["tools"].values())
    if behind:
        return True
    # both clearly on/over target: only send a celebratory summary at day's end
    return is_final_checkpoint(now, config)


def build_message(st: dict, now: datetime) -> str:
    emoji = {"behind": "😴", "ontrack": "🙂", "ahead": "🔥", "done": "✅", "rocket": "🚀"}
    head = f"⏱ TokenPulse · {now.strftime('%H:%M')} · {WEEKDAY[now.weekday()]}"
    lines = [head]
    for tool, label in (("claude", "Claude"), ("codex", "Codex ")):
        t = st["tools"][tool]
        e = emoji.get(t["mood"], "•")
        today, target = core.humanize(t["today"]), core.humanize(t["target"])
        if t["hit"]:
            lines.append(f"{label} {e} {today}/{target} ({t['percent']:.0f}%) ✓")
        else:
            pace_txt = f"pace {core.humanize(t['expected_by_now'])}"
            lines.append(f"{label} {e} {today}/{target} — need {core.humanize(t['remaining'])} ({pace_txt})")
    c = st["combined"]
    lines.append(f"Σ {core.humanize(c['today'])}/{core.humanize(c['target'])} ({c['percent']:.0f}%)")

    all_hit = all(t["hit"] for t in st["tools"].values())
    if all_hit:
        lines.append("")
        lines.append("🎉 两个 plan 今天都达标了，去做别的事吧。")
    else:
        sug = sessions.suggestion()
        lines.append("")
        lines.append("▶ 去把 token 用掉：")
        if sug:
            snip = f"\n   {sug['snippet']}" if sug.get("snippet") else ""
            lines.append(f"resume [{sug['tool']}] {sug['name']} · {sug['age']}{snip}")
        else:
            lines.append("（最近 5 天没有 session — 开个新任务）")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="always send")
    ap.add_argument("--dry-run", action="store_true", help="print, do not send")
    args = ap.parse_args(argv)

    config = core.load_config()
    if not config.get("telegram", {}).get("enabled", True) and not args.force:
        print("[nudge] telegram disabled in config")
        return 0
    now = datetime.now().astimezone()
    st = core.status(now=now, config=config)
    if not should_send(st, now, config, args.force):
        print("[nudge] on pace, nothing to nudge")
        return 0
    msg = build_message(st, now)
    if args.dry_run:
        print(msg)
        return 0
    ok = send_telegram(msg)
    print("[nudge] sent" if ok else "[nudge] failed")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
