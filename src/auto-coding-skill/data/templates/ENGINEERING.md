---
project:
  name: ""
  repo_root: "."
  stack: "go-fullstack-monorepo"
  backend_dir: ""
  frontend_dir: ""
  go_main: ""
  dockerfile: ""
  jenkinsfile: "Jenkinsfile"

commands:
  build: ""
  test: ""
  lint: ""
  typecheck: ""
  format: ""
  docker_build: ""
  compose_up: ""
  compose_down: ""
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
  startup_timeout_sec: 120

jenkins:
  base_url: ""
  crumb_url: ""
  job_name: ""
  job_url: ""
  trigger_branch: ""
  image_repository: ""
  image_tag_strategy: ""
  deploy_env: ""
  deploy_timeout_sec: 1800
  prod_health_base_url: ""
  prod_health_path: ""
  api_user: ""
  api_token: ""
  api_user_env: "JENKINS_USER"
  api_token_env: "JENKINS_TOKEN"

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
读任务 → 写DD → 实现 → 本地构建/测试通过 → 静态分析+Review落盘 → 更新 API Markdown+接口变更清单 →  
本地 Docker Compose 启动验证 → 本地健康检查 → 对本地环境全量回归 + 回归矩阵 0 fail →  
记录 Bug 并新增自动化回归 → 任务总结落盘 → commit → push 触发 Jenkins → Jenkins 构建镜像并更新目标环境 →  
生产健康检查通过

规则：任一步骤失败或缺产物，禁止进入下一步；本地 compose 验证未通过禁止 commit；Jenkins 未成功或生产健康检查未通过，任务不视为完成。

补充规则：
- 每次任务闭环后，必须清理临时文件、临时目录、日志、截图、回归中间产物、构建缓存等非必要产物；仅 `.local/` 下的本地运行数据允许保留。

---

## 0. 配置填写（必须）

先填写 `docs/ENGINEERING.md` frontmatter 中的所有空值（例如 Go/前端目录、Docker 文件、Compose 服务、Jenkins Job、健康检查地址、命令）。  
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
- 查看 Jenkins、知识库、设计稿、页面、缺陷系统时，优先使用现成的连接器或 MCP，而不是手工拼接上下文。

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
Gate-4 本地CI：后端必须通过 `commands.test`；前端至少通过 `commands.build`、`commands.lint`、`commands.typecheck`；前端自动化测试能力逐步补齐  
Gate-5 静态分析+Review：静态分析通过；docs/reviews/ 生成记录  
Gate-6 文档：更新 api.md + 追加 api-change-log.md  
Gate-7 本地运行：必须用项目 Compose 启动本地 Docker 环境；失败先修复再继续  
Gate-8 健康检查：本地容器启动后必须健康检查通过  
Gate-9 全量回归：按 API Markdown 对本地 Compose 环境全量回归；回归矩阵仅可在真实执行后标记 PASS，且必须附证据；发现问题必须写 bug-list 并新增自动化回归用例  
Gate-10 Jenkins 准备：Jenkinsfile、Job 配置、镜像仓库策略必须可用  
Gate-11 任务总结：必须生成 docs/tasks/summaries/<TASK_ID>.md  
Gate-12 提交触发：本地门禁全过且临时产物已清理后，才允许 commit+push  
Gate-13 流水线验证：push 后必须确认 Jenkins 自动构建、镜像发布、目标环境更新成功  
Gate-14 完成：生产健康检查通过并补齐部署记录后，任务才完成

---

## 3. Repo 工具入口

统一用 `python3 docs/tools/autopipeline/ap.py <command>` 执行。

补充：
- `commands.smoke` / `commands.regression` 可以封装 repo 脚本，但必须真正在本地运行目标系统。
- `docs/testing/regression-matrix.md` 中的 `PASS` 只在真实执行并填入证据后允许保留；占位符证据会被视为未完成。
