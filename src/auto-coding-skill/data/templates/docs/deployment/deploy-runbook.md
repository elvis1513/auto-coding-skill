# Deployment Runbook（按需使用，不是默认小改动产物）

用途：
- 手工部署
- 高风险发布
- 需要额外审计证据的发布

默认情况下：
- 小改动直接走 Jenkins 自动构建与自动部署
- 主要闭环证据写入 `docs/tasks/closure-log.md`
- 只有需要更重的发布审计时，才补本目录文档
