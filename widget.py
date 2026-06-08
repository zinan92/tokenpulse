"""TokenPulse desktop widget — a trimmed CodexBar mirror.

Per tool (Claude, Codex only): Session % + reset, Weekly % + reset, Today cost,
30d cost, 30d tokens, Latest tokens. No Spark windows, no bar chart, no Gemini.

Data: limits.py (session/weekly via CodexBar's history feed) + cost.py (cost &
token aggregates priced at models.dev API rates). Pure-stdlib Tkinter, frameless,
always-on-top. Refresh runs in a worker thread; the heavy 30d cost scan is
TTL-cached in cost.py.

Run: python3 widget.py   ·   Quit: Esc / right-click → Quit   ·   Drag to move.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from datetime import datetime

import cost
import limits

BG = "#0d1117"
FG = "#e6edf3"
MUTED = "#8b949e"
DIM = "#6e7681"
TRACK = "#21262d"
TEAL = "#2dd4bf"
AMBER = "#d29922"
RED = "#f85149"

TOOL_LABEL = {"claude": "Claude", "codex": "Codex"}


def _bar_color(left_pct: float) -> str:
    if left_pct <= 10:
        return RED
    if left_pct <= 25:
        return AMBER
    return TEAL


class TokenPulseWidget:
    def __init__(self, config: dict):
        self.config = config
        self.refresh_ms = int(config.get("widget", {}).get("refresh_seconds", 180) * 1000) or 180_000
        self.results: "queue.Queue[tuple]" = queue.Queue()
        self._drag = (0, 0)

        self.root = tk.Tk()
        self.root.title("TokenPulse")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", 0.97)
        except tk.TclError:
            pass
        self.root.configure(bg=BG)

        self.frame = tk.Frame(self.root, bg=BG, padx=14, pady=11)
        self.frame.pack(fill="both", expand=True)

        header = tk.Frame(self.frame, bg=BG)
        header.pack(fill="x")
        tk.Label(header, text="⏱ TokenPulse", bg=BG, fg=FG, font=("Menlo", 12, "bold")).pack(side="left")
        self.updated_lbl = tk.Label(header, text="", bg=BG, fg=DIM, font=("Menlo", 8))
        self.updated_lbl.pack(side="right")

        self.cards: dict[str, dict] = {}
        for tool in ("claude", "codex"):
            self.cards[tool] = self._make_card(tool)

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

    # ------------------------------------------------------------------ layout
    def _make_card(self, tool: str) -> dict:
        card = tk.Frame(self.frame, bg=BG)
        card.pack(fill="x", pady=(10, 0))
        name = tk.Label(card, text=TOOL_LABEL[tool], bg=BG, fg=FG, font=("Menlo", 11, "bold"),
                        anchor="w")
        name.pack(fill="x")

        rows = {}
        for wname in ("session", "weekly"):
            row = tk.Frame(card, bg=BG)
            row.pack(fill="x", pady=(2, 0))
            tk.Label(row, text=wname[:4].title(), bg=BG, fg=MUTED, font=("Menlo", 9),
                     width=5, anchor="w").pack(side="left")
            canvas = tk.Canvas(row, height=10, width=120, bg=TRACK, highlightthickness=0)
            canvas.pack(side="left", padx=(2, 6))
            txt = tk.Label(row, text="…", bg=BG, fg=MUTED, font=("Menlo", 9), anchor="w")
            txt.pack(side="left")
            rows[wname] = {"canvas": canvas, "txt": txt, "row": row}

        cost_lbl = tk.Label(card, text="", bg=BG, fg=FG, font=("Menlo", 9), anchor="w")
        cost_lbl.pack(fill="x", pady=(3, 0))
        tok_lbl = tk.Label(card, text="", bg=BG, fg=MUTED, font=("Menlo", 9), anchor="w")
        tok_lbl.pack(fill="x")

        widgets = [card, name, cost_lbl, tok_lbl] + [r["row"] for r in rows.values()]
        for w in widgets:
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)
        return {"rows": rows, "cost": cost_lbl, "tok": tok_lbl}

    def _draw_window(self, tool: str, wname: str, w: dict | None):
        r = self.cards[tool]["rows"][wname]
        canvas: tk.Canvas = r["canvas"]
        canvas.delete("all")
        width = canvas.winfo_width()
        if width <= 1:
            width = 120
        h = 10
        canvas.create_rectangle(0, 0, width, h, fill=TRACK, outline="")
        if not w:
            r["txt"].configure(text="—", fg=DIM)
            return
        left = w["left_percent"]
        color = _bar_color(left)
        canvas.create_rectangle(0, 0, max(2, int(width * left / 100)), h, fill=color, outline="")
        rin = f"  {w['reset_in']}" if w["reset_in"] else ""
        r["txt"].configure(text=f"{left}% left{rin}", fg=MUTED)

    # ----------------------------------------------------------------- refresh
    def kick_refresh(self):
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        # Post limits first (fast) so the bars show immediately, then the heavy
        # 30-day cost scan fills in the cost/token lines.
        try:
            pl = limits.plan_limits()
            self.results.put(("limits", pl))
        except Exception as exc:  # noqa: BLE001
            self.results.put(("err", (str(exc), None)))
            return
        try:
            summaries = {t: cost.usage_summary(t) for t in ("claude", "codex")}
            self.results.put(("cost", summaries))
        except Exception as exc:  # noqa: BLE001
            self.results.put(("err", (str(exc), None)))

    def _poll_results(self):
        try:
            while True:
                kind, payload = self.results.get_nowait()
                if kind == "limits":
                    self._render_limits(payload)
                elif kind == "cost":
                    self._render_cost(payload)
                    self.root.after(self.refresh_ms, self.kick_refresh)
                else:
                    self.updated_lbl.configure(text=f"⚠ {payload[0][:30]}")
        except queue.Empty:
            pass
        self.root.after(500, self._poll_results)

    def _render_limits(self, pl: dict):
        for tool in ("claude", "codex"):
            info = pl.get(tool, {})
            avail = info.get("available")
            for wname in ("session", "weekly"):
                w = limits.window(info, wname) if avail else None
                self._draw_window(tool, wname, w)
        stale = any(pl.get(t, {}).get("stale") for t in ("claude", "codex"))
        flag = " ⚠stale" if stale else ""
        self.updated_lbl.configure(text=f"{datetime.now().strftime('%H:%M')}{flag}")

    def _render_cost(self, summaries: dict):
        for tool in ("claude", "codex"):
            s = summaries.get(tool, {})
            c = self.cards[tool]
            c["cost"].configure(
                text=f"Today {cost.humanize_cost(s.get('cost_today', 0))}   "
                     f"30d {cost.humanize_cost(s.get('cost_30d', 0))}")
            c["tok"].configure(
                text=f"30d {cost.humanize_tokens(s.get('tokens_30d', 0))} tok   "
                     f"today {cost.humanize_tokens(s.get('tokens_today', 0))}")

    # -------------------------------------------------------------- placement
    def _place_top_right(self):
        self.root.update_idletasks()
        w = 300
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"{w}x250+{sw - w - 24}+48")

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
    import core
    TokenPulseWidget(core.load_config()).run()


if __name__ == "__main__":
    main()
