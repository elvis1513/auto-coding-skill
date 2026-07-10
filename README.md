# auto-coding-skill

A generic `.agents` engineering workflow with adaptive execution profiles,
minimal project scaffolding, evidence-backed closure, and optional CI/Jenkins and
target-environment verification.

## What changed in v2.2.0

- Added `micro`, `standard`, and `high-risk` execution profiles.
- `workflow.profile: auto` classifies changed work and cannot downgrade detected
  high-risk changes.
- High-risk and explicit verify work now require a real `gate_full`/`full_gate`;
  light and standard commands are no longer accepted as full-gate fallbacks.
- Generic structure checks are advisory by default. Projects can opt into
  blocking enforcement.
- Reduced a new project scaffold from 46 files / about 10,120 lines to 20 files /
  about 5,300 lines.
- Replaced duplicated repository-side Python tools with a small launcher that
  delegates to the single project-local skill runtime.
- Kept only ENGINEERING, taskbook, and closure log in the default documentation
  scaffold; all specialized documents are materialized on demand.
- Removed hard-coded model names from managed Agent templates. New installs
  inherit the active client model; existing project model overrides survive sync.
- Added behavioral regression tests for profile resolution, strict full gates,
  advisory structure checks, minimal scaffold budgets, on-demand docs, and Agent
  model inheritance.

## Install

```bash
npm install -g @elvis1513/auto-coding-skill
autocoding init
autocoding sync --projects .
pip install pyyaml requests
```

`autocoding init` installs the project-local skill and five managed roles under
`.agents`. `autocoding sync` installs the minimal project scaffold:

```text
.agents/skills/auto-coding-skill/
.agents/agents/
docs/ENGINEERING.md
docs/tasks/taskbook.md
docs/tasks/closure-log.md
docs/tools/autopipeline/ap.py
```

The `docs/tools` entry point is a compatibility launcher. Runtime code lives only
under `.agents/skills/auto-coding-skill/scripts`.

## Execution profiles

Configure the selector in `docs/ENGINEERING.md`:

```yaml
workflow:
  mode: dev
  profile: auto
```

| Effective profile | Intended work | Gate scope | Mode |
| --- | --- | --- | --- |
| `micro` | docs/tests-only or explicitly isolated work | changed | dev |
| `standard` | normal feature and defect work | standard | dev |
| `high-risk` | DB/auth/payment/file transfer/gateway/prod/deploy/build changes | full | verify |

`auto` is a selector, not a fourth effective profile. Full-path patterns,
high-risk categories, `gate.rules[].profile: high-risk`, and explicit verify work
raise the plan to `high-risk`. A CLI `--profile micro` or `--mode dev` cannot
lower it.

An explicit configured `micro`, `standard`, or `high-risk` profile replaces
auto's low/normal baseline and acts as a floor for CLI overrides. Independently
detected high-risk signals still force `high-risk`.

Inspect the plan:

```bash
python3 docs/tools/autopipeline/ap.py classify --scope auto
python3 docs/tools/autopipeline/ap.py impact --scope auto --json
```

Each result includes the effective profile, mode, gate scope, reasons, required
verification surfaces, and recommended Agent roles.

## Gate configuration

```yaml
commands:
  gate_changed: "npm run test:changed"
  gate_standard: "npm test"
  gate_full: "npm run test:full"

gate:
  default_scope: auto
  rules:
    - name: payments
      paths: ["src/payments/**"]
      profile: high-risk
```

For Node projects, a new scaffold can infer changed/standard commands from
`test`, `test:changed`, and `test:standard`. It only infers a full command from a
dedicated `test:full` script; ordinary `npm test` is never promoted to full.
A high-risk or verify run fails clearly when no real full command is configured.

## Structure policy

The generic checker remains useful for surfacing large files, large additions,
function-size signals, and import-direction heuristics, but it is not universally
authoritative:

```yaml
structure:
  enabled: true
  enforcement: advisory # advisory | blocking
  architecture_standard: project-defined
```

`advisory` reports findings without blocking. Projects with reliable, tailored
rules can opt into `blocking`. Repository-native architecture, compiler output,
tests, and real dependency graphs take precedence over generic path heuristics.

## Optional documentation

Specialized templates are created only when required:

```bash
python3 docs/tools/autopipeline/ap.py scaffold api --write
python3 docs/tools/autopipeline/ap.py scaffold design --write
python3 docs/tools/autopipeline/ap.py scaffold architecture --write
python3 docs/tools/autopipeline/ap.py scaffold review --write
python3 docs/tools/autopipeline/ap.py scaffold testing --write
python3 docs/tools/autopipeline/ap.py scaffold deployment --write
python3 docs/tools/autopipeline/ap.py scaffold bugs --write
python3 docs/tools/autopipeline/ap.py scaffold all --write
```

The command is idempotent and does not overwrite existing project documents
unless `--force` is supplied. `baseline init` and `gen-summary` generate their
outputs directly without static templates.

For a one-step legacy-style full scaffold:

```bash
python3 .agents/skills/auto-coding-skill/scripts/ap.py --repo . install --full
```

## Dynamic Agents and models

Managed role templates define role instructions, permissions, and reasoning
effort but do not pin a model. The current client therefore supplies a supported
model automatically.

Existing project-local `model = "..."` lines are treated as explicit overrides:

- `status` reports them but does not mark the project stale for model-only drift.
- `sync` updates managed instructions while preserving the override.
- `sync --reset-agent-models` removes managed-role overrides and returns to
  client inheritance.
- Custom Agent files are always preserved byte-for-byte.

The effective profile recommends roles dynamically:

- micro: main Agent only by default
- standard: explorer → fixer, plus browser/docs roles when indicated
- high-risk: explorer/docs as indicated → fixer → browser as indicated → reviewer

## Verification configuration

Generic projects start with both optional external surfaces disabled:

```yaml
verification:
  target_env_required: false
  jenkins_required: false
```

When target verification is enabled, `doctor` requires only the health URL/path
needed by the default health check. Frontend/backend URLs and credentials are
validated when the corresponding path or basic-auth options are actually used.
Jenkins keeps its explicit configuration checks. Unused sections should stay
absent rather than containing placeholders.

## Core commands

```bash
python3 docs/tools/autopipeline/ap.py doctor
python3 docs/tools/autopipeline/ap.py classify --scope auto
python3 docs/tools/autopipeline/ap.py light-gate --scope auto --explain
python3 docs/tools/autopipeline/ap.py structure-check --scope auto
python3 docs/tools/autopipeline/ap.py docs-ledger-check
python3 docs/tools/autopipeline/ap.py gate-profile
python3 docs/tools/autopipeline/ap.py commit-push T0001 --msg "T0001: summary"
```

## Upgrade and multi-project sync

```bash
autocoding sync --projects /path/a,/path/b

python3 docs/tools/autopipeline/ap.py upgrade --dry-run
python3 docs/tools/autopipeline/ap.py upgrade --write

autocoding status --projects /path/a,/path/b
autocoding sync --projects /path/a,/path/b --dry-run
```

For a v2.1 project, run the new CLI sync first; invoking its old project-local
`upgrade` command would still execute v2.1 logic. Upgrade and sync preserve
existing optional docs, legacy `core.py` /
`http_checks.py` tool copies, custom Agents, and project-specific configuration.
Retired template files do not count as drift.

## Development

```bash
npm run sync-assets
npm run check:assets
npm run test:src
npm test
npm run release:check
```

`release:check` synchronizes source assets, validates Python 3.11 grammar and
TOML, runs installer and profile regressions, and performs `npm pack --dry-run`.

License: MIT.
