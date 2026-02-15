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
autocoding init --ai codex
# or
autocoding init --ai claude
# or both
autocoding init --ai all
```

2. Initialize docs/tooling:

```bash
python3 .codex/skills/auto-coding-skill/scripts/ap.py --repo . install
# or
python3 .claude/skills/auto-coding-skill/scripts/ap.py --repo . install
```

3. Fill one config file only:

- `docs/project/project-config.md`

This file is the single source for:
- build/test/lint/typecheck/smoke/regression commands
- deployment info (ip/user/password/service/path/health)
- docs paths

Required Python deps:

```bash
pip install pyyaml requests
```

4. Let AI execute workflow by docs constraints:

- `ENGINEERING.md`
- `docs/tasks/taskbook.md`
- `docs/design/**`
- `docs/interfaces/**`
- `docs/testing/regression-matrix.md`
- `docs/bugs/bug-list.md`
- `docs/tasks/summaries/**`

## AGENTS.md Constraint Example

Add this in project `AGENTS.md`:

```md
## Mandatory Skill
- Always use `auto-coding-skill` for every implementation task.
- Before any code change, read and obey:
  1) ENGINEERING.md
  2) docs/project/project-config.md
  3) docs/tasks/taskbook.md
- Execute gates using `python3 tools/autopipeline/ap.py`.
- If any required doc is missing, create/update docs first, then code.
```

## Commands

```bash
python3 tools/autopipeline/ap.py run build
python3 tools/autopipeline/ap.py run test
python3 tools/autopipeline/ap.py run lint
python3 tools/autopipeline/ap.py verify-api-docs
python3 tools/autopipeline/ap.py check-matrix
python3 tools/autopipeline/ap.py gen-summary T0001-1
python3 tools/autopipeline/ap.py commit-push T0001-1 --msg "T0001-1: <summary>" --require-matrix
```

## Publish

```bash
npm login
npm whoami
npm run release:check
npm publish --access public
```

## License

MIT
