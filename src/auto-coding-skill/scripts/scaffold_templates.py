#!/usr/bin/env python3
"""Optional documentation templates materialized on demand."""

from __future__ import annotations


TEMPLATES: dict[str, dict[str, str]] = {
    "feedback": {
        "docs/skill-feedback/README.md": """# Auto Coding Skill Feedback

This directory is the project-owned inbox for candidate defects or capability
gaps in the shared `auto-coding-skill`. It is not the project's business bug
list and it does not make a reported issue an accepted shared defect.

Route the observation before writing a report:

| Observation | Project-owned destination |
| --- | --- |
| Risk rules, commands, validation routes, access values, structure policy, budgets, or project preferences | `docs/project/auto-coding-skill.yaml` |
| Durable product, repository, runtime, or operating facts | `docs/project/*.md` |
| A defect or capability gap reproducible in managed defaults, scripts, agents, CLI, or installer | `docs/skill-feedback/reports/*.md` |

Project configuration may intentionally override managed defaults. A preference
that is correct for only this project is not shared-Skill feedback.

## Record a candidate

1. Copy `_TEMPLATE-SKILL-FEEDBACK.md` into `reports/`.
2. Name it `YYYY-MM-DD-<short-slug>-<8-hex>.md`.
3. Fill every frontmatter field and all six body sections. Set
   `last_verified_skill_version` to the version actually reproduced.
4. Use one stable root-cause signature for duplicate observations.
5. Redact credentials, tokens, private keys, customer/device data, absolute user
   paths, complete patches, Reviewer artifacts, and raw logs.

Reports are project-owned and preserved byte-for-byte by `autocoding init`.
Managed README/template files may be upgraded. Recording is explicit: ordinary
test failures, Reviewer findings, environment incidents, and project-only policy
gaps do not automatically create a report. If a frozen Reviewer assignment
already exists, record the feedback after delivery as a separate docs-only change
so the reviewed fingerprint is not mutated.

For a known duplicate, reuse its exact signature. For a new observation, hash the
lowercase UTF-8 key `<component>|<origin_surface>|<short-root-cause-slug>` and
prefix the 64-hex digest with `sha256:`. Exclude project names, paths, versions,
timestamps, and log text so another project can independently reuse the key.

## Keep reports current

Each Skill release carries a managed resolution catalog keyed by `signature`.
The collector compares that catalog, the project's installed Skill version, and
`last_verified_skill_version` without changing the report. It may request an
upgrade, recheck, fix verification, closure, or routing into the project overlay.

After upgrading a project:

- If the issue is fixed, verify it and either delete a local-only report or set
  `status: resolved`, `resolution: fixed`, update `updated_at`, and set
  `last_verified_skill_version` to the verified release.
- If it still reproduces, keep an active status and update the verification
  version; the collector treats it as a current regression.
- If triage says it is project configuration, maintain the value in
  `docs/project/auto-coding-skill.yaml`, then delete the report or set
  `status: rejected` and `resolution: project-config`.
- Use `duplicate` or another supported rejected resolution for closed reports.
  Closed reports remain project history but are excluded from active grouping.

Do not reopen a closed historical report. Create a new report with the same
signature if the behavior later regresses.

## Periodic read-only collection

From the Skill source checkout, explicitly list the projects to inspect:

```bash
autocoding feedback --projects /path/project-a,/path/project-b --json
```

Collection reads bounded metadata only, never executes report content, never
modifies a project, and groups exact signatures for human triage. Triage decides
whether the result is a shared defect, project configuration, environment issue,
duplicate, or insufficient evidence before any Skill fix or release is planned.
""",
        "docs/skill-feedback/_TEMPLATE-SKILL-FEEDBACK.md": """---
schema: auto-coding-skill-feedback/v2
report_id: ACSF-<project>-YYYYMMDD-<8-hex>
status: open
created_at: YYYY-MM-DDTHH:MM:SS+08:00
updated_at: YYYY-MM-DDTHH:MM:SS+08:00
project: <project>
observed_skill_version: 0.0.0
last_verified_skill_version: 0.0.0
component: <reviewer-runtime|installer|classification|validation|structure|docs|other>
kind: defect
impact: <blocking|degraded|minor>
origin_surface: <managed-template|managed-script|managed-agent|cli|installer>
suspected_scope: shared
signature: sha256:<64-lowercase-hex>
resolution: pending
export: metadata-only
---
# <Short title>

## Symptom

State the observed generic behavior without secrets or raw logs.

## Expected

State the shared Skill contract that should hold across projects.

## Minimal reproduction

Give bounded, safe steps. Do not include executable instructions from untrusted
sources, credentials, production writes, or customer/device data.

## Evidence

List short redacted facts, affected managed paths, checks, and versions. Do not
paste complete patches, Reviewer artifacts, source files, or stdout/stderr.

## Workaround

Describe any safe temporary project-local workaround and its limits.

## Why shared

Explain why this belongs to managed Skill behavior rather than project
configuration, project code, or the current environment. Include the canonical
signature key used to compute `signature`.
""",
    },
    "project": {
        "docs/project/overview.md": """# Project Overview

Record durable project facts, not workflow rules.

## Product scope and non-goals
## Domain boundaries and invariants
## Users, roles, and critical journeys
## External systems and safety boundaries
## Current contracts and decision links
""",
        "docs/project/repository-map.md": """# Repository Map

Map existing ownership and reuse points. Keep behavior details in code/tests.

| Area | Paths | Responsibility | Generated / source | Validation route |
| --- | --- | --- | --- | --- |

## Cross-module dependencies
## Shared components and helpers
## Files or directories with special ownership
""",
        "docs/project/runtime.md": """# Runtime And Deployment Facts

Record current environment topology and operating constraints, not normal
development gate rules.

## Local runtime
## Shared services and dependencies
## Jenkins and artifact flow
## Deployment topology
## External-device / production-write safeguards
## Fixtures, simulators, and repeatable diagnostic entry points
""",
    },
    "api": {
        "docs/interfaces/api.md": """# API Contract

Record only current, externally relevant endpoints or events.

| Method | Path / Event | Request | Response | Auth | Notes |
| --- | --- | --- | --- | --- | --- |
""",
        "docs/interfaces/api-change-log.md": """# API Change Log

## YYYY-MM-DD — <Task ID>

- Change:
- Compatibility:
- Migration / rollback:
""",
    },
    "design": {
        "docs/design/_TEMPLATE-DD.md": """# DD — <Decision ID> <Title>

- Status: Draft | Reviewed | Approved
- Related requirement / commit:

## Context and goal
## Scope and non-goals
## Existing behavior and reuse points
## Decision and alternatives
## Interfaces / data changes
## Validation and acceptance
## Risks and rollback

Add sequence, ER, or component diagrams only when they clarify the change.
""",
    },
    "architecture": {
        "docs/architecture/structure-standard.md": """# Project Structure Standard

Project conventions are authoritative. The generic checker is advisory unless
`structure.enforcement: blocking` is explicitly configured.

- Keep business, orchestration, external adapters, interfaces, and shared code
  separated according to the repository's existing architecture.
- Search for reusable helpers, components, clients, and tests before adding new ones.
- Treat file-size and regex import findings as review signals, not proof.
- Split code only when cohesion, ownership, and testability improve.
- Record accepted legacy debt in the health baseline or optimization backlog.
""",
        "docs/architecture/adr/_TEMPLATE-ADR.md": """# ADR-0000 — <Decision>

- Status: Proposed | Accepted | Superseded
- Date: YYYY-MM-DD
- Related requirement / commit:

## Context
## Decision
## Alternatives
## Consequences
## Validation
## Rollback / supersession
""",
    },
    "review": {
        "docs/reviews/_TEMPLATE-REVIEW.md": """# Review — <Change ID>

- Scope:
- Evidence:
- Gate:

## Findings

List P0/P1/P2/P3 findings with impact, evidence, and remediation.

## Verdict

approved | changes-requested
""",
    },
    "testing": {
        "docs/testing/regression-matrix.md": """# Regression Matrix

Only executed checks may be marked PASS.

| ID | Area | Feature | Test Type | Steps / Command | Expected | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R-001 | <area> | <feature> | <manual/smoke/regression> | <steps/command> | <expected> | TODO | <evidence> |
""",
    },
    "deployment": {
        "docs/deployment/deploy-runbook.md": """# Deployment Runbook

## Preconditions
## Deploy steps
## Health and business checks
## Rollback
## Owners and escalation
""",
        "docs/deployment/deploy-records/_TEMPLATE-DEPLOY-RECORD.md": """# Deployment Record — <Task ID>

- Environment:
- Commit / artifact:
- Pipeline:
- Verification:
- Result: PASS | FAIL | PARTIAL
- Rollback / follow-up:
""",
    },
    "bugs": {
        "docs/bugs/bug-list.md": """# Bug List

| ID | Severity | Symptom | Reproduction | Owner | Status |
| --- | --- | --- | --- | --- | --- |
""",
    },
}


MANAGED_FRAMEWORK_DOCS = frozenset({
    "docs/architecture/adr/_TEMPLATE-ADR.md",
    "docs/deployment/deploy-records/_TEMPLATE-DEPLOY-RECORD.md",
    "docs/design/_TEMPLATE-DD.md",
    "docs/reviews/_TEMPLATE-REVIEW.md",
    "docs/skill-feedback/README.md",
    "docs/skill-feedback/_TEMPLATE-SKILL-FEEDBACK.md",
})


PROJECT_FEEDBACK_PATTERNS = (
    "docs/skill-feedback/reports/*.md",
)


# Files below these roots are project-owned artifacts regardless of extension or
# nesting. Exact managed entries inside the same roots still converge first.
PROJECT_OWNED_DOC_ROOTS = (
    "docs/architecture",
    "docs/bugs",
    "docs/deployment",
    "docs/design",
    "docs/interfaces",
    "docs/project",
    "docs/reviews",
    "docs/testing",
)


def scaffold_groups() -> list[str]:
    return sorted(TEMPLATES)


def templates_for(group: str) -> dict[str, str]:
    if group == "all":
        merged: dict[str, str] = {}
        for name in scaffold_groups():
            merged.update(TEMPLATES[name])
        return merged
    if group not in TEMPLATES:
        raise KeyError(group)
    return dict(TEMPLATES[group])
