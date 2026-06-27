# Project Health Baseline

> 用于固定“当前项目结构是否达标”的判断口径。整体分析、结构优化和新会话复盘必须先读本文件，再读 `docs/reviews/optimization-backlog.md`。

- Baseline date: YYYY-MM-DD
- Baseline commit: `<git-sha>`
- Owner: <name / team>
- Review scope: <repo / module / subsystem>
- Standard: `docs/architecture/structure-standard.md`

## 1. Current Accepted Structure

记录当前被接受的目录结构、主要模块边界、已知历史原因和不再重复争论的事实。

| Area | Current state | Accepted because | Review date |
| --- | --- | --- | --- |
| <module/path> |  |  |  |
| `docs/tasks/taskbook.md` | active ledger, <= configured line budget | History is archived under `docs/tasks/archives/**` | YYYY-MM-DD |
| `docs/tasks/closure-log.md` | active closure ledger, <= configured line budget | History is archived under `docs/tasks/archives/**` | YYYY-MM-DD |
| `docs/design/` | active DDs only, <= configured file budget | Historical DDs are archived under `docs/archive/design/**` | YYYY-MM-DD |

## 2. Closed Optimization Scope

记录已经闭环的优化项。新会话不能把这些项重复判定为“当前未完成”。

| ID | Closed date | Scope | Acceptance evidence |
| --- | --- | --- | --- |
| OPT-000 | YYYY-MM-DD |  |  |

## 3. Accepted Debt

这些是已知但暂不处理的问题。除非新增风险、影响扩大或优先级升级，否则只保留在 backlog，不作为当前任务失败原因。

| ID | Priority | Scope | Debt | Why accepted | Revisit trigger |
| --- | --- | --- | --- | --- | --- |
| DEBT-000 | P2 |  |  |  |  |

## 4. Priority Rules

- P0: blocks build, release, deploy, core user flow, data integrity, security, or compliance.
- P1: clear architectural violation, contract drift, missing test around high-risk change, or recently introduced maintainability risk.
- P2: planned debt such as large files, hot directories, module extraction, stronger tests, or tool consolidation.
- P3: optional naming, style, polish, or further abstraction.

## 5. Completion Standard

An optimization task is complete when all are true:

- The scoped P0/P1/P2 items listed for this task are closed.
- Local gate passed, including docs ledger and structure checks when enabled.
- No new unclassified P0/P1 was introduced.
- Remaining P2/P3 items are either in `docs/reviews/optimization-backlog.md` or accepted debt above.
- Review output says explicitly whether the project meets this baseline.

## 6. New Review Instructions

When asked to analyze structure or optimization:

- Read this baseline first.
- Read `docs/reviews/optimization-backlog.md` second.
- Report only:
  - new or worsened issues;
  - unrecorded P0/P1;
  - backlog items whose priority should now be upgraded;
  - baseline drift.
- Do not repeat accepted debt as fresh findings.
