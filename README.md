# auto-coding-skill

A generic `.agents` engineering workflow with isolated parallel worktrees, fast
local validation, push-based completion, required access configuration, and safe
branch cleanup.

## What changed in v3.0.1

- Fixed normal development to analysis → decomposition → design → development →
  one changed-scope fast gate → push.
- Kept risk profiles for planning/review depth without promoting local work to a
  standard/full gate or verify mode.
- Ended coding tasks immediately after safe target-branch push; Jenkins owns
  later build/deploy work and the project owner owns acceptance.
- Removed repeated integration gates and all automatic post-push Jenkins/target
  polling from `commit-push`.
- Required all project/Jenkins/GitLab/Nexus URLs, usernames, and direct passwords
  under `access.*` during project initialization.
- Removed the shared-checkout `legacy` escape hatch; worktree isolation is now
  mandatory for every write task.
- Added a structured subagent plan with parallel discovery, one-writer worktree
  ownership, reviewer feedback loops, and main-agent Git lifecycle ownership.
- Enforced task-owned paths, dependency revisions, writer leases, and
  fingerprint-bound review approvals in the task runtime.
- Added review, writer handoff, and conflicted-rebase resume lifecycle commands.
- Added planned paths and task intent to pre-development classification and
  published a stable orchestration contract.
- Added controlled `ENGINEERING.md` workflow synchronization while preserving
  project configuration and custom content.

## What changed in v3.0.0

- Isolated every write task in a registered Git worktree and task branch.
- Added `task-start`, `task-status`, `task-submodule-sync`, `task-integrate`,
  `task-finish`, and `task-prune` lifecycle commands.
- Made `commit-push` validate the task manifest before any gate or ledger write,
  stage only the task worktree's exact paths, and detect gate-time mutations.
- Added task-scoped active, closure, and evidence records to avoid shared append
  conflicts.
- Serialized target-branch integration and re-ran the resolved gate after
  updating to the latest remote target.
- Automatically removed integrated worktrees and local task branches, with safe
  lease-based remote task-branch cleanup and merged-branch pruning.
- Initially kept a `legacy` compatibility escape hatch; v3.0.1 removes that path and
  migrates existing configuration to mandatory worktree isolation.

## What changed in v2.2.1

- Made same-period ledger archiving update one cumulative archive-index entry
  instead of appending duplicate month headings.
- Recognized Markdown-wrapped and localized settled statuses such as
  `` `Done / PASS` `` and `Done（PASS）` during physical history archiving.
- Added regression coverage for repeated same-month archives and these status
  formats.

## What changed in v2.2.0

- Added `micro`, `standard`, and `high-risk` execution profiles.
- `workflow.profile: auto` classifies changed work and cannot downgrade detected
  high-risk changes.
- High-risk and explicit verify work now require a real `gate_full`/`full_gate`;
  light and standard commands are no longer accepted as full-gate fallbacks.
- Generic structure checks are advisory by default. Projects can opt into
  blocking enforcement.
- Reduced a new project scaffold from 46 files / about 10,120 lines to 20 files /
  about 5,300 lines.
- Replaced duplicated repository-side Python tools with a small launcher that
  delegates to the single project-local skill runtime.
- Kept only ENGINEERING, taskbook, and closure log in the default documentation
  scaffold; all specialized documents are materialized on demand.
- Removed hard-coded model names from managed Agent templates. New installs
  inherit the active client model; existing project model overrides survive sync.
- Added behavioral regression tests for profile resolution, strict full gates,
  advisory structure checks, minimal scaffold budgets, on-demand docs, and Agent
  model inheritance.

This section records historical v2 behavior. The v3.0.1 workflow above supersedes
its full-gate and verify-mode rules for normal development.

## Install

```bash
npm install -g @elvis1513/auto-coding-skill
autocoding init
autocoding sync --projects .
pip install pyyaml requests
```

`autocoding init` installs the project-local skill and five managed roles under
`.agents`. `autocoding sync` installs the minimal project scaffold:

```text
.agents/skills/auto-coding-skill/
.agents/agents/
docs/ENGINEERING.md
docs/tasks/taskbook.md
docs/tasks/closure-log.md
docs/tools/autopipeline/ap.py
```

The `docs/tools` entry point is a compatibility launcher. Runtime code lives only
under `.agents/skills/auto-coding-skill/scripts`.

## Execution profiles

Configure the selector in `docs/ENGINEERING.md`:

```yaml
workflow:
  mode: dev
  profile: auto
  completion: push
```

| Effective profile | Intended work | Local gate | Completion |
| --- | --- | --- | --- |
| `micro` | docs/tests-only or explicitly isolated work | changed/quick | pushed |
| `standard` | normal feature and defect work | changed/quick | pushed |
| `high-risk` | sensitive, broad, deploy/build, or structural work | changed/quick | pushed |

`auto` is a selector, not a fourth effective profile. Profiles affect analysis,
design depth, and reviewer recommendations only. They never expand the automatic
local gate or turn Jenkins/target verification into a completion condition.

An explicit configured `micro`, `standard`, or `high-risk` profile replaces
auto's low/normal baseline and acts as a floor for CLI overrides. Independently
detected high-risk signals still force `high-risk`.

Inspect the plan:

```bash
python3 docs/tools/autopipeline/ap.py classify --scope auto
python3 docs/tools/autopipeline/ap.py impact --scope auto --json
```

Each result includes the effective profile, fixed fast gate scope, reasons,
recommended Agent roles, and a machine-readable `agent_plan` describing stages,
dependencies, assignment/result contracts, and lifecycle ownership.

## Parallel write isolation

Each task that may write files runs in its own registered Git worktree and
`codex/` task branch. `worktree` is the only supported isolation value. Each
worktree has exactly one writer; read-only discovery may remain in the primary
worktree.

```yaml
concurrency:
  isolation: worktree
  base_ref: origin/dev
  target_branch: dev
  branch_prefix: codex/
  worktree_root: ../.worktrees
  cleanup_merged: true
  delete_remote_branch: true
  disposable_ignored: []
```

```bash
python3 docs/tools/autopipeline/ap.py task-start T0001 --owned-path src --writer "$FIXER"
# Continue in the worktree path printed by task-start.
python3 docs/tools/autopipeline/ap.py task-status T0001
python3 docs/tools/autopipeline/ap.py task-submodule-sync T0001
python3 docs/tools/autopipeline/ap.py task-review T0001 --verdict approved --diff-fingerprint "$SHA256"
python3 docs/tools/autopipeline/ap.py task-handoff T0001 --from "$FIXER" --to "$CODEX_THREAD_ID" --generation 1
python3 docs/tools/autopipeline/ap.py commit-push T0001 --writer "$CODEX_THREAD_ID" --msg "T0001: summary"
python3 docs/tools/autopipeline/ap.py task-integrate T0001 --writer "$CODEX_THREAD_ID"
```

`commit-push` runs only inside the task worktree recorded in the repository
manifest and stages only that task's changes. Unknown changes stop the command;
the workflow never restores, resets, stashes, or cleans them.

Before upgrading a v3.0.0 project, finish and clean every registered in-flight
task with its currently installed runtime. `autocoding sync` refuses to replace
that runtime while a schema-1 task remains, because 3.0.1 cannot safely infer
its path ownership, dependencies, writer lease, or review state.

`commit-push` runs the only local gate. `task-integrate` is the rest of the same
push stage: it fetches/rebases, CAS-pushes the configured target, confirms the
remote SHA, and cleans up without repeating the gate. Successful integration
ends the coding task; do not wait for Jenkins, deployment, or acceptance results.
The task commit runs project commit hooks once. Its internal backup-branch push
skips the pre-push hook, while the final target-branch push runs that hook once.
Integration does not create a second evidence commit.

Successful integration removes the clean worktree and merged local branch, and
deletes the merged remote task branch by default. `task-finish T0001` retries
cleanup for one integrated task; `task-prune` removes registered merged tasks
left behind. Dirty worktrees and unmerged branches are never removed. Integration
does not update the primary checkout; pull it explicitly when its local state is
ready. Cleanup also refuses unknown ignored files such as local secrets; list
only disposable project cache/build paths under `concurrency.disposable_ignored`.
Initialized submodules are recursively checked before forced task-worktree
removal: they must be clean and contain no unknown ignored data, local-only
commits, unmirrored local branches, or additional linked worktrees. Their
remotes are refreshed before that decision. A durable snapshot
of refs and reflog commits is stored under Git's
`auto-coding-skill/submodule-recovery` state before forced worktree removal, so
a remote deletion race cannot destroy the last copy of a commit. Cleanup never
deinitializes the primary checkout's shared submodule configuration.
`task-start` enables Git worktree-scoped config and seeds each task's submodule
URLs. After changing `.gitmodules`, run `task-submodule-sync` before initializing
or syncing modules. Relative URLs follow Git's current-worktree default-remote
rules, including task bases whose `.gitmodules` differs from the control checkout.
Shared/common submodule config changes are reported and never overwritten.
Residual Git directories from modules manually deinitialized inside a task block
forced cleanup until they are reinitialized or recovered.

## Gate configuration

```yaml
commands:
  gate_changed: "git diff --check"

gate:
  default_scope: auto
  rules:
    - name: payments
      paths: ["src/payments/**"]
      profile: high-risk
```

Rules affect classification and planning only. Legacy `scope` or `commands`
inside a rule never execute automatically; invoke an explicitly configured
diagnostic with `ap.py run <name>` when the user asks for it.

For Node projects, a new scaffold selects `npm run test:changed` only when that
dedicated quick script exists. It never promotes ordinary `npm test`, builds, or
full regression into the automatic changed gate. Standard/full commands may be
kept as explicit diagnostics, but normal development does not invoke them.

## Structure policy

The generic checker remains useful for surfacing large files, large additions,
function-size signals, and import-direction heuristics, but it is not universally
authoritative:

```yaml
structure:
  enabled: true
  enforcement: advisory # advisory | blocking
  architecture_standard: project-defined
```

`advisory` reports findings without blocking. Projects with reliable, tailored
rules can opt into `blocking`. Repository-native architecture, compiler output,
tests, and real dependency graphs take precedence over generic path heuristics.

## Optional documentation

Specialized templates are created only when required:

```bash
python3 docs/tools/autopipeline/ap.py scaffold api --write
python3 docs/tools/autopipeline/ap.py scaffold design --write
python3 docs/tools/autopipeline/ap.py scaffold architecture --write
python3 docs/tools/autopipeline/ap.py scaffold review --write
python3 docs/tools/autopipeline/ap.py scaffold testing --write
python3 docs/tools/autopipeline/ap.py scaffold deployment --write
python3 docs/tools/autopipeline/ap.py scaffold bugs --write
python3 docs/tools/autopipeline/ap.py scaffold all --write
```

The command is idempotent and does not overwrite existing project documents
unless `--force` is supplied. `baseline init` and `gen-summary` generate their
outputs directly without static templates.

For a one-step legacy-style full scaffold:

```bash
python3 .agents/skills/auto-coding-skill/scripts/ap.py --repo . install --full
```

## Dynamic Agents and models

Managed role templates define role instructions, permissions, and reasoning
effort but do not pin a model. The current client therefore supplies a supported
model automatically.

Existing project-local `model = "..."` lines are treated as explicit overrides:

- `status` reports them but does not mark the project stale for model-only drift.
- `sync` updates managed instructions while preserving the override.
- `sync --reset-agent-models` removes managed-role overrides and returns to
  client inheritance.
- Custom Agent files are always preserved byte-for-byte.

The effective profile emits an executable collaboration shape:

- micro: main Agent only unless useful independent work exceeds dispatch overhead
- standard/high-risk: main decomposition → parallel justified explorer/docs/browser
  discovery → main design → dependency waves of isolated fixers → read-only
  reviewers → main fast gate/integration, followed by final push/cleanup

Only dependency-free fixer units with explicitly non-overlapping paths may run
in parallel. A dependent writer starts after its prerequisite is integrated.
Subagents do not commit, push, integrate, clean branches, or run the project gate.
Reviewer findings return to the owning fixer. Verdicts bind to a diff fingerprint,
so any edit requires re-review before the main Agent may run the gate.

## Required access configuration

For a new project, `autocoding sync` creates `access.project`, `access.jenkins`,
`access.gitlab`, and `access.nexus` in `docs/ENGINEERING.md`. Existing projects
must run `ap.py upgrade --write` to merge newly required fields into their manual
configuration. Fill every URL, username, and direct password during
initialization as an inline YAML string; quote values that resemble numbers,
dates, booleans, or YAML collections. `status` rejects blank/TODO fields;
`doctor` and `task-start`
also validate URL shape locally. These access checks never contact the listed
service endpoints; after validation, `task-start` may still fetch the configured
Git remote unless `--no-fetch` is used. Configuration presence does not enable
Jenkins/build/deploy verification.

## Core commands

```bash
python3 docs/tools/autopipeline/ap.py doctor
python3 docs/tools/autopipeline/ap.py classify --scope auto
python3 docs/tools/autopipeline/ap.py light-gate --scope auto --explain
python3 docs/tools/autopipeline/ap.py structure-check --scope auto
python3 docs/tools/autopipeline/ap.py task-start T0001 --owned-path src --writer "$FIXER"
python3 docs/tools/autopipeline/ap.py task-status T0001
python3 docs/tools/autopipeline/ap.py task-submodule-sync T0001
python3 docs/tools/autopipeline/ap.py task-review T0001 --verdict approved --diff-fingerprint "$SHA256"
python3 docs/tools/autopipeline/ap.py task-handoff T0001 --from "$FIXER" --to "$CODEX_THREAD_ID" --generation 1
python3 docs/tools/autopipeline/ap.py docs-ledger-check
python3 docs/tools/autopipeline/ap.py gate-profile
python3 docs/tools/autopipeline/ap.py commit-push T0001 --writer "$CODEX_THREAD_ID" --msg "T0001: summary"
python3 docs/tools/autopipeline/ap.py task-integrate T0001 --writer "$CODEX_THREAD_ID"
python3 docs/tools/autopipeline/ap.py task-finish T0001
python3 docs/tools/autopipeline/ap.py task-prune
```

## Upgrade and multi-project sync

```bash
autocoding sync --projects /path/a,/path/b

python3 docs/tools/autopipeline/ap.py upgrade --dry-run
python3 docs/tools/autopipeline/ap.py upgrade --write

autocoding status --projects /path/a,/path/b
autocoding sync --projects /path/a,/path/b --dry-run
```

For a v2.1 project, run the new CLI sync first; invoking its old project-local
`upgrade` command would still execute v2.1 logic. Upgrade and sync preserve
existing optional docs, legacy `core.py` /
`http_checks.py` tool copies, custom Agents, and project-specific configuration.
Retired template files do not count as drift.

## Development

Normal changes should use the configured changed-scope gate only. The commands
below are explicit package-maintainer diagnostics, not the default project
development gate:

```bash
npm run test:src
npm test
npm run release:check
```

Run `npm run sync-assets` explicitly after source changes. `release:check` is a
read-only release gate: it rejects asset drift, validates Python 3.11 grammar and
TOML, runs the broader regressions, and performs `npm pack --dry-run`.

License: MIT.
