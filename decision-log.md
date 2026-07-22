# Decision log — issue #34

## 2026-07-22 — Codex accuracy and compact presentation

- **Decision:** When available, TokenPulse reads the installed `codexbar cost`
  local result for Codex token/cost totals instead of independently summing
  `last_token_usage` rows.
- **Why:** On the user's live logs, the old raw sum was about `4.48B` tokens
  while CodexBar's lineage-aware local scan reported about `825.6M`. Current
  Codex rollouts emit cumulative `total_token_usage` snapshots and forked-agent
  streams, so a simple row sum is not a trustworthy accounting model.
- **Fallback:** Without CodexBar, TokenPulse stays local and keeps its existing
  parser; it does not add telemetry, API login, or log upload.
- **Presentation:** Keep the full desktop widget as the default. Add two
  explicit, reversible display settings: one-line compact mode and a native
  macOS menu-bar status item.

## Gotchas

- CodexBar totals change while agents are active; tests must use fixtures and
  production verification must compare a same-time snapshot, not a stale value.
- The native status item must be optional and macOS-only; imports stay inside
  the controller so CLI/tests do not require AppKit on other platforms.
- Menu-bar mode hides the desktop widget but its menu must still expose a way
  to open the full settings panel.
- `pywebview.start` invokes its startup callback on a worker thread. Creating
  an `NSStatusBar` item there fails; create it from `main()` before starting the
  GUI loop, and persist placement changes for the next app launch.
- Compact mode must never hide the only route back to settings; retain a
  visible control that restores the full widget before opening its panel.
- An expanded frameless panel must scroll inside a bounded viewport; otherwise
  content accessibility depends on users discovering an invisible resize edge.
