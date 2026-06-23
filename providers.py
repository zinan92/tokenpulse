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

import core

# id -> metadata. metric="tokens" unless the vendor only exposes requests/credits.
REGISTRY: dict[str, dict] = {
    "claude":   {"label": "Claude Code", "kind": "local", "metric": "tokens",   "default_on": True},
    "codex":    {"label": "Codex",       "kind": "local", "metric": "tokens",   "default_on": True},
    "cursor":   {"label": "Cursor",      "kind": "local", "metric": "requests", "default_on": False},
    "glm":      {"label": "GLM 智谱",     "kind": "api",   "metric": "tokens",   "default_on": False, "auth": "api_key"},
    "deepseek": {"label": "DeepSeek",    "kind": "api",   "metric": "tokens",   "default_on": False, "auth": "api_key"},
    "doubao":   {"label": "豆包 Doubao",  "kind": "api",   "metric": "tokens",   "default_on": False, "auth": "api_key"},
    "minimax":  {"label": "MiniMax",     "kind": "api",   "metric": "tokens",   "default_on": False, "auth": "api_key"},
    "mimo":     {"label": "MiMo 小米",    "kind": "api",   "metric": "tokens",   "default_on": False, "auth": "api_key"},
}

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


def is_api(pid: str) -> bool:
    return kind(pid) == "api"


def api_key(pid: str, config: dict | None = None) -> str:
    """The user's stored key for an API provider (config.providers.keys.<pid>)."""
    config = config or core.load_config()
    p = config.get("providers") if isinstance(config.get("providers"), dict) else {}
    keys = p.get("keys") if isinstance(p.get("keys"), dict) else {}
    return (keys.get(pid) or "").strip()


if __name__ == "__main__":
    print("registry:", list(REGISTRY))
    print("default enabled:", DEFAULT_ENABLED)
    print("enabled now:", enabled_ids())
