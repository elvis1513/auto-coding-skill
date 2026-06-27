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
  gate_changed: ""
  gate_standard: ""
  gate_full: ""
  light_gate: ""
  build: ""
  test: ""
  quick_test: ""
  lint: ""
  typecheck: ""
  format: ""

gate:
  default_scope: "standard"
  fallback_scope: "standard"
  full_on_unknown: true
  no_change_scope: "standard"
  full_on:
    paths:
      - "Jenkinsfile"
      - "Jenkinsfile.*"
      - ".github/workflows/**"
      - "Dockerfile"
      - "**/Dockerfile"
      - "docker-compose*.yml"
      - "docker-compose*.yaml"
      - "compose*.yml"
      - "compose*.yaml"
      - "docs/ENGINEERING.md"
      - "docs/tools/autopipeline/**"
      - "package-lock.json"
      - "pnpm-lock.yaml"
      - "yarn.lock"
      - "go.mod"
      - "go.sum"
      - "Cargo.lock"
      - "pom.xml"
      - "build.gradle*"
      - "settings.gradle*"
  rules: []

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
  frontend_password_env: ""
  backend_base_url: ""
  backend_username: ""
  backend_password_env: ""
  backend_root_username: ""
  backend_root_password_env: ""
  health_base_url: ""
  health_path: ""

jenkins:
  base_url: ""
  ui_username: ""
  ui_password_env: ""
  job_url: ""
  trigger_branch: ""
  image_repository: ""
  image_tag_strategy: ""
  deploy_env: ""
  deploy_timeout_sec: 1800
  api_user: ""
  api_password_env: ""

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
- 目标环境和 Jenkins 密码默认通过 `*_password_env` 指向当前 shell 中的环境变量；确需兼容旧项目时才使用明文 `*_password` 字段。
- 未参与默认流程的环境项不要保留占位；模板中未保留的字段视为已清理，不再额外配置。

---

## 0. 配置填写（必须）

先填写 `docs/ENGINEERING.md` frontmatter 中的所有空值。重点包括：
- `workflow.mode`：`dev` 或 `verify`，默认推荐 `dev`
- `commands.gate_changed` / `commands.gate_standard` / `commands.gate_full`：推荐配置分层门禁命令；旧项目也可以继续只配置 `commands.light_gate`
- `gate.*`：按项目声明路径规则和高风险升级规则；未配置时保持标准门禁行为
- `target_env.*`：目标环境前端 / 后端地址、用户名、密码引用，必须全部填写且真实可用
- `jenkins.*`：Jenkins UI/API 用户名、密码引用、Job、分支、镜像、部署环境，必须全部填写且真实可用

字段说明：
- `target_env.backend_username` + `target_env.backend_password_env` 或 `target_env.backend_password`：目标环境后台账号
- `target_env.backend_root_username` + `target_env.backend_root_password_env` 或 `target_env.backend_root_password`：目标环境后台服务器 root 账号
- `target_env.frontend_username` + `target_env.frontend_password_env` 或 `target_env.frontend_password`：目标环境前端登录账号
- `jenkins.ui_username` + `jenkins.ui_password_env` 或 `jenkins.ui_password`：Jenkins 页面登录账号
- `jenkins.api_user` + `jenkins.api_password_env` 或 `jenkins.api_password`：Jenkins API 用户名 / 密码

默认必填：
- `workflow.mode`
- `project.name`
- `commands.gate_changed` / `commands.gate_standard` / `commands.gate_full`，或 `commands.light_gate` / `commands.quick_test` / `commands.test` / `commands.build`
- `target_env.name`
- `target_env.frontend_base_url`
- `target_env.frontend_username`
- `target_env.frontend_password` 或 `target_env.frontend_password_env`
- `target_env.backend_base_url`
- `target_env.backend_username`
- `target_env.backend_password` 或 `target_env.backend_password_env`
- `target_env.backend_root_username`
- `target_env.backend_root_password` 或 `target_env.backend_root_password_env`
- `target_env.health_base_url`
- `target_env.health_path`
- `jenkins.base_url`
- `jenkins.ui_username`
- `jenkins.ui_password` 或 `jenkins.ui_password_env`
- `jenkins.api_user`
- `jenkins.api_password` 或 `jenkins.api_password_env`
- `jenkins.trigger_branch`
- `jenkins.image_repository`
- `jenkins.image_tag_strategy`
- `jenkins.deploy_env`
- `jenkins.job_url`

按需填写：
- `gate.default_scope`：默认 `standard`；需要小步快跑时设为 `auto` 或 `changed`
- `gate.rules`：项目自定义路径规则。每条规则可包含 `name`、`paths`、`commands`、`scope`
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

任务开始时先做能力盘点：当前可用的 MCP servers、已安装 skills、plugins / apps / connectors、浏览器控制能力、repo 脚本。能直接读取权威状态、当前文档或真实 UI 的能力，优先于手写推测。

默认路由：

1) 本地代码 / 测试 / Git / 门禁
   优先使用 shell、项目脚本、`docs/tools/autopipeline/ap.py`。本地 diff、提交、推送以 Git 实际状态为准。

2) 当前库 / 框架 / SDK / API / CLI / 云服务文档
   优先使用 Context7 等文档 MCP 或对应已安装 skill，先确认版本、参数、默认行为、废弃项，再改代码。

3) 浏览器与 UI 验证
   - localhost、file、应用内页面：优先 Browser / in-app browser；需要脚本控制时配合 node_repl。
   - 必须复用用户 Chrome 登录态、扩展或已有标签页：使用 Chrome 控制能力；需要脚本控制时配合 node_repl。
   - 需要稳定自动化复现、截图或 smoke test：使用 Playwright。
   - 原生桌面 App 或没有专用连接器的 UI：才使用 Computer Use。

4) GitHub / PR / Issue / CI
   远端 PR、Issue、review comments、Actions/CI 状态优先用 GitHub connector；本地 diff、commit、push 仍用本地 Git。

5) Figma / 视觉设计 / 前端体验
   设计上下文先用 Figma；视觉强相关页面优先使用 frontend / build-web / product-design 类 skill，并用浏览器截图或真实页面验证收口。

6) 安全敏感变更
   鉴权、权限、支付、文件上传下载、部署、依赖、数据边界变更，默认安排 reviewer 或安全扫描能力做只读复核。

7) 报告与文件类产物
   Dashboard / 数据报告使用 Data Analytics；Word/PDF/表格/PPT/LaTeX 使用对应文档类 skill 或插件，并做渲染/校验。

8) OpenAI/API key/密钥类操作
   使用平台提供的安全 key 创建或写入流程；不要在普通文档、日志或提交中手写、复制、持久化密钥。

9) 屏幕与近期操作上下文
   当任务依赖用户当前屏幕、浏览器登录状态或最近手工操作时，优先使用 Chronicle / screenshot 类能力获取真实上下文。

回退规则：
- 工具不可用、权限不足、结果不可靠或比直接执行更慢时，才回退到 shell 或手工流程。
- 不重复手写工具已经能直接读取或写回的权威数据。
- 外部信息必须优先来自官方文档、项目连接器或真实运行状态。

---

## 1.6 多 Agent 协作策略（Claude / Codex 专属）

默认使用 `.agents/agents` 中的角色模型来拆解任务；只有在当前客户端明确提供并允许子代理/多代理工具时，才实际并行派发。若运行时策略不允许子代理，则由主 agent 按同一角色顺序串行完成，不假装并行。

默认角色：

1) `explorer`
   只读探索：定位入口、调用链、关键文件、配置项、根因候选。

2) `docs_researcher`
   文档/API 核对：确认当前版本行为、参数、兼容性、废弃项和官方建议。

3) `browser_debugger`
   浏览器验证：复现路径、控制台、网络请求、截图、实际/预期行为。

4) `fixer`
   定点实现：在问题和验收路径清晰后做最小可辩护修改，并运行聚焦校验。

5) `reviewer`
   只读复核：正确性、安全性、回归风险、边界条件和测试缺口。

主 agent 始终负责：
- 任务定义、范围裁决、方案取舍
- 代码集成和冲突处理
- 轻量门禁、Jenkins/目标环境闭环
- 文档闭环、Git 状态、最终交付

任务边界不清、需要强一致裁决或涉及架构取舍时，由主 agent 保持控制，不机械拆分。

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
