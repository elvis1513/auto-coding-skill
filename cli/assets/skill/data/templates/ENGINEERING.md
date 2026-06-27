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
  structure_check: ""
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
  profile_log: ".local/auto-coding-skill/gate-profile.jsonl"
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

structure:
  enabled: true
  architecture_standard: "clean-architecture-ddd-lite"
  max_file_lines_warn: 800
  max_file_lines_block: 1500
  max_function_lines_warn: 120
  max_added_lines_to_large_file: 80
  require_reuse_search: true
  block_new_responsibility_in_large_file: true
  allow_large_files:
    - ".agents/skills/**"
    - ".claude/skills/**"
    - "docs/tools/autopipeline/**"
    - "generated/**"
    - "**/generated/**"
    - "**/__generated__/**"
    - "vendor/**"
    - "dist/**"
    - "build/**"
    - "target/**"
    - "node_modules/**"
    - "**/*.generated.*"
    - "**/*.gen.*"
    - "**/*.min.js"
    - "**/*.bundle.js"
    - "**/*.map"
  accepted_debt_paths: []
  layer_rules:
    enabled: true
    block: true
    rules:
      - name: "domain"
        paths:
          - "**/domain/**"
          - "**/domains/**"
          - "**/model/**"
          - "**/models/**"
        forbidden_imports:
          - "**/infrastructure/**"
          - "**/infra/**"
          - "**/adapter/**"
          - "**/repository/**"
          - "**/repositories/**"
          - "**/client/**"
          - "**/clients/**"
          - "**/controller/**"
          - "**/handler/**"
          - "**/page/**"
          - "**/pages/**"
          - "**/component/**"
          - "**/components/**"
          - "**/view/**"
          - "**/views/**"
      - name: "application"
        paths:
          - "**/application/**"
          - "**/service/**"
          - "**/services/**"
          - "**/usecase/**"
          - "**/usecases/**"
        forbidden_imports:
          - "**/controller/**"
          - "**/handler/**"
          - "**/page/**"
          - "**/pages/**"
          - "**/component/**"
          - "**/components/**"
          - "**/view/**"
          - "**/views/**"
      - name: "shared"
        paths:
          - "**/shared/**"
          - "**/common/**"
          - "**/utils/**"
          - "**/lib/**"
        forbidden_imports:
          - "**/domain/**"
          - "**/application/**"
          - "**/service/**"
          - "**/services/**"
          - "**/infrastructure/**"
          - "**/controller/**"
          - "**/page/**"
          - "**/pages/**"
  reusable_tool_dirs:
    - "docs/tools/**"
    - "scripts/**"
    - "tools/**"
    - "packages/*/src/**"
    - "src/**/shared/**"
    - "src/**/utils/**"

optimization:
  completion_policy: "baseline-aware"
  require_baseline_for_global_review: true
  report_accepted_debt_as_findings: false

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
  evidence_log: "docs/tasks/evidence.jsonl"
  design_dir: "docs/design"
  task_archive_dir: "docs/tasks/archives"
  design_archive_dir: "docs/archive/design"
  archive_index: "docs/tasks/archive-index.md"
  ledger_check_enabled: true
  ledger_block_on_exceed: true
  active_taskbook_max_lines: 1200
  active_closure_log_max_lines: 800
  active_design_max_files: 120
  review_dir: "docs/reviews"
  health_baseline: "docs/reviews/project-health-baseline.md"
  optimization_backlog: "docs/reviews/optimization-backlog.md"
  structure_standard: "docs/architecture/structure-standard.md"
  adr_dir: "docs/architecture/adr"
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
- `commands.structure_check`：可覆盖内置结构检查；留空时使用通用 `ap.py structure-check`
- `structure.*`：通用工程结构阈值、允许的大文件模式、复用搜索目录
- `structure.layer_rules`：通用分层 import 边界检查；项目可按技术栈细化路径
- `optimization.*`：健康基线感知的优化闭环口径，避免重复把已接受债务判定为当前未完成
- `docs.evidence_log`：结构化证据 JSONL，记录 doctor / gate / verify / closure 等实际执行结果
- `docs.task_archive_dir` / `docs.design_archive_dir` / `docs.archive_index`：文档账本物理归档目录和导航索引；索引不能替代归档
- `docs.active_taskbook_max_lines` / `docs.active_closure_log_max_lines` / `docs.active_design_max_files`：活跃账本预算，超过后必须归档瘦身
- `docs.health_baseline` / `docs.optimization_backlog` / `docs.structure_standard` / `docs.adr_dir`：项目结构治理文档位置
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
- `gate.profile_log`：本地门禁耗时画像，默认写入 `.local/auto-coding-skill/gate-profile.jsonl`
- `gate.rules`：项目自定义路径规则。每条规则可包含 `name`、`paths`、`commands`、`scope`
- `structure.enabled`：是否把结构检查纳入 `light-gate`
- `structure.layer_rules.enabled` / `block`：是否检查分层 import 边界，以及违规时阻塞还是仅提示
- `structure.max_file_lines_warn` / `structure.max_file_lines_block`：文件长度预警 / 阻塞阈值
- `structure.max_added_lines_to_large_file`：禁止在已偏大的文件里继续大块堆职责
- `structure.allow_large_files`：生成物、供应商代码、构建产物等允许超长或跳过结构检查的路径
- `structure.accepted_debt_paths`：已记录为接受债务的历史大文件；只豁免历史体量，不豁免继续大幅新增
- `optimization.completion_policy`：默认 `baseline-aware`，表示“优化完成”按本轮范围和已记录基线判断，不等于仓库没有任何可优化点
- `docs.ledger_check_enabled`：默认启用文档账本健康检查
- `docs.ledger_block_on_exceed`：默认阻塞超过预算的活跃账本；仅迁移期才允许临时关闭
- `runtime.*`：仅在本地运行诊断时使用
- `commands.build` / `commands.test` / `commands.quick_test` / `commands.lint` / `commands.typecheck` / `commands.format`：按项目实际情况保留

---

## 1. 权威输入与冲突裁决（优先级）

1) `docs/ENGINEERING.md`
2) `docs/tasks/taskbook.md`
3) `docs/tasks/archives/**`
4) `docs/design/**`
5) `docs/archive/design/**`
6) `docs/interfaces/api.md`
7) `docs/interfaces/api-change-log.md`
8) `docs/testing/regression-matrix.md`
9) `docs/bugs/bug-list.md`
10) `docs/tasks/closure-log.md`
11) `docs/tasks/summaries/**`
12) `docs/deployment/**`
13) 代码实现

说明：
- `closure-log.md` 是每个任务默认必须留下的轻量闭环记录。
- `taskbook.md`、`closure-log.md` 和顶层 `docs/design/T*.md` 是活跃账本，不是永久历史仓库。超过预算时必须把已关闭历史内容物理归档到 `docs/tasks/archives/**` 和 `docs/archive/design/**`。
- `docs/tasks/archive-index.md` 只用于导航归档位置；只有索引、没有物理归档，不算完成账本瘦身。
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

## 1.7 工程结构与优化标准

默认采用 `docs/architecture/structure-standard.md` 中的通用结构标准。具体项目可以按技术栈细化目录名，但不得降低以下要求：

1) 分层清晰
   - 业务规则、用例编排、外部适配、接口入口、共享工具必须有清晰边界。
   - 新代码先落到对应层；没有合适位置时，先补最小设计或 ADR，再新增目录 / 模块。

2) 复用优先
   - 新增工具、并发控制、缓存、请求封装、格式转换、权限判断、校验逻辑前，必须先搜索已有 helper、库、组件、脚本。
   - 正常情况下复用成熟库或项目既有工具；只有明确的性能、并发、部署、许可证、兼容性约束才允许自研，并记录理由和验证。

3) 单文件容量控制
   - 超过 `structure.max_file_lines_warn` 的文件只允许小修和缺陷修复，新增职责应优先抽取模块。
   - 超过 `structure.max_file_lines_block` 的文件不得继续承载新职责，除非该文件在 `structure.allow_large_files` 中声明为生成物或外部产物。
   - 已记录为接受债务的历史大文件可放入 `structure.accepted_debt_paths`，但继续大幅新增仍会被阻塞。
   - 对已偏大的文件一次性增加超过 `structure.max_added_lines_to_large_file` 行时，`structure-check` 会阻塞，要求拆分或写明例外理由。

4) 优化完成标准
   - “优化完成”不表示仓库没有任何可优化点。
   - 默认定义为：本轮约定范围内的 P0/P1/P2 scoped items 已闭环，本地 gate 通过，没有新增未分级 P0/P1，剩余 P2/P3 已进入 backlog 或被接受为债务。
   - 新会话做整体分析时，必须先读 `docs/reviews/project-health-baseline.md` 和 `docs/reviews/optimization-backlog.md`，只报告新增、恶化、未记录 P0/P1，或已记录但需要升级优先级的问题。

5) 本地执行
   - 任务开始分类：`python3 docs/tools/autopipeline/ap.py classify --scope auto`
   - 小步快跑默认执行：`python3 docs/tools/autopipeline/ap.py structure-check --scope auto`
   - 发布、跨模块重构、架构调整默认执行：`python3 docs/tools/autopipeline/ap.py structure-check --scope full`
   - 首次落基线：`python3 docs/tools/autopipeline/ap.py baseline init --write --update-config`
   - 项目升级预检：`python3 docs/tools/autopipeline/ap.py upgrade --dry-run`
   - 文档账本健康检查：`python3 docs/tools/autopipeline/ap.py docs-ledger-check`
   - 文档账本归档预览：`python3 docs/tools/autopipeline/ap.py docs-ledger-archive --plan`
   - 文档账本归档执行：`python3 docs/tools/autopipeline/ap.py docs-ledger-archive --write`
   - 门禁耗时画像：`python3 docs/tools/autopipeline/ap.py gate-profile`
   - `doctor` 默认纳入文档账本健康检查；`light-gate` 会先跑 `doctor`，因此活跃账本超预算会阻塞后续任务，避免“只建索引、不归档瘦身”的状态长期存在。
   - `light-gate` 在 `structure.enabled: true` 时会自动纳入结构检查；如项目需要更强规则，可配置 `commands.structure_check` 覆盖内置实现。

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
