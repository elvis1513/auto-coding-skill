---
workflow:
  mode: "dev"

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
  light_gate: ""
  build: ""
  test: ""
  quick_test: ""
  lint: ""
  typecheck: ""
  format: ""

runtime:
  docker_compose_file: ""
  docker_service: ""
  health_base_url: ""
  health_path: ""
  env_file: ""
  startup_timeout_sec: 120

target_env:
  name: ""
  frontend_base_url: ""
  frontend_username: ""
  frontend_password: ""
  backend_base_url: ""
  backend_username: ""
  backend_password: ""
  backend_root_username: ""
  backend_root_password: ""
  health_base_url: ""
  health_path: ""

jenkins:
  base_url: ""
  ui_username: ""
  ui_password: ""
  job_url: ""
  trigger_branch: ""
  image_repository: ""
  image_tag_strategy: ""
  deploy_env: ""
  deploy_timeout_sec: 1800
  api_user: ""
  api_password: ""

docs:
  taskbook: "docs/tasks/taskbook.md"
  closure_log: "docs/tasks/closure-log.md"
  design_dir: "docs/design"
  review_dir: "docs/reviews"
  api_doc: "docs/interfaces/api.md"
  api_change_log: "docs/interfaces/api-change-log.md"
  regression_matrix: "docs/testing/regression-matrix.md"
  bug_list: "docs/bugs/bug-list.md"
  summary_dir: "docs/tasks/summaries"
---

# docs/ENGINEERING.md — Lightweight Default Workflow (Source of Truth)

目标：默认采用高效率开发闭环，并通过 `workflow.mode` 控制流程长度。

- `dev`：开发模式，最快闭环。轻量门禁通过后，提前写 `DEV-CLOSED` 闭环，commit + push 触发 Jenkins 后结束。
- `verify`：验证模式，完整闭环。轻量门禁、commit + push、Jenkins 构建验证、目标环境验证全部完成后，写 `PASS` 闭环。

默认原则：
- 默认不要求本地 Docker Compose 启动。
- 默认不要求本地 Docker build。
- 默认不要求本地完整 regression。
- 默认不要求每个小改动生成长 summary。
- 默认不要求 regression matrix 全 PASS。
- 默认不要求 deployment record。
- Jenkins 构建结果和目标环境真实验证，比本地模拟更重要。

补充规则：
- 每次任务闭环后，必须清理临时文件、临时目录、日志、截图、构建缓存等非必要产物；仅明确需要保留的本地诊断目录允许保留。
- 所有手工填写信息，只维护在本文件 frontmatter 中，其他文档不得重复配置。
- `docs/ENGINEERING.md` 必须提交到 Git 管理，不允许写入 `.gitignore`。
- 本 workflow 明确允许在 `docs/ENGINEERING.md` 中明文维护平台账号、密码，并随 Git 一起版本化。
- 未参与默认流程的环境项不要保留占位；模板中未保留的字段视为已清理，不再额外配置。

---

## 0. 配置填写（必须）

先填写 `docs/ENGINEERING.md` frontmatter 中的所有空值。重点包括：
- `workflow.mode`：`dev` 或 `verify`，默认推荐 `dev`
- `commands.light_gate`：推荐配置一个项目级快速门禁命令，作为默认本地校验入口
- `target_env.*`：目标环境前端 / 后端地址、用户名、密码，必须全部填写且真实可用
- `jenkins.*`：Jenkins UI/API 用户名、密码、Job、分支、镜像、部署环境，必须全部填写且真实可用

字段说明：
- `target_env.backend_username` / `target_env.backend_password`：目标环境后台账号
- `target_env.backend_root_username` / `target_env.backend_root_password`：目标环境后台服务器 root 账号
- `target_env.frontend_username` / `target_env.frontend_password`：目标环境前端登录账号
- `jenkins.ui_username` / `jenkins.ui_password`：Jenkins 页面登录账号
- `jenkins.api_user` / `jenkins.api_password`：Jenkins API 用户名 / 密码

默认必填：
- `workflow.mode`
- `project.name`
- `commands.light_gate` 或 `commands.quick_test` 或 `commands.test` 或 `commands.build`
- `target_env.name`
- `target_env.frontend_base_url`
- `target_env.frontend_username`
- `target_env.frontend_password`
- `target_env.backend_base_url`
- `target_env.backend_username`
- `target_env.backend_password`
- `target_env.backend_root_username`
- `target_env.backend_root_password`
- `target_env.health_base_url`
- `target_env.health_path`
- `jenkins.ui_username`
- `jenkins.ui_password`
- `jenkins.api_user`
- `jenkins.api_password`
- `jenkins.trigger_branch`
- `jenkins.image_repository`
- `jenkins.image_tag_strategy`
- `jenkins.deploy_env`
- `jenkins.job_url`

按需填写：
- `runtime.*`：仅在本地运行诊断时使用
- `commands.build` / `commands.test` / `commands.quick_test` / `commands.lint` / `commands.typecheck` / `commands.format`：按项目实际情况保留

---

## 1. 权威输入与冲突裁决（优先级）

1) `docs/ENGINEERING.md`
2) `docs/tasks/taskbook.md`
3) `docs/design/**`
4) `docs/interfaces/api.md`
5) `docs/interfaces/api-change-log.md`
6) `docs/testing/regression-matrix.md`
7) `docs/bugs/bug-list.md`
8) `docs/tasks/closure-log.md`
9) `docs/tasks/summaries/**`
10) `docs/deployment/**`
11) 代码实现

说明：
- `closure-log.md` 是每个任务默认必须留下的轻量闭环记录。
- `summaries/**` 只用于跨模块、高风险、阶段性里程碑、需要完整复盘的任务。
- `deployment/**` 只用于真实部署记录、手工发布或高风险发布场景。

---

## 1.5 工具使用策略（Claude / Codex 专属）

优先使用当前环境已安装、已授权、已可访问的工具能力：

1) MCP servers
2) 已安装 skills
3) plugins / apps / connectors
4) shell / 手工实现

规则：
- 做设计、查资料、查文档、查 Jenkins、查页面、写回外部系统时，优先调用现成能力。
- 工具不可用、权限不足、结果不可靠时，才回退到 shell 或手工流程。
- 不重复手写工具已经能直接读取或写回的权威数据。

---

## 1.6 多 Agent 协作策略（Claude / Codex 专属）

整个流程尽可能使用多 agent 并行推进。

规则：
- 主 agent 负责任务定义、方案裁决、代码集成、轻量门禁、Jenkins/目标环境闭环、最终交付。
- 子 agent 优先拆为：设计/调研、后端实现、前端实现、验证/文档。
- 任务边界不清或需要强一致裁决时，由主 agent 保持控制，不机械拆分。

---

## 2. 标准流程（默认）

### 2.1 开发模式：`workflow.mode: "dev"`

用于日常快速开发。默认闭环：

需求确认 → 最小设计记录 → 开发实现 → 本地轻量校验 → 写 `DEV-CLOSED` 闭环 → commit + push → 结束

规则：
- 只跑最轻量门禁。
- push 触发 Jenkins 后不等待、不轮询、不验证目标环境。
- `closure-log.md` 必须提前写入本次提交。
- 闭环结果写 `DEV-CLOSED`，不要伪装成完整 `PASS`。
- Jenkins Build 写 `triggered by push, not verified in dev mode`。
- Target Env 写 `not verified in dev mode`。

### 2.2 验证模式：`workflow.mode: "verify"`

用于发布前、验收、高风险变更或需要完整证据的任务。默认闭环：

需求确认 → 最小设计 / 必要 DD → 开发实现 → 本地轻量校验 → commit + push → Jenkins 构建验证 → 目标环境验证 → 写 `PASS` 闭环

规则：
- Jenkins 构建必须成功。
- 目标环境健康检查必须通过。
- 关键接口 / 页面路径按任务需要补充验证。
- 只有真实验证完成后，闭环结果才允许写 `PASS`。
- 回归矩阵只有真实执行并有证据时才允许标 `PASS`。

### 2.3 任务步骤

1. 需求确认  
   明确任务范围、影响服务、是否涉及 API/数据库/部署/Jenkins/前端页面。

2. 最小设计记录  
   普通小改动只更新 `taskbook` 或设计文档中的最小必要段落；跨模块、接口、数据库、部署、Jenkins、关键页面流程变更才补 DD。

3. 开发实现  
   只修改本次任务必要文件，不做无关重构。

4. 本地轻量校验  
   默认只跑最少必要检查：
   - 优先执行 `commands.light_gate`
   - 若未配置，则执行 `quick_test` / `test` / `build` 中最先配置的一项
   - `git diff --check`
   - API 文档检查
   - Jenkins 配置检查

5. 提交推送  
   `dev` 模式先写开发闭环再 commit + push；`verify` 模式 commit + push 后继续验证 Jenkins 和目标环境。

6. Jenkins 验证  
   仅 `verify` 模式默认执行。查看 Jenkins 构建、镜像、部署结果；失败则根据 Jenkins 日志修复，再次提交推送。

7. 目标环境验证  
   仅 `verify` 模式默认执行。在真实目标环境做健康检查、关键接口、关键页面或业务路径验证。

8. 回归与证据记录  
   只有真实执行过 Jenkins / 目标环境验证，或显式要求本地运行验证时，才允许把 `regression-matrix.md` 标为 `PASS`。

9. 闭环记录  
   每个任务必须留下轻量闭环记录。`dev` 模式用 `DEV-CLOSED`，`verify` 模式用 `PASS` / `FAIL` / `PARTIAL`。

10. 配置入库  
   `docs/ENGINEERING.md` 中保留下来的环境信息、前端/后端账号、Jenkins 账号与密码必须 100% 填写、正确填写，并提交 Git 作为项目权威配置持续维护。

---

## 3. 高风险变更（必须补强验证）

以下类型默认视为高风险变更：
- 数据库迁移
- 鉴权 / 权限
- 支付 / 订单
- 部署 / Jenkins
- Nginx / 网关
- 文件上传 / 下载
- 生产配置

高风险变更至少额外要求：
- 明确 DD
- 使用 `workflow.mode: "verify"`，或在 `dev` 快速闭环后显式补目标环境真实验证
- 闭环记录写清楚验证路径和结果
- 必要时补 summary / deployment record / regression matrix

---

## 4. 本地 Docker 与完整回归（按需，不默认）

以下能力保留，但仅用于显式要求、问题复现、Jenkins/目标环境问题前置诊断：
- `runtime-up`
- `runtime-down`
- 本地 health check
- `check-matrix`
- `gen-summary`

默认情况下，不把它们作为每个小改动的固定门禁。

---

## 5. Repo 工具入口

统一使用：
- `python3 docs/tools/autopipeline/ap.py doctor`
- `python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> --msg "<TASK_ID>: <summary>"`
- `python3 docs/tools/autopipeline/ap.py commit-push <TASK_ID> --mode verify --msg "<TASK_ID>: <summary>" ...`
- `python3 docs/tools/autopipeline/ap.py light-gate`
- `python3 docs/tools/autopipeline/ap.py verify-jenkins-build ...`
- `python3 docs/tools/autopipeline/ap.py wait-health --scope target`
- `python3 docs/tools/autopipeline/ap.py verify-target ...`
- `python3 docs/tools/autopipeline/ap.py record-closure <TASK_ID> ...`

说明：
- `doctor`：检查默认流程必填项和常见配置错误。
- `light-gate`：默认轻量门禁，优先执行项目自定义快速门禁命令。
- `commit-push`：按 `workflow.mode` 自动选择开发闭环或完整验证闭环。
- `verify-target`：目标环境健康检查 + 按需关键 API / 页面验证。
- `record-closure`：默认轻量闭环记录。
- `check-matrix`、`gen-summary`、`runtime-up/down`：保留为按需工具。
