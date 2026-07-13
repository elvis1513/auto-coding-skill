---
workflow:
  mode: "dev"
  profile: "auto"
  completion: "push"

project:
  name: ""
  repo_root: "."
  stack: "generic"

access:
  project:
    frontend:
      url: ""
      username: ""
      password: ""
    backend:
      url: ""
      username: ""
      password: ""
  jenkins:
    frontend:
      url: ""
      username: ""
      password: ""
    backend:
      url: ""
      username: ""
      password: ""
  gitlab:
    url: ""
    username: ""
    password: ""
  nexus:
    frontend:
      url: ""
      username: ""
      password: ""

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
  gate_changed: "git diff --check"

gate:
  default_scope: "changed"
  fallback_scope: "changed"
  full_on_unknown: false
  no_change_scope: "changed"
  profile_log: ".local/auto-coding-skill/gate-profile.jsonl"
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

<!-- auto-coding-skill:managed-workflow:start version=3.0.2 -->

This file is the single project workflow configuration. Keep it in Git. Its YAML
frontmatter and content outside these versioned markers are manually maintained;
`autocoding sync` updates only this managed workflow block. Fill every access URL,
username, and password during project initialization.

## Execution profiles

`workflow.profile: auto` selects one of three effective profiles:

| Profile | Typical work | Local gate | Completion |
| --- | --- | --- | --- |
| `micro` | docs/tests-only, very small isolated work | changed/quick | pushed |
| `standard` | ordinary feature and defect work | changed/quick | pushed |
| `high-risk` | DB/auth/payment/deploy/build config or declared high risk | changed/quick | pushed |

`auto` is only a selector. The effective profile remains useful for analysis,
design depth, and reviewer recommendations, but it never expands the local gate.
All profiles run the fast changed-scope gate and complete when the configured
target branch is pushed. Jenkins owns later build/deploy work; its result and
manual acceptance are outside the coding task.

Project `gate.rules` may raise the planning profile or request design/reviewer
attention. Their legacy `scope` and `commands` values never execute in the
automatic development flow. Standard/full commands remain callable on demand
with `ap.py run <name>` but are not part of normal development.

## Minimal configuration

Required for normal development:

- `workflow.mode`: `dev`
- `workflow.profile`: `auto`, `micro`, `standard`, or `high-risk`
- `workflow.completion`: `push`
- `project.name`
- all URL, username, and direct password fields under `access.project`,
  `access.jenkins`, `access.gitlab`, and `access.nexus`; blank/TODO values make
  initialization incomplete and block `doctor`; keep each value as an inline
  YAML string, quoting values that resemble numbers, dates, booleans, or YAML
  collections
- `concurrency.isolation`: the only supported value is `worktree`; shared-checkout
  and legacy write modes are rejected
- `concurrency.base_ref` and `target_branch`: leave blank to derive the current
  upstream, or set them explicitly for a fixed integration branch
- `concurrency.branch_prefix` and `worktree_root`
- `concurrency.cleanup_merged` and `delete_remote_branch`: keep both enabled to
  remove integrated temporary worktrees and branches
- `concurrency.disposable_ignored`: add only project-specific ignored cache/build
  paths that may be discarded with a task worktree; ignored data and unknown
  paths block cleanup, including inside initialized submodules
- one fast `commands.gate_changed`; the default is `git diff --check`

Legacy command keys such as `commands.light_gate`, `test`, and `build` remain
callable explicitly with `ap.py run <name>` but never replace the automatic
changed gate. `quick_test` remains the only fallback when `gate_changed` is
absent. Run `doctor` for exact missing-field diagnostics.

If the actual changed gate fails only because a dependency already declared in
the repository lockfile is not installed in the task worktree, restore that
locked dependency locally (for example with `npm ci`) and rerun the same changed
gate once. Do not install dependencies or restart a standard/full diagnostic
that was invoked outside the normal development gate, and never promote this
recovery into a full-gate run.

## Concurrent write tasks

Run every write task in a registered Git worktree and task branch. Do not share
the primary worktree between writers.

```bash
python3 docs/tools/autopipeline/ap.py task-start <TASK_ID> \
  --owned-path <PATH> [--owned-path <PATH> ...] \
  [--depends-on <TASK_ID>=<SHA> ...] [--writer <WRITER>]
# Enter the worktree path printed by task-start.
python3 docs/tools/autopipeline/ap.py task-status <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-submodule-sync <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-review <TASK_ID> \
  --verdict approved --diff-fingerprint <SHA256> [--reviewer <REVIEWER>]
python3 docs/tools/autopipeline/ap.py task-handoff <TASK_ID> \
  --from <WRITER> --to <WRITER> [--generation <N>]
python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> \
  --msg "<TASK_ID>: <summary>" [--writer <WRITER>]
python3 docs/tools/autopipeline/ap.py task-integrate <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-resume <TASK_ID>
```

`task-start` fixes the task's base revision and records its task branch and
worktree, repeated `owned_paths`, dependency task/SHA pairs, and the active writer
lease in the repository manifest. Run `commit-push` only from that registered
worktree. Changed and staged paths must be a subset of `owned_paths`; an unknown
change blocks the push and must never be restored, reset, stashed, cleaned, or
otherwise altered.

The lifecycle fields are runtime gates, not advisory notes. `task-review` records
the reviewer verdict against the current diff fingerprint; any edit, rebase, or
conflict resolution invalidates that approval. `task-handoff` is the only way to
transfer the writer lease, and its generation check prevents stale owners from
resuming writes. `commit-push` validates the active writer (explicit `--writer`
or `CODEX_THREAD_ID`), path ownership, exact dependency SHAs, and an approved
current fingerprint before it runs the single fast gate. `task-integrate` repeats
the dependency and review checks. If integration stops on a conflict, resolve it
inside the task worktree, run `task-resume`, obtain a fresh review, and then retry
integration. A target rebase likewise requires a fresh review.

The task commit runs project commit hooks once. The internal backup task-branch
push skips the pre-push hook; the final target-branch push runs it once.
`task-integrate` creates no second evidence commit.

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

Before running `autocoding sync`, finish, integrate, and clean every registered
v3.0 task with the currently installed 3.0.0 runtime. Sync atomically rejects the
whole project batch while any schema-v1 task remains, including
`--components skill`; it never guesses or auto-claims owned paths during upgrade.

## Subagent orchestration

The main agent owns the task graph and Git lifecycle. Before dispatch, decompose
the request into bounded units and record for each unit its task ID, role, scope,
dependencies, acceptance criteria, and expected result. Run only independent
work concurrently.

1. Run justified `explorer`, `docs_researcher`, and `browser_debugger` roles in
   parallel for read-only discovery. Browser work collects reproduction evidence;
   it is not post-push acceptance.
2. The main agent merges discovery evidence and decides the design, dependency
   graph, and non-overlapping path ownership.
3. Assign each independent write unit to exactly one `fixer`, one registered task
   branch, and one worktree. Never run two writers in one worktree, and do not let
   the main agent edit a fixer-owned worktree concurrently.
4. Parallelize fixer units only when they are dependency-free and their owned
   paths do not overlap. Complete implementation → review → gate/integration for
   the current dependency wave, then start the next wave only after its
   prerequisites are integrated into the target branch.
5. A read-only `reviewer` checks a stable diff after implementation and binds its
   verdict to the diff fingerprint. Blocking findings return to the owning fixer;
   any edit invalidates approval and requires re-review. Record the final verdict
   with `task-review` before handing the writer lease back to the main agent.
6. Subagents never commit, push, integrate, clean branches, or run the project
   gate. Their versioned result contains node/task/role, base SHA, status,
   dependencies, owned and changed paths, diff fingerprint, evidence, findings,
   verdict, risks, and next owner. Read-only roles return no changed paths.
7. After all required results return, use `task-handoff` to transfer the lease to
   the main agent. The main agent alone runs `commit-push` for each write task,
   which validates the current review and runs the single fast gate, then
   integrates in dependency order, pushes, and cleans all temporary branches and
   worktrees.

`classify` emits a machine-readable `agent_plan` with this stage and ownership
contract. Micro tasks remain main-agent-only unless useful independent work
clearly exceeds delegation overhead. If the client cannot run subagents, execute
the same stages sequentially without weakening worktree isolation.

## Default workflow

Development:

1. Read this file and the active task entry.
2. Analyze and decompose the request; run or reason through `classify --scope auto`.
3. Fan out independent discovery roles, then fan their results back into one main-agent design.
4. Record the smallest useful design note; create DD/ADR only when indicated.
5. Start one registered worktree per independent write unit with explicit owned paths, dependency SHAs, and writer lease.
6. Review stable diffs, record their fingerprints with `task-review`, and return findings to their owning fixers until approved.
7. Hand the writer lease to the main agent. The main agent runs `commit-push` for each write task; it enforces ownership,
   dependency, lease, and current-review gates, executes the one changed-scope fast gate, records
   `DEV-CLOSED`, commits, and pushes the task branch.
8. The main agent runs `task-integrate` in dependency order to push the target branch and clean the task worktree and
   merged task branches. This completes the push stage and ends the coding task.

Do not wait for, poll, diagnose, or record Jenkins/build/deploy results after the
push. The project owner performs real acceptance separately.

The authoritative order is analysis, decomposition, design, development, fast
local gate, then push. Do not mark unexecuted external checks as PASS.

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
python3 docs/tools/autopipeline/ap.py task-start <TASK_ID> --owned-path <PATH>
python3 docs/tools/autopipeline/ap.py task-status <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-submodule-sync <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-review <TASK_ID> --verdict approved --diff-fingerprint <SHA256>
python3 docs/tools/autopipeline/ap.py task-handoff <TASK_ID> --from <WRITER> --to <WRITER>
python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> --msg "<TASK_ID>: <summary>"
python3 docs/tools/autopipeline/ap.py task-integrate <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-resume <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-finish <TASK_ID>
python3 docs/tools/autopipeline/ap.py task-prune
python3 docs/tools/autopipeline/ap.py docs-ledger-check
python3 docs/tools/autopipeline/ap.py gate-profile
```

`light-gate` is available for an explicit gate-diagnostic task. Do not run it
before normal `commit-push`; `commit-push` owns the single automatic gate.

The launcher under `docs/tools/autopipeline` delegates to the single runtime in
`.agents/skills/auto-coding-skill/scripts`; do not duplicate that runtime.

<!-- auto-coding-skill:managed-workflow:end -->
