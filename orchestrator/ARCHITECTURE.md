# TokenPulse Orchestrator — Milestone → Atomic Units → Autonomous Execution

The furnace burns idle quota. The orchestrator decides *what valuable work* to
burn it on, by turning a clearly-stated milestone into a DAG of atomic units,
storing them as GitHub Issues, and driving them through execution + review to
done — one round of agent work at a time.

## Locked decisions

| Layer | Choice | Why |
|---|---|---|
| ① Milestone + success criteria | **You write it** | Only you know "done". Template provided. |
| ② Decompose → atomic-unit DAG | **Reuse GSD `plan-phase`** | Already does dependency analysis + goal-backward verification. |
| ③ Task store | **GitHub Issues + PR** | "AI reviews PR" is native here; both pilots are code. |
| ④ Execute + review + merge | **Reuse `threads` skill** | Codex-native parallel lanes, file-ownership safety, merge gate. |
| ⑤ Drive / idle-trigger / route | **TokenPulse furnace** | When behind pace, advance the next ready unit. |

## The atomic unit ↔ GitHub Issue contract

One atomic unit = one GitHub Issue. The hard rule: **a unit must be completable
and verifiable in ONE round of agent work.** If not, decompose further (L1
subtask → L2 unit) until every leaf meets the bar.

```
Issue title:  [unit] <imperative, specific>
Labels:
  unit                         # marks it as an atomic unit
  milestone:<slug>             # which milestone
  agent:claude | agent:codex | agent:either   # capability routing
  status:ready | status:blocked | status:running | status:review | status:done
  layer:1 | layer:2            # decomposition depth (optional)
Body (structured):
  ## Intent        — what & why, 1–2 lines
  ## Depends on    — #12, #15   (blocked until those close)
  ## Acceptance    — checkboxes; each must be agent/test-verifiable
  ## Output        — where artifacts land (PR branch / file path)
  ## Verify        — exact test command OR reviewer prompt
```

- **Parallel vs sequential** is encoded by `Depends on`. A unit is **ready** when
  all its dependencies are closed. The scheduler hands ready units to `threads`,
  which additionally enforces *disjoint writable files* so parallel lanes never
  collide.
- **Capability routing**: `agent:codex` → dispatched via `codex exec` (can fan
  out into `threads` lanes); `agent:claude` → `claude -p` (sanitized env,
  curated allowedTools); `agent:either` → whichever plan is more behind on quota.

## Pilot build sequence (douyin bot)

1. **You** finalize `orchestrator/milestones/douyin-bot.md` (milestone + success
   criteria). A draft decomposition is included — correct it.
2. **GSD** decomposes it into a verified phase plan (atomic tasks + deps).
3. **`sync_issues.py`** (to build) turns the plan into GitHub Issues per the
   contract, in the douyin-bot repo.
4. **By hand once**: take one `status:ready` issue → `threads` → PR → review →
   merge → close. Validates the execution loop end-to-end.
5. **`scheduler.py`** (to build): list open issues → compute ready set (deps
   closed) → dispatch to `threads`/`claude -p` → on merge, close issue + unblock
   dependents.
6. **Furnace integration**: the scheduler becomes a fuel provider — when behind
   pace, the furnace pulls the next ready unit instead of a flat queue line.

Reused (not rebuilt): GSD decomposition/verification, `threads` execution/review.
Built here: `sync_issues.py`, `scheduler.py`, furnace fuel-provider glue,
capability routing.

## Open items / loose ends
- Telegram notify token: park-io bot is revoked (401). Switch `nudge.py` to the
  live openclaw `wendy` bot (`~/.openclaw/openclaw.json` →
  `channels.telegram.accounts.wendy.botToken`, chat `1416138619`). Plumbing.
- GitHub repo for the douyin bot: needs to exist before issues can be synced.
