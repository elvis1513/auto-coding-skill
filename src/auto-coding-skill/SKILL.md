---
name: auto-coding-skill
description: Use for strict project engineering workflow in Claude/Codex. It initializes docs and enforces taskbook -> design -> implement -> quality gates -> docs -> deploy -> regression -> summary -> commit/push.
---

# Auto Coding Skill (Claude + Codex)

## Supported clients

- Claude Code
- Codex CLI

## Entry

1) Install skill files into target repo:

```bash
autocoding init --ai codex
# or claude / all
```

2) Initialize docs/tooling:

```bash
python3 .codex/skills/auto-coding-skill/scripts/ap.py --repo . install
# or .claude path
```

Install runtime deps:

```bash
pip install pyyaml requests
```

## Single manual config file

Fill only this file:

- `docs/project/project-config.md`

YAML frontmatter in this file contains:
- `commands.*`
- `deployment.*`
- `docs.*`

Do not duplicate config in other md/yaml files.

## Execution order

1) `ENGINEERING.md`
2) `docs/project/project-config.md`
3) `docs/tasks/taskbook.md`
4) `docs/design/**`
5) implementation
6) run gates via `python3 tools/autopipeline/ap.py`
7) update API docs + regression matrix + bug list + summary
8) commit/push

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
