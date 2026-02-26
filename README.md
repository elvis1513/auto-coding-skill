# auto-coding-skill

Framework-agnostic engineering workflow skill for:

- Claude Code
- Codex CLI

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

This frontmatter is the only manual config source (commands + deployment + docs paths).

4. Start AI development by constraints:

- `docs/ENGINEERING.md`
- `docs/tasks/taskbook.md`
- `docs/design/**`
- `docs/interfaces/**`
- `docs/testing/regression-matrix.md`
- `docs/bugs/bug-list.md`
- `docs/tasks/summaries/**`

## AGENTS.md Constraint Example

```md
## Mandatory Skill
- Always use `auto-coding-skill` for implementation tasks.
- Before any code change, read and obey:
  1) docs/ENGINEERING.md
  2) docs/tasks/taskbook.md
- Execute gates using `python3 scripts/autopipeline/ap.py`.
- If required docs are missing, create/update docs first, then code.
```

## Docs Structure and Recording Rules

### 1) docs/ENGINEERING.md
- Purpose: single source of project config + engineering gate rules.
- How to record:
  - Fill YAML frontmatter once (project/commands/deployment/docs fields).
  - Keep all environment info here only (ip/username/password/service/path/health).
  - Do not duplicate config in other docs.

### 2) docs/deployment/
- Files:
  - `docs/deployment/deploy-runbook.md`: deployment procedure and validation checklist.
  - `docs/deployment/deploy-records/<TASK_ID>-YYYYMMDD.md`: per-deploy execution record.
- How to record:
  - In deploy record, write target host, service, artifact, remote path, backup, systemctl status, smoke/regression evidence.

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
  - Gate review evidence: static checks, code quality, test quality, risks.
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
  - Full regression matrix; must be 0 FAIL.
- How to record:
  - Add/maintain rows by regression ID (R-xxx), area, steps/command, expected, status, evidence.
  - If any FAIL exists, gate fails.

## Commands

```bash
pip install pyyaml requests
python3 scripts/autopipeline/ap.py run build
python3 scripts/autopipeline/ap.py run test
python3 scripts/autopipeline/ap.py run lint
python3 scripts/autopipeline/ap.py verify-api-docs
python3 scripts/autopipeline/ap.py check-matrix
python3 scripts/autopipeline/ap.py gen-summary T0001-1
python3 scripts/autopipeline/ap.py commit-push T0001-1 --msg "T0001-1: <summary>" --require-matrix
```

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
