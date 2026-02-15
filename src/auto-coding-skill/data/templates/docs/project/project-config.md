---
project:
  name: "fill-project-name"
  repo_root: "."

commands:
  build: "fill-build-command"
  test: "fill-test-command"
  lint: "fill-lint-command"
  typecheck: "fill-typecheck-command"
  format: "fill-format-command"
  smoke: "fill-smoke-command"
  regression: "fill-regression-command"

docs:
  taskbook: "docs/tasks/taskbook.md"
  design_dir: "docs/design"
  review_dir: "docs/reviews"
  api_doc: "docs/interfaces/api.md"
  api_change_log: "docs/interfaces/api-change-log.md"
  regression_matrix: "docs/testing/regression-matrix.md"
  bug_list: "docs/bugs/bug-list.md"
  summary_dir: "docs/tasks/summaries"

deployment:
  host: "fill-ip-or-domain"
  ssh_port: 22
  username: "fill-username"
  password: "fill-password"
  service_name: "fill-service-name"
  systemd_dir: "/usr/lib/systemd/system"
  remote_app_root: "fill-remote-app-root"
  remote_jar_path: "fill-remote-jar-path"
  remote_config_dir: "fill-remote-config-dir"
  remote_bin_dir: "fill-remote-bin-dir"
  health_base_url: "fill-health-base-url"
  health_path: "/health"
---

# Project Config（唯一人工维护入口）

规则：
1) 所有需要人工维护的项统一写在本文件 frontmatter。
2) 其他 docs 不再重复维护配置，统一引用本文件。
3) 开发前先补齐本文件，再启动任何 Gate。
