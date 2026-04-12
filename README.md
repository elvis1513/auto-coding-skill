# auto-coding-skill

Engineering workflow skill for:

- Claude Code
- Codex CLI

This branch is specialized for Go backend + frontend monorepo projects that build Docker images locally, validate with project `docker compose`, and rely on Jenkins to auto-build and update target environments after push.
It supports both Claude and Codex. During development, it prefers already available MCP servers, installed skills, plugins, and app connectors for design, research, documentation, verification, and external system updates.
It also prefers multi-agent execution whenever the work can be split into parallel subtasks safely.

## Install

```bash
npm install -g @elvis1513/auto-coding-skill
```

Fallback:

```bash
npm install -g git+https://github.com/elvis1513/auto-coding-skill.git
```

## Standard Workflow

1. Install skill into project:

```bash
autocoding init --ai all
# or: --ai codex / --ai claude
```

2. Initialize docs and local scripts:

```bash
python3 .codex/skills/auto-coding-skill/scripts/ap.py --repo . install
# or
python3 .claude/skills/auto-coding-skill/scripts/ap.py --repo . install
```

3. Fill only one file manually:

- `docs/ENGINEERING.md` frontmatter

This frontmatter is the only manual config source (commands + local Docker runtime + Jenkins + docs paths).

4. Start AI development by constraints:

- `docs/ENGINEERING.md`
- `docs/tasks/taskbook.md`
- `docs/design/**`
- `docs/interfaces/**`
- `docs/testing/regression-matrix.md`
- `docs/bugs/bug-list.md`
- `docs/tasks/summaries/**`

5. Tool selection rule during execution:

- Prefer current MCP/skills/plugins/apps first.
- Fall back to shell/manual work only when those capabilities are unavailable or insufficient.

6. Collaboration rule during execution:

- Prefer multi-agent mode.
- Split research, design, implementation, validation, and documentation into parallel subtasks whenever the boundaries are clear.
- Keep one main agent responsible for integration and final gates.

7. Delivery rule during execution:

- Local `docker compose` validation must pass before commit.
- `git push` is expected to trigger Jenkins automatically.
- Task is not complete until Jenkins succeeds and the target environment health check passes.

8. Branch rule during execution:

- `dev` is the long-lived integration branch.
- If there is no parallel work conflict, prefer `dev`-first.
- If the repo is in detached HEAD, worktree mode, or another task is already mutating `dev`, create a temporary task branch first.
- Temporary branches should stay task-scoped and rebase back to latest `dev` before final integration.

## AGENTS.md Constraint Example

```md
## Mandatory Skill
- Always use `auto-coding-skill` for implementation tasks.
- Before any code change, read and obey:
  1) docs/ENGINEERING.md
  2) docs/tasks/taskbook.md
- Execute gates using `python3 docs/tools/autopipeline/ap.py`.
- If required docs are missing, create/update docs first, then code.
```

## Docs Structure and Recording Rules

### 1) docs/ENGINEERING.md
- Purpose: single source of project config + engineering gate rules.
- How to record:
  - Fill YAML frontmatter once (project/commands/runtime/jenkins/docs fields).
  - Keep all local runtime and Jenkins info here only (compose file/service/container/image/health/job/env).
  - Do not duplicate config in other docs.

### 2) docs/deployment/
- Files:
  - `docs/deployment/deploy-runbook.md`: local Compose validation + Jenkins deployment procedure.
  - `docs/deployment/deploy-records/<TASK_ID>-YYYYMMDD.md`: local validation + Jenkins deployment evidence.
- How to record:
  - Record both local Compose validation and Jenkins deployment evidence: compose file, service, container, image tag, Jenkins build, deploy env, health checks.

### 3) docs/design/
- Files:
  - `docs/design/<TASK_ID>-<slug>.md` (from DD template).
- Purpose:
  - Detailed design before coding (scope,方案、时序图、ER图、接口编排、测试策略、回滚).
- How to record:
  - One task/subtask one DD file.
  - Status changes: Draft -> Reviewed -> Approved.

### 4) docs/interfaces/
- Files:
  - `docs/interfaces/api.md`: authoritative API documentation (current contract).
  - `docs/interfaces/api-change-log.md`: append-only API changes per task.
- How to record:
  - API changes must update both files in the same task.
  - `api.md` records latest endpoint contract.
  - `api-change-log.md` appends task-level delta (新增/修改/废弃/兼容策略/影响面).

### 5) docs/reviews/
- Files:
  - `docs/reviews/<TASK_ID>-<timestamp>.md` (from review template).
- Purpose:
  - Gate review evidence: static checks, Go + frontend quality, local Compose validation, Jenkins readiness, risks.
- How to record:
  - Record commands used (lint/typecheck from docs/ENGINEERING.md frontmatter) and conclusion (Pass/Blocked).

### 6) docs/tasks/
- Files:
  - `docs/tasks/taskbook.md`: master task ledger (all tasks appended here).
  - `docs/tasks/summaries/<TASK_ID>.md`: end-of-task summary artifact.
- How to record:
  - `taskbook.md` stores task scope/acceptance/subtasks/evidence links.
  - `summaries/<TASK_ID>.md` stores final objective result, change overview, gate evidence, risks, follow-ups.

### 7) docs/testing/
- Files:
  - `docs/testing/regression-matrix.md`
- Purpose:
  - Full regression matrix against the local Compose environment; must be 0 FAIL.
- How to record:
  - Add rows by regression ID (R-xxx), area, steps/command, expected, status, evidence.
  - New or unexecuted rows must stay `TODO`.
  - `PASS` is valid only after real execution with non-placeholder evidence.
  - If any row is not `PASS`, or evidence is placeholder text, gate fails.

## Branch Policy

- `dev` is the only long-lived integration branch.
- Temporary branches are preferred when parallel worktrees or concurrent tasks would otherwise collide on `dev`.
- Temporary branches should be small, task-scoped, and rebased frequently against latest `dev`.
- Final integration target remains `dev`; temporary branches are not release branches.

## CI Trigger Strategy

- Prefer split Jenkins behavior:
- Branch or MR validation job for build/test/lint/typecheck and optional non-deploy runtime checks.
- `dev` integration/deploy job for actual deployment-triggering pushes.
- Avoid duplicate deploy triggers from both merge acceptance events and `dev` push events.

## Commands

```bash
pip install pyyaml requests
python3 docs/tools/autopipeline/ap.py run build
python3 docs/tools/autopipeline/ap.py run test
python3 docs/tools/autopipeline/ap.py run lint
python3 docs/tools/autopipeline/ap.py run typecheck
python3 docs/tools/autopipeline/ap.py run docker_build
python3 docs/tools/autopipeline/ap.py runtime-up
python3 docs/tools/autopipeline/ap.py wait-health
python3 docs/tools/autopipeline/ap.py run smoke
python3 docs/tools/autopipeline/ap.py run regression
python3 docs/tools/autopipeline/ap.py runtime-down
python3 docs/tools/autopipeline/ap.py verify-jenkins
python3 docs/tools/autopipeline/ap.py verify-jenkins-build --git-ref HEAD
python3 docs/tools/autopipeline/ap.py wait-health --scope prod
python3 docs/tools/autopipeline/ap.py verify-api-docs
python3 docs/tools/autopipeline/ap.py check-matrix
python3 docs/tools/autopipeline/ap.py gen-summary T0001-1
python3 docs/tools/autopipeline/ap.py commit-push T0001-1 --msg "T0001-1: <summary>" --require-runtime-health --require-jenkins --require-matrix
```

## Quality Gate Expectations

- Backend quality gate: `commands.test` must pass.
- Frontend quality gate: at minimum `commands.build`, `commands.lint`, and `commands.typecheck` must pass.
- Regression matrix rows must start as `TODO` until actually executed.
- `PASS` requires real evidence, not placeholders.
- Before final commit/push, clean temporary logs, screenshots, generated artifacts, and cache by-products. `.local/` may remain when it is the intended local runtime data directory.

## Publish (NPM)

1. Sync assets and basic check:

```bash
npm run sync-assets
npm test
```

2. Bump version (required before every publish):

```bash
npm version patch
# or: npm version minor
# or: npm version major
```

`npm version` will update `package.json` and create a git tag.

3. Login and run release check:

```bash
npm login
npm whoami
npm run release:check
```

4. Publish package:

```bash
npm publish --access public
# if your account requires 2FA OTP:
npm publish --access public --otp <6-digit-otp>
```

5. Verify and update clients:

```bash
npm view @elvis1513/auto-coding-skill version
npm install -g @elvis1513/auto-coding-skill@latest
```

### Common Publish Errors

- `403 You cannot publish over the previously published versions`
  - Cause: same version already exists.
  - Fix: run `npm version patch` (or `minor`/`major`) then publish again.
- `403 Two-factor authentication ... is required to publish`
  - Cause: publish requires 2FA.
  - Fix: use `npm publish --access public --otp <6-digit-otp>`.
- `404 Not Found` when install
  - Cause: package not published successfully, or scope/name mismatch.
  - Fix: verify with `npm view @elvis1513/auto-coding-skill version` first.
- `Access token expired or revoked`
  - Cause: npm auth token expired.
  - Fix: run `npm login` again and retry publish/install.

## License

MIT
