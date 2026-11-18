# Parallel repository development

## Choose the task workspace

Check the current branch and `git worktree list`. Reuse the worktree that
belongs to this task if it is linked and on its own `codex/<task>` branch. If
the host supplied a new **task-owned, clean, detached** linked worktree, confirm
its base and attach a unique task branch there; no second worktree is needed.
If starting in the primary checkout, create a separate linked worktree from
current `dev` (normally fetched `origin/dev`). If the base cannot be refreshed,
say which revision was used. Never repurpose a dirty or unowned workspace.
Run edits and tests in the selected worktree. Devices, databases, ports and
deployments are still shared; worktree isolation does not grant access to them.

## Integrate and finish

Reconcile current `dev` in the task branch. Resolve textual and behavioral
conflicts there, preserve both changes and recheck the affected behavior.
Ask only if product intent cannot be reconciled from the evidence. Serialize
final integration using the project's existing queue or a non-forced fast-forward.
If `dev` moves, reconcile and verify again; do not overwrite it.

For **local-only** delivery, fast-forward the local `dev` checkout only if
clean and unused. For authorized remote delivery without a required MR/queue,
`git push origin HEAD:refs/heads/dev` from the task worktree avoids switching
the shared checkout. Respect existing hooks and pipeline triggers. If a shared
checkout is busy, leave it intact and report which ref contains the result.

Retire only this task's clean worktree/branch, after its commits are integrated,
needed artifacts preserved, and no chat still needs it. Never bulk-delete task branches.

## Clones with the optional Git guard

`python3 config/git-workflow/guard.py status` checks the local hook chain.
Explicit `install` on an opted-in clone preserves existing hooks and task
receipts across linked worktrees; it does not install on CI or prevent editor
writes. Authorized `uninstall` restores the previous hook setting and retains
recovery data. To test the guard itself, run `python3 -B config/git-workflow/test_guard.py`
in an isolated development workspace, not as an application delivery check.
