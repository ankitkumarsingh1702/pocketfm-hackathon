# Repository agent instructions

## Required UI skill

For every task that creates, edits, reviews, or tests frontend UI, visual design,
CSS, responsive layout, interaction states, accessibility, or UX copy:

1. Read `.agents/skills/pocketfm-ui-design/SKILL.md` completely before acting.
2. Follow it as the repository's visual source of truth.
3. Read its linked design-system reference before making visual decisions.
4. Report any deliberate exception and the product reason for it.

This requirement applies to Codex, Claude, and any other coding agent working in
this repository. Backend-only and infrastructure-only tasks do not trigger it.

## Required continuous-shipping skill

For every task that changes code, integrates parallel work, pushes a branch,
opens or merges a PR, monitors CI/CD, deploys frontend or backend, verifies
production, or needs to continue after a blocker:

1. Read `.agents/skills/pocketfm-continuous-shipping/SKILL.md` completely.
2. Follow its one-task/one-worktree isolation and proof-first shipping workflow.
3. Read its delivery reference before running test, push, merge, or deploy commands.
4. Keep source, PR, merge, deployment, and live-browser/API truth separate.

This requirement applies to Codex, Claude, and any other coding agent working in
this repository.
