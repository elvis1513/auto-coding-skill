# auto-coding-skill

A delivery-first Codex engineering workflow:

`analysis → decomposition → necessary design → development → one final fast
changed-scope gate → commit/push`.

The Skill is a selectable guardrail, not a command sequence that must run for
every task. The model skips machinery whose expected benefit does not exceed its
cost; read-only work and obvious small clean-checkout changes normally stay direct.

Version 4.3.5 keeps retry artifact reads mutation-free and can repair the exact
untouched or procedurally blocked 4.3.4 retry once without rewriting evidence.
Version 4.3.4 adds one fail-closed, immutable-evidence retry for tasks whose
4.2.8-4.3.2 Reviewer was consumed solely by the fixed Git-local artifact access
defect. Version 4.3.3 resolves the first multi-project feedback batch: read-only
Reviewer artifact access is mutation-free, substantive nonzero-exit results are
preserved, lifecycle identities fail early, managed protocol classification and
database migration signals are precise, and empty feedback status reports the
installed version. Version 4.3.2 keeps upgrade history outside active `docs/`, so an upgrade that
archives the previous managed AGENTS or ENGINEERING contract is immediately
idempotent and `status` remains current. Version 4.3.1 preserves recursively nested project documentation assets of any
file type, and gives project-owned Skill feedback a release-aware lifecycle with
active/closed grouping, recheck and verification notices, and explicit routing
of project preferences into the project overlay. Version 4.3.0 separates exact managed defaults from a byte-stable project
configuration overlay, migrates legacy specialization with semantic proof, and
adds project-owned shared-Skill feedback inboxes with bounded read-only
multi-project triage. Upgrades now use recoverable, owner-bound transactions.
Version 4.2.8 makes the supervised Reviewer observable and recoverable without
weakening review semantics: it streams private event metadata, distinguishes
startup failure from analysis timeout, retries one no-event startup, and supports
an audited fingerprint-bound user override that is never reported as approval.
Version 4.2.7 freezes every pre-commit Reviewer diff as a private, SHA-256-bound
Git-local patch, including staged, unstaged, untracked, deleted, mode, symlink,
and binary changes. Version 4.2.6 makes the managed structure/optimization description defer to
preserved project frontmatter instead of restating template defaults. Version
4.2.5 keeps JSX self-closing and closing-tag slashes out of regex state.
Version 4.2.4 fixes TypeScript function-body detection after an explicit return
type. Version 4.2.3 restores an explicit opt-in strict size-warning policy without
changing the default, makes semicolon-terminated Java/Kotlin imports visible to
project layer rules, and hardens function-range detection. Version 4.2.2 preserves
project-owned risk and structure policy during upgrades, restores explicit full
and final changed-scope structure enforcement, makes Reviewer assignments
deadline-bound and directly executable, fixes task merge status semantics, and
updates Jenkins/target diagnostics for the current
`access.*` schema while retaining legacy fallback. Version 4.2.1 makes
dirty/concurrent classification fail closed, bounds focused
review latency, provides a complete Reviewer result template, preserves the
caller's runtime environment for routed commands, keeps non-authoritative Agent
history out of structure findings, and distinguishes UI paths and mechanical
renames from semantic changes. Version 4.2.0 makes registered closure resilient
to normal Git staging, reuses an exact successful final gate, and lets an active
task expand scope safely before its first commit.
Version 4.1.9 makes `autocoding init` verify the bounded managed installation after every install or upgrade:
it replaces every managed constraint, migrates only schema-approved project
configuration, and converges `docs/` to one canonical directory framework. Version 4.1.7 made
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
docs/project/auto-coding-skill.yaml
docs/tools/autopipeline/ap.py
AGENTS.md (fully managed canonical repository contract)
```

`autocoding init` also installs the exact shared documentation tree under
`docs/{architecture,bugs,deployment,design,interfaces,project,reviews,skill-feedback,testing}`.
Managed templates are replaced; project-owned files under the designated
architecture, bugs, deployment, design, interfaces, project, reviews, and testing
roots are preserved recursively and byte-for-byte regardless of extension, as
are `docs/skill-feedback/reports/*.md`;
unrelated
directories are archived under `.agents/archive/`. Re-running init is the complete upgrade operation;
`sync` is the explicit multi-project equivalent. Project-local
`ap.py upgrade --dry-run` remains a read-only legacy diagnostic; its old write
mode is retired so upgrades cannot bypass the transactional installer.
Multi-project sync completes all read-only preflights before its first write;
after that boundary, each project has its own recoverable transaction, so a
later host I/O failure does not roll back projects that already completed.

`docs/ENGINEERING.md` is the exact managed default layer. Project-specific
access, commands, validation routes, risk rules, structure policy, and other
supported values belong in `docs/project/auto-coding-skill.yaml`. Runtime commands
recursively overlay project mappings on managed defaults; project scalar and list
values replace defaults, while code-enforced safety invariants remain mandatory.
Ordinary init, sync, and upgrade operations never rewrite an existing overlay.
The first compatible upgrade extracts the semantic difference from the previous
managed default, verifies equivalence, and creates the overlay before replacing
managed files.

## Shared Skill feedback

Every initialized project receives:

```text
docs/skill-feedback/
├── README.md
├── _TEMPLATE-SKILL-FEEDBACK.md
└── reports/                         # created when the first report is added
    └── YYYY-MM-DD-<slug>-<8-hex>.md
```

The README and template are managed; reports are project-owned and upgrades
preserve them byte-for-byte. Releases carry a signature-keyed resolution catalog;
the read-only collector derives upgrade, recheck, verification, closure, and
project-overlay routing actions without rewriting reports. Closed reports are
excluded from active cross-project grouping. A report is a candidate observation only. Create one
after distinguishing managed Skill behavior from project `risk.rules`, validation
routes, access values, structure policy, business code, and environment failures.
Do not automatically turn test failures or Reviewer findings into reports, and do
not include credentials, customer/device data, complete patches, Reviewer
artifacts, raw logs, or absolute user paths.

Periodic triage is explicit and read-only:

```bash
autocoding feedback --projects /path/geestock,/path/geesight,/path/xjmate --json
```

The collector scans only bounded report metadata from the listed projects,
executes nothing from the documents, changes no repository, and groups exact
root-cause signatures. Human triage still decides whether an observation is a
shared defect, project configuration, environment issue, duplicate, or missing
evidence before fixes and a release are planned.

After a project upgrade, verify each requested action. Fixed reports should be
deleted or updated to `resolved`; current regressions should update their last
verified version; project-only preferences belong in
`docs/project/auto-coding-skill.yaml` and should be removed from active feedback.

Fill the project/Jenkins/GitLab/Nexus URL, username, and password overrides under
`access.*` in `docs/project/auto-coding-skill.yaml`, then configure one real fast
validation command and run:

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
- `repo`, `workspace_dirty`, `dirty_paths`, and `active_writer`: the repository
  and concurrency evidence used for the execution decision.
- `review_required` and `design_required`: risk-based escalation decisions.
- `change_nature`: `mechanical`, `semantic`, or conservative `unknown`; a
  mechanical rename may skip a generic durable-design requirement but never a
  project rule or required high-risk review.
- `task_kind`: `read_only`, `change`, `terminal_maintenance`, or internal `none`.
- `mechanism_plan.required`: the complete minimum mechanism set for the task.
- `mechanism_plan.optional_when_beneficial`: model-selectable mechanisms whose
  expected benefit must exceed coordination cost.
- `mechanism_plan.forbidden`: mechanisms that stay off unless the user overrides.
- `optional_agents`: model-selectable explorer/docs/browser candidates; they are
  never automatic stages.
- an adaptive agent plan that does not force fan-out for ordinary work.

Classification reads the working tree with one fail-closed `git status
--porcelain=v2 -z --untracked-files=all --no-renames` snapshot. A Git error or
malformed result blocks classification instead of being treated as clean. Both
`direct` and dirty/isolated decisions are point-in-time verdicts: reclassify if
the checkout or writer state changes before the first write. Any other active
direct claim is a writer, including another claim with the same owner identity.

Clean serial work proceeds directly on the current branch with normal Git; it does
not create machine lifecycle state. Use `task-start` only when classification
requires isolation/review or the user explicitly requests lifecycle tracking:

If a registered task discovers another path before its first commit, expand it
with `task-scope-add` instead of finishing and restarting. Expansion is explicit,
lease/conflict checked, risk-monotonic, and invalidates old review/gate state.
Unregistered direct work should reclassify before writing outside its clean claim.

```bash
python3 docs/tools/autopipeline/ap.py task-start T0001 \
  --owned-path backend/internal/orders --force-lifecycle
python3 docs/tools/autopipeline/ap.py task-scope-add T0001 \
  --owned-path config/orders
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
python3 docs/tools/autopipeline/ap.py review-run T0002 \
  --reviewer "$REVIEWER_ID" --json
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

Route commands run in a non-login Bash that inherits the invoking process PATH
and selected runtime. Projects that intentionally require profile activation
declare it inside the configured command.

Check coverage without running project commands:

```bash
python3 docs/tools/autopipeline/ap.py validation-map-check --path contracts/api.yaml
python3 docs/tools/autopipeline/ap.py validation-map-check --tracked
```

Focused tests may be run and rerun during implementation. Only the final routed
closure gate is limited to one stable-diff run. Full regression, Docker, builds,
Jenkins, deployment, API verification, and target checks remain explicit
diagnostics outside normal closure.

Registered tasks call `commit-push` directly because it performs or strictly
reuses that final gate. Run `light-gate` manually only for unregistered normal Git
closure or when explicitly requesting a fresh diagnostic pass. When project
`structure.enabled` is true, the same final gate also runs the changed-scope
structure check; `structure.enforcement: blocking` makes new violations fail.
File/function size thresholds remain warnings by default. They are promoted to
blocking findings only when a project sets both `structure.enforcement: blocking`
and `structure.block_warnings: true`; the template default is `false`, so existing
project behavior does not change merely by upgrading.

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
- Focused review uses `high` effort and a 150-second hard wall over the supplied
  stable diff and evidence. Deep review uses `xhigh` and 360 seconds.
- Cross-module or parallel work and API, auth, database, payment, file-transfer,
  gateway, or production-configuration boundaries use deep review.
  Fixing Reviewer JSON formatting reuses the same analysis and never starts
  another substantive review.
- `review-assignment` writes the validated assignment under Git-local state with
  the exact fingerprint, HEAD, scope revision, owning fixer, review depth, and
  150/360-second deadline. Before that deadline begins, it freezes the exact
  task-owned working-tree state into a mode-0600 binary patch and binds its
  canonical path, format, and SHA-256 into the assignment. Reissuing the same
  live assignment is idempotent. Snapshot inputs and emitted patches above
  64 MiB fail closed and require a narrower scope or a project-specific
  large-artifact review path;
  expired or completed attempts cannot be silently renewed, and late results are
  rejected by `task-review`.
- `review-run` is the default executable path: it creates/reuses that assignment,
  starts a separate `codex exec` session in read-only mode, removes the parent
  lifecycle identity, consumes JSON events incrementally, and supervises the full
  process group against the original remaining deadline. If no semantic event
  arrives within 30 seconds it retries the same immutable assignment once. After
  analysis starts it never retries. Private schema-2 receipts record only bounded,
  allowlisted event/diagnostic categories, byte counts, and hashes. Plain `review-assignment` remains
  available only when another host can enforce the deadline itself; it does not
  stop an in-app subagent. A descendant that deliberately creates a new POSIX
  session is outside portable process-group termination, but cannot keep the
  non-blocking event readers or Reviewer deadline open.
- Exhausted `runtime-unavailable` or `analysis-timed-out` states remain blocked by
  default. `review-runtime-override` can record explicit user authorization bound
  to the exact fingerprint, assignment, artifact, and runtime receipt. Its verdict
  is `runtime-bypassed`, never `approved`; real blocked/changes-requested results
  cannot use this path.
- DD/ADR is created only for lasting cross-module, API, data, security,
  deployment, or key user-flow decisions.
- Historical debt does not block product work unless the current change worsens it.

Before returning a Reviewer result, use the absolute assignment path printed by
`review-assignment` to verify and read the frozen patch. Never reconstruct a
pre-commit review from `diff_base..diff_head` or a live `git diff`:

```bash
python3 docs/tools/autopipeline/ap.py review-artifact \
  --file <assignment.json>
```

Then generate the complete 16-field skeleton and fill its summary, evidence,
findings, and risks:

```bash
python3 docs/tools/autopipeline/ap.py agent-result-template \
  --file <assignment.json> --verdict <approved|changes-requested|blocked>
```

The generated object prevents field-by-field contract retries; contract checking
also reports all known field errors together. If only its JSON shape needs repair,
correct that object without rerunning review analysis.

The main agent owns architecture, final validation, Git closure, ordered
integration, push, and cleanup. Push ends the coding task; later CI/acceptance is
not polled automatically. An explicitly requested failure diagnosis may continue
in the same conversation/task without an artificial second ledger lifecycle.

## Upgrade projects

Finish every registered task using its currently installed runtime before changing
the Skill version. Then run `autocoding init` from each project root. It is safe to
rerun and needs no force flag.

The only migration exception is an active 4.2.8-4.3.2 task whose completed
Reviewer result contains no findings and is blocked solely by the fixed
`review-artifact` Git-local permission error. Run the managed 4.3.5 runtime from
outside the project install to authorize one audited retry, then immediately run
the original Reviewer identity:

```bash
python3 /absolute/managed/4.3.5/ap.py --repo /path/project \
  review-runtime-retry T0001 --diff-fingerprint <SHA256> \
  --reason-code managed-review-artifact-access \
  --confirm-managed-runtime-retry
python3 /absolute/managed/4.3.5/ap.py --repo /path/project \
  review-run T0001 --reviewer <ORIGINAL_REVIEWER> --json
```

The command preserves the original assignment, patch, result, receipt, and event
log byte-for-byte. It refuses substantive findings, changed scope or fingerprint,
tampered evidence, user overrides, duplicate retries, and unmanaged runtimes.
If 4.3.4 already authorized the same retry, 4.3.5 may supersede only an untouched
pending attempt or its exact non-substantive artifact-access block; both audit
chains and any prior runtime files remain immutable.

```bash
cd /path/a && autocoding init
cd /path/b && autocoding init
autocoding status --projects /path/a,/path/b
```

Init replaces the managed Skill, root `AGENTS.md`, managed agents, ENGINEERING
schema/body, runtime launcher, and documentation framework. It preserves explicit
model overrides, complete project `risk.rules`, supported project/access/
concurrency/route/structure values, and an existing project-owned structure
standard byte-for-byte. Removed content is archived outside active docs.

## What changed in 4.3.5

- Stopped read-only `review-artifact` from recomputing the live task snapshot;
  the writable supervisor remains responsible for the immediately pre-launch
  HEAD, scope, and fingerprint check.
- Added one fail-closed repair for `retry-v4.3.4` when it is still untouched or
  ended only in the known Git-local permission block. The repair publishes a new
  audit and tokenized evidence while retaining and revalidating the full 4.3.4
  audit chain.

## What changed in 4.3.4

- Added `review-runtime-retry`, a one-attempt migration for the exact
  4.2.8-4.3.2 read-only `review-artifact` permission defect. Eligibility is bound
  to the lifecycle owner, original Reviewer, task UUID, base/HEAD/scope,
  fingerprint, canonical non-substantive blocked result, and a strictly newer
  managed runtime.
- Kept the original assignment, frozen patch, result, runtime receipt, and event
  log immutable. The retry writes a mode-0600 create-only audit plus tokenized
  result/run/events files and carries its own fixed 150/360-second deadline.
- Made `review-run`, `review-artifact`, `task-review`, approval validation, and
  task status validate the retry audit and effective deadline. Artifact access
  receives the extension only through the supervised runtime environment and
  the exact absolute managed script that authorized it.

## What changed in 4.3.3

- Made existing Git-local Reviewer storage validation read-only: the writable
  supervisor establishes mode `0700`, while the Reviewer verifies ownership and
  mode without calling `chmod` from its read-only sandbox. Reviewer artifact and
  result-template commands now use the exact absolute runtime that launched
  `review-run`, allowing a fixed runtime to review a task created by an older
  project installation without changing that task's base or owned scope.
- Preserved contract-valid `blocked` and `changes-requested` results when the
  Reviewer process exits nonzero, while retaining the blocking runtime receipt.
- Rejected `task-start` owner/writer values that conflict with
  `CODEX_THREAD_ID` before creating task state or worktrees.
- Classified root `AGENTS.md` as managed release/tooling authority and prevented
  unqualified workflow/configuration migration wording or policy filenames from
  being mislabeled as database changes.
- Reported the installed Skill version in status even before a project creates
  its first feedback report.
- Added release-catalog resolutions for all nine reports collected from the
  seven-project 4.3.2 rollout, including canonical duplicate mappings.

## What changed in 4.3.2

- Moved managed AGENTS and duplicate-workflow ENGINEERING history into
  `.agents/archive/auto-coding-skill/<version>/` instead of `docs/archive/`.
- Added an upgrade regression proving legacy 4.3.1 active-doc archives are moved
  out of active docs without byte loss and post-upgrade `status` is immediately
  current.

## What changed in 4.3.1

- Replaced extension-bound documentation preservation with recursive ownership
  for designated project documentation roots. PNG, SVG, JSON, YAML, binary, and
  nested assets now remain byte-identical across status, dry-run, init, and sync;
  active documentation symlinks and special files fail before writes.
- Added the managed, signature-keyed feedback resolution catalog and compatible
  v1/v2 report parsing. Collection now separates active and closed reports and
  derives release-aware upgrade, recheck, verification, regression, closure, and
  project-overlay routing states without modifying project-owned reports.
- Surfaced feedback maintenance as non-blocking status, sync, init, and doctor
  advisories, while keeping explicit feedback collection strict, bounded,
  metadata-only, and read-only.

## What changed in 4.3.0

- Made `docs/ENGINEERING.md` the exact managed default layer and added
  `docs/project/auto-coding-skill.yaml` as the higher-priority project-owned
  overlay. Mappings merge recursively; explicit project scalars and lists replace
  defaults, while managed workflow identity and code-enforced safety invariants
  remain protected.
- Added one-time semantic migration from the previous manifest-bound default.
  Initialization creates the overlay without overwriting an existing one, proves
  the reconstructed effective configuration is equivalent, archives the legacy
  document, and then converges the managed default byte-for-byte.
- Added `docs/skill-feedback/` with managed guidance/template and preserved
  project-owned reports. `autocoding feedback --projects ... --json` performs an
  explicit bounded metadata-only read and groups exact root-cause signatures for
  later human triage.
- Replaced partial upgrade writes with owner-bound, recoverable installation
  transactions, staged/installed hash checks, active-installer rejection, safe
  project-file operations, and fail-closed effective-configuration validation.
  Project-local `ap.py upgrade --write` is retired in favor of transactional
  `autocoding init` or explicit multi-project `sync`.
- Batched protected executable-mode convergence so the safer installer retains
  practical upgrade latency while preserving symlink/reparse checks.

## What changed in 4.2.8

- Replaced end-only Reviewer output collection with bounded JSONL event streaming.
  Schema-2 Git-local receipts now record CLI/model/effort identity, attempt phases,
  first/last event times, event-log hashes, diagnostic categories, and byte counts
  without persisting prompt, patch, stderr, tool output, or model content.
- Split runtime startup failure from analysis timeout. A no-semantic-event startup
  is capped at 30 seconds and retried once with the same assignment, fingerprint,
  artifact, command, and absolute deadline; an analysis that started is never
  repeated. Focused review now uses `high/150s`, while deep uses `xhigh/360s`.
- Added `review-runtime-override` for explicit user-authorized delivery after an
  exhausted runtime-unavailable or analysis-timeout failure. The private override
  binds all immutable review evidence and records `runtime-bypassed`, never
  `approved`; failure-time hashes reject pre-authorization tampering, and a
  substantive Reviewer result observed before timeout remains non-bypassable.
- Restricted the hidden custom runner to explicit test harnesses and closed spawn
  failure, unbounded-output, silent-startup, and lost-diagnostics paths.

## What changed in 4.2.7

- Replaced live pre-commit diff discovery with an immutable Git-local patch
  artifact that captures staged, unstaged, untracked, deleted, mode, symlink,
  and binary changes in both direct and isolated task modes.
- Bound the artifact's canonical path, format, and SHA-256 into the Reviewer
  assignment, then bound the complete assignment SHA-256 into runtime state,
  receipt, verdict validation, and final commit authorization. The deadline
  starts only after snapshot creation.
- Added the full `review-artifact` command for verified Reviewer access and
  lifecycle cleanup for task artifacts after successful direct closure,
  isolated cleanup, or explicit orphan pruning. Cleanup now preserves registry
  and review evidence on failure so the same task can be retried safely.

## What changed in 4.2.6

- Made the managed `structure` / `optimization` description configuration-neutral:
  the preserved project frontmatter is authoritative for enforcement and debt
  completion policy.
- Added a 4.2.5-to-4.2.6 initialization regression that preserves strict
  `blocking + baseline-aware` project settings and proves repeated init remains
  byte-idempotent.

## What changed in 4.2.5

- Prevented standalone JSX `/>` and closing-tag `</...>` slashes from starting a
  JavaScript regex token during function-range scans. GeeStack now matches its
  TypeScript AST size baseline, and XJMate strict full structure passes cleanly.

## What changed in 4.2.4

- Fixed TypeScript/TSX named and arrow function ranges across generic constraints,
  predicates, conditional/object/function return types, and multiple same-line
  arrows. Exact arrow locations are evaluated with bounded longest-range selection,
  so type arrows neither truncate real bodies nor create duplicate findings.

## What changed in 4.2.3

- Added the explicit `structure.block_warnings` policy with a default of `false`.
  File/function size threshold findings become blocking only when the project also
  sets `structure.enforcement: blocking`; advisory and default configurations keep
  their existing warning-only behavior.
- Recognized semicolon-terminated Java and Kotlin imports during structure checks,
  so project-configured forbidden-import layer rules can enforce JVM boundaries.
- Hardened function-range detection for Go receivers, Python suites, brace bodies,
  and block/expression arrow functions. Scans are threshold-bounded, honor the
  final Gate deadline, and ignore braces in comments and string literals.

## What changed in 4.2.2

- Classified root and nested `package.json` files as `release_or_tooling` high-risk
  changes requiring review, and added upgrade regression coverage that preserves
  complete project `risk.rules` instead of deleting partially overlapping rules.
- Honored explicit `structure-check --scope full`, included tracked and unignored
  untracked files, and restored the enabled structure check inside the final
  changed-scope gate. Init now preserves supported strict structure settings and
  treats `docs/architecture/structure-standard.md` as scaffold-once project policy.
- Added `review-run` with a validated Git-local assignment, fixed 90/300-second
  process-group supervision, one attempt per fingerprint, Reviewer identity/HEAD/
  scope binding, safe result normalization, and late-result rejection. The child
  runs as a separate read-only Codex process without the lifecycle-owner identity;
  the documented template command uses the complete
  `python3 docs/tools/autopipeline/ap.py ...` invocation.
- Added `has_task_commits` and prevented a no-commit task from reporting
  `merged_into_target=true` merely because its baseline equals the target tip.
- Updated `verify-jenkins`, `verify-jenkins-build`, `verify-target`, and target
  health checks to prefer `access.jenkins.<component>` and
  `access.project.<component>`, fail before network activity on missing or
  ambiguous endpoints, isolate Jenkins crumbs by URL and username, and preserve
  legacy `jenkins.*` / `target_env.*` compatibility.

## What changed in 4.2.1

- Made classification take one fail-closed Git porcelain-v2 snapshot and expose
  `repo`, `workspace_dirty`, `dirty_paths`, and `active_writer` in normal output.
  Direct/dirty decisions are explicit snapshots, and another same-owner direct
  claim still counts as a concurrent writer.
- Kept the `reviewer` Agent at `xhigh` while adding one-pass, 90-second focused
  review and 300-second deep routing for cross-module, parallel, API, auth,
  database, payment, file-transfer, gateway, and production-configuration changes.
  Focused timeout is `blocked`, never an approval or a reason to call `task-review`.
- Added `agent-result-template` to generate all 16 Reviewer result fields from a
  validated assignment and made contract validation return all known field errors
  together. JSON-only repair reuses the completed analysis instead of launching
  another substantive review.
- Replaced the login Shell used for routed commands with an inherited-environment
  non-login Shell, preserving the caller's PATH and selected Python/Node runtime.
- Excluded `.agents/archive/**`, managed Agent definitions, and the install
  manifest from structure scans while continuing to scan project-owned `.agents` code.
- Replaced substring UI classification with exact directory segments and UI-only
  extensions, removing false browser signals from files such as `.env.components`.
- Added conservative mechanical/semantic/unknown change classification. Exact
  renames and explicitly behavior-stable syncs can avoid generic cross-module
  design ceremony; semantic/unknown changes and explicit project design rules
  remain protected, and high-risk review is unchanged.

## What changed in 4.2.0

- Made `commit-push` preserve already staged deletions and mixed index/worktree
  state, and made ownership/validation see both ends of a rename.
- Added an exact per-worktree final-gate PASS receipt. Registered `commit-push`
  reuses it only when content, index, base, scope, validation plan, command hashes,
  and writer lease still match; staging or push retries no longer rerun a stable gate.
- Added `task-scope-add` for conflict-checked, monotonic scope expansion before the
  first commit. Expansion raises risk when necessary and invalidates review/gate state.
- Clarified that registered tasks call `commit-push` directly; standalone
  `light-gate` is for unregistered Git closure or an explicit fresh diagnostic.

## What changed in 4.1.9

- Added a packaged managed-install manifest with path, version, content hash, and
  executable-bit expectations for release-owned files.
- Made `autocoding init` verify the written Skill, managed agents, root protocol,
  launcher, managed ENGINEERING region, and canonical templates before success.
- Made `doctor` recheck the local manifest and `status` compare it with the current
  release while excluding project facts, durable records, custom agents, and archives.

## What changed in 4.1.8

- Made `autocoding init` perform a complete project install or upgrade without a
  separate sync/upgrade chain or `--force`.
- Rebuilt ENGINEERING from the current schema, preserving only supported project
  values and removing unknown legacy fields and competing workflow text.
- Made the generated docs directory topology and managed templates identical
  across projects while preserving mutable project docs and valid durable records;
  obsolete paths are archived under `.agents/archive/` before removal.
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
