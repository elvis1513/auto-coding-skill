---
name: auto-coding-skill
description: Use for a lightweight Jenkins-first engineering workflow in Claude/Codex. Initialize docs, fill docs/ENGINEERING.md once, then execute task->minimal-design->light-gate->push->jenkins->target-env->closure.
---

# Auto Coding Skill (Claude + Codex)

This skill is for Go backend + frontend monorepo projects that rely on Jenkins to build and deploy after push. It supports both Claude and Codex. The default workflow is lightweight locally, then uses Jenkins and the real target environment as the authoritative verification path.

`docs/ENGINEERING.md` is intentionally Git-tracked in this workflow. The remaining environment fields in that file are mandatory, must be filled with real values, and are committed as part of the project baseline. Unused environment keys should be removed from the template instead of being left as placeholders.

Prefer already available MCP servers, installed skills, plugins, and app connectors over ad-hoc manual work whenever they can complete the task reliably.

Default to multi-agent execution when the client supports it. Break work into independent design, research, implementation, validation, and documentation subtasks so Claude/Codex can run them in parallel whenever that reduces cycle time without weakening control of the main task.

## Supported clients

- Claude Code
- Codex CLI

## Tooling policy

Use available platform capabilities first:

1) Prefer installed MCP servers for design context, documentation lookup, browser automation, issue/docs systems, and deployment/runtime inspection.
2) Prefer already installed local skills when the task matches them.
3) Prefer supported plugins/apps/connectors when they provide authoritative project context or can write back records.
4) Fall back to manual shell/code workflows only when the above are unavailable, insufficient, or slower than direct execution.

## Collaboration policy

Prefer multi-agent mode across the workflow:

1) Split independent subtasks early when they can run in parallel.
2) Keep the main agent on the critical path: task framing, design decisions, integration, Jenkins / target-env verification, and final closure.
3) Use side agents for bounded work such as research, code slices, documentation updates, targeted regression checks, or review passes.
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
- `runtime.*` (only for optional local diagnostics)
- `target_env.*`
- `jenkins.*`
- `docs.*`

Do not duplicate config in other md/yaml files.
Do not hide `docs/ENGINEERING.md` in `.gitignore`.

Minimum required config for the default flow:
- `project.name`
- `commands.build`
- `commands.quick_test` or `commands.test`
- `commands.lint` or `commands.typecheck`
- `target_env.name`
- `target_env.frontend_base_url`
- `target_env.frontend_username`
- `target_env.frontend_password`
- `target_env.backend_base_url`
- `target_env.backend_username`
- `target_env.backend_password`
- `target_env.health_base_url`
- `target_env.health_path`
- `jenkins.base_url`
- `jenkins.ui_username`
- `jenkins.ui_password`
- `jenkins.api_user`
- `jenkins.api_password`
- `jenkins.trigger_branch`
- `jenkins.image_repository`
- `jenkins.image_tag_strategy`
- `jenkins.deploy_env`
- `jenkins.job_url`

## Branch policy

- `dev` is the long-lived integration branch.
- Use a temporary task branch only when parallel work would otherwise collide on `dev`.
- Keep temporary branches task-scoped and merge/rebase back into `dev` after closure.

## Execution order

1) read `docs/ENGINEERING.md`
2) read / update `docs/tasks/taskbook.md`
3) write minimal design notes; create a DD only when the change is cross-module, API, DB, deployment, Jenkins, or key-page-flow related
4) implement only the necessary changes
5) run the default local lightweight gate
6) commit + push
7) verify Jenkins build / deployment result
8) verify the real target environment
9) append `docs/tasks/closure-log.md`
10) use summary / deployment record / regression matrix only when the task actually requires them

## Commands

Default commands:

```bash
python3 docs/tools/autopipeline/ap.py doctor
python3 docs/tools/autopipeline/ap.py light-gate
python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> --msg "<TASK_ID>: <summary>" --require-light-gate --require-jenkins
python3 docs/tools/autopipeline/ap.py verify-jenkins-build --git-ref HEAD
python3 docs/tools/autopipeline/ap.py wait-health --scope target
python3 docs/tools/autopipeline/ap.py verify-target --backend-path /health --frontend-path /
python3 docs/tools/autopipeline/ap.py record-closure <TASK_ID> --commit HEAD --jenkins <build-url> --result PASS --verification "health check" --verification "key api"
```

On-demand commands:

```bash
python3 docs/tools/autopipeline/ap.py runtime-up
python3 docs/tools/autopipeline/ap.py wait-health --scope runtime
python3 docs/tools/autopipeline/ap.py run smoke
python3 docs/tools/autopipeline/ap.py run regression
python3 docs/tools/autopipeline/ap.py runtime-down
python3 docs/tools/autopipeline/ap.py check-matrix
python3 docs/tools/autopipeline/ap.py gen-summary <TASK_ID>
```

## Quality policy

- Default local gate is lightweight only: build, unit/quick test, lint, typecheck, API docs, Jenkinsfile / script syntax, `git diff --check`.
- `doctor` should be used early to catch missing or invalid config before the first implementation loop.
- `light-gate` now fails if the required default commands are not configured.
- `doctor`, `light-gate`, and `commit-push` all fail when required environment fields are missing, placeholder-like, or syntactically invalid.
- Do not require local Docker Compose or full local regression for every small change.
- Jenkins and target environment verification are more valuable than repeated local simulation of deploy-only problems.
- `verify-target` should be used for real target-environment API/page checks when the task touches user-visible or deploy-sensitive behavior.
- `commit-push --record-closure` can close the loop in one command when Jenkins build URL and verification results are already known.
- `regression-matrix.md` can mark `PASS` only after real execution with evidence.
- High-risk changes must include target environment verification and usually a DD.
