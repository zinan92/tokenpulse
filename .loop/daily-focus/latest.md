# Daily Focus - 2026-06-15

project: TokenPulse
repo_path: /Users/wendy/work/tokenpulse
today_focus: Make every loop run explain the product-level before/after, not only technical logs.
desired_outcome: Wendy can return after a loop run and immediately understand what changed for TokenPulse users and why it matters.
target_user_or_operator: Wendy as the TokenPulse operator and user.
product_work_category: UX/usability; Docs/operator experience; Reliability
auto_allowed:
  - Improve digest, status, and review-surface wording.
  - Add low-risk tests for product-impact summaries.
  - Improve loop output structure so completed work includes user-visible before/after.
  - Make small, bounded observability and reporting changes.
requires_approval:
  - Scheduler, daemon, cron, launchd, or autonomous background changes.
  - Credential, secret, authentication, or token-handling changes.
  - Cross-project automation changes.
  - GitHub or Linear structural changes beyond normal issue/PR reporting.
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
- Anything under `requires_approval` must become a waiting-for-human item.
- Anything under `do_not_touch` is out of scope for today's loop.
- Each completed issue summary must include before/after product impact.
