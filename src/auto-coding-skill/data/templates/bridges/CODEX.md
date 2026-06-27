Follow `docs/ENGINEERING.md` strictly. Source of truth: `docs/ENGINEERING.md`.
Before code changes, read the configured structure standard and place new code in the correct layer; do not add new responsibilities to already-large files.
Before optimization reviews, read the project health baseline and optimization backlog, and report only new, worsened, unrecorded P0/P1, or upgraded-priority items.
Route work through already available MCP servers, installed skills, plugins, and app connectors when they provide current docs, design context, browser evidence, GitHub/CI state, security review, or artifact rendering.
Use the `.agents/agents` role model when available: explorer, docs_researcher, browser_debugger, fixer, reviewer. If the client cannot run subagents, execute the same roles sequentially in the main agent.
Default to the lightweight local gate first; when `structure.enabled` is true, the gate includes `structure-check`.
Use Jenkins build verification and real target-environment verification as the primary completion gate in verify mode.
Local Docker Compose and full local regression are on-demand diagnostic tools, not the default gate for every small change.
