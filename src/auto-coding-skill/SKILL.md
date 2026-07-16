---
name: auto-coding-skill
description: Optional delivery-first engineering workflow for repository changes. Use when its bounded validation, adaptive Git isolation, review, or coordination will improve delivery speed or defect prevention. Keep clean serial work on the current branch and let the model select beneficial design or subagents without turning them into mandatory ceremony.
---

# Auto Coding Skill

## Use the two authorities

Read root `AGENTS.md` for the shared behavioral protocol and
`docs/ENGINEERING.md` for project facts, access, risk, validation, and budgets.
Do not reconstruct or duplicate those rules from historical task documents.

Normal delivery is:

`analysis → decomposition → necessary design → development → one bounded final
changed-scope gate → commit/push`.

## Select the minimum mechanism set

Read-only questions need no workflow command. Obvious clean serial edits and
terminal ledger maintenance may follow root `AGENTS.md` directly. When task kind,
impact, risk, or concurrency is unclear, run:

```bash
python3 docs/tools/autopipeline/ap.py classify --scope auto \
  --planned-path <PATH> --intent "<intent>" [--writers <N>] \
  [--task-kind read_only|change|terminal_maintenance]
```

Run `mechanism_plan.required`. The model may select
`optional_when_beneficial` only when expected value exceeds coordination cost.
Do not run `forbidden` mechanisms unless the user explicitly overrides the plan.
Reclassify only after material change. For already-direct work, add `--continue-direct`
with every task path and reuse it on `task-start` if needed; unknown dirt isolates.

Use the registered lifecycle only when classification requires isolation or
fingerprinted review, or when the user explicitly requests it:

```bash
python3 docs/tools/autopipeline/ap.py task-start T0001 \
  --owned-path src [--isolated] [--review-required] [--continue-direct] [--force-lifecycle]
# For review-required work, obtain the current fingerprint and approve it:
python3 docs/tools/autopipeline/ap.py task-status T0001 --json
python3 docs/tools/autopipeline/ap.py task-review T0001 \
  --verdict approved --diff-fingerprint <CURRENT_DIFF_FINGERPRINT> --reviewer <REVIEWER_ID>
python3 docs/tools/autopipeline/ap.py commit-push T0001 --msg "T0001: summary"
# Isolated tasks only:
python3 docs/tools/autopipeline/ap.py task-integrate T0001
```

Each parallel writer uses a distinct task ID, registered worktree, writer lease,
dependency SHAs, and non-overlapping `owned_paths`. The main agent alone runs the
final gate, integrates, pushes, and cleans safely merged temporary branches.

## Close with the bounded routed gate

```bash
python3 docs/tools/autopipeline/ap.py validation-map-check --path <PATH>
python3 docs/tools/autopipeline/ap.py light-gate --scope changed --explain
```

Every changed code/config path must map to a real project command. The runtime
de-duplicates commands and enforces route, command, and total budgets. Defaults
are 120 seconds per command and 180 total; projects may raise them for a measured
affected-scope check. Timeouts should narrow the route, never trigger a full build.
Focused test/fix/retest loops remain allowed before the final gate.

Run full regression, Docker, Jenkins, deployment, browser/device writes, or target
acceptance only as an explicit diagnostic. A requested just-pushed failure
diagnosis continues in the same task without inventing another lifecycle.

## Keep state and upgrades safe

Machine task state, leases, fingerprints, and gate evidence stay in Git local
state. Ordinary work creates no taskbook, closure, evidence JSONL, active-task,
or design artifact. Terminal ledger reconciliation validates and commits once.

```bash
autocoding init
autocoding sync --projects .
python3 docs/tools/autopipeline/ap.py upgrade --dry-run
python3 docs/tools/autopipeline/ap.py upgrade --write
python3 docs/tools/autopipeline/ap.py doctor
```

Finish registered tasks before changing versions. Sync replaces root `AGENTS.md`,
archives it, preserves project facts/access, and converges all managed assets.
