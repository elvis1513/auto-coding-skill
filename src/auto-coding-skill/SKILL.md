---
name: auto-coding-skill
description: Optional delivery-first engineering workflow for repository changes. Use when its bounded validation, adaptive Git isolation, review, or coordination will improve delivery speed or defect prevention. Keep clean serial work on the current branch and let the model select beneficial design or subagents without turning them into mandatory ceremony.
---

# Auto Coding Skill

## Use the two authorities

Read root `AGENTS.md` for the shared behavioral protocol,
`docs/ENGINEERING.md` for access/risk/validation configuration, and
`docs/project/` for durable project facts.
Do not reconstruct or duplicate those rules from historical task documents.

Normal delivery is:

`analysis → decomposition → necessary design → development → bounded gate → commit/push`.

## Select the minimum mechanism set

Read-only questions need no workflow command. Clean serial edits and terminal
maintenance may follow `AGENTS.md` directly. When impact or concurrency is unclear, run:

```bash
python3 docs/tools/autopipeline/ap.py classify --scope auto \
  --planned-path <PATH> --intent "<intent>" [--writers <N>] \
  [--task-kind read_only|change|terminal_maintenance] [--claim-direct]
```

Run `mechanism_plan.required`; select `optional_when_beneficial` only when its
value exceeds coordination cost, and keep `forbidden` off absent user override.
`classify` is a fail-closed snapshot: inspect `repo`, `workspace_dirty`,
`dirty_paths`, and `active_writer`, and reclassify if state changes before writing.
Same-owner claims conflict unless continuing the exact ID; `change_nature` never bypasses a rule or review.

Use the registered lifecycle only when classification requires isolation/fingerprinted review or the user explicitly requests it:

```bash
python3 docs/tools/autopipeline/ap.py task-start T0001 \
  --owned-path src [--isolated] [--review-required] [--continue-direct --direct-claim <ID>]
# Before the first commit, expand an active task instead of restarting it:
python3 docs/tools/autopipeline/ap.py task-scope-add T0001 --owned-path config/new-scope
# Run a read-only Reviewer under its fixed deadline and record the bound result:
python3 docs/tools/autopipeline/ap.py review-run T0001 --reviewer <REVIEWER_ID> --json
python3 docs/tools/autopipeline/ap.py commit-push T0001 --msg "T0001: summary"
# Isolated tasks only:
python3 docs/tools/autopipeline/ap.py task-integrate T0001
```

Each parallel writer uses a task ID, worktree, lease, dependency SHAs, and distinct
`owned_paths`. Main integrates, gates, pushes, and cleans. Validate delegated JSON
with `agent-contract-check`; parallel fixers require reclassification with
`--writers >1`.

Use `reviewer` at `xhigh`: focused gets 90 seconds; parallel/cross-module or sensitive boundaries get 300. `review-run` creates the assignment, launches a separate read-only
Codex process without the lifecycle-owner identity, terminates its process group at the deadline, and records only an exact HEAD/scope/fingerprint match. Before the deadline,
`review-assignment` freezes staged, unstaged, untracked, deleted, mode, symlink, and binary changes into a mode-0600 Git-local patch with assignment-bound path, format, and SHA-256.
The Reviewer must run `python3 docs/tools/autopipeline/ap.py review-artifact --file <assignment.json>` and review that emitted patch instead of reconstructing a live Git diff. Timeout is `blocked`.
`review-assignment` alone requires another deadline-capable host and cannot stop an
in-app subagent. `agent-result-template` supplies all 16 fields; `review-run` safely
normalizes presentation fields from the same analysis.

## Close with the bounded routed gate

For unregistered clean serial work, run the final gate and then use normal Git:

```bash
python3 docs/tools/autopipeline/ap.py validation-map-check --path <PATH>
python3 docs/tools/autopipeline/ap.py light-gate --scope changed --explain
```

For a registered task, call only `commit-push`: it owns the final gate and reuses
an exact Git-local PASS only while content, base, scope, routes, commands, and
lease match. Matching manual passes are reusable; changed state is not.

Every changed code/config path must map to a real project command. The runtime
de-duplicates commands and enforces 120-second command and 180-second total
budgets; measured routes may override them. Timeouts narrow, never expand, scope.
Focused test/fix/retest remains allowed; commands inherit PATH in non-login Bash.
Size warnings block only with `structure.enforcement: blocking` and `structure.block_warnings: true` (default `false`).

Run full regression, Docker, Jenkins, deployment, browser/device writes, or target
acceptance only as an explicit diagnostic. A requested just-pushed failure
diagnosis continues in the same task without inventing another lifecycle.

## Keep state and upgrades safe

Machine task state, leases, fingerprints, and gate evidence stay Git-local.
Ordinary work creates no taskbook, closure, evidence JSONL, active-task, or
design artifact. Terminal ledger reconciliation validates and commits once.

```bash
autocoding init
python3 docs/tools/autopipeline/ap.py doctor
```

Finish registered tasks before changing versions. `autocoding init` idempotently
replaces managed constraints, preserves schema-supported values, installs canonical
docs/templates, archives obsolete content outside active `docs/`, and preserves
designated artifacts. It verifies the managed-install manifest; `doctor` cheaply
rechecks declared paths without treating project-owned files or archives as a mirror.
