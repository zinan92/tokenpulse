"""Tests for cloud-provider fetchers (HTTP mocked — no network)."""
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import providers       # noqa: E402
import providers_api   # noqa: E402


def test_glm_parses_token_window(monkeypatch):
    monkeypatch.setattr(providers, "api_key", lambda pid, config=None: "k")
    monkeypatch.setattr(providers_api, "_get", lambda url, headers, timeout=8: {
        "data": {"planName": "GLM Coding Pro", "limits": [
            {"type": "REQUESTS_LIMIT", "used": 3, "limit": 100},
            {"type": "TOKENS_LIMIT", "used": 1200000, "limit": 5000000, "nextResetTime": 1782000000000}]}})
    out = providers_api.glm_summary(config={})
    assert out["available"] and out["metric"] == "tokens"
    assert out["tokens_today"] == 1200000
    assert out["display"]["limit"] == 5000000 and out["display"]["percent"] == 24.0
    assert out["display"]["plan"] == "GLM Coding Pro" and out["display"]["reset_at"]


def test_glm_no_key_unavailable(monkeypatch):
    monkeypatch.setattr(providers, "api_key", lambda pid, config=None: "")
    out = providers_api.glm_summary(config={})
    assert out["available"] is False and out["reason"] == "no-key"


def test_glm_401_retries_without_bearer(monkeypatch):
    monkeypatch.setattr(providers, "api_key", lambda pid, config=None: "k")
    seen = []

    def fake_get(url, headers, timeout=8):
        seen.append(headers["Authorization"])
        if headers["Authorization"].startswith("Bearer "):
            raise urllib.error.HTTPError(url, 401, "unauth", {}, None)
        return {"data": {"limits": [{"type": "TOKENS_LIMIT", "used": 1, "limit": 2, "nextResetTime": 0}]}}

    monkeypatch.setattr(providers_api, "_get", fake_get)
    out = providers_api.glm_summary(config={})
    assert out["available"] and seen == ["Bearer k", "k"]   # retried raw key on 401


def test_deepseek_balance_is_credits(monkeypatch):
    monkeypatch.setattr(providers, "api_key", lambda pid, config=None: "k")
    monkeypatch.setattr(providers_api, "_get", lambda url, headers, timeout=8: {
        "is_available": True, "balance_infos": [
            {"currency": "CNY", "total_balance": "110.00", "granted_balance": "10.00", "topped_up_balance": "100.00"}]})
    out = providers_api.deepseek_summary(config={})
    assert out["available"] and out["metric"] == "credits"
    assert out["display"]["total"] == "110.00" and out["display"]["currency"] == "CNY"
    assert out["tokens_30d"] == 0   # never contributes to the token headline


def test_unreachable_is_graceful(monkeypatch):
    monkeypatch.setattr(providers, "api_key", lambda pid, config=None: "k")

    def boom(url, headers, timeout=8):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(providers_api, "_get", boom)
    out = providers_api.glm_summary(config={})
    assert out["available"] is False and out["reason"] == "unreachable"


def test_enabled_statuses_only_api_and_caches(monkeypatch):
    monkeypatch.setattr(providers_api, "_CACHE", {})
    monkeypatch.setattr(providers, "enabled_ids", lambda config=None: ["claude", "glm", "deepseek"])
    calls = {"n": 0}

    def fake_summary(pid, now=None, config=None):
        calls["n"] += 1
        return {"available": True, "metric": providers.metric(pid), "display": {"x": pid}}

    monkeypatch.setattr(providers, "summary", fake_summary)
    st = providers_api.enabled_statuses({})
    ids = [s["id"] for s in st]
    assert ids == ["glm", "deepseek"]            # claude (local) excluded
    assert st[0]["metric"] == "tokens" and st[1]["metric"] == "credits"
    n1 = calls["n"]
    providers_api.enabled_statuses({})           # second call served from cache
    assert calls["n"] == n1
