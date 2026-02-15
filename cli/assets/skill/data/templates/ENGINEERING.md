# ENGINEERING.md — AutoPipeline Gates (Source of Truth)

目标：把一次任务固化为不可跳过的流水线：  
读任务 → 写DD → 实现 → 本地测试通过 → 静态分析+Review落盘 → 更新API Markdown+接口变更清单 →  
部署(systemd/jar) → 重启验证 → 按API Markdown全量回归 + 回归矩阵0fail →  
记录Bug并新增自动化回归 → 任务总结落盘 → commit → push

规则：任一步骤失败或缺产物，禁止进入下一步；**未 push 视为任务未完成**，禁止开始下一个任务/子任务。

---

## 0. 权威输入与冲突裁决（优先级）
## 0.1 项目配置（必须，单一入口）

- 所有人工维护信息统一放在：`docs/project/project-config.md`
- 该文件 YAML frontmatter 中必须包含：
  - `commands.*`（build/test/lint/typecheck/smoke/regression）
  - `deployment.*`（ip/用户名/密码/服务名/路径/健康检查等）
  - `docs.*`（任务本、API文档、回归矩阵、Bug清单、总结目录等路径）

任何 gate 只允许使用该文件中的配置执行，禁止在其他 md/yaml 再维护一份配置。


1) ENGINEERING.md（本文件）  
2) docs/project/project-config.md  
3) docs/tasks/taskbook.md  
4) docs/design/**  
5) docs/interfaces/api.md  
6) docs/interfaces/api-change-log.md  
7) docs/testing/regression-matrix.md（必须 0 FAIL）  
8) docs/bugs/bug-list.md（长期积累，回归必测）  
9) docs/tasks/summaries/**（每任务一份，强制产物）  
10) docs/deployment/**  
11) 代码实现（不得反向覆盖 1~10）

---

## 1. Gate 流水线（强制、不可跳过）

Gate-1 读任务：只从 taskbook 取范围与验收；缺信息先补 taskbook  
Gate-1.5 配置确认：先补齐 `docs/project/project-config.md`；未补齐禁止进入实现  
Gate-2 写DD：无DD禁止写代码；DD必须含 时序图/ER图/接口时序（Mermaid）  
Gate-3 实现：严格按DD；接口变更必须同步 API Markdown  
Gate-4 本地CI：必须通过（ci-local）  
Gate-5 静态分析+Review：静态分析通过；docs/reviews/ 生成记录  
Gate-6 文档：更新 api.md + 追加 api-change-log.md  
Gate-7 部署：单机 systemd/jar；允许 root+密码；service目录固定 /usr/lib/systemd/system；只保留1份备份；失败自动回滚  
Gate-8 重启+健康：restart后必须健康检查通过  
Gate-9 全量回归：按 API Markdown 全量回归；回归矩阵（`docs/testing/regression-matrix.md`）全量 PASS（0 fail）；发现问题必须写 bug-list 并新增自动化回归用例（纳入 Gate-9）  
Gate-10 任务总结：必须生成 docs/tasks/summaries/<TASK_ID>.md（可用工具生成初稿）  
Gate-11 完成：全门禁通过后必须 commit+push（未push=未完成）

---

## 2. 部署约束（来自你的固定要求）

- 允许 sshpass / 或 python 从 `docs/project/project-config.md` 读取 root 密码（非交互）
- systemd 目录固定：/usr/lib/systemd/system
- 只保留一个最新备份（*.bak / *.tgz.bak），失败自动回滚并重启服务
- 健康检查端点不固定：`docs/project/project-config.md` 的 deployment.health_* 字段配置
- 部署可更新项：app/config/、app/bin/、/usr/lib/systemd/system/*.service、jar

---

## 3. Repo 工具入口（建议）

统一用 `python3 tools/autopipeline/ap.py <command>` 执行。
