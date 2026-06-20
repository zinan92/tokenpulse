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

import webview

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


def _on_start(window):
    pass  # position is set at create time; easy_drag handles repositioning


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
