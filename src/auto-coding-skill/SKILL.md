---
name: auto-coding-skill
description: Delivery-first engineering workflow for repository changes. Use for analysis, task decomposition, necessary design, implementation, fast changed-scope validation, safe commit/push, adaptive Git isolation, parallel writer coordination, and temporary branch cleanup. Keep clean single-writer work on the current branch; escalate to worktrees, subagents, review, or stronger affected-scope checks only when risk or concurrency justifies them.
---

# Auto Coding Skill

## Activate only useful guardrails

This Skill is a decision aid, not a mandatory ceremony. For each task, use only
the mechanisms whose expected efficiency or quality benefit exceeds their cost.
Read-only questions, obvious clean-checkout edits, and terminal ledger maintenance
need no classify command, machine task lifecycle, design record, reviewer, or
subagent by default. Repository code changes still receive one real, fast,
affected-scope validation before commit/push.

Deliver changes through:

`analysis → decomposition → necessary design → development → one final fast
changed-scope gate → commit/push`.

Read the fully managed root `AGENTS.md`, then `docs/ENGINEERING.md` for project
facts, access values, risk rules, and validation routes. Treat target-branch push
as normal coding completion. Do not poll Jenkins, deployment, or owner acceptance.
When the user explicitly asks to diagnose a failure caused by that push, continue
the diagnosis and repair in the same conversation/task without inventing another
ledger lifecycle.

## Choose the lightest safe path

Inspect the checkout before writing:

- Use the current branch for one writer when the checkout is clean.
- Use an isolated task branch/worktree when unrelated changes already exist,
  when more than one writer will run, or when the project explicitly requires it.
- Use one writer per worktree and non-overlapping owned paths.
- Create no temporary branch merely to analyze a task or when no diff is produced.
- Never restore, reset, stash, clean, or modify unknown user/task changes.

Classify planned work before development when impact is unclear:

```bash
python3 docs/tools/autopipeline/ap.py classify --scope auto \
  --planned-path <PATH> --intent "<intent>" [--writers <N>]
```

`execution_mode=direct` means stay on the current branch.
`execution_mode=isolated` means start registered worktrees. `execution_mode=none`
means do not create Git state.

Use the runtime-supported lifecycle when a machine-enforced task boundary helps:

```bash
python3 docs/tools/autopipeline/ap.py task-start T0001 \
  --owned-path src [--isolated] [--review-required]
# Work in the path printed by task-start.
python3 docs/tools/autopipeline/ap.py commit-push T0001 --msg "T0001: summary"
# Isolated tasks only:
python3 docs/tools/autopipeline/ap.py task-integrate T0001
```

Direct `commit-push` runs the final gate and pushes the current target branch.
If the task has no diff, it clears its machine state without commit or push.
Isolated `commit-push` pushes the task branch; `task-integrate` serializes the
target push and removes clean merged temporary worktrees and branches. Use
`task-finish` or `task-prune` only for safe lifecycle cleanup.

## Scale design and review by risk

Use `micro`, `standard`, and `high-risk` only to scale reasoning and guardrails;
never use them to trigger a full local repository gate automatically.

- Keep ordinary micro/standard work main-agent-only unless delegation has a
  concrete latency or expertise benefit.
- Create DD/ADR only for lasting cross-module, API, data, security, deployment,
  or key user-flow decisions.
- Require independent fingerprinted review for high-risk, cross-module,
  explicitly configured, or parallel integration work.
- Route blocking review findings back to the owning writer and invalidate the
  approval after any content change or rebase.
- Keep review inside the promised task scope. Adjacent pre-existing findings are
  non-blocking follow-ups. Semantic changes require full review against a new
  fingerprint; mechanical docs-only corrections may use a targeted recheck.

Historical debt does not block normal delivery. Block only new or worsened P0/P1
issues. Handle repository-wide governance through an explicit task and optional
baseline/backlog.

## Use subagents when they improve throughput

Let the main agent own decomposition, architecture, dependencies, final gate,
Git closure, integration, and cleanup.

- Run independent read-only explorer, docs, or browser questions in parallel only
  when the model judges their expected value higher than coordination cost;
  classification may suggest capabilities but never auto-dispatches them.
- Dispatch fixers only for bounded, dependency-free units with non-overlapping
  paths; give each parallel fixer its own task ID, writer lease, and registered
  worktree. `task-start` creates exactly one writer/worktree.
- Start dependent writers only after prerequisite commits are integrated.
- Add a reviewer only when the risk policy requires one.
- Do not force fan-out for small serial tasks.

Subagents do not commit, push, integrate, clean branches, or run the final project
gate. Use the bundled orchestration contract when structured assignments/results
are useful; ordinary main-agent work needs no task ledger.

## Run real changed-scope validation

Keep classification under `risk.rules` and executable checks under
`validation.routes`. Match every changed path against all routes, collect command
references in configuration order, remove duplicates, and run each once.

```bash
python3 docs/tools/autopipeline/ap.py validation-map-check --path <PATH>
python3 docs/tools/autopipeline/ap.py light-gate --scope changed --explain
```

- Fail before staging when changed code is unmapped or a route references a
  missing/blank command.
- Allow docs-only changes to use the built-in diff check.
- Treat `git diff --check` as additional hygiene, never as business validation.
- Allow focused tests and test/fix/retest loops during development.
- Run one final routed closure gate after the diff is stable.
- Do not automatically run full regression, Docker, builds, Jenkins, deployment,
  API verification, or target checks.
- Do not install dependencies proactively. Only after the selected final route
  fails because a repository-locked dependency is absent may it be restored once;
  then retry only that affected route.

## Keep project state small

Store task manifests, the installed Skill version, ownership, leases,
dependencies, and review fingerprints in the Git common directory. Store gate
timing/evidence under `.local` by default.
Do not create taskbook, closure Markdown, evidence JSONL, active-task, or design
documents for ordinary work. Preserve existing project documents as user data;
create or update them only when explicitly useful.

Keep root `AGENTS.md` byte-identical to the packaged canonical file; sync replaces
it as a whole and archives its previous contents as historical, non-authoritative
context. Keep `docs/ENGINEERING.md` as the only manual workflow configuration
source. Put larger product, repository, and runtime facts in `docs/project/`, not
in root AGENTS or duplicated workflow sections. Allow direct plaintext values
under `access.*`; do not invent or echo credentials.

Pure ledger, closure, or archive reconciliation is a terminal maintenance action:
run its targeted consistency check and commit once. It must not create another
active task, closure record, evidence chain, or review cycle for closing itself.

## Install and upgrade

```bash
autocoding init
autocoding sync --projects .
python3 docs/tools/autopipeline/ap.py upgrade --dry-run
python3 docs/tools/autopipeline/ap.py upgrade --write
python3 docs/tools/autopipeline/ap.py doctor
```

Finish every registered task before syncing a different runtime version. Upgrade
must preserve project configuration, access values, custom role agents, optional
documents, and explicit model overrides while removing obsolete managed Skill
files and filling new managed assets. Root `AGENTS.md` is the exception: it is
fully replaced by the canonical version, with the previous file archived under
`docs/archive/workflow/`.
