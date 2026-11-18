---
name: auto-coding-skill
description: Use in opted-in projects to locate project-owned context, or to inspect and safely refresh their managed guidance.
---

# Auto Coding Skill

The repository's `AGENTS.md` is the shared entry point. If its instructions and
the applicable project context are already in this chat, use them; revisit when
the checkout, constraints, or task scope changes.

For a project fact, start at the relevant section of `docs/PROJECT.md` and
follow its links. Shared endpoint and credential **lookup** guidance lives in
`docs/ENVIRONMENT.md`; do not dump access records into tool or chat output.

For worktree setup, conflicts or integration, see
[parallel development](references/parallel-development.md). For a Skill upgrade,
preview with `autocoding init --dry-run`. If managed content has diverged,
review and migrate project facts before explicitly replacing it with a private
external backup. Existing project documents are never overwritten by init/sync.
`autocoding doctor` is an optional read-only diagnostic, not a development step.
