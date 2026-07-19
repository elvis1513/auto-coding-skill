# auto-coding-skill

`auto-coding-skill` 5.x provides detailed general engineering guidance plus a
small, project-owned documentation layout. It is not a workflow engine.

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
docs/architecture/
docs/design/
docs/interfaces/
docs/deployment/
docs/product/
```

The environment file is intentionally project-owned and may contain project-
approved plaintext usernames and passwords for local development and diagnosis.
Do not invent, echo, or copy credentials beyond the project.

All documents are created only when missing and are never overwritten by later
`init` or `sync` runs. Documentation is optional: record durable facts only when
the user asks or when they will help future work. Do not create a document for
every task, review, test, or commit.

## Commands

```bash
autocoding init
autocoding sync --projects /path/project-a,/path/project-b
autocoding status --projects . --json
```

These commands only install, preserve, and report documentation. They never run
project tests, validation, Gates, reviews, builds, Jenkins jobs, deployment, or
other external-system operations.
