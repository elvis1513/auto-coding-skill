---
workflow:
  mode: "dev"
  profile: "auto"

project:
  name: ""
  repo_root: "."
  stack: "generic"

concurrency:
  isolation: "worktree"
  base_ref: ""
  target_branch: ""
  branch_prefix: "codex/"
  worktree_root: "../.worktrees"
  cleanup_merged: true
  delete_remote_branch: true
  disposable_ignored: []

commands:
  gate_changed: ""
  gate_standard: ""
  gate_full: ""

gate:
  default_scope: "auto"
  fallback_scope: "standard"
  full_on_unknown: true
  no_change_scope: "standard"
  profile_log: ".local/auto-coding-skill/gate-profile.jsonl"
  full_on:
    paths:
      - "Jenkinsfile"
      - "Jenkinsfile.*"
      - ".github/workflows/**"
      - "Dockerfile"
      - "**/Dockerfile"
      - "docker-compose*.yml"
      - "docker-compose*.yaml"
      - "compose*.yml"
      - "compose*.yaml"
      - "docs/ENGINEERING.md"
      - "docs/tools/autopipeline/**"
      - "package-lock.json"
      - "pnpm-lock.yaml"
      - "yarn.lock"
      - "go.mod"
      - "go.sum"
      - "Cargo.lock"
      - "pom.xml"
      - "build.gradle*"
      - "settings.gradle*"
  rules: []

structure:
  enabled: true
  enforcement: "advisory"
  architecture_standard: "project-defined"
  max_file_lines_warn: 800
  max_file_lines_block: 1500
  max_function_lines_warn: 120
  max_added_lines_to_large_file: 80
  require_reuse_search: true
  block_new_responsibility_in_large_file: true
  allow_large_files:
    - ".agents/skills/**"
    - "docs/tools/autopipeline/**"
    - "generated/**"
    - "**/generated/**"
    - "vendor/**"
    - "dist/**"
    - "build/**"
    - "target/**"
    - "node_modules/**"
    - "**/*.generated.*"
    - "**/*.min.js"
    - "**/*.map"
  accepted_debt_paths: []
  layer_rules:
    enabled: true
    block: false

optimization:
  completion_policy: "baseline-aware"
  require_baseline_for_global_review: false
  report_accepted_debt_as_findings: false

verification:
  target_env_required: false
  jenkins_required: false

docs:
  taskbook: "docs/tasks/taskbook.md"
  closure_log: "docs/tasks/closure-log.md"
  evidence_log: "docs/tasks/evidence.jsonl"
  active_task_dir: "docs/tasks/active"
  task_closure_dir: "docs/tasks/closures"
  task_evidence_dir: "docs/tasks/evidence"
  design_dir: "docs/design"
  task_archive_dir: "docs/tasks/archives"
  design_archive_dir: "docs/archive/design"
  archive_index: "docs/tasks/archive-index.md"
  ledger_check_enabled: true
  ledger_block_on_exceed: true
  active_taskbook_max_lines: 1200
  active_closure_log_max_lines: 800
  active_design_max_files: 120
  health_baseline: "docs/reviews/project-health-baseline.md"
  optimization_backlog: "docs/reviews/optimization-backlog.md"
  structure_standard: "docs/architecture/structure-standard.md"
  api_docs_required: false
  api_doc: "docs/interfaces/api.md"
  api_change_log: "docs/interfaces/api-change-log.md"
  regression_matrix: "docs/testing/regression-matrix.md"
  bug_list: "docs/bugs/bug-list.md"
  summary_dir: "docs/tasks/summaries"
---

# Engineering Workflow

This file is the single manually maintained workflow configuration. Keep it in
Git. Add optional sections only when the project enables the related surface.

## Execution profiles

`workflow.profile: auto` selects one of three effective profiles:

| Profile | Typical work | Gate | Closure mode |
| --- | --- | --- | --- |
| `micro` | docs/tests-only, very small isolated work | changed | dev |
| `standard` | ordinary feature and defect work | standard | dev |
| `high-risk` | DB/auth/payment/deploy/build config or declared high risk | full | verify |

`auto` is only a selector. The effective profile is always `micro`, `standard`,
or `high-risk`. A high-risk signal cannot be downgraded with a CLI flag or a
project rule. An explicit non-auto profile replaces auto's low/normal baseline.
`workflow.mode: verify` also requires the full gate.

Project `gate.rules` may declare `paths`, `commands`, `scope`, and an optional
`profile`. Configure `commands.gate_full` (or legacy `commands.full_gate`) for
high-risk work; a light or standard command does not count as a full gate.

## Minimal configuration

Required for normal development:

- `workflow.mode`: `dev` or `verify`
- `workflow.profile`: `auto`, `micro`, `standard`, or `high-risk`
- `project.name`
- `concurrency.isolation`: keep `worktree` for every task that may write files
- `concurrency.base_ref` and `target_branch`: leave blank to derive the current
  upstream, or set them explicitly for a fixed integration branch
- `concurrency.branch_prefix` and `worktree_root`
- `concurrency.cleanup_merged` and `delete_remote_branch`: keep both enabled to
  remove integrated temporary worktrees and branches
- `concurrency.disposable_ignored`: add only project-specific ignored cache/build
  paths that may be discarded with a task worktree; ignored secrets and unknown
  paths block cleanup, including inside initialized submodules
- at least one usable gate command; configure all three gate commands when the
  project can exercise changed, standard, and full scopes
- `verification.target_env_required` and `verification.jenkins_required`

Legacy command keys such as `commands.light_gate`, `quick_test`, `test`, and
`build` remain supported. Run `doctor` for exact missing-field diagnostics.

When target verification is enabled, add `target_env.health_base_url` and
`health_path`. Add frontend/backend URLs only for requested endpoint checks, and
login/secret references only when basic auth is requested. When Jenkins is
enabled, add `jenkins` with its base/job URLs, branch, artifact/deploy metadata,
timeout, UI/API users, and password values or environment references. Unused
sections should remain absent rather than filled with placeholders.

## Concurrent write tasks

Run every write task in a registered Git worktree and task branch. Do not share
the primary worktree between writers.

```bash
python3 docs/tools/autopipeline/ap.py task-start <TASK_ID>
# Enter the worktree path printed by task-start.
python3 docs/tools/autopipeline/ap.py task-status <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-submodule-sync <TASK_ID>
python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> --msg "<TASK_ID>: <summary>"
python3 docs/tools/autopipeline/ap.py task-integrate <TASK_ID>
```

`task-start` fixes the task's base revision and records its task branch and
worktree in the repository manifest. Run `commit-push` only from that registered
worktree. Stage only task-owned paths. If an unknown change appears, stop and
report it; never restore, reset, stash, clean, or otherwise alter it.

Successful integration removes the clean worktree and merged local branch, and
deletes the merged remote task branch by default. Use `task-finish <TASK_ID>` to
retry cleanup for one integrated task and `task-prune` for registered merged
tasks left behind. Cleanup must refuse dirty worktrees and unmerged branches.
Before forced task-worktree removal, recursively require initialized submodules
to be clean and contain no unknown ignored data, local-only history, or
unmirrored local branches. A submodule with another linked worktree or an
unrefreshable remote blocks cleanup. Before forced worktree removal, persist its
refs and reflog commits in the managed Git-common-dir submodule recovery store.
Do not run submodule deinit from a linked task worktree because its shared config
can alter the primary checkout.
`task-start` enables worktree-scoped Git config and seeds task-local submodule
URLs. After changing `.gitmodules`, run `task-submodule-sync` before submodule
initialization or sync. Resolve relative URLs with Git's current-worktree
default-remote semantics. If shared/common submodule config changed after task
start, report and stop without restoring or overwriting it. Residual module Git
directories from a manual deinit or removal block forced cleanup until they are
reinitialized or recovered.
Integration must not update the primary checkout; pull it explicitly only when
its user-owned state is ready.

## Default workflow

Development:

1. Read this file and the active task entry.
2. Start the write task with `task-start` and enter its registered worktree.
3. Run or reason through `classify --scope auto`.
4. Record the smallest useful design note; create DD/ADR only when indicated.
5. Implement the necessary change using existing project structure and reuse points.
6. Run the resolved profile gate.
7. Record `DEV-CLOSED`, commit, push, integrate, and clean the task worktree.

High-risk or explicit verification:

1. Run the real full gate.
2. Commit and push.
3. Verify enabled CI/Jenkins and target-environment surfaces.
4. Record `PASS`, `FAIL`, or `PARTIAL` from actual evidence.
5. Integrate successful work and clean its temporary worktree and branches.

The authoritative order remains ENGINEERING, taskbook/archives, design and
interface records, regression/bug records, closure evidence, deployment records,
then implementation. Do not mark unexecuted checks as PASS.

## Structure policy

Generic structure checks are advisory by default. They may report file size,
function size, or regex-based import-boundary signals, but they block only when
`structure.enforcement: blocking` is explicitly configured. Repository-native
architecture and compiler/test evidence take precedence over generic naming
heuristics. Reuse existing helpers and avoid adding unrelated responsibilities
to already large files; do not split code merely to satisfy a line count.

Use `baseline init --write --update-config` for repository-wide structural work.
Accepted historical debt belongs in the generated baseline/backlog.

## Core and optional documents

The default scaffold contains only this file, taskbook, and closure log. Create
specialized documents when the task needs them:

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

`baseline init` and `gen-summary` generate their outputs directly. The active
taskbook, closure log, and top-level DD files are bounded working ledgers; use
`docs-ledger-archive --plan` before archiving closed history.

## Common commands

```bash
python3 docs/tools/autopipeline/ap.py doctor
python3 docs/tools/autopipeline/ap.py classify --scope auto
python3 docs/tools/autopipeline/ap.py light-gate --scope auto --explain
python3 docs/tools/autopipeline/ap.py structure-check --scope auto
python3 docs/tools/autopipeline/ap.py task-start <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-status <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-submodule-sync <TASK_ID>
python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> --msg "<TASK_ID>: <summary>"
python3 docs/tools/autopipeline/ap.py task-integrate <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-finish <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-prune
python3 docs/tools/autopipeline/ap.py docs-ledger-check
python3 docs/tools/autopipeline/ap.py gate-profile
```

The launcher under `docs/tools/autopipeline` delegates to the single runtime in
`.agents/skills/auto-coding-skill/scripts`; do not duplicate that runtime.
