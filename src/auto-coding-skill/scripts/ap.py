#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoPipeline Pro Max - repo automation CLI (python)"""

from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path
from typing import Optional, List

from core import APError, ensure_git_repo, copy_tree, run, load_yaml, find_config, run_shell


def _skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def cmd_install(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    templates = _skill_root() / "data" / "templates"

    copy_tree(templates / "docs", repo / "docs")
    copy_tree(templates / "ENGINEERING.md", repo / "ENGINEERING.md")

    if args.bridges:
        copy_tree(templates / "bridges", repo)

    tools_dir = repo / "tools" / "autopipeline"
    tools_dir.mkdir(parents=True, exist_ok=True)
    copy_tree(Path(__file__).resolve(), tools_dir / "ap.py")
    copy_tree(Path(__file__).resolve().parent / "core.py", tools_dir / "core.py")

    gi = repo / ".gitignore"
    secret_line = "docs/project/project-config.md"
    if gi.exists():
        txt = gi.read_text(encoding="utf-8")
        if secret_line not in txt:
            gi.write_text(txt.rstrip() + "\n" + secret_line + "\n", encoding="utf-8")
    else:
        gi.write_text(secret_line + "\n", encoding="utf-8")

    print(f"[install] OK: scaffold installed into {repo}")
    print("[install] Next: edit docs/project/project-config.md and fill all project/env fields")


def _infer_title(repo: Path, task_id: str) -> str:
    taskbook = repo / "docs" / "tasks" / "taskbook.md"
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
    api_change_log = str(docs_cfg.get("api_change_log", "docs/interfaces/api-change-log.md"))
    regression_matrix = str(docs_cfg.get("regression_matrix", "docs/testing/regression-matrix.md"))

    out_dir = repo / "docs" / "tasks" / "summaries"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{task_id}.md"
    if out_file.exists() and not args.force:
        raise APError(f"Summary already exists: {out_file} (use --force to overwrite)")

    title = _infer_title(repo, task_id)
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

## 2. 变更概览（代码/配置/部署）
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
- 回归矩阵：`{regression_matrix}`（全量 PASS，0 fail）
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
    Run a configured gate command:
      build | test | lint | typecheck | format | smoke | regression
    Commands are read from docs/project/project-config.md frontmatter.
    """
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    commands = (cfg.get("commands") or {})
    name = args.name
    if name not in commands:
        raise APError(
            f"Command not configured: commands.{name}. "
            "Edit docs/project/project-config.md. "
            f"Available: {', '.join(commands.keys()) or '(none)'}"
        )
    cmd = str(commands[name])
    print(f"[run] {name}: {cmd}")
    run_shell(cmd, cwd=repo)
    print(f"[run] OK: {name}")


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

    task_id = args.task_id
    msg = args.msg

    summary = repo / "docs" / "tasks" / "summaries" / f"{task_id}.md"
    if not summary.exists():
        raise APError(
            f"Task summary missing: {summary}\n"
            f"Generate: python3 tools/autopipeline/ap.py gen-summary {task_id}"
        )

    if args.require_matrix:
        cmd_check_matrix(argparse.Namespace(repo=str(repo)))

    run(["git", "add", "-A"], cwd=repo)
    diff = run(["git", "diff", "--cached", "--name-only"], cwd=repo).stdout.strip()
    if not diff:
        raise APError("Nothing to commit.")

    run(["git", "commit", "-m", msg], cwd=repo)
    run(["git", "push"], cwd=repo)
    print("[commit-push] OK")


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

    s = sp.add_parser("verify-api-docs")
    s.set_defaults(func=cmd_verify_api_docs)

    s = sp.add_parser("commit-push")
    s.add_argument("task_id")
    s.add_argument("--msg", required=True)
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
