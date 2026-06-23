"""Tests for the provider registry + enabled-set resolution."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import providers  # noqa: E402
import configio  # noqa: E402


def test_default_enabled_is_claude_codex():
    assert providers.enabled_ids({}) == ["claude", "codex"]
    assert providers.DEFAULT_ENABLED == ["claude", "codex"]


def test_enabled_honors_config_and_drops_unknown():
    cfg = {"providers": {"enabled": ["codex", "glm", "bogus"]}}
    got = providers.enabled_ids(cfg)
    assert got == ["codex", "glm"]            # known kept, order = REGISTRY, unknown dropped


def test_empty_enabled_falls_back_to_default():
    assert providers.enabled_ids({"providers": {"enabled": []}}) == ["claude", "codex"]


def test_metric_kind_and_api():
    assert providers.metric("cursor") == "requests"   # request-based, flagged
    assert providers.metric("glm") == "tokens"
    assert providers.kind("claude") == "local"
    assert providers.is_api("glm") and not providers.is_api("codex")


def test_is_token_provider_gates_the_headline():
    assert providers.is_token_provider("glm") and providers.is_token_provider("claude")
    assert not providers.is_token_provider("deepseek")   # credits, not tokens
    assert not providers.is_token_provider("minimax")    # requests, not tokens
    assert providers.metric_label("deepseek") == "余额"


def test_api_key_resolution_order(monkeypatch):
    # hermetic: no keychain item, no env vars → falls through to config
    monkeypatch.setattr(providers, "_keychain_get", lambda pid: "")
    for v in providers.ENV_KEYS.values():
        monkeypatch.delenv(v, raising=False)
    cfg = {"providers": {"keys": {"glm": "  abc.def  "}}}
    assert providers.api_key("glm", cfg) == "abc.def"    # config, trimmed
    assert providers.api_key("deepseek", cfg) == ""
    # keychain wins over config
    monkeypatch.setattr(providers, "_keychain_get", lambda pid: "kc-key" if pid == "glm" else "")
    assert providers.api_key("glm", cfg) == "kc-key"


def test_summary_dispatch_routes_to_fetcher(monkeypatch):
    import providers_api
    monkeypatch.setattr(providers_api, "glm_summary", lambda now=None, config=None: {"available": True, "metric": "tokens"})
    assert providers.summary("glm")["available"] is True
    assert providers.summary("claude") is None           # local providers have no api fetcher


def test_configio_validates_providers():
    assert configio.validate_partial({"providers": {"enabled": ["claude", "glm"]}}) == []
    assert "providers.enabled" in configio.validate_partial({"providers": {"enabled": "claude"}})
    assert "providers.keys" in configio.validate_partial({"providers": {"keys": {"glm": 123}}})
    assert "providers" in configio.validate_partial({"providers": "nope"})
