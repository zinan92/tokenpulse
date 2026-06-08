# Production Shipping Pipeline — GSD × Superpowers × gstack

Mixing three frameworks by **strength**, one owner per stage. Two entry tracks
(new project vs existing/brownfield), converging after Phase 0.

## Division of labor

| Framework | Role | Owns |
|---|---|---|
| **GSD** | The spine | Decompose milestone → atomic-unit DAG → wave-parallel execute → verify → code-review → ship-PR → milestone lifecycle. Also the **brownfield entry** (map/import/intel/forensics). |
| **Superpowers** | Craft *inside* each unit | TDD, systematic-debugging, verification-before-completion, code-review etiquette. How one unit gets built *right*. |
| **gstack** | The bookends + taste + ops | Ideation (office-hours), multi-lens plan critique (autoplan), design exploration, real-browser QA/perf (browse/qa/benchmark), security audit (cso), deploy + monitoring (land-and-deploy/canary), retro. |

Rule: **one owner per stage.** Add a second framework only for a *distinct lens*
(e.g. gstack `/codex` as an adversarial second opinion on top of `/gsd-code-review`).

## Phase 0 — Understand & Frame  (NEW vs OLD diverge ONLY here)

**NEW project:**
- `/office-hours`  — gstack: is it worth building? narrowest wedge? (kills bad ideas cheap)
- `/gsd-new-project` — GSD: deep context → PROJECT.md

**OLD project (e.g. Daily Newsletter):**
- `/gsd-map-codebase` — GSD: map existing architecture
- `/gsd-import` — GSD: bring the existing repo under GSD's model
- `/gsd-intel` — GSD: generate code intelligence
- `/freeze` + `/benchmark` — gstack: capture a baseline BEFORE changes (so QA can prove no regression)

**Gate (both):** *you* write the milestone + success criteria. This is the one
step no tool replaces.

## Phase 1 — Decompose  (GSD — the only one that truly does this)
- `/gsd-new-milestone`
- `/gsd-discuss-phase --auto` (gather context; `--auto` skips Q&A)
- `/gsd-research-phase` (only if real unknowns)
- `/gsd-plan-phase` → atomic tasks + `depends_on` waves + `acceptance_criteria`; built-in plan-checker
- **Gate:** plan-checker PASS

## Phase 2 — Critique the plan BEFORE building  (gstack — cheap error-catching)
- `/autoplan` — runs CEO + eng + design + devex reviews with auto-decisions
- UI products: `/gsd-ui-phase` (design contract) + `/design-consultation`
- **Gate:** no blocker; `/gsd-validate-phase`

## Phase 3 — Build  (GSD orchestrates · Superpowers inside each unit)
- `/gsd-execute-phase` — wave-parallel, worktree-isolated; lights up ready units wave by wave
- Inside each unit the executor follows Superpowers: `test-driven-development`
  (RED→GREEN→refactor), `systematic-debugging` when stuck, `verification-before-completion`
- **Gate:** every unit's `acceptance_criteria` passes

## Phase 4 — Verify & Review  (GSD + one adversarial lens)
- `/gsd-verify-work` — goal-backward: did we deliver what the phase promised?
- `/gsd-code-review` → `/gsd-code-review-fix`
- Risky units: `/codex` — gstack's "200 IQ" adversarial second opinion
- **Gate:** verify PASS, review no blocker

## Phase 5 — Harden  (security + QA + perf — gstack's home turf)
- Security: `/gsd-secure-phase` (verify threat mitigations) + `/cso` for sensitive surfaces
- Real QA: `/qa` + `/browse` (headless real-user flows) + `/benchmark` (perf vs Phase-0 baseline)
- User acceptance: `/gsd-audit-uat`
- **Gate:** QA green, no perf regression, no security blocker

## Phase 6 — Ship
- `/gsd-ship` (open PR, archive phase) for GSD-managed phases — or gstack `/ship`
- **Gate:** PR merged, CI green

## Phase 7 — Deploy & Watch  (gstack)
- `/land-and-deploy` → `/canary` (post-deploy: console errors, perf, page failures) → `/document-release`
- **Gate:** canary clean

## Phase 8 — Close & Learn
- `/gsd-complete-milestone` + `/gsd-audit-milestone` + `/gsd-milestone-summary`
- `/retro` (gstack) · `finishing-a-development-branch` (Superpowers)

---

## Cheat-sheet: NEW project
```
/office-hours                          # gstack: worth building? wedge?
/gsd-new-project                       # GSD: PROJECT.md
# —— you write milestone + success criteria ——
/gsd-new-milestone
/gsd-discuss-phase --auto
/gsd-research-phase                    # only if unknowns
/gsd-plan-phase                        # decompose → atomic-unit DAG
/autoplan                              # gstack: 4-lens plan critique
/gsd-execute-phase                     # build (wave parallel); TDD inside each unit
/gsd-verify-work
/gsd-code-review  →  /gsd-code-review-fix
/codex                                 # gstack: adversarial re-review (risky units)
/gsd-secure-phase
/qa  +  /browse  +  /benchmark         # gstack: real QA + perf
/gsd-ship                              # open PR
/land-and-deploy  →  /canary  →  /document-release
/gsd-complete-milestone  →  /retro
```

## Cheat-sheet: OLD project (Daily Newsletter) — only Phase 0 differs
```
/gsd-map-codebase                      # GSD: map existing architecture
/gsd-import                            # GSD: adopt into GSD model
/gsd-intel                             # GSD: code intelligence
/freeze  +  /benchmark                 # gstack: baseline before changes (catch regressions)
# —— you write the NEXT milestone + success criteria ——
/gsd-new-milestone
/gsd-discuss-phase --auto
/gsd-plan-phase
/autoplan
/gsd-execute-phase                     # TDD + systematic-debugging (legacy lands here)
/gsd-verify-work
/gsd-code-review  →  /gsd-code-review-fix
/gsd-secure-phase
/qa  +  /browse  +  /benchmark         # compare to Phase-0 baseline → prove no regression
/gsd-ship
/land-and-deploy  →  /canary
/gsd-complete-milestone  →  /retro
```

**NEW vs OLD = only Phase 0.** New asks "worth building?" + scaffolds from zero.
Old "maps + adopts + baselines" and guards against regressions. Phases 1–8 identical.

## Ties to the rest of this project
- The **furnace** automates "advance to the next command when idle": behind on
  quota → `/gsd-next` to push the milestone forward one atomic unit.
- For **pipeline-type products** (Daily Newsletter, douyin bot), Phase 3's output
  *form* can be an n8n workflow (orchestration layer) — but engine nodes stay
  real, tested code. (Workflow-as-code at the orchestration layer, not the algorithm layer.)
