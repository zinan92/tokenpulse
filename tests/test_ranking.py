"""Tests for the global-ranking client (HTTP mocked — no network)."""
import io
import json
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ranking  # noqa: E402

CFG = {"handle": "burner", "ranking": {"enabled": True, "url": "https://rank.example.dev"}}


class _FakeResp(io.BytesIO):
    """Minimal context-manager stand-in for urllib's response object."""
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def _mock_urlopen(monkeypatch, payload=None, captured=None, exc=None):
    def fake(req, timeout=None):
        if captured is not None:
            captured["url"] = req.full_url
            captured["method"] = req.get_method()
            captured["body"] = req.data
            captured["ua"] = req.get_header("User-agent")
        if exc is not None:
            raise exc
        return _FakeResp(json.dumps(payload).encode())
    monkeypatch.setattr(ranking.urllib.request, "urlopen", fake)


# ── submit ────────────────────────────────────────────────────────────────

def test_submit_disabled_returns_none(monkeypatch):
    _mock_urlopen(monkeypatch, payload={"ok": True})  # must never be called
    cfg = {"handle": "x", "ranking": {"enabled": False, "url": "https://r.dev"}}
    assert ranking.submit(1, 2, config=cfg) is None


def test_submit_no_url_returns_none():
    cfg = {"handle": "x", "ranking": {"enabled": True, "url": ""}}
    assert ranking.submit(1, 2, config=cfg) is None


def test_submit_no_handle_returns_none(monkeypatch):
    _mock_urlopen(monkeypatch, payload={"ok": True})
    cfg = {"handle": "  ", "ranking": {"enabled": True, "url": "https://r.dev"}}
    assert ranking.submit(1, 2, config=cfg) is None


def test_submit_posts_handle_and_returns_rank(monkeypatch):
    captured = {}
    _mock_urlopen(monkeypatch, payload={"ok": True, "rank": 3}, captured=captured)
    out = ranking.submit(123, 456, config=CFG)
    assert out == {"ok": True, "rank": 3}
    assert captured["method"] == "POST"
    assert captured["url"] == "https://rank.example.dev/rank/submit"
    body = json.loads(captured["body"])
    assert body == {"handle": "burner", "tokens_30d": 123, "tokens_lifetime": 456}
    # Cloudflare 403s the default Python-urllib UA — an explicit UA is mandatory.
    assert captured["ua"] and "Python-urllib" not in captured["ua"]


def test_top_sends_custom_user_agent(monkeypatch):
    captured = {}
    _mock_urlopen(monkeypatch, payload={"rows": [], "total": 0}, captured=captured)
    ranking.top(config=CFG)
    assert captured["ua"] and "Python-urllib" not in captured["ua"]


def test_submit_swallows_network_error(monkeypatch):
    _mock_urlopen(monkeypatch, exc=urllib.error.URLError("down"))
    assert ranking.submit(1, 2, config=CFG) is None


# ── top / me ────────────────────────────────────────────────────────────────

def test_top_returns_rows(monkeypatch):
    captured = {}
    rows = {"rows": [{"handle": "a", "tokens_30d": 9, "rank": 1}], "total": 1}
    _mock_urlopen(monkeypatch, payload=rows, captured=captured)
    out = ranking.top(n=5, config=CFG)
    assert out["total"] == 1 and out["rows"][0]["handle"] == "a"
    assert "n=5" in captured["url"]


def test_top_no_url_returns_none():
    assert ranking.top(config={"ranking": {"url": ""}}) is None


def test_top_swallows_network_error(monkeypatch):
    _mock_urlopen(monkeypatch, exc=urllib.error.URLError("down"))
    assert ranking.top(config=CFG) is None


def test_me_returns_rank(monkeypatch):
    _mock_urlopen(monkeypatch, payload={"found": True, "handle": "burner", "rank": 7})
    out = ranking.me("burner", config=CFG)
    assert out["found"] and out["rank"] == 7


def test_me_empty_handle_returns_none():
    assert ranking.me("", config=CFG) is None


def test_me_swallows_error(monkeypatch):
    _mock_urlopen(monkeypatch, exc=TimeoutError("slow"))
    assert ranking.me("burner", config=CFG) is None
