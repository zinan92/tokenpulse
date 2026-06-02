# ⏱ TokenPulse

A lightweight daily-quota **coach** for your Claude Code and Codex subscription
plans. CodexBar is the odometer (raw token numbers); TokenPulse is the coach —
it frames those numbers against a **daily target**, shows **pace**, and
**nudges you with something concrete to go build** when you're behind.

Goal it tracks: burn **150M tokens/day per plan on weekdays** (300M combined),
**75M/day per plan on weekends** (150M combined). The whole point is to *not
leave tokens on the table* — when you're behind, it tells you which recent
session to jump back into.

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

Day boundary is **local** by default (your real day, UTC+8). Set
`"day_boundary": "utc"` in `config.json` to mirror CodexBar's boundary exactly.

## Parts

| File | What it is |
|------|-----------|
| `core.py` | The engine: extractors + targets + pace/mood. Pure stdlib, tested. |
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
