"""Cloud-provider usage fetchers. Each returns the SAME normalized summary dict
as the local claude/codex summaries, so callers never branch on provider. Never
raises into the UI — returns {available: False, reason} on any failure.

Honesty: only GLM exposes real TOKENS. DeepSeek = money balance, MiniMax =
request quota, etc. — those carry their native numbers in `display` and are
metric-gated out of the token headline upstream. stdlib only.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

import providers

TIMEOUT = 8


def _empty(metric: str = "tokens", reason: str = "no-key") -> dict:
    return {"metric": metric, "tokens_today": 0, "tokens_30d": 0, "latest_tokens": 0,
            "cost_today": 0.0, "cost_30d": 0.0, "cache_read_30d": 0, "input_30d": 0,
            "display": {}, "available": False, "reason": reason}


def _get(url: str, headers: dict, timeout: int = TIMEOUT):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (trusted vendor hosts)
        return json.loads(r.read().decode("utf-8"))


def _fetch_json(url: str, headers: dict, out: dict, *, retry_no_bearer_key: str | None = None):
    """GET json with one optional 401-retry (GLM's raw-key quirk). Mutates `out`
    with a reason on failure; returns the parsed dict or None."""
    attempts = [headers]
    if retry_no_bearer_key:
        attempts.append({**headers, "Authorization": retry_no_bearer_key})
    for hdr in attempts:
        try:
            return _get(url, hdr)
        except urllib.error.HTTPError as e:
            if e.code == 401 and hdr is not attempts[-1]:
                continue
            out["reason"] = f"http-{e.code}"
            return None
        except (urllib.error.URLError, ValueError, OSError, TimeoutError):
            out["reason"] = "unreachable"
            return None
    out["reason"] = "auth"
    return None


# ----------------------------------------------- GLM / Zhipu (z.ai Coding Plan)

def glm_summary(now=None, config=None) -> dict:
    """5h rolling TOKEN window for a GLM Coding Plan key (the real token win)."""
    out = _empty("tokens")
    key = providers.api_key("glm", config)
    if not key:
        return out
    pcfg = (config or {}).get("providers", {}) if isinstance(config, dict) else {}
    host = "https://bigmodel.cn" if pcfg.get("glm_mainland") else "https://api.z.ai"
    data = _fetch_json(f"{host}/api/monitor/usage/quota/limit",
                       {"Authorization": f"Bearer {key}", "Accept": "application/json"},
                       out, retry_no_bearer_key=key)
    if data is None:
        return out
    d = data.get("data") if isinstance(data, dict) else None
    if not isinstance(d, dict):
        out["reason"] = "bad-shape"
        return out
    tok = next((l for l in (d.get("limits") or []) if l.get("type") == "TOKENS_LIMIT"), None)
    if not tok:
        out["reason"] = "no-token-limit"
        return out
    used = int(tok.get("used", 0) or 0)
    lim = int(tok.get("limit", 0) or 0)
    reset_ms = tok.get("nextResetTime") or 0
    reset = (datetime.fromtimestamp(reset_ms / 1000, tz=timezone.utc).isoformat()
             if reset_ms else None)
    out.update(available=True, reason="ok", tokens_today=used)
    out["display"] = {"window": "5h", "used": used, "limit": lim,
                      "percent": round(used / lim * 100, 1) if lim else 0.0,
                      "reset_at": reset, "plan": d.get("planName") or ""}
    return out


# --------------------------------------------------------------- DeepSeek (balance)

def deepseek_summary(now=None, config=None) -> dict:
    out = _empty("credits")
    key = providers.api_key("deepseek", config)
    if not key:
        return out
    data = _fetch_json("https://api.deepseek.com/user/balance",
                       {"Authorization": f"Bearer {key}", "Accept": "application/json"}, out)
    if data is None:
        return out
    infos = data.get("balance_infos") or []
    if not infos:
        out["reason"] = "bad-shape"
        return out
    b = infos[0]
    out.update(available=True, reason="ok")
    out["display"] = {"currency": b.get("currency"), "total": b.get("total_balance"),
                      "granted": b.get("granted_balance"), "topped_up": b.get("topped_up_balance"),
                      "is_available": data.get("is_available")}
    return out


# --------------------------------------------------------------- MiniMax (requests)

def minimax_summary(now=None, config=None) -> dict:
    out = _empty("requests")
    key = providers.api_key("minimax", config)
    if not key:
        return out
    data = _fetch_json("https://api.minimax.io/v1/token_plan/remains",
                       {"Authorization": f"Bearer {key}", "Accept": "application/json"}, out)
    if data is None:
        return out
    # per-model objects with currentIntervalRemainingCount / currentIntervalTotalCount
    rows = data.get("data") if isinstance(data.get("data"), list) else (
        data.get("models") if isinstance(data.get("models"), list) else [])
    rem = sum(int(r.get("currentIntervalRemainingCount", 0) or 0) for r in rows)
    tot = sum(int(r.get("currentIntervalTotalCount", 0) or 0) for r in rows)
    out.update(available=True, reason="ok")
    out["display"] = {"remaining": rem, "total": tot,
                      "percent": round((tot - rem) / tot * 100, 1) if tot else 0.0,
                      "raw_models": len(rows)}
    return out


if __name__ == "__main__":
    import core
    cfg = core.load_config()
    for pid, fn in (("glm", glm_summary), ("deepseek", deepseek_summary), ("minimax", minimax_summary)):
        print(pid, "->", fn(config=cfg))
