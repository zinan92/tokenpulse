"""TokenPulse desktop widget — a lightweight always-on-top quota coach.

Pure-stdlib Tkinter (no Chromium, ~30-50MB resident). Frameless, pinned to the
top-right of the desktop as a constant reminder: how far each plan is from its
daily token target, and one recent session to jump back into.

Refresh runs in a worker thread so the file scan never freezes the UI.

Run:  python3 widget.py
Quit: press Esc, or right-click -> Quit. Drag anywhere to move.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from datetime import datetime

import core
import limits
import sessions

# ----------------------------------------------------------------- appearance

BG = "#0d1117"
CARD = "#161b22"
FG = "#e6edf3"
MUTED = "#8b949e"
TRACK = "#21262d"

MOOD = {
    "behind": ("#f85149", "😴"),
    "ontrack": ("#d29922", "🙂"),
    "ahead": ("#3fb950", "🔥"),
    "done": ("#2ea043", "✅"),
    "rocket": ("#a371f7", "🚀"),
}
TOOL_LABEL = {"claude": "Claude", "codex": "Codex "}
REFRESH_MS_DEFAULT = 180_000  # 3 min


class TokenPulseWidget:
    def __init__(self, config: dict):
        self.config = config
        self.refresh_ms = int(config.get("widget", {}).get("refresh_seconds", 180) * 1000) or REFRESH_MS_DEFAULT
        self.results: "queue.Queue[tuple]" = queue.Queue()
        self._drag = (0, 0)

        self.root = tk.Tk()
        self.root.title("TokenPulse")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", 0.96)
        except tk.TclError:
            pass
        self.root.configure(bg=BG)

        self.frame = tk.Frame(self.root, bg=BG, padx=12, pady=10)
        self.frame.pack(fill="both", expand=True)

        header = tk.Frame(self.frame, bg=BG)
        header.pack(fill="x")
        tk.Label(header, text="⏱ TokenPulse", bg=BG, fg=FG,
                 font=("Menlo", 12, "bold")).pack(side="left")
        self.combined_lbl = tk.Label(header, text="", bg=BG, fg=MUTED, font=("Menlo", 10))
        self.combined_lbl.pack(side="right")

        self.bars: dict[str, dict] = {}
        for tool in ("claude", "codex"):
            self.bars[tool] = self._make_bar(tool)

        self.suggest_lbl = tk.Label(self.frame, text="", bg=BG, fg=MUTED,
                                    font=("Menlo", 9), justify="left", anchor="w",
                                    wraplength=260)
        self.suggest_lbl.pack(fill="x", pady=(8, 0))
        self.updated_lbl = tk.Label(self.frame, text="", bg=BG, fg="#484f58",
                                    font=("Menlo", 8), anchor="w")
        self.updated_lbl.pack(fill="x")

        # interactions
        for w in (self.root, self.frame, header):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.root.bind("<Button-3>", self._menu)
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Refresh now", command=self.kick_refresh)
        self.menu.add_command(label="Quit", command=self.root.destroy)

        self._place_top_right()
        self.kick_refresh()
        self.root.after(200, self._poll_results)

    # ---------------------------------------------------------------- widgets
    def _make_bar(self, tool: str) -> dict:
        card = tk.Frame(self.frame, bg=BG)
        card.pack(fill="x", pady=(8, 0))
        top = tk.Frame(card, bg=BG)
        top.pack(fill="x")
        name = tk.Label(top, text=TOOL_LABEL[tool], bg=BG, fg=FG, font=("Menlo", 10, "bold"))
        name.pack(side="left")
        amount = tk.Label(top, text="…", bg=BG, fg=MUTED, font=("Menlo", 10))
        amount.pack(side="right")
        canvas = tk.Canvas(card, height=14, bg=TRACK, highlightthickness=0)
        canvas.pack(fill="x", pady=(3, 0))
        plan = tk.Label(card, text="", bg=BG, fg=MUTED, font=("Menlo", 8),
                        anchor="w", justify="left")
        plan.pack(fill="x")
        # weekly-plan mini-bar: fill = used%, marker = where you should be
        wk = tk.Canvas(card, height=7, bg=TRACK, highlightthickness=0)
        wk.pack(fill="x", pady=(1, 0))
        for w in (card, top, name, canvas, plan, wk):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)
        return {"canvas": canvas, "amount": amount, "plan": plan, "weekly": wk}

    def _draw_bar(self, tool: str, tdata: dict):
        b = self.bars[tool]
        canvas: tk.Canvas = b["canvas"]
        canvas.delete("all")
        canvas.update_idletasks()
        w = canvas.winfo_width() or 260
        h = 14
        color, emoji = MOOD.get(tdata["mood"], (MUTED, "•"))
        frac = min(1.0, tdata["today"] / tdata["target"]) if tdata["target"] else 1.0
        canvas.create_rectangle(0, 0, w, h, fill=TRACK, outline="")
        if frac > 0:
            canvas.create_rectangle(0, 0, max(2, int(w * frac)), h, fill=color, outline="")
        # pace marker
        pf = tdata.get("active_fraction", 0)
        if 0 < pf < 1:
            x = int(w * pf)
            canvas.create_line(x, 0, x, h, fill="#ffffff", width=1)
        today = core.humanize(tdata["today"])
        target = core.humanize(tdata["target"])
        if tdata["hit"]:
            tail = f"{emoji} {today}/{target} ({tdata['percent']:.0f}%)"
        else:
            tail = f"{emoji} {today}/{target}  need {core.humanize(tdata['remaining'])}"
        b["amount"].configure(text=tail, fg=color)

    def _draw_limits(self, tool: str, info: dict):
        lbl = self.bars[tool]["plan"]
        wk_canvas: tk.Canvas = self.bars[tool]["weekly"]
        wk_canvas.delete("all")
        if not info or not info.get("available"):
            lbl.configure(text="plan: CodexBar 未运行", fg="#484f58")
            return
        parts = []
        behind = False
        weekly_win = None
        for w in info["windows"]:
            rin = f" {w['reset_in']}" if w["reset_in"] else ""
            seg = f"{w['name'][:4]} {w['left_percent']}%{rin}"
            p = w.get("pace")
            if p and not p["on_pace"] and p["behind_by"] >= 5:
                seg += f"⚠{p['behind_by']:.0f}"
                behind = True
            if w["name"] == "weekly":
                weekly_win = w
            parts.append(seg)
        prefix = "plan⚠ " if info.get("stale") else "plan "
        color = "#d29922" if (info.get("stale") or behind) else MUTED
        lbl.configure(text=prefix + " · ".join(parts), fg=color)
        self._draw_weekly(wk_canvas, weekly_win)

    def _draw_weekly(self, canvas: tk.Canvas, w: dict | None):
        """Mini-bar for the weekly plan: fill = used%, white tick = pace target.
        The gap between fill and tick is the allowance you're on track to waste."""
        canvas.update_idletasks()
        width = canvas.winfo_width()
        if width <= 1:
            width = 260
        h = 7
        canvas.create_rectangle(0, 0, width, h, fill=TRACK, outline="")
        if not w:
            return
        used = max(0, min(100, w.get("used_percent", 0)))
        p = w.get("pace")
        on_pace = bool(p and p["on_pace"])
        fill = "#3fb950" if on_pace else "#d29922"
        if used > 0:
            canvas.create_rectangle(0, 0, max(2, int(width * used / 100)), h, fill=fill, outline="")
        if p:
            x = int(width * min(100, p["expected_used_percent"]) / 100)
            canvas.create_line(x, 0, x, h, fill="#ffffff", width=1)

    # ----------------------------------------------------------------- refresh
    def kick_refresh(self):
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            st = core.status(config=self.config)
            sug = sessions.suggestion(days=self.config.get("suggest_days", 5))
            pl = limits.plan_limits()
            self.results.put(("ok", (st, sug, pl)))
        except Exception as exc:  # never let the worker kill the UI
            self.results.put(("err", (str(exc), None, None)))

    def _poll_results(self):
        try:
            while True:
                kind, payload = self.results.get_nowait()
                if kind == "ok":
                    self._render(*payload)
                else:
                    self.updated_lbl.configure(text=f"⚠ {payload[0]}")
        except queue.Empty:
            pass
        self.root.after(500, self._poll_results)

    def _render(self, st: dict, sug: dict | None, pl: dict | None = None):
        pl = pl or {}
        for tool in ("claude", "codex"):
            self._draw_bar(tool, st["tools"][tool])
            self._draw_limits(tool, pl.get(tool, {}))
        c = st["combined"]
        self.combined_lbl.configure(
            text=f"Σ {core.humanize(c['today'])}/{core.humanize(c['target'])} ({c['percent']:.0f}%)")
        if sug:
            snip = f"\n  {sug['snippet']}" if sug.get("snippet") else ""
            self.suggest_lbl.configure(
                text=f"▶ resume [{sug['tool']}] {sug['name']} · {sug['age']}{snip}")
        else:
            self.suggest_lbl.configure(text="▶ no recent sessions — start something!")
        self.updated_lbl.configure(text=f"updated {datetime.now().strftime('%H:%M:%S')}")
        self.root.after(self.refresh_ms, self.kick_refresh)

    # -------------------------------------------------------------- placement
    def _place_top_right(self):
        self.root.update_idletasks()
        w = 290
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"{w}x218+{sw - w - 24}+48")

    def _start_drag(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _on_drag(self, e):
        self.root.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def _menu(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def run(self):
        self.root.mainloop()


def main():
    TokenPulseWidget(core.load_config()).run()


if __name__ == "__main__":
    main()
