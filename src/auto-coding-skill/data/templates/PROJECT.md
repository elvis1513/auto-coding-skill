# Project Configuration

This file is project-owned. Skill installation creates it only when missing;
upgrades never overwrite it. Keep the current working context here and link to
maintained topic documents for detail, rather than accumulating task history.

## Current working context

Record the facts needed before writing files or operating this project:

- Workspace constraints: approved directories, temporary output location, and
  any concurrent work or external systems that must not be touched.
- Integration: `dev` is the integration target; each changing task uses its own
  `codex/*` branch and independent worktree. Record any explicit project exception.
- Validation entry points: module working directories, focused checks, and the
  acceptance boundaries relevant to delivery.
- Environment boundaries: deployment targets and actions requiring additional
  authority. An endpoint or stored credential is not authorization to use it.

Replace this guidance with verified project facts; omit inapplicable fields and
identify genuinely unknown facts without inventing values.

## Runtime and topic index

Keep current service endpoints and operating entry points here. Link to the
existing product, architecture, interface, design, and deployment documents only
when they help locate durable knowledge. Historical release and acceptance
evidence belongs in the relevant topic document, not in the current-context block.

## Access records

Project-approved credentials may be maintained here or at the project's approved
private location. Keep each record associated with its system and purpose.
Read only the required record; never print this whole file when it contains
credentials, and never echo secrets in chat, command arguments, or logs.
