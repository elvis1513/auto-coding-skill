---
name: auto-coding-skill
description: Use when a project opts into auto-coding-skill or the user asks to initialize, refresh, or inspect its project guidance and documentation. Provides context without imposing a fixed engineering workflow.
---

# Auto Coding Skill

Read `AGENTS.md`. Before repository edits, artifact-producing tools, or environment
operations, read the applicable constraints and entry points in `docs/PROJECT.md`.
Start with its short current-context section and follow only relevant links;
do not routinely load its history or credential records in full.

- `docs/ENVIRONMENT.md` for shared access endpoints, ports, and local credential references.
- `docs/PROJECT.md` for project-specific runtime facts and configuration.
- `docs/product/` for durable product context and decisions.
- `docs/architecture/`, `docs/design/`, `docs/interfaces/`, and
  `docs/deployment/` for existing topic-specific knowledge.

Use the project's guidance to choose an approach and enough verification for the
requested outcome. This Skill adds context, not a fixed task protocol or model
profile; it does not narrow existing authorization or redefine completion.

For repository changes, use a task-owned `codex/*` branch in an independent
worktree, then integrate the verified result into `dev`. Read
[parallel development](references/parallel-development.md) before creating or
integrating a task worktree. Read-only questions do not require a branch.

Project constraints govern tool output paths, including defaults from other
skills. Put temporary output in the project's approved location, normally
`.local/<task>/`; do not create root-level output directories by default.

Write documentation only when the user asks for it or when a durable fact,
contract, decision, test strategy, or operating procedure would otherwise be
lost. Choose the relevant existing folder; do not create routine task records,
review records, or duplicate summaries.

The installed skill, `AGENTS.md`, and `docs/ENVIRONMENT.md` are managed assets:
never append project-specific instructions or environment facts to them. Put
those in `docs/PROJECT.md` or its linked topic documents. Keep current constraints
and entry points prominent; maintain historical detail in the relevant existing
topic document rather than appending a diary to the project entry point.

`autocoding init` and `sync` preview changes with `--dry-run`. Modified or unowned
managed files block replacement until reviewed; migrate useful project content
first, then explicitly replace with a private external backup. Existing
`docs/PROJECT.md` and topic documents are never overwritten.
