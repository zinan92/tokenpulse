"""TokenPulse web widget host — a frameless, always-on-top webview running the
impeccable-designed goad UI (web/widget.html).

The HTML calls back through `window.pywebview.api.core()` / `.cost()`; this host
returns the merged payloads from webdata.py. The heavy 30-day cost scan stays in
its own (TTL-cached) call so the goad state paints instantly.

Run: python3 webwidget.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time

import webview

import subprocess

import badges
import card
import configio
import core
import continuity
import cost
import history
import lifetime
import providers
import share
import webdata

HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "widget.html")
WIDTH = 332
HEIGHT = 300
DEFAULT_X = 2200
DEFAULT_Y = 48


class Api:
    def __init__(self):
        self.window = None
        self.menu_controller = None
        self._rank_cache: tuple[float, str] | None = None

    def core(self) -> str:
        try:
            return json.dumps(webdata.core_payload(), default=str)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    def cost(self) -> str:
        try:
            return json.dumps(webdata.cost_payload(), default=str)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    def panel(self) -> str:
        try:
            return json.dumps(webdata.panel_payload(), default=str)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    def badges(self) -> str:
        try:
            import moments
            d = badges.card_data()
            try:
                d["moments"] = moments.check(d)   # proud crossings since last open → share nudge
            except Exception:  # noqa: BLE001
                d["moments"] = []
            return json.dumps(d, default=str)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    def share_card(self, kind: str = "monthly") -> str:
        """Render a shareable card PNG and return a QR share payload."""
        try:
            from datetime import date
            cfg = core.load_config()
            today = date.today().isoformat()
            card_kind = (kind or "monthly").strip().lower()
            if card_kind in {"record", "daily", "day", "daily-record", "daily_record"}:
                path = card.make_record_card(date_str=today)
                payload = share.build_share_payload(
                    path,
                    config=cfg,
                    title="TokenPulse 单日纪录卡",
                    share_text="我刷新了 TokenPulse 单日 token 纪录。",
                    body_text="先分享单日纪录图片；如果系统不支持文件分享，就保存图片后打开目标平台发布。",
                    filename="tokenpulse-record-card.png",
                )
                return json.dumps({"ok": True, "kind": "record", "path": path, **payload})
            path = card.make_card(date_str=today)
            payload = share.build_share_payload(path, config=cfg)
            return json.dumps({"ok": True, "kind": "monthly", "path": path, **payload})
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"ok": False, "error": str(exc)})

    def open_url(self, url: str) -> bool:
        try:
            subprocess.Popen(["open", url])
            return True
        except Exception:  # noqa: BLE001
            return False

    def reveal_path(self, path: str) -> bool:
        try:
            subprocess.Popen(["open", "-R", path])
            return True
        except Exception:  # noqa: BLE001
            return False

    def config(self) -> str:
        try:
            return json.dumps(configio.editable_config(), default=str)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    def save_config(self, partial_str: str) -> str:
        try:
            partial = json.loads(partial_str)
        except (ValueError, TypeError):
            return json.dumps({"ok": False, "errors": ["bad json"]})
        # config.json is re-read on every tick, so the change applies on the next
        # refresh; nothing to invalidate here.
        previous_display = core.load_config().get("display") or {}
        result = configio.save_partial(partial)
        requested_display = partial.get("display") if isinstance(partial.get("display"), dict) else {}
        if (result.get("ok") and "placement" in requested_display
                and requested_display["placement"] != previous_display.get("placement", "desktop")):
            # pywebview API calls run off Cocoa's main thread.  Persist the
            # placement safely now; the next app launch creates/removes the
            # native status item on the correct thread.
            result["restart_required"] = True
        return json.dumps(result, default=str)

    def providers_catalog(self) -> str:
        """All providers + the enabled set + whether each api provider has a key
        (the key value itself is never returned)."""
        try:
            cfg = core.load_config()
            enabled = providers.enabled_ids(cfg)
            out = []
            for pid in providers.all_ids():
                m = providers.meta(pid)
                out.append({
                    "id": pid, "label": m.get("label", pid), "kind": m.get("kind"),
                    "metric": providers.metric(pid), "metric_label": providers.metric_label(pid),
                    "note": m.get("note", ""), "needs_key": providers.is_api(pid),
                    "enabled": pid in enabled,
                    "has_key": bool(providers.api_key(pid, cfg)) if providers.is_api(pid) else None,
                })
            return json.dumps({"providers": out, "enabled": enabled}, default=str)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    def save_providers(self, enabled_str: str, keys_str: str) -> str:
        """Save the enabled set to config.json and any new api keys to the Keychain."""
        try:
            enabled = json.loads(enabled_str) if enabled_str else []
            keys = json.loads(keys_str) if keys_str else {}
        except (ValueError, TypeError):
            return json.dumps({"ok": False, "errors": ["bad json"]})
        for pid, val in (keys or {}).items():
            v = (val or "").strip()
            if v and pid in providers.REGISTRY:
                providers.keychain_set(pid, v)   # keys -> keychain, never config
        res = configio.save_partial({"providers": {"enabled": list(enabled)}})
        return json.dumps(res, default=str)

    def provider_status(self, pid: str) -> str:
        """Live-fetch one api provider's status (a 'test this key' button)."""
        try:
            s = providers.summary(pid, config=core.load_config())
            return json.dumps(s or {"available": False, "reason": "no-fetcher"}, default=str)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"available": False, "reason": str(exc)})

    def provider_statuses(self) -> str:
        """Cached live status of every enabled api provider — for the panel."""
        try:
            import providers_api
            return json.dumps({"providers": providers_api.enabled_statuses(core.load_config())}, default=str)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    def ranking_submit_now(self) -> str:
        """Push to the board immediately (called right after the user consents in
        settings) and drop the cache so the rank line reflects it at once."""
        try:
            res = _submit_ranking()
            self._rank_cache = None
            return json.dumps({"ok": bool(res), "result": res}, default=str)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"ok": False, "error": str(exc)})

    def ranking_top(self) -> str:
        """Top-10 global ranking + current user's position (TTL-cached 5 min)."""
        import time as _time
        if self._rank_cache:
            ts, data = self._rank_cache
            if _time.time() - ts < 300:
                return data
        try:
            import ranking
            cfg = core.load_config()
            handle = (cfg.get("handle") or "").strip()
            top_data = ranking.top(n=10, config=cfg)
            me_data = ranking.me(handle, config=cfg) if handle else None
            result = json.dumps({"top": top_data, "me": me_data, "handle": handle}, default=str)
            self._rank_cache = (_time.time(), result)
            return result
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    def fit(self, height) -> bool:
        """Resize the window to the content height the UI measured — so nothing
        (e.g. the '$2,690' cost number) ever gets clipped by a fixed height."""
        try:
            # Compact mode measures to one short row.  Do not retain the
            # legacy full-card minimum here, or the widget looks compact while
            # still reserving a large empty rectangle on the desktop.
            h = max(34, min(900, int(round(float(height)))))
            if self.window is not None:
                self.window.resize(WIDTH, h)
            return True
        except Exception:  # noqa: BLE001
            return False


def _submit_ranking(config=None) -> dict | None:
    """Push today's monthly + lifetime burn to the global ranking server, IF the
    user enabled it. Returns the server reply, or None when disabled / no url /
    on any failure. Pulled out of the warm loop so it's unit-testable."""
    import ranking
    import badges
    cfg = config or core.load_config()
    r = cfg.get("ranking") if isinstance(cfg.get("ranking"), dict) else {}
    if not (r.get("enabled") and r.get("url")):
        return None
    bd = badges.card_data()
    life = bd.get("lifetime") if isinstance(bd.get("lifetime"), dict) else {}
    return ranking.submit(
        tokens_30d=int(bd.get("monthly_tokens") or 0),
        tokens_lifetime=int(life.get("lifetime_tokens") or 0),
        config=cfg,
    )


def _warm_loop():
    """Keep the heavy 30-day panel scan (and cost) pre-cached in the background
    so opening the detail panel is instant, not a 14s wait."""
    time.sleep(25)  # let the first paint (core/cost/limits) finish uncontended
    try:
        lifetime.ensure_backfill()    # one-time full-log scan for the lifetime trophy
        continuity.ensure_backfill()  # one-time scan for the longest-run record
    except Exception:  # noqa: BLE001
        pass
    while True:
        try:
            history.panel_data(ttl=0)          # panel + egg/badges (share card)
            history.daily_tokens(days=120)     # 120d series for velocity badges + best-30d
            history.daily_active_minutes(days=120)  # merged active-minutes cache (marathon)
            cost.usage_summary("claude", ttl=0)  # keep cost warm so badges is instant
            cost.usage_summary("codex", ttl=0)
            lifetime.update(refresh_peak=True)  # daily increment + peak-session refresh
            continuity.update()                 # cheap fold of settled days
            try:
                _submit_ranking()               # push to the global leaderboard if enabled
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass
        time.sleep(480)  # ~8 min, under the 10-min in-memory TTL


def _menu_bar_title(payload: dict) -> str:
    """Short, glanceable native menu-bar text; safe to exercise without AppKit."""
    combined = payload.get("combined") if isinstance(payload, dict) else {}
    today = int((combined or {}).get("today") or 0)
    state = (combined or {}).get("state") or "ontrack"
    mark = {"behind": "↓", "early": "·", "ahead": "↑", "done": "✓", "rocket": "✦"}.get(state, "·")
    return f"⏱ {cost.humanize_tokens(today)} {mark}"


class MenuBarController:
    """Native macOS status item, created only when the user opts into it."""
    def __init__(self, window):
        self.window = window
        self.item = None
        self.button = None
        self.timer = None
        self.visible = False

    def _menu_item(self, title: str, action: str):
        from AppKit import NSMenuItem

        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
        item.setTarget_(self)
        return item

    def _install(self) -> None:
        if self.item is not None:
            return
        from AppKit import NSMenu, NSMenuItem, NSStatusBar, NSTimer, NSVariableStatusItemLength

        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.button = self.item.button()
        menu = NSMenu.alloc().init()
        menu.addItem_(self._menu_item("打开 TokenPulse", "toggle_"))
        menu.addItem_(self._menu_item("刷新用量", "refresh_"))
        menu.addItem_(NSMenuItem.separatorItem())
        menu.addItem_(self._menu_item("退出 TokenPulse", "quit_"))
        self.item.setMenu_(menu)
        self.refresh_(None)
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            60.0, self, "refresh:", None, True
        )

    def toggle_(self, _sender) -> None:
        if self.visible:
            self.window.hide()
        else:
            self.window.show()
        self.visible = not self.visible

    def refresh_(self, _sender) -> None:
        try:
            import codexbar

            codexbar.clear_cache()
            payload = webdata.core_payload()
            if self.button is not None:
                self.button.setTitle_(_menu_bar_title(payload))
        except Exception:  # noqa: BLE001
            if self.button is not None:
                self.button.setTitle_("⏱ —")

    def quit_(self, _sender) -> None:
        try:
            self.window.destroy()
        finally:
            from AppKit import NSApp

            NSApp.terminate_(None)


def _on_start(window, api):
    threading.Thread(target=_warm_loop, daemon=True).start()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _main_screen_size():
    try:
        import AppKit
        screen = AppKit.NSScreen.mainScreen()
        if screen is None:
            return None
        frame = screen.frame()
        return int(frame.size.width), int(frame.size.height)
    except Exception:  # noqa: BLE001
        return None


def _clamp_window_position(x: int, y: int, width: int = WIDTH, height: int = HEIGHT,
                           screen_size=None) -> tuple[int, int]:
    if screen_size is None:
        screen_size = _main_screen_size()
    if not screen_size:
        return x, y
    screen_width, screen_height = screen_size
    max_x = max(0, int(screen_width) - width)
    max_y = max(0, int(screen_height) - height)
    return max(0, min(x, max_x)), max(0, min(y, max_y))


def _window_position() -> tuple[int, int]:
    return _clamp_window_position(
        _env_int("TOKENPULSE_X", DEFAULT_X),
        _env_int("TOKENPULSE_Y", DEFAULT_Y),
    )


def _patch_pywebview_cocoa_screen_guard(cocoa_module=None) -> None:
    """pywebview 6.2.x can emit windowDidMove before NSWindow has a screen."""
    if cocoa_module is None:
        if sys.platform != "darwin":
            return
        try:
            from webview.platforms import cocoa as cocoa_module
        except Exception:  # noqa: BLE001
            return

    delegate = cocoa_module.BrowserView.WindowDelegate
    if getattr(delegate, "_tokenpulse_screen_guard", False):
        return
    original = delegate.windowDidMove_

    def windowDidMove_(self, notification):
        try:
            instance = cocoa_module.BrowserView.get_instance("window", notification.object())
            if instance is not None and instance.window.screen() is None:
                return None
        except Exception:  # noqa: BLE001
            return None
        return original(self, notification)

    delegate.windowDidMove_ = windowDidMove_
    delegate._tokenpulse_screen_guard = True


# pywebview's window X maps to this machine's top-right ~(2104) on the main
# display; override via env if you move displays. easy_drag lets you reposition.
def main():
    _patch_pywebview_cocoa_screen_guard()
    x, y = _window_position()
    api = Api()
    display = core.load_config().get("display") or {}
    menu_bar = display.get("placement", "desktop") == "menu_bar"
    window = webview.create_window(
        "TokenPulse",
        url=HTML,
        js_api=api,
        width=WIDTH,
        height=HEIGHT,
        x=x,
        y=y,
        hidden=menu_bar,
        frameless=True,
        easy_drag=True,
        on_top=True,
        resizable=True,  # frameless => no visible handles; needed for api.fit()
        background_color="#0e1118",
    )
    api.window = window
    # This runs on Python's main thread before pywebview starts its worker
    # callback, which is the safe point for native status-item creation.
    api.menu_controller = MenuBarController(window)
    if menu_bar:
        api.menu_controller._install()
    webview.start(_on_start, (window, api))


if __name__ == "__main__":
    main()
