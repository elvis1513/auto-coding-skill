Follow `docs/ENGINEERING.md` strictly. Source of truth: `docs/ENGINEERING.md`.
At task start, use `ap.py classify --scope auto` when changed-file impact is not obvious.
Before code changes, read the configured structure standard and place new code in the correct layer; do not add new responsibilities to already-large files.
Obey `structure.layer_rules` import boundaries unless a DD/ADR explicitly records the exception.
Before optimization reviews, read the project health baseline and optimization backlog, and report only new, worsened, unrecorded P0/P1, or upgraded-priority items.
Route work through already available MCP servers, installed skills, plugins, and app connectors when they provide current docs, design context, browser evidence, GitHub/CI state, security review, or artifact rendering.
Use the `.agents/agents` role model when available. The main agent decomposes and fans out independent explorer/docs_researcher/browser_debugger work, fans evidence into one design, assigns each independent fixer exactly one registered branch/worktree with explicit non-overlapping paths, routes stable diffs through reviewer and back to the owning fixer, then alone runs the fast gate, commits, integrates in dependency order, pushes, and cleans. Never run two writers in one worktree; start dependent write work only after its prerequisite is integrated. If the client cannot run subagents, execute the same stages sequentially without weakening isolation.
Use exactly one fast changed-scope local gate before pushing. Keep advisory structure, docs-ledger, full regression, Docker, API, Jenkins, and target checks outside the default development gate.
Keep active docs ledgers small: `taskbook.md`, `closure-log.md`, and top-level `docs/design/T*.md` must be physically archived when over budget. Use `docs-ledger-archive --plan` before `--write`; `archive-index.md` is only navigation.
Keep `docs/tasks/evidence.jsonl` and closure Markdown aligned with actual executed checks.
Treat target-branch push as coding completion. Do not wait for, poll, diagnose, or fix Jenkins/build/deploy results unless the user starts a separate diagnostic task; the project owner performs acceptance.
Use the direct URL, username, and password values configured under `access.*` in `docs/ENGINEERING.md`; do not invent credentials.
