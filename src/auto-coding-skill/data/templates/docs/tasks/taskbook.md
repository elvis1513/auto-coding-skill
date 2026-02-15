# Taskbook（任务本：持续续写，权威任务来源）

规则：
1) 所有任务都写在本文件（持续续写，不另起任务文件）
2) 允许拆子任务：每个子任务也必须走全流程（DD→实现→测试→review→接口文档→部署→回归→总结→commit→push）
3) 每个任务必须有明确验收与证据（日志/报告/文件路径）

---

## Task T0001 — <Title>
- 状态：Planned | Designing | Implementing | Testing | Reviewing | Deploying | Done
- 范围（In scope）：
- 非目标（Out of scope）：
- 验收标准（必须可执行）：
- 依赖/约束：
- 子任务：
  - [ ] T0001-1 <subtask>
  - [ ] T0001-2 <subtask>

### 证据（完成后填写）
- 项目配置：`docs/project/project-config.md`
- DD：`docs/design/T0001-<slug>.md`
- Review：`docs/reviews/T0001-YYYYMMDD-HHMM.md`
- API 文档：`docs/interfaces/api.md`
- API Change Log：`docs/interfaces/api-change-log.md`
- 本地CI：粘贴摘要或给出文件路径
- 部署记录（如部署）：`docs/deployment/deploy-records/T0001-YYYYMMDD.md`
- 回归矩阵：`docs/testing/regression-matrix.md`（全量PASS）
- Bug清单（如有）：`docs/bugs/bug-list.md`
- 任务总结（强制）：`docs/tasks/summaries/T0001.md`

---

继续在下方追加任务（不要删除历史记录）
