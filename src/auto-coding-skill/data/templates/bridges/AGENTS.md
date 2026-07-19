<!-- auto-coding-skill:managed-agents:start version=5.0.0 -->
# General Engineering Guidance

## Authority and scope

Use the current user request as the primary authority. Treat the current source,
tests, schemas, runtime configuration, and deployment configuration as the truth
for existing behavior. Documentation describes durable intent and operating
context; it must not override working code without an explicit decision.

Work only within the requested scope. Do not silently change deployment systems,
Jenkins, production data, credentials, infrastructure, or another developer's
work. When a shared checkout contains unrelated changes, preserve them and avoid
reset, clean, overwrite, or bulk formatting operations.

## Development approach

Choose the smallest useful approach for the request. Work directly for ordinary
changes. Use a branch, worktree, tests, review, design note, or diagnostic only
when the task or repository makes it useful; none is required by this guidance.

Do not treat a test, build, lint, review, commit, push, Jenkins run, deployment,
or target check as mandatory completion ceremony. Run a check when the user asks,
when the project explicitly needs it, or when it is the proportionate way to
answer a technical question. State clearly what was and was not verified.

## Documentation

Read relevant project documentation before relying on project context:

- `docs/ENVIRONMENT.md`: shared GitLab, Nexus, Jenkins, and backend endpoint/port references. Managed and refreshed by the Skill.
- `docs/PROJECT.md`: project-specific runtime facts, access overrides, and constraints. Project-owned and never overwritten by the Skill.
- `docs/product/`: durable product context, boundaries, and decisions.
- `docs/architecture/`: architecture and ADRs.
- `docs/design/`: durable design notes that help future implementation.
- `docs/interfaces/`: public API, event, protocol, or integration contracts.
- `docs/deployment/`: runbooks and durable operating procedures.

Documentation is optional. Do not create a record for a routine edit, a transient
investigation, an ordinary review, or every commit. Record something only when the
user asks or when the information will remain useful after the immediate task.
Put it in the narrowest applicable folder and update an existing document instead
of creating parallel summaries.

## Environment and credentials

`docs/ENVIRONMENT.md` is shared managed context: it names endpoint ports and
credential lookup guidance, but never contains plaintext credentials. Project
specific configuration belongs in `docs/PROJECT.md`; it is preserved across
Skill upgrades and may hold project-approved plaintext credential records. Never
invent credentials, copy them into chat output, or expose them in logs.

<!-- auto-coding-skill:managed-agents:end -->
