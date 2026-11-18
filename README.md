# auto-coding-skill

`auto-coding-skill` 5.x provides lightweight general engineering guidance plus a
small documentation layout. It is not a workflow engine.

The guidance preserves task authorization, scales verification to risk, and
defines completion by the user's requested outcome. It leaves model choice,
reasoning effort, and execution strategy to the user and runtime; it ships no
fixed agent profiles or Gate runtime. Repository changes use task-owned
`codex/*` branches and independent worktrees, with verified integration into
`dev`; read-only questions do not need a branch. Development stays parallel,
while integration resolves conflicts against current `dev` without force pushes.

## Install

```bash
npm install -g @elvis1513/auto-coding-skill
autocoding init
```

Initialization installs a managed general `AGENTS.md` and this lightweight
documentation layout:

```text
docs/ENVIRONMENT.md
docs/PROJECT.md
docs/architecture/
docs/design/
docs/interfaces/
docs/deployment/
docs/product/
```

`docs/ENVIRONMENT.md` is managed shared context and is refreshed on each
`init`/`sync`. It records common endpoints and ports without empty project
credential fields. `docs/PROJECT.md` is project-owned and never overwritten;
use it for project-specific configuration and project-approved credential
records.

The installed `.agents/skills/auto-coding-skill/` tree, `AGENTS.md`, and
`docs/ENVIRONMENT.md` are managed and refreshed by later `init` or `sync` runs.
Put custom guidance in project-owned documents, not managed files.
Project documents are created only when missing and are never
overwritten. Documentation is optional: record durable facts only when the user
asks or when they will help future work. Do not create a document for every task,
review, test, or commit.

## Commands

```bash
autocoding init
autocoding init --dry-run --json
autocoding sync --projects /path/project-a,/path/project-b
autocoding status --projects . --json
autocoding doctor --projects . --json
```

These commands only install, preserve, and report documentation. They never run
project tests, validation, Gates, reviews, builds, Jenkins jobs, deployment, or
other external-system operations.

`status` checks both install-time integrity (`integrity`) and alignment with the
running CLI's version and packaged assets (`current`). It also reports unexpected
installed skill files and recognizable legacy workflow files. `ok` is true only
when both checks pass and no leftovers need review; otherwise status exits with
code 1. This is a local comparison, not an npm registry update check or an
engineering gate. Project-owned document contents are not inspected for drift.

`doctor` separates managed integrity, project-owned context/legacy profiles,
the selected worktree, and clone-local Git guard health. A primary checkout is
normal for inspection, not a failed check. Profiles are reported by path and pin
presence, not loaded, removed or printed. No project script is executed.

For clones **already opted into** the optional Git guard, its single source and
hermetic tests are in `src/git-workflow/` in this package. In a task-owned
linked worktree use `autocoding guard-sync --dry-run` and then
`autocoding guard-sync` to refresh a recognized source/test pair under
`config/git-workflow/`. Unknown downstream changes are never overwritten.
After verification, `python3 config/git-workflow/guard.py install` explicitly
updates that clone's hooks and preserves its baseline, receipts and prior hook
chain. New clones do not inherit local activation. Neither init/sync nor doctor
installs a hook; no Jenkins, repository protection or publishing settings change.

`init`/`sync` preflight every requested project before refreshing any of them.
Modified or unowned files in the managed skill tree, `AGENTS.md`, or
`docs/ENVIRONMENT.md` block replacement; their contents are not printed.
`--dry-run --json` previews affected paths and conflicts without writing files.
Review the differences and migrate useful project facts into `PROJECT.md` or
topic documents first. If replacement is then intended, explicitly request it:

```bash
autocoding init --replace-managed --backup-dir /private/external/skill-backups
```

The backup directory must be outside all target projects, including through
symlinks. Each replacement creates a new private backup directory (0700), copies
the conflicting files with mode 0600, verifies their hashes, and records their
source paths. It does not overwrite an earlier backup. A dry-run does not create
backups. Review backups as potentially credential-bearing data; never commit them.
The override does not merge project instructions automatically or authorize
discarding them. Whole-batch preflight prevents known conflicts from producing a
partial upgrade; it is not a filesystem transaction for failures such as disk loss.

During upgrades, unchanged manifest-owned legacy files can be retired; the old
`docs/ENGINEERING.md` policy is archived first. Modified legacy files outside the
managed skill tree are preserved and reported across subsequent upgrades.
Unowned legacy candidates are reported, never automatically deleted. Review
their useful content before moving or removing them. Existing `docs/PROJECT.md`
is always preserved verbatim; a pre-managed environment document migrates intact
to `PROJECT.md` only when that project document is missing.

## Developing this skill

Edit `src/auto-coding-skill/`. The repository's discoverable skill at
`.agents/skills/auto-coding-skill` links directly to this source. Keep that symlink
intact; `autocoding init` and `sync` reject this source repository so they cannot
overwrite its own development instructions. Here, `status` reports source
discovery, packaged asset alignment, and legacy leftovers instead of expecting a
project install manifest.

Keep project constraints and validation entry points near the top of
`PROJECT.md`; read them before writing files or operating environments, including
when another skill suggests a default output path. Link to relevant existing
topic docs for historical detail. Shared managed files are not project overrides.

```bash
npm run sync-assets
npm run release:check
```

Before changing shared instructions, try representative requests with the
intended models: a read-only diagnosis, a focused fix, an already-authorized
delivery, and a blocked external job. Compare scope adherence, verification,
completion evidence, and unnecessary questions or repeated work. These are
evaluation scenarios, not required steps for every consuming project task.

Include regressions for artifact paths, managed-file ownership, preservation
during upgrades, concurrent worktrees with conflicting changes, and a completed
application delivery followed by an unrelated documentation build. The last case
must not add an unrequested CI wait or background monitor. For parallel work,
exercise a rejected stale push, conflict reconciliation, verification of both
changes, and non-force integration; do not merely test instruction wording.
