Follow `docs/ENGINEERING.md` strictly. Source of truth: `docs/ENGINEERING.md`.
Route work through already available MCP servers, installed skills, plugins, and app connectors when they provide current docs, design context, browser evidence, GitHub/CI state, security review, or artifact rendering.
Use the `.agents/agents` role model when available: explorer, docs_researcher, browser_debugger, fixer, reviewer. If the client cannot run subagents, execute the same roles sequentially in the main agent.
Default to the lightweight local gate first, then use Jenkins build verification and real target-environment verification as the primary completion gate.
Local Docker Compose and full local regression are on-demand diagnostic tools, not the default gate for every small change.
