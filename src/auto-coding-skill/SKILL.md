---
name: auto-coding-skill
description: Generic .agents engineering workflow with adaptive micro, standard, and high-risk execution profiles; minimal project scaffold; dev and verified closure modes.
---

# Auto Coding Skill

Use this skill for a disciplined task → design → implementation → verification
→ closure workflow. The project keeps one manual configuration source:
`docs/ENGINEERING.md`.

At task start, inventory installed skills, MCP servers, connectors, browser
tools, and repository scripts. Prefer the most direct authoritative capability.
Use subagents only when work is independent and the runtime supports them.

## Install and upgrade

```bash
autocoding init
autocoding sync --projects .
pip install pyyaml requests
```

New projects receive a minimal scaffold: the project-local skill, managed role
templates, `docs/ENGINEERING.md`, taskbook, closure log, and a small compatibility
launcher. Optional design, API, review, testing, deployment, and bug documents
are created only with `ap.py scaffold <group> --write`.

For existing projects:

```bash
autocoding sync --projects .
python3 docs/tools/autopipeline/ap.py upgrade --dry-run
python3 docs/tools/autopipeline/ap.py upgrade --write
```

Upgrade preserves project documents, custom agents, and explicit local model
overrides. Managed agents without a `model` inherit the current client model.

## Configuration and profiles

Read `docs/ENGINEERING.md` before choosing a path. `workflow.profile: auto`
resolves to exactly one execution profile:

- `micro`: docs/tests-only or isolated low-risk work; changed gate; dev closure.
- `standard`: ordinary feature or defect work; standard gate; dev closure.
- `high-risk`: DB, auth, payment, deployment/build configuration, declared full
  rules, or explicit verify work; real full gate; verify closure.

High-risk signals cannot be manually downgraded. A full gate must use
`commands.gate_full` or `commands.full_gate`; light/standard fallbacks do not
count. An explicit non-auto configured profile replaces auto's low/normal
baseline but cannot suppress high-risk signals. CI/Jenkins and target
verification remain controlled by `verification.*_required`.

Run:

```bash
python3 docs/tools/autopipeline/ap.py doctor
python3 docs/tools/autopipeline/ap.py classify --scope auto
python3 docs/tools/autopipeline/ap.py light-gate --scope auto --explain
```

## Development closure

1. Locate the real entry point, call chain, existing owner module, tests, and
   reusable helpers.
2. Update the active task with the smallest useful design note.
3. Create DD/ADR only for cross-module, API, DB, deployment/CI, security, key UI
   flow, or lasting structural decisions.
4. Implement only necessary changes.
5. Run the resolved gate.
6. Record `DEV-CLOSED`, commit, push, and stop.

## Verified closure

High-risk or explicitly verified work uses the strongest path:

1. Run the real full local gate.
2. Commit and push.
3. Verify enabled CI/Jenkins and target-environment surfaces.
4. Record `PASS`, `FAIL`, or `PARTIAL` only from executed evidence.

## Structure policy

Follow repository-native architecture first. Generic file-size, function-size,
and regex import rules are advisory unless the project explicitly sets
`structure.enforcement: blocking`. Search for reusable utilities, components,
clients, validation, permissions, caching, retry, and automation before adding
new helpers. Do not split files only to reduce line count.

For repository-wide structural reviews, generate and read the health baseline
and optimization backlog. Accepted debt is not a fresh blocker unless it worsens.

```bash
python3 docs/tools/autopipeline/ap.py baseline init --write --update-config
```

## Collaboration roles

Role templates provide behavior and permission boundaries, while the active
client supplies the available model unless a project keeps an explicit override.
`classify` recommends only roles justified by the effective profile:

- `explorer`: read-only repository discovery and root-cause tracing.
- `docs_researcher`: current official API/version research.
- `browser_debugger`: UI reproduction and browser evidence.
- `fixer`: bounded implementation after scope is clear.
- `reviewer`: correctness, security, regression, and evidence review.

The main agent owns framing, architecture decisions, integration, verification,
closure records, and Git state.

## Tool routing

- Local code, tests, gates, and Git: shell, repository scripts, and `ap.py`.
- Current library/API behavior: official documentation MCP or matching skill.
- UI: in-app browser for local pages, Chrome for existing logged-in state,
  Playwright for deterministic automation, Computer Use for unsupported native UI.
- PR/issue/CI state: GitHub connector; local Git for local changes and pushes.
- Design, security, analytics, and document artifacts: use the matching installed
  skill or connector before manual recreation.
- Secrets: use configured environment references or secure platform flows; do
  not invent values.

## Optional documents and operations

```bash
python3 docs/tools/autopipeline/ap.py scaffold all --write
python3 docs/tools/autopipeline/ap.py docs-ledger-check
python3 docs/tools/autopipeline/ap.py docs-ledger-archive --plan
python3 docs/tools/autopipeline/ap.py gate-profile
python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> --msg "<TASK_ID>: <summary>"
```

`status` and `sync` manage only the minimal required scaffold. Existing optional
documents and legacy tool copies are preserved but do not count as drift.
