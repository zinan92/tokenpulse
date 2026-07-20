"""Provider registry — which LLM vendors TokenPulse can track, and how each one
is sourced. The user ticks providers in Settings; claude + codex are on by
default. Two sourcing kinds:

  - "local": usage read from on-disk logs/state (no credentials) — Claude Code,
    Codex, Cursor.
  - "api":   usage fetched from the vendor's own usage/billing API with the
    user's key — GLM, DeepSeek, Doubao, MiniMax, MiMo.

This module only declares the catalog + reads the enabled set from config; the
per-provider fetchers live in cost.py / limits.py (local) and providers_api.py
(cloud). Pure stdlib.
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess

import core

# id -> metadata. metric is HONEST: only the vendors that expose real token
# counts are "tokens" (they sum into the burn headline); the rest are gauges.
#   fetch = "module:function" returning the normalized summary (api providers).
REGISTRY: dict[str, dict] = {
    "claude":   {"label": "Claude Code", "kind": "local",  "metric": "tokens",   "default_on": True},
    "codex":    {"label": "Codex",       "kind": "local",  "metric": "tokens",   "default_on": True},
    "glm":      {"label": "GLM 智谱",     "kind": "api",    "metric": "tokens",   "default_on": False,
                 "auth": "api_key", "fetch": "providers_api:glm_summary"},
    "deepseek": {"label": "DeepSeek",    "kind": "api",    "metric": "credits",  "default_on": False,
                 "auth": "api_key", "fetch": "providers_api:deepseek_summary", "note": "余额，非 token"},
    "minimax":  {"label": "MiniMax",     "kind": "api",    "metric": "requests", "default_on": False,
                 "auth": "api_key", "fetch": "providers_api:minimax_summary", "note": "次数额度，非 token"},
    "cursor":   {"label": "Cursor",      "kind": "hybrid", "metric": "requests", "default_on": False,
                 "note": "本地登录态，用量在云端（$/credit）"},
    "doubao":   {"label": "豆包 Doubao",  "kind": "api",    "metric": "requests", "default_on": False,
                 "auth": "api_key", "note": "token 需 Volcengine AK/SK 签名"},
    "mimo":     {"label": "MiMo 小米",    "kind": "api",    "metric": "credits",  "default_on": False,
                 "auth": "api_key", "note": "额度（cookie，较脆）"},
}

METRIC_LABEL = {"tokens": "tokens", "credits": "余额", "requests": "次数"}

# env-var fallback per provider (keychain is preferred; never plaintext config)
ENV_KEYS = {"glm": "Z_AI_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
            "minimax": "MINIMAX_API_KEY", "doubao": "ARK_API_KEY", "mimo": "MIMO_API_KEY"}

DEFAULT_ENABLED = [pid for pid, m in REGISTRY.items() if m.get("default_on")]


def all_ids() -> list[str]:
    return list(REGISTRY.keys())


def enabled_ids(config: dict | None = None) -> list[str]:
    """Providers the user has turned on (config.providers.enabled), defaulting to
    claude + codex. Unknown ids are dropped; order follows REGISTRY."""
    config = config or core.load_config()
    p = config.get("providers") if isinstance(config.get("providers"), dict) else {}
    chosen = p.get("enabled")
    if isinstance(chosen, list):
        chosen_set = {c for c in chosen if c in REGISTRY}
        return [pid for pid in REGISTRY if pid in chosen_set] or list(DEFAULT_ENABLED)
    return list(DEFAULT_ENABLED)


def meta(pid: str) -> dict:
    return REGISTRY.get(pid, {"label": pid, "kind": "api", "metric": "tokens"})


def label(pid: str) -> str:
    return meta(pid).get("label", pid)


def kind(pid: str) -> str:
    return meta(pid).get("kind", "api")


def metric(pid: str) -> str:
    return meta(pid).get("metric", "tokens")


def metric_label(pid: str) -> str:
    return METRIC_LABEL.get(metric(pid), metric(pid))


def is_api(pid: str) -> bool:
    return kind(pid) == "api"


def is_token_provider(pid: str) -> bool:
    """Only token-metric providers sum into the burn headline / tier."""
    return metric(pid) == "tokens"


# --------------------------------------------------------------- credentials
# Keychain-first (never plaintext): security CLI. Falls back to env, then config.

def _keychain_get(pid: str) -> str:
    try:
        r = subprocess.run(["security", "find-generic-password", "-a", pid,
                            "-s", f"tokenpulse-{pid}", "-w"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def keychain_set(pid: str, key: str) -> bool:
    """Store/replace an API key in the macOS keychain. Returns success."""
    try:
        r = subprocess.run(["security", "add-generic-password", "-a", pid,
                            "-s", f"tokenpulse-{pid}", "-w", key, "-U"],
                           capture_output=True, timeout=5)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _glm_autodetect() -> str:
    """GLM Coding Plan key = ANTHROPIC_AUTH_TOKEN when the base points at z.ai."""
    base = os.environ.get("ANTHROPIC_BASE_URL", "")
    if any(h in base for h in ("z.ai", "bigmodel")):
        t = os.environ.get("ANTHROPIC_AUTH_TOKEN", "").strip()
        if t:
            return t
    try:
        s = json.load(open(os.path.expanduser("~/.claude/settings.json"), encoding="utf-8"))
        env = s.get("env", {}) if isinstance(s.get("env"), dict) else {}
        if any(h in (env.get("ANTHROPIC_BASE_URL", "") or "") for h in ("z.ai", "bigmodel")):
            return (env.get("ANTHROPIC_AUTH_TOKEN") or "").strip()
    except (OSError, ValueError):
        pass
    return ""


def api_key(pid: str, config: dict | None = None) -> str:
    """Resolve an API provider's key: keychain → env var → config.providers.keys
    → (GLM only) auto-detect from a z.ai ANTHROPIC_AUTH_TOKEN."""
    k = _keychain_get(pid)
    if k:
        return k
    env = os.environ.get(ENV_KEYS.get(pid, ""), "").strip()
    if env:
        return env
    config = config or core.load_config()
    p = config.get("providers") if isinstance(config.get("providers"), dict) else {}
    keys = p.get("keys") if isinstance(p.get("keys"), dict) else {}
    cfgk = (keys.get(pid) or "").strip()
    if cfgk:
        return cfgk
    return _glm_autodetect() if pid == "glm" else ""


def summary(pid: str, now=None, config: dict | None = None):
    """Dispatch to a provider's normalized fetcher; None if it has no fetcher yet."""
    fetch = meta(pid).get("fetch")
    if not fetch:
        return None
    mod, fn = fetch.split(":")
    return getattr(importlib.import_module(mod), fn)(now=now, config=config)


if __name__ == "__main__":
    print("registry:", list(REGISTRY))
    print("default enabled:", DEFAULT_ENABLED)
    print("enabled now:", enabled_ids())
