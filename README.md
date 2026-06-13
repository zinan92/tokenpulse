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

`plan_behind_threshold` is measured in percentage points of weekly-plan pace.
For example, the default `10` means plan-aware nudges and furnace decisions
ignore small drift, but treat a weekly window as behind once its `behind_by`
value reaches 10 points.

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
| `webwidget.py` / `webdata.py` | Browser-rendered widget path: pywebview hosts `web/widget.html`, while `webdata.py` bridges core, plan-limit, and cost payloads. |
| `cost.py` | Today/30d cost and token summaries, priced from the local CodexBar model-pricing cache when available. |
| `nudge.py` | Telegram push at checkpoints when behind pace (actionable). |
| `furnace.py` / `fuel.py` | Optional unattended quota burner. Disabled by default; when enabled, dispatches one queued or recurring job to the most-behind tool. |
| `cli.py` | Terminal status (`--json`, `--sessions`). |
| `jobs.example.json` | Example recurring-job source for the furnace; copy its shape into a local `jobs.json` if you want baseline jobs. |
| `config.json` | Targets, active window, checkpoints, day boundary, plan threshold, and furnace kill switch. |

## Use

```bash
python3 cli.py              # quick terminal status
python3 cli.py --sessions   # recent sessions to resume
python3 widget.py           # launch the desktop widget
python3 webwidget.py        # launch the browser-rendered pywebview widget
python3 nudge.py --dry-run --force   # preview a Telegram nudge
python3 furnace.py --dry-run          # preview the optional furnace decision
python3 -m pytest tests/    # run the engine tests
```

The Tkinter widget and web widget show cost lines from `cost.py`: today's cost,
30-day cost, 30-day tokens, and today's tokens. Pricing depends on the local
CodexBar model-pricing cache at
`~/Library/Caches/codexbar/model-pricing/models-dev-v1.json`; if pricing for a
model is unavailable, that model contributes zero cost rather than blocking the
token display.

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
  "plan_behind_threshold": 10,                    // weekly-plan behind points
  "telegram": { "enabled": true },
  "furnace": {
    "enabled": false,                             // kill switch; off by default
    "max_jobs_per_day": 12,
    "max_runtime_minutes": 30,
    "default_cwd": "~/work",
    "telegram": true
  }
}
```

## Furnace

`furnace.enabled` defaults to `false`, so TokenPulse will not launch unattended
Claude or Codex jobs unless you opt in through config. When enabled, the furnace
checks the same token pace and weekly-plan pace signals as the nudge path,
respects the active work window, daily cap, runtime cap, and per-tool locks, then
dispatches one eligible job to the most-behind tool.

Fuel comes from `queue.txt` first, then recurring jobs from `jobs.json`. Use
`jobs.example.json` as the documented shape for recurring jobs: each entry names
a prompt, optional preferred tool, cooldown, working directory, and tool/sandbox
limits. The example is only a job-source template; it does not install launchd
jobs, edit credentials, or publish anything externally.
