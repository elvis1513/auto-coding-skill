<!-- auto-coding-skill:managed-agents:start version=5.2.0 -->
# Working in this project

Before writing files or operating an environment, use the applicable constraints
and entry points in `docs/PROJECT.md`. Read the relevant section, not the whole
file; reuse current context. Put temporary output in the project-approved
location (normally `.local/<task>/`), including output from other tools.

Develop changes on a task-owned `codex/*` branch in an independent linked
worktree based on current `dev`. Reuse the same worktree for follow-ups; do not
edit on shared `dev` or switch, stash, or clean another chat's workspace.
Resolve conflicts in the task worktree, verify the combined change and integrate
without force. For setup, integration and cleanup details see
[parallel development](.agents/skills/auto-coding-skill/references/parallel-development.md).
Read-only work needs no branch.

Choose tools, reasoning and delegation to fit the task. Verify changed behavior
in proportion to risk and honor project-required checks. Diagnosis does not
authorize changes. Report what actually finished: local integration, push, CI,
deployment and user acceptance are distinct. Do not trigger duplicate pipelines
or wait for unrelated jobs.

This file, the installed Skill and `docs/ENVIRONMENT.md` are managed. Keep
project-specific facts in `docs/PROJECT.md` or a linked topic, never in these
managed files. Write documentation when requested or when durable knowledge
would otherwise be lost; do not create routine task records. Never print secrets.
<!-- auto-coding-skill:managed-agents:end -->
