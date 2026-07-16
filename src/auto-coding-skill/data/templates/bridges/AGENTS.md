<!-- auto-coding-skill:managed-agents:start version=4.2.0 -->
# Shared Engineering Protocol

This file is fully managed by `auto-coding-skill`. Keep project-specific facts,
access values, risk rules, and validation routes in `docs/ENGINEERING.md`.

## Authority

Use this order when sources disagree:

1. The current user request.
2. Code, tests, schemas, migrations, and runtime configuration for behavior that
   exists now.
3. `docs/ENGINEERING.md` for workflow configuration and access values, then the
   managed `docs/project/` files for durable project facts.
4. Current interface documentation for intended contracts.
5. Accepted DD/ADR for lasting decisions.
6. Taskbooks, closures, reviews, and deployment records as history only.

Update authoritative documentation when a change intentionally changes its
contract. Never let stale history override current implementation.

## Minimum mechanism budget

Use only mechanisms that improve expected delivery speed or defect prevention.
The default budget is:

| Situation | Required mechanisms |
| --- | --- |
| Read-only question | analysis only; no workflow command |
| Obvious clean serial edit | analysis, affected gate, commit/push |
| Terminal ledger/archive maintenance | targeted consistency check, one commit |
| Dirty checkout or concurrent writer | registered lifecycle and isolated worktree |
| High-risk or contract-crossing change | necessary design and independent review |
| Multiple independent writers | one task/worktree/lease per writer, ordered integration |

Do not add classify, task lifecycle, durable design, subagents, reviewer, or a
worktree merely because the tool exists. If task kind or impact is unclear, run
`classify`: run `mechanism_plan.required`, let the model select
`optional_when_beneficial` only when expected value exceeds coordination cost,
and keep `forbidden` mechanisms off unless the user explicitly overrides the
plan. Reclassify only after a material task-kind, scope, risk, or writer change.

Normal delivery is:

`analysis → decomposition → necessary design → development → one bounded final
changed-scope gate → commit/push`.

Push to the target branch ends normal coding. Do not poll Jenkins, deploy, or run
owner acceptance automatically. A user-requested diagnosis of the just-pushed
failure may continue in the same conversation/task without a second lifecycle.

## Git and parallel work

- One writer in a clean checkout works directly. If review may be needed, create a
  claim before the first write; continuation requires that claim and exact paths.
- Existing unrelated changes, another writer, or configured mandatory isolation
  requires a registered task branch/worktree.
- Every delegated fixer or parallel writer owns a task ID/worktree, writer lease,
  non-overlapping `owned_paths`, and prerequisite commit SHAs.
- Before its first commit, an active task may add explicit paths with
  `task-scope-add`; the command checks leases/conflicts, only raises risk, and
  invalidates prior review and final-gate state. Never restart a no-diff task just
  to enlarge its declared scope.
- Never let multiple writing agents share a checkout. Never restore, reset, stash,
  clean, overwrite, or commit unknown changes.
- No diff means no commit, push, or temporary branch.
- Main integrates in dependency order and removes only clean, merged temporary state.
- Do not sync or upgrade while any registered task is active.

## Design, agents, and review

- Micro and standard tasks stay main-agent-only unless the model identifies an
  independent question whose latency or expertise benefit exceeds coordination
  cost.
- Create DD/ADR only for lasting cross-module, API, data, security, deployment,
  or key user-flow decisions.
- Use read-only explorer/docs/browser agents only for independent questions.
- Use parallel fixers only for bounded, dependency-free, non-overlapping units.
- Reclassify before parallel fixers; single-writer plans grant no implicit writes.
- Validate delegated assignment/result JSON with `agent-contract-check` before use.
- Require fingerprinted review only for path/rule-confirmed high-risk,
  contract-crossing, parallel, or configured work; intent words are candidates only.
- Review blocks only defects introduced or worsened in the promised scope.
  Adjacent existing issues are non-blocking follow-ups.
- Semantic changes invalidate approval. Mechanical documentation-only corrections
  may receive a targeted recheck by the same reviewer.
- Historical debt does not block ordinary delivery; block only new or worsened
  P0/P1 issues.

## Bounded real validation

- `risk.rules` controls reasoning/review depth. `validation.routes` alone selects
  executable closure checks.
- Every changed code/config path must match one or more explicit routes. Run every
  matched command once in stable order and de-duplicate references.
- Unmapped code or blank commands fail before staging. Documentation-only work may
  use the built-in diff/format check. `git diff --check` is hygiene, not business
  validation.
- Focused tests may run and rerun during development. Run one final routed gate
  after the diff is stable.
- For registered tasks, `commit-push` owns that final gate; do not run a separate
  `light-gate` first. A strict Git-local PASS receipt may be reused only while the
  content/index, base, scope, route/command plan, and writer lease still match.
  Unregistered clean serial work runs `light-gate` before normal Git closure.
- The final gate defaults to 120 seconds per command and 180 seconds total. A
  project may raise either budget for a measured affected-scope check, and may set
  a smaller `timeout_seconds` on an individual route. A timeout should narrow the
  route; never expand or retry it as a full gate.
- Do not proactively install dependencies. Only after the selected route fails
  because a repository-locked dependency is absent may it be restored once and
  only that route retried.
- Full regression, repository-wide scans, builds, Docker, Jenkins, deployment,
  live-device writes, browser/API acceptance, and target checks are explicit
  diagnostics, not normal closure.
- External-system writes require the project safety rule or user confirmation;
  use fixtures/simulators when the project supplies them.

## Documentation and access

- This AGENTS file is the single behavioral protocol. The installed `SKILL.md`
  contains invocation guidance. `docs/ENGINEERING.md` is the exact project
  configuration source; `docs/project/` owns durable facts. Do not repeat the
  protocol elsewhere.
- `autocoding init` owns the active `docs/` directory topology and managed
  templates. Put durable facts into the installed project files. Architecture,
  ADR, interface, DD, review, and deploy-record artifacts may use their designated
  directories; unrelated directories are archived outside active docs on upgrade.
- The managed-install manifest owns only its declared files and exact namespaces.
  Never treat the whole `.agents` or `docs` tree as a release-package mirror.
- Ordinary work creates no taskbook, closure Markdown, evidence JSONL, active-task
  document, or design file. Machine coordination/evidence stays in Git
  common/local state and cannot change the reviewed diff.
- Pure ledger/archive reconciliation is terminal: validate, commit once, and stop.
- Fill configured project/Jenkins/GitLab/Nexus access fields during initialization.
  Plaintext values are allowed; do not invent or unnecessarily echo credentials.

<!-- auto-coding-skill:managed-agents:end -->
