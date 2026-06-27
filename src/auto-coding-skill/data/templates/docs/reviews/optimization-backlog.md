# Optimization Backlog

> 这里记录持续优化项。被记录为 `accepted-debt` 的项目不等于当前任务未完成；只有新增、恶化或升级优先级时才需要重新报告。

## Status Values

- `open`: 已确认，等待排期。
- `accepted-debt`: 当前接受的债务，按触发条件再处理。
- `in-progress`: 正在处理。
- `closed`: 已闭环，证据写在表格中。
- `superseded`: 被其他方案或任务替代。

## Backlog

| ID | Priority | Status | Scope | Item | Reason | Acceptance | Last reviewed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OPT-000 | P2 | open | `<path/module>` |  |  |  | YYYY-MM-DD |
| LEDGER-000 | P2 | open | `docs/tasks`, `docs/design` | Archive active ledgers when they exceed `docs.active_*` budgets | Keeps project context searchable and prevents giant task/closure/DD files | `ap.py docs-ledger-archive --plan` reviewed, `--write` applied when safe, then `ap.py docs-ledger-check` passes | YYYY-MM-DD |

## Review Rules

- P0/P1 不能长期停留在 backlog；应进入当前迭代或明确升级。
- P2 可以排队，但必须有范围、原因和验收标准。
- P3 只在低成本或同域修改时顺手处理，不影响“优化完成”结论。
- 新会话整体分析只允许新增、升级或关闭条目，不要重复制造同义优化项。
