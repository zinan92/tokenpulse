"""Tests for the pywebview host safety shims."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import webwidget  # noqa: E402


def test_menu_bar_title_is_short_and_stateful():
    payload = {
        "combined": {"today": 9_000_000_000, "state": "rocket"},
        "tools": {
            "claude": {"today": 40_443_106, "state": "ontrack"},
            "codex": {"today": 825_620_085, "state": "done"},
        },
    }
    assert webwidget._menu_bar_title(payload) == "⏱ Codex 826M ✓"


def test_menu_actions_use_objective_c_selectors():
    source = open(webwidget.__file__, encoding="utf-8").read()
    assert '"打开 TokenPulse", "toggle:"' in source
    assert '"刷新用量", "refresh:"' in source
    assert '"退出 TokenPulse", "quit:"' in source


def test_widget_exposes_compact_and_menu_bar_display_controls():
    html = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "widget.html"), encoding="utf-8").read()
    assert 'id="compact-line"' in html
    assert 'id="s-display-mode"' in html
    assert 'id="s-display-placement"' in html
    assert 'id="compact-settings"' in html
    assert "openCompactSettings" in html
    assert "overflow-y: auto" in html
    assert 'id="s-save">保存并重启' in html
    assert "restart_widget" in html


def test_display_mode_change_does_not_require_restart(monkeypatch):
    api = webwidget.Api()
    monkeypatch.setattr(webwidget.core, "load_config", lambda: {"display": {"placement": "desktop"}})
    monkeypatch.setattr(webwidget.configio, "save_partial", lambda partial: {"ok": True, "config": partial})

    mode_only = json.loads(api.save_config(json.dumps({"display": {"mode": "full"}})))
    placement_same = json.loads(api.save_config(json.dumps({"display": {"placement": "desktop"}})))
    placement_changed = json.loads(api.save_config(json.dumps({"display": {"placement": "menu_bar"}})))

    assert "restart_required" not in mode_only
    assert "restart_required" not in placement_same
    assert placement_changed["restart_required"] is True


def test_fit_allows_a_one_line_compact_height():
    calls = []

    class FakeWindow:
        def resize(self, width, height):
            calls.append((width, height))

    api = webwidget.Api()
    api.window = FakeWindow()

    assert api.fit(34) is True
    assert calls == [(webwidget.WIDTH, 34)]


def test_restart_widget_acknowledges_before_scheduling_kickstart(monkeypatch):
    commands = []

    class Result:
        returncode = 0

    class ImmediateTimer:
        def __init__(self, _delay, callback):
            self.callback = callback

        def start(self):
            self.callback()

    def fake_run(command, **_kwargs):
        commands.append(command)
        return Result()

    monkeypatch.setattr(webwidget.subprocess, "run", fake_run)
    monkeypatch.setattr(webwidget.threading, "Timer", ImmediateTimer)
    monkeypatch.setattr(webwidget.os, "getuid", lambda: 501)

    result = json.loads(webwidget.Api().restart_widget())

    assert result == {"ok": True, "restarting": True}
    assert commands == [
        ["launchctl", "print", "gui/501/com.tokenpulse.widget"],
        ["launchctl", "kickstart", "-k", "gui/501/com.tokenpulse.widget"],
    ]


def test_restart_widget_reports_missing_launchd_service(monkeypatch):
    class Result:
        returncode = 1

    monkeypatch.setattr(webwidget.subprocess, "run", lambda *_args, **_kwargs: Result())

    result = json.loads(webwidget.Api().restart_widget())

    assert result == {"ok": False, "error": "未找到 TokenPulse 启动服务"}


def test_main_installs_menu_bar_before_starting_gui_loop(monkeypatch):
    captured = {}

    class FakeWindow:
        pass

    class FakeMenu:
        def __init__(self, window):
            captured["menu_window"] = window

        def _install(self):
            captured["menu_installed"] = True

    monkeypatch.setattr(webwidget, "_patch_pywebview_cocoa_screen_guard", lambda: None)
    monkeypatch.setattr(webwidget, "_window_position", lambda: (1, 2))
    monkeypatch.setattr(webwidget.core, "load_config", lambda: {"display": {"placement": "menu_bar"}})
    monkeypatch.setattr(webwidget, "MenuBarController", FakeMenu)
    monkeypatch.setattr(webwidget.webview, "create_window", lambda *args, **kwargs: captured.update(kwargs) or FakeWindow())
    monkeypatch.setattr(webwidget.webview, "start", lambda func, args: captured.update(start=(func, args)))

    webwidget.main()

    assert captured["hidden"] is True
    assert captured["menu_installed"] is True
    assert captured["start"][0] is webwidget._on_start


def test_clamp_window_position_keeps_widget_on_primary_screen():
    assert webwidget._clamp_window_position(2200, 48, screen_size=(2560, 1440)) == (2200, 48)
    assert webwidget._clamp_window_position(9999, 9999, screen_size=(2560, 1440)) == (
        2560 - webwidget.WIDTH,
        1440 - webwidget.HEIGHT,
    )
    assert webwidget._clamp_window_position(-20, -10, screen_size=(2560, 1440)) == (0, 0)


def test_cocoa_screen_guard_skips_move_event_without_screen():
    calls = []

    class FakeScreen:
        pass

    class FakeWindow:
        def __init__(self, screen):
            self._screen = screen

        def screen(self):
            return self._screen

    class FakeNotification:
        def object(self):
            return object()

    class FakeDelegate:
        def windowDidMove_(self, notification):
            calls.append("original")

    class FakeBrowserView:
        WindowDelegate = FakeDelegate
        instance = None

        @classmethod
        def get_instance(cls, _kind, _window):
            return cls.instance

    class FakeCocoa:
        BrowserView = FakeBrowserView

    class FakeInstance:
        def __init__(self, screen):
            self.window = FakeWindow(screen)

    webwidget._patch_pywebview_cocoa_screen_guard(FakeCocoa)
    delegate = FakeDelegate()

    FakeBrowserView.instance = FakeInstance(None)
    assert delegate.windowDidMove_(FakeNotification()) is None
    assert calls == []

    FakeBrowserView.instance = FakeInstance(FakeScreen())
    delegate.windowDidMove_(FakeNotification())
    assert calls == ["original"]


def test_share_card_record_routes_to_record_renderer(monkeypatch, tmp_path):
    api = webwidget.Api()
    out = tmp_path / "record.png"
    captured = {}

    def fake_record_card(date_str=""):
        captured["date_str"] = date_str
        out.write_bytes(b"record")
        return str(out)

    def fake_share_payload(path, config=None, **kwargs):
        captured["path"] = path
        captured["kwargs"] = kwargs
        return {
            "url": "http://127.0.0.1/share/",
            "https": False,
            "qr": "data:image/png;base64,x",
            "share_id": "id",
            "page_dir": str(tmp_path),
            "card": str(out),
            "title": kwargs.get("title"),
            "filename": kwargs.get("filename"),
            "reachable": "local",
            "mode": "local",
        }

    monkeypatch.setattr(webwidget.card, "make_record_card", fake_record_card)
    monkeypatch.setattr(webwidget.card, "make_card", lambda **_: (_ for _ in ()).throw(AssertionError("monthly card used")))
    monkeypatch.setattr(webwidget.core, "load_config", lambda: {"share": {"mode": "local"}})
    monkeypatch.setattr(webwidget.share, "build_share_payload", fake_share_payload)

    result = json.loads(api.share_card("record"))

    assert result["ok"] is True
    assert result["kind"] == "record"
    assert result["path"] == str(out)
    assert captured["path"] == str(out)
    assert captured["kwargs"]["title"] == "TokenPulse 单日纪录卡"
    assert captured["kwargs"]["filename"] == "tokenpulse-record-card.png"


def test_ranking_top_merges_top_and_me(monkeypatch):
    import ranking
    monkeypatch.setattr(webwidget.core, "load_config",
                        lambda: {"handle": "burner", "ranking": {"enabled": True, "url": "https://r.dev"}})
    monkeypatch.setattr(ranking, "top", lambda n=10, config=None: {"rows": [{"handle": "burner"}], "total": 1})
    monkeypatch.setattr(ranking, "me", lambda h, config=None: {"found": True, "handle": h, "rank": 1})

    api = webwidget.Api()
    out = json.loads(api.ranking_top())

    assert out["handle"] == "burner"
    assert out["me"]["rank"] == 1
    assert out["top"]["total"] == 1


def test_ranking_top_uses_ttl_cache(monkeypatch):
    import ranking
    calls = {"top": 0}
    monkeypatch.setattr(webwidget.core, "load_config",
                        lambda: {"handle": "burner", "ranking": {"enabled": True, "url": "https://r.dev"}})

    def counting_top(n=10, config=None):
        calls["top"] += 1
        return {"rows": [], "total": 0}

    monkeypatch.setattr(ranking, "top", counting_top)
    monkeypatch.setattr(ranking, "me", lambda h, config=None: {"found": False})

    api = webwidget.Api()
    api.ranking_top()
    api.ranking_top()  # second call must be served from the 5-min cache

    assert calls["top"] == 1


def test_ranking_submit_now_pushes_and_clears_cache(monkeypatch):
    """The consent-time immediate submit reports success and drops the rank cache
    so the next ranking_top() refetches the freshly-submitted standing."""
    import time as _time
    monkeypatch.setattr(webwidget, "_submit_ranking", lambda *a, **k: {"ok": True, "rank": 2})
    api = webwidget.Api()
    api._rank_cache = (_time.time(), '{"stale": true}')

    out = json.loads(api.ranking_submit_now())

    assert out["ok"] is True and out["result"]["rank"] == 2
    assert api._rank_cache is None   # forces a refetch on the next ranking_top()


def test_ranking_submit_now_when_disabled_returns_not_ok(monkeypatch):
    monkeypatch.setattr(webwidget, "_submit_ranking", lambda *a, **k: None)  # disabled / no url
    out = json.loads(webwidget.Api().ranking_submit_now())
    assert out["ok"] is False


def test_share_card_monthly_default_route(monkeypatch, tmp_path):
    """The default (monthly) path — what celebrateHatch auto-fires and the share
    button uses — must render the monthly card with no record-only copy."""
    api = webwidget.Api()
    out = tmp_path / "monthly.png"
    captured = {}

    def fake_make_card(date_str=""):
        captured["date_str"] = date_str
        out.write_bytes(b"monthly")
        return str(out)

    def fake_share_payload(path, config=None, **kwargs):
        captured["path"] = path
        captured["kwargs"] = kwargs
        return {"url": "http://127.0.0.1/share/", "https": False, "qr": "x",
                "share_id": "id", "page_dir": str(tmp_path), "card": str(out),
                "reachable": "local", "mode": "local"}

    monkeypatch.setattr(webwidget.card, "make_card", fake_make_card)
    monkeypatch.setattr(webwidget.card, "make_record_card",
                        lambda **_: (_ for _ in ()).throw(AssertionError("record card used")))
    monkeypatch.setattr(webwidget.core, "load_config", lambda: {"share": {"mode": "local"}})
    monkeypatch.setattr(webwidget.share, "build_share_payload", fake_share_payload)

    result = json.loads(api.share_card())  # default kind == monthly

    assert result["ok"] is True
    assert result["kind"] == "monthly"
    assert result["path"] == str(out)
    assert captured["date_str"]  # today's date threaded through
    # monthly path must NOT pass the record-only copy kwargs
    assert "title" not in captured["kwargs"] and "filename" not in captured["kwargs"]


def test_ranking_top_survives_unreachable_server(monkeypatch):
    """When the ranking server is down, ranking.top/me return None — ranking_top
    must still return valid JSON (no error) so the UI just hides the rank line."""
    import ranking
    monkeypatch.setattr(webwidget.core, "load_config",
                        lambda: {"handle": "burner", "ranking": {"enabled": True, "url": "https://r.dev"}})
    monkeypatch.setattr(ranking, "top", lambda n=10, config=None: None)
    monkeypatch.setattr(ranking, "me", lambda h, config=None: None)

    out = json.loads(webwidget.Api().ranking_top())

    assert "error" not in out
    assert out["top"] is None and out["me"] is None


# ── _submit_ranking helper (the warm-loop ranking push) ──

def _patch_badges(monkeypatch, data):
    import badges
    monkeypatch.setattr(badges, "card_data", lambda *a, **k: data)


def test_submit_ranking_disabled_returns_none(monkeypatch):
    import ranking
    monkeypatch.setattr(ranking, "submit", lambda *a, **k: (_ for _ in ()).throw(AssertionError("submitted")))
    assert webwidget._submit_ranking({"ranking": {"enabled": False, "url": "https://r.dev"}}) is None


def test_submit_ranking_no_url_returns_none(monkeypatch):
    import ranking
    monkeypatch.setattr(ranking, "submit", lambda *a, **k: (_ for _ in ()).throw(AssertionError("submitted")))
    assert webwidget._submit_ranking({"ranking": {"enabled": True, "url": ""}}) is None


def test_submit_ranking_enabled_pushes_burn(monkeypatch):
    import ranking
    captured = {}
    _patch_badges(monkeypatch, {"monthly_tokens": 5_000_000, "lifetime": {"lifetime_tokens": 9_000_000}})
    monkeypatch.setattr(ranking, "submit", lambda tokens_30d, tokens_lifetime, config=None: captured.update(
        t30=tokens_30d, tlt=tokens_lifetime) or {"ok": True, "rank": 1})
    res = webwidget._submit_ranking({"ranking": {"enabled": True, "url": "https://r.dev"}})
    assert res == {"ok": True, "rank": 1}
    assert captured == {"t30": 5_000_000, "tlt": 9_000_000}


def test_submit_ranking_tolerates_missing_badge_keys(monkeypatch):
    import ranking
    captured = {}
    _patch_badges(monkeypatch, {})  # no monthly_tokens, no lifetime
    monkeypatch.setattr(ranking, "submit", lambda tokens_30d, tokens_lifetime, config=None: captured.update(
        t30=tokens_30d, tlt=tokens_lifetime) or {"ok": True})
    webwidget._submit_ranking({"ranking": {"enabled": True, "url": "https://r.dev"}})
    assert captured == {"t30": 0, "tlt": 0}  # submits zeros, never crashes


def test_submit_ranking_tolerates_malformed_lifetime(monkeypatch):
    import ranking
    captured = {}
    _patch_badges(monkeypatch, {"monthly_tokens": 7, "lifetime": "oops-not-a-dict"})
    monkeypatch.setattr(ranking, "submit", lambda tokens_30d, tokens_lifetime, config=None: captured.update(
        t30=tokens_30d, tlt=tokens_lifetime) or {"ok": True})
    webwidget._submit_ranking({"ranking": {"enabled": True, "url": "https://r.dev"}})
    assert captured == {"t30": 7, "tlt": 0}  # malformed lifetime -> 0, no AttributeError
