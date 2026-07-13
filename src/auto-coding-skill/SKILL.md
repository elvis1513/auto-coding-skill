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
The main agent decomposes the task before dispatch. Run independent read-only
discovery roles in parallel when the runtime supports them. Assign each
independent write unit to exactly one fixer in its own registered worktree;
never share a write worktree between agents.

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
# Before development, add repeatable --planned-path values and either --intent
# or --intent-file when the working tree does not yet describe the task.
```

`light-gate` remains available for an explicit gate-diagnostic task. Do not run
it before normal `commit-push`; `commit-push` owns the single automatic gate.

## Parallel write isolation

Every task that may write files must use its own registered Git worktree and
task branch. Read-only discovery may stay in the primary worktree. A registered
worktree has exactly one writer. The main agent and other fixers must not edit it
while its owning fixer is active.

```bash
python3 docs/tools/autopipeline/ap.py task-start <TASK_ID> \
  --owned-path <PATH> --depends-on <TASK_ID=SHA> --writer <WRITER>
# Continue in the worktree path printed by task-start.
python3 docs/tools/autopipeline/ap.py task-status <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-submodule-sync <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-review <TASK_ID> \
  --verdict approved --diff-fingerprint <SHA256> --reviewer <REVIEWER>
python3 docs/tools/autopipeline/ap.py task-handoff <TASK_ID> \
  --from <WRITER> --to <WRITER> [--generation <N>]
python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> \
  --msg "<TASK_ID>: <summary>" [--writer <WRITER>]
python3 docs/tools/autopipeline/ap.py task-integrate <TASK_ID>
# After resolving an integration rebase conflict:
python3 docs/tools/autopipeline/ap.py task-resume <TASK_ID>
```

`task-start` records the base revision, target branch, task branch, worktree,
owned paths, prerequisite task SHAs, and writer lease in the repository manifest.
Pass one `--owned-path` per owned path and one `--depends-on TASK_ID=SHA` per
prerequisite. The writer defaults to `CODEX_THREAD_ID`; pass `--writer` only when
an explicit stable identity is needed. Use `task-handoff` for an intentional
lease transfer; its generation check prevents a stale writer from reclaiming the
task. `commit-push` is valid only for the active writer inside the registered
worktree and may stage only owned paths. If unknown changes appear, stop and
report them. Never restore, reset, stash, clean, or otherwise modify another
task's or the user's changes.

After a reviewer returns, the main agent records the verdict and exact 64-character
diff fingerprint with `task-review`. Any content change invalidates that review.
`commit-push` and `task-integrate` require a current approval for the current
fingerprint and verify prerequisite SHAs. If integration enters a rebase conflict,
resolve it in the registered worktree, continue or abort the rebase as instructed,
then run `task-resume`; do not bypass the conflicted manifest state.

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

1. The main agent analyzes and decomposes the request into bounded units with
   explicit dependencies, acceptance criteria, and owned paths.
2. Run justified `explorer`, `docs_researcher`, and `browser_debugger` discovery
   in parallel, then let the main agent merge their evidence into one design.
3. Create DD/ADR only for cross-module, API, DB, deployment/CI, security, key UI
   flow, or lasting structural decisions.
4. Start one registered task worktree per independent write unit and assign one
   fixer to it. Parallelize only dependency-free units with non-overlapping paths;
   deliver implementation → review → gate/integration in dependency waves, and
   start the next wave only after its prerequisites are integrated.
5. Review each stable diff with a read-only reviewer. Route blocking findings to
   the owning fixer and re-review after any change. The main agent records the
   current verdict with `task-review`, then hands the writer lease back before Git
   closure when required.
6. After all agents have returned, the main agent runs `commit-push` for each
   write task; it executes the changed-scope fast gate once, records
   `DEV-CLOSED`, commits, and pushes the task branch.
   If that configured fast gate fails only because a dependency already present
   in the lockfile is not installed locally, restore the locked dependencies and
   rerun that same fast gate once. Missing dependencies in an accidentally or
   explicitly invoked standard/full diagnostic do not justify dependency
   installation or a full-gate rerun.
7. The main agent runs `task-integrate` in dependency order to push the target
   branch and clean every task worktree and merged task branch.
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
`classify` returns both justified roles and a structured `agent_plan`:

- `explorer`: read-only repository discovery and root-cause tracing.
- `docs_researcher`: current official API/version research.
- `browser_debugger`: UI reproduction and browser evidence.
- `fixer`: bounded implementation after scope is clear.
- `reviewer`: correctness, security, regression, and evidence review.

For standard and high-risk write tasks, use the following fan-out/fan-in contract:

1. The main agent owns decomposition and supplies every subagent with `task_id`,
   role, scope, dependencies, acceptance criteria, and expected output.
2. Discovery roles are read-only and may run in parallel. Browser work is limited
   to requested reproduction/evidence; it does not replace owner acceptance.
3. Each fixer receives a task branch, absolute worktree path, and owned paths.
   It may edit only that worktree and must not commit, push, integrate, clean, or
   run the project gate.
4. Each reviewer receives a stable diff and binds approved or changes-requested
   to its fingerprint. Changes go back to the same fixer and invalidate approval.
5. Every subagent returns exactly one JSON object conforming to
   `data/contracts/orchestration-v1.schema.json#/$defs/agentResult`, with integer
   `contract_version: 1`. It includes node/task/role, base SHA, dependencies,
   owned and changed paths, diff fingerprint, evidence, findings, verdict, risks,
   and next owner. Read-only roles return no changed paths.
6. The main agent alone owns architecture decisions, the single fast gate per
   write task, closure records, commits, integration, push, and branch cleanup.

Micro tasks stay main-agent-only unless they contain genuinely independent work
whose benefit exceeds delegation overhead. If subagents are unavailable, the
main agent executes the same stages sequentially without weakening isolation.

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
python3 docs/tools/autopipeline/ap.py task-start <TASK_ID> --owned-path <PATH> [--depends-on <TASK_ID=SHA>] [--writer <WRITER>]
python3 docs/tools/autopipeline/ap.py task-status <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-submodule-sync <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-review <TASK_ID> --verdict <VERDICT> --diff-fingerprint <SHA256> [--reviewer <REVIEWER>]
python3 docs/tools/autopipeline/ap.py task-handoff <TASK_ID> --from <WRITER> --to <WRITER> [--generation <N>]
python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> --msg "<TASK_ID>: <summary>" [--writer <WRITER>]
python3 docs/tools/autopipeline/ap.py task-integrate <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-resume <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-finish <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-prune
```

`status` and `sync` manage only the minimal required scaffold. Existing optional
documents and legacy tool copies are preserved but do not count as drift.
