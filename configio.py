"""Read/validate/write the editable subset of config.json — for the settings UI.

The widget exposes a few knobs (daily targets, plan price, active window). This
module loads the current values, validates a partial edit, deep-merges it into
the on-disk config.json, and writes it back. Pure-logic functions are testable;
the only side effect is the file write in save_partial().
"""
from __future__ import annotations

import json
from pathlib import Path

import core

CONFIG_PATH = Path(__file__).with_name("config.json")
EDITABLE = ("targets", "handle", "xhs_id", "providers", "ranking")  # + leaderboard consent


def load_raw() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def editable_config() -> dict:
    """Current effective values for the editable fields (defaults filled in)."""
    c = core.load_config()
    return {k: c.get(k) for k in EDITABLE}


def validate_partial(p: dict) -> list[str]:
    """Return a list of human-readable problems; empty means valid."""
    errs = []
    t = p.get("targets", {})
    if not isinstance(t, dict):
        errs.append("targets")
    else:
        for tool in ("claude", "codex"):
            for k in ("weekday", "weekend"):
                v = (t.get(tool) or {}).get(k)
                if v is not None and (not isinstance(v, (int, float)) or v <= 0 or v > 100000):
                    errs.append(f"目标 {tool}.{k}")
    h = p.get("handle")
    if h is not None and (not isinstance(h, str) or len(h.lstrip("@")) > 40):
        errs.append("handle")
    x = p.get("xhs_id")
    if x is not None and (not isinstance(x, str) or len(x) > 40):
        errs.append("xhs_id")
    r = p.get("ranking")
    if r is not None:
        if not isinstance(r, dict):
            errs.append("ranking")
        else:
            if r.get("enabled") is not None and not isinstance(r.get("enabled"), bool):
                errs.append("ranking.enabled")
            if r.get("url") is not None and not isinstance(r.get("url"), str):
                errs.append("ranking.url")
    pr = p.get("providers")
    if pr is not None:
        if not isinstance(pr, dict):
            errs.append("providers")
        else:
            en = pr.get("enabled")
            if en is not None and (not isinstance(en, list)
                                   or any(not isinstance(i, str) for i in en)):
                errs.append("providers.enabled")
            ks = pr.get("keys")
            if ks is not None and (not isinstance(ks, dict)
                                   or any(not isinstance(v, str) for v in ks.values())):
                errs.append("providers.keys")
    return errs


def deep_merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def save_partial(partial: dict) -> dict:
    """Validate + deep-merge into config.json. Returns {ok, errors?, config?}."""
    if not isinstance(partial, dict):
        return {"ok": False, "errors": ["bad payload"]}
    # keep only editable keys — never let the UI write furnace/telegram/etc.
    partial = {k: v for k, v in partial.items() if k in EDITABLE}
    errs = validate_partial(partial)
    if errs:
        return {"ok": False, "errors": errs}
    merged = deep_merge(load_raw(), partial)
    try:
        CONFIG_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "errors": [str(exc)]}
    return {"ok": True, "config": {k: merged.get(k) for k in EDITABLE}}
