---
name: auto-coding-skill
description: Use for strict project engineering workflow in Claude/Codex. Initialize docs, fill ENGINEERING.md frontmatter once, then execute design->implement->gates->summary->commit/push.
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

3) Install runtime deps:

```bash
pip install pyyaml requests
```

## Single manual config source

Fill only:

- `ENGINEERING.md` frontmatter

This contains all manual fields:
- `commands.*`
- `deployment.*`
- `docs.*`

Do not duplicate config in other md/yaml files.

## Execution order

1) `ENGINEERING.md`
2) `docs/tasks/taskbook.md`
3) `docs/design/**`
4) implementation
5) run gates via `python3 scripts/autopipeline/ap.py`
6) update API docs + regression matrix + bug list + summary
7) commit/push

## Commands

```bash
python3 scripts/autopipeline/ap.py run build
python3 scripts/autopipeline/ap.py run test
python3 scripts/autopipeline/ap.py run lint
python3 scripts/autopipeline/ap.py verify-api-docs
python3 scripts/autopipeline/ap.py check-matrix
python3 scripts/autopipeline/ap.py gen-summary T0001-1
python3 scripts/autopipeline/ap.py commit-push T0001-1 --msg "T0001-1: <summary>" --require-matrix
```
