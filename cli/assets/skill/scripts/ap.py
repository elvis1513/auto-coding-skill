#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoPipeline Pro Max - repo automation CLI (python)"""

from __future__ import annotations

import argparse
import base64
import hashlib
import datetime as _dt
import fnmatch
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, List

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

from core import APError, ensure_git_repo, copy_tree, run, load_yaml, find_config, run_shell, http_get_status


_JENKINS_CRUMB_CACHE: dict[str, dict[str, str]] = {}
_INVALID_PLACEHOLDERS = {"N/A", "TODO", "TBD", "CHANGEME", "CHANGE_ME", "FILL_ME", "FILL-ME", "PLACEHOLDER", "XXX"}


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


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _repo_rel(repo: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def _evidence_log_path(repo: Path, cfg: dict) -> Path:
    docs_cfg = cfg.get("docs") or {}
    rel = _text(docs_cfg.get("evidence_log")) or "docs/tasks/evidence.jsonl"
    return Path(repo, rel)


def _gate_profile_path(repo: Path, cfg: dict) -> Path:
    gate_cfg = _gate_cfg(cfg)
    rel = _text(gate_cfg.get("profile_log")) or ".local/auto-coding-skill/gate-profile.jsonl"
    return Path(repo, rel)


def _record_evidence(repo: Path, cfg: dict, event: str, status: str, payload: Optional[dict] = None) -> None:
    record = {
        "timestamp": _now_iso(),
        "event": event,
        "status": status,
        "repo": str(repo),
    }
    if payload:
        record.update(payload)
    try:
        _append_jsonl(_evidence_log_path(repo, cfg), record)
    except Exception as exc:
        print(f"[evidence] WARN: failed to write evidence log: {exc}", file=sys.stderr)


def _record_gate_profile(
    repo: Path,
    cfg: dict,
    name: str,
    status: str,
    duration_s: float,
    scope: str = "",
    detail: str = "",
) -> None:
    record = {
        "timestamp": _now_iso(),
        "name": name,
        "status": status,
        "duration_s": round(duration_s, 3),
        "scope": scope,
        "detail": detail,
    }
    try:
        _append_jsonl(_gate_profile_path(repo, cfg), record)
    except Exception as exc:
        print(f"[gate-profile] WARN: failed to write profile log: {exc}", file=sys.stderr)


def _run_configured_command(repo: Path, cfg: dict, name: str) -> bool:
    commands = (cfg.get("commands") or {})
    command = str(commands.get(name) or "").strip()
    if not command:
        return False
    print(f"[run] {name}: {command}")
    start = time.time()
    try:
        run_shell(command, cwd=repo)
    except APError as exc:
        duration_s = time.time() - start
        _record_gate_profile(repo, cfg, name, "fail", duration_s, detail=str(exc))
        _record_evidence(repo, cfg, "command", "fail", {"name": name, "duration_s": round(duration_s, 3)})
        raise
    duration_s = time.time() - start
    _record_gate_profile(repo, cfg, name, "pass", duration_s)
    _record_evidence(repo, cfg, "command", "pass", {"name": name, "duration_s": round(duration_s, 3)})
    print(f"[run] OK: {name} ({duration_s:.1f}s)")
    return True


def _jenkins_basic_auth_headers(cfg: dict) -> dict:
    jenkins_cfg = (cfg.get("jenkins") or {})
    credential_pairs = [
        ("api_user", "api_password"),
        ("ui_username", "ui_password"),
    ]
    errors: list[str] = []

    for user_field, secret_field in credential_pairs:
        user = _text(jenkins_cfg.get(user_field))
        if not _is_explicit_fill(user):
            continue
        try:
            secret = _resolve_secret("jenkins", jenkins_cfg, secret_field)
        except APError as exc:
            errors.append(str(exc))
            continue
        raw = f"{user}:{secret}".encode("utf-8")
        auth = base64.b64encode(raw).decode("ascii")
        return {"Authorization": f"Basic {auth}"}

    detail = "\n- " + "\n- ".join(errors) if errors else ""
    raise APError(
        "Missing Jenkins API credentials. Configure jenkins.api_user with "
        "jenkins.api_password or jenkins.api_password_env, or configure "
        "jenkins.ui_username with jenkins.ui_password or jenkins.ui_password_env."
        + detail
    )


def _http_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def _http_get(url: str, headers: Optional[dict[str, str]] = None, timeout_s: int = 10) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def _basic_auth_header(username: str, password: str) -> dict[str, str]:
    raw = f"{username}:{password}".encode("utf-8")
    auth = base64.b64encode(raw).decode("ascii")
    return {"Authorization": f"Basic {auth}"}


def _jenkins_root_url(cfg: dict, job_url: str = "") -> str:
    jenkins_cfg = (cfg.get("jenkins") or {})
    base_url = str(jenkins_cfg.get("base_url") or "").strip().rstrip("/")
    if base_url:
        return base_url

    source = str(job_url or jenkins_cfg.get("job_url") or "").strip().rstrip("/")
    if not source:
        return ""
    if "/job/" in source:
        return source.split("/job/", 1)[0].rstrip("/")
    return source


def _jenkins_crumb_api_url(cfg: dict, job_url: str = "") -> str:
    root = _jenkins_root_url(cfg, job_url=job_url)
    if not root:
        return ""
    return root.rstrip("/") + "/crumbIssuer/api/json"


def _jenkins_crumb_headers(cfg: dict, job_url: str = "", timeout_s: int = 15) -> dict:
    crumb_url = _jenkins_crumb_api_url(cfg, job_url=job_url)
    if not crumb_url:
        return {}
    cached = _JENKINS_CRUMB_CACHE.get(crumb_url)
    if cached:
        return dict(cached)

    headers = {"Accept": "application/json"}
    headers.update(_jenkins_basic_auth_headers(cfg))
    req = urllib.request.Request(crumb_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {}
        body = _http_error_body(exc)
        raise APError(
            f"Jenkins crumb request failed: {crumb_url}\n"
            f"HTTP {exc.code}\n{body or '(empty response body)'}"
        ) from exc
    except Exception as exc:
        raise APError(f"Jenkins crumb request failed: {crumb_url}\n{exc}") from exc

    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise APError(f"Jenkins crumb endpoint returned non-JSON response: {crumb_url}\n{exc}") from exc

    field = str(payload.get("crumbRequestField") or "").strip()
    crumb = str(payload.get("crumb") or "").strip()
    if not field or not crumb:
        return {}

    crumb_headers = {field: crumb}
    _JENKINS_CRUMB_CACHE[crumb_url] = crumb_headers
    return dict(crumb_headers)


def _jenkins_api_get_json(url: str, cfg: dict, timeout_s: int = 15, allow_404: bool = False) -> Optional[dict]:
    headers = {"Accept": "application/json"}
    headers.update(_jenkins_basic_auth_headers(cfg))
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = _http_error_body(exc)
        if exc.code == 404 and allow_404:
            return None
        if exc.code == 403:
            crumb_headers = _jenkins_crumb_headers(cfg, job_url=url, timeout_s=timeout_s)
            if crumb_headers:
                retry_headers = dict(headers)
                retry_headers.update(crumb_headers)
                retry_req = urllib.request.Request(url, headers=retry_headers, method="GET")
                try:
                    with urllib.request.urlopen(retry_req, timeout=timeout_s) as resp:
                        data = resp.read().decode("utf-8")
                except urllib.error.HTTPError as retry_exc:
                    if retry_exc.code == 404 and allow_404:
                        return None
                    retry_body = _http_error_body(retry_exc)
                    raise APError(
                        f"Jenkins API request failed after crumb retry: {url}\n"
                        f"HTTP {retry_exc.code}\n{retry_body or '(empty response body)'}"
                    ) from retry_exc
                except Exception as retry_exc:
                    raise APError(f"Jenkins API request failed after crumb retry: {url}\n{retry_exc}") from retry_exc
            else:
                raise APError(
                    f"Jenkins API request failed: {url}\n"
                    f"HTTP 403\n{body or '(empty response body)'}\n"
                    "Jenkins may require crumb/CSRF handling, but no crumb issuer endpoint was available. "
                    "Fill jenkins.base_url in docs/ENGINEERING.md if needed."
                ) from exc
        else:
            raise APError(
                f"Jenkins API request failed: {url}\n"
                f"HTTP {exc.code}\n{body or '(empty response body)'}"
            ) from exc
    except Exception as exc:
        raise APError(f"Jenkins API request failed: {url}\n{exc}") from exc
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        raise APError(f"Jenkins API returned non-JSON response: {url}\n{exc}") from exc


def _resolve_git_short_sha(repo: Path, ref: str) -> str:
    result = run(["git", "rev-parse", "--short=12", ref], cwd=repo, check=False)
    value = result.stdout.strip()
    if value:
        return value
    return ref.strip()


def _resolve_git_branch_name(repo: Path, ref: str) -> str:
    result = run(["git", "rev-parse", "--abbrev-ref", ref], cwd=repo, check=False)
    value = result.stdout.strip()
    if value and value != "HEAD":
        return value
    return ""


def _jenkins_builds_api_url(job_url: str, max_builds: int) -> str:
    base = str(job_url or "").strip().rstrip("/")
    if not base:
        raise APError("Missing jenkins.job_url in docs/ENGINEERING.md")
    tree = f"builds[number,result,building,description,url]{{0,{max_builds}}}"
    return f"{base}/api/json?tree={urllib.parse.quote(tree, safe='=,')}"


def _jenkins_job_path(job_name: str) -> str:
    parts = [p.strip() for p in str(job_name or "").split("/") if p.strip()]
    if not parts:
        raise APError("Jenkins job name is empty. Pass --job-name or fill jenkins.job_name.")
    return "/".join(f"job/{urllib.parse.quote(part, safe='')}" for part in parts)


def _jenkins_job_url_from_name(base_url: str, job_name: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        raise APError("Missing Jenkins base URL. Fill jenkins.base_url or pass --job-url.")
    return f"{base}/{_jenkins_job_path(job_name)}"


def _jenkins_branch_job_candidates(branch_name: str) -> List[str]:
    raw = str(branch_name or "").strip()
    if not raw:
        return []

    candidates: List[str] = []

    def add(value: str) -> None:
        if value and value not in candidates:
            candidates.append(value)

    if "/" not in raw:
        add(urllib.parse.quote(raw, safe=""))
    single = urllib.parse.quote(raw, safe="")
    double = urllib.parse.quote(single, safe="")
    add(single)
    add(double)
    return candidates


def _jenkins_branch_job_urls(root_job_url: str, branch_name: str) -> List[str]:
    base = str(root_job_url or "").strip().rstrip("/")
    if not base:
        raise APError("Missing Jenkins multibranch root job URL.")
    urls: List[str] = []
    for candidate in _jenkins_branch_job_candidates(branch_name):
        url = f"{base}/job/{candidate}"
        if url not in urls:
            urls.append(url)
    return urls


def _resolve_jenkins_job_url(cfg: dict, job_name: str = "", job_url: str = "") -> str:
    jenkins_cfg = (cfg.get("jenkins") or {})
    explicit_url = str(job_url or "").strip()
    requested_name = str(job_name or "").strip()
    configured_url = str(jenkins_cfg.get("job_url") or "").strip()
    base_url = str(jenkins_cfg.get("base_url") or "").strip()

    if explicit_url:
        return explicit_url.rstrip("/")
    if requested_name:
        if base_url:
            return _jenkins_job_url_from_name(base_url, requested_name)
        raise APError(
            f"Cannot resolve Jenkins job URL for job '{requested_name}'. "
            "Pass --job-url, or fill jenkins.base_url in docs/ENGINEERING.md."
        )
    if configured_url:
        return configured_url.rstrip("/")
    raise APError(
        "Missing Jenkins job location. Fill jenkins.job_url in docs/ENGINEERING.md, "
        "or pass --job-url / --job-name explicitly."
    )


def _resolve_jenkins_job_candidates(
    cfg: dict,
    repo: Path,
    git_ref: str = "",
    job_name: str = "",
    job_url: str = "",
    multibranch_root_job: str = "",
    branch_name: str = "",
) -> List[str]:
    jenkins_cfg = (cfg.get("jenkins") or {})
    effective_branch = str(branch_name or "").strip()
    effective_root = str(multibranch_root_job or "").strip()
    if not effective_branch and effective_root:
        inferred_branch = _resolve_git_branch_name(repo, git_ref or "HEAD")
        if inferred_branch:
            effective_branch = inferred_branch

    explicit_url = str(job_url or "").strip()
    explicit_name = str(job_name or "").strip()
    configured_url = str(jenkins_cfg.get("job_url") or "").strip()

    if effective_branch:
        if explicit_url:
            return _jenkins_branch_job_urls(explicit_url, effective_branch)
        if effective_root:
            base_url = str(jenkins_cfg.get("base_url") or "").strip()
            return _jenkins_branch_job_urls(_jenkins_job_url_from_name(base_url, effective_root), effective_branch)
        if explicit_name:
            base_url = str(jenkins_cfg.get("base_url") or "").strip()
            return _jenkins_branch_job_urls(_jenkins_job_url_from_name(base_url, explicit_name), effective_branch)
        if configured_url:
            return _jenkins_branch_job_urls(configured_url, effective_branch)
        raise APError(
            "Missing Jenkins multibranch root job location. Pass --job-url / --job-name together with "
            "--branch-name, or pass --multibranch-root-job with jenkins.base_url."
        )

    return [_resolve_jenkins_job_url(cfg, job_name=job_name, job_url=job_url)]


def _jenkins_build_api_url(job_url: str, build_number: int) -> str:
    base = str(job_url or "").strip().rstrip("/")
    if not base:
        raise APError("Missing Jenkins job URL.")
    if build_number <= 0:
        raise APError("Build number must be a positive integer.")
    tree = "number,result,building,description,url"
    return f"{base}/{build_number}/api/json?tree={urllib.parse.quote(tree, safe='=,')}"


def _assert_jenkins_build_success(build: dict, identifier: str, allow_no_deploy: bool) -> tuple[str, str]:
    if build.get("building"):
        raise APError(f"Jenkins build is still running: {identifier}")

    result = str(build.get("result") or "").strip().upper()
    description = str(build.get("description") or "").strip()
    if result != "SUCCESS":
        raise APError(f"Jenkins build did not succeed: {identifier} result={result or '(empty)'}")
    if not allow_no_deploy and description.startswith("no-deploy:"):
        raise APError(f"Jenkins build succeeded but did not deploy: {identifier} {description}")
    return result, description


def cmd_install(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    templates = _skill_root() / "data" / "templates"

    copy_tree(templates / "docs", repo / "docs")
    copy_tree(templates / "ENGINEERING.md", repo / "docs" / "ENGINEERING.md")

    if args.bridges:
        copy_tree(templates / "bridges", repo)

    tools_dir = repo / "docs" / "tools" / "autopipeline"
    tools_dir.mkdir(parents=True, exist_ok=True)
    copy_tree(Path(__file__).resolve(), tools_dir / "ap.py")
    copy_tree(Path(__file__).resolve().parent / "core.py", tools_dir / "core.py")
    copy_tree(Path(__file__).resolve().parent / "http_checks.py", tools_dir / "http_checks.py")

    print(f"[install] OK: scaffold installed into {repo}")
    print("[install] Next: edit docs/ENGINEERING.md frontmatter, fill all platform credentials, and commit that file into Git.")


def cmd_upgrade(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    write = bool(args.write) and not bool(args.dry_run)
    source_root = _find_skill_asset_root(repo)
    templates = source_root / "data" / "templates"
    actions: list[dict] = []

    def add_action(kind: str, path: Path, action: str, detail: str = "") -> None:
        actions.append({
            "kind": kind,
            "path": _repo_rel(repo, path),
            "action": action,
            "detail": detail,
        })

    tool_files = [
        (source_root / "scripts" / "ap.py", repo / "docs" / "tools" / "autopipeline" / "ap.py"),
        (source_root / "scripts" / "core.py", repo / "docs" / "tools" / "autopipeline" / "core.py"),
        (source_root / "scripts" / "http_checks.py", repo / "docs" / "tools" / "autopipeline" / "http_checks.py"),
    ]
    for src, dst in tool_files:
        if not src.exists():
            continue
        if not dst.exists():
            add_action("tool", dst, "create")
            if write:
                copy_tree(src, dst)
        elif _files_differ(src, dst):
            add_action("tool", dst, "update")
            if write:
                copy_tree(src, dst)
        else:
            add_action("tool", dst, "ok")

    project_skill = repo / ".agents" / "skills" / "auto-coding-skill"
    if project_skill.exists():
        for src in _iter_files(source_root):
            if ".git" in src.parts:
                continue
            rel = src.relative_to(source_root)
            dst = project_skill / rel
            if not dst.exists():
                add_action("skill", dst, "create")
                if write:
                    copy_tree(src, dst)
            elif _files_differ(src, dst):
                add_action("skill", dst, "update")
                if write:
                    copy_tree(src, dst)
        for dst in _iter_files(project_skill):
            rel = dst.relative_to(project_skill)
            if not (source_root / rel).exists():
                add_action("skill", dst, "extra", "present only in project copy")
    else:
        add_action("skill", project_skill, "missing", "run autocoding init --ai codex --mode project --force")

    docs_template = templates / "docs"
    for src in _iter_files(docs_template):
        rel = src.relative_to(docs_template)
        dst = repo / "docs" / rel
        if not dst.exists():
            add_action("doc", dst, "create")
            if write:
                copy_tree(src, dst)
        elif _files_differ(src, dst) and str(rel).startswith(("architecture/", "reviews/optimization-backlog.md", "reviews/project-health-baseline.md")):
            add_action("doc", dst, "stale", "kept unchanged; review manually")
        else:
            add_action("doc", dst, "ok")

    engineering = repo / "docs" / "ENGINEERING.md"
    template_engineering = templates / "ENGINEERING.md"
    if engineering.exists() and template_engineering.exists():
        current_cfg, body = _read_frontmatter_markdown(engineering)
        template_cfg, _ = _read_frontmatter_markdown(template_engineering)
        merged_cfg = json.loads(json.dumps(current_cfg))
        added_keys = _deep_merge_missing(merged_cfg, template_cfg)
        if added_keys:
            add_action("config", engineering, "merge", ", ".join(added_keys))
            if write:
                _write_frontmatter_markdown(engineering, merged_cfg, body)
        else:
            add_action("config", engineering, "ok")
    elif template_engineering.exists():
        add_action("config", engineering, "create")
        if write:
            copy_tree(template_engineering, engineering)

    result = {
        "source_root": str(source_root),
        "mode": "write" if write else "dry-run",
        "actions": actions,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[upgrade] source={source_root}")
        print(f"[upgrade] mode={'write' if write else 'dry-run'}")
        for item in actions:
            if item["action"] == "ok":
                continue
            detail = f" - {item['detail']}" if item.get("detail") else ""
            print(f"[upgrade] {item['action']} {item['kind']}: {item['path']}{detail}")
        if not any(item["action"] != "ok" for item in actions):
            print("[upgrade] OK: no changes needed")
        elif not write:
            print("[upgrade] dry-run only; re-run with --write to apply safe updates")
    try:
        cfg = _load_cfg(repo)
    except Exception:
        cfg = {}
    if cfg and write:
        _record_evidence(repo, cfg, "upgrade", "pass", {"mode": result["mode"], "action_count": len(actions)})


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

    title = str(args.title or "").strip() or _infer_title(taskbook, task_id)
    date = _dt.date.today().isoformat()

    staged = run(["git", "diff", "--cached", "--name-only"], cwd=repo, check=False).stdout.strip()
    unstaged = run(["git", "diff", "--name-only"], cwd=repo, check=False).stdout.strip()
    status = run(["git", "status", "--porcelain=v1"], cwd=repo, check=False).stdout.strip()
    staged_block = "- " + staged.replace("\n", "\n- ") if staged else "- (none)"
    unstaged_block = "- " + unstaged.replace("\n", "\n- ") if unstaged else "- (none)"

    content = f"""# Task Summary — {task_id} — {title}

> 仅用于高风险、跨模块、阶段性里程碑、需要完整复盘的任务。

- Task ID：{task_id}
- Date：{date}
- Scope（本次范围）：TODO
- Out of scope（明确未做）：TODO

---

## 1. 目标与验收结论
- 目标：TODO
- 验收结论：PASS / FAIL — TODO

## 2. 变更概览
### Git change snapshot
- Staged files:
{staged_block}
- Unstaged files:
{unstaged_block}
- Status:
```text
{status}
```

## 3. 接口变更（以 API Markdown 为准）
- 变更记录位置：`{api_change_log}`

## 4. 质量证据
- 本地轻量校验：light_gate or quick_test/test/build / api docs / jenkins / diff-check — TODO
- 结构检查：structure-check — TODO
- 结构化证据：docs/tasks/evidence.jsonl — TODO
- 门禁画像：.local/auto-coding-skill/gate-profile.jsonl — TODO
- Jenkins Build：TODO
- 目标环境验证：TODO
- 闭环记录：TODO
- 回归矩阵（如有）：`{regression_matrix}`

## 5. 风险与回滚
- 风险：TODO
- 回滚：TODO

## 6. 后续行动
- TODO：TODO
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

    def evidence_missing(value: str) -> bool:
        stripped = value.strip()
        lower = stripped.lower()
        if not stripped:
            return True
        if stripped.startswith("<") and stripped.endswith(">"):
            return True
        placeholder_tokens = [
            "todo",
            "tbd",
            "pending",
            "replace-with",
            "paste log path",
            "paste evidence",
            "fill-with",
            "待补",
            "待填",
            "占位",
        ]
        return any(token in lower for token in placeholder_tokens)

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
            continue
        evidence = cols[7] if len(cols) > 7 else ""
        if evidence_missing(evidence):
            fail.append((rid, "PASS-without-evidence"))

    if rows == 0:
        raise APError(f"No regression rows found in matrix: {matrix}")

    if fail:
        msg = "\n".join([f"- {rid}: {st}" for rid, st in fail])
        raise APError(f"Regression matrix not 0-fail:\n{msg}")

    print("[check-matrix] OK (0-fail)")


def _load_cfg(repo: Path) -> dict:
    cfg_path = find_config(repo)
    return load_yaml(cfg_path)


def _candidate_skill_roots(repo: Path) -> list[Path]:
    return [
        _skill_root(),
        repo / ".agents" / "skills" / "auto-coding-skill",
        Path.home() / ".agents" / "skills" / "auto-coding-skill",
        repo / ".claude" / "skills" / "auto-coding-skill",
        Path.home() / ".claude" / "skills" / "auto-coding-skill",
    ]


def _find_skill_asset_root(repo: Path) -> Path:
    for root in _candidate_skill_roots(repo):
        if (root / "data" / "templates").exists() and (root / "scripts" / "ap.py").exists():
            return root
    raise APError(
        "Cannot find auto-coding-skill asset root. Run `autocoding init --ai codex --mode global --force` "
        "or execute this command from an installed skill copy."
    )


def _file_sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _files_differ(a: Path, b: Path) -> bool:
    return _file_sha256(a) != _file_sha256(b)


def _read_frontmatter_markdown(path: Path) -> tuple[dict, str]:
    if not path.exists():
        return {}, ""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*(\n|$)(.*)$", text, flags=re.DOTALL)
    if not m:
        raise APError(f"Markdown frontmatter not found: {path}")
    if yaml is None:
        raise APError("PyYAML not installed. Install dependencies with: pip install pyyaml requests")
    data = yaml.safe_load(m.group(1)) or {}
    return data, m.group(3)


def _write_frontmatter_markdown(path: Path, data: dict, body: str) -> None:
    if yaml is None:
        raise APError("PyYAML not installed. Install dependencies with: pip install pyyaml requests")
    dumped = yaml.safe_dump(data, allow_unicode=True, sort_keys=False).strip()
    path.write_text(f"---\n{dumped}\n---\n{body}", encoding="utf-8")


def _deep_merge_missing(target: dict, template: dict, prefix: str = "") -> list[str]:
    added: list[str] = []
    for key, value in template.items():
        field = f"{prefix}.{key}" if prefix else str(key)
        if key not in target or target.get(key) is None:
            target[key] = value
            added.append(field)
            continue
        if isinstance(target.get(key), dict) and isinstance(value, dict):
            added.extend(_deep_merge_missing(target[key], value, field))
    return added


def _iter_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    out: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts and path.name != ".DS_Store" and not path.name.endswith(".pyc"):
            out.append(path)
    return sorted(out)


def _workflow_mode(cfg: dict, args: Optional[argparse.Namespace] = None) -> str:
    explicit = str(getattr(args, "mode", "") or "").strip().lower() if args else ""
    configured = str(((cfg.get("workflow") or {}).get("mode")) or "dev").strip().lower()
    mode = explicit or configured or "dev"
    if mode not in {"dev", "verify"}:
        raise APError("workflow.mode must be 'dev' or 'verify'.")
    return mode


def _text(value: object) -> str:
    return str(value or "").strip()


def _is_placeholder(value: object) -> bool:
    raw = _text(value)
    upper = raw.upper()
    return (
        upper in _INVALID_PLACEHOLDERS
        or (raw.startswith("<") and raw.endswith(">"))
        or upper.startswith("REPLACE_")
        or upper.startswith("YOUR_")
    )


def _is_explicit_fill(value: object) -> bool:
    return bool(_text(value)) and not _is_placeholder(value)


def _validate_url_field(errors: List[str], field: str, value: object) -> None:
    if not _is_explicit_fill(value):
        return
    raw = _text(value)
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        errors.append(f"{field} must be a valid http/https URL")


def _validate_path_field(errors: List[str], field: str, value: object) -> None:
    if not _is_explicit_fill(value):
        return
    raw = _text(value)
    if not raw.startswith("/"):
        errors.append(f"{field} must start with '/'")


def _require_explicit_field(missing: List[str], field: str, value: object) -> None:
    raw = _text(value)
    if not _is_explicit_fill(raw):
        missing.append(f"{field} (must be explicitly filled, not blank/TODO)")


def _has_secret_reference(section_cfg: dict, field: str) -> bool:
    return _is_explicit_fill(section_cfg.get(field)) or _is_explicit_fill(section_cfg.get(f"{field}_env"))


def _require_secret_reference(missing: List[str], section_name: str, section_cfg: dict, field: str) -> None:
    if not _has_secret_reference(section_cfg, field):
        missing.append(
            f"{section_name}.{field} or {section_name}.{field}_env "
            "(must be explicitly filled, not blank/TODO)"
        )


def _resolve_secret(section_name: str, section_cfg: dict, field: str) -> str:
    direct_value = section_cfg.get(field)
    if _is_explicit_fill(direct_value):
        return _text(direct_value)

    env_field = f"{field}_env"
    env_name = _text(section_cfg.get(env_field))
    if _is_explicit_fill(env_name):
        env_value = os.environ.get(env_name, "")
        if _is_explicit_fill(env_value):
            return _text(env_value)
        raise APError(
            f"Missing secret value for {section_name}.{field}. "
            f"Set environment variable {env_name} declared by {section_name}.{env_field}, "
            f"or fill {section_name}.{field}."
        )

    raise APError(
        f"Missing {section_name}.{field}. Fill {section_name}.{field} "
        f"or declare {section_name}.{env_field}."
    )


_GATE_SCOPES = {"auto", "changed", "standard", "full"}
_DOC_PATH_PATTERNS = ["*.md", "docs/**"]
_DEFAULT_FULL_PATH_PATTERNS = [
    ".agents/**",
    ".claude/**",
    ".github/workflows/**",
    "Jenkinsfile",
    "Jenkinsfile.*",
    "Dockerfile",
    "**/Dockerfile",
    "docker-compose*.yml",
    "docker-compose*.yaml",
    "compose*.yml",
    "compose*.yaml",
    "docs/ENGINEERING.md",
    "docs/tools/autopipeline/**",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
    "go.mod",
    "go.sum",
    "Cargo.lock",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
]


def _gate_cfg(cfg: dict) -> dict:
    gate_cfg = cfg.get("gate") or {}
    return gate_cfg if isinstance(gate_cfg, dict) else {}


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _command_name(ref: object) -> str:
    raw = _text(ref)
    if raw.startswith("commands."):
        raw = raw.split(".", 1)[1]
    return raw


def _configured_command(cfg: dict, name: str) -> str:
    commands = cfg.get("commands") or {}
    return _text(commands.get(name))


def _run_first_configured_command(repo: Path, cfg: dict, names: list[str]) -> str:
    for name in names:
        command_name = _command_name(name)
        if command_name and _configured_command(cfg, command_name):
            _run_configured_command(repo, cfg, command_name)
            return command_name
    return ""


def _run_configured_command_list(repo: Path, cfg: dict, names: list) -> list[str]:
    executed: list[str] = []
    missing: list[str] = []
    for name_ref in names:
        name = _command_name(name_ref)
        if not name:
            continue
        if _configured_command(cfg, name):
            _run_configured_command(repo, cfg, name)
            executed.append(name)
        else:
            missing.append(name)
    if missing and not executed:
        raise APError("Gate rule references missing commands: " + ", ".join(missing))
    return executed


def _path_matches(path: str, patterns: list) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    for pattern_ref in patterns:
        pattern = _text(pattern_ref).replace("\\", "/").lstrip("./")
        if not pattern:
            continue
        if fnmatch.fnmatch(normalized, pattern):
            return True
        if "/" not in pattern and fnmatch.fnmatch(Path(normalized).name, pattern):
            return True
    return False


def _unique_paths(paths: list[str]) -> list[str]:
    seen = set()
    out = []
    for path in paths:
        normalized = path.replace("\\", "/").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return sorted(out)


def _git_lines(repo: Path, cmd: list[str]) -> list[str]:
    try:
        result = run(cmd, cwd=repo, check=False)
    except APError:
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _default_base_ref(repo: Path) -> str:
    upstream = _git_lines(repo, ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    return upstream[0] if upstream else ""


def _changed_files(repo: Path, base_ref: str = "") -> list[str]:
    paths: list[str] = []
    effective_base = base_ref or _default_base_ref(repo)
    if effective_base:
        paths.extend(_git_lines(repo, ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", f"{effective_base}...HEAD"]))
    paths.extend(_git_lines(repo, ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB"]))
    paths.extend(_git_lines(repo, ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMRTUXB"]))
    paths.extend(_git_lines(repo, ["git", "ls-files", "--others", "--exclude-standard"]))
    return _unique_paths(paths)


def _docs_only(paths: list[str]) -> bool:
    return bool(paths) and all(_path_matches(path, _DOC_PATH_PATTERNS) for path in paths)


def _gate_rules(gate_cfg: dict) -> list[dict]:
    rules = gate_cfg.get("rules") or []
    return [rule for rule in rules if isinstance(rule, dict)]


def _matching_gate_rules(paths: list[str], gate_cfg: dict) -> list[dict]:
    matches = []
    for rule in _gate_rules(gate_cfg):
        patterns = _as_list(rule.get("paths"))
        if patterns and any(_path_matches(path, patterns) for path in paths):
            matches.append(rule)
    return matches


def _gate_full_patterns(gate_cfg: dict) -> list:
    full_on = gate_cfg.get("full_on") or {}
    patterns = list(_DEFAULT_FULL_PATH_PATTERNS)
    if isinstance(full_on, dict):
        patterns.extend(_as_list(full_on.get("paths")))
    else:
        patterns.extend(_as_list(full_on))
    return patterns


def _has_changed_gate(cfg: dict, gate_cfg: dict, paths: list[str]) -> bool:
    if _configured_command(cfg, "gate_changed"):
        return True
    for rule in _matching_gate_rules(paths, gate_cfg):
        if _as_list(rule.get("commands")):
            return True
    return False


def _select_gate_scope(cfg: dict, requested_scope: str, paths: list[str]) -> tuple[str, list[str], list[dict]]:
    gate_cfg = _gate_cfg(cfg)
    scope = (requested_scope or _text(gate_cfg.get("default_scope")) or "standard").lower()
    if scope not in _GATE_SCOPES:
        raise APError("gate scope must be one of: " + ", ".join(sorted(_GATE_SCOPES)))

    matching_rules = _matching_gate_rules(paths, gate_cfg)
    reasons: list[str] = []

    if scope != "auto":
        return scope, [f"requested scope: {scope}"], matching_rules

    if not paths:
        fallback = _text(gate_cfg.get("no_change_scope")) or "standard"
        if fallback not in {"changed", "standard", "full"}:
            fallback = "standard"
        return fallback, ["no changed files detected"], matching_rules

    rule_scopes = {_text(rule.get("scope")).lower() for rule in matching_rules if _text(rule.get("scope"))}
    if "full" in rule_scopes:
        return "full", ["matched gate rule with scope=full"], matching_rules
    if "standard" in rule_scopes:
        return "standard", ["matched gate rule with scope=standard"], matching_rules

    if any(_path_matches(path, _gate_full_patterns(gate_cfg)) for path in paths):
        return "full", ["changed files match full-gate patterns"], matching_rules

    if _docs_only(paths):
        return "changed", ["docs-only change"], matching_rules

    if _has_changed_gate(cfg, gate_cfg, paths):
        return "changed", ["matched changed-gate command or rule"], matching_rules

    fallback = _text(gate_cfg.get("fallback_scope")) or "standard"
    if fallback not in {"changed", "standard", "full"}:
        fallback = "standard"
    if fallback == "changed" and _text(gate_cfg.get("full_on_unknown")).lower() in {"1", "true", "yes", "on"}:
        fallback = "full"
    reasons.append("no changed-gate command/rule matched")
    return fallback, reasons, matching_rules


def _impact_summary(cfg: dict, repo: Path, requested_scope: str, base_ref: str = "") -> dict:
    paths = _changed_files(repo, base_ref=base_ref)
    scope, reasons, matching_rules = _select_gate_scope(cfg, requested_scope, paths)
    return {
        "requested_scope": requested_scope or _text(_gate_cfg(cfg).get("default_scope")) or "standard",
        "selected_scope": scope,
        "reasons": reasons,
        "changed_files": paths,
        "matched_rules": [_text(rule.get("name")) or "(unnamed)" for rule in matching_rules],
    }


def _print_impact(summary: dict, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    print(f"[impact] requested_scope={summary['requested_scope']}")
    print(f"[impact] selected_scope={summary['selected_scope']}")
    for reason in summary.get("reasons") or []:
        print(f"[impact] reason: {reason}")
    for rule in summary.get("matched_rules") or []:
        print(f"[impact] matched_rule: {rule}")
    files = summary.get("changed_files") or []
    if files:
        for path in files:
            print(f"[impact] changed: {path}")
    else:
        print("[impact] changed: (none)")


def _run_changed_gate(repo: Path, cfg: dict, paths: list[str], matching_rules: list[dict]) -> list[str]:
    executed: list[str] = []
    for rule in matching_rules:
        executed.extend(_run_configured_command_list(repo, cfg, _as_list(rule.get("commands"))))
    if executed:
        return executed

    fallback_commands = ["gate_changed"]
    if _docs_only(paths):
        fallback_commands.append("docs_check")
    command = _run_first_configured_command(repo, cfg, fallback_commands)
    if command:
        return [command]

    if _docs_only(paths):
        print("[gate] docs-only change with no changed-gate command configured; running built-in post checks only.")
        return ["docs_only_builtin"]

    fallback = _run_first_configured_command(repo, cfg, ["quick_test", "test", "build"])
    if fallback:
        return [fallback]

    raise APError(
        "Changed gate has no configured command. Add commands.gate_changed or matching gate.rules commands, "
        "or run light-gate --scope standard/full."
    )


def _run_standard_gate(repo: Path, cfg: dict) -> list[str]:
    command = _run_first_configured_command(repo, cfg, ["gate_standard", "light_gate", "quick_test", "test", "build"])
    if not command:
        raise APError(
            "Standard gate is under-configured. Add commands.gate_standard, commands.light_gate, "
            "commands.quick_test, commands.test, or commands.build."
        )
    return [command]


def _run_full_gate(repo: Path, cfg: dict) -> list[str]:
    command = _run_first_configured_command(repo, cfg, ["gate_full", "full_gate", "gate_standard", "light_gate", "test", "build"])
    if not command:
        raise APError(
            "Full gate is under-configured. Add commands.gate_full, commands.full_gate, commands.test, "
            "commands.build, or commands.light_gate."
        )
    return [command]


def _run_git_diff_check(repo: Path, cfg: dict) -> None:
    print("[diff-check] git diff --check")
    start = time.time()
    run(["git", "diff", "--check"], cwd=repo)
    _record_gate_profile(repo, cfg, "diff_check", "pass", time.time() - start)
    _record_evidence(repo, cfg, "diff_check", "pass")
    print("[diff-check] OK")


_DEFAULT_STRUCTURE_ALLOW_PATTERNS = [
    ".git/**",
    ".agents/skills/**",
    ".claude/skills/**",
    ".next/**",
    ".nuxt/**",
    ".svelte-kit/**",
    ".turbo/**",
    "coverage/**",
    "dist/**",
    "build/**",
    "out/**",
    "target/**",
    "vendor/**",
    "node_modules/**",
    "generated/**",
    "**/generated/**",
    "**/__generated__/**",
    "docs/tools/autopipeline/**",
    "**/*.generated.*",
    "**/*.gen.*",
    "**/*.min.js",
    "**/*.bundle.js",
    "**/*.map",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
    "go.sum",
    "Cargo.lock",
]
_TEXT_SOURCE_EXTENSIONS = {
    ".bash",
    ".c",
    ".cc",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".gradle",
    ".graphql",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".kts",
    ".less",
    ".m",
    ".md",
    ".mm",
    ".php",
    ".properties",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".scss",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
    ".zsh",
}
_TEXT_SOURCE_FILENAMES = {
    "Dockerfile",
    "Jenkinsfile",
    "Makefile",
    "go.mod",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "tsconfig.json",
}
_FUNCTION_START_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:def|function|func)\s+[A-Za-z_][\w]*\b"
    r"|^\s*(?:public|private|protected|static|final|async|\s)+\s*[\w<>\[\], ?]+\s+[A-Za-z_]\w*\s*\([^;]*\)\s*\{"
    r"|^\s*(?:export\s+)?(?:const|let|var)\s+[A-Za-z_]\w*\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"
)
_IMPORT_PATTERNS = [
    re.compile(r"^\s*import\s+(?:.+?\s+from\s+)?[\"']([^\"']+)[\"']"),
    re.compile(r"\brequire\(\s*[\"']([^\"']+)[\"']\s*\)"),
    re.compile(r"\bimport\(\s*[\"']([^\"']+)[\"']\s*\)"),
    re.compile(r"^\s*from\s+([A-Za-z_][\w.]*)\s+import\b"),
    re.compile(r"^\s*import\s+([A-Za-z_][\w.]*)(?:\s+as\s+\w+)?\s*$"),
    re.compile(r"^\s*import\s+[\"']([^\"']+)[\"']\s*$"),
    re.compile(r"^\s*[\"']([^\"']+/[^\"']*)[\"']\s*$"),
]
_DEFAULT_LAYER_RULES = {
    "enabled": True,
    "block": True,
    "rules": [
        {
            "name": "domain",
            "paths": ["**/domain/**", "**/domains/**", "**/model/**", "**/models/**"],
            "forbidden_imports": [
                "**/infrastructure/**",
                "**/infra/**",
                "**/adapter/**",
                "**/repository/**",
                "**/repositories/**",
                "**/client/**",
                "**/clients/**",
                "**/controller/**",
                "**/handler/**",
                "**/page/**",
                "**/pages/**",
                "**/component/**",
                "**/components/**",
                "**/view/**",
                "**/views/**",
            ],
        },
        {
            "name": "application",
            "paths": ["**/application/**", "**/service/**", "**/services/**", "**/usecase/**", "**/usecases/**"],
            "forbidden_imports": [
                "**/controller/**",
                "**/handler/**",
                "**/page/**",
                "**/pages/**",
                "**/component/**",
                "**/components/**",
                "**/view/**",
                "**/views/**",
            ],
        },
        {
            "name": "shared",
            "paths": ["**/shared/**", "**/common/**", "**/utils/**", "**/lib/**"],
            "forbidden_imports": [
                "**/domain/**",
                "**/application/**",
                "**/service/**",
                "**/services/**",
                "**/infrastructure/**",
                "**/controller/**",
                "**/page/**",
                "**/pages/**",
            ],
        },
    ],
}


def _structure_cfg(cfg: dict) -> dict:
    value = cfg.get("structure") or {}
    return value if isinstance(value, dict) else {}


def _optimization_cfg(cfg: dict) -> dict:
    value = cfg.get("optimization") or {}
    return value if isinstance(value, dict) else {}


def _bool_config(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raw = _text(value).lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _int_config(value: object, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _tracked_files(repo: Path) -> list[str]:
    return _unique_paths(_git_lines(repo, ["git", "ls-files"]))


def _structure_allow_patterns(structure_cfg: dict) -> list:
    patterns = list(_DEFAULT_STRUCTURE_ALLOW_PATTERNS)
    patterns.extend(_as_list(structure_cfg.get("allow_large_files")))
    patterns.extend(_as_list(structure_cfg.get("exclude")))
    return patterns


def _structure_accepted_debt_patterns(structure_cfg: dict) -> list:
    return _as_list(structure_cfg.get("accepted_debt_paths"))


def _is_structure_accepted_debt(path: str, structure_cfg: dict) -> bool:
    return _path_matches(path, _structure_accepted_debt_patterns(structure_cfg))


def _is_structure_candidate(path: str, structure_cfg: dict) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    if _path_matches(normalized, _structure_allow_patterns(structure_cfg)):
        return False
    name = Path(normalized).name
    suffix = Path(normalized).suffix.lower()
    return suffix in _TEXT_SOURCE_EXTENSIONS or name in _TEXT_SOURCE_FILENAMES


def _structure_paths_for_scope(repo: Path, scope: str, base_ref: str, structure_cfg: dict) -> list[str]:
    if scope == "full":
        paths = _tracked_files(repo)
    else:
        paths = _changed_files(repo, base_ref=base_ref)
    return [path for path in paths if _is_structure_candidate(path, structure_cfg)]


def _read_text_lines(repo: Path, path: str) -> Optional[list[str]]:
    file_path = repo / path
    if not file_path.exists() or not file_path.is_file():
        return None
    try:
        return file_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return None
    except OSError:
        return None


def _parse_numstat_line(line: str) -> tuple[str, int]:
    parts = line.split("\t", 2)
    if len(parts) < 3:
        return "", 0
    added_raw, _, path = parts
    if added_raw == "-":
        return "", 0
    try:
        added = int(added_raw)
    except ValueError:
        return "", 0
    return path.replace("\\", "/").strip(), added


def _added_lines_by_path(repo: Path, base_ref: str = "") -> dict[str, int]:
    added: dict[str, int] = {}
    commands: list[list[str]] = []
    effective_base = base_ref or _default_base_ref(repo)
    if effective_base:
        commands.append(["git", "diff", "--numstat", f"{effective_base}...HEAD"])
    commands.extend([
        ["git", "diff", "--numstat"],
        ["git", "diff", "--cached", "--numstat"],
    ])

    for cmd in commands:
        for line in _git_lines(repo, cmd):
            path, count = _parse_numstat_line(line)
            if path:
                added[path] = added.get(path, 0) + count

    for path in _git_lines(repo, ["git", "ls-files", "--others", "--exclude-standard"]):
        lines = _read_text_lines(repo, path)
        if lines is not None:
            added[path] = added.get(path, 0) + len(lines)
    return added


def _function_size_warnings(path: str, lines: list[str], threshold: int) -> list[str]:
    if threshold <= 0:
        return []
    starts: list[int] = []
    for index, line in enumerate(lines):
        if _FUNCTION_START_RE.search(line):
            starts.append(index)
    warnings: list[str] = []
    for pos, start in enumerate(starts):
        end = starts[pos + 1] if pos + 1 < len(starts) else len(lines)
        size = end - start
        if size > threshold:
            warnings.append(f"{path}:{start + 1} function-like block has {size} lines (warn>{threshold})")
    return warnings


def _layer_rules_config(structure_cfg: dict) -> dict:
    raw = structure_cfg.get("layer_rules")
    if not isinstance(raw, dict):
        return dict(_DEFAULT_LAYER_RULES)
    merged = dict(_DEFAULT_LAYER_RULES)
    merged.update(raw)
    if "rules" not in raw:
        merged["rules"] = _DEFAULT_LAYER_RULES["rules"]
    return merged


def _extract_import_targets(path: str, lines: list[str]) -> list[tuple[int, str]]:
    suffix = Path(path).suffix.lower()
    if suffix not in {".py", ".js", ".jsx", ".ts", ".tsx", ".vue", ".go", ".java", ".kt", ".kts", ".rs", ".swift"}:
        return []
    targets: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//", "*")):
            continue
        for pattern in _IMPORT_PATTERNS:
            match = pattern.search(line)
            if match:
                targets.append((index + 1, match.group(1).strip()))
                break
    return targets


def _resolve_relative_import(source_path: str, target: str) -> str:
    normalized = target.replace("\\", "/")
    if not normalized.startswith("."):
        return normalized
    source_dir = Path(source_path).parent
    parts = []
    for part in (source_dir / normalized).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _import_matches_pattern(target: str, pattern: str) -> bool:
    normalized = target.replace("\\", "/").lstrip("./")
    dotted_as_path = normalized.replace(".", "/")
    pat = pattern.replace("\\", "/").lstrip("./")
    if _path_matches(normalized, [pat]) or _path_matches(dotted_as_path, [pat]):
        return True
    marker = pat.replace("**/", "").replace("/**", "").strip("/")
    if marker and (f"/{marker}/" in f"/{normalized}/" or f"/{marker}/" in f"/{dotted_as_path}/"):
        return True
    return False


def _structure_boundary_issues(path: str, lines: list[str], structure_cfg: dict) -> list[str]:
    layer_cfg = _layer_rules_config(structure_cfg)
    if not _bool_config(layer_cfg.get("enabled"), True):
        return []
    rules = [rule for rule in _as_list(layer_cfg.get("rules")) if isinstance(rule, dict)]
    if not rules:
        return []
    matching_rules = [rule for rule in rules if _path_matches(path, _as_list(rule.get("paths")))]
    if not matching_rules:
        return []
    imports = _extract_import_targets(path, lines)
    issues: list[str] = []
    for rule in matching_rules:
        name = _text(rule.get("name")) or "layer"
        forbidden = _as_list(rule.get("forbidden_imports"))
        for line_no, target in imports:
            resolved = _resolve_relative_import(path, target)
            if any(_import_matches_pattern(target, pattern) or _import_matches_pattern(resolved, pattern) for pattern in forbidden):
                issues.append(f"{path}:{line_no} layer '{name}' imports forbidden target '{target}'")
    return issues


def _configured_structure_docs(cfg: dict) -> dict[str, str]:
    docs_cfg = cfg.get("docs") or {}
    return {
        "docs.health_baseline": _text(docs_cfg.get("health_baseline")),
        "docs.optimization_backlog": _text(docs_cfg.get("optimization_backlog")),
        "docs.structure_standard": _text(docs_cfg.get("structure_standard")),
    }


def _docs_cfg(cfg: dict) -> dict:
    value = cfg.get("docs") or {}
    return value if isinstance(value, dict) else {}


def _docs_ledger_paths(repo: Path, cfg: dict) -> tuple[dict, dict[str, Path]]:
    docs_cfg = _docs_cfg(cfg)
    return docs_cfg, {
        "taskbook": Path(repo, _text(docs_cfg.get("taskbook")) or "docs/tasks/taskbook.md"),
        "closure_log": Path(repo, _text(docs_cfg.get("closure_log")) or "docs/tasks/closure-log.md"),
        "design_dir": Path(repo, _text(docs_cfg.get("design_dir")) or "docs/design"),
        "task_archive_dir": Path(repo, _text(docs_cfg.get("task_archive_dir")) or "docs/tasks/archives"),
        "design_archive_dir": Path(repo, _text(docs_cfg.get("design_archive_dir")) or "docs/archive/design"),
        "archive_index": Path(repo, _text(docs_cfg.get("archive_index")) or "docs/tasks/archive-index.md"),
    }


def _count_lines(path: Path) -> Optional[int]:
    if not path.exists() or not path.is_file():
        return None
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except UnicodeDecodeError:
        return None
    except OSError:
        return None


def _count_files(root: Path, pattern: str, recursive: bool = True) -> int:
    if not root.exists() or not root.is_dir():
        return 0
    iterator = root.rglob(pattern) if recursive else root.glob(pattern)
    return sum(1 for path in iterator if path.is_file())


def _ledger_message(blocking: list[str], warnings: list[str], block: bool, message: str) -> None:
    if block:
        blocking.append(message)
    else:
        warnings.append(message)


def _docs_ledger_check_result(repo: Path, cfg: dict) -> dict:
    docs_cfg, paths = _docs_ledger_paths(repo, cfg)
    enabled = _bool_config(docs_cfg.get("ledger_check_enabled"), True)
    block_on_exceed = _bool_config(docs_cfg.get("ledger_block_on_exceed"), True)

    taskbook = paths["taskbook"]
    closure_log = paths["closure_log"]
    design_dir = paths["design_dir"]
    task_archive_dir = paths["task_archive_dir"]
    design_archive_dir = paths["design_archive_dir"]
    archive_index = paths["archive_index"]

    taskbook_max = _int_config(docs_cfg.get("active_taskbook_max_lines"), 1200)
    closure_max = _int_config(docs_cfg.get("active_closure_log_max_lines"), 800)
    design_max = _int_config(docs_cfg.get("active_design_max_files"), 120)

    taskbook_lines = _count_lines(taskbook)
    closure_lines = _count_lines(closure_log)
    active_design_files = _count_files(design_dir, "T*.md", recursive=False)
    task_archive_files = _count_files(task_archive_dir, "*.md", recursive=True)
    design_archive_files = _count_files(design_archive_dir, "T*.md", recursive=True)
    archive_index_exists = archive_index.exists()

    blocking: list[str] = []
    warnings: list[str] = []
    exceeded: list[str] = []

    if not enabled:
        return {
            "enabled": False,
            "blocking": blocking,
            "warnings": warnings,
        }

    if taskbook_lines is None:
        blocking.append(f"docs.taskbook missing or unreadable: {_repo_rel(repo, taskbook)}")
    if closure_lines is None:
        blocking.append(f"docs.closure_log missing or unreadable: {_repo_rel(repo, closure_log)}")
    if not design_dir.exists() or not design_dir.is_dir():
        blocking.append(f"docs.design_dir missing on disk: {_repo_rel(repo, design_dir)}")

    if taskbook_lines is not None and taskbook_max > 0 and taskbook_lines > taskbook_max:
        exceeded.append("taskbook")
        _ledger_message(
            blocking,
            warnings,
            block_on_exceed,
            f"docs.taskbook has {taskbook_lines} lines (max {taskbook_max}); "
            f"physically archive closed tasks under {_repo_rel(repo, task_archive_dir)} instead of keeping an index-only ledger",
        )
        if task_archive_files == 0:
            _ledger_message(
                blocking,
                warnings,
                block_on_exceed,
                f"docs.taskbook exceeds the active ledger budget but docs.task_archive_dir has no archive files: {_repo_rel(repo, task_archive_dir)}",
            )

    if closure_lines is not None and closure_max > 0 and closure_lines > closure_max:
        exceeded.append("closure_log")
        _ledger_message(
            blocking,
            warnings,
            block_on_exceed,
            f"docs.closure_log has {closure_lines} lines (max {closure_max}); "
            f"physically archive historical closure entries under {_repo_rel(repo, task_archive_dir)}",
        )
        if task_archive_files == 0:
            _ledger_message(
                blocking,
                warnings,
                block_on_exceed,
                f"docs.closure_log exceeds the active ledger budget but docs.task_archive_dir has no archive files: {_repo_rel(repo, task_archive_dir)}",
            )

    if design_max > 0 and active_design_files > design_max:
        exceeded.append("design_dir")
        _ledger_message(
            blocking,
            warnings,
            block_on_exceed,
            f"docs.design_dir has {active_design_files} top-level T*.md files (max {design_max}); "
            f"move historical DD files under {_repo_rel(repo, design_archive_dir)}",
        )
        if design_archive_files == 0:
            _ledger_message(
                blocking,
                warnings,
                block_on_exceed,
                f"docs.design_dir exceeds the active DD budget but docs.design_archive_dir has no archived T*.md files: {_repo_rel(repo, design_archive_dir)}",
            )

    if exceeded and archive_index_exists and task_archive_files == 0 and design_archive_files == 0:
        _ledger_message(
            blocking,
            warnings,
            block_on_exceed,
            f"{_repo_rel(repo, archive_index)} exists, but no physical docs archives were found; "
            "archive indexes are navigation aids and do not satisfy active-ledger slimming",
        )

    return {
        "enabled": True,
        "limits": {
            "active_taskbook_max_lines": taskbook_max,
            "active_closure_log_max_lines": closure_max,
            "active_design_max_files": design_max,
        },
        "paths": {
            "taskbook": _repo_rel(repo, taskbook),
            "closure_log": _repo_rel(repo, closure_log),
            "design_dir": _repo_rel(repo, design_dir),
            "task_archive_dir": _repo_rel(repo, task_archive_dir),
            "design_archive_dir": _repo_rel(repo, design_archive_dir),
            "archive_index": _repo_rel(repo, archive_index),
        },
        "counts": {
            "taskbook_lines": taskbook_lines,
            "closure_log_lines": closure_lines,
            "active_design_files": active_design_files,
            "task_archive_files": task_archive_files,
            "design_archive_files": design_archive_files,
            "archive_index_exists": archive_index_exists,
        },
        "exceeded": exceeded,
        "blocking": blocking,
        "warnings": warnings,
    }


_TASKBOOK_ARCHIVE_HEADING_RE = re.compile(r"^##\s+Task\s+([A-Za-z][A-Za-z0-9]*\d+(?:-\d+)?)\b")
_CLOSURE_ARCHIVE_HEADING_RE = re.compile(r"^##\s+([A-Za-z][A-Za-z0-9]*\d+(?:-\d+)?)\b")
_TASK_RESULT_RE = re.compile(r"(?:^|\n)\s*-\s*Result\s*[:：]\s*(DEV-CLOSED|PASS|FAIL|PARTIAL)\b", re.IGNORECASE)
_TASK_STATUS_RE = re.compile(r"(?:^|\n)\s*-\s*(?:状态|Status)\s*[:：]\s*([^|\n]+)", re.IGNORECASE)
_DESIGN_TASK_FILE_RE = re.compile(r"^([Tt][A-Za-z0-9]*\d+(?:-\d+)?)")
_CLOSED_TASK_STATUSES = {
    "done",
    "closed",
    "dev-closed",
    "pass",
    "passed",
    "fail",
    "failed",
    "partial",
    "完成",
    "已完成",
    "关闭",
    "已关闭",
}


def _normalize_task_id(task_id: str) -> str:
    return str(task_id or "").strip().upper()


def _resolve_archive_period(period: str) -> str:
    value = str(period or "").strip()
    if not value:
        return _dt.date.today().strftime("%Y-%m")
    if not re.fullmatch(r"\d{4}-\d{2}", value):
        raise APError("--period must use YYYY-MM")
    month = int(value.split("-", 1)[1])
    if month < 1 or month > 12:
        raise APError("--period month must be between 01 and 12")
    return value


def _split_markdown_sections(text: str, heading_re: re.Pattern[str]) -> tuple[list[str], list[dict]]:
    preamble: list[str] = []
    sections: list[dict] = []
    current: Optional[dict] = None

    for line in text.splitlines():
        match = heading_re.match(line.strip())
        if match:
            if current is not None:
                sections.append(current)
            current = {"id": match.group(1), "lines": [line]}
            continue
        if current is None:
            preamble.append(line)
        else:
            current["lines"].append(line)

    if current is not None:
        sections.append(current)
    return preamble, sections


def _section_text(section: dict) -> str:
    lines = section.get("lines") or []
    return "\n".join(str(line) for line in lines).rstrip() + "\n"


def _render_markdown_doc(preamble: list[str], sections: list[dict]) -> str:
    parts: list[str] = []
    preamble_text = "\n".join(preamble).rstrip()
    if preamble_text:
        parts.append(preamble_text)
    for section in sections:
        text = _section_text(section).rstrip()
        if text:
            parts.append(text)
    return "\n\n".join(parts).rstrip() + "\n"


def _is_closed_task_section(section: dict) -> bool:
    text = _section_text(section)
    if _TASK_RESULT_RE.search(text):
        return True
    status_match = _TASK_STATUS_RE.search(text)
    if not status_match:
        return False
    status = status_match.group(1).strip()
    status = re.split(r"[\s/，,;；。]+", status, maxsplit=1)[0].strip().lower()
    return status in _CLOSED_TASK_STATUSES


def _append_archive_sections(path: Path, title: str, period: str, sections: list[dict]) -> bool:
    if not sections:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    header = f"# {title} — {period}\n\n"
    body = "\n\n".join(_section_text(section).rstrip() for section in sections).rstrip() + "\n"
    if existing.strip():
        path.write_text(existing.rstrip() + "\n\n" + body, encoding="utf-8")
    else:
        path.write_text(header + body, encoding="utf-8")
    return True


def _append_archive_index(repo: Path, archive_index: Path, period: str, result: dict) -> bool:
    counts = result.get("counts") or {}
    if not any(int(counts.get(key) or 0) for key in ["taskbook_sections", "closure_sections", "design_files"]):
        return False

    paths = result.get("paths") or {}
    entry = (
        f"## {period}\n"
        f"- Generated: {_now_iso()}\n"
        f"- Taskbook archive: `{paths.get('taskbook_archive', '')}` ({counts.get('taskbook_sections', 0)} sections)\n"
        f"- Closure archive: `{paths.get('closure_archive', '')}` ({counts.get('closure_sections', 0)} sections)\n"
        f"- Design archive: `{paths.get('design_archive_dir', '')}` ({counts.get('design_files', 0)} files)\n"
    )
    archive_index.parent.mkdir(parents=True, exist_ok=True)
    existing = archive_index.read_text(encoding="utf-8") if archive_index.exists() else ""
    if existing.strip():
        archive_index.write_text(existing.rstrip() + "\n\n" + entry, encoding="utf-8")
    else:
        archive_index.write_text("# Docs Archive Index\n\n" + entry, encoding="utf-8")
    return True


def _plan_docs_ledger_archive(repo: Path, cfg: dict, period: str) -> dict:
    _docs_cfg_value, paths = _docs_ledger_paths(repo, cfg)
    taskbook = paths["taskbook"]
    closure_log = paths["closure_log"]
    design_dir = paths["design_dir"]
    task_archive_dir = paths["task_archive_dir"] / period
    design_archive_dir = paths["design_archive_dir"] / period
    taskbook_archive = task_archive_dir / "taskbook.md"
    closure_archive = task_archive_dir / "closure-log.md"

    if not taskbook.exists() or not taskbook.is_file():
        raise APError(f"docs.taskbook missing on disk: {_repo_rel(repo, taskbook)}")
    if not closure_log.exists() or not closure_log.is_file():
        raise APError(f"docs.closure_log missing on disk: {_repo_rel(repo, closure_log)}")

    taskbook_preamble, taskbook_sections = _split_markdown_sections(
        taskbook.read_text(encoding="utf-8"),
        _TASKBOOK_ARCHIVE_HEADING_RE,
    )
    closure_preamble, closure_sections = _split_markdown_sections(
        closure_log.read_text(encoding="utf-8"),
        _CLOSURE_ARCHIVE_HEADING_RE,
    )

    closed_taskbook_sections = [section for section in taskbook_sections if _is_closed_task_section(section)]
    active_taskbook_sections = [section for section in taskbook_sections if not _is_closed_task_section(section)]
    closure_ids = {_normalize_task_id(section["id"]) for section in closure_sections}
    closed_task_ids = {_normalize_task_id(section["id"]) for section in closed_taskbook_sections}
    archived_task_ids = closed_task_ids | closure_ids

    design_files: list[Path] = []
    if design_dir.exists() and design_dir.is_dir():
        for path in sorted(design_dir.glob("T*.md")):
            match = _DESIGN_TASK_FILE_RE.match(path.name)
            if match and _normalize_task_id(match.group(1)) in archived_task_ids:
                design_files.append(path)

    return {
        "enabled": True,
        "period": period,
        "paths": {
            "taskbook": _repo_rel(repo, taskbook),
            "closure_log": _repo_rel(repo, closure_log),
            "design_dir": _repo_rel(repo, design_dir),
            "taskbook_archive": _repo_rel(repo, taskbook_archive),
            "closure_archive": _repo_rel(repo, closure_archive),
            "design_archive_dir": _repo_rel(repo, design_archive_dir),
            "archive_index": _repo_rel(repo, paths["archive_index"]),
        },
        "counts": {
            "taskbook_sections": len(closed_taskbook_sections),
            "closure_sections": len(closure_sections),
            "design_files": len(design_files),
            "active_taskbook_sections_after": len(active_taskbook_sections),
        },
        "archived_task_ids": sorted(archived_task_ids),
        "taskbook_preamble": taskbook_preamble,
        "active_taskbook_sections": active_taskbook_sections,
        "closed_taskbook_sections": closed_taskbook_sections,
        "closure_preamble": closure_preamble,
        "closure_sections": closure_sections,
        "design_files": design_files,
        "archive_index": paths["archive_index"],
        "taskbook_archive": taskbook_archive,
        "closure_archive": closure_archive,
        "design_archive_dir": design_archive_dir,
        "taskbook_path": taskbook,
        "closure_log_path": closure_log,
    }


def _public_docs_ledger_archive_result(repo: Path, result: dict, mode: str, wrote: bool, index_updated: bool = False) -> dict:
    return {
        "enabled": result.get("enabled", True),
        "mode": mode,
        "wrote": wrote,
        "archive_index_updated": index_updated,
        "period": result.get("period"),
        "paths": result.get("paths"),
        "counts": result.get("counts"),
        "archived_task_ids": result.get("archived_task_ids"),
        "design_files": [_repo_rel(repo, path) if isinstance(path, Path) else str(path) for path in result.get("design_files", [])],
    }


def cmd_docs_ledger_archive(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    period = _resolve_archive_period(getattr(args, "period", ""))
    plan = _plan_docs_ledger_archive(repo, cfg, period)
    write = bool(getattr(args, "write", False))
    index_updated = False

    if write:
        design_archive_dir: Path = plan["design_archive_dir"]
        for src in plan["design_files"]:
            dst = design_archive_dir / src.name
            if dst.exists():
                raise APError(f"archive destination already exists: {_repo_rel(repo, dst)}")

        taskbook_path: Path = plan["taskbook_path"]
        closure_log_path: Path = plan["closure_log_path"]
        taskbook_path.write_text(_render_markdown_doc(plan["taskbook_preamble"], plan["active_taskbook_sections"]), encoding="utf-8")
        closure_log_path.write_text(_render_markdown_doc(plan["closure_preamble"], []), encoding="utf-8")
        _append_archive_sections(plan["taskbook_archive"], "Taskbook Archive", period, plan["closed_taskbook_sections"])
        _append_archive_sections(plan["closure_archive"], "Closure Log Archive", period, plan["closure_sections"])

        for src in plan["design_files"]:
            dst = design_archive_dir / src.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.replace(dst)
        index_updated = _append_archive_index(repo, plan["archive_index"], period, _public_docs_ledger_archive_result(repo, plan, "write", True))

    public_result = _public_docs_ledger_archive_result(repo, plan, "write" if write else "plan", write, index_updated=index_updated)
    if getattr(args, "json", False):
        print(json.dumps(public_result, ensure_ascii=False, indent=2))
    else:
        counts = public_result.get("counts") or {}
        print(
            "[docs-ledger-archive] "
            f"mode={public_result['mode']} period={period} "
            f"taskbook_sections={counts.get('taskbook_sections', 0)} "
            f"closure_sections={counts.get('closure_sections', 0)} "
            f"design_files={counts.get('design_files', 0)}"
        )
        if not write:
            print("[docs-ledger-archive] plan only; re-run with --write to apply")
        elif not any(int(counts.get(key) or 0) for key in ["taskbook_sections", "closure_sections", "design_files"]):
            print("[docs-ledger-archive] no closed ledger content to archive")
        else:
            print("[docs-ledger-archive] OK")

    if write:
        _record_evidence(repo, cfg, "docs_ledger_archive", "pass", public_result)


def cmd_docs_ledger_check(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    result = _docs_ledger_check_result(repo, cfg)
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if not result.get("enabled", True):
            print("[docs-ledger-check] disabled")
        else:
            counts = result.get("counts") or {}
            print(
                "[docs-ledger-check] "
                f"taskbook_lines={counts.get('taskbook_lines')} "
                f"closure_log_lines={counts.get('closure_log_lines')} "
                f"active_design_files={counts.get('active_design_files')} "
                f"task_archive_files={counts.get('task_archive_files')} "
                f"design_archive_files={counts.get('design_archive_files')}"
            )
            _print_limited("[docs-ledger-check] blocking", result.get("blocking") or [])
            _print_limited("[docs-ledger-check] warnings", result.get("warnings") or [])

    if result.get("blocking"):
        _record_evidence(repo, cfg, "docs_ledger_check", "fail", result)
        raise APError(f"docs-ledger-check failed with {len(result['blocking'])} blocking issue(s)")

    _record_evidence(repo, cfg, "docs_ledger_check", "pass", result)
    if not getattr(args, "json", False) and result.get("enabled", True):
        print("[docs-ledger-check] OK")


def _structure_gate_enabled(cfg: dict) -> bool:
    structure_cfg = cfg.get("structure")
    if isinstance(structure_cfg, dict) and not _bool_config(structure_cfg.get("enabled"), default=True):
        return False
    if _configured_command(cfg, "structure_check"):
        return True
    return isinstance(structure_cfg, dict)


def _print_limited(label: str, items: list[str], max_items: int = 60) -> None:
    if not items:
        return
    print(label)
    for item in items[:max_items]:
        print(f"- {item}")
    remaining = len(items) - max_items
    if remaining > 0:
        print(f"- ... {remaining} more")


def cmd_structure_check(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    requested_scope = str(getattr(args, "scope", "") or "").strip().lower()
    impact = _impact_summary(cfg, repo, requested_scope=requested_scope, base_ref=str(getattr(args, "base", "") or ""))
    selected_scope = str(impact["selected_scope"])
    base_ref = str(getattr(args, "base", "") or "")

    structure_cfg = _structure_cfg(cfg)
    optimization_cfg = _optimization_cfg(cfg)
    warn_file_lines = _int_config(structure_cfg.get("max_file_lines_warn"), 800)
    block_file_lines = _int_config(structure_cfg.get("max_file_lines_block"), 1500)
    warn_function_lines = _int_config(structure_cfg.get("max_function_lines_warn"), 120)
    max_added_to_large = _int_config(structure_cfg.get("max_added_lines_to_large_file"), 80)
    block_large_growth = _bool_config(structure_cfg.get("block_new_responsibility_in_large_file"), True)
    layer_cfg = _layer_rules_config(structure_cfg)
    block_layer_violations = _bool_config(layer_cfg.get("block"), True)

    paths = _structure_paths_for_scope(repo, selected_scope, base_ref, structure_cfg)
    added_by_path = _added_lines_by_path(repo, base_ref=base_ref) if selected_scope != "full" else {}

    blocking: list[str] = []
    warnings: list[str] = []
    inspected = 0

    for path in paths:
        lines = _read_text_lines(repo, path)
        if lines is None:
            continue
        inspected += 1
        line_count = len(lines)
        accepted_debt = _is_structure_accepted_debt(path, structure_cfg)
        if block_file_lines > 0 and line_count > block_file_lines:
            message = f"{path} has {line_count} lines (block>{block_file_lines}); split responsibilities before adding more work"
            if accepted_debt:
                warnings.append(message + " [accepted_debt_paths]")
            else:
                blocking.append(message)
        elif warn_file_lines > 0 and line_count > warn_file_lines:
            warnings.append(f"{path} has {line_count} lines (warn>{warn_file_lines}); prefer extraction before extending it")

        added_lines = added_by_path.get(path, 0)
        if (
            block_large_growth
            and selected_scope != "full"
            and warn_file_lines > 0
            and max_added_to_large > 0
            and line_count > warn_file_lines
            and added_lines > max_added_to_large
        ):
            blocking.append(
                f"{path} adds {added_lines} lines to an already large file ({line_count} lines); "
                "extract a module/helper or document why this is intentionally co-located"
            )

        warnings.extend(_function_size_warnings(path, lines, warn_function_lines))
        boundary_issues = _structure_boundary_issues(path, lines, structure_cfg)
        if block_layer_violations:
            blocking.extend(boundary_issues)
        else:
            warnings.extend(boundary_issues)

    missing_docs: list[str] = []
    for key, rel_path in _configured_structure_docs(cfg).items():
        if rel_path and not Path(repo, rel_path).exists():
            missing_docs.append(f"{key} missing on disk: {rel_path}")
    require_baseline = _bool_config(optimization_cfg.get("require_baseline_for_global_review"), True)
    if missing_docs and selected_scope == "full" and require_baseline:
        blocking.extend(missing_docs)
    else:
        warnings.extend(missing_docs)

    result = {
        "scope": selected_scope,
        "inspected_files": inspected,
        "blocking": blocking,
        "warnings": warnings,
    }
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_limited("[structure-check] blocking", blocking)
        _print_limited("[structure-check] warnings", warnings)

    if blocking:
        _record_evidence(repo, cfg, "structure_check", "fail", result)
        raise APError(f"structure-check failed with {len(blocking)} blocking issue(s)")

    _record_evidence(repo, cfg, "structure_check", "pass", result)
    if not getattr(args, "json", False):
        print(f"[structure-check] OK scope={selected_scope} inspected={inspected} warnings={len(warnings)}")


def _run_structure_check_for_gate(repo: Path, cfg: dict, selected_scope: str, base_ref: str) -> list[str]:
    if not _structure_gate_enabled(cfg):
        return []
    if _configured_command(cfg, "structure_check"):
        _run_configured_command(repo, cfg, "structure_check")
        return ["structure_check"]
    cmd_structure_check(
        argparse.Namespace(
            repo=str(repo),
            scope=selected_scope,
            base=base_ref,
            json=False,
        )
    )
    return ["structure_check"]


def _current_git_ref(repo: Path) -> str:
    value = run(["git", "rev-parse", "--short=12", "HEAD"], cwd=repo, check=False).stdout.strip()
    return value or "uncommitted"


def _directory_hotspots(paths: list[str]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for path in paths:
        parts = path.split("/")
        if len(parts) <= 1:
            key = "."
        elif parts[0] in {"frontend", "backend", "packages", "apps", "services"} and len(parts) >= 3:
            key = "/".join(parts[:3])
        else:
            key = "/".join(parts[:2])
        counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20]


def _scan_structure_inventory(repo: Path, cfg: dict) -> dict:
    structure_cfg = _structure_cfg(cfg)
    warn_file_lines = _int_config(structure_cfg.get("max_file_lines_warn"), 800)
    block_file_lines = _int_config(structure_cfg.get("max_file_lines_block"), 1500)
    paths = [path for path in _tracked_files(repo) if _is_structure_candidate(path, structure_cfg)]
    large_files: list[dict] = []
    for path in paths:
        lines = _read_text_lines(repo, path)
        if lines is None:
            continue
        line_count = len(lines)
        if line_count > warn_file_lines:
            large_files.append({
                "path": path,
                "lines": line_count,
                "priority": "P1" if block_file_lines > 0 and line_count > block_file_lines else "P2",
            })
    large_files.sort(key=lambda item: (-int(item["lines"]), str(item["path"])))
    return {
        "files_inspected": len(paths),
        "large_files": large_files,
        "hotspots": _directory_hotspots(paths),
    }


def _render_health_baseline(repo: Path, cfg: dict, inventory: dict) -> str:
    date = _dt.date.today().isoformat()
    commit = _current_git_ref(repo)
    large_rows = "\n".join(
        f"| `{item['path']}` | {item['lines']} lines | Accepted for baseline; no large new additions without extraction | {date} |"
        for item in inventory["large_files"][:30]
    ) or "| (none) |  |  |  |"
    debt_rows = "\n".join(
        f"| DEBT-{idx:03d} | {item['priority']} | `{item['path']}` | Large file baseline: {item['lines']} lines | Existing state at baseline | New large additions or touched feature work |"
        for idx, item in enumerate(inventory["large_files"][:30], start=1)
    ) or "| (none) |  |  |  |  |  |"
    return f"""# Project Health Baseline

> Generated by `ap.py baseline init`. Update this file when accepted structure debt changes.

- Baseline date: {date}
- Baseline commit: `{commit}`
- Owner: TODO
- Review scope: repo
- Standard: `docs/architecture/structure-standard.md`
- Files inspected: {inventory['files_inspected']}

## 1. Current Accepted Structure

| Area | Current state | Accepted because | Review date |
| --- | --- | --- | --- |
{large_rows}

## 2. Closed Optimization Scope

| ID | Closed date | Scope | Acceptance evidence |
| --- | --- | --- | --- |
| (none) |  |  |  |

## 3. Accepted Debt

| ID | Priority | Scope | Debt | Why accepted | Revisit trigger |
| --- | --- | --- | --- | --- | --- |
{debt_rows}

## 4. Priority Rules

- P0: blocks build, release, deploy, core user flow, data integrity, security, or compliance.
- P1: clear architectural violation, contract drift, missing test around high-risk change, or recently introduced maintainability risk.
- P2: planned debt such as large files, hot directories, module extraction, stronger tests, or tool consolidation.
- P3: optional naming, style, polish, or further abstraction.

## 5. Completion Standard

An optimization task is complete when all are true:

- The scoped P0/P1/P2 items listed for this task are closed.
- Local gate passed, including structure check when enabled.
- No new unclassified P0/P1 was introduced.
- Remaining P2/P3 items are either in `docs/reviews/optimization-backlog.md` or accepted debt above.
- Review output says explicitly whether the project meets this baseline.

## 6. New Review Instructions

- Read this baseline first.
- Read `docs/reviews/optimization-backlog.md` second.
- Report only new or worsened issues, unrecorded P0/P1, priority upgrades, or baseline drift.
"""


def _render_optimization_backlog(inventory: dict) -> str:
    date = _dt.date.today().isoformat()
    rows = "\n".join(
        f"| OPT-{idx:03d} | {item['priority']} | accepted-debt | `{item['path']}` | Split or reduce {item['lines']}-line file | Existing large file baseline | No new responsibilities; extract during touched feature work | {date} |"
        for idx, item in enumerate(inventory["large_files"][:30], start=1)
    ) or "| (none) |  |  |  |  |  |  |  |"
    hotspot_rows = "\n".join(
        f"| HOT-{idx:03d} | P3 | open | `{path}` | Review module cohesion ({count} tracked source files) | Hotspot directory | Split only when feature work naturally touches this area | {date} |"
        for idx, (path, count) in enumerate(inventory["hotspots"][:10], start=1)
    )
    if hotspot_rows:
        rows = rows + "\n" + hotspot_rows
    return f"""# Optimization Backlog

> Generated by `ap.py baseline init`. Accepted debt is not a current-task failure unless it worsens or is touched by new feature work.

## Status Values

- `open`: confirmed and waiting for planning.
- `accepted-debt`: accepted current debt with a revisit trigger.
- `in-progress`: currently being handled.
- `closed`: completed with evidence.
- `superseded`: replaced by another item.

## Backlog

| ID | Priority | Status | Scope | Item | Reason | Acceptance | Last reviewed |
| --- | --- | --- | --- | --- | --- | --- | --- |
{rows}

## Review Rules

- P0/P1 cannot remain in backlog without immediate owner and plan.
- P2 needs scope, reason, and acceptance.
- P3 does not block completion.
- New reviews update existing rows instead of duplicating equivalent findings.
"""


def _update_accepted_debt_paths(repo: Path, cfg: dict, paths: list[str]) -> list[str]:
    if not paths:
        return []
    engineering = find_config(repo)
    current_cfg, body = _read_frontmatter_markdown(engineering)
    structure_cfg = current_cfg.setdefault("structure", {})
    existing = [str(item) for item in _as_list(structure_cfg.get("accepted_debt_paths")) if str(item).strip()]
    added = [path for path in paths if path not in existing]
    if added:
        structure_cfg["accepted_debt_paths"] = existing + added
        _write_frontmatter_markdown(engineering, current_cfg, body)
    return added


def cmd_baseline_init(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    docs_cfg = cfg.get("docs") or {}
    inventory = _scan_structure_inventory(repo, cfg)
    health_path = Path(repo, _text(docs_cfg.get("health_baseline")) or "docs/reviews/project-health-baseline.md")
    backlog_path = Path(repo, _text(docs_cfg.get("optimization_backlog")) or "docs/reviews/optimization-backlog.md")
    write = bool(args.write)
    force = bool(args.force)
    update_config = bool(args.update_config)

    actions: list[dict] = []
    for path, content, label in [
        (health_path, _render_health_baseline(repo, cfg, inventory), "health_baseline"),
        (backlog_path, _render_optimization_backlog(inventory), "optimization_backlog"),
    ]:
        if path.exists() and not force:
            actions.append({"path": _repo_rel(repo, path), "action": "exists", "kind": label})
            continue
        actions.append({"path": _repo_rel(repo, path), "action": "write" if write else "would-write", "kind": label})
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    accepted_added: list[str] = []
    accepted_paths = [str(item["path"]) for item in inventory["large_files"] if item["priority"] in {"P1", "P2"}]
    if write and update_config:
        accepted_added = _update_accepted_debt_paths(repo, cfg, accepted_paths)
        if accepted_added:
            actions.append({
                "path": "docs/ENGINEERING.md",
                "action": "merge",
                "kind": "accepted_debt_paths",
                "detail": ", ".join(accepted_added),
            })

    result = {
        "files_inspected": inventory["files_inspected"],
        "large_files": inventory["large_files"],
        "hotspots": inventory["hotspots"],
        "actions": actions,
        "updated_accepted_debt_paths": accepted_added,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[baseline] files_inspected={inventory['files_inspected']}")
        print(f"[baseline] large_files={len(inventory['large_files'])}")
        for item in actions:
            detail = f" - {item.get('detail')}" if item.get("detail") else ""
            print(f"[baseline] {item['action']} {item['kind']}: {item['path']}{detail}")
        if not write:
            print("[baseline] dry-run only; re-run with --write to create baseline files")

    if write:
        _record_evidence(
            repo,
            cfg,
            "baseline_init",
            "pass",
            {"write": write, "large_file_count": len(inventory["large_files"]), "files_inspected": inventory["files_inspected"]},
        )


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def cmd_gate_profile(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    records = _read_jsonl(_gate_profile_path(repo, cfg))
    limit = int(args.limit or 20)
    by_name: dict[str, dict] = {}
    for record in records:
        name = _text(record.get("name")) or "(unknown)"
        bucket = by_name.setdefault(name, {"name": name, "runs": 0, "failures": 0, "total_duration_s": 0.0, "max_duration_s": 0.0})
        duration = float(record.get("duration_s") or 0)
        bucket["runs"] += 1
        bucket["total_duration_s"] += duration
        bucket["max_duration_s"] = max(float(bucket["max_duration_s"]), duration)
        if _text(record.get("status")) != "pass":
            bucket["failures"] += 1
    summary = []
    for bucket in by_name.values():
        runs = int(bucket["runs"])
        total = float(bucket["total_duration_s"])
        summary.append({
            "name": bucket["name"],
            "runs": runs,
            "failures": int(bucket["failures"]),
            "failure_rate": round(int(bucket["failures"]) / runs, 3) if runs else 0,
            "avg_duration_s": round(total / runs, 3) if runs else 0,
            "max_duration_s": round(float(bucket["max_duration_s"]), 3),
        })
    summary.sort(key=lambda item: (-float(item["avg_duration_s"]), str(item["name"])))
    result = {"profile_log": str(_gate_profile_path(repo, cfg)), "commands": summary[:limit], "record_count": len(records)}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[gate-profile] log={result['profile_log']}")
        print(f"[gate-profile] records={len(records)}")
        if not summary:
            print("[gate-profile] no profile records yet; run light-gate or configured commands first")
        for item in summary[:limit]:
            print(
                f"[gate-profile] {item['name']}: runs={item['runs']} "
                f"avg={item['avg_duration_s']}s max={item['max_duration_s']}s failures={item['failures']}"
            )


def _classify_paths(paths: list[str]) -> dict:
    categories: set[str] = set()
    for path in paths:
        lower = path.lower()
        if _path_matches(path, _DEFAULT_FULL_PATH_PATTERNS):
            categories.add("release_or_tooling")
        if any(token in lower for token in ["migration", "schema", "database", "/db/", "/sql/"]) or lower.endswith(".sql"):
            categories.add("db")
        if any(token in lower for token in ["api", "controller", "handler", "route", "server"]):
            categories.add("api")
        if any(token in lower for token in ["auth", "permission", "role", "tenant", "security"]):
            categories.add("auth")
        if any(token in lower for token in ["page", "component", "view", "frontend", "miniapp", ".tsx", ".jsx", ".vue", ".scss", ".css"]):
            categories.add("ui")
        if any(token in lower for token in ["test", "spec", "__tests__"]):
            categories.add("test")
        if lower.startswith("docs/") or lower.endswith(".md"):
            categories.add("docs")
        if any(token in lower for token in ["domain", "service", "usecase", "repository", "infrastructure", "adapter", "shared", "utils"]):
            categories.add("structure")
    return {
        "categories": sorted(categories),
        "needs_dd": bool(categories & {"api", "db", "auth", "release_or_tooling"}) or len(paths) > 12,
        "needs_adr": bool(categories & {"structure", "release_or_tooling"}) and not categories <= {"docs"},
        "needs_browser": "ui" in categories,
        "needs_jenkins": bool(categories & {"release_or_tooling", "db", "auth"}),
        "needs_target": bool(categories & {"api", "db", "auth", "ui"}),
    }


def cmd_classify(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    scope = str(args.scope or "").strip().lower()
    impact = _impact_summary(cfg, repo, requested_scope=scope, base_ref=str(args.base or ""))
    paths = list(impact.get("changed_files") or [])
    path_classification = _classify_paths(paths)
    selected_scope = str(impact["selected_scope"])
    risk = "P3"
    if path_classification["needs_jenkins"] or selected_scope == "full":
        risk = "P1"
    elif path_classification["needs_target"] or path_classification["needs_dd"]:
        risk = "P2"
    elif not paths:
        risk = "P3"
    commands = [
        "python3 docs/tools/autopipeline/ap.py impact --scope auto",
        "python3 docs/tools/autopipeline/ap.py structure-check --scope auto",
        f"python3 docs/tools/autopipeline/ap.py light-gate --scope {selected_scope} --explain",
    ]
    if path_classification["needs_jenkins"]:
        commands.append("python3 docs/tools/autopipeline/ap.py verify-jenkins")
    result = {
        "requested_scope": impact["requested_scope"],
        "selected_scope": selected_scope,
        "risk": risk,
        "changed_files": paths,
        "categories": path_classification["categories"],
        "needs_dd": path_classification["needs_dd"],
        "needs_adr": path_classification["needs_adr"],
        "needs_browser": path_classification["needs_browser"],
        "needs_jenkins": path_classification["needs_jenkins"],
        "needs_target": path_classification["needs_target"],
        "recommended_commands": commands,
        "reasons": impact.get("reasons") or [],
        "matched_rules": impact.get("matched_rules") or [],
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[classify] risk={risk}")
        print(f"[classify] selected_scope={selected_scope}")
        print("[classify] categories=" + (", ".join(result["categories"]) or "(none)"))
        for key in ["needs_dd", "needs_adr", "needs_browser", "needs_jenkins", "needs_target"]:
            print(f"[classify] {key}={result[key]}")
        for command in commands:
            print(f"[classify] command: {command}")
    _record_evidence(repo, cfg, "classify", "pass", result)


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
    cmd = str(commands.get(name) or "").strip()
    if not cmd:
        raise APError(f"Command is blank: commands.{name}. Edit docs/ENGINEERING.md frontmatter.")
    print(f"[run] {name}: {cmd}")
    run_shell(cmd, cwd=repo)
    print(f"[run] OK: {name}")


def cmd_light_gate(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    light_gate_start = time.time()
    cmd_doctor(argparse.Namespace(repo=str(repo)))
    cfg = _load_cfg(repo)
    requested_scope = str(getattr(args, "scope", "") or "").strip().lower()
    impact = _impact_summary(cfg, repo, requested_scope=requested_scope, base_ref=str(getattr(args, "base", "") or ""))
    if getattr(args, "explain", False):
        _print_impact(impact)

    selected_scope = str(impact["selected_scope"])
    paths = list(impact.get("changed_files") or [])
    matching_rules = _matching_gate_rules(paths, _gate_cfg(cfg))
    executed: list[str] = []
    executed.extend(_run_structure_check_for_gate(repo, cfg, selected_scope, str(getattr(args, "base", "") or "")))

    if selected_scope == "changed":
        executed.extend(_run_changed_gate(repo, cfg, paths, matching_rules))
    elif selected_scope == "full":
        executed.extend(_run_full_gate(repo, cfg))
    else:
        executed.extend(_run_standard_gate(repo, cfg))

    _run_git_diff_check(repo, cfg)
    cmd_verify_api_docs(argparse.Namespace(repo=str(repo)))
    cmd_verify_jenkins(argparse.Namespace(repo=str(repo)))
    executed.extend(["diff_check", "verify_api_docs", "verify_jenkins"])
    duration_s = time.time() - light_gate_start
    _record_gate_profile(repo, cfg, "light_gate", "pass", duration_s, scope=selected_scope, detail=", ".join(executed))
    _record_evidence(
        repo,
        cfg,
        "light_gate",
        "pass",
        {"scope": selected_scope, "executed": executed, "duration_s": round(duration_s, 3), "changed_files": paths},
    )
    print(f"[light-gate] OK scope={selected_scope}: " + ", ".join(executed))


def cmd_impact(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    scope = str(args.scope or "").strip().lower()
    summary = _impact_summary(cfg, repo, requested_scope=scope, base_ref=str(args.base or ""))
    _print_impact(summary, as_json=bool(args.json))
    _record_evidence(repo, cfg, "impact", "pass", summary)


def cmd_runtime_up(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    runtime_cfg = (cfg.get("runtime") or {})
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
        target_cfg = (cfg.get("target_env") or {})
        jenkins_cfg = (cfg.get("jenkins") or {})
        base_url = str(target_cfg.get("health_base_url") or "")
        path = str(target_cfg.get("health_path") or "")
        url = _join_url(
            base_url,
            path,
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


def cmd_verify_target(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    target_cfg = (cfg.get("target_env") or {})

    cmd_wait_health(argparse.Namespace(repo=str(repo), scope="target"))

    checks: List[str] = []

    backend_base = str(target_cfg.get("backend_base_url") or "").strip().rstrip("/")
    frontend_base = str(target_cfg.get("frontend_base_url") or "").strip().rstrip("/")

    backend_headers: dict[str, str] = {}
    frontend_headers: dict[str, str] = {}
    if args.backend_basic_auth:
        user = str(target_cfg.get("backend_username") or "").strip()
        if not user:
            raise APError("Missing target_env.backend_username for backend basic auth.")
        password = _resolve_secret("target_env", target_cfg, "backend_password")
        backend_headers = _basic_auth_header(user, password)
    if args.frontend_basic_auth:
        user = str(target_cfg.get("frontend_username") or "").strip()
        if not user:
            raise APError("Missing target_env.frontend_username for frontend basic auth.")
        password = _resolve_secret("target_env", target_cfg, "frontend_password")
        frontend_headers = _basic_auth_header(user, password)

    for path in args.backend_path or []:
        if not backend_base:
            raise APError("Missing target_env.backend_base_url for backend path verification.")
        url = _join_url(backend_base, path)
        status, body = _http_get(url, headers=backend_headers, timeout_s=10)
        if not (200 <= status < 400):
            raise APError(f"Backend target verification failed: {url} -> {status}\n{body[:400]}")
        checks.append(f"backend:{url}->{status}")

    for path in args.frontend_path or []:
        if not frontend_base:
            raise APError("Missing target_env.frontend_base_url for frontend path verification.")
        url = _join_url(frontend_base, path)
        status, body = _http_get(url, headers=frontend_headers, timeout_s=10)
        if not (200 <= status < 400):
            raise APError(f"Frontend target verification failed: {url} -> {status}\n{body[:400]}")
        checks.append(f"frontend:{url}->{status}")

    summary = ", ".join(checks) if checks else "health-only"
    _record_evidence(repo, cfg, "verify_target", "pass", {"summary": summary, "checks": checks})
    print(f"[verify-target] OK: {summary}")
    return summary


def cmd_verify_jenkins(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    project_cfg = (cfg.get("project") or {})
    jenkins_cfg = (cfg.get("jenkins") or {})
    target_cfg = (cfg.get("target_env") or {})
    jenkinsfile = Path(repo, str(project_cfg.get("jenkinsfile") or "Jenkinsfile"))
    if not jenkinsfile.exists():
        raise APError(f"Jenkinsfile not found: {jenkinsfile}")

    required = [
        ("jenkins.base_url", jenkins_cfg.get("base_url")),
        ("jenkins.job_url", jenkins_cfg.get("job_url")),
        ("jenkins.trigger_branch", jenkins_cfg.get("trigger_branch")),
        ("jenkins.image_repository", jenkins_cfg.get("image_repository")),
        ("jenkins.image_tag_strategy", jenkins_cfg.get("image_tag_strategy")),
        ("jenkins.deploy_env", jenkins_cfg.get("deploy_env")),
        ("target_env.health_base_url", target_cfg.get("health_base_url")),
        ("target_env.health_path", target_cfg.get("health_path")),
    ]
    missing = [name for name, value in required if not str(value or "").strip()]
    if missing:
        raise APError("Missing Jenkins config: " + ", ".join(missing))
    _record_evidence(repo, cfg, "verify_jenkins", "pass", {"jenkinsfile": str(jenkinsfile)})
    print(f"[verify-jenkins] OK: {jenkinsfile}")


def cmd_doctor(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    workflow_cfg = (cfg.get("workflow") or {})
    project_cfg = (cfg.get("project") or {})
    commands = (cfg.get("commands") or {})
    target_cfg = (cfg.get("target_env") or {})
    jenkins_cfg = (cfg.get("jenkins") or {})
    docs_cfg = (cfg.get("docs") or {})
    runtime_cfg = (cfg.get("runtime") or {})

    missing: List[str] = []
    validation_errors: List[str] = []

    mode = str(workflow_cfg.get("mode") or "dev").strip().lower()
    if mode not in {"dev", "verify"}:
        missing.append("workflow.mode (must be dev or verify)")
    if not str(project_cfg.get("name") or "").strip():
        missing.append("project.name")
    if not (
        str(commands.get("gate_changed") or "").strip()
        or str(commands.get("gate_standard") or "").strip()
        or str(commands.get("gate_full") or "").strip()
        or str(commands.get("full_gate") or "").strip()
        or str(commands.get("light_gate") or "").strip()
        or str(commands.get("quick_test") or "").strip()
        or str(commands.get("test") or "").strip()
        or str(commands.get("build") or "").strip()
    ):
        missing.append(
            "commands.gate_changed/gate_standard/gate_full, commands.light_gate, "
            "commands.quick_test, commands.test, or commands.build"
        )
    _require_explicit_field(missing, "target_env.name", target_cfg.get("name"))
    _require_explicit_field(missing, "target_env.frontend_base_url", target_cfg.get("frontend_base_url"))
    _require_explicit_field(missing, "target_env.frontend_username", target_cfg.get("frontend_username"))
    _require_secret_reference(missing, "target_env", target_cfg, "frontend_password")
    _require_explicit_field(missing, "target_env.backend_base_url", target_cfg.get("backend_base_url"))
    _require_explicit_field(missing, "target_env.backend_username", target_cfg.get("backend_username"))
    _require_secret_reference(missing, "target_env", target_cfg, "backend_password")
    _require_explicit_field(missing, "target_env.backend_root_username", target_cfg.get("backend_root_username"))
    _require_secret_reference(missing, "target_env", target_cfg, "backend_root_password")
    _require_explicit_field(missing, "target_env.health_base_url", target_cfg.get("health_base_url"))
    _require_explicit_field(missing, "target_env.health_path", target_cfg.get("health_path"))

    _require_explicit_field(missing, "jenkins.base_url", jenkins_cfg.get("base_url"))
    _require_explicit_field(missing, "jenkins.ui_username", jenkins_cfg.get("ui_username"))
    _require_secret_reference(missing, "jenkins", jenkins_cfg, "ui_password")
    _require_explicit_field(missing, "jenkins.job_url", jenkins_cfg.get("job_url"))
    _require_explicit_field(missing, "jenkins.trigger_branch", jenkins_cfg.get("trigger_branch"))
    _require_explicit_field(missing, "jenkins.image_repository", jenkins_cfg.get("image_repository"))
    _require_explicit_field(missing, "jenkins.image_tag_strategy", jenkins_cfg.get("image_tag_strategy"))
    _require_explicit_field(missing, "jenkins.deploy_env", jenkins_cfg.get("deploy_env"))
    _require_explicit_field(missing, "jenkins.api_user", jenkins_cfg.get("api_user"))
    _require_secret_reference(missing, "jenkins", jenkins_cfg, "api_password")

    repo_docs = {
        "docs.taskbook": Path(repo, str(docs_cfg.get("taskbook", "docs/tasks/taskbook.md"))),
        "docs.closure_log": Path(repo, str(docs_cfg.get("closure_log", "docs/tasks/closure-log.md"))),
        "docs.api_doc": Path(repo, str(docs_cfg.get("api_doc", "docs/interfaces/api.md"))),
        "docs.api_change_log": Path(repo, str(docs_cfg.get("api_change_log", "docs/interfaces/api-change-log.md"))),
    }
    for key, path in repo_docs.items():
        if not path.exists():
            validation_errors.append(f"{key} missing on disk: {path}")

    _validate_url_field(validation_errors, "target_env.frontend_base_url", target_cfg.get("frontend_base_url"))
    _validate_url_field(validation_errors, "target_env.backend_base_url", target_cfg.get("backend_base_url"))
    _validate_url_field(validation_errors, "target_env.health_base_url", target_cfg.get("health_base_url"))
    _validate_path_field(validation_errors, "target_env.health_path", target_cfg.get("health_path"))
    _validate_url_field(validation_errors, "jenkins.base_url", jenkins_cfg.get("base_url"))
    _validate_url_field(validation_errors, "jenkins.job_url", jenkins_cfg.get("job_url"))

    runtime_enabled = any(str(runtime_cfg.get(key) or "").strip() for key in ["docker_compose_file", "docker_service", "health_base_url", "health_path"])
    if runtime_enabled and not str(runtime_cfg.get("docker_compose_file") or "").strip():
        validation_errors.append("runtime config is partially enabled but runtime.docker_compose_file is missing")

    ledger_result = _docs_ledger_check_result(repo, cfg)
    ledger_status = "skipped" if not ledger_result.get("enabled", True) else ("fail" if ledger_result.get("blocking") else "pass")
    _record_evidence(repo, cfg, "docs_ledger_check", ledger_status, ledger_result)
    for issue in ledger_result.get("blocking") or []:
        validation_errors.append(f"docs-ledger: {issue}")
    for warning in ledger_result.get("warnings") or []:
        print(f"[doctor] WARN docs-ledger: {warning}")

    try:
        timeout_s = int(jenkins_cfg.get("deploy_timeout_sec") or 0)
        if timeout_s <= 0:
            validation_errors.append("jenkins.deploy_timeout_sec must be a positive integer")
    except Exception:
        validation_errors.append("jenkins.deploy_timeout_sec must be a positive integer")

    missing.extend(validation_errors)

    if missing:
        _record_evidence(repo, cfg, "doctor", "fail", {"issues": missing})
        raise APError("Doctor found blocking config issues:\n- " + "\n- ".join(missing))

    _record_evidence(repo, cfg, "doctor", "pass", {"mode": mode})
    print("[doctor] OK")


def cmd_verify_jenkins_build(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    jenkins_cfg = (cfg.get("jenkins") or {})
    git_ref = str(args.git_ref or "HEAD").strip()
    candidate_job_urls = _resolve_jenkins_job_candidates(
        cfg,
        repo,
        git_ref=git_ref,
        job_name=args.job_name,
        job_url=args.job_url,
        multibranch_root_job=args.multibranch_root_job,
        branch_name=args.branch_name,
    )
    build_number = args.build_number
    max_builds = int(args.max_builds or 20)
    timeout_s = int(args.timeout_sec or 300)
    poll_s = int(args.poll_sec or 5)
    inferred_branch = ""
    if args.multibranch_root_job and not args.branch_name:
        inferred_branch = _resolve_git_branch_name(repo, git_ref)
    branch_hint = str(args.branch_name or inferred_branch or "").strip()
    root_hint = str(
        args.multibranch_root_job
        or args.job_name
        or args.job_url
        or jenkins_cfg.get("job_url")
        or ""
    ).strip()
    if branch_hint and root_hint:
        job_label = f"{root_hint}/{branch_hint}"
    else:
        job_label = branch_hint or root_hint or "(configured)"

    deadline = time.time() + timeout_s
    if build_number is not None:
        payload = None
        while time.time() < deadline:
            payload = None
            for candidate_job_url in candidate_job_urls:
                api_url = _jenkins_build_api_url(candidate_job_url, int(build_number))
                payload = _jenkins_api_get_json(api_url, cfg, allow_404=True)
                if payload is not None:
                    break
            if payload is not None and not payload.get("building"):
                break
            time.sleep(poll_s)
        if not payload:
            raise APError(
                f"No Jenkins build payload found for build #{build_number} under any candidate job URL. "
                f"Checked for up to {timeout_s}s."
            )
        if payload.get("building"):
            raise APError(
                f"Jenkins build is still running: "
                f"#{payload.get('number')} {payload.get('url')}"
            )
        result, description = _assert_jenkins_build_success(
            payload,
            f"#{payload.get('number')} {payload.get('url')}",
            args.allow_no_deploy,
        )
        build_url = str(payload.get("url") or "").strip()
        _record_evidence(
            repo,
            cfg,
            "verify_jenkins_build",
            "pass",
            {"job": job_label, "build": payload.get("number"), "result": result, "url": build_url},
        )
        print(
            "[verify-jenkins-build] OK: "
            f"job={job_label} "
            f"build=#{payload.get('number')} "
            f"result={result} "
            f"description={description} "
            f"url={build_url}"
        )
        return build_url

    git_short_sha = _resolve_git_short_sha(repo, git_ref)
    matched = None

    while time.time() < deadline:
        matched = None
        for candidate_job_url in candidate_job_urls:
            api_url = _jenkins_builds_api_url(candidate_job_url, max_builds)
            payload = _jenkins_api_get_json(api_url, cfg, allow_404=True)
            if payload is None:
                continue
            builds = payload.get("builds") or []
            matched = next((b for b in builds if git_short_sha in str(b.get("description") or "")), None)
            if matched:
                break
        if matched and not matched.get("building"):
            break
        time.sleep(poll_s)

    if not matched:
        raise APError(
            f"No Jenkins build found for commit {git_short_sha} under any candidate job URL. "
            f"Checked latest {max_builds} builds for up to {timeout_s}s."
        )

    result, description = _assert_jenkins_build_success(
        matched,
        f"#{matched.get('number')} {matched.get('url')}",
        args.allow_no_deploy,
    )
    build_url = str(matched.get("url") or "").strip()
    _record_evidence(
        repo,
        cfg,
        "verify_jenkins_build",
        "pass",
        {"commit": git_short_sha, "job": job_label, "build": matched.get("number"), "result": result, "url": build_url},
    )
    print(
        "[verify-jenkins-build] OK: "
        f"commit={git_short_sha} "
        f"job={job_label} "
        f"build=#{matched.get('number')} "
        f"result={result} "
        f"description={description} "
        f"url={build_url}"
    )
    return build_url


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
    _record_evidence(repo, cfg, "verify_api_docs", "pass", {"api_doc": str(api_doc), "api_change_log": str(change_log)})
    print(f"[verify-api-docs] OK: {api_doc} + {change_log}")


def cmd_record_closure(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    docs_cfg = (cfg.get("docs") or {})
    target_cfg = (cfg.get("target_env") or {})
    taskbook = Path(repo, str(docs_cfg.get("taskbook", "docs/tasks/taskbook.md")))
    closure_log = Path(repo, str(docs_cfg.get("closure_log", "docs/tasks/closure-log.md")))
    closure_log.parent.mkdir(parents=True, exist_ok=True)
    if not closure_log.exists():
        closure_log.write_text("# Closure Log\n\n", encoding="utf-8")

    task_id = args.task_id
    title = str(args.title or "").strip() or _infer_title(taskbook, task_id)
    timestamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    commit_value = _resolve_git_short_sha(repo, args.commit)
    target_env = str(args.target_env or target_cfg.get("name") or "").strip() or "(not set)"
    verification_items = args.verification or []
    verification_text = "; ".join(verification_items) if verification_items else "TODO"
    follow_up = str(args.follow_up or "").strip() or "none"
    jenkins_build = str(args.jenkins or "").strip() or "TODO"
    structure_check = str(getattr(args, "structure_check", "") or "").strip() or "TODO"

    lines = [
        f"## {task_id} — {title} — {timestamp}",
        f"- Task: {task_id}",
        f"- Commit: {commit_value}",
        f"- Jenkins Build: {jenkins_build}",
        f"- Target Env: {target_env}",
        f"- Verification: {verification_text}",
        f"- Structure Check: {structure_check}",
        f"- Result: {args.result}",
        f"- Follow-up: {follow_up}",
    ]
    if str(args.initial_commit or "").strip():
        lines.append(f"- Initial Commit: {args.initial_commit.strip()}")
    if str(args.jenkins_failure or "").strip():
        lines.append(f"- Jenkins Failure: {args.jenkins_failure.strip()}")
    if str(args.fix_commit or "").strip():
        lines.append(f"- Fix Commit: {args.fix_commit.strip()}")

    with closure_log.open("a", encoding="utf-8") as f:
        if closure_log.stat().st_size > 0:
            f.write("\n")
        f.write("\n".join(lines))
        f.write("\n")
    _record_evidence(
        repo,
        cfg,
        "record_closure",
        "pass",
        {"task_id": task_id, "result": args.result, "commit": commit_value, "structure_check": structure_check},
    )
    print(f"[record-closure] OK: {closure_log}")


def _record_commit_push_closure(
    repo: Path,
    args: argparse.Namespace,
    *,
    commit: str,
    jenkins: str,
    target_env: str,
    verification: List[str],
    result: str,
    follow_up: str,
    structure_check: str,
) -> None:
    cmd_record_closure(
        argparse.Namespace(
            repo=str(repo),
            task_id=args.task_id,
            title=args.title,
            commit=commit,
            jenkins=jenkins,
            target_env=target_env,
            verification=verification,
            result=result,
            follow_up=follow_up,
            structure_check=structure_check,
            initial_commit=args.initial_commit,
            jenkins_failure=args.jenkins_failure,
            fix_commit=args.fix_commit,
        )
    )


def cmd_commit_push(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cmd_doctor(argparse.Namespace(repo=str(repo)))
    cfg = _load_cfg(repo)
    mode = _workflow_mode(cfg, args)
    target_cfg = (cfg.get("target_env") or {})

    msg = args.msg
    structure_check_status = "skipped"

    if args.require_runtime_health:
        cmd_wait_health(argparse.Namespace(repo=str(repo), scope="runtime"))

    if mode in {"dev", "verify"} or args.require_light_gate:
        cmd_light_gate(argparse.Namespace(repo=str(repo)))
        structure_check_status = "passed via light-gate" if _structure_gate_enabled(cfg) else "skipped (structure disabled)"

    if args.require_jenkins:
        cmd_verify_jenkins(argparse.Namespace(repo=str(repo)))

    if args.require_matrix and mode != "verify":
        cmd_check_matrix(argparse.Namespace(repo=str(repo)))

    if mode == "dev":
        dev_verification = args.verification or [
            "light-gate only",
            "Jenkins triggered by push; build not verified in dev mode",
            "target environment not verified in dev mode",
        ]
        _record_commit_push_closure(
            repo,
            args,
            commit="generated by this commit-push run",
            jenkins=args.jenkins_build or "triggered by push, not verified in dev mode",
            target_env=args.target_env or "not verified in dev mode",
            verification=dev_verification,
            result=args.result or "DEV-CLOSED",
            follow_up=args.follow_up or "Run verify mode when Jenkins and target-environment evidence is required.",
            structure_check=args.structure_check or structure_check_status,
        )

    run(["git", "add", "-A"], cwd=repo)
    diff = run(["git", "diff", "--cached", "--name-only"], cwd=repo).stdout.strip()
    if not diff:
        raise APError("Nothing to commit.")

    run(["git", "commit", "-m", msg], cwd=repo)
    run(["git", "push"], cwd=repo)

    if mode == "verify":
        jenkins_build = cmd_verify_jenkins_build(
            argparse.Namespace(
                repo=str(repo),
                git_ref="HEAD",
                job_name=args.job_name,
                job_url=args.job_url,
                multibranch_root_job=args.multibranch_root_job,
                branch_name=args.branch_name,
                build_number=args.build_number,
                max_builds=args.max_builds,
                timeout_sec=args.timeout_sec,
                poll_sec=args.poll_sec,
                allow_no_deploy=args.allow_no_deploy,
            )
        )
        target_summary = cmd_verify_target(
            argparse.Namespace(
                repo=str(repo),
                backend_path=args.backend_path,
                frontend_path=args.frontend_path,
                backend_basic_auth=args.backend_basic_auth,
                frontend_basic_auth=args.frontend_basic_auth,
            )
        )
        if args.require_matrix:
            cmd_check_matrix(argparse.Namespace(repo=str(repo)))
        verification = args.verification or [
            f"Jenkins build verified: {jenkins_build or 'verified by git-ref HEAD'}",
            f"Target verification: {target_summary}",
        ]
        _record_commit_push_closure(
            repo,
            args,
            commit="HEAD",
            jenkins=args.jenkins_build or jenkins_build or "verified by git-ref HEAD",
            target_env=args.target_env or str(target_cfg.get("name") or "").strip(),
            verification=verification,
            result=args.result or "PASS",
            follow_up=args.follow_up or "none",
            structure_check=args.structure_check or structure_check_status,
        )
        run(["git", "add", "-A"], cwd=repo)
        closure_diff = run(["git", "diff", "--cached", "--name-only"], cwd=repo).stdout.strip()
        if closure_diff:
            run(["git", "commit", "-m", f"{args.task_id}: record verification closure [skip ci]"], cwd=repo)
            run(["git", "push"], cwd=repo)
    elif args.record_closure and mode != "dev":
        _record_commit_push_closure(
            repo,
            args,
            commit="HEAD",
            jenkins=args.jenkins_build or "TODO",
            target_env=args.target_env or str(target_cfg.get("name") or "").strip(),
            verification=args.verification or [],
            result=args.result or "PARTIAL",
            follow_up=args.follow_up or "none",
            structure_check=args.structure_check or structure_check_status,
        )
    print(f"[commit-push] OK - mode={mode}")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="autopipeline")
    p.add_argument("--repo", default=".")
    sp = p.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("install")
    s.add_argument("--bridges", action="store_true")
    s.set_defaults(func=cmd_install)

    s = sp.add_parser("upgrade")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--write", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_upgrade)

    s = sp.add_parser("baseline")
    baseline_sp = s.add_subparsers(dest="baseline_cmd", required=True)
    b = baseline_sp.add_parser("init")
    b.add_argument("--write", action="store_true")
    b.add_argument("--force", action="store_true")
    b.add_argument("--update-config", action="store_true")
    b.add_argument("--json", action="store_true")
    b.set_defaults(func=cmd_baseline_init)

    s = sp.add_parser("gen-summary")
    s.add_argument("task_id")
    s.add_argument("--title")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_gen_summary)

    s = sp.add_parser("check-matrix")
    s.set_defaults(func=cmd_check_matrix)

    s = sp.add_parser("run")
    s.add_argument("name")
    s.set_defaults(func=cmd_run)

    s = sp.add_parser("impact")
    s.add_argument("--scope", choices=sorted(_GATE_SCOPES), default="")
    s.add_argument("--base")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_impact)

    s = sp.add_parser("classify")
    s.add_argument("--scope", choices=sorted(_GATE_SCOPES), default="")
    s.add_argument("--base")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_classify)

    s = sp.add_parser("structure-check")
    s.add_argument("--scope", choices=sorted(_GATE_SCOPES), default="")
    s.add_argument("--base")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_structure_check)

    s = sp.add_parser("gate-profile")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_gate_profile)

    s = sp.add_parser("docs-ledger-check")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_docs_ledger_check)

    s = sp.add_parser("docs-ledger-archive")
    mode = s.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--write", action="store_true")
    s.add_argument("--period", help="Archive period in YYYY-MM; defaults to current month")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_docs_ledger_archive)

    s = sp.add_parser("light-gate")
    s.add_argument("--scope", choices=sorted(_GATE_SCOPES), default="")
    s.add_argument("--base")
    s.add_argument("--explain", action="store_true")
    s.set_defaults(func=cmd_light_gate)

    s = sp.add_parser("doctor")
    s.set_defaults(func=cmd_doctor)

    s = sp.add_parser("runtime-up")
    s.set_defaults(func=cmd_runtime_up)

    s = sp.add_parser("runtime-down")
    s.set_defaults(func=cmd_runtime_down)

    s = sp.add_parser("wait-health")
    s.add_argument("--scope", choices=["runtime", "target", "prod"], default="runtime")
    s.set_defaults(func=cmd_wait_health)

    s = sp.add_parser("verify-jenkins")
    s.set_defaults(func=cmd_verify_jenkins)

    s = sp.add_parser("verify-jenkins-build")
    s.add_argument("--git-ref")
    s.add_argument("--job-name")
    s.add_argument("--job-url")
    s.add_argument("--multibranch-root-job")
    s.add_argument("--branch-name")
    s.add_argument("--build-number", type=int)
    s.add_argument("--max-builds", type=int, default=20)
    s.add_argument("--timeout-sec", type=int, default=300)
    s.add_argument("--poll-sec", type=int, default=5)
    s.add_argument("--allow-no-deploy", action="store_true")
    s.set_defaults(func=cmd_verify_jenkins_build)

    s = sp.add_parser("verify-api-docs")
    s.set_defaults(func=cmd_verify_api_docs)

    s = sp.add_parser("verify-target")
    s.add_argument("--backend-path", action="append")
    s.add_argument("--frontend-path", action="append")
    s.add_argument("--backend-basic-auth", action="store_true")
    s.add_argument("--frontend-basic-auth", action="store_true")
    s.set_defaults(func=cmd_verify_target)

    s = sp.add_parser("record-closure")
    s.add_argument("task_id")
    s.add_argument("--title")
    s.add_argument("--commit", default="HEAD")
    s.add_argument("--jenkins")
    s.add_argument("--target-env")
    s.add_argument("--verification", action="append")
    s.add_argument("--structure-check")
    s.add_argument("--result", choices=["DEV-CLOSED", "PASS", "FAIL", "PARTIAL"], required=True)
    s.add_argument("--follow-up")
    s.add_argument("--initial-commit")
    s.add_argument("--jenkins-failure")
    s.add_argument("--fix-commit")
    s.set_defaults(func=cmd_record_closure)

    s = sp.add_parser("commit-push")
    s.add_argument("task_id")
    s.add_argument("--title")
    s.add_argument("--msg", required=True)
    s.add_argument("--mode", choices=["dev", "verify"])
    s.add_argument("--require-light-gate", action="store_true")
    s.add_argument("--require-runtime-health", action="store_true")
    s.add_argument("--require-jenkins", action="store_true")
    s.add_argument("--require-matrix", action="store_true")
    s.add_argument("--record-closure", action="store_true")
    s.add_argument("--job-name")
    s.add_argument("--job-url")
    s.add_argument("--multibranch-root-job")
    s.add_argument("--branch-name")
    s.add_argument("--build-number", type=int)
    s.add_argument("--max-builds", type=int, default=20)
    s.add_argument("--timeout-sec", type=int, default=300)
    s.add_argument("--poll-sec", type=int, default=5)
    s.add_argument("--allow-no-deploy", action="store_true")
    s.add_argument("--backend-path", action="append")
    s.add_argument("--frontend-path", action="append")
    s.add_argument("--backend-basic-auth", action="store_true")
    s.add_argument("--frontend-basic-auth", action="store_true")
    s.add_argument("--jenkins-build")
    s.add_argument("--target-env")
    s.add_argument("--verification", action="append")
    s.add_argument("--structure-check")
    s.add_argument("--result", choices=["DEV-CLOSED", "PASS", "FAIL", "PARTIAL"])
    s.add_argument("--follow-up")
    s.add_argument("--initial-commit")
    s.add_argument("--jenkins-failure")
    s.add_argument("--fix-commit")
    s.set_defaults(func=cmd_commit_push)

    try:
        args = p.parse_args(argv)
        args.func(args)
        return 0
    except APError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
