# Parallel repository development

Use this reference for repository-changing work, not read-only diagnosis. The
user may explicitly change the branch policy; do not infer an exception merely
because an edit is small. This is isolation for concurrent conversations, not a
task-ledger, fixed-review, or model-selection protocol.

## Own a branch and a worktree

- Inspect the repository instructions, status, remotes, and existing worktrees.
  Fetch the integration branch when available; start a unique `codex/<task>`
  branch from current `dev`. Report an unavailable remote rather than pretending
  an old base is current.
- Give the task an independent worktree. A different branch in the same directory
  does not isolate files. Prefer the host's managed worktree tools when available;
  otherwise use the project's approved worktree location. Keep temporary output
  under that worktree's approved `.local/<task>/` location.
- Reuse the same task-owned branch/worktree for its follow-ups. Do not adopt,
  reset, stash, switch, or remove another conversation's workspace. Existing
  uncommitted work is not automatically part of the new request.
- Run edits, builds, formatters, and tests against the task worktree explicitly.
  Do not apply a patch to the shared checkout accidentally. Shared output paths,
  databases, devices, and deployments remain shared even with separate worktrees;
  respect their own authorization and coordination boundaries.

## Integrate into dev

- Commit only the task's verified changes. Fetch current `dev` again before
  integration. Merge it into the task branch, or rebase only task-owned history
  when doing so will not rewrite another participant's work.
- Resolve both textual and semantic conflicts in the task worktree. Read the
  surrounding code, contracts, and tests; preserve both tasks' valid behavior.
  Do not use blanket `ours`/`theirs`, reset, or force pushes as conflict resolution.
  Re-run the checks affected by the combination, not merely the old task checks.
- Resolve implementation conflicts directly when evidence is sufficient. If
  product requirements genuinely contradict and the intended result is unknown,
  preserve both versions and ask for that decision.
- Serialize the final integration attempt. Where available, use the repository's
  existing merge queue or integration lock. A non-force Git push is the final
  concurrency guard, not proof that a stale candidate is safe to combine.
- If no PR/merge queue is required and pushing is authorized, a verified task
  branch containing the latest remote `dev` may be fast-forwarded to remote
  `dev` from its own worktree (`git push origin HEAD:refs/heads/dev`). This avoids
  editing or switching the shared checkout. If rejected because `dev` moved,
  fetch, reconcile, verify the changed combination, and retry without force.
- Update a local `dev` checkout only when it is clean and not in use by another
  task; otherwise leave it untouched and report that remote integration succeeded
  while the shared checkout still needs a safe fast-forward. Never discard local
  changes to synchronize it.

## Finish without losing work

Verify that the intended integration target contains the task commit. Distinguish
branch completion, dev integration, push, CI, deployment, and user/device
acceptance. Follow only the completion boundaries the user actually requested;
do not add unrelated CI waits or automatically start monitoring.

Remove/archive a task worktree or delete its branch only after its commits are
integrated, needed artifacts are preserved, it is clean, and no active task uses
it. Prefer recoverable worktree archival. Never bulk-delete `codex/*`: another
conversation may still be developing there.
