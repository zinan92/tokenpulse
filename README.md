# ⏱ TokenPulse

A lightweight daily-quota **coach** for your Claude Code and Codex subscription
plans. CodexBar is the odometer (raw token numbers); TokenPulse is the coach —
it frames those numbers against a **daily target**, shows **pace**, and
**nudges you with something concrete to go build** when you're behind.

Goal it tracks: burn **150M tokens/day per plan, every day** (300M combined,
Claude + Codex). The whole point is to *not leave tokens on the table* — when
you're behind, it tells you which recent session to jump back into. (Targets are
per-tool and weekday/weekend-aware in config, currently set flat at 150M.)

## How it counts tokens

Total throughput per tool, matching what CodexBar shows you (validated:
reproduces CodexBar's "today ~200M" to within rounding):

- **Claude** — `~/.claude/projects/**/*.jsonl`, summing `message.usage`
  (input + cache_creation + cache_read + output), **deduped by
  `(message.id, requestId)`** to undo the transcript double-counting that
  inflates a naïve scan (~485M) back to the real ~200M.
- **Codex** — `~/.codex/sessions/**/*.jsonl`, summing per-turn
  `last_token_usage.total_tokens` (Codex's `total_token_usage` is cumulative —
  summing it would over-count), deduped by session UUID across `sessions/` and
  `archived_sessions/`.

## Real plan quota (remaining %) — via CodexBar

Token counts are a self-imposed proxy; the *actual* subscription windows
(session 5h, weekly, opus weekly) are the true "am I using my plan" signal.
Those percentages are **not** in any local Claude file — Anthropic only exposes
them through an OAuth usage endpoint. Rather than extract OAuth tokens from the
Keychain and call an undocumented endpoint ourselves, `limits.py` **piggybacks
on CodexBar**, which already does that auth + probing and writes the results to
disk (refreshed ~hourly):

```
~/Library/Application Support/com.steipete.codexbar/history/{claude,codex}.json
```

We read the latest sample per window → `{name, used_percent, left_percent,
resets_at, reset_in, pace}`. **Requires CodexBar installed and running.** If
it's absent or its data is stale (>6h old), the gadget degrades gracefully
(shows "CodexBar 未运行" / a ⚠ stale flag) and the token tracker keeps working.

### Weekly-plan pace — the "use it all" signal

For weekly-scale windows we compute a **pace**: by the fraction of the 7-day
window elapsed you'd need that same fraction used to fully consume the
allowance before reset. `behind_by` = points of allowance you're trailing
(unused headroom you're on track to waste). The 5h *session* window is a burst
limit you don't pace-fill, so it gets no pace. The nudge fires when any weekly
window trails by more than `plan_behind_threshold` (default 10pts) — so it
catches under-utilization of the *real* plan even on days you hit the token
target. Example: `Codex weekly 97%left 4d9h ⚠落后34%` = 37% through the week
but only 3% used.

## Day boundary

Day boundary is **local** by default (your real day, UTC+8) — what "today's
goal" means to a human, and what the pace window aligns to. A naïve UTC-date
filter happened to match CodexBar's "~200M" at one afternoon reading; that's a
single coincidental datapoint, not proof CodexBar uses UTC. If your numbers
drift a couple percent from CodexBar near the day edges and you'd rather match
it, set `"day_boundary": "utc"` in `config.json` and compare.

## Parts

| File | What it is |
|------|-----------|
| `core.py` | The engine: extractors + targets + pace/mood. Pure stdlib, tested. |
| `limits.py` | Real plan quota (session/weekly/opus % left + reset) via CodexBar feed. |
| `sessions.py` | Recent Claude+Codex sessions (last 5 days) → "go resume this". |
| `widget.py` | **Tkinter** always-on-top desktop widget (~30–50MB, no Chromium). |
| `nudge.py` | Telegram push at checkpoints when behind pace (actionable). |
| `cli.py` | Terminal status (`--json`, `--sessions`). |
| `config.json` | Targets, active window, checkpoints, day boundary. |

## Use

```bash
python3 cli.py              # quick terminal status
python3 cli.py --sessions   # recent sessions to resume
python3 widget.py           # launch the desktop widget
python3 nudge.py --dry-run --force   # preview a Telegram nudge
python3 -m pytest tests/    # run the engine tests
```

## Run it always (macOS launchd)

```bash
./install.sh     # widget at login (keep-alive) + nudge at checkpoint times
./uninstall.sh   # remove both
```

The widget pins to the top-right. Drag to move, **Esc** or right-click → Quit.

## Telegram

Reuses your existing park-io bot — no new token. Credentials load from env
(`PARKIO_TELEGRAM_BOT_TOKEN` / `PARKIO_TELEGRAM_CHAT_ID`) or
`~/park-io/secrets/telegram-{bot-token,chat-id}`. Nudges fire only when you're
behind pace on a plan (or a celebratory summary at the final checkpoint when
both targets are hit).

## Config

```jsonc
{
  "day_boundary": "local",                       // or "utc" to match CodexBar
  "active_window": { "start": "09:00", "end": "23:59" },  // pace ramps 0→1 across this
  "targets": {
    "claude": { "weekday": 150, "weekend": 75 }, // millions of tokens
    "codex":  { "weekday": 150, "weekend": 75 }
  },
  "checkpoints": ["15:00", "20:00", "23:00"],     // nudge times
  "telegram": { "enabled": true }
}
```
