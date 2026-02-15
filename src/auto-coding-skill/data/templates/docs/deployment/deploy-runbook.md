# Deploy Runbook（单机 systemd / jar）

targets.yaml 必填：
- target.host/user/password/ssh_port
- service.name（systemd service 文件名）
- service.systemd_dir（固定：/usr/lib/systemd/system）
- paths.remote_*（远端目录与 jar 路径）
- health.base_url + health_path（可配置）

部署后必须：
- smoke-test
- api-regression
- 回归矩阵全量 PASS（0 fail）
