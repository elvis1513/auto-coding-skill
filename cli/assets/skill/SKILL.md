---
name: auto-coding-skill
description: Use for strict project engineering workflow in Claude/Codex. Initialize docs, fill docs/ENGINEERING.md frontmatter once, then execute design->implement->local-docker-gates->summary->commit/push.
---

# Auto Coding Skill (Claude + Codex)

This skill is a Claude/Codex-only engineering workflow. During design, research, implementation, verification, and delivery, prefer already available MCP servers, installed skills, plugins, and app connectors over ad-hoc manual work whenever they can complete the task reliably.

Default to multi-agent execution when the client supports it. Break work into independent design, research, implementation, validation, and documentation subtasks so Claude/Codex can run them in parallel whenever that reduces cycle time without weakening control of the main task.

## Supported clients

- Claude Code
- Codex CLI

## Tooling policy

Use available platform capabilities first:

1) Prefer installed MCP servers for design context, documentation lookup, browser automation, issue/docs systems, and deployment/runtime inspection.
2) Prefer already installed local skills when the task matches them.
3) Prefer supported plugins/apps/connectors when they provide authoritative project context or can write back records.
4) Fall back to manual shell/code workflows only when the above are unavailable, insufficient, or slower than direct execution.

Typical examples:
- Design/UI work: prefer Figma MCP and related design skills.
- Documentation/library lookup: prefer official docs and MCP-backed doc tools.
- Project management or knowledge base updates: prefer Linear/Notion connectors if available.
- Browser/runtime verification: prefer Playwright/browser tools if available.

## Collaboration policy

Prefer multi-agent mode across the workflow:

1) Split independent subtasks early when they can run in parallel.
2) Keep the main agent on the critical path: task framing, design decisions, integration, and final quality gates.
3) Use side agents for bounded work such as research, code slices, documentation updates, regression checks, or review passes.
4) Do not delegate a blocking architectural decision without keeping one agent responsible for final integration and correctness.

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

- `docs/ENGINEERING.md` frontmatter

This contains all manual fields:
- `commands.*`
- `runtime.*`
- `docs.*`

Do not duplicate config in other md/yaml files.

## Execution order

1) `docs/ENGINEERING.md`
2) `docs/tasks/taskbook.md`
3) `docs/design/**`
4) implementation
5) run gates via `python3 scripts/autopipeline/ap.py`
6) start and validate local Docker runtime
7) update API docs + regression matrix + bug list + summary
8) commit/push

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
