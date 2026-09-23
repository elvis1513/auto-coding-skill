# auto-coding-skill

`auto-coding-skill` 5.x provides lightweight general engineering guidance plus a
small documentation layout. It is not a workflow engine.

The guidance preserves task authorization, scales verification to risk, and
defines completion by the user's requested outcome. It leaves model choice,
reasoning effort, and execution strategy to the user and runtime; it ships no
fixed agent profiles or mandatory task protocol.

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
autocoding sync --projects /path/project-a,/path/project-b
autocoding status --projects . --json
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

```bash
npm run sync-assets
npm run release:check
```

Before changing shared instructions, try representative requests with the
intended models: a read-only diagnosis, a focused fix, an already-authorized
delivery, and a blocked external job. Compare scope adherence, verification,
completion evidence, and unnecessary questions or repeated work. These are
evaluation scenarios, not required steps for every consuming project task.
