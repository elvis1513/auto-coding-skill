# auto-coding-skill

Engineering workflow skill for:

- Claude Code
- Codex CLI

This skill targets Go backend + frontend monorepo projects that rely on Jenkins for build and deployment. The default `dev` mode is optimized for fast development: light gate, early closure record, commit, push, then move to the next task. Switch to `verify` mode when Jenkins and target-environment evidence must be completed before closure.

`docs/ENGINEERING.md` is intentionally Git-tracked. The environment fields kept in that file are mandatory, must be filled with real values, and are committed as part of project maintenance. Unused environment items should be removed instead of being kept as placeholders.

## Install

```bash
npm install -g @elvis1513/auto-coding-skill
```

Fallback:

```bash
npm install -g git+https://github.com/elvis1513/auto-coding-skill.git
```

## Release Notes

### Unreleased

- Added `ap.py docs-ledger-check` to prevent documentation ledgers from growing without a real archive.
- Added `ap.py docs-ledger-archive --plan|--write --period YYYY-MM` for generic physical archiving of closed taskbook entries, closure records, and matching top-level DD files.
- `doctor` now runs docs ledger health checks by default: large `taskbook.md`, `closure-log.md`, or active `docs/design/T*.md` sets require physical archives.
- `doctor` records a standalone `docs_ledger_check` evidence event with counts and blocking details.
- `docs-ledger-check` now fails on missing active ledger files instead of treating them as empty ledgers.
- `autocoding status` now parses `docs/ENGINEERING.md` frontmatter key paths instead of matching config tokens in prose.
- Added `docs.task_archive_dir`, `docs.design_archive_dir`, `docs.archive_index`, and active ledger budget settings to `docs/ENGINEERING.md`.
- Clarified that `archive-index.md` is only navigation; it does not replace monthly or legacy physical archives.

### v2.1.0

- Added project upgrade support: `ap.py upgrade --dry-run|--write` safely syncs tooling and merges missing `docs/ENGINEERING.md` keys without overwriting existing values.
- Added baseline initialization: `ap.py baseline init --write --update-config` scans large files/hotspots, creates health baseline + optimization backlog, and can seed `structure.accepted_debt_paths`.
- Added configurable structure import-boundary checks through `structure.layer_rules`.
- Added local gate profiling: configured gate commands write `.local/auto-coding-skill/gate-profile.jsonl`, summarized by `ap.py gate-profile`.
- Added multi-project npm CLI operations: `autocoding status --projects ...` and `autocoding sync --projects ...`.
- Added structured evidence logging to `docs/tasks/evidence.jsonl` for classify, doctor, structure-check, gates, verification, and closure.
- Added task classification: `ap.py classify --scope auto` reports risk, categories, required DD/ADR/browser/Jenkins/target checks, and recommended commands.

### v2.0.6

- Fixed `structure-check --json` so successful output stays machine-readable JSON without a trailing OK line.
- Moved CLI error messages to stderr, preserving JSON stdout for failing machine-readable commands.
- Made `structure.enabled: false` disable structure gate integration even when `commands.structure_check` is still present.

### v2.0.5

- Added generic engineering-structure governance: `docs/architecture/structure-standard.md`, ADR template, project health baseline, and optimization backlog templates.
- Added `ap.py structure-check --scope auto|changed|standard|full` for large-file thresholds, large-file growth blocking, function-size warnings, and baseline-doc checks.
- Integrated `structure-check` into `light-gate` when `structure.enabled: true` or `commands.structure_check` is configured.
- Added baseline-aware optimization policy so “optimization complete” means scoped P0/P1/P2 closure plus tracked/accepted remaining debt, not “no future optimizations exist.”

### v2.0.4

- Added a generic impact-aware gate engine: `ap.py impact`, `light-gate --scope auto|changed|standard|full`, and `--explain`.
- Added project-owned `gate.*` policy support in `docs/ENGINEERING.md`; the skill chooses scope, while each project declares its own commands and optional path rules.
- Kept backward compatibility: projects without `gate.*` continue to use the existing standard `commands.light_gate` / quick-test fallback.
- Added conservative full-gate upgrades for CI, deploy, Docker, lockfile, build-tool, and autopipeline config changes.

### v2.0.3

- Fixed `doctor`, `light-gate`, `verify-target`, and Jenkins API verification to accept secret references via `*_password_env`.
- Kept direct `*_password` fields compatible for legacy projects while making the default template use environment-variable secret references.
- Updated docs so `docs/ENGINEERING.md` can stay Git-tracked without requiring committed secrets.

### v2.0.2

- Added default Codex subagent templates under `.agents/agents`.
- `autocoding init --ai codex` and `autocoding init --ai all` now install the Codex agent templates automatically.
- Updated Codex agent defaults to current model names: `gpt-5.5`, `gpt-5.4-mini`, and `gpt-5.3-codex-spark`; highest reasoning uses `xhigh`.
- Added concrete capability routing for MCP servers, installed skills, plugins/apps/connectors, browser tools, GitHub, Figma, security review, and artifact workflows.
- Changed multi-agent guidance from unconditional delegation to a role model that works either as real subagents or as sequential main-agent phases.
- Hardened CLI help/argument validation, asset sync checks, and stricter autopipeline config diagnostics.

### v2.0.1

- Updated the Codex installer target to `.agents/skills`, matching current Codex global and project skill discovery.

### v0.3.1

- Added Jenkins crumb / CSRF retry support for API verification requests.
- Added finer-grained Jenkins folder / multibranch pipeline resolution.
- Added multibranch root job + branch child job support, with current Git branch inference when needed.
- Kept existing `verify-jenkins-build --git-ref` and direct `--job-url` / `--build-number` flows compatible.

### v0.3.0

- Synced reusable workflow improvements from a production project back into this skill.
- Moved repo-side helper entrypoint to `docs/tools/autopipeline`.
- Tightened regression matrix rules: rows start as `TODO`, and `PASS` requires real execution evidence.
- Added Jenkins API verification flow with credentials sourced from `docs/ENGINEERING.md`.

## Optimized Standard Flow

模式由 `docs/ENGINEERING.md` 顶部控制：

```yaml
workflow:
  mode: "dev" # dev | verify
```

`dev` 默认闭环：

`需求/任务记录 -> 最小设计 -> 开发 -> 本地轻量校验 -> 写 DEV-CLOSED 闭环 -> commit/push -> 结束`

`verify` 完整闭环：

`需求/任务记录 -> 最小设计 -> 开发 -> 本地轻量校验 -> commit/push -> Jenkins 构建部署验证 -> 目标环境验证 -> 写 PASS 闭环`

具体执行顺序：

1. 需求确认
   - 明确任务范围、影响服务、是否涉及 API / 数据库 / 部署 / Jenkins / 前端页面。
2. 最小设计记录
   - 普通小改动只更新 `taskbook` 或相关设计文档的一小段。
   - 跨模块、接口、数据库、部署、Jenkins、关键页面流程变更才补 DD。
3. 开发实现
   - 只修改本次任务必要文件，不做无关重构。
4. 本地轻量校验
   - 优先执行一个项目自定义快速门禁命令
   - 若未配置，再执行 quick test / test / build 中最先配置的一项
   - `git diff --check`
   - API 文档检查
   - Jenkins 配置检查
5. 提交推送
   - `dev` 模式：轻量校验通过后，先写 `DEV-CLOSED` 闭环，再 commit + push，触发 Jenkins 后结束。
   - `verify` 模式：commit + push 后继续等待 Jenkins 和目标环境验证。
6. Jenkins 验证
   - 仅 `verify` 模式默认执行。看 Jenkins 构建、镜像、部署结果；失败则基于 Jenkins 日志修复并再次提交。
7. 目标环境验证
   - 仅 `verify` 模式默认执行。在真实目标环境做健康检查、关键接口、关键页面或业务路径验证。
8. 回归与证据记录
   - 只有真实执行过 Jenkins / 目标环境验证，或明确要求本地运行验证时，才把 regression matrix 写成 `PASS`。
9. 闭环记录
   - `dev` 模式记录 `DEV-CLOSED`，表示开发闭环完成但 Jenkins/目标环境未验证。
   - `verify` 模式记录 `PASS` / `FAIL` / `PARTIAL`，必须基于真实验证结果。

## Default vs On-demand

默认不做：
- 本地 Docker Compose 启动
- 本地 Docker build
- 本地完整 regression
- 每个小改动强制 `check-matrix`
- 每个小改动强制生成 summary
- 未真实执行就要求 regression matrix 全 `PASS`
- 未真实部署目标环境就生成 deployment record

按需保留：
- `runtime-up` / `runtime-down`
- 本地 health
- `check-matrix`
- `gen-summary`
- deployment runbook / deployment record

## Standard Workflow

1. Install skill into project:

```bash
autocoding init --ai all
# or: --ai codex / --ai claude
```

For Codex installs, the command also creates `.agents/agents/` with the default `explorer`, `fixer`, `reviewer`, `docs_researcher`, and `browser_debugger` subagents.

2. Initialize docs and local scripts:

```bash
python3 .agents/skills/auto-coding-skill/scripts/ap.py --repo . install
# or
python3 .claude/skills/auto-coding-skill/scripts/ap.py --repo . install
```

3. Fill only one file manually:

- `docs/ENGINEERING.md` frontmatter

This frontmatter is the only manual config source.
It must be committed to Git. Do not add it to `.gitignore`.

重点字段：
- `workflow.mode`
- `commands.*`
- `gate.*`
- `structure.*`
- `optimization.*`
- `target_env.*`
- `jenkins.*`
- `docs.*`

默认必填：
- `workflow.mode`
- `project.name`
- `commands.gate_changed` / `commands.gate_standard` / `commands.gate_full`，或 `commands.light_gate` / `commands.quick_test` / `commands.test` / `commands.build`
- `target_env.name`
- `target_env.frontend_base_url`
- `target_env.frontend_username`
- `target_env.frontend_password` 或 `target_env.frontend_password_env`
- `target_env.backend_base_url`
- `target_env.backend_username`
- `target_env.backend_password` 或 `target_env.backend_password_env`
- `target_env.backend_root_username`
- `target_env.backend_root_password` 或 `target_env.backend_root_password_env`
- `target_env.health_base_url`
- `target_env.health_path`
- `jenkins.base_url`
- `jenkins.ui_username`
- `jenkins.ui_password` 或 `jenkins.ui_password_env`
- `jenkins.api_user`
- `jenkins.api_password` 或 `jenkins.api_password_env`
- `jenkins.trigger_branch`
- `jenkins.image_repository`
- `jenkins.image_tag_strategy`
- `jenkins.deploy_env`
- `jenkins.job_url`

4. Start AI development by constraints:

- `docs/ENGINEERING.md`
- `docs/architecture/structure-standard.md`
- `docs/reviews/project-health-baseline.md`
- `docs/reviews/optimization-backlog.md`
- `docs/tasks/taskbook.md`
- `docs/tasks/closure-log.md`
- `docs/interfaces/**`
- `docs/testing/regression-matrix.md`
- `docs/bugs/bug-list.md`

5. Tool selection rule during execution:

- Local code, tests, git, and project gates: use shell, repo scripts, and `docs/tools/autopipeline/ap.py`.
- Current library/framework/API/CLI/cloud docs: use Context7 or the matching installed skill before coding against uncertain behavior.
- UI verification: use Browser/in-app browser for local pages, Chrome for the user's logged-in Chrome state, Playwright for deterministic automation, and Computer Use only for native or unsupported UI surfaces.
- GitHub/PR/CI: use GitHub connectors for remote PR, issue, review, and CI state; use local git for local diff, commit, and push.
- Figma/frontend/design, security review, data/reporting, and document artifacts: use the matching installed plugin or skill before manual recreation.
- Fall back to shell/manual work only when those capabilities are unavailable, insufficient, unreliable, or slower than direct execution.

6. Collaboration rule during execution:

- Use `.agents/agents` as the default role model: `explorer`, `docs_researcher`, `browser_debugger`, `fixer`, `reviewer`.
- If the client permits subagents, split independent work across those roles.
- If the client cannot run subagents, execute the same role sequence in the main agent.
- Keep one main agent responsible for scope, integration, quality gates, docs closure, git state, and final delivery.

## Structure Governance

The default project scaffold includes a generic professional structure standard:

- `docs/architecture/structure-standard.md`: layer boundaries, reuse-first rules, file/function size rules, and review priority definitions.
- `docs/architecture/adr/_TEMPLATE-ADR.md`: architectural decision record template.
- `docs/reviews/project-health-baseline.md`: accepted current structure, closed optimizations, accepted debt, and completion standard.
- `docs/reviews/optimization-backlog.md`: ongoing P0/P1/P2/P3 optimization backlog.

Useful commands:

```bash
python3 docs/tools/autopipeline/ap.py classify --scope auto
python3 docs/tools/autopipeline/ap.py docs-ledger-check
python3 docs/tools/autopipeline/ap.py docs-ledger-archive --plan --period YYYY-MM
python3 docs/tools/autopipeline/ap.py structure-check --scope auto
python3 docs/tools/autopipeline/ap.py structure-check --scope full
python3 docs/tools/autopipeline/ap.py light-gate --scope auto --explain
python3 docs/tools/autopipeline/ap.py baseline init --write --update-config
python3 docs/tools/autopipeline/ap.py gate-profile
python3 docs/tools/autopipeline/ap.py upgrade --dry-run
```

`structure-check` is intentionally generic. Project-specific paths and stricter rules belong in `docs/ENGINEERING.md` under `structure.*`, `optimization.*`, and optional `commands.structure_check`.
Historical large-file debt can be listed in `structure.accepted_debt_paths` after it is recorded in the health baseline or optimization backlog; continued large additions to those files still fail.

`docs-ledger-check` is intentionally separate from `structure-check`. It treats `docs/tasks/taskbook.md`, `docs/tasks/closure-log.md`, and top-level `docs/design/T*.md` as active working sets. When they exceed `docs.active_*` budgets, the fix is physical archiving under `docs.task_archive_dir` / `docs.design_archive_dir`; `docs.archive_index` is only a navigation index and does not count as archive slimming.

Use `docs-ledger-archive --plan --period YYYY-MM` first. If the plan only contains closed task sections, closure records, and matching top-level `T*.md` DD files, apply it with `docs-ledger-archive --write --period YYYY-MM`, then rerun `docs-ledger-check`.

## Project Upgrade

For existing projects, do not rerun initialization blindly. Use:

```bash
python3 docs/tools/autopipeline/ap.py upgrade --dry-run
python3 docs/tools/autopipeline/ap.py upgrade --write
```

`upgrade` updates autopipeline scripts, syncs project-local `.agents` skill copies when present, creates missing template docs, and merges only missing frontmatter keys into `docs/ENGINEERING.md`.

## Baseline And Evidence

Initialize a project health baseline:

```bash
python3 docs/tools/autopipeline/ap.py baseline init --write --update-config
```

This creates:

- `docs/reviews/project-health-baseline.md`
- `docs/reviews/optimization-backlog.md`
- optional `structure.accepted_debt_paths` entries for existing large files

Execution evidence is written as JSONL:

- `docs/tasks/evidence.jsonl`
- `.local/auto-coding-skill/gate-profile.jsonl`

Use `python3 docs/tools/autopipeline/ap.py gate-profile` to summarize command duration and failure history.
Use `python3 docs/tools/autopipeline/ap.py docs-ledger-check` to verify that active docs ledgers remain small enough for fast lookup. Use `python3 docs/tools/autopipeline/ap.py docs-ledger-archive --plan --period YYYY-MM` before applying physical archives.

## Multi-project Sync

```bash
autocoding status --projects /path/to/repo1,/path/to/repo2
autocoding sync --projects /path/to/repo1,/path/to/repo2 --dry-run
autocoding sync --projects /path/to/repo1,/path/to/repo2
```

`status` reports drift in `.agents`, Codex agents, autopipeline scripts, missing template docs, and missing config keys. `sync` updates generated assets and creates missing docs, but leaves `docs/ENGINEERING.md` to `ap.py upgrade --write`.

## AGENTS.md Constraint Example

```md
## Mandatory Skill
- Always use `auto-coding-skill` for implementation tasks.
- Before any code change, read and obey:
  1) docs/ENGINEERING.md
  2) docs/architecture/structure-standard.md
  3) docs/tasks/taskbook.md
- Before any optimization review, also read:
  1) docs/reviews/project-health-baseline.md
  2) docs/reviews/optimization-backlog.md
- Execute workflow commands using `python3 docs/tools/autopipeline/ap.py`.
- If required docs are missing, create/update docs first, then code.

## Tooling Policy
- Route by source of truth:
  1) local code/tests/git -> shell + repo scripts
  2) current docs/API behavior -> Context7 or matching docs skill
  3) UI/browser proof -> Browser, Chrome, Playwright, or Computer Use by scenario
  4) PR/Issue/CI -> GitHub connector
  5) design/frontend/security/artifacts -> matching installed skill/plugin
- When a connector or MCP can read or write the authoritative source directly, use it instead of retyping or duplicating state.

## Multi-Agent Policy
- Use `.agents/agents` roles:
  1) explorer
  2) docs_researcher
  3) browser_debugger
  4) fixer
  5) reviewer
- Spawn subagents only when the client supports and allows it; otherwise run the same role phases in the main agent.
- Keep one main agent responsible for task framing, integration, quality gates, docs closure, git state, and final delivery.

## Default Gate Policy
- Default local gate is lightweight only.
- Use `python3 docs/tools/autopipeline/ap.py classify --scope auto` to classify risk, required docs, verification surfaces, and recommended commands.
- Use `python3 docs/tools/autopipeline/ap.py docs-ledger-check` when docs/task ledgers grow; use `docs-ledger-archive --plan` before `--write`; do not treat `archive-index.md` as a substitute for physical archives.
- Use `python3 docs/tools/autopipeline/ap.py impact --scope auto` to inspect changed files, matched project rules, and selected gate scope.
- Use `python3 docs/tools/autopipeline/ap.py structure-check --scope auto` to catch file growth, large-file extension, and missing structure baseline docs.
- Use `python3 docs/tools/autopipeline/ap.py light-gate --scope auto --explain` for small-step development after a project declares `gate.default_scope: auto`, `commands.gate_changed`, or matching `gate.rules`.
- Use `light-gate --scope standard` for the backward-compatible configured gate, and `light-gate --scope full` before release/deploy-sensitive closure.
- The gate engine is generic. Project-specific path mapping belongs in `docs/ENGINEERING.md` under `gate.rules`; unknown or high-risk impact should upgrade to standard/full rather than silently skipping checks.
- The structure gate is generic. Project-specific thresholds and accepted generated/vendor paths belong in `docs/ENGINEERING.md` under `structure.*`.
- Do not require local Docker Compose or full local regression unless the task explicitly needs local runtime diagnosis.
- In `dev` mode, push is the finish line after `DEV-CLOSED` is recorded.
- In `verify` mode, Jenkins success, target environment verification, and closure record are mandatory.

## Structure Policy
- Before coding, identify the right layer and reuse points.
- Do not add new responsibilities to already-large files.
- Prefer existing libraries, helpers, components, and scripts over new local frameworks.
- Self-built concurrency/performance/tooling primitives require a reason plus tests or runtime evidence.
- For optimization review, read the health baseline and backlog first; accepted debt is not a fresh blocker.
```

## Docs Structure and Recording Rules

### 1) docs/ENGINEERING.md
- Purpose: single source of project config + workflow rules.
- How to record:
  - Fill YAML frontmatter once.
  - Keep target env front/backend usernames, Jenkins UI/API usernames, password fields or `*_password_env` references, commands, and docs paths here only.
  - Target environment also includes backend server root username/password.
  - This file is expected to be committed to Git; prefer `*_password_env` for secrets so actual secret values stay in the current shell.
  - Remaining environment keys are all mandatory; blank values, TODO-like placeholders, and incorrect URL/path formats are treated as blocking errors by `doctor`.
  - For secret fields, `doctor` requires either a direct `*_password` value or a `*_password_env` variable name. Commands that actually authenticate require the referenced environment variable to be set at execution time.
  - Do not duplicate config elsewhere.

### 2) docs/tasks/taskbook.md
- Purpose: master task ledger.
- How to record:
  - Every task writes scope, risk, impact area, minimal design note, acceptance, evidence links.
  - For code changes, record structure placement, reuse check, and whether ADR is needed.
  - Keep this file active-only. Closed history belongs under `docs/tasks/archives/**`; an index-only file is not enough.

### 3) docs/tasks/closure-log.md
- Purpose: default lightweight closure record.
- How to record:
  - Append one record per task.
  - Required fields: task, commit, Jenkins build, target env verification, structure check, result, follow-up.
  - If Jenkins failed then was fixed, also record failure reason and fix commit.
  - Keep this file active-only. Historical closure records belong under `docs/tasks/archives/**`.

### 4) docs/architecture/
- Files:
  - `docs/architecture/structure-standard.md`
  - `docs/architecture/adr/_TEMPLATE-ADR.md`
- Rule:
  - Read the structure standard before adding or relocating code.
  - Create an ADR for decisions that affect long-term structure, module boundaries, framework-like helpers, or major tradeoffs.

### 5) docs/reviews/
- Files:
  - `docs/reviews/project-health-baseline.md`
  - `docs/reviews/optimization-backlog.md`
- Rule:
  - Structure and optimization reviews must read these before listing findings.
  - Accepted debt is not a fresh blocker unless it worsened or needs priority upgrade.

### 6) docs/design/
- Purpose: DD for cross-module / API / DB / deployment / Jenkins / key-page-flow changes.
- How to record:
  - Small changes do not need a standalone DD file.
  - Higher-risk changes create `docs/design/<TASK_ID>-<slug>.md`.
  - Keep top-level `docs/design/T*.md` active-only. Historical DDs belong under `docs/archive/design/**`.

### 6.5) docs/tasks/archives/ and docs/archive/design/
- Purpose: physical history archives for closed taskbook entries, closure records, and old DDs.
- Rule:
  - Archive by period or legacy bucket when active ledgers exceed `docs.active_*` budgets.
  - `docs/tasks/archive-index.md` may summarize and link archives, but it is not the archive itself.
  - `doctor` blocks over-budget active ledgers when `docs.ledger_block_on_exceed: true`.

### 7) docs/interfaces/
- Files:
  - `docs/interfaces/api.md`
  - `docs/interfaces/api-change-log.md`
- Rule:
  - Any API change updates both files in the same task.

### 8) docs/testing/regression-matrix.md
- Purpose: on-demand regression evidence, not default gate for every small change.
- Rule:
  - Only real executed items can be marked `PASS`.
  - `check-matrix` is used only when full regression is explicitly required.

### 9) docs/tasks/summaries/
- Purpose: optional long-form summary.
- Rule:
  - Only for high-risk changes, milestones, or tasks that need full retrospective.

### 8) docs/deployment/
- Purpose: optional heavy deployment audit docs.
- Rule:
  - Only for manual deploys, high-risk releases, or explicit audit requirements.

## High-risk Changes

These categories require stronger verification and usually a DD:
- Database migration
- Authentication / authorization
- Payment / order
- Deployment / Jenkins
- Nginx / gateway
- File upload / download
- Production configuration

For these tasks, use `workflow.mode: "verify"` or run an explicit verification pass after the fast `dev` closure.

## Commands

Recommended default flow:

```bash
pip install pyyaml requests
python3 docs/tools/autopipeline/ap.py doctor
python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> --msg "<TASK_ID>: <summary>"
```

Development mode can also be forced per run:

```bash
python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> --mode dev --msg "<TASK_ID>: <summary>"
```

Verification mode runs the full Jenkins + target-environment loop:

```bash
python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> \
  --mode verify \
  --msg "<TASK_ID>: <summary>" \
  --backend-path /health \
  --frontend-path /
```

Manual verification commands remain available:

```bash
python3 docs/tools/autopipeline/ap.py verify-jenkins-build --git-ref HEAD
python3 docs/tools/autopipeline/ap.py wait-health --scope target
python3 docs/tools/autopipeline/ap.py verify-target --backend-path /health --frontend-path /
python3 docs/tools/autopipeline/ap.py record-closure <TASK_ID> --commit HEAD --jenkins <build-url> --result PASS --verification "health check" --verification "key api" --verification "key page"
```

Available on-demand commands:

```bash
python3 docs/tools/autopipeline/ap.py doctor
python3 docs/tools/autopipeline/ap.py docs-ledger-check
python3 docs/tools/autopipeline/ap.py docs-ledger-archive --plan --period YYYY-MM
python3 docs/tools/autopipeline/ap.py verify-api-docs
python3 docs/tools/autopipeline/ap.py verify-jenkins
python3 docs/tools/autopipeline/ap.py verify-target --backend-path /health --frontend-path /
python3 docs/tools/autopipeline/ap.py verify-jenkins-build --job-name <job-name> --build-number <number>
python3 docs/tools/autopipeline/ap.py verify-jenkins-build --job-url <job-url> --build-number <number>
python3 docs/tools/autopipeline/ap.py verify-jenkins-build --multibranch-root-job <root-job> --branch-name <branch> --build-number <number>
python3 docs/tools/autopipeline/ap.py runtime-up
python3 docs/tools/autopipeline/ap.py wait-health --scope runtime
python3 docs/tools/autopipeline/ap.py runtime-down
python3 docs/tools/autopipeline/ap.py check-matrix
python3 docs/tools/autopipeline/ap.py gen-summary <TASK_ID>
```

## Jenkins Build Tracking

- `verify-jenkins-build --git-ref HEAD`
  - Use when Jenkins build descriptions include commit SHA and you want to find the latest build automatically.
- `verify-jenkins-build --job-name <folder/job> --build-number <N>`
  - Use when you already know the Jenkins job and build number.
- `verify-jenkins-build --job-url <full-job-url> --build-number <N>`
  - Use when you want to bypass configured job resolution.
- `verify-jenkins-build --multibranch-root-job <folder/repo> --branch-name <branch> --build-number <N>`
  - Use for multibranch or organization-folder jobs where the branch is a child job.
- `verify-jenkins-build --multibranch-root-job <folder/repo> --git-ref HEAD`
  - Use when the current Git branch should be inferred automatically.
- If Jenkins returns `403`, the script retries with crumb / CSRF handling automatically.

## New Safeguards

- `doctor`
  - Checks whether the default lightweight workflow is actually configured instead of silently skipping gates.
- `light-gate`
  - Now prefers one curated fast gate command instead of serially running every expensive check.
- `verify-target`
  - Performs real target-environment verification beyond health checks when you provide key backend/frontend paths.
- `commit-push --record-closure`
  - Kept for compatibility; normal `commit-push` now records closure automatically based on `workflow.mode`.

## Publish (NPM)

1. Sync assets and basic check:

```bash
npm run sync-assets
npm test
```

2. Bump version:

```bash
npm version patch
# or: npm version minor / major
```

3. Release check:

```bash
npm whoami
npm run release:check
```

4. Publish:

```bash
npm publish --access public
# or
npm publish --access public --otp <6-digit-otp>
```

5. Verify and update:

```bash
npm view @elvis1513/auto-coding-skill version
npm install -g @elvis1513/auto-coding-skill@latest
```

## License

MIT
