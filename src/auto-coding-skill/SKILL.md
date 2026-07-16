---
name: auto-coding-skill
description: Delivery-first engineering workflow for repository changes. Use for analysis, task decomposition, necessary design, implementation, bounded changed-scope validation, safe commit/push, adaptive Git isolation, parallel writer coordination, and temporary branch cleanup. Keep clean serial work on the current branch and add lifecycle, worktrees, subagents, design, or review only when classify marks them required or the user explicitly requests them.
---

# Auto Coding Skill

## Use the two authorities

Read root `AGENTS.md` for the shared behavioral protocol. Read
`docs/ENGINEERING.md` frontmatter for project facts, access values, risk rules,
validation routes, and time budgets. Do not reconstruct or duplicate those rules
from historical task documents.

Normal delivery is:

`analysis → decomposition → necessary design → development → one bounded final
changed-scope gate → commit/push`.

## Select the minimum mechanism set

Skip classification for read-only work, obvious clean serial edits, and terminal
ledger maintenance. When impact, risk, or concurrency is unclear, run:

```bash
python3 docs/tools/autopipeline/ap.py classify --scope auto \
  --planned-path <PATH> --intent "<intent>" [--writers <N>]
```

Follow `mechanism_plan.required`. Do not add anything listed under
`mechanism_plan.not_required` unless the user explicitly requests it. In
particular, ordinary direct work does not create a task lifecycle.

Use the registered lifecycle only when classification requires isolation or
fingerprinted review, or when the user explicitly requests it:

```bash
python3 docs/tools/autopipeline/ap.py task-start T0001 \
  --owned-path src [--isolated] [--review-required]
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
de-duplicates matched commands and enforces both per-command and total closure
budgets. A timeout means the route must be narrowed; it never falls back to a full
build. Focused test/fix/retest loops remain allowed before the final gate.

Run full regression, Docker, Jenkins, deployment, browser/device writes, or target
acceptance only as an explicit diagnostic. If the user asks to diagnose the
just-pushed failure, continue in the same conversation/task without inventing a
new ledger lifecycle.

## Keep state and upgrades safe

Machine task state, leases, fingerprints, and gate evidence stay in Git
common/local state. Ordinary work creates no taskbook, closure Markdown, evidence
JSONL, active-task, or design artifact. Terminal ledger reconciliation validates
and commits once without creating another lifecycle.

```bash
autocoding init
autocoding sync --projects .
python3 docs/tools/autopipeline/ap.py upgrade --dry-run
python3 docs/tools/autopipeline/ap.py upgrade --write
python3 docs/tools/autopipeline/ap.py doctor
```

Finish registered tasks before changing runtime versions. Sync replaces the
canonical root `AGENTS.md`, archives its previous content, preserves project facts
and access values, and converges all managed Skill/runtime/agent assets together.
