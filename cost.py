"""Cost + token aggregates for TokenPulse.

Prices tokens at API rates from the open models.dev catalog (fetched directly),
giving "Today cost / 30d cost / 30d tokens". When CodexBar is installed, its
local Codex scanner is reused because it understands current cumulative and
forked-agent Codex logs.

Cost = Σ over priced units of  input×in + cache_creation×cache_write +
cache_read×cache_read + output×output  (per model, /1e6).

Heavy 30-day scans are TTL-cached (the widget refreshes often; 30d barely moves).
Pure stdlib.
"""
from __future__ import annotations

import glob
import json
import os
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import codexbar
import core  # reuse _codex_session_uuid, _parse_ts, dedup ideas

MODELS_DEV_URL = "https://models.dev/api.json"
PRICE_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".models-pricing.json")
PRICE_TTL = 86400  # refetch models.dev at most once a day
# Optional fallback if models.dev is unreachable AND our cache is empty.
CODEXBAR_PRICE = os.path.expanduser(
    "~/Library/Caches/codexbar/model-pricing/models-dev-v1.json"
)
MILLION = 1_000_000
_CACHE: dict = {}
DEFAULT_TTL = 600  # seconds


# ----------------------------------------------------------------- price table

def _flatten(providers: dict) -> dict:
    """{provider: {models: {id: {cost}}}} -> flat {id: cost} for anthropic+openai."""
    out = {}
    for pid in ("anthropic", "openai"):
        for mid, m in providers.get(pid, {}).get("models", {}).items():
            if isinstance(m.get("cost"), dict):
                out[mid] = m["cost"]
    return out


def _load_prices() -> dict:
    """model-id -> {input, output, cache_read, cache_write} ($/Mtok).

    Source order: our fresh disk cache → live models.dev → stale disk cache →
    CodexBar's cache (legacy fallback). Decoupled from CodexBar.
    """
    if "prices" in _CACHE:
        return _CACHE["prices"]
    prices: dict[str, dict] = {}
    # 1. our own disk cache, if fresh
    try:
        if os.path.exists(PRICE_CACHE) and time.time() - os.path.getmtime(PRICE_CACHE) < PRICE_TTL:
            prices = json.load(open(PRICE_CACHE, encoding="utf-8"))
    except (OSError, ValueError):
        pass
    # 2. fetch live models.dev (top-level providers) and cache it
    if not prices:
        try:
            req = urllib.request.Request(
                MODELS_DEV_URL, headers={"User-Agent": "tokenpulse/1.0 (+https://github.com/zinan92/tokenpulse)"})
            with urllib.request.urlopen(req, timeout=10) as r:
                prices = _flatten(json.loads(r.read()))
            if prices:
                try:
                    json.dump(prices, open(PRICE_CACHE, "w", encoding="utf-8"))
                except OSError:
                    pass
        except Exception:  # noqa: BLE001  (network / parse — fall through)
            pass
    # 3. stale disk cache
    if not prices:
        try:
            prices = json.load(open(PRICE_CACHE, encoding="utf-8"))
        except (OSError, ValueError):
            pass
    # 4. CodexBar's cache (legacy fallback; catalog.providers structure)
    if not prices:
        try:
            prices = _flatten(json.load(open(CODEXBAR_PRICE, encoding="utf-8"))["catalog"]["providers"])
        except (OSError, ValueError, KeyError):
            pass
    _CACHE["prices"] = prices
    return prices


def _is_dated(mid: str) -> bool:
    return bool(re.search(r"\d{8}$", mid))


def price_for(model: str, prices: dict | None = None) -> dict:
    """Look up a model's rates with graceful fallback.

    1. exact match
    2. strip a trailing -YYYYMMDD
    3. family fallback: trim trailing -<seg> until siblings exist, then pick the
       highest-version, non-dated sibling. This keeps NEW models priced when the
       cached table lags (e.g. claude-opus-4-8 → claude-opus-4-7 rates, since
       Anthropic keeps Opus pricing flat across point releases).
    """
    if not model:
        return {}
    prices = prices if prices is not None else _load_prices()
    if model in prices:
        return prices[model]
    base = re.sub(r"-\d{8}$", "", model)
    if base in prices:
        return prices[base]
    stem = base
    while "-" in stem:
        stem = stem.rsplit("-", 1)[0]
        sibs = [k for k in prices if k == stem or k.startswith(stem + "-")]
        if sibs:
            best = max(sibs, key=lambda k: (
                0 if _is_dated(k) else 1,
                tuple(int(n) for n in re.findall(r"\d+", k[len(stem):])),
            ))
            return prices[best]
    return {}


def _cost(rates: dict, inp: int, cache_create: int, cache_read: int, out: int) -> float:
    if not rates:
        return 0.0
    return (
        inp * rates.get("input", 0)
        + cache_create * rates.get("cache_write", rates.get("input", 0))
        + cache_read * rates.get("cache_read", 0)
        + out * rates.get("output", 0)
    ) / MILLION


# ------------------------------------------------------------------- Claude

def _claude_summary(now: datetime) -> dict:
    prices = _load_prices()
    today = now.astimezone().date()
    floor_day = today - timedelta(days=30)
    floor_mtime = (datetime.combine(floor_day, datetime.min.time()).astimezone()
                   - timedelta(days=1)).timestamp()
    seen: set = set()
    cost_today = cost_30d = 0.0
    tok_today = tok_30d = 0
    cache_read_30d = input_30d = 0  # for cache hit-rate (Claude buckets are disjoint)
    # latest session = most-recently-modified transcript file
    sessions: dict[str, dict] = {}  # path -> {mtime, tokens}
    for f in glob.glob(os.path.expanduser("~/.claude/projects/**/*.jsonl"), recursive=True):
        try:
            mt = os.path.getmtime(f)
        except OSError:
            continue
        if mt < floor_mtime:
            continue
        try:
            for line in open(f, encoding="utf-8"):
                try:
                    d = json.loads(line)
                except (ValueError, TypeError):
                    continue
                msg = d.get("message")
                if not isinstance(msg, dict):
                    continue
                u = msg.get("usage")
                if not isinstance(u, dict):
                    continue
                mid = msg.get("id")
                key = (mid, d.get("requestId"))
                if mid and key in seen:
                    continue
                if mid:
                    seen.add(key)
                dt = core._parse_ts(d.get("timestamp"))
                if dt is None:
                    continue
                ld = dt.astimezone().date()
                if ld < floor_day:
                    continue
                inp = u.get("input_tokens", 0) or 0
                cc = u.get("cache_creation_input_tokens", 0) or 0
                cr = u.get("cache_read_input_tokens", 0) or 0
                out = u.get("output_tokens", 0) or 0
                toks = inp + cc + cr + out
                c = _cost(price_for(msg.get("model", ""), prices), inp, cc, cr, out)
                cost_30d += c
                tok_30d += toks
                cache_read_30d += cr
                input_30d += inp + cc + cr  # disjoint buckets; output excluded
                if ld == today:
                    cost_today += c
                    tok_today += toks
                s = sessions.setdefault(f, {"mtime": mt, "tokens": 0})
                s["tokens"] += toks
        except OSError:
            continue
    latest = max(sessions.values(), key=lambda s: s["mtime"], default={"tokens": 0})
    return {"cost_today": cost_today, "cost_30d": cost_30d,
            "tokens_today": tok_today, "tokens_30d": tok_30d,
            "latest_tokens": latest["tokens"],
            "cache_read_30d": cache_read_30d, "input_30d": input_30d}


# -------------------------------------------------------------------- Codex

def _codex_session_model(path: str) -> str:
    try:
        for line in open(path, encoding="utf-8"):
            if '"model"' not in line:
                continue
            try:
                d = json.loads(line)
            except (ValueError, TypeError):
                continue
            payload = d.get("payload")
            if isinstance(payload, dict) and isinstance(payload.get("model"), str):
                return payload["model"]
    except OSError:
        pass
    return ""


def _codex_summary(now: datetime) -> dict:
    # Codex's current rollout format emits cumulative snapshots through forked
    # agents. CodexBar's local scanner handles those boundaries exactly; use its
    # already-local result when available so our widget matches the trusted
    # ledger instead of multiplying repeated per-turn snapshots.
    external = codexbar.usage(now=now, days=30)
    if external.get("available"):
        return {
            "cost_today": external["cost_today"],
            "cost_30d": external["cost_30d"],
            "tokens_today": external["tokens_today"],
            "tokens_30d": external["tokens_30d"],
            "latest_tokens": external["tokens_today"],
            "cache_read_30d": external["cache_read_30d"],
            "input_30d": external["input_30d"],
        }
    prices = _load_prices()
    today = now.astimezone().date()
    floor_day = today - timedelta(days=30)
    floor_mtime = (datetime.combine(floor_day, datetime.min.time()).astimezone()
                   - timedelta(days=1)).timestamp()
    cost_today = cost_30d = 0.0
    tok_today = tok_30d = 0
    cache_read_30d = input_30d = 0  # Codex cached_input is a SUBSET of input
    latest_mtime, latest_tokens = 0.0, 0
    chosen: dict[str, str] = {}
    mtimes: dict[str, float] = {}
    for pat in (os.path.expanduser("~/.codex/sessions/**/*.jsonl"),
                os.path.expanduser("~/.codex/archived_sessions/**/*.jsonl")):
        for f in glob.glob(pat, recursive=True):
            try:
                mt = os.path.getmtime(f)
            except OSError:
                continue
            if mt < floor_mtime:
                continue
            uid = core._codex_session_uuid(f)
            if uid not in mtimes or mt > mtimes[uid]:
                mtimes[uid], chosen[uid] = mt, f
    for uid, f in chosen.items():
        rates = price_for(_codex_session_model(f), prices)
        mt = mtimes[uid]
        sess_tokens = 0
        try:
            for line in open(f, encoding="utf-8"):
                try:
                    d = json.loads(line)
                except (ValueError, TypeError):
                    continue
                info = (d.get("payload") or {}).get("info") if isinstance(d.get("payload"), dict) else None
                if not isinstance(info, dict):
                    continue
                lt = info.get("last_token_usage")
                if not isinstance(lt, dict):
                    continue
                dt = core._parse_ts(d.get("timestamp"))
                if dt is None:
                    continue
                ld = dt.astimezone().date()
                if ld < floor_day:
                    continue
                inp = lt.get("input_tokens", 0) or 0
                cached = lt.get("cached_input_tokens", 0) or 0
                out = lt.get("output_tokens", 0) or 0
                toks = lt.get("total_tokens", 0) or 0
                c = _cost(rates, max(0, inp - cached), 0, cached, out)
                cost_30d += c
                tok_30d += toks
                sess_tokens += toks
                cache_read_30d += cached
                input_30d += inp  # cached is already a subset of input
                if ld == today:
                    cost_today += c
                    tok_today += toks
        except OSError:
            continue
        if mt > latest_mtime:
            latest_mtime, latest_tokens = mt, sess_tokens
    return {"cost_today": cost_today, "cost_30d": cost_30d,
            "tokens_today": tok_today, "tokens_30d": tok_30d,
            "latest_tokens": latest_tokens,
            "cache_read_30d": cache_read_30d, "input_30d": input_30d}


# ----------------------------------------------------------------- public API

def usage_summary(tool: str, now: datetime | None = None, ttl: int = DEFAULT_TTL) -> dict:
    """{cost_today, cost_30d, tokens_today, tokens_30d, latest_tokens} per tool.

    TTL-cached (default 10 min) — the 30-day scan is expensive and barely moves.
    """
    now = now or datetime.now().astimezone()
    ck = f"summary:{tool}"
    hit = _CACHE.get(ck)
    if hit and (time.time() - hit[0]) < ttl:
        return hit[1]
    fn = _claude_summary if tool == "claude" else _codex_summary
    val = fn(now)
    _CACHE[ck] = (time.time(), val)
    return val


def humanize_tokens(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1e9:.1f}B"
    if n >= MILLION:
        return f"{n / MILLION:.0f}M"
    if n >= 1000:
        return f"{n / 1000:.0f}K"
    return str(n)


def humanize_cost(c: float) -> str:
    return f"${c:,.2f}"


def cache_hit_rate(cache_read: int, total_input: int) -> float:
    """rolling-30d cache_read / total input tokens, clamped to [0,1]."""
    if total_input <= 0:
        return 0.0
    return min(1.0, cache_read / total_input)


if __name__ == "__main__":
    for tool in ("claude", "codex"):
        s = usage_summary(tool, ttl=0)
        print(f"{tool}:  today {humanize_cost(s['cost_today'])} · 30d {humanize_cost(s['cost_30d'])} "
              f"· 30d tokens {humanize_tokens(s['tokens_30d'])} · latest {humanize_tokens(s['latest_tokens'])}")
