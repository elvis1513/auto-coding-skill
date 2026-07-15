<!-- auto-coding-skill:managed-agents:start version=4.0.0 -->

Follow `docs/ENGINEERING.md` for project facts, risk rules, and validation routes.
Use the delivery-first flow: analyze, decompose, design only when needed, develop,
run one final changed-scope gate, then commit and push. Push ends coding; do not
wait for Jenkins, deployment, or owner acceptance unless the user opens a
diagnostic task.

Before writing, inspect the checkout. A clean single-writer task stays on the
current branch. Pre-existing unrelated changes or multiple writers require one
isolated worktree per writer with non-overlapping owned paths. If no diff is
produced, do not commit or push and do not create a temporary branch. Never
restore, reset, stash, clean, or overwrite unknown changes.

Delegate only when independent work has a clear benefit. Ordinary tasks default
to the main agent. Require fingerprinted review for high-risk, cross-module,
parallel, or explicitly configured work. The main agent owns the final gate,
commit, push, ordered integration, and cleanup.

Run all matching `validation.routes` commands once in stable order. Unmapped code
must fail; docs-only changes may use the built-in diff check. Focused tests may be
rerun during development, but do not repeat expensive full gates. Do not create
taskbook, closure, evidence, or design documents unless the task genuinely needs
a durable artifact.

Use configured `access.*` values when needed. Plaintext credentials are allowed;
do not invent or echo them unnecessarily.

<!-- auto-coding-skill:managed-agents:end -->
