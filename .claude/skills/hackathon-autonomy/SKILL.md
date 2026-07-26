---
name: hackathon-autonomy
description: Move fast and self-unblock during the PocketFM hackathon. Use for any build, implementation, fix, or ship task in this repo — favor sensible defaults over clarifying questions, avoid collisions with the parallel sessions, verify by running, and drive work through to a commit/PR. Destructive, irreversible, spend, or security-sensitive actions still get an explicit check first.
---

# Hackathon autonomy — keep moving

This is a fast-moving hackathon with several sessions working the same repo in
parallel. The working style the user wants: **use judgment, keep momentum, and
carry each task to a shippable state instead of stalling on small decisions.**

## 1. Favor decisions over questions

- When a reasonable default exists, take it, state the assumption in one line,
  and continue. Don't raise a question for something you can decide and later
  adjust.
- Reserve a real check-in for actions that are hard to undo: deleting or
  overwriting others' work, force-pushing, spending money, touching
  credentials/security, or requirements ambiguous enough that a wrong guess is
  expensive. Reversible choices don't need a gate.
- Don't use "should I proceed?" as filler. Either it's reversible (just do it and
  report) or it's one of the above (name the specific risk and let the user
  decide).
- Ship the smallest coherent slice that fully works; note follow-ups rather than
  gold-plating.

## 2. Survive parallel work (many sessions, one repo)

The tree changes under you — branches switch, files get edited mid-task. Assume
it.

- Before writing: `git branch --show-current`, `git status`, and re-read a file
  right before editing (an earlier read may be stale).
- If the tree is shifting or your change touches files other sessions edit, work
  in an isolated worktree based on the *latest* code:
  `git worktree add -b feat/<you>/<slice> .claude/worktrees/<slice> <latest-branch>`.
  Note: no `worktree.baseRef` is set, so `EnterWorktree` alone branches from
  `origin/develop` and drops in-flight work — base on the current feature
  branch's HEAD instead, then `EnterWorktree` into that path.
- A worktree has no `node_modules`; symlink the main tree's for a quick
  lint/build, then remove the symlink before handing off.
- Prefer additive new files over editing shared ones so branches merge clean.
  Confirm no overlap with the target branch:
  `git diff <base>..<target> -- <your files>` (empty = clean).

## 3. Verify by running

- Frontend: follow the `pocketfm-ui-design` skill, run `npm run lint` and
  `npm run build`, and check desktop **and** mobile via the preview browser. The
  backend on `:8000` is usually already live with seeded data — use it. When
  screenshots are flaky, assert state with `javascript_tool`.
- Report what actually happened — passed, seen, or still broken. No fake "done."

## 4. Carry it to shippable

- Commit in clear, scoped messages as you finish coherent pieces.
- Open the PR against the branch the work is built on (often a local feature
  branch like `feat/ankit/plot-hole-scale`, not `develop`) so the diff is just
  your slice. If that base isn't on the remote yet, push your branch and say so.
- Close each turn with: what shipped, where (branch + PR), how it was verified,
  and any assumption made — so the user can redirect, but nothing waits on them.
