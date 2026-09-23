---
name: auto-coding-skill
description: Use when a project opts into auto-coding-skill or the user asks to initialize, refresh, or inspect its project guidance and documentation. Provides context without imposing a fixed engineering workflow.
---

# Auto Coding Skill

Read `AGENTS.md`, then use the project documentation only when it helps the
current request:

- `docs/ENVIRONMENT.md` for shared access endpoints, ports, and local credential references.
- `docs/PROJECT.md` for project-specific runtime facts and configuration.
- `docs/product/` for durable product context and decisions.
- `docs/architecture/`, `docs/design/`, `docs/interfaces/`, and
  `docs/deployment/` for existing topic-specific knowledge.

Use the project's guidance to choose an approach and enough verification for the
requested outcome. This Skill adds context, not a fixed task protocol or model
profile; it does not narrow existing authorization or redefine completion.

Write documentation only when the user asks for it or when a durable fact,
contract, decision, test strategy, or operating procedure would otherwise be
lost. Choose the relevant existing folder; do not create routine task records,
review records, or duplicate summaries.

`autocoding init` refreshes `AGENTS.md` and `docs/ENVIRONMENT.md`. It creates
`docs/PROJECT.md` and topic directories only when missing, and never overwrites
project-owned documentation.
