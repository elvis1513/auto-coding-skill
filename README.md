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
# or claude / all
```

2. Initialize docs and local scripts:

```bash
python3 .codex/skills/auto-coding-skill/scripts/ap.py --repo . install
# or
python3 .claude/skills/auto-coding-skill/scripts/ap.py --repo . install
```

3. Fill only one file manually:

- `ENGINEERING.md` frontmatter

This frontmatter is the only manual config source (commands + deployment + docs paths).

4. Start AI development by constraints:

- `ENGINEERING.md`
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
  1) ENGINEERING.md
  2) docs/tasks/taskbook.md
- Execute gates using `python3 scripts/autopipeline/ap.py`.
- If required docs are missing, create/update docs first, then code.
```

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

## Release New Version

1. Bump version (cannot republish an existing version):

```bash
npm version patch
# or: npm version minor
# or: npm version major
```

2. Login and pre-check:

```bash
npm login
npm whoami
npm run release:check
```

3. Publish:

```bash
npm publish --access public --otp <6-digit-otp>
```

4. Verify release:

```bash
npm view @elvis1513/auto-coding-skill version
```

5. Update installed clients:

```bash
npm install -g @elvis1513/auto-coding-skill@latest
```

## License

MIT
