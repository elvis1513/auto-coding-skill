# auto-coding-skill

A delivery-first Codex engineering workflow:

`analysis → decomposition → necessary design → development → one final fast
changed-scope gate → commit/push`.

The Skill is a selectable guardrail, not a command sequence that must run for
every task. The model skips machinery whose expected benefit does not exceed its
cost; read-only work and obvious small clean-checkout changes normally stay direct.

Version 4.1.8 makes `autocoding init` the idempotent install-and-upgrade entry:
it replaces every managed constraint, migrates only schema-approved project
configuration, and converges `docs/` to one exact framework. Version 4.1.7 made
the Python runtime check, release verification, and tag publication environment
reproducible while removing the unnecessary `requests` dependency. Version 4.1.4
made direct continuation provably pre-write, closed self-review and
risk-classification gaps, validated Agent contracts, and made tag publication
idempotent. Version 4.1.3 closed classification bypasses. Version 4.1.2 made mechanisms required,
model-selectable when beneficial, or forbidden for the current task. Version
4.1.1 consolidated the 4.x delivery-first workflow into one canonical
repository contract. Version 4.0 replaced the 3.x governance-first defaults with progressive
guardrails. Clean single-writer work stays on the current branch. Worktrees,
parallel fixers, fingerprint review, durable design records, and stronger
affected-scope checks are enabled only when concurrency or risk justifies them.

## Install

```bash
npm install -g @elvis1513/auto-coding-skill
python3 -m pip install PyYAML==6.0.3
autocoding init
```

The project install contains:

```text
.agents/skills/auto-coding-skill/
.agents/agents/
docs/ENGINEERING.md
docs/tools/autopipeline/ap.py
AGENTS.md (fully managed canonical repository contract)
```

`autocoding init` also installs the exact shared documentation tree under
`docs/{architecture,bugs,deployment,design,interfaces,project,reviews,testing}`.
Files outside the canonical tree are archived under `.agents/archive/` and
removed from active `docs/`. Re-running init is the complete upgrade operation;
`sync` and project-local `upgrade` are compatibility commands, not required steps.

Fill the project/Jenkins/GitLab/Nexus URL, username, and password fields under
`access.*`, then configure one real fast validation command and run:

```bash
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
- `task_kind`: `read_only`, `change`, `terminal_maintenance`, or internal `none`.
- `mechanism_plan.required`: the complete minimum mechanism set for the task.
- `mechanism_plan.optional_when_beneficial`: model-selectable mechanisms whose
  expected benefit must exceed coordination cost.
- `mechanism_plan.forbidden`: mechanisms that stay off unless the user overrides.
- `optional_agents`: model-selectable explorer/docs/browser candidates; they are
  never automatic stages.
- an adaptive agent plan that does not force fan-out for ordinary work.

Clean serial work proceeds directly on the current branch with normal Git; it does
not create machine lifecycle state. Use `task-start` only when classification
requires isolation/review or the user explicitly requests lifecycle tracking:

When a direct task materially changes scope after writing, reclassify with
`--continue-direct` and repeat every current task `--planned-path`. Undeclared
dirty paths, another writer, or mandatory isolation still selects a worktree. If
the new plan requires review lifecycle, reuse `--continue-direct` on `task-start`.

```bash
python3 docs/tools/autopipeline/ap.py task-start T0001 \
  --owned-path backend/internal/orders --force-lifecycle
python3 docs/tools/autopipeline/ap.py commit-push T0001 \
  --msg "T0001: fix order retry"
```

When a required review still uses the current clean checkout, `task-start` records
a direct manifest without creating a branch/worktree. If no diff is produced,
closure clears the manifest without commit or push.

Dirty or parallel work receives an isolated task branch/worktree:

```bash
python3 docs/tools/autopipeline/ap.py task-start T0002 \
  --owned-path backend --review-required
# implement in the printed worktree
python3 docs/tools/autopipeline/ap.py task-status T0002 --json
python3 docs/tools/autopipeline/ap.py task-review T0002 \
  --verdict approved --diff-fingerprint "$CURRENT_DIFF_FINGERPRINT" \
  --reviewer "$REVIEWER_ID"
python3 docs/tools/autopipeline/ap.py commit-push T0002 \
  --msg "T0002: bounded change"
python3 docs/tools/autopipeline/ap.py task-integrate T0002
```

Integration serializes the target push and removes clean merged worktrees and
temporary branches. Unknown changes, unmerged history, unsafe ignored data, or
dirty submodules block cleanup rather than being discarded.

Parallel development uses one task ID and one `task-start` per writer. `--writers`
belongs to `classify` planning only; the runtime rejects overlapping active
`owned_paths` and never creates multiple writers in one task/worktree.

## Real changed-scope validation

Risk classification and validation execution are deliberately separate:

```yaml
commands:
  backend_fast: "cd backend && go test ./internal/orders/..."
  frontend_fast: "cd frontend && npm run test:changed"

validation:
  on_unmapped: error
  max_command_seconds: 120
  max_total_seconds: 180
  routes:
    - name: backend
      paths: ["backend/**", "contracts/**"]
      commands: [backend_fast]
      timeout_seconds: 90
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

The recommended final closure defaults are 120 seconds per command and 180
seconds total. Projects may raise them for measured affected-scope checks or set
a smaller `timeout_seconds` on a route. A timeout calls for a narrower route and
never triggers a broader fallback.

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
not polled automatically. An explicitly requested failure diagnosis may continue
in the same conversation/task without an artificial second ledger lifecycle.

## Upgrade projects

Finish every registered task using its currently installed runtime before changing
the Skill version. Then run `autocoding init` from each project root. It is safe to
rerun and needs no force flag.

```bash
cd /path/a && autocoding init
cd /path/b && autocoding init
autocoding status --projects /path/a,/path/b
```

Init replaces the managed Skill, root `AGENTS.md`, managed agents, ENGINEERING
schema/body, runtime launcher, and documentation framework. It preserves explicit
model overrides and current values at supported project/access/concurrency/route
fields. Removed content is archived outside active docs.

## What changed in 4.1.8

- Made `autocoding init` perform a complete project install or upgrade without a
  separate sync/upgrade chain or `--force`.
- Rebuilt ENGINEERING from the current schema, preserving only supported project
  values and removing unknown legacy fields and competing workflow text.
- Made the generated docs file/directory set exact and identical across projects;
  prior or extra content is archived under `.agents/archive/` before removal.
- Made root AGENTS, managed agents, the Skill copy, and the project launcher fully
  converge during init.

## What changed in 4.1.7

- Made tag publication reproducible with explicit Node 24, Python 3.12, and pinned
  PyYAML setup before package verification.
- Made `autocoding init` fail before writes with one interpreter-specific recovery
  command when its Python runtime cannot import PyYAML.
- Removed the `requests` runtime dependency by using Python's standard HTTP library.
- Made concurrency tests self-contained instead of borrowing local thread and Git
  identity configuration.
- Supported both GitHub-secret publication and local-token publication followed by
  idempotent tag verification.

## What changed in 4.1.4

- Added clean pre-write direct claims so broad paths cannot adopt unknown existing
  dirt after development starts.
- Prevented the current writer lease holder from approving its own diff and added
  executable assignment/result contract validation.
- Escalated high-confidence database, authorization, settlement, gateway, and
  production intents while keeping ordinary UI work lightweight.
- Made mechanism plans dependency-closed: parallel fixers require reclassification
  with multiple writers and therefore require isolated worktrees.
- Published from matching `v*` tags with idempotent npm registry checks and a final
  registry verification.

## What changed in 4.1.3

- Made explicit task kinds fail closed: `none` is internal-only and terminal
  maintenance cannot be applied to code or unrelated documentation paths.
- Added guarded `--continue-direct` reclassification for already-owned changes;
  unknown dirty paths still require isolation.
- Separated intent risk hints from path/rule-confirmed high risk so ordinary login
  or payment UI work no longer automatically receives a heavy lifecycle.
- Aligned generated Agent plans with their JSON Schema and exposed optional
  read-only Agent candidates without auto-dispatching them.
- Clarified delegated-fixer worktree ownership, reviewer identity, and explorer
  source authority.

## What changed in 4.1.2

- Added explicit read-only, change, and terminal-maintenance task kinds so
  intent-only questions cannot accidentally trigger code-delivery machinery.
- Split mechanism planning into required, model-selectable, and forbidden sets;
  read-only discovery agents remain available when they save time or add needed
  expertise.
- Made 120/180-second gate budgets recommended defaults, added route-level
  timeouts, and kept project-specific affected-scope overrides valid.
- Rejected unnecessary lifecycle creation before access checks, fetching, locks,
  or branch work; corrected the review lifecycle examples.
- Added a release-package assertion and prepack cache cleanup so generated Python
  caches cannot leak into the npm tarball.

## What changed in 4.1.1

- Added a machine-readable minimum mechanism plan and rejected unnecessary clean
  serial task lifecycles unless explicitly requested.
- Added bounded per-command and total time budgets for the final changed-scope gate.
- Made root `AGENTS.md` the sole behavioral protocol, reduced `SKILL.md` to
  invocation guidance, and reduced `ENGINEERING.md` to project configuration and
  facts.

## What changed in 4.1.0

- Made root `AGENTS.md` byte-identical across installed projects and whole-file
  managed on every full sync/upgrade.
- Established code/tests/runtime as the source of current behavior and
  `ENGINEERING.md` as the single project workflow/configuration source.
- Added an engineering-centered documentation framework plus optional
  `docs/project/` fact templates.
- Prevented Skill upgrades while any registered task is active and recorded the
  installed Skill version in new task manifests.
- Made reviewer scope bounded, with targeted recheck for mechanical docs-only
  fixes and non-blocking handling of adjacent findings.
- Defined ledger/archive reconciliation as a terminal maintenance action, so
  closing records cannot recursively create more task records.
- Kept explicit Jenkins failure diagnosis in the same requested task while
  preserving push-as-completion and no automatic polling.

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
