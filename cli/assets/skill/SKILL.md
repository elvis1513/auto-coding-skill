---
name: auto-coding-skill
description: Generic .agents engineering workflow with isolated Git worktrees for parallel write tasks, fast changed-scope local gates, push-based completion, required project access configuration, safe integration, and branch cleanup.
---

# Auto Coding Skill

Use this skill for an analysis → decomposition → design → development → fast
gate → push workflow. The project keeps one manual configuration source:
`docs/ENGINEERING.md`.

At task start, inventory installed skills, MCP servers, connectors, browser
tools, and repository scripts. Prefer the most direct authoritative capability.
Use subagents only when work is independent and the runtime supports them.

## Install and upgrade

```bash
autocoding init
autocoding sync --projects .
pip install pyyaml requests
```

New projects receive a minimal scaffold: the project-local skill, managed role
templates, `docs/ENGINEERING.md`, taskbook, closure log, and a small compatibility
launcher. Optional design, API, review, testing, deployment, and bug documents
are created only with `ap.py scaffold <group> --write`.

For existing projects:

```bash
autocoding sync --projects .
python3 docs/tools/autopipeline/ap.py upgrade --dry-run
python3 docs/tools/autopipeline/ap.py upgrade --write
```

Upgrade preserves project documents, custom agents, and explicit local model
overrides. Managed agents without a `model` inherit the current client model.
Initialization is incomplete until every URL, username, and direct password under
`access.*` is filled in `docs/ENGINEERING.md` and `doctor` passes.

## Configuration and profiles

Read `docs/ENGINEERING.md` before choosing a path. `workflow.profile: auto`
resolves to exactly one execution profile:

- `micro`: docs/tests-only or isolated low-risk work.
- `standard`: ordinary feature or defect work.
- `high-risk`: DB, auth, payment, deployment/build, or broad structural work.

Use profiles only to adjust analysis, design depth, and reviewer recommendations.
Run exactly one changed-scope fast local gate for every profile. Keep standard/full
regression, structure scans, Docker, API verification, Jenkins, deployment, and
target checks as explicit diagnostics outside the default development flow.

Run the configuration and impact preflight:

```bash
python3 docs/tools/autopipeline/ap.py doctor
python3 docs/tools/autopipeline/ap.py classify --scope auto
```

`light-gate` remains available for an explicit gate-diagnostic task. Do not run
it before normal `commit-push`; `commit-push` owns the single automatic gate.

## Parallel write isolation

Every task that may write files must use its own registered Git worktree and
task branch. Read-only discovery may stay in the primary worktree.

```bash
python3 docs/tools/autopipeline/ap.py task-start <TASK_ID>
# Continue in the worktree path printed by task-start.
python3 docs/tools/autopipeline/ap.py task-status <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-submodule-sync <TASK_ID>
python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> --msg "<TASK_ID>: <summary>"
python3 docs/tools/autopipeline/ap.py task-integrate <TASK_ID>
```

`task-start` records the base revision, target branch, task branch, and worktree
in the repository manifest. `commit-push` is valid only inside that task's
registered worktree and may stage only changes owned by that task. If unknown
changes appear, stop and report them. Never restore, reset, stash, clean, or
otherwise modify another task's or the user's changes.

Treat `commit-push` plus `task-integrate` as one push stage. Run the fast gate
only in `commit-push`; integration fetches/rebases, safely pushes the target, and
cleans the task without repeating the gate. Successful target push ends the
coding task. Do not wait for or inspect Jenkins/build/deploy results afterward.
The task commit runs project commit hooks once. The internal backup task-branch
push skips the pre-push hook; the final target-branch push runs it once.
Integration creates no second evidence commit.

After a successful integration, remove the clean worktree and merged local task
branch. Delete the merged remote task branch by default. Use `task-finish` to
retry cleanup for one integrated task and `task-prune` to clean registered merged
tasks in bulk. Refuse cleanup when a worktree is dirty or a branch is unmerged.
Do not update the primary checkout during integration; pull it explicitly when
its user-owned state is ready. Treat unknown ignored files as user data and
block cleanup; allow only explicitly disposable cache/build paths. Before a
forced task-worktree removal, recursively require every initialized submodule
to be clean and contain no unknown ignored data, local-only history, or
unmirrored local branch. Block cleanup when the submodule has another linked
worktree or its remotes cannot be refreshed. Before the validated forced removal,
persist its refs and reflog commits in the Git common directory's managed
submodule-recovery store so a remote race cannot erase the final copy. Never run
submodule deinit from a linked task worktree because its shared config can alter
the primary checkout.

`task-start` enables Git worktree-scoped config and seeds task-local submodule
URLs. After editing `.gitmodules`, run `task-submodule-sync` before submodule
initialization or sync. Resolve relative URLs with Git's current-worktree
default-remote semantics, not the integration remote. If shared/common submodule
config differs from the task-start snapshot, stop and report it without restoring
or overwriting the value. Treat residual module Git directories from a manual
deinit/removal as user data: block forced cleanup until they are reinitialized or
explicitly recovered.

## Development closure

1. Start the write task with `task-start` and enter its registered worktree.
2. Locate the real entry point, call chain, existing owner module, tests, and
   reusable helpers.
3. Update the active task with the smallest useful design note.
4. Create DD/ADR only for cross-module, API, DB, deployment/CI, security, key UI
   flow, or lasting structural decisions.
5. Implement only necessary changes.
6. Run `commit-push`; it executes the changed-scope fast gate once, records
   `DEV-CLOSED`, commits, and pushes the task branch.
7. Run `task-integrate` to push the target branch and clean the task worktree and
   merged task branches.
8. Stop. Jenkins owns later build/deploy work and the project owner owns actual
   acceptance. Ignore later external failures unless the user opens a diagnostic task.

## Structure policy

Follow repository-native architecture first. Generic file-size, function-size,
and regex import rules are advisory unless the project explicitly sets
`structure.enforcement: blocking`. Search for reusable utilities, components,
clients, validation, permissions, caching, retry, and automation before adding
new helpers. Do not split files only to reduce line count.

For repository-wide structural reviews, generate and read the health baseline
and optimization backlog. Accepted debt is not a fresh blocker unless it worsens.

```bash
python3 docs/tools/autopipeline/ap.py baseline init --write --update-config
```

## Collaboration roles

Role templates provide behavior and permission boundaries, while the active
client supplies the available model unless a project keeps an explicit override.
`classify` recommends only roles justified by the effective profile:

- `explorer`: read-only repository discovery and root-cause tracing.
- `docs_researcher`: current official API/version research.
- `browser_debugger`: UI reproduction and browser evidence.
- `fixer`: bounded implementation after scope is clear.
- `reviewer`: correctness, security, regression, and evidence review.

The main agent owns framing, architecture decisions, the fast gate, integration,
closure records, and Git state through successful push.

## Tool routing

- Local code, tests, gates, and Git: shell, repository scripts, and `ap.py`.
- Current library/API behavior: official documentation MCP or matching skill.
- UI: in-app browser for local pages, Chrome for existing logged-in state,
  Playwright for deterministic automation, Computer Use for unsupported native UI.
- PR/issue state: GitHub connector; local Git for local changes and pushes.
- Design, security, analytics, and document artifacts: use the matching installed
  skill or connector before manual recreation.
- Credentials: use the direct values configured under `access.*` in
  `docs/ENGINEERING.md`; do not invent or echo values unnecessarily.

## Optional documents and operations

```bash
python3 docs/tools/autopipeline/ap.py scaffold all --write
python3 docs/tools/autopipeline/ap.py docs-ledger-check
python3 docs/tools/autopipeline/ap.py docs-ledger-archive --plan
python3 docs/tools/autopipeline/ap.py gate-profile
python3 docs/tools/autopipeline/ap.py task-start <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-status <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-submodule-sync <TASK_ID>
python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> --msg "<TASK_ID>: <summary>"
python3 docs/tools/autopipeline/ap.py task-integrate <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-finish <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-prune
```

`status` and `sync` manage only the minimal required scaffold. Existing optional
documents and legacy tool copies are preserved but do not count as drift.
