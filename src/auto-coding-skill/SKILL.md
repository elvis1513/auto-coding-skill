---
name: auto-coding-skill
description: Framework-agnostic engineering workflow skill for Claude Code and Codex CLI. Use it to scaffold docs and enforce gates from task intake to design, implementation, test, review, API docs, deployment, regression, summary, commit and push.
---

# Auto Coding Skill (Claude + Codex Only)

This skill is portable across projects and does not depend on any specific scaffold.

## Supported clients

- Claude Code
- Codex CLI

## Workflow gates

Taskbook -> DD -> Implement -> Build/Test -> Static Analysis -> Review -> API Docs -> Deploy -> Smoke -> Regression Matrix (0 fail) -> Summary -> Commit -> Push

## Install into a target repo

From the target repo root:

```bash
# Claude Code
autocoding init --ai claude

# Codex CLI
autocoding init --ai codex

# Both
autocoding init --ai all
```

## Initialize project scaffold

Run one of the following (depending on where the skill was installed):

```bash
python3 .claude/skills/auto-coding-skill/scripts/ap.py --repo . install
# or
python3 .codex/skills/auto-coding-skill/scripts/ap.py --repo . install
```

This will create `ENGINEERING.md`, `docs/**`, `tools/autopipeline/ap.py`, and update `.gitignore` with `docs/deployment/targets.yaml`.

## Configure project commands

Copy and edit config:

```bash
cp docs/autocoding/config.example.yaml autocoding.config.yaml
```

Set at least:

- `commands.build`
- `commands.test`
- `commands.lint`
- `commands.typecheck`
- `commands.smoke`
- `commands.regression`

## Common commands

```bash
python3 tools/autopipeline/ap.py run build
python3 tools/autopipeline/ap.py run test
python3 tools/autopipeline/ap.py run lint
python3 tools/autopipeline/ap.py verify-api-docs
python3 tools/autopipeline/ap.py check-matrix
python3 tools/autopipeline/ap.py gen-summary T0001-1
python3 tools/autopipeline/ap.py commit-push T0001-1 --msg "T0001-1: <summary>" --require-matrix
```
