# Daily Focus - 2026-06-15

project: TokenPulse
repo_path: /Users/wendy/work/tokenpulse
today_focus: Make every loop run explain the product-level before/after, not only technical logs.
desired_outcome: Wendy can return after a loop run and immediately understand what changed for TokenPulse users and why it matters.
target_user_or_operator: Wendy as the TokenPulse operator and user.
product_work_category: UX/usability; Docs/operator experience; Reliability
portfolio_rank: 1
recommended_cycles: 1-2
stop_condition: Desktop/widget surface clearly shows Operator/Impact so Wendy can see what changed without reading CLI logs.
stop_condition_file: web/widget.html
stop_condition_contains:
  - Operator
  - Impact
value_threshold: 3
allow_do_nothing: true
max_noop_cycles: 1
auto_allowed:
  - Improve digest, status, and review-surface wording.
  - Add low-risk tests for product-impact summaries.
  - Improve loop output structure so completed work includes user-visible before/after.
  - Make small, bounded observability and reporting changes.
requires_approval:
  - Medium-risk visible desktop/widget UI changes unless run through the supervised envelope below.
  - Scheduler, daemon, cron, launchd, or autonomous background changes.
  - Credential, secret, authentication, or token-handling changes.
  - Cross-project automation changes.
  - GitHub or Linear structural changes beyond normal issue/PR reporting.
preapproved_medium_risk: desktop-widget-operator-impact
preapproved_medium_risk_supervised_first_run: true
preapproved_medium_risk_allowed_files:
  - web/widget.html
  - webdata.py
  - tests/
preapproved_medium_risk_verification_commands:
  - python3 -m pytest tests/
do_not_touch:
  - launchd, cron, or scheduler activation.
  - secret files or credential stores.
  - broker, trading, publishing, or other live external side effects.
success_criteria:
  - Digest can answer the product before/after in user language.
  - Each completed task summary explains the user or operator benefit.
  - Verification tests pass.
  - No safety blocker is left waiting for human review.

## PM Notes

- Why today: TokenPulse is the pilot product for the loop itself. If the loop cannot explain product impact here, it will be hard to trust it on other projects.
- User benefit: Wendy spends less time reading technical artifacts and more time judging whether the product actually improved.
- Questions resolved: TokenPulse is approved as today's loop target.
- Open questions: Whether Newsletter should become the next registered loop project after TokenPulse remains separate from today's run.

## Loop Instructions

- The loop may only execute work inside `auto_allowed`.
- The loop must skip work below `value_threshold`; no-op is acceptable when no candidate clears the value line.
- The loop must pause when `recommended_cycles` is exhausted or `stop_condition` is met.
- Anything under `requires_approval` must become a waiting-for-human item.
- Medium-risk work may execute only inside `preapproved_medium_risk_*` and only when Wendy runs a supervised cycle.
- Anything under `do_not_touch` is out of scope for today's loop.
- Each completed issue summary must include before/after product impact.
