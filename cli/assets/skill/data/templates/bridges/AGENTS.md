<!-- auto-coding-skill:managed-agents:start version=4.1.0 -->

# Repository Delivery Rules

This file is fully managed by `auto-coding-skill`. Keep project-specific facts,
commands, access values, path mappings, architecture boundaries, and runtime
notes in `docs/ENGINEERING.md` or its linked project documents. Do not add local
workflow rules here; the next Skill sync replaces this file as a whole.

## Required sources

Before changing a repository, read:

1. the current user request;
2. this file;
3. `docs/ENGINEERING.md` frontmatter and project-specific sections;
4. only the source, tests, contracts, migrations, runtime configuration, or
   decision records relevant to the requested scope.

Use this authority order when sources disagree:

1. the current user request;
2. executable code, tests, schemas, migrations, and runtime configuration for
   behavior that exists now;
3. `docs/ENGINEERING.md` for project boundaries, access, risk, and validation;
4. interface documentation for intended external contracts;
5. accepted DD/ADR documents for lasting decisions;
6. taskbooks, closure logs, summaries, reviews, and deployment records as
   historical evidence only.

Do not let stale historical documents override current implementation. If a
requested change intentionally changes a contract or decision, update the
authoritative documentation in the same change.

## Delivery flow

This Skill is a selectable guardrail, not a mandatory ceremony. The model first
decides which mechanisms have positive net value for the current task. Read-only
work, an obvious clean-checkout edit, or terminal ledger reconciliation normally
needs no classify command, task lifecycle, design record, reviewer, or subagent.
Use the smallest safe path for repository changes:

`analysis → decomposition → necessary design → development → one final
changed-scope gate → commit/push`.

- Analyze impact and reuse points before writing.
- Split only genuinely independent work; keep dependencies and file ownership
  explicit.
- Create DD/ADR only for lasting cross-module, API, data, security, deployment,
  or key user-flow decisions.
- Focused tests may run and rerun during implementation. Run the configured final
  routed gate once after the diff is stable.
- Commit and push all intended changes. A successful target-branch push ends
  normal coding work.
- Do not poll Jenkins, deploy, or perform target acceptance automatically. If the
  user explicitly asks to diagnose a failure caused by the pushed change, keep
  that diagnosis and fix in the same conversation and task scope without
  creating an artificial new ledger task.

## Git safety and parallel work

Inspect the checkout before writing.

- One writer in a clean checkout works on the current branch.
- Pre-existing unrelated changes, an already active writer, or two or more
  writers require isolated task branches/worktrees.
- Each parallel writer gets one registered worktree, non-overlapping
  `owned_paths`, dependency commit SHAs, a distinct task ID, and a writer lease.
- Never let multiple writing agents share a checkout.
- Never restore, reset, stash, clean, overwrite, or commit unknown changes.
- If a task produces no diff, create no commit or push. Direct work creates no
  temporary branch.
- The main agent alone integrates by dependency order, pushes the target branch,
  and removes only clean, safely merged temporary worktrees and branches.

Do not upgrade or sync the Skill while any registered task is active. Finish,
integrate, or clean it with the installed runtime first so lifecycle semantics do
not change mid-task.

## Risk, agents, and review

- Micro and standard tasks default to the main agent. Do not require design,
  fan-out, a task ledger, or a reviewer merely because a change is non-trivial.
- Use read-only explorer, documentation researcher, or browser roles only for
  independent questions whose expected value exceeds coordination cost.
- Use parallel fixers only for bounded, dependency-aware units with separate
  worktrees and non-overlapping paths.
- Require independent review for high-risk, cross-module, parallel integration,
  or explicitly configured work.
- Review blocks only defects introduced or worsened inside the promised task
  scope. Record adjacent pre-existing issues as non-blocking follow-ups.
- Any semantic code/config change invalidates review approval and requires a new
  diff fingerprint. A mechanical documentation-only correction may receive a
  targeted recheck by the same reviewer against the new fingerprint.
- Historical debt does not block ordinary delivery. Block only new or worsened
  P0/P1 issues; handle broad cleanup through an explicit governance task.

## Validation

`risk.rules` controls reasoning and review depth. `validation.routes` controls
executable checks. Keep them separate.

- Every changed code/config path must match one or more explicit validation
  routes in `docs/ENGINEERING.md`.
- Run every matched command once in stable configuration order and de-duplicate
  repeated command references.
- Unmapped code or a missing/blank command fails before staging.
- Documentation-only work may use the built-in diff/format check.
- `git diff --check` is additional hygiene and never business-code validation.
- Use project-native fast checks. Do not automatically run a full repository
  build, Docker, Jenkins, deployment, live-device writes, or target validation.
- Do not install dependencies proactively. Only after the selected final route
  fails because a repository-locked dependency is absent may it be restored once;
  then retry only that affected route.
- External-system or real-device writes require the project's explicit safety
  rule or user confirmation; prefer fixtures/simulators for repeatable local
  coverage where the project supplies them.

## Documentation and access

- `docs/ENGINEERING.md` is the single project workflow configuration source. Its
  managed block explains the shared protocol; content outside that block contains
  project facts, not competing workflow instructions.
- Put durable product/domain facts, repository maps, and runtime/deployment facts
  in `docs/project/` when they are too large for `ENGINEERING.md`.
- Ordinary work does not create taskbook, closure Markdown, evidence JSONL,
  active-task documents, or design files. Pure ledger/archive reconciliation is
  a terminal maintenance action and must not create another task lifecycle.
- Generated task state, leases, fingerprints, and gate evidence stay in Git
  common/local state so recording them cannot change the reviewed diff.
- Fill the configured project/Jenkins/GitLab/Nexus access fields during project
  initialization. Plaintext values are allowed by the generic workflow; do not
  invent or echo credentials unnecessarily.

<!-- auto-coding-skill:managed-agents:end -->
