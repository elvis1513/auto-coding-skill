This repository is the source of `auto-coding-skill`. Do not apply the installed
project workflow to development of the skill itself; maintain it directly on the
current repository branch.

Edit `src/auto-coding-skill/` as the canonical skill source. The local discovery
entry at `.agents/skills/auto-coding-skill` is a symlink to that source, not a
second installation. General project guidance lives in
`src/auto-coding-skill/data/templates/bridges/AGENTS.md`.

After changing source assets, refresh the packaged copy and verify it:

```bash
npm run sync-assets
npm run release:check
```

Use `autocoding init` only in consuming projects. It manages their skill,
`AGENTS.md`, and `docs/ENVIRONMENT.md`; it preserves `docs/PROJECT.md` and topic
documents. This skill ships no agent profiles or Gate runtime. Do not add fixed
model names, reasoning levels, or mandatory task ceremonies to the shared skill.
