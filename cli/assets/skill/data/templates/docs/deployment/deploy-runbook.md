# Deployment Runbook（按需使用，不是默认小改动产物）

用途：
- 手工部署
- 高风险发布
- 需要额外审计证据的发布

默认情况下：
- 小改动优先走项目已配置的 CI/Jenkins 自动构建与自动部署；未启用时以本地 gate 和 closure evidence 为准
- 主要闭环证据写入 `docs/tasks/closure-log.md`
- 只有需要更重的发布审计时，才补本目录文档
