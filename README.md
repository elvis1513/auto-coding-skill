# auto-coding-skill

Portable, framework-agnostic engineering workflow skill for:

- Claude Code
- Codex CLI

It enforces an end-to-end gate:

Task -> DD -> Implement -> Build/Test -> Static Analysis -> Review -> API Docs (Markdown) -> Deploy -> Smoke -> Full Regression -> Bug Log -> Summary -> Commit -> Push

## Install (npm)

```bash
npm install -g auto-coding-skill
```

## Quick start (any repo)

From your target repo root:

```bash
# install skill files for Claude
autocoding init --ai claude

# install skill files for Codex
autocoding init --ai codex

# install both
autocoding init --ai all
```

Skill install locations:

- `.claude/skills/auto-coding-skill`
- `.codex/skills/auto-coding-skill`

Then initialize the project scaffold (run one path that exists):

```bash
python3 .claude/skills/auto-coding-skill/scripts/ap.py --repo . install
# or
python3 .codex/skills/auto-coding-skill/scripts/ap.py --repo . install
```

This creates:

- `ENGINEERING.md`
- `docs/**` (taskbook, DD/review templates, API docs, deployment/runbook, regression matrix, bug list)
- `tools/autopipeline/ap.py` + `tools/autopipeline/core.py`
- `.gitignore` rule: `docs/deployment/targets.yaml`

## Configure project commands

```bash
cp docs/autocoding/config.example.yaml autocoding.config.yaml
```

Edit at least:

- `commands.build`
- `commands.test`
- `commands.lint`
- `commands.typecheck`
- `commands.smoke`
- `commands.regression`

## Gate commands

```bash
python3 tools/autopipeline/ap.py run build
python3 tools/autopipeline/ap.py run test
python3 tools/autopipeline/ap.py verify-api-docs
python3 tools/autopipeline/ap.py check-matrix
python3 tools/autopipeline/ap.py gen-summary T0001-1
python3 tools/autopipeline/ap.py commit-push T0001-1 --msg "T0001-1: <summary>" --require-matrix
```

## CLI options

```bash
autocoding init --ai claude|codex|all [--mode project|global] [--dest <path>] [--force]
```

When `--ai all` and `--dest` are both used, output will be:

- `<dest>/claude`
- `<dest>/codex`

## Publish

```bash
npm publish
```

## License

MIT
