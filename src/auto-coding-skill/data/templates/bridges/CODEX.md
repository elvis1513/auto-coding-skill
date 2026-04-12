Follow docs/ENGINEERING.md strictly. Source of truth: docs/ENGINEERING.md.
Prefer already available MCP servers, installed skills, plugins, and app connectors during design, research, verification, and documentation workflows.
Prefer multi-agent mode whenever the task can be split into independent parallel subtasks without weakening integration control.
Do not keep substantial work on a single agent when it can be partitioned safely; keep one main agent for integration and gates, and use side agents for design, backend, frontend, validation, and documentation when those scopes are independent.
For Go monorepo + Jenkins projects, local Docker Compose validation must pass before commit, and push is expected to trigger Jenkins pipeline verification.
