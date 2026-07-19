# auto-coding-skill

`auto-coding-skill` 5.x provides detailed general engineering guidance plus a
small documentation layout. It is not a workflow engine.

It does not require a Gate, classification, task lifecycle, worktree, Reviewer,
test route, design record, Jenkins check, or deployment check.

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

Only `AGENTS.md` and `docs/ENVIRONMENT.md` are refreshed by later `init` or
`sync` runs. Project documents are created only when missing and are never
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
