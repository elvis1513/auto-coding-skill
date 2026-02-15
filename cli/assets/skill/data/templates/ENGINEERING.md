---
project:
  name: ""
  repo_root: "."

commands:
  build: ""
  test: ""
  lint: ""
  typecheck: ""
  format: ""
  smoke: ""
  regression: ""

deployment:
  host: ""
  ssh_port: 22
  username: ""
  password: ""
  service_name: ""
  systemd_dir: "/usr/lib/systemd/system"
  remote_app_root: ""
  remote_jar_path: ""
  remote_config_dir: ""
  remote_bin_dir: ""
  health_base_url: ""
  health_path: ""

docs:
  taskbook: "docs/tasks/taskbook.md"
  design_dir: "docs/design"
  review_dir: "docs/reviews"
  api_doc: "docs/interfaces/api.md"
  api_change_log: "docs/interfaces/api-change-log.md"
  regression_matrix: "docs/testing/regression-matrix.md"
  bug_list: "docs/bugs/bug-list.md"
  summary_dir: "docs/tasks/summaries"
---

# ENGINEERING.md — AutoPipeline Gates (Source of Truth)

目标：把一次任务固化为不可跳过的流水线：  
读任务 → 写DD → 实现 → 本地测试通过 → 静态分析+Review落盘 → 更新API Markdown+接口变更清单 →  
部署(systemd/jar) → 重启验证 → 按API Markdown全量回归 + 回归矩阵0fail →  
记录Bug并新增自动化回归 → 任务总结落盘 → commit → push

规则：任一步骤失败或缺产物，禁止进入下一步；未 push 视为任务未完成，禁止开始下一个任务/子任务。

---

## 0. 配置填写（必须）

先填写本文件 frontmatter 中的所有空值（例如 ip/用户名/密码/服务名/路径/命令）。  
禁止在其他 md/yaml 重复维护这些配置。

---

## 1. 权威输入与冲突裁决（优先级）

1) ENGINEERING.md（本文件）  
2) docs/tasks/taskbook.md  
3) docs/design/**  
4) docs/interfaces/api.md  
5) docs/interfaces/api-change-log.md  
6) docs/testing/regression-matrix.md（必须 0 FAIL）  
7) docs/bugs/bug-list.md（长期积累，回归必测）  
8) docs/tasks/summaries/**（每任务一份，强制产物）  
9) docs/deployment/**  
10) 代码实现（不得反向覆盖 1~9）

---

## 2. Gate 流水线（强制、不可跳过）

Gate-1 读任务：只从 taskbook 取范围与验收；缺信息先补 taskbook  
Gate-2 写DD：无DD禁止写代码；DD必须含 时序图/ER图/接口时序（Mermaid）  
Gate-3 实现：严格按DD；接口变更必须同步 API Markdown  
Gate-4 本地CI：必须通过（commands.build / commands.test）  
Gate-5 静态分析+Review：静态分析通过；docs/reviews/ 生成记录  
Gate-6 文档：更新 api.md + 追加 api-change-log.md  
Gate-7 部署：单机 systemd/jar；service目录固定 /usr/lib/systemd/system；失败自动回滚  
Gate-8 重启+健康：restart后必须健康检查通过  
Gate-9 全量回归：按 API Markdown 全量回归；回归矩阵全量 PASS（0 fail）；发现问题必须写 bug-list 并新增自动化回归用例  
Gate-10 任务总结：必须生成 docs/tasks/summaries/<TASK_ID>.md  
Gate-11 完成：全门禁通过后必须 commit+push

---

## 3. Repo 工具入口

统一用 `python3 scripts/autopipeline/ap.py <command>` 执行。
