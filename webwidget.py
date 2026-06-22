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
import share
import webdata

HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "widget.html")
WIDTH = 332
HEIGHT = 300


class Api:
    def __init__(self):
        self.window = None

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
            return json.dumps(badges.card_data(), default=str)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    def share_card(self) -> str:
        """Render the shareable value-card PNG and return a QR share payload."""
        try:
            from datetime import date
            path = card.make_card(date_str=date.today().isoformat())
            payload = share.build_share_payload(path, config=core.load_config())
            return json.dumps({"ok": True, "path": path, **payload})
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
        return json.dumps(configio.save_partial(partial), default=str)

    def fit(self, height) -> bool:
        """Resize the window to the content height the UI measured — so nothing
        (e.g. the '$2,690' cost number) ever gets clipped by a fixed height."""
        try:
            h = max(180, min(900, int(round(float(height)))))
            if self.window is not None:
                self.window.resize(WIDTH, h)
            return True
        except Exception:  # noqa: BLE001
            return False


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
        except Exception:  # noqa: BLE001
            pass
        time.sleep(480)  # ~8 min, under the 10-min in-memory TTL


def _on_start(window):
    threading.Thread(target=_warm_loop, daemon=True).start()


# pywebview's window X maps to this machine's top-right ~(2104) on the main
# display; override via env if you move displays. easy_drag lets you reposition.
def main():
    x = int(os.environ.get("TOKENPULSE_X", 2200))
    y = int(os.environ.get("TOKENPULSE_Y", 48))
    api = Api()
    window = webview.create_window(
        "TokenPulse",
        url=HTML,
        js_api=api,
        width=WIDTH,
        height=HEIGHT,
        x=x,
        y=y,
        frameless=True,
        easy_drag=True,
        on_top=True,
        resizable=True,  # frameless => no visible handles; needed for api.fit()
        background_color="#0e1118",
    )
    api.window = window
    webview.start(_on_start, window)


if __name__ == "__main__":
    main()
