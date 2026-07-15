---
workflow:
  skill_version: "4.0.0"
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
  isolation: "adaptive"
  base_ref: ""
  target_branch: ""
  branch_prefix: "codex/"
  worktree_root: "../.worktrees"
  cleanup_merged: true
  delete_remote_branch: true
  disposable_ignored: []

commands:
  # Configure one real, fast project-native command. `autocoding sync` fills
  # this automatically only when package.json declares `test:changed`.
  project_fast: ""

validation:
  on_unmapped: "error"
  routes:
    - name: "project-code"
      paths: ["**"]
      exclude: ["*.md", "docs/**"]
      commands: ["project_fast"]

risk:
  rules: []

structure:
  enabled: true
  enforcement: "advisory"
  architecture_standard: "project-defined"
  accepted_debt_paths: []
  layer_rules:
    enabled: true
    block: false

optimization:
  completion_policy: "no-new-debt"
  require_baseline_for_global_review: false
  report_accepted_debt_as_findings: false

docs:
  design_dir: "docs/design"
  health_baseline: "docs/reviews/project-health-baseline.md"
  optimization_backlog: "docs/reviews/optimization-backlog.md"
  structure_standard: "docs/architecture/structure-standard.md"
  api_docs_required: false
  api_doc: "docs/interfaces/api.md"
  api_change_log: "docs/interfaces/api-change-log.md"
---

# Engineering Workflow

<!-- auto-coding-skill:managed-workflow:start version=4.0.0 -->

This file contains project facts and the small amount of configuration the
generic workflow cannot infer. Normal delivery is:

`analysis → decomposition → necessary design → development → one final fast
changed-scope gate → commit/push`.

Target-branch push ends the coding task. Jenkins, deployment, and owner
acceptance happen later unless the user opens an explicit diagnostic task.

## Delivery levels

| Level | Default behavior | Added guardrails |
| --- | --- | --- |
| Micro | main agent, current branch, fast route | none |
| Standard | main agent or justified read-only help | no mandatory reviewer or design document |
| High risk | focused design and independent review | only the affected validation routes |
| Parallel | one isolated writer per unit | owned paths, dependency SHAs, leases, fingerprint review, ordered integration |

Risk changes analysis, design, and review depth. It never promotes normal local
development to a full repository build, Docker run, Jenkins poll, deployment, or
target-environment acceptance.

## Adaptive isolation

Run task planning before development:

```bash
python3 docs/tools/autopipeline/ap.py classify --scope auto \
  --planned-path <PATH> --intent "<task intent>" [--writers <N>]
```

- A clean checkout with one writer uses the current branch directly.
- A checkout that already contains unrelated changes uses an isolated task
  branch/worktree.
- Two or more concurrent writers always use separate worktrees with
  non-overlapping owned paths.
- A task that produces no diff creates no commit or push; direct mode creates no
  temporary branch at all.
- Never restore, reset, stash, clean, or otherwise modify unknown user or task
  changes.

`task-start` implements this decision. Use `--isolated` to force a worktree and
`--review-required` when a project rule or the task risk requires fingerprinted
review:

```bash
python3 docs/tools/autopipeline/ap.py task-start T0001 \
  --owned-path src --writers 1
python3 docs/tools/autopipeline/ap.py commit-push T0001 --msg "T0001: summary"
```

In direct mode, `commit-push` runs the final gate, commits, and pushes the current
target branch. In isolated mode it pushes the task branch; the main agent then
runs `task-integrate`, which pushes the target branch and removes clean merged
temporary branches/worktrees. `task-prune` removes only safely merged leftovers.

## Real changed-scope validation

`risk.rules` classifies work. `validation.routes` executes checks. Do not mix
these responsibilities.

```yaml
commands:
  backend_fast: "cd backend && go test ./internal/orders/..."
  frontend_fast: "cd frontend && npm run test:changed"

validation:
  on_unmapped: error
  routes:
    - name: backend
      paths: ["backend/**", "contracts/**"]
      commands: [backend_fast]
    - name: frontend
      paths: ["frontend/**"]
      commands: [frontend_fast]
```

Every changed path may match multiple routes. The runtime collects all commands
in configuration order, removes duplicates, and executes each once. Unmapped
code fails before staging. Documentation-only changes may use the built-in diff
check. `git diff --check` is always an additional hygiene check and never counts
as business-code validation.

Inspect coverage without running the commands:

```bash
python3 docs/tools/autopipeline/ap.py validation-map-check --path backend/foo.go
python3 docs/tools/autopipeline/ap.py validation-map-check --tracked
```

Focused tests may be run and rerun during implementation. The "one gate" rule
means one final routed closure gate after the diff is stable; it does not prohibit
reasonable test/fix/retest cycles. Do not install dependencies automatically.
If the final routed command needs a dependency already locked by the repository,
restore the locked dependency once and retry that same command only.

## Design, review, and subagents

- Create DD/ADR only for lasting cross-module, API, data, security, deployment,
  or key user-flow decisions.
- Ordinary work defaults to the main agent. Delegate only independent discovery
  or implementation units whose latency or expertise benefit exceeds dispatch
  cost.
- Read-only explorer/docs/browser roles may run in parallel when their questions
  are independent.
- Parallel fixers require separate worktrees and non-overlapping owned paths.
- Require reviewer fingerprint approval for high-risk, cross-module, explicitly
  configured, or parallel integration work; ordinary serial fixes do not require it.
- The main agent alone owns the final gate, commit, push, ordered integration,
  and temporary-branch cleanup.

## Lightweight records

Ordinary tasks do not create taskbook, closure Markdown, evidence JSONL, or active
task documents. Isolated-task coordination state lives under the Git common
directory and gate timing lives under `.local/auto-coding-skill`. Existing project
ledgers are user data: upgrades preserve them but do not require or update them.
Use `record-closure`, documentation scaffolds, or a baseline only when the user or
task genuinely needs a durable artifact.

Historical debt does not block product work. Block only new or worsened P0/P1
issues; keep accepted debt in an optional backlog and address it through explicit
governance tasks.

## Access and explicit diagnostics

Fill all URL, username, and password fields under `access.*` during project
initialization. Direct plaintext values are allowed. The generic workflow neither
forbids them nor rewrites a project's credential policy.

Full regression, structure scans, Docker, Jenkins, API checks, target verification,
and deployment remain explicit diagnostic commands. Do not run them during normal
closure unless the user explicitly requests that diagnostic scope.

<!-- auto-coding-skill:managed-workflow:end -->
