"""TokenPulse ranking client — submits the user's monthly burn to the CF global
ranking Worker and fetches the leaderboard. stdlib only; never raises into UI.

Every fetcher returns None on ANY failure (network, timeout, HTTP error,
malformed JSON, or disabled config) — callers treat None as "unavailable, any
reason" and degrade gracefully (the widget hides the rank line)."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 8
# Cloudflare's edge 403s the default "Python-urllib/x" UA before it reaches the
# Worker, so every request must carry an explicit, non-default User-Agent.
UA = "TokenPulse/1.0 (+https://park-ai-intel.com/tokenpulse)"


def _cfg(config: dict | None) -> tuple[str, bool]:
    """Return (base_url, enabled) from config.ranking.*."""
    r = (config or {}).get("ranking")
    if not isinstance(r, dict):
        return "", False
    return (r.get("url") or "").rstrip("/"), bool(r.get("enabled", True))


def submit(tokens_30d: int, tokens_lifetime: int, config: dict | None = None) -> dict | None:
    """Upsert the user's score. Returns {ok, rank} or None on failure/disabled."""
    url, enabled = _cfg(config)
    if not enabled or not url:
        return None
    import core as _c
    cfg = config or _c.load_config()
    handle = (cfg.get("handle") or "").strip()[:64]  # match the Worker's 64-char store
    if not handle:
        return None
    try:
        body = json.dumps({
            "handle": handle,
            "tokens_30d": int(tokens_30d),
            "tokens_lifetime": int(tokens_lifetime),
        }).encode()
        req = urllib.request.Request(
            f"{url}/rank/submit",
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": UA},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception:  # noqa: BLE001
        return None


def top(n: int = 10, offset: int = 0, config: dict | None = None) -> dict | None:
    """Fetch top-N rows from the leaderboard. Returns {rows, total} or None."""
    url, _ = _cfg(config)
    if not url:
        return None
    try:
        q = urllib.parse.urlencode({"n": n, "offset": offset})
        req = urllib.request.Request(f"{url}/rank/top?{q}", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception:  # noqa: BLE001
        return None


def me(handle: str, config: dict | None = None) -> dict | None:
    """Fetch one user's rank entry. Returns {found, handle, rank, ...} or None."""
    url, _ = _cfg(config)
    if not url or not handle:
        return None
    try:
        q = urllib.parse.urlencode({"handle": handle})
        req = urllib.request.Request(f"{url}/rank/me?{q}", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception:  # noqa: BLE001
        return None
