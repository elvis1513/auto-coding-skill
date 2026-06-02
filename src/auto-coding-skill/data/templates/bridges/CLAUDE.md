Follow `docs/ENGINEERING.md` strictly. Source of truth: `docs/ENGINEERING.md`.
Prefer already available MCP servers, installed skills, plugins, and app connectors during design, research, verification, and documentation workflows.
Prefer multi-agent mode whenever the task can be split into independent parallel subtasks without weakening integration control.
Default to the lightweight local gate first, then use Jenkins build verification and real target-environment verification as the primary completion gate.
Local Docker Compose and full local regression are on-demand diagnostic tools, not the default gate for every small change.
