#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoPipeline Pro Max - repo automation CLI (python)"""

from __future__ import annotations

import argparse
import base64
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


def _run_configured_command(repo: Path, cfg: dict, name: str) -> bool:
    commands = (cfg.get("commands") or {})
    command = str(commands.get(name) or "").strip()
    if not command:
        return False
    print(f"[run] {name}: {command}")
    run_shell(command, cwd=repo)
    print(f"[run] OK: {name}")
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
    run(["git", "diff", "--check"], cwd=repo)
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


def _configured_structure_docs(cfg: dict) -> dict[str, str]:
    docs_cfg = cfg.get("docs") or {}
    return {
        "docs.health_baseline": _text(docs_cfg.get("health_baseline")),
        "docs.optimization_backlog": _text(docs_cfg.get("optimization_backlog")),
        "docs.structure_standard": _text(docs_cfg.get("structure_standard")),
    }


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
        raise APError(f"structure-check failed with {len(blocking)} blocking issue(s)")

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
    print(f"[light-gate] OK scope={selected_scope}: " + ", ".join(executed))


def cmd_impact(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    scope = str(args.scope or "").strip().lower()
    summary = _impact_summary(cfg, repo, requested_scope=scope, base_ref=str(args.base or ""))
    _print_impact(summary, as_json=bool(args.json))


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

    try:
        timeout_s = int(jenkins_cfg.get("deploy_timeout_sec") or 0)
        if timeout_s <= 0:
            validation_errors.append("jenkins.deploy_timeout_sec must be a positive integer")
    except Exception:
        validation_errors.append("jenkins.deploy_timeout_sec must be a positive integer")

    missing.extend(validation_errors)

    if missing:
        raise APError("Doctor found blocking config issues:\n- " + "\n- ".join(missing))

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

    s = sp.add_parser("structure-check")
    s.add_argument("--scope", choices=sorted(_GATE_SCOPES), default="")
    s.add_argument("--base")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_structure_check)

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
