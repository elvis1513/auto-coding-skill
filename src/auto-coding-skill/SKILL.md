---
name: auto-coding-skill
description: Use for a Claude/Codex engineering workflow with dev and verify modes. Initialize docs, fill docs/ENGINEERING.md once, then execute task->minimal-design->light-gate->DEV-CLOSED->push in dev mode, or full Jenkins->target-env->PASS closure in verify mode.
---

# Auto Coding Skill (Claude + Codex)

This skill is for Go backend + frontend monorepo projects that rely on Jenkins to build and deploy after push. It supports both Claude and Codex. The default `dev` mode is optimized for fast development: lightweight local gate, early closure record, commit, push, then move to the next task. Use `verify` mode when Jenkins and the real target environment must be completed before closure.

`docs/ENGINEERING.md` is intentionally Git-tracked in this workflow. The remaining environment fields in that file are mandatory, must be filled with real values, and are committed as part of the project baseline. Secret fields may be represented either as direct `*_password` values for legacy projects or as `*_password_env` names that point to environment variables in the current shell. Unused environment keys should be removed from the template instead of being left as placeholders.

At task start, inventory the current client capabilities before choosing a route: installed MCP servers, local skills, plugins/apps/connectors, browser/control tools, and repo scripts. Prefer those capabilities when they provide current, authoritative, or directly inspectable state.

Use multi-agent roles deliberately. When the client exposes subagent tools and the active runtime policy permits delegation, split independent research, exploration, implementation, browser verification, and review work. When delegation is unavailable or restricted, execute the same role sequence in the main agent instead of pretending parallelism is possible.

## Supported clients

- Claude Code
- Codex CLI

## Tooling policy

Use the most direct authoritative capability for each task:

1) Local repo work: use shell, repo scripts, and `docs/tools/autopipeline/ap.py` for edits, tests, gates, git, and project-local verification.
2) Current library/framework/API/CLI/cloud behavior: use a documentation MCP such as Context7 or the matching installed skill before coding migrations, config changes, or API integrations.
3) Browser and UI verification: use Browser/in-app browser for localhost and app-owned sessions; use Chrome when the user's existing logged-in Chrome state is required; use Playwright for deterministic browser automation or terminal-first smoke tests; use Computer Use only for native apps or UI surfaces without a purpose-built connector.
4) Product/design sources: use Figma, Build Web Apps, Product Design, or frontend skills when the task depends on design context, visual implementation, screenshots, or generated UI.
5) GitHub/PR/CI state: use GitHub connectors for PRs, issues, review comments, and Actions/CI metadata; use local git for local diff, staging, commits, and pushes.
6) Security-sensitive changes: use reviewer/security skills or security scan capabilities for auth, permission, payment, file transfer, deployment, dependency, and data-boundary changes.
7) Analytical or document artifacts: use Data Analytics, documents, PDFs, spreadsheets, presentations, or LaTeX skills/plugins for those artifact types, including render/validation steps.
8) OpenAI/API keys and other secrets: use secure platform/key setup capabilities when available; do not paste, invent, or persist secrets outside the configured secure flow.
9) Screen/recent-work context: use Chronicle or screenshot skills when the user references visible UI state or recent manual actions.
10) Fall back to manual shell/code workflows only when the above are unavailable, insufficient, or slower than direct execution.

## Collaboration policy

Use `.agents/agents` role templates as the default collaboration model for Codex installs:

1) `explorer`: read-only repo discovery, call-chain tracing, config mapping, and root-cause candidates.
2) `docs_researcher`: current external documentation, API signatures, version behavior, and compatibility checks.
3) `browser_debugger`: browser reproduction, console/network evidence, screenshots, and UI behavior verification.
4) `fixer`: bounded implementation after the cause and acceptance path are clear.
5) `reviewer`: read-only correctness, security, regression-risk, and missing-test review.

The main agent always owns task framing, design decisions, integration, Jenkins / target-env verification, closure records, git state, and final delivery. Do not delegate a blocking architectural decision without keeping one agent responsible for final integration and correctness.

## Entry

1) Install skill files into target repo:

```bash
autocoding init --ai codex
# or claude / all
```

For Codex targets, this also installs the default subagent templates into `.agents/agents/`.

2) Initialize docs/tooling:

```bash
python3 .agents/skills/auto-coding-skill/scripts/ap.py --repo . install
# or .claude path
```

Existing projects should use upgrade mode before replacing tracked docs:

```bash
python3 docs/tools/autopipeline/ap.py upgrade --dry-run
python3 docs/tools/autopipeline/ap.py upgrade --write
```

3) Install runtime deps:

```bash
pip install pyyaml requests
```

## Single manual config source

Fill only:

- `docs/ENGINEERING.md` frontmatter

This contains all manual fields:
- `workflow.mode`
- `commands.*`
- `gate.*`
- `structure.*`
- `optimization.*`
- `runtime.*` (only for optional local diagnostics)
- `target_env.*`
- `jenkins.*`
- `docs.*`

Do not duplicate config in other md/yaml files.
Do not hide `docs/ENGINEERING.md` in `.gitignore`.

Minimum required config for the default flow:
- `workflow.mode`
- `project.name`
- `commands.gate_changed` / `commands.gate_standard` / `commands.gate_full`, or `commands.light_gate` / `commands.quick_test` / `commands.test` / `commands.build`
- `target_env.name`
- `target_env.frontend_base_url`
- `target_env.frontend_username`
- `target_env.frontend_password` or `target_env.frontend_password_env`
- `target_env.backend_base_url`
- `target_env.backend_username`
- `target_env.backend_password` or `target_env.backend_password_env`
- `target_env.backend_root_username`
- `target_env.backend_root_password` or `target_env.backend_root_password_env`
- `target_env.health_base_url`
- `target_env.health_path`
- `jenkins.base_url`
- `jenkins.ui_username`
- `jenkins.ui_password` or `jenkins.ui_password_env`
- `jenkins.api_user`
- `jenkins.api_password` or `jenkins.api_password_env`
- `jenkins.trigger_branch`
- `jenkins.image_repository`
- `jenkins.image_tag_strategy`
- `jenkins.deploy_env`
- `jenkins.job_url`

## Branch policy

- `dev` is the long-lived integration branch.
- Use a temporary task branch only when parallel work would otherwise collide on `dev`.
- Keep temporary branches task-scoped and merge/rebase back into `dev` after closure.

## Execution order

Read `workflow.mode` from `docs/ENGINEERING.md` before choosing the path.

`dev` mode:

1) read `docs/ENGINEERING.md`
2) run or reason through `classify --scope auto` for changed work
3) read `docs/architecture/structure-standard.md` when the change adds or relocates code
4) read / update `docs/tasks/taskbook.md`
5) write minimal design notes; create a DD or ADR only when the change is cross-module, API, DB, deployment, Jenkins, key-page-flow, or long-term structure related
6) implement only the necessary changes
7) run the default local lightweight gate
8) append `docs/tasks/closure-log.md` with `Result: DEV-CLOSED`
9) commit + push
10) stop and start the next development task

`verify` mode:

1) read / update the same authoritative docs
2) run the default local lightweight gate
3) commit + push
4) verify Jenkins build / deployment result
5) verify the real target environment
6) append `docs/tasks/closure-log.md` with `Result: PASS / FAIL / PARTIAL`
7) use summary / deployment record / regression matrix only when the task actually requires them

## Commands

Default commands:

```bash
python3 docs/tools/autopipeline/ap.py doctor
python3 docs/tools/autopipeline/ap.py classify --scope auto
python3 docs/tools/autopipeline/ap.py impact --scope auto
python3 docs/tools/autopipeline/ap.py docs-ledger-check
python3 docs/tools/autopipeline/ap.py docs-ledger-archive --plan
python3 docs/tools/autopipeline/ap.py structure-check --scope auto
python3 docs/tools/autopipeline/ap.py light-gate --scope auto --explain
python3 docs/tools/autopipeline/ap.py light-gate --scope full
python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> --msg "<TASK_ID>: <summary>"
python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> --mode dev --msg "<TASK_ID>: <summary>"
python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> --mode verify --msg "<TASK_ID>: <summary>" --backend-path /health --frontend-path /
```

On-demand commands:

```bash
python3 docs/tools/autopipeline/ap.py runtime-up
python3 docs/tools/autopipeline/ap.py wait-health --scope runtime
python3 docs/tools/autopipeline/ap.py runtime-down
python3 docs/tools/autopipeline/ap.py upgrade --dry-run
python3 docs/tools/autopipeline/ap.py baseline init --write --update-config
python3 docs/tools/autopipeline/ap.py docs-ledger-archive --write
python3 docs/tools/autopipeline/ap.py structure-check --scope full
python3 docs/tools/autopipeline/ap.py gate-profile
python3 docs/tools/autopipeline/ap.py check-matrix
python3 docs/tools/autopipeline/ap.py gen-summary <TASK_ID>
```

## Engineering structure policy

- Before coding, locate the existing layer, module owner, helper APIs, scripts, and tests for the behavior being changed.
- Put new code in the correct layer: domain rules stay out of controllers/pages, orchestration belongs in application/service/usecase code, external systems belong behind infrastructure adapters, and UI components should not own deep business workflows.
- Reuse before building: search existing utilities, components, clients, validation, permissions, caching, retry, formatting, and automation scripts before adding another helper.
- Do not add new responsibilities to large files. If a file exceeds `structure.max_file_lines_warn`, prefer extracting a focused module or component; if it exceeds `structure.max_file_lines_block`, only small fixes are acceptable unless the path is explicitly allowed.
- Historical large files can be listed in `structure.accepted_debt_paths` only after they are recorded in the health baseline or optimization backlog; this does not permit large new additions to those files.
- `structure.layer_rules` enforces configurable import boundaries between domain, application, infrastructure, interface, and shared layers.
- Self-built algorithms, concurrency controls, caches, protocol clients, or framework-like helpers require a concrete reason such as performance, concurrency, offline/deploy constraints, licensing, security, or compatibility, plus tests or benchmark/runtime evidence.
- For structural reviews, read `docs/reviews/project-health-baseline.md` and `docs/reviews/optimization-backlog.md` first. Do not re-report accepted debt as a fresh blocker; report only new, worsened, unrecorded P0/P1, or backlog items that now deserve priority upgrade.
- “Optimization complete” means the scoped P0/P1/P2 work is closed, local gate passes, no new unclassified P0/P1 exists, and remaining P2/P3 work is tracked or accepted debt.
- `baseline init` creates the first project health baseline and optimization backlog; use `--update-config` to seed `accepted_debt_paths`.
- `docs-ledger-check` enforces active documentation ledger budgets. `docs/tasks/taskbook.md`, `docs/tasks/closure-log.md`, and top-level `docs/design/T*.md` are active working sets, not unbounded history stores.
- When active ledger budgets are exceeded, run `docs-ledger-archive --plan`, inspect the plan, then run `docs-ledger-archive --write` only when the closed entries and DD files are correct. Add `--period 2026-06` only when backfilling a specific archive month. The archiver handles clearly closed task sections, non-conflicting closure records, and matching top-level `T*.md` DDs.
- `docs.archive_index` is only navigation; an index without physical archive files does not satisfy ledger health.
- `docs/tasks/evidence.jsonl` is the machine-readable execution trail for gates, verification, and closure. Keep it aligned with closure Markdown.
- `gate-profile` summarizes local gate duration and failure history so small-step development can keep the fast path honest.

## Quality policy

- Default local gate is lightweight and time-bounded: prefer one curated project command via `commands.light_gate`, then run only diff/API/Jenkins checks.
- For small-step development, prefer the generic impact-aware gate: `light-gate --scope auto`. The skill provides the gate engine; each project owns its commands and optional `gate.rules` path mapping in `docs/ENGINEERING.md`.
- `light-gate` automatically runs `structure-check` when `structure.enabled: true` or `commands.structure_check` is configured.
- Keep `standard` as the backward-compatible default when no `gate.*` policy is configured. Use `changed` only when project commands/rules make the reduced scope explicit.
- Automatically upgrade to `full` for CI/deploy/build-tool/lockfile/autopipeline config changes, project-declared full rules, unknown impact when configured, or release/verify tasks.
- `workflow.mode: dev` closes development after light gate, closure record, commit, and push.
- `workflow.mode: verify` closes only after Jenkins and target-environment verification.
- `doctor` should be used early to catch missing or invalid config before the first implementation loop.
- `doctor` runs the built-in docs ledger health check by default so projects do not accumulate giant taskbooks, closure logs, or active DD directories.
- `light-gate` now fails if no usable fast gate command is configured.
- `doctor`, `light-gate`, and `commit-push` all fail when required environment fields are missing, placeholder-like, or syntactically invalid.
- Do not require local Docker Compose or full local regression for every small change.
- Jenkins and target environment verification are mandatory in `verify` mode, not in default `dev` mode.
- `verify-target` should be used for real target-environment API/page checks when the task touches user-visible or deploy-sensitive behavior.
- `commit-push` records closure automatically according to `workflow.mode`.
- `regression-matrix.md` can mark `PASS` only after real execution with evidence.
- High-risk changes must include target environment verification and usually a DD.

## Multi-project operations

Use the npm CLI from outside or inside a repo:

```bash
autocoding status --projects /path/to/repo1,/path/to/repo2
autocoding sync --projects /path/to/repo1,/path/to/repo2 --dry-run
autocoding sync --projects /path/to/repo1,/path/to/repo2
```

`status` reports drift in project-local `.agents`, Codex agent templates, autopipeline scripts, missing template docs, and missing config keys. `sync` updates generated skill/tooling assets and only creates missing docs; it does not overwrite project-specific `docs/ENGINEERING.md`, which should be merged through `ap.py upgrade --write`.
