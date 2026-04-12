---
name: auto-coding-skill
description: Use for strict Go fullstack monorepo engineering workflow in Claude/Codex. Initialize docs, fill docs/ENGINEERING.md frontmatter once, then execute design->implement->local-docker-gates->jenkins-trigger->verify.
---

# Auto Coding Skill (Claude + Codex)

This branch specializes the skill for Go backend + frontend monorepo projects that build Docker images locally and use Jenkins pipelines to auto-deploy after push. It supports both Claude and Codex. During design, research, implementation, verification, and delivery, prefer already available MCP servers, installed skills, plugins, and app connectors over ad-hoc manual work whenever they can complete the task reliably.

Default to multi-agent execution when the client supports it. Break work into independent design, research, implementation, validation, and documentation subtasks so Claude/Codex can run them in parallel whenever that reduces cycle time without weakening control of the main task. Do not keep the whole task on one agent when the work can be partitioned safely.

## Supported clients

- Claude Code
- Codex CLI

## Tooling policy

Use available platform capabilities first:

1) Prefer installed MCP servers for design context, documentation lookup, browser automation, issue/docs systems, and deployment/runtime inspection.
2) Prefer already installed local skills when the task matches them.
3) Prefer supported plugins/apps/connectors when they provide authoritative project context or can write back records.
4) Fall back to manual shell/code workflows only when the above are unavailable, insufficient, or slower than direct execution.

Typical examples:
- Design/UI work: prefer Figma MCP and related design skills.
- Documentation/library lookup: prefer official docs and MCP-backed doc tools.
- Project management or knowledge base updates: prefer Linear/Notion connectors if available.
- Browser/runtime verification: prefer Playwright/browser tools if available.
- Pipeline and deployment verification: prefer Jenkins-capable connectors, browser automation, or project-integrated tools if available.

## Collaboration policy

Prefer multi-agent mode across the workflow:

1) Split independent subtasks early when they can run in parallel.
2) Keep the main agent on the critical path: task framing, design decisions, integration, and final quality gates.
3) Use side agents for bounded work such as research, code slices, documentation updates, regression checks, or review passes.
4) Do not delegate a blocking architectural decision without keeping one agent responsible for final integration and correctness.
5) A practical default split for Go fullstack work is: design/research, backend implementation, frontend implementation, validation/documentation.

## Entry

1) Install skill files into target repo:

```bash
autocoding init --ai codex
# or claude / all
```

2) Initialize docs/tooling:

```bash
python3 .codex/skills/auto-coding-skill/scripts/ap.py --repo . install
# or .claude path
```

3) Install runtime deps:

```bash
pip install pyyaml requests
```

## Single manual config source

Fill only:

- `docs/ENGINEERING.md` frontmatter

This contains all manual fields:
- `commands.*`
- `runtime.*`
- `jenkins.*`
- `docs.*`

Do not duplicate config in other md/yaml files.

## Branch policy

- `dev` remains the only long-lived integration branch.
- Default behavior stays `dev`-first when there is no parallel work conflict.
- If Claude or Codex is operating in a derived worktree, detached HEAD, or any parallel task context where another thread is already changing `dev`, prefer creating a temporary branch from the latest `dev` before editing.
- Name temporary branches after the task, preferably `codex/<task-id>-<slug>` such as `codex/t0005-domestic-payment-site`.
- Keep the temporary branch scoped to one task, complete design/implementation/verification there, then merge or rebase it back onto `dev` only after local gates pass.
- Do not treat temporary branches as release branches; the final integration target is still `dev`.
- In temporary-branch mode, work in small, closed-loop slices. Each slice should have a clear scope, synchronized docs, the relevant local validation, and a commit that can stand on its own.
- Rebase temporary branches frequently against the latest `dev` to keep merge surfaces small.

## CI trigger strategy

- Prefer a split Jenkins model when parallel worktrees are active:
- MR or branch validation job: build/test/lint/typecheck and optional non-deploy runtime checks on temporary branches or merge requests.
- `dev` integration/deploy job: trigger only from pushes that land on `dev`.
- Do not rely on merge-request acceptance events to drive production deployment when a `dev` push event already exists; that commonly creates duplicate builds around merge time.

## Execution order

1) choose branch mode (`dev` directly, or temporary branch if parallel worktree rules apply)
2) `docs/ENGINEERING.md`
3) `docs/tasks/taskbook.md`
4) `docs/design/**`
5) implementation
6) local build/test/lint gates
7) start and validate local Docker Compose runtime
8) update API docs + regression matrix + bug list + summary
9) verify Jenkins config / Jenkinsfile readiness
10) if temporary-branch mode is used, close one small slice at a time with reviewable commits and rebase regularly onto `dev`
11) merge/rebase temporary branch back to latest `dev` when temporary-branch mode was used
12) commit/push to trigger Jenkins
13) verify Jenkins pipeline + target environment health, preferably with `verify-jenkins-build --git-ref HEAD`; when a precise Jenkins build is already known, use `verify-jenkins-build --job-name <folder/job> --build-number <N>` or `--job-url <url> --build-number <N>` (strict deploy check by default; use `--allow-no-deploy` only for docs-only sync verification)

## Commands

```bash
python3 docs/tools/autopipeline/ap.py run build
python3 docs/tools/autopipeline/ap.py run test
python3 docs/tools/autopipeline/ap.py run lint
python3 docs/tools/autopipeline/ap.py run typecheck
python3 docs/tools/autopipeline/ap.py run docker_build
python3 docs/tools/autopipeline/ap.py runtime-up
python3 docs/tools/autopipeline/ap.py wait-health
python3 docs/tools/autopipeline/ap.py run smoke
python3 docs/tools/autopipeline/ap.py run regression
python3 docs/tools/autopipeline/ap.py runtime-down
python3 docs/tools/autopipeline/ap.py verify-jenkins
python3 docs/tools/autopipeline/ap.py verify-jenkins-build --git-ref HEAD
python3 docs/tools/autopipeline/ap.py verify-jenkins-build --job-name platform/deploy-dev --build-number 152
python3 docs/tools/autopipeline/ap.py verify-jenkins-build --job-url https://jenkins.example.com/job/platform/job/deploy-dev --build-number 152
python3 docs/tools/autopipeline/ap.py verify-jenkins-build --multibranch-root-job platform/backend-service --branch-name main --build-number 152
python3 docs/tools/autopipeline/ap.py verify-jenkins-build --multibranch-root-job platform/backend-service --git-ref HEAD
python3 docs/tools/autopipeline/ap.py wait-health --scope prod
python3 docs/tools/autopipeline/ap.py verify-api-docs
python3 docs/tools/autopipeline/ap.py check-matrix
python3 docs/tools/autopipeline/ap.py gen-summary T0001-1
python3 docs/tools/autopipeline/ap.py commit-push T0001-1 --msg "T0001-1: <summary>" --require-runtime-health --require-jenkins --require-matrix
```

## Quality gate expectations

- Gate-4: backend must pass `commands.test`; frontend must at least pass `commands.build`, `commands.lint`, and `commands.typecheck`. Frontend automated tests are added incrementally when the repo gains them.
- Gate-9: `docs/testing/regression-matrix.md` rows must start as `TODO` until they are actually executed.
- A matrix row can be marked `PASS` only after real execution, and `Evidence` must contain non-placeholder logs, screenshots, or report paths.
- `python3 docs/tools/autopipeline/ap.py check-matrix` should be treated as a hard gate; placeholder evidence is equivalent to incomplete regression.
- Before the final commit/push, clean temporary files, logs, screenshots, generated verification artifacts, cache directories, and similar by-products created during the task. The only persistent local runtime data that may remain is `.local/`.
