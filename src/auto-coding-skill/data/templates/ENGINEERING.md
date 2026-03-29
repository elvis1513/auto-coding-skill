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

runtime:
  docker_compose_file: ""
  docker_service: ""
  container_name: ""
  image: ""
  app_port: ""
  health_base_url: ""
  health_path: ""
  env_file: ""
  startup_timeout_sec: 60

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

# docs/ENGINEERING.md — AutoPipeline Gates (Source of Truth)

目标：把一次任务固化为不可跳过的流水线：  
读任务 → 写DD → 实现 → 本地测试通过 → 静态分析+Review落盘 → 更新API Markdown+接口变更清单 →  
本地 Docker 启动验证 → 健康检查 → 按 API Markdown 对本地环境全量回归 + 回归矩阵 0 fail →  
记录 Bug 并新增自动化回归 → 任务总结落盘 → commit → push

规则：任一步骤失败或缺产物，禁止进入下一步；未 push 视为任务未完成，禁止开始下一个任务/子任务。

---

## 0. 配置填写（必须）

先填写 `docs/ENGINEERING.md` frontmatter 中的所有空值（例如 Docker 文件、服务名、容器名、健康检查地址、命令）。  
禁止在其他 md/yaml 重复维护这些配置。

---

## 1. 权威输入与冲突裁决（优先级）

1) docs/ENGINEERING.md（本文件）  
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

## 1.5 工具使用策略（Claude / Codex 专属）

优先使用当前环境已安装、已授权、已可访问的工具能力：

1) MCP servers  
2) 已安装 skills  
3) plugins / apps / connectors  
4) shell / 手工实现

规则：
- 做设计、查资料、看文档、看页面、查知识库、写回外部系统时，优先调用现有 MCP / skills / plugins / apps。
- 能用权威工具直接完成时，不重复手写中间数据。
- 工具不可用、无权限、结果不可靠时，才回退到本地命令或手工处理。
- 选择工具时优先“已安装且当前项目可直接使用”的能力，而不是重新造流程。

---

## 1.6 多 Agent 协作策略（Claude / Codex 专属）

整个流程尽可能使用多 agent 模式并行推进。

规则：
- 任务开始后，优先拆分为可并行的子任务：设计补充、资料检索、实现分块、测试验证、文档回写、review。
- 主 agent 负责关键路径：任务定义、方案裁决、代码集成、质量门禁、最终交付。
- 子 agent 负责边界清晰、可独立推进的工作，完成后回收结果给主 agent 集成。
- 如果某项工作会直接阻塞主路径且难以独立定义，不要机械拆分；由主 agent 保持控制。
- 能并行就不要串行；能拆独立 write scope 就不要让多个 agent 写同一块内容。

---

## 2. Gate 流水线（强制、不可跳过）

Gate-1 读任务：只从 taskbook 取范围与验收；缺信息先补 taskbook  
Gate-2 写DD：无DD禁止写代码；DD必须含 时序图/ER图/接口时序（Mermaid）  
Gate-3 实现：严格按DD；接口变更必须同步 API Markdown  
Gate-4 本地CI：必须通过（commands.build / commands.test）  
Gate-5 静态分析+Review：静态分析通过；docs/reviews/ 生成记录  
Gate-6 文档：更新 api.md + 追加 api-change-log.md  
Gate-7 本地运行：必须在本地 Docker 环境启动目标服务；失败先修复再继续  
Gate-8 健康检查：本地容器启动后必须健康检查通过  
Gate-9 全量回归：按 API Markdown 对本地环境全量回归；回归矩阵全量 PASS（0 fail）；发现问题必须写 bug-list 并新增自动化回归用例  
Gate-10 任务总结：必须生成 docs/tasks/summaries/<TASK_ID>.md  
Gate-11 完成：全门禁通过后必须 commit+push

---

## 3. Repo 工具入口

统一用 `python3 scripts/autopipeline/ap.py <command>` 执行。
