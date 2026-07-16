#!/usr/bin/env python3
"""Optional documentation templates materialized on demand."""

from __future__ import annotations


TEMPLATES: dict[str, dict[str, str]] = {
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
    "docs/architecture/structure-standard.md",
    "docs/architecture/adr/_TEMPLATE-ADR.md",
    "docs/deployment/deploy-records/_TEMPLATE-DEPLOY-RECORD.md",
    "docs/design/_TEMPLATE-DD.md",
    "docs/reviews/_TEMPLATE-REVIEW.md",
})


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
