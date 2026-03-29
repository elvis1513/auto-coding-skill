# Local Runtime Runbook（本地 Docker 验证）

运行参数统一读取：`docs/ENGINEERING.md` frontmatter
- runtime.docker_compose_file / runtime.docker_service
- runtime.container_name / runtime.image / runtime.app_port
- runtime.health_base_url / runtime.health_path
- runtime.env_file / runtime.startup_timeout_sec

本地 Docker 启动后必须：
- smoke-test
- api-regression
- 回归矩阵全量 PASS（0 fail）
