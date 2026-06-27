# Taskbook（任务本：持续续写，默认权威任务来源）

规则：
1) 所有任务都写在本文件（持续续写，不另起零散任务文件）
2) 普通小改动只要求最小设计记录；跨模块、接口、数据库、部署、Jenkins、关键页面流程变更才补 DD
3) 每个任务最终必须有闭环证据：提交、Jenkins、目标环境验证、结果、遗留问题
4) 长 summary 不是默认强制产物；只有高风险或需要完整复盘时再补

---

## Task T0001 — <Title>
- 状态：Planned | Designing | Implementing | Local Checking | Pipeline Verifying | Target Verifying | Done | Blocked
- 范围（In scope）：
- 非目标（Out of scope）：
- 是否高风险（Yes/No）：
- 高风险分类（如有）：DB / Auth / Payment / Jenkins / Gateway / Upload / Prod Config
- 影响面（API / DB / Jenkins / Page / Config / Deploy）：
- 分类结果（`ap.py classify --scope auto`：risk / gate / needs）：
- 结构落位（Domain / Application / Infrastructure / Interface / Shared / Tooling / N/A）：
- 复用检查（已有 helper / 组件 / 脚本 / 库）：
- 是否需要 ADR（Yes/No）：
- 最小设计记录：
- 验收标准：
- 子任务（如有）：
  - [ ] T0001-1 <subtask>

### 默认证据（完成后填写）
- 项目配置：`docs/ENGINEERING.md`
- 提交：<commit sha>
- Jenkins Build：<build url>
- 目标环境验证：<health/api/page/business path>
- 闭环记录：`docs/tasks/closure-log.md`

### 按需补充证据（仅在需要时填写）
- DD：`docs/design/T0001-<slug>.md`
- Review：`docs/reviews/T0001-YYYYMMDD-HHMM.md`
- API 文档：`docs/interfaces/api.md`
- API Change Log：`docs/interfaces/api-change-log.md`
- 回归矩阵：`docs/testing/regression-matrix.md`
- Bug 清单：`docs/bugs/bug-list.md`
- Task Summary：`docs/tasks/summaries/T0001.md`
- Deployment Record：`docs/deployment/deploy-records/T0001-YYYYMMDD.md`

---

继续在下方追加任务（不要删除历史记录）
