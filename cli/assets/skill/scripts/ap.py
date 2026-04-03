#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoPipeline Pro Max - repo automation CLI (python)"""

from __future__ import annotations

import argparse
import datetime as _dt
import time
from pathlib import Path
from typing import Optional, List

from core import APError, ensure_git_repo, copy_tree, run, load_yaml, find_config, run_shell, http_get_status


def _skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _compose_base_args(runtime_cfg: dict) -> List[str]:
    args = ["docker", "compose"]
    compose_file = str(runtime_cfg.get("docker_compose_file") or "").strip()
    env_file = str(runtime_cfg.get("env_file") or "").strip()
    if compose_file:
        args.extend(["-f", compose_file])
    if env_file:
        args.extend(["--env-file", env_file])
    return args


def _join_url(base: str, path: str) -> str:
    base = str(base or "").strip().rstrip("/")
    path = str(path or "").strip()
    if not base or not path:
        raise APError("Health URL config incomplete. Fill base url and path in docs/ENGINEERING.md.")
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def _run_configured_command(repo: Path, cfg: dict, name: str) -> bool:
    commands = (cfg.get("commands") or {})
    command = str(commands.get(name) or "").strip()
    if not command:
        return False
    print(f"[run] {name}: {command}")
    run_shell(command, cwd=repo)
    print(f"[run] OK: {name}")
    return True


def cmd_install(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    templates = _skill_root() / "data" / "templates"

    copy_tree(templates / "docs", repo / "docs")
    copy_tree(templates / "ENGINEERING.md", repo / "docs" / "ENGINEERING.md")

    if args.bridges:
        copy_tree(templates / "bridges", repo)

    scripts_dir = repo / "scripts" / "autopipeline"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    copy_tree(Path(__file__).resolve(), scripts_dir / "ap.py")
    copy_tree(Path(__file__).resolve().parent / "core.py", scripts_dir / "core.py")

    gi = repo / ".gitignore"
    secret_line = "docs/ENGINEERING.md"
    if gi.exists():
        txt = gi.read_text(encoding="utf-8")
        if secret_line not in txt:
            gi.write_text(txt.rstrip() + "\n" + secret_line + "\n", encoding="utf-8")
    else:
        gi.write_text(secret_line + "\n", encoding="utf-8")

    print(f"[install] OK: scaffold installed into {repo}")
    print("[install] Next: edit docs/ENGINEERING.md frontmatter and fill project/runtime/jenkins fields")


def _infer_title(taskbook: Path, task_id: str) -> str:
    if not taskbook.exists():
        return "<Title>"
    for line in taskbook.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("## Task ") and task_id in line:
            for sep in ["—", "-"]:
                if sep in line:
                    return line.split(sep, 1)[1].strip()
    return "<Title>"


def cmd_gen_summary(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    task_id = args.task_id
    cfg = _load_cfg(repo)
    docs_cfg = (cfg.get("docs") or {})
    taskbook = Path(repo, str(docs_cfg.get("taskbook", "docs/tasks/taskbook.md")))
    summary_dir = Path(repo, str(docs_cfg.get("summary_dir", "docs/tasks/summaries")))
    api_change_log = str(docs_cfg.get("api_change_log", "docs/interfaces/api-change-log.md"))
    regression_matrix = str(docs_cfg.get("regression_matrix", "docs/testing/regression-matrix.md"))

    out_dir = summary_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{task_id}.md"
    if out_file.exists() and not args.force:
        raise APError(f"Summary already exists: {out_file} (use --force to overwrite)")

    title = _infer_title(taskbook, task_id)
    date = _dt.date.today().isoformat()

    staged = run(["git", "diff", "--cached", "--name-only"], cwd=repo, check=False).stdout.strip()
    unstaged = run(["git", "diff", "--name-only"], cwd=repo, check=False).stdout.strip()
    status = run(["git", "status", "--porcelain=v1"], cwd=repo, check=False).stdout.strip()

    content = f"""# Task Summary — {task_id} — {title}

- Task ID：{task_id}
- Date：{date}
- Scope（本次范围）：TODO
- Out of scope（明确未做）：TODO

---

## 1. 目标与验收结论
- 目标：TODO
- 验收结论：PASS / FAIL — TODO

## 2. 变更概览（代码/配置/本地运行/Jenkins）
### Git change snapshot
- Staged files:
{('- ' + staged.replace('\n','\n- ')) if staged else '- (none)'}
- Unstaged files:
{('- ' + unstaged.replace('\n','\n- ')) if unstaged else '- (none)'}
- Status:
```text
{status}
```

## 3. 接口变更（以 API Markdown 为准）
- 变更记录位置：`{api_change_log}`

## 5. 质量门禁证据（必须可追溯）
- 本地CI：TODO
- 静态分析：TODO
- Review 文档：TODO
- DD 文档：TODO
- Jenkins 准备：TODO
- 回归矩阵：`{regression_matrix}`（全量 PASS，0 fail）

## 6. 本地运行与 Jenkins 部署记录
- Local compose：TODO
- Jenkins build / deploy：TODO
"""

    out_file.write_text(content, encoding="utf-8")
    print(f"[gen-summary] OK: {out_file}")


def cmd_check_matrix(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    docs_cfg = (cfg.get("docs") or {})
    matrix = Path(repo, str(docs_cfg.get("regression_matrix", "docs/testing/regression-matrix.md")))
    if not matrix.exists():
        raise APError(f"Matrix not found: {matrix}")

    rows = 0
    fail = []
    for line in matrix.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cols = [c.strip() for c in s.split("|")[1:-1]]
        if len(cols) < 8:
            continue
        rid = cols[0]
        status = cols[6].upper()
        if rid in {"ID", "---"} or rid.startswith("---"):
            continue
        if not rid.startswith("R-"):
            continue
        rows += 1
        if status != "PASS":
            fail.append((rid, status or "(empty)"))

    if rows == 0:
        raise APError(f"No regression rows found in matrix: {matrix}")

    if fail:
        msg = "\n".join([f"- {rid}: {st}" for rid, st in fail])
        raise APError(f"Regression matrix not 0-fail:\n{msg}")

    print("[check-matrix] OK (0-fail)")


def _load_cfg(repo: Path) -> dict:
    cfg_path = find_config(repo)
    return load_yaml(cfg_path)


def cmd_run(args: argparse.Namespace) -> None:
    """
    Run any configured gate command by name.
    Commands are read from docs/ENGINEERING.md frontmatter.
    """
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    commands = (cfg.get("commands") or {})
    name = args.name
    if name not in commands:
        raise APError(
            f"Command not configured: commands.{name}. "
            "Edit docs/ENGINEERING.md frontmatter. "
            f"Available: {', '.join(commands.keys()) or '(none)'}"
        )
    cmd = str(commands[name])
    print(f"[run] {name}: {cmd}")
    run_shell(cmd, cwd=repo)
    print(f"[run] OK: {name}")


def cmd_runtime_up(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    runtime_cfg = (cfg.get("runtime") or {})
    if _run_configured_command(repo, cfg, "compose_up"):
        return
    compose_args = _compose_base_args(runtime_cfg) + ["up", "-d"]
    docker_service = str(runtime_cfg.get("docker_service") or "").strip()
    if docker_service:
        compose_args.append(docker_service)
    print(f"[runtime-up] {' '.join(compose_args)}")
    run(compose_args, cwd=repo)
    print("[runtime-up] OK")


def cmd_runtime_down(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    runtime_cfg = (cfg.get("runtime") or {})
    if _run_configured_command(repo, cfg, "compose_down"):
        return
    compose_args = _compose_base_args(runtime_cfg) + ["down", "--remove-orphans"]
    print(f"[runtime-down] {' '.join(compose_args)}")
    run(compose_args, cwd=repo)
    print("[runtime-down] OK")


def cmd_wait_health(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    scope = args.scope
    if scope == "runtime":
        runtime_cfg = (cfg.get("runtime") or {})
        url = _join_url(str(runtime_cfg.get("health_base_url") or ""), str(runtime_cfg.get("health_path") or ""))
        timeout_s = int(runtime_cfg.get("startup_timeout_sec") or 120)
    else:
        jenkins_cfg = (cfg.get("jenkins") or {})
        url = _join_url(
            str(jenkins_cfg.get("prod_health_base_url") or ""),
            str(jenkins_cfg.get("prod_health_path") or "")
        )
        timeout_s = int(jenkins_cfg.get("deploy_timeout_sec") or 1800)

    deadline = time.time() + timeout_s
    last_error = "(none)"
    while time.time() < deadline:
        try:
            status = http_get_status(url, timeout_s=5)
            last_error = f"HTTP {status}"
            if 200 <= status < 400:
                print(f"[wait-health] OK: {scope} {url} -> {status}")
                return
        except Exception as exc:  # pragma: no cover - depends on runtime env
            last_error = str(exc)
        time.sleep(2)
    raise APError(f"Health check timeout for {scope}: {url}\nLast result: {last_error}")


def cmd_verify_jenkins(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    project_cfg = (cfg.get("project") or {})
    jenkins_cfg = (cfg.get("jenkins") or {})
    jenkinsfile = Path(repo, str(project_cfg.get("jenkinsfile") or "Jenkinsfile"))
    if not jenkinsfile.exists():
        raise APError(f"Jenkinsfile not found: {jenkinsfile}")

    required = [
        ("jenkins.job_name", jenkins_cfg.get("job_name")),
        ("jenkins.job_url", jenkins_cfg.get("job_url")),
        ("jenkins.trigger_branch", jenkins_cfg.get("trigger_branch")),
        ("jenkins.image_repository", jenkins_cfg.get("image_repository")),
        ("jenkins.image_tag_strategy", jenkins_cfg.get("image_tag_strategy")),
        ("jenkins.deploy_env", jenkins_cfg.get("deploy_env")),
        ("jenkins.prod_health_base_url", jenkins_cfg.get("prod_health_base_url")),
        ("jenkins.prod_health_path", jenkins_cfg.get("prod_health_path")),
    ]
    missing = [name for name, value in required if not str(value or "").strip()]
    if missing:
        raise APError("Missing Jenkins config: " + ", ".join(missing))
    print(f"[verify-jenkins] OK: {jenkinsfile}")


def cmd_verify_api_docs(args: argparse.Namespace) -> None:
    """Ensure API markdown doc and change-log exist."""
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    docs = (cfg.get("docs") or {})
    api_doc = Path(repo, str(docs.get("api_doc", "docs/interfaces/api.md")))
    change_log = Path(repo, str(docs.get("api_change_log", "docs/interfaces/api-change-log.md")))
    missing = [p for p in [api_doc, change_log] if not p.exists()]
    if missing:
        raise APError("Missing API docs: " + ", ".join([str(p) for p in missing]))
    print(f"[verify-api-docs] OK: {api_doc} + {change_log}")


def cmd_commit_push(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    docs_cfg = (cfg.get("docs") or {})
    summary_dir = Path(repo, str(docs_cfg.get("summary_dir", "docs/tasks/summaries")))

    task_id = args.task_id
    msg = args.msg

    summary = summary_dir / f"{task_id}.md"
    if not summary.exists():
        raise APError(
            f"Task summary missing: {summary}\n"
            f"Generate: python3 scripts/autopipeline/ap.py gen-summary {task_id}"
        )

    if args.require_runtime_health:
        cmd_wait_health(argparse.Namespace(repo=str(repo), scope="runtime"))

    if args.require_jenkins:
        cmd_verify_jenkins(argparse.Namespace(repo=str(repo)))

    if args.require_matrix:
        cmd_check_matrix(argparse.Namespace(repo=str(repo)))

    run(["git", "add", "-A"], cwd=repo)
    diff = run(["git", "diff", "--cached", "--name-only"], cwd=repo).stdout.strip()
    if not diff:
        raise APError("Nothing to commit.")

    run(["git", "commit", "-m", msg], cwd=repo)
    run(["git", "push"], cwd=repo)
    print("[commit-push] OK - push completed, Jenkins should auto-trigger")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="autopipeline")
    p.add_argument("--repo", default=".")
    sp = p.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("install")
    s.add_argument("--bridges", action="store_true")
    s.set_defaults(func=cmd_install)

    s = sp.add_parser("gen-summary")
    s.add_argument("task_id")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_gen_summary)

    s = sp.add_parser("check-matrix")
    s.set_defaults(func=cmd_check_matrix)

    s = sp.add_parser("run")
    s.add_argument("name")
    s.set_defaults(func=cmd_run)

    s = sp.add_parser("runtime-up")
    s.set_defaults(func=cmd_runtime_up)

    s = sp.add_parser("runtime-down")
    s.set_defaults(func=cmd_runtime_down)

    s = sp.add_parser("wait-health")
    s.add_argument("--scope", choices=["runtime", "prod"], default="runtime")
    s.set_defaults(func=cmd_wait_health)

    s = sp.add_parser("verify-jenkins")
    s.set_defaults(func=cmd_verify_jenkins)

    s = sp.add_parser("verify-api-docs")
    s.set_defaults(func=cmd_verify_api_docs)

    s = sp.add_parser("commit-push")
    s.add_argument("task_id")
    s.add_argument("--msg", required=True)
    s.add_argument("--require-runtime-health", action="store_true")
    s.add_argument("--require-jenkins", action="store_true")
    s.add_argument("--require-matrix", action="store_true")
    s.set_defaults(func=cmd_commit_push)

    try:
        args = p.parse_args(argv)
        args.func(args)
        return 0
    except APError as e:
        print(f"[ERROR] {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
