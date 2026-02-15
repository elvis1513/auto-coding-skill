# ENGINEERING.md — AutoPipeline Gates (Source of Truth)

目标：把一次任务固化为不可跳过的流水线：  
读任务 → 写DD → 实现 → 本地测试通过 → 静态分析+Review落盘 → 更新API Markdown+接口变更清单 →  
部署(systemd/jar) → 重启验证 → 按API Markdown全量回归 + 回归矩阵0fail →  
记录Bug并新增自动化回归 → 任务总结落盘 → commit → push

规则：任一步骤失败或缺产物，禁止进入下一步；**未 push 视为任务未完成**，禁止开始下一个任务/子任务。

---

## 0. 权威输入与冲突裁决（优先级）
## 0.1 工程命令配置（必须）

- 构建/测试/静态分析/回归命令必须由项目提供并配置在：
  - `autocoding.config.yaml`（推荐放 repo 根目录），或
  - `docs/autocoding/config.yaml`

任何 gate 只允许通过这些配置的命令执行（避免把流程绑死在某个脚手架）。


1) ENGINEERING.md（本文件）  
2) docs/tasks/taskbook.md  
3) docs/design/**  
4) docs/interfaces/api.md  
5) docs/interfaces/api-change-log.md  
6) docs/requirements/regression-matrix.md（必须 0 FAIL）  
7) docs/bugs/bug-list.md（长期积累，回归必测）  
8) docs/tasks/summaries/**（每任务一份，强制产物）  
9) docs/deployment/**  
10) 代码实现（不得反向覆盖 1~9）

---

## 1. Gate 流水线（强制、不可跳过）

Gate-1 读任务：只从 taskbook 取范围与验收；缺信息先补 taskbook  
Gate-2 写DD：无DD禁止写代码；DD必须含 时序图/ER图/接口时序（Mermaid）  
Gate-3 实现：严格按DD；接口变更必须同步 API Markdown  
Gate-4 本地CI：必须通过（ci-local）  
Gate-5 静态分析+Review：静态分析通过；docs/reviews/ 生成记录  
Gate-6 文档：更新 api.md + 追加 api-change-log.md  
Gate-7 部署：单机 systemd/jar；允许 root+密码；service目录固定 /usr/lib/systemd/system；只保留1份备份；失败自动回滚  
Gate-8 重启+健康：restart后必须健康检查通过  
Gate-9 全量回归：按 API Markdown 全量回归；回归矩阵全量 PASS（0 fail）；发现问题必须写 bug-list 并新增自动化回归用例（纳入 Gate-9）  
Gate-10 任务总结：必须生成 docs/tasks/summaries/<TASK_ID>.md（可用工具生成初稿）  
Gate-11 完成：全门禁通过后必须 commit+push（未push=未完成）

---

## 2. 部署约束（来自你的固定要求）

- 允许 sshpass / 或 python 读取 targets.yaml 的 root 密码（非交互）
- systemd 目录固定：/usr/lib/systemd/system
- 只保留一个最新备份（*.bak / *.tgz.bak），失败自动回滚并重启服务
- 健康检查端点不固定：targets.yaml 配置 base_url + health_path
- 部署可更新项：app/config/、app/bin/、/usr/lib/systemd/system/*.service、jar

---

## 3. Repo 工具入口（建议）

统一用 `python3 tools/autopipeline/ap.py <command>` 执行。
