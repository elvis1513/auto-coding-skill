# Deployment Runbook（本地 Compose 验证 + Jenkins 自动部署）

统一读取：`docs/ENGINEERING.md` frontmatter
- `runtime.*`：本地 Compose 启动与健康检查
- `jenkins.*`：Jenkins Job、镜像仓库、目标环境、生产健康检查

执行顺序：
1. 本地构建、测试、lint、typecheck 通过
2. 本地 `docker compose` 启动目标服务
3. 本地 health / smoke / regression 全部通过
4. `commit + push`
5. Jenkins 自动触发，完成镜像构建、镜像推送、目标环境更新
6. 检查 Jenkins 结果与目标环境健康状态

完成条件：
- 本地 Compose 验证通过
- Jenkins Pipeline 成功
- 目标环境健康检查通过
- `docs/deployment/deploy-records/<TASK_ID>-YYYYMMDD.md` 证据补齐
