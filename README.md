# auto-coding-skill

A delivery-first Codex engineering workflow:

`analysis → decomposition → necessary design → development → one final fast
changed-scope gate → commit/push`.

Version 4.0 replaces the 3.x governance-first defaults with progressive
guardrails. Clean single-writer work stays on the current branch. Worktrees,
parallel fixers, fingerprint review, durable design records, and stronger
affected-scope checks are enabled only when concurrency or risk justifies them.

## Install

```bash
npm install -g @elvis1513/auto-coding-skill
autocoding init
autocoding sync --projects .
pip install pyyaml requests
```

The project install contains:

```text
.agents/skills/auto-coding-skill/
.agents/agents/
docs/ENGINEERING.md
docs/tools/autopipeline/ap.py
AGENTS.md (managed bridge only; project content is preserved)
```

Ordinary projects no longer receive taskbook or closure logs. Existing optional
documents are preserved during upgrades but are not required or updated by the
normal workflow.

Fill the project/Jenkins/GitLab/Nexus URL, username, and password fields under
`access.*`, then configure one real fast validation command and run:

```bash
python3 docs/tools/autopipeline/ap.py upgrade --write
python3 docs/tools/autopipeline/ap.py doctor
```

Plaintext credential values are allowed by the generic workflow.

## Adaptive development

Inspect a task before writing:

```bash
python3 docs/tools/autopipeline/ap.py classify --scope auto \
  --planned-path backend/internal/orders/service.go \
  --intent "fix order retry" \
  --writers 1
```

The result includes:

- `execution_mode=direct`: clean checkout and one writer; stay on the current branch.
- `execution_mode=isolated`: dirty checkout, explicit isolation, or multiple writers.
- `execution_mode=none`: no task signal or change; create no branch/worktree.
- `review_required` and `design_required`: risk-based escalation decisions.
- an adaptive agent plan that does not force fan-out for ordinary work.

Use a machine-enforced task lifecycle when useful:

```bash
python3 docs/tools/autopipeline/ap.py task-start T0001 \
  --owned-path backend/internal/orders
python3 docs/tools/autopipeline/ap.py commit-push T0001 \
  --msg "T0001: fix order retry"
```

On a clean single-writer checkout, `task-start` records a lightweight direct
manifest in the Git common directory and creates no branch or worktree.
`commit-push` runs the final gate, commits, and pushes the current target branch.
If no diff was produced, it clears the manifest without commit or push.

Dirty or parallel work receives an isolated task branch/worktree:

```bash
python3 docs/tools/autopipeline/ap.py task-start T0002 \
  --owned-path backend --writers 2 --review-required
# implement in the printed worktree
python3 docs/tools/autopipeline/ap.py task-review T0002 \
  --verdict approved --diff-fingerprint "$SHA256"
python3 docs/tools/autopipeline/ap.py commit-push T0002 \
  --msg "T0002: bounded change"
python3 docs/tools/autopipeline/ap.py task-integrate T0002
```

Integration serializes the target push and removes clean merged worktrees and
temporary branches. Unknown changes, unmerged history, unsafe ignored data, or
dirty submodules block cleanup rather than being discarded.

## Real changed-scope validation

Risk classification and validation execution are deliberately separate:

```yaml
commands:
  backend_fast: "cd backend && go test ./internal/orders/..."
  frontend_fast: "cd frontend && npm run test:changed"

validation:
  on_unmapped: error
  routes:
    - name: backend
      paths: ["backend/**", "contracts/**"]
      commands: [backend_fast]
    - name: frontend
      paths: ["frontend/**"]
      commands: [frontend_fast]

risk:
  rules:
    - name: auth
      paths: ["backend/**/auth/**"]
      profile: high-risk
      review: required
```

Every path may match multiple routes. All referenced commands are collected in
configuration order, de-duplicated, and executed once. Unmapped code and missing
commands fail before staging. Documentation-only changes may use the built-in
diff check. `git diff --check` remains an additional hygiene check and is never
treated as business validation.

Check coverage without running project commands:

```bash
python3 docs/tools/autopipeline/ap.py validation-map-check --path contracts/api.yaml
python3 docs/tools/autopipeline/ap.py validation-map-check --tracked
```

Focused tests may be run and rerun during implementation. Only the final routed
closure gate is limited to one stable-diff run. Full regression, Docker, builds,
Jenkins, deployment, API verification, and target checks remain explicit
diagnostics outside normal closure.

## Risk and subagent policy

- Micro and standard work default to the main agent.
- Read-only explorer/docs/browser roles run only for independent questions with
  clear value.
- Parallel fixers require separate worktrees and non-overlapping paths.
- Reviewer fingerprint approval is required for high-risk, cross-module,
  explicitly configured, or parallel integration work.
- DD/ADR is created only for lasting cross-module, API, data, security,
  deployment, or key user-flow decisions.
- Historical debt does not block product work unless the current change worsens it.

The main agent owns architecture, final validation, Git closure, ordered
integration, push, and cleanup. Push ends the coding task; later CI/acceptance is
handled only through a separately requested diagnostic task.

## Upgrade and multi-project sync

Finish all in-flight schema-1/schema-2 registered tasks using their installed 3.x
runtime before syncing 4.0. Batch sync fails before any writes when it finds an
incompatible active task.

```bash
autocoding status --projects /path/a,/path/b
autocoding sync --projects /path/a,/path/b --dry-run
autocoding sync --projects /path/a,/path/b
```

Sync replaces the managed Skill directory, so missing files are restored and
obsolete managed files are removed. It preserves project frontmatter, access
values, custom agents, explicit model overrides, optional documents, and content
outside managed AGENTS/ENGINEERING blocks.

## What changed in 4.0.0

- Added real `direct` and `isolated` runtime execution modes.
- Stopped creating branches/worktrees for clean serial or no-diff work.
- Added multi-match `validation.routes`, stable command de-duplication,
  fail-closed unmapped code, and `validation-map-check`.
- Separated `risk.rules` from executable validation.
- Made ordinary tasks main-agent-first and review/design conditional.
- Kept advanced worktree ownership, dependency SHA, lease, fingerprint,
  integration, submodule safety, and branch cleanup for parallel/high-risk work.
- Removed taskbook, closure, evidence, and active-task documents from the default
  scaffold and normal closure path.
- Changed structure/debt policy to no-new-debt and kept full/CI/runtime checks as
  explicit diagnostics.
- Added schema-3 task manifests and atomic sync refusal for in-flight pre-4.0 tasks.

## Maintainer commands

```bash
npm run sync-assets
npm run release:check
```

`release:check` validates source/assets, Python 3.11 grammar, managed Agent TOML,
CLI/profile/concurrency regressions, and the npm package contents.

License: MIT.
