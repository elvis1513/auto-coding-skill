# Task Summary — <TASK_ID> — <Title>

- Task ID：<TASK_ID>
- Date：YYYY-MM-DD
- Scope（本次范围）：
- Out of scope（明确未做）：

---

## 1. 目标与验收结论
- 目标：
- 验收结论：PASS / FAIL（FAIL 必须说明原因与后续计划）

## 2. 变更概览（代码/配置/部署）
- 关键改动点：
- 影响模块：
- 兼容性影响（是否破坏兼容、迁移方案）：

## 3. 接口变更（以 API Markdown 为准）
- 新增：
- 修改：
- 废弃：
- 变更记录位置：`docs/interfaces/api-change-log.md`（对应条目）

## 4. 数据变更（如有）
- 表/字段变更：
- 迁移方式：
- 回滚方式：

## 5. 质量门禁证据（必须可追溯）
- 项目配置：`docs/ENGINEERING.md`（frontmatter）
- 本地CI：`ci-local`
- 静态分析：`static`
- Review 文档：`docs/reviews/<TASK_ID>-<timestamp>.md`
- API 文档：`docs/interfaces/api.md`
- 回归矩阵：`docs/testing/regression-matrix.md`（全量 PASS，0 fail）

## 6. Bug 清单与回归用例
- 新增/确认的 Bug（写入 `docs/bugs/bug-list.md`）：
- 新增自动化回归用例（引用回归矩阵ID）：

## 7. 部署记录（如有部署）
- 部署记录：`docs/deployment/deploy-records/<TASK_ID>-YYYYMMDD.md`
- systemd/service/config/bin 变更（若有）：

## 8. 风险与回滚
- 风险：
- 回滚点（备份/回滚步骤）：

## 9. 后续行动（如有）
- TODO：
