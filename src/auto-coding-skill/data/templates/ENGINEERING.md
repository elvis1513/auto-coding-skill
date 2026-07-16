---
workflow:
  skill_version: "4.1.1"
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
  # Optional convenience command. Define the project-native fast commands used
  # by validation.routes; sync fills this only for package.json test:changed.
  project_fast: ""

validation:
  on_unmapped: "error"
  # Normal closure cannot exceed these hard ceilings. Values may be lowered but
  # not raised above 120 seconds per command or 180 seconds total.
  max_command_seconds: 120
  max_total_seconds: 180
  # Initialization must replace this with real path-to-command mappings. Empty
  # routes intentionally fail closed for code/config changes.
  routes: []

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
  framework: "engineering-centered"
  design_dir: "docs/design"
  health_baseline: "docs/reviews/project-health-baseline.md"
  optimization_backlog: "docs/reviews/optimization-backlog.md"
  structure_standard: "docs/architecture/structure-standard.md"
  api_docs_required: false
  api_doc: "docs/interfaces/api.md"
  api_change_log: "docs/interfaces/api-change-log.md"
---

# Engineering Configuration and Project Facts

<!-- auto-coding-skill:managed-workflow:start version=4.1.1 -->

Root `AGENTS.md` is the single shared behavioral protocol. The installed
`SKILL.md` contains invocation guidance. This file is the single source for the
project-specific configuration and facts that neither file can infer.

The frontmatter contract is:

- `workflow`: installed version and push-completion mode.
- `access`: required project, Jenkins, GitLab, and Nexus access values.
- `concurrency`: target branch and adaptive isolation settings.
- `commands`: project-native executable commands.
- `validation`: explicit path-to-command routes plus the bounded final-gate time
  budget. Code/config paths must be mapped; slower checks belong to explicit
  diagnostics.
- `risk`: project-specific signals that increase design/review depth but never
  expand the automatic local gate.
- `structure` and `optimization`: advisory architecture and no-new-debt policy.
- `docs`: locations of optional durable project artifacts.

Run `python3 docs/tools/autopipeline/ap.py doctor` after changing frontmatter.
Do not put competing delivery flows, agent roles, lifecycle rules, gate semantics,
or completion rules outside this managed block.

<!-- auto-coding-skill:managed-workflow:end -->

# Project Facts

Keep only current, project-specific facts here. Put larger material under
`docs/project/` and link it from the relevant section.

## Product and domain boundaries

## Repository and ownership map

## Runtime and deployment topology

## External-system and real-device safety

## Interface and decision links
