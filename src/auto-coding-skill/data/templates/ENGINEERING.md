---
workflow:
  mode: "dev"
  profile: "auto"

project:
  name: ""
  repo_root: "."
  stack: "generic"

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

## Default workflow

Development:

1. Read this file and the active task entry.
2. Run or reason through `classify --scope auto`.
3. Record the smallest useful design note; create DD/ADR only when indicated.
4. Implement the necessary change using existing project structure and reuse points.
5. Run the resolved profile gate.
6. Record `DEV-CLOSED`, commit, and push.

High-risk or explicit verification:

1. Run the real full gate.
2. Commit and push.
3. Verify enabled CI/Jenkins and target-environment surfaces.
4. Record `PASS`, `FAIL`, or `PARTIAL` from actual evidence.

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
python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> --msg "<TASK_ID>: <summary>"
python3 docs/tools/autopipeline/ap.py docs-ledger-check
python3 docs/tools/autopipeline/ap.py gate-profile
```

The launcher under `docs/tools/autopipeline` delegates to the single runtime in
`.agents/skills/auto-coding-skill/scripts`; do not duplicate that runtime.
