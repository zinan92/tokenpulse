"""Tier ladder ("电子宠物" progression) + badges + share-card data.

The tier ladder is the 西游记 ascension — you raise your AI from a 石猴 (stone
monkey) all the way to 如来佛祖, by monthly token burn. 6.3B/mo lands you at
齐天大圣 (second-from-top of the ladder); 10B/mo is the 如来 prestige summit.
Tier names carry the identity flex; badges are metric achievements across many
dimensions; lifetime totals come from the never-pruned accumulator (lifetime.py).

card_data() is the single source the widget panel and the share card render from.
Pure stdlib.
"""
from __future__ import annotations

from datetime import datetime

import continuity
import cost
import core
import history
import lifetime

MILLION = 1_000_000
BILLION = 1_000_000_000

# 西游记 ascension ladder — climbs with rolling-30d combined tokens (DESCENDING).
# (min_monthly_tokens, emoji, name_cn, name_en, blurb)
SAGA_TIERS = [
    (10 * BILLION, "🌸", "如来佛祖", "Tathagata", "登顶 — 超脱三界，万法归一。"),
    (8 * BILLION, "🏆", "斗战胜佛", "Victorious Buddha", "悟空的证道之身，斗战即胜。"),
    (5 * BILLION, "🐵", "齐天大圣", "Great Sage", "齐天大圣 — 与天同寿，一人撼天宫。"),
    (2_500 * MILLION, "🔱", "哪吒三太子", "Prince Nezha", "三头六臂，天庭先锋。"),
    (1 * BILLION, "🛡️", "天将", "Heavenly General", "首过十亿 — 受封天将，统御一方。"),
    (500 * MILLION, "☁️", "地仙", "Earth Immortal", "得道成仙，腾云驾雾。"),
    (100 * MILLION, "🦍", "美猴王", "Monkey King", "花果山称王，初掌一方。"),
    (0, "🐒", "石猴", "Stone Monkey", "灵石初醒 — 修行自此而始。"),
]

# legacy generic milestone tables (kept for utility / tests)
TOKEN_MILESTONES = [(100 * BILLION, "100B"), (50 * BILLION, "50B"),
                    (10 * BILLION, "10B"), (1 * BILLION, "1B")]
COST_MILESTONES = [(50000, "$50k"), (10000, "$10k"), (5000, "$5k"), (1000, "$1k")]
STREAK_MILESTONES = [(100, 100), (30, 30), (7, 7)]


def _tier(monthly_tokens: int) -> dict:
    for i, (thr, emoji, cn, en, blurb) in enumerate(SAGA_TIERS):
        if monthly_tokens >= thr:
            nxt = SAGA_TIERS[i - 1] if i > 0 else None
            progress = None
            if nxt:
                span = nxt[0] - thr
                progress = round((monthly_tokens - thr) / span, 3) if span else 1.0
            return {
                "emoji": emoji, "name": cn, "name_en": en, "blurb": blurb, "min": thr,
                "next": ({"emoji": nxt[1], "name": nxt[2], "name_en": nxt[3], "at": nxt[0]} if nxt else None),
                "progress_to_next": progress,
            }
    last = SAGA_TIERS[-1]
    return {"emoji": last[1], "name": last[2], "name_en": last[3], "blurb": last[4],
            "min": 0, "next": None, "progress_to_next": None}


def _best_streak(series: list, target: int) -> int:
    best = cur = 0
    for r in series:
        cur = cur + 1 if r["total"] >= target else 0
        best = max(best, cur)
    return best


def _highest(thresholds, value):
    for thr, label in thresholds:
        if value >= thr:
            return label
    return None


def _best_window(totals: list, w: int) -> int:
    """Largest sum of any `w` consecutive days."""
    if not totals:
        return 0
    if len(totals) < w:
        return sum(totals)
    cur = best = sum(totals[:w])
    for i in range(w, len(totals)):
        cur += totals[i] - totals[i - w]
        best = max(best, cur)
    return best


def _tok(n: int) -> str:
    return cost.humanize_tokens(n)


def _builder_config(config: dict) -> dict:
    defaults = core.DEFAULT_CONFIG.get("builder", {})
    raw = config.get("builder") if isinstance(config.get("builder"), dict) else {}
    out = {**defaults, **raw}
    return {
        "handle": (out.get("handle") or "").lstrip("@"),
        "xhs_id": out.get("xhs_id") or "",
        "douyin_id": out.get("douyin_id") or "",
        "url": out.get("url") or defaults.get("url", ""),
    }


def _build_badges(life, streak, best_streak, record_total, per_tool30, cur30, prev30, best30,
                  hit_rate=0.0, peak_session=None) -> list:
    """Earned badges across many dimensions. hero=screenshot-headline."""
    out = []

    def add(cond, icon, name, hero=False, expert=False):
        if cond:
            out.append({"icon": icon, "name": name, "hero": hero, "expert": expert})

    lt = life["lifetime_tokens"]
    cl, cx = per_tool30.get("claude", 0), per_tool30.get("codex", 0)
    tot = cl + cx

    # lifetime milestones (highest achieved; hero) ------------------------------
    add(lt >= 1000 * BILLION, "💫", "万亿俱乐部 1T", hero=True, expert=True)
    add(100 * BILLION <= lt < 1000 * BILLION, "🌌", "千亿级 100B", hero=True, expert=True)
    add(10 * BILLION <= lt < 100 * BILLION, "🌠", "百亿级 10B", hero=True, expert=True)
    add(1 * BILLION <= lt < 10 * BILLION, "✨", "十亿里程 1B", hero=False, expert=True)
    # single-day intensity ------------------------------------------------------
    add(record_total >= 1 * BILLION, "☄️", "十亿日 Billion-Day", hero=True, expert=True)
    add(500 * MILLION <= record_total < 1 * BILLION, "🌋", "五亿日", hero=False, expert=True)
    add(250 * MILLION <= record_total < 500 * MILLION, "💥", "爆燃日", hero=False)
    # single-SESSION intensity (one unbroken session, distinct from a whole day) --
    pst = (peak_session or {}).get("total", 0)
    add(pst >= 1 * BILLION, "🌪️", "单会话 1B", hero=True, expert=True)
    add(500 * MILLION <= pst < 1 * BILLION, "🌀", "单会话 500M", hero=True, expert=True)
    add(250 * MILLION <= pst < 500 * MILLION, "🔥", "单会话 250M", hero=False, expert=True)
    add(100 * MILLION <= pst < 250 * MILLION, "💢", "单会话 100M", hero=False)
    # streaks -------------------------------------------------------------------
    add(best_streak >= 365, "♾️", "不熄之核 365d", hero=True, expert=True)
    add(100 <= best_streak < 365, "⛓️", "铁流 100d", hero=True, expert=True)
    add(30 <= best_streak < 100, "🕯️", "持灯者 30d", hero=False, expert=True)
    add(7 <= best_streak < 30, "🔥", "不灭之火 7d", hero=False)
    # multi-tool breadth --------------------------------------------------------
    add(cl >= 1 * BILLION and cx >= 1 * BILLION, "⚖️", "双机手 Two-Rig", hero=True, expert=True)
    add(tot > 0 and min(cl, cx) / tot >= 0.35, "🎛️", "均衡输出", hero=False, expert=True)
    # velocity ------------------------------------------------------------------
    add(prev30 > 0 and cur30 >= 1.5 * prev30, "🚀", "扩产 Scaling-Up", hero=False, expert=True)
    add(cur30 > 0 and best30 > 0 and cur30 >= best30, "🌊", "月度新高", hero=False)
    # context-engineering mastery (cache hit-rate; mutually exclusive) -----------
    add(hit_rate >= 0.80, "🧠", "缓存宗师 Cache Virtuoso", hero=True, expert=True)
    add(0.60 <= hit_rate < 0.80, "📦", "上下文大师 Context Loader", hero=False, expert=True)

    out.sort(key=lambda b: (not b["hero"], not b["expert"]))
    return out


def card_data(now: datetime | None = None, config: dict | None = None) -> dict:
    """Everything the egg/badge UI and the share card render from."""
    config = config or core.load_config()
    p = history.panel_data(now=now, config=config)
    rec = history.lifetime_records(now=now, config=config)
    costs = {t: cost.usage_summary(t) for t in ("claude", "codex")}
    monthly_tokens = costs["claude"]["tokens_30d"] + costs["codex"]["tokens_30d"]
    monthly_cost = round(costs["claude"]["cost_30d"] + costs["codex"]["cost_30d"], 2)
    today_cl = costs["claude"].get("tokens_today", 0) or 0
    today_cx = costs["codex"].get("tokens_today", 0) or 0
    life = lifetime.summary(now, today_tokens=today_cl + today_cx,
                            today_claude=today_cl, today_codex=today_cx)

    streak = p["streak"]
    best_streak = rec["best_streak"]
    record_day = life["peak_day"] or rec["record_day"]   # all-time (never-pruned)
    per_tool30 = {t: costs[t]["tokens_30d"] for t in ("claude", "codex")}

    # longer daily series for windows / velocity (cached, up to 120d)
    long = history.daily_tokens(now, days=120)["series"]
    totals = [r["total"] for r in long]
    prev30 = sum(totals[-60:-30]) if len(totals) >= 60 else 0
    # cost.tokens_30d is the canonical "this month" figure; keep the daily-series
    # windows consistent with it so the card can never show best-30d < this-month
    # (the daily sum and cost's dedup differ by ~1%, which would contradict itself).
    cur30 = max(sum(totals[-30:]), monthly_tokens)
    best30 = max(_best_window(totals, 30), cur30)

    cache_read_30d = costs["claude"].get("cache_read_30d", 0) + costs["codex"].get("cache_read_30d", 0)
    input_30d = costs["claude"].get("input_30d", 0) + costs["codex"].get("input_30d", 0)
    hit_rate = cost.cache_hit_rate(cache_read_30d, input_30d)

    # engagement (active/online time) — honest "≤30min-gap" stretch + per-day active.
    # NB: inflated by background automation that emits timestamps; framed as 在线/活跃,
    # not hands-on-keyboard. Non-hero so it never dominates the public card.
    cont = continuity.summary(now)
    active_series = history.daily_active_minutes(now, days=120)["series"]
    peak_active_min = max((r["minutes"] for r in active_series), default=0)
    lifetime_active_min = sum(r["minutes"] for r in active_series)

    # engagement stays OUT of the card badge list (panel-only, per user) — the panel
    # reads longest_run / active directly from the returned dict below.
    badges = _build_badges(life, streak, best_streak,
                           (record_day or {}).get("total", 0), per_tool30, cur30, prev30, best30,
                           hit_rate=hit_rate, peak_session=life.get("peak_session"))

    return {
        "tier": _tier(monthly_tokens),
        "monthly_tokens": monthly_tokens,
        "monthly_cost": monthly_cost,
        "streak": streak,
        "best_streak": best_streak,
        "record_day": record_day,
        "best_day": p.get("best"),
        "lifetime": life,
        "rank_self": {
            "peak_day": record_day,
            "best_30d": best30,
            "cur_30d": cur30,
            "is_high_water": cur30 > 0 and best30 > 0 and cur30 >= best30,
            "founding": True,           # honest local stand-in until a real pool exists
        },
        "cache_hit_rate": round(hit_rate, 3),
        "peak_session": life.get("peak_session"),
        "longest_run": cont,  # {longest_hours, longest_start, longest_end, ...}
        "active": {"peak_minutes": peak_active_min, "lifetime_minutes": lifetime_active_min,
                   "today_minutes": history.active_minutes_today_merged(now)},
        "days_tracked": rec["days_tracked"],
        "avg": p["avg"],
        "hit_days": p["hit_days"],
        "total_days": p["total_days"],
        "active_today": p.get("active_today"),
        "series": [r["total"] for r in p["series"]],
        "combined_target": p["combined_target"],
        "badges": badges,
        "handles": {"x": config.get("handle") or "", "xhs": config.get("xhs_id") or ""},
        "builder": _builder_config(config),
        "per_tool": {t: {"tokens_30d": costs[t]["tokens_30d"],
                         "cost_30d": round(costs[t]["cost_30d"], 2)} for t in ("claude", "codex")},
    }


if __name__ == "__main__":
    d = card_data()
    t = d["tier"]
    print(f"{t['emoji']} {t['name']} ({t['name_en']})  {d['monthly_tokens']/1e9:.1f}B/mo  ${d['monthly_cost']:.0f}")
    if t["next"]:
        print(f"  next: {t['next']['emoji']} {t['next']['name']} at {t['next']['at']/1e9:.0f}B "
              f"({d['tier']['progress_to_next']*100:.0f}% there)")
    lf = d["lifetime"]
    print(f"  lifetime {lf['lifetime_tokens']/1e9:.2f}B since {lf['first_use_date']} "
          f"({lf['days_active']} active days)")
    print(f"  streak {d['streak']} (best {d['best_streak']}) · record {_tok((d['record_day'] or {}).get('total',0))}")
    print(f"  badges: {[b['icon']+' '+b['name'] for b in d['badges']]}")
