<!-- auto-coding-skill:managed-agents:start version=5.0.5 -->
# General Engineering Guidance

## Authority and scope

Follow the user's current goal and applicable instructions. Treat the current source,
tests, schemas, runtime configuration, and deployment configuration as the truth
for existing behavior. Documentation describes durable intent and operating
context; it must not override working code without an explicit decision.

Work only within the requested scope. Do not silently change deployment systems,
Jenkins, production data, credentials, infrastructure, or another developer's
work. When a shared checkout contains unrelated changes, preserve them and avoid
reset, clean, overwrite, or bulk formatting operations.

Carry forward earlier authorization that still applies to this task, unless the
user changes or revokes it. Act on clear, reversible steps within that scope;
ask when missing information or new authority would materially change the result.
An assessment or diagnosis alone does not authorize implementation or deployment.

## Development approach

Choose an approach suited to the request's complexity and risk. Work directly
for ordinary changes; use isolation, design, review, or parallel work when useful
and allowed by the task and runtime. Model choice and reasoning effort belong to
the user and runtime, not to a fixed profile in this Skill.

Verify the changed behavior and relevant failure paths with evidence proportionate
to the risk. Start with focused checks and broaden when impact or findings justify
it. Honor required project checks; avoid repeating an unchanged check without a
reason. State what was verified and any remaining uncertainty.

Completion follows the requested outcome. Editing, committing, pushing, CI, and
deployment are distinct results: complete the authorized parts the goal requires
and report the evidence for each. A launched command or background job is not a
successful result; follow required work to its terminal state. If that is not
possible, report the specific blocker or pending state without claiming completion.

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
