# Project Structure Standard

> 通用工程结构标准。项目可以按技术栈调整目录名，但不能降低分层、复用、可维护性和验证要求。

## 1. 目标

- 目录结构能表达业务边界、技术边界和变更边界。
- 单个文件、类、组件、函数只承担清晰职责。
- 新代码优先复用成熟库、项目已有 helper、组件、脚本和平台能力。
- 优化结论按健康基线和 backlog 判断，避免反复把已接受债务当成当前阻塞。

## 2. 推荐分层

不同语言和框架可以使用不同目录名，但职责应保持一致：

| 层级 | 常见目录名 | 职责 | 不应包含 |
| --- | --- | --- | --- |
| Domain | `domain`, `model`, `entity`, `value-object`, `policy` | 业务概念、规则、不可变约束 | HTTP、DB、UI、第三方 SDK 细节 |
| Application | `application`, `service`, `usecase`, `workflow` | 用例编排、事务边界、跨领域协调 | 控制器入参解析、SQL 细节、组件渲染 |
| Infrastructure | `infrastructure`, `adapter`, `repository`, `client`, `gateway` | DB、缓存、消息、外部 API、文件系统、运行时适配 | 核心业务规则 |
| Interface | `api`, `controller`, `handler`, `route`, `page`, `component`, `view` | HTTP/CLI/UI 入口、协议转换、展示逻辑 | 复杂业务编排和持久化细节 |
| Shared | `shared`, `common`, `utils`, `lib` | 稳定通用工具、类型、组件 | 业务专属逻辑、临时拼凑函数 |
| Tooling | `scripts`, `tools`, `docs/tools` | 自动化脚本、门禁、迁移辅助 | 在线业务运行逻辑 |

## 3. 落位规则

- 修改前先定位现有同类实现、模块边界、调用链和测试入口。
- 新增业务规则优先进入 Domain 或 Application，不直接塞进 Controller/Page/Component。
- 新增外部依赖访问优先进入 Infrastructure，并通过接口或窄适配暴露给 Application。
- UI 组件应拆分为容器、状态/数据适配、纯展示组件；不要在单个页面里混合远程请求、权限、复杂计算和大段渲染。
- 跨模块、跨层、数据库、API、部署、权限、并发、缓存、核心页面流的变更，需要最小设计；影响长期结构的决策需要 ADR。

## 4. 文件和函数规模

默认阈值来自 `docs/ENGINEERING.md`：

- 文件超过 `structure.max_file_lines_warn`：只允许小修、缺陷修复、类型补充；新增职责应先抽取模块。
- 文件超过 `structure.max_file_lines_block`：不得继续承载新职责，除非是生成物、外部产物或已在 `structure.allow_large_files` 中声明。
- 历史大文件如果已进入健康基线 / backlog，可在 `structure.accepted_debt_paths` 中登记；登记只豁免历史体量，不豁免继续大幅新增。
- 函数 / 方法 / 组件超过 `structure.max_function_lines_warn`：应拆分为命名清晰的子函数、hook、service、query、mapper 或 view component。
- 对大文件新增超过 `structure.max_added_lines_to_large_file` 行：默认阻塞，必须拆分或记录例外理由。

## 5. 复用优先规则

新增以下能力前必须先搜索现有实现：

- HTTP/API client、认证、权限、表单校验、错误处理、日志、缓存、重试、并发控制。
- 日期、金额、单位、国际化、文件处理、导入导出、分页、排序、过滤、权限判断。
- UI 基础组件、布局、表格、弹窗、上传、图表、状态管理、路由守卫。
- 自动化脚本、部署脚本、测试工具、mock、fixture、数据迁移 helper。

允许自研的前提：

- 成熟库不能满足性能、并发、部署、许可证、离线、兼容性或安全边界。
- ADR 或设计记录说明取舍。
- 有测试、benchmark、压测或真实运行证据支撑。

## 6. Review 口径

结构 review 不应只说“还能优化”。必须分级：

- P0 阻塞：构建 / 发布 / 数据 / 安全 / 核心流程风险。
- P1 必修：明显架构违规、契约漂移、重要测试缺失、近期高风险改动。
- P2 计划债务：大文件、热点目录、可拆分模块、测试增强。
- P3 可选建议：命名、风格、进一步抽象、审美类优化。

“优化完成”只表示当前约定范围闭环，不表示没有任何后续可优化点。新会话必须先读健康基线和 backlog，只报告新增、恶化、未记录 P0/P1，或需要升级优先级的已记录问题。
