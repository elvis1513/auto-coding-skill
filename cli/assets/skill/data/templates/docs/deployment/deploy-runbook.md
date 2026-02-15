# Deploy Runbook（单机 systemd / jar）

部署参数统一读取：`docs/project/project-config.md`
- deployment.host / deployment.ssh_port / deployment.username / deployment.password
- deployment.service_name / deployment.systemd_dir
- deployment.remote_app_root / deployment.remote_jar_path / deployment.remote_config_dir / deployment.remote_bin_dir
- deployment.health_base_url / deployment.health_path

部署后必须：
- smoke-test
- api-regression
- 回归矩阵全量 PASS（0 fail）
