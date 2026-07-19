---
name: auto-coding-skill
description: General project guidance and a lightweight documentation layout. It provides context files and optional places to record durable project knowledge, without imposing a development workflow.
---

# Auto Coding Skill

Read `AGENTS.md`, then use the project documentation only when it helps the
current request:

- `docs/ENVIRONMENT.md` for local/runtime facts and project-approved access data.
- `docs/product/` for durable product context and decisions.
- `docs/architecture/`, `docs/design/`, `docs/interfaces/`, and
  `docs/deployment/` for existing topic-specific knowledge.

This Skill has no required task protocol. It does not require classification,
Gates, Reviews, worktrees, designs, tests, commits, or deployment checks.

Write documentation only when the user asks for it or when a durable fact,
contract, decision, test strategy, or operating procedure would otherwise be
lost. Choose the relevant existing folder; do not create routine task records,
review records, or duplicate summaries.

`autocoding init` creates missing guidance, the environment file, and empty
topic directories. It never overwrites project documentation.
