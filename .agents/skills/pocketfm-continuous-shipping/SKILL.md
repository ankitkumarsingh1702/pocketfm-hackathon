---
name: pocketfm-continuous-shipping
description: Keep PocketFM feature work moving safely from implementation through push, PR, merge, deployment, and live verification while Codex and Claude tasks run in parallel. Use for any PocketFM repository task that changes code, resolves integration conflicts, pushes a feature branch, opens or merges a PR, monitors CI/CD, deploys or verifies the frontend, simulated-studio backend, or story-genre-convertor, or needs an unblock-and-continue workflow.
---

# PocketFM Continuous Shipping

Own the requested scope through a verified handoff. Keep parallel work isolated,
move to the next safe action instead of stopping at a status report, and separate
source, merge, deploy, and live truth.

Read [references/pocketfm-delivery.md](references/pocketfm-delivery.md) before
running PocketFM-specific test, push, merge, or deploy commands.

## Operating contract

- Use one task, one feature branch, and one worktree.
- Start from the latest `origin/develop`; target PRs to `develop`, never `main`.
- Treat shared dirty files and other worktrees as owned by other parallel tasks.
- Never stash, reset, restore, overwrite, force-push, or delete another task's work.
- If the current worktree is dirty or on another task's branch, create a clean
  isolated worktree from `origin/develop` and continue there.
- Keep the change narrowly scoped. Do not absorb nearby features merely because
  they are visible.
- For frontend, CSS, responsive, accessibility, interaction, or UX work, load
  `.agents/skills/pocketfm-ui-design/SKILL.md` and its reference before acting.
- Never print, commit, or copy credentials. Use ADC, WIF, Secret Manager, and
  repository variables already provided by the project.

When the user says to ship, finish, keep pushing, deploy, or keep tasks unblocked,
continue through push, PR, permitted merge, deploy monitoring, and live proof.
Do not wait for a second prompt between normal stages. Do not bypass a required
review, missing permission, failing gate, or explicit user restriction.

## Shipping workflow

### 1. Establish ownership and truth

1. Read repository instructions and the relevant deployment workflow.
2. Fetch `origin` and inspect branch, status, worktrees, and latest `develop`.
3. Identify staged, unstaged, untracked, incoming, and branch-diff files.
4. Check whether another task already owns or edits any target file.
5. Record the requested deliverable and the files or services it legitimately owns.

Do not call a checkout "latest" until its commit is an ancestor of current
`origin/develop`, or it has merged current `origin/develop`.

### 2. Isolate parallel work

Use the current worktree only when it is clean and dedicated to this task.
Otherwise create a uniquely named worktree and feature branch from
`origin/develop`. Prefer `codex/<scope>` for Codex and `claude/<scope>` for
Claude. Check that the local and remote branch names are unused first.

If two tasks need the same file, split responsibilities by component or sequence
the integration. Do not let both silently rewrite the file.

### 3. Implement the complete vertical slice

- Trace the user-visible behavior through UI, API, model, persistence, and deploy
  configuration before editing.
- Implement the smallest complete slice, including loading, empty, error, and
  recovery states where relevant.
- Preserve compatibility across existing tabs and services.
- Add or update tests for logic and API behavior.
- Keep deploy configuration aligned with the actual artifact boundary.

### 4. Run proportional gates

Run the scoped checks first, then the repository gates for every touched area:

- Frontend: dependency install, lint, production build, and focused UI/runtime
  verification.
- Simulated Studio backend: locked dependency sync, tests, and local health/API
  smoke checks without paid model calls unless explicitly needed.
- Story Genre Convertor: no-token self-tests, import/startup checks, and its
  service health contract.
- Cross-stack or Docker changes: validate both frontend and backend plus the
  container build path or CI-equivalent check.

Do not dismiss a failure as pre-existing without reproducing it on unmodified
`origin/develop` or providing equivalent evidence.

### 5. Integrate the latest `develop`

Fetch again immediately before handoff. Merge current `origin/develop` into the
feature branch when it advanced. Resolve conflicts by understanding both sides;
never blanket-select "ours" or "theirs". Re-run all affected gates after the
merge.

### 6. Push and open the PR

1. Self-review the exact diff and confirm no unrelated or generated files entered.
2. Commit only task-owned files with a concise human-authored message.
3. Push the feature branch without force.
4. Open a focused PR targeting `develop`; include behavior, validation, deploy
   lane, and known limitations.
5. Monitor checks and review state. Fix actionable failures in the same branch.

If the user authorized shipping/deployment and repository rules permit merging,
merge after required gates and reviews pass. Otherwise leave a ready PR and
report the single remaining external gate.

### 7. Select and monitor the deploy lane

Use changed paths and artifact ownership to select the lane described in the
reference:

- Frontend changes deploy the whole `simulated-studio` image.
- Studio backend, skills, data, or root Docker changes deploy
  `simulated-studio`.
- Convertor-only changes deploy `story-genre-convertor`.
- Changes spanning both backend services deploy both, serializing shared studio
  deploys through the workflow concurrency group.
- Documentation and agent-skill-only changes do not need an application deploy.

Prefer the automatic workflow triggered by the merge to `develop`. Use manual
dispatch only for an intentional redeploy, recovery, or service-selective
operation. Watch the exact run to completion; do not infer success from a queued
or in-progress job.

### 8. Prove production

For every shipped service, capture:

- feature commit and merge commit;
- workflow run and its exact `headSha`;
- successful build/deploy/smoke jobs;
- Cloud Run latest ready revision and 100% traffic;
- public health and relevant API responses;
- frontend HTML/assets and a visual interaction check for UI work.

Do not make paid Gemini calls, Firestore writes, or destructive data mutations
for a smoke test unless the requested feature requires them and the user
authorized that scope.

### 9. Report state precisely

State each layer separately:

- local implementation and tests;
- pushed branch;
- PR and review state;
- merged commit;
- deployment workflow;
- Cloud Run revision/traffic;
- browser/API live verification.

Never use "done", "deployed", or "live" for a layer that was not verified.

## Unblock ladder

Apply these in order and keep progressing:

1. Dirty shared worktree: create an isolated worktree.
2. Stale base: fetch and merge current `origin/develop`.
3. Overlapping files: identify the owner, split scope, or sequence the integration.
4. Conflict: resolve only after tracing both behaviors, then re-test.
5. Local failure: diagnose and fix in scope; compare with clean `origin/develop`
   before labeling it pre-existing.
6. CI failure: inspect the failing job and logs, fix the cause, and rerun once
   evidence supports a retry.
7. Deploy queue: wait on the serialized run; do not cancel another feature's deploy.
8. Missing auth, IAM, secret, required review, or user decision: continue every
   other safe task, then report the exact command, role, review, or choice needed.

Do not manufacture progress by weakening tests, bypassing protection, hiding
conflicts, or claiming unverified production state.

## Completion checklist

- Latest `origin/develop` ancestry confirmed
- Other task work preserved
- Scoped implementation complete
- Relevant tests, lint, and build green
- Diff self-reviewed; generated artifacts excluded
- Feature branch pushed without force
- PR targets `develop`
- Required checks and reviews satisfied
- Correct deploy workflow completed for the merge SHA
- Cloud Run revision and traffic verified
- Live UI/API behavior verified
- Remaining external blocker, if any, stated as one concrete prerequisite
