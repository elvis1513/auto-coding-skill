#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoPipeline Pro Max - repo automation CLI (python)"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import datetime as _dt
import fnmatch
import json
import os
import posixpath
import re
import socket
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Iterator, Optional, List

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

from core import APError, ensure_git_repo, copy_tree, run, load_yaml, find_config, run_shell, http_get_status
from scaffold_templates import scaffold_groups, templates_for


_JENKINS_CRUMB_CACHE: dict[str, dict[str, str]] = {}
_INVALID_PLACEHOLDERS = {"N/A", "TODO", "TBD", "CHANGEME", "CHANGE_ME", "FILL_ME", "FILL-ME", "PLACEHOLDER", "XXX", "NULL", "~"}
_GENERATED_NOISE_PATTERNS = [
    ".local/auto-coding-skill/**",
    "__pycache__/**",
    "**/__pycache__/**",
    "*.pyc",
    "**/*.pyc",
    ".DS_Store",
    "**/.DS_Store",
]
_AGENT_CONTRACT_VERSION = 1
_AGENT_CONTRACT_SCHEMA = "data/contracts/orchestration-v1.schema.json"
_DEFAULT_DISPOSABLE_IGNORED_PATTERNS = [
    ".local/auto-coding-skill",
    ".local/auto-coding-skill/**",
    "node_modules",
    "node_modules/**",
    "**/node_modules",
    "**/node_modules/**",
    "target",
    "target/**",
    "**/target",
    "**/target/**",
    "dist",
    "dist/**",
    "**/dist",
    "**/dist/**",
    "build",
    "build/**",
    "**/build",
    "**/build/**",
    "coverage",
    "coverage/**",
    "**/coverage",
    "**/coverage/**",
    ".pytest_cache",
    ".pytest_cache/**",
    "**/.pytest_cache",
    "**/.pytest_cache/**",
    ".mypy_cache",
    ".mypy_cache/**",
    "**/.mypy_cache",
    "**/.mypy_cache/**",
    ".ruff_cache",
    ".ruff_cache/**",
    "**/.ruff_cache",
    "**/.ruff_cache/**",
    "__pycache__",
    "__pycache__/**",
    "**/__pycache__",
    "**/__pycache__/**",
    "*.pyc",
    "**/*.pyc",
    ".DS_Store",
    "**/.DS_Store",
]


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
    manifest = _active_task_manifest(repo)
    if manifest:
        docs_cfg = cfg.get("docs") or {}
        task_dir = _text(docs_cfg.get("task_evidence_dir")) or "docs/tasks/evidence"
        return Path(repo, task_dir, f"{manifest['task_id']}.jsonl")
    return Path(repo, ".local/auto-coding-skill/evidence.jsonl")


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


def _copy_conflicts(src: Path, dst: Path) -> list[Path]:
    if src.is_file():
        return [dst] if dst.exists() else []
    conflicts: list[Path] = []
    for path in _iter_files(src):
        target = dst / path.relative_to(src)
        if target.exists():
            conflicts.append(target)
    return conflicts


_MANAGED_EXTRA_CLEANUP_DIRS = {
    Path("data/templates/bridges"),
}

_CORE_DOC_TEMPLATES = [
    Path("tasks/taskbook.md"),
    Path("tasks/closure-log.md"),
]


def _inferred_gate_commands(repo: Path) -> dict[str, str]:
    package_json = repo / "package.json"
    if not package_json.exists():
        return {}
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except Exception:
        return {}
    scripts = payload.get("scripts") or {}
    if not isinstance(scripts, dict):
        return {}
    if isinstance(scripts.get("test:changed"), str) and scripts["test:changed"].strip():
        return {"gate_changed": "npm run test:changed"}
    return {}


def _initialize_engineering_defaults(path: Path, repo: Path) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    updated = text.replace(
        'project:\n  name: ""',
        f"project:\n  name: {json.dumps(repo.name, ensure_ascii=False)}",
        1,
    )
    for key, gate_command in _inferred_gate_commands(repo).items():
        for default_value in ['""', '"git diff --check"']:
            candidate = updated.replace(
                f"  {key}: {default_value}",
                f"  {key}: {json.dumps(gate_command)}",
                1,
            )
            if candidate != updated:
                updated = candidate
                break
    if updated != text:
        path.write_text(updated, encoding="utf-8")


def _migrate_fast_development_defaults(cfg: dict, repo: Path) -> list[str]:
    changed: list[str] = []

    workflow_cfg = cfg.setdefault("workflow", {})
    if not isinstance(workflow_cfg, dict):
        workflow_cfg = {}
        cfg["workflow"] = workflow_cfg
    if _text(workflow_cfg.get("mode")).lower() != "dev":
        workflow_cfg["mode"] = "dev"
        changed.append("workflow.mode")
    if _text(workflow_cfg.get("completion")).lower() != "push":
        workflow_cfg["completion"] = "push"
        changed.append("workflow.completion")

    commands_cfg = cfg.setdefault("commands", {})
    if not isinstance(commands_cfg, dict):
        commands_cfg = {}
        cfg["commands"] = commands_cfg
    current_changed_gate = _text(commands_cfg.get("gate_changed"))
    if current_changed_gate in {"", "npm test"}:
        replacement = _inferred_gate_commands(repo).get("gate_changed", "git diff --check")
        if current_changed_gate != replacement:
            commands_cfg["gate_changed"] = replacement
            changed.append("commands.gate_changed")

    gate_cfg = cfg.setdefault("gate", {})
    if not isinstance(gate_cfg, dict):
        gate_cfg = {}
        cfg["gate"] = gate_cfg
    for key in ["default_scope", "fallback_scope", "no_change_scope"]:
        if _text(gate_cfg.get(key)).lower() != "changed":
            gate_cfg[key] = "changed"
            changed.append(f"gate.{key}")
    if _bool_config(gate_cfg.get("full_on_unknown"), False):
        gate_cfg["full_on_unknown"] = False
        changed.append("gate.full_on_unknown")

    concurrency_cfg = cfg.setdefault("concurrency", {})
    if not isinstance(concurrency_cfg, dict):
        concurrency_cfg = {}
        cfg["concurrency"] = concurrency_cfg
    if _text(concurrency_cfg.get("isolation")).lower() != "worktree":
        concurrency_cfg["isolation"] = "worktree"
        changed.append("concurrency.isolation")

    return changed


def cmd_scaffold(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    group = str(args.group or "").strip().lower()
    try:
        selected = templates_for(group)
    except KeyError as exc:
        choices = ", ".join(scaffold_groups() + ["all"])
        raise APError(f"Unknown scaffold group '{group}'. Choose one of: {choices}") from exc

    write = bool(args.write)
    force = bool(args.force)
    actions: list[dict] = []
    for rel, content in sorted(selected.items()):
        path = repo / rel
        if path.exists() and not force:
            actions.append({"path": rel, "action": "exists"})
            continue
        action = "write" if write else "would-write"
        actions.append({"path": rel, "action": action})
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    result = {"group": group, "mode": "write" if write else "plan", "actions": actions}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    for item in actions:
        print(f"[scaffold] {item['action']}: {item['path']}")
    if not write:
        print("[scaffold] plan only; re-run with --write to create missing files")


def cmd_install(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    templates = _skill_root() / "data" / "templates"

    planned_copies = [(templates / "ENGINEERING.md", repo / "docs" / "ENGINEERING.md")]
    for rel in _CORE_DOC_TEMPLATES:
        planned_copies.append((templates / "docs" / rel, repo / "docs" / rel))

    if args.bridges:
        planned_copies.append((templates / "bridges" / "AGENTS.md", repo / "AGENTS.md"))

    tools_dir = repo / "docs" / "tools" / "autopipeline"
    planned_copies.append((templates / "tools" / "ap.py", tools_dir / "ap.py"))

    conflicts: list[Path] = []
    for src, dst in planned_copies:
        conflicts.extend(_copy_conflicts(src, dst))
    if conflicts and not args.force:
        conflict_list = "\n".join(f"- {_repo_rel(repo, path)}" for path in conflicts[:20])
        extra = "" if len(conflicts) <= 20 else f"\n- ... and {len(conflicts) - 20} more"
        raise APError(
            "Install would overwrite existing files:\n"
            f"{conflict_list}{extra}\n"
            "For existing projects, run `ap.py upgrade --dry-run` then `ap.py upgrade --write`. "
            "Use `install --force` only when intentionally resetting generated docs/tooling."
        )

    for src, dst in planned_copies:
        copy_tree(src, dst)

    _initialize_engineering_defaults(repo / "docs" / "ENGINEERING.md", repo)
    if args.full:
        cmd_scaffold(
            argparse.Namespace(repo=str(repo), group="all", write=True, force=args.force, json=False)
        )

    layout = "full" if args.full else "minimal"
    print(f"[install] OK: {layout} scaffold installed into {repo}")
    print(
        "[install] Next: fill every access.* URL, username, and password in "
        "docs/ENGINEERING.md, run doctor, and commit that file into Git."
    )


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
        (
            source_root / "data" / "templates" / "tools" / "ap.py",
            repo / "docs" / "tools" / "autopipeline" / "ap.py",
        ),
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
                if rel.parts[:3] == ("data", "templates", "docs"):
                    continue
                if rel.parent in _MANAGED_EXTRA_CLEANUP_DIRS:
                    add_action("skill", dst, "delete", "stale managed template")
                    if write:
                        dst.unlink()
                else:
                    add_action("skill", dst, "extra", "present only in project copy")
    else:
        add_action("skill", project_skill, "create", "install runtime required by the project launcher")
        if write:
            copy_tree(source_root, project_skill)

    docs_template = templates / "docs"
    for rel in _CORE_DOC_TEMPLATES:
        src = docs_template / rel
        if not src.exists():
            continue
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
        migrated_keys = _migrate_fast_development_defaults(merged_cfg, repo)
        if added_keys or migrated_keys:
            detail_parts = []
            if added_keys:
                detail_parts.append("add " + ", ".join(added_keys))
            if migrated_keys:
                detail_parts.append("migrate " + ", ".join(migrated_keys))
            add_action("config", engineering, "merge", "; ".join(detail_parts))
            if write:
                _write_frontmatter_markdown(engineering, merged_cfg, body)
        else:
            add_action("config", engineering, "ok")
    elif template_engineering.exists():
        add_action("config", engineering, "create")
        if write:
            copy_tree(template_engineering, engineering)
            _initialize_engineering_defaults(engineering, repo)

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

## 1. 目标与开发闭环
- 目标：TODO
- 开发结论：DEV-CLOSED / BLOCKED — TODO

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
- 本地快速门禁：changed gate + diff-check — TODO
- 项目 Git hooks：commit/push 时执行
- 结构化证据：docs/tasks/evidence.jsonl — TODO
- 门禁画像：.local/auto-coding-skill/gate-profile.jsonl — TODO
- 目标分支推送：TODO
- Jenkins / 构建 / 部署 / 实际验收：项目负责人推送后处理
- 可选诊断（如明确要求）：`{regression_matrix}`

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
        raise APError(
            f"Matrix not found: {matrix}. Create it with `ap.py scaffold testing --write`."
        )

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
    local_root = _skill_root()
    project_root = repo / ".agents" / "skills" / "auto-coding-skill"
    global_root = Path.home() / ".agents" / "skills" / "auto-coding-skill"

    # The runtime executing this command is authoritative. In particular, a
    # modern project copy must not be overwritten by an older global copy.
    candidates = [local_root, project_root, global_root]

    unique: list[Path] = []
    seen: set[Path] = set()
    for root in candidates:
        if root in seen:
            continue
        seen.add(root)
        unique.append(root)
    return unique


def _find_skill_asset_root(repo: Path) -> Path:
    candidates = _candidate_skill_roots(repo)

    def is_asset_root(root: Path) -> bool:
        return (root / "data" / "templates").exists() and (root / "scripts" / "ap.py").exists()

    def has_modern_layout(root: Path) -> bool:
        return (
            is_asset_root(root)
            and (root / "data" / "templates" / "tools" / "ap.py").exists()
            and (root / "scripts" / "scaffold_templates.py").exists()
        )

    for root in candidates:
        if has_modern_layout(root):
            return root
    for root in candidates:
        if is_asset_root(root):
            return root
    raise APError(
        "Cannot find auto-coding-skill asset root. Run `autocoding init --mode global --force` "
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
    if mode != "dev":
        raise APError("workflow.mode must be 'dev'; external verification is owner-managed after push.")
    return mode


def _text(value: object) -> str:
    return str(value or "").strip()


_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _concurrency_cfg(cfg: dict) -> dict:
    value = cfg.get("concurrency") or {}
    return value if isinstance(value, dict) else {}


def _task_isolation(cfg: dict) -> str:
    isolation = _text(_concurrency_cfg(cfg).get("isolation")).lower() or "worktree"
    if isolation != "worktree":
        raise APError(
            "concurrency.isolation must be worktree; shared-checkout/legacy writes are no longer supported"
        )
    return isolation


def _cleanup_policy(cfg: dict) -> dict:
    concurrency_cfg = _concurrency_cfg(cfg)
    return {
        "cleanup_merged": _bool_config(concurrency_cfg.get("cleanup_merged"), True),
        "delete_remote_branch": _bool_config(concurrency_cfg.get("delete_remote_branch"), True),
        "disposable_ignored": [
            _text(item)
            for item in _as_list(concurrency_cfg.get("disposable_ignored"))
            if _text(item)
        ],
    }


def _manifest_cleanup_policy(manifest: dict, fallback_cfg: dict) -> dict:
    value = manifest.get("cleanup_policy")
    return value if isinstance(value, dict) else _cleanup_policy(fallback_cfg)


def _validate_task_id(task_id: str) -> str:
    value = _text(task_id)
    if not _TASK_ID_RE.fullmatch(value) or value.endswith(".lock") or ".." in value:
        raise APError(
            "Task ID must be 1-64 characters using letters, digits, '.', '_' or '-', "
            "must start with a letter/digit, and cannot contain '..' or end with '.lock'."
        )
    return value


def _resolve_git_dir(repo: Path, option: str) -> Path:
    result = run(["git", "rev-parse", option], cwd=repo, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        raise APError(f"Cannot resolve {option} for Git repository: {repo}")
    value = Path(result.stdout.strip())
    if not value.is_absolute():
        value = repo / value
    return value.resolve()


def _git_common_dir(repo: Path) -> Path:
    return _resolve_git_dir(repo, "--git-common-dir")


def _git_dir(repo: Path) -> Path:
    return _resolve_git_dir(repo, "--git-dir")


def _task_state_root(repo: Path) -> Path:
    return _git_common_dir(repo) / "auto-coding-skill"


def _task_registry_path(repo: Path, task_id: str) -> Path:
    return _task_state_root(repo) / "tasks" / f"{_validate_task_id(task_id)}.json"


def _worktree_manifest_path(repo: Path) -> Path:
    return _git_dir(repo) / "auto-coding-skill-task.json"


def _read_json_object(path: Path) -> Optional[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json_object(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _active_task_manifest(repo: Path) -> Optional[dict]:
    try:
        return _read_json_object(_worktree_manifest_path(repo))
    except APError:
        return None


def _validate_task_manifest(repo: Path, manifest: dict, expected_task_id: str = "") -> dict:
    task_id = _validate_task_id(_text(manifest.get("task_id")))
    if expected_task_id and task_id != _validate_task_id(expected_task_id):
        raise APError(
            f"Task registry identity mismatch: expected={expected_task_id}, manifest={task_id}"
        )
    task_uuid = _text(manifest.get("task_uuid"))
    if not re.fullmatch(r"[0-9a-f]{32}", task_uuid):
        raise APError(f"Invalid task manifest UUID for {task_id}; refusing Git operations.")
    task_branch = _text(manifest.get("task_branch"))
    if not task_branch.endswith(f"/{task_id}") or run(
        ["git", "check-ref-format", "--branch", task_branch],
        cwd=repo,
        check=False,
    ).returncode != 0:
        raise APError(f"Invalid task branch in manifest for {task_id}: {task_branch!r}")
    target_branch = _text(manifest.get("target_branch"))
    if run(
        ["git", "check-ref-format", "--branch", target_branch],
        cwd=repo,
        check=False,
    ).returncode != 0:
        raise APError(f"Invalid target branch in manifest for {task_id}: {target_branch!r}")
    remote = _text(manifest.get("remote"))
    if not remote or remote.startswith("-") or any(char in remote for char in "\0\r\n"):
        raise APError(f"Invalid remote in manifest for {task_id}: {remote!r}")
    base_sha = _text(manifest.get("base_sha"))
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", base_sha):
        raise APError(f"Invalid base commit in manifest for {task_id}: {base_sha!r}")
    worktree_raw = _text(manifest.get("worktree_path"))
    control_raw = _text(manifest.get("control_worktree_path"))
    worktree = Path(worktree_raw)
    control = Path(control_raw)
    if not worktree_raw or not control_raw or not worktree.is_absolute() or not control.is_absolute():
        raise APError(f"Task manifest paths must be absolute for {task_id}.")
    worktree = worktree.resolve()
    control = control.resolve()
    if worktree == control or control in worktree.parents or worktree in control.parents:
        raise APError(
            f"Task worktree must be outside its control checkout for {task_id}: {worktree}"
        )
    owned_paths = manifest.get("owned_paths")
    if not isinstance(owned_paths, list) or not owned_paths or not all(
        isinstance(item, str) and item for item in owned_paths
    ):
        raise APError(f"Task {task_id} has no valid owned_paths; refusing lifecycle operations.")
    depends_on = manifest.get("depends_on")
    prerequisite_shas = manifest.get("prerequisite_shas")
    if not isinstance(depends_on, list) or not isinstance(prerequisite_shas, dict):
        raise APError(f"Task {task_id} has an invalid dependency contract.")
    if set(depends_on) != set(prerequisite_shas):
        raise APError(f"Task {task_id} dependency IDs and prerequisite SHAs do not match.")
    for dependency, sha in prerequisite_shas.items():
        _validate_task_id(str(dependency))
        if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", _text(sha)):
            raise APError(f"Task {task_id} has an invalid prerequisite SHA for {dependency}.")
    lease = manifest.get("writer_lease")
    if not isinstance(lease, dict) or not _text(lease.get("holder")):
        raise APError(f"Task {task_id} has an invalid writer lease.")
    if int(lease.get("generation") or 0) < 1 or _text(lease.get("state")) != "active":
        raise APError(f"Task {task_id} writer lease is not active.")
    review = manifest.get("review")
    if not isinstance(review, dict) or _text(review.get("verdict")) not in {
        "pending",
        "approved",
        "changes-requested",
    }:
        raise APError(f"Task {task_id} has an invalid review contract.")
    return manifest


def _load_task_manifest(repo: Path, task_id: str) -> dict:
    path = _task_registry_path(repo, task_id)
    manifest = _read_json_object(path)
    if not manifest:
        raise APError(
            f"Task is not registered: {task_id}. Run `ap.py task-start {task_id}` first."
        )
    return _validate_task_manifest(repo, manifest, task_id)


def _save_task_manifest(repo: Path, manifest: dict) -> None:
    _validate_task_manifest(repo, manifest)
    task_id = _validate_task_id(_text(manifest.get("task_id")))
    manifest["updated_at"] = _now_iso()
    _write_json_object(_task_registry_path(repo, task_id), manifest)
    worktree_value = _text(manifest.get("worktree_path"))
    if worktree_value:
        worktree = Path(worktree_value)
        if worktree.exists():
            try:
                _write_json_object(_worktree_manifest_path(worktree), manifest)
            except APError:
                pass


def _delete_task_manifest(repo: Path, manifest: dict) -> None:
    task_id = _validate_task_id(_text(manifest.get("task_id")))
    _task_registry_path(repo, task_id).unlink(missing_ok=True)


def _current_branch(repo: Path) -> str:
    result = run(["git", "branch", "--show-current"], cwd=repo, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def _require_control_checkout(repo: Path, manifest: Optional[dict] = None) -> None:
    if _active_task_manifest(repo):
        raise APError("Run this command from the primary/control checkout, not from a task worktree.")
    if _git_dir(repo) != _git_common_dir(repo):
        raise APError("Run this command from the primary/control checkout, not from a linked worktree.")
    if manifest:
        expected = _text(manifest.get("control_worktree_path"))
        if expected and repo.resolve() != Path(expected).resolve():
            raise APError(f"Task control checkout mismatch: current={repo.resolve()}, expected={expected}")


def _resolve_commit(repo: Path, ref: str) -> str:
    result = run(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=repo, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        raise APError(f"Cannot resolve Git commit: {ref}")
    return result.stdout.strip()


def _git_z_paths(repo: Path, command: list[str]) -> list[str]:
    result = run(command, cwd=repo, check=False)
    if result.returncode != 0:
        return []
    return [item for item in result.stdout.split("\0") if item]


def _checked_git_z_paths(repo: Path, command: list[str], context: str) -> list[str]:
    result = run(command, cwd=repo, check=False)
    if result.returncode != 0:
        raise APError(
            f"Cannot inspect {context}: {result.stderr.strip() or result.stdout.strip()}"
        )
    return [item for item in result.stdout.split("\0") if item]


def _working_tree_paths(repo: Path) -> list[str]:
    paths: set[str] = set()
    paths.update(
        _git_z_paths(
            repo,
            ["git", "diff", "--name-only", "-z", "--diff-filter=ACDMRTUXB"],
        )
    )
    paths.update(
        _git_z_paths(
            repo,
            ["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACDMRTUXB"],
        )
    )
    paths.update(
        _git_z_paths(repo, ["git", "ls-files", "--others", "--exclude-standard", "-z"])
    )
    return sorted(path.replace("\\", "/") for path in paths if path)


def _task_runtime_paths(repo: Path, cfg: dict, manifest: Optional[dict]) -> set[str]:
    docs_cfg = cfg.get("docs") or {}
    gate_cfg = _gate_cfg(cfg)
    paths = {
        _text(gate_cfg.get("profile_log")) or ".local/auto-coding-skill/gate-profile.jsonl",
    }
    if manifest:
        task_id = _validate_task_id(_text(manifest.get("task_id")))
        evidence_dir = _text(docs_cfg.get("task_evidence_dir")) or "docs/tasks/evidence"
        paths.add(f"{evidence_dir.rstrip('/')}/{task_id}.jsonl")
    else:
        paths.add(_text(docs_cfg.get("evidence_log")) or "docs/tasks/evidence.jsonl")
    normalized: set[str] = set()
    for path in paths:
        value = path.replace("\\", "/")
        if value.startswith("./"):
            value = value[2:]
        if value:
            normalized.add(value)
    return normalized


def _task_content_fingerprint(repo: Path, cfg: dict, manifest: Optional[dict]) -> str:
    runtime_paths = _task_runtime_paths(repo, cfg, manifest)
    relevant = [
        path
        for path in _working_tree_paths(repo)
        if path not in runtime_paths and not _is_generated_noise_path(path)
    ]
    digest = hashlib.sha256()
    digest.update(f"branch:{_current_branch(repo)}\n".encode("utf-8"))
    digest.update(f"head:{_resolve_commit(repo, 'HEAD')}\n".encode("utf-8"))
    for rel in relevant:
        digest.update(rel.encode("utf-8", errors="surrogateescape"))
        path = repo / rel
        try:
            digest.update(f"mode:{path.lstat().st_mode:o}".encode("ascii"))
        except OSError:
            digest.update(b"mode:<missing>")
        if path.is_symlink():
            try:
                digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
            except OSError:
                digest.update(b"<unreadable-symlink>")
        elif path.is_file():
            try:
                digest.update(path.read_bytes())
            except OSError:
                digest.update(b"<unreadable>")
        else:
            digest.update(b"<missing>")
    for start in range(0, len(relevant), 100):
        batch = relevant[start : start + 100]
        if not batch:
            continue
        cached = run(
            ["git", "diff", "--cached", "--binary", "--no-ext-diff", "--", *batch],
            cwd=repo,
            check=False,
        )
        digest.update(cached.stdout.encode("utf-8", errors="surrogateescape"))
        unstaged = run(
            ["git", "diff", "--binary", "--no-ext-diff", "--", *batch],
            cwd=repo,
            check=False,
        )
        digest.update(unstaged.stdout.encode("utf-8", errors="surrogateescape"))
        index_state = run(
            ["git", "ls-files", "--stage", "-z", "--", *batch],
            cwd=repo,
            check=False,
        )
        digest.update(index_state.stdout.encode("utf-8", errors="surrogateescape"))
    return digest.hexdigest()


def _stage_exact_paths(repo: Path, paths: list[str]) -> list[str]:
    expected = sorted(set(path for path in paths if path))
    for start in range(0, len(expected), 100):
        run(["git", "add", "-A", "--", *expected[start : start + 100]], cwd=repo)
    staged = sorted(
        set(
            _checked_git_z_paths(
                repo,
                [
                    "git",
                    "diff",
                    "--cached",
                    "--name-only",
                    "-z",
                    "--diff-filter=ACDMRTUXB",
                ],
                "staged task paths",
            )
        )
    )
    unexpected = sorted(set(staged) - set(expected))
    if unexpected:
        raise APError(
            "Refusing to commit paths outside the current task:\n- " + "\n- ".join(unexpected)
        )
    return staged


def _task_commit_paths(repo: Path) -> list[str]:
    return [path for path in _working_tree_paths(repo) if not _is_generated_noise_path(path)]


def _normalize_owned_path(value: object) -> str:
    raw = _text(value).replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    normalized = posixpath.normpath(raw)
    if (
        not raw
        or raw.startswith("/")
        or normalized == ".."
        or normalized.startswith("../")
        or normalized == ".git"
        or normalized.startswith(".git/")
    ):
        raise APError(f"Owned paths must be safe repository-relative paths: {value!r}")
    return normalized


def _path_is_owned(path: str, owned_paths: list[str]) -> bool:
    normalized = _normalize_owned_path(path)
    return any(
        owner == "." or normalized == owner or normalized.startswith(owner.rstrip("/") + "/")
        for owner in owned_paths
    )


def _task_managed_paths(cfg: dict, manifest: dict) -> list[str]:
    docs_cfg = cfg.get("docs") or {}
    task_id = _validate_task_id(_text(manifest.get("task_id")))
    return sorted(
        {
            f"{(_text(docs_cfg.get('active_task_dir')) or 'docs/tasks/active').rstrip('/')}/{task_id}.md",
            f"{(_text(docs_cfg.get('task_closure_dir')) or 'docs/tasks/closures').rstrip('/')}/{task_id}.md",
            f"{(_text(docs_cfg.get('task_evidence_dir')) or 'docs/tasks/evidence').rstrip('/')}/{task_id}.jsonl",
        }
    )


def _task_changed_paths_from_base(repo: Path, base_sha: str) -> list[str]:
    paths = set(
        _checked_git_z_paths(
            repo,
            ["git", "diff", "--name-only", "-z", "--diff-filter=ACDMRTUXB", base_sha, "--"],
            "task diff paths",
        )
    )
    paths.update(
        _checked_git_z_paths(
            repo,
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            "task untracked paths",
        )
    )
    return sorted(path.replace("\\", "/") for path in paths if not _is_generated_noise_path(path))


def _task_unowned_paths(repo: Path, cfg: dict, manifest: dict) -> list[str]:
    owned = [_normalize_owned_path(item) for item in manifest.get("owned_paths") or []]
    managed = set(_task_managed_paths(cfg, manifest))
    return [
        path
        for path in _task_changed_paths_from_base(repo, _text(manifest.get("base_sha")))
        if path not in managed and not _path_is_owned(path, owned)
    ]


def _task_review_fingerprint(repo: Path, manifest: dict, cfg: Optional[dict] = None) -> str:
    base_sha = _text(manifest.get("base_sha"))
    owned = [_normalize_owned_path(item) for item in manifest.get("owned_paths") or []]
    managed = set(_task_managed_paths(cfg or _load_cfg(repo), manifest))
    paths = [
        path
        for path in _task_changed_paths_from_base(repo, base_sha)
        if path not in managed and _path_is_owned(path, owned)
    ]
    digest = hashlib.sha256()
    digest.update(f"contract:{_AGENT_CONTRACT_VERSION}\nbase:{base_sha}\n".encode("utf-8"))
    for rel in paths:
        digest.update(f"path:{rel}\0".encode("utf-8", errors="surrogateescape"))
        path = repo / rel
        try:
            mode = path.lstat().st_mode
        except OSError:
            digest.update(b"missing\0")
            continue
        digest.update(f"mode:{mode:o}\0".encode("ascii"))
        if path.is_symlink():
            digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
        elif path.is_file():
            digest.update(path.read_bytes())
        else:
            digest.update(b"non-file")
        digest.update(b"\0")
    return digest.hexdigest()


def _invalidate_task_review(manifest: dict, reason: str) -> None:
    manifest["review"] = {
        "verdict": "pending",
        "diff_base": _text(manifest.get("base_sha")),
        "diff_head": "",
        "diff_fingerprint": "",
        "reviewer": "",
        "reviewed_at": "",
        "reason": reason,
    }


def _actor_id(args: argparse.Namespace, field: str = "writer") -> str:
    actor = _text(getattr(args, field, "")) or _text(os.environ.get("CODEX_THREAD_ID"))
    if not actor:
        raise APError(f"A stable --{field.replace('_', '-')} or CODEX_THREAD_ID is required.")
    if any(char in actor for char in "\0\r\n"):
        raise APError("Actor identity contains invalid characters.")
    return actor


def _require_current_writer(manifest: dict, args: argparse.Namespace) -> str:
    actor = _actor_id(args, "writer")
    lease = manifest.get("writer_lease") or {}
    if _text(lease.get("state")) != "active" or actor != _text(lease.get("holder")):
        raise APError(
            f"Writer lease mismatch: current={actor}, holder={_text(lease.get('holder')) or '(missing)'}."
        )
    return actor


def _require_dependencies(repo: Path, manifest: dict, ancestor_ref: str) -> None:
    for dependency in manifest.get("depends_on") or []:
        sha = _text((manifest.get("prerequisite_shas") or {}).get(dependency))
        if run(
            ["git", "merge-base", "--is-ancestor", sha, ancestor_ref],
            cwd=repo,
            check=False,
        ).returncode != 0:
            raise APError(
                f"Prerequisite {dependency} at {sha} is not integrated into {ancestor_ref}."
            )


def _require_approved_review(repo: Path, cfg: dict, manifest: dict) -> str:
    unowned = _task_unowned_paths(repo, cfg, manifest)
    if unowned:
        raise APError("Changes outside task owned_paths:\n- " + "\n- ".join(unowned))
    fingerprint = _task_review_fingerprint(repo, manifest)
    review = manifest.get("review") or {}
    if _text(review.get("verdict")) != "approved":
        raise APError("Task review must be approved before commit-push or integration.")
    if _text(review.get("diff_fingerprint")) != fingerprint:
        raise APError("Approved review fingerprint is stale for the current owned diff.")
    if _text(review.get("diff_base")) != _text(manifest.get("base_sha")):
        raise APError("Approved review base is stale for the current task base.")
    return fingerprint


def _unstaged_task_paths(repo: Path) -> list[str]:
    paths = set(
        _checked_git_z_paths(
            repo,
            ["git", "diff", "--name-only", "-z", "--diff-filter=ACDMRTUXB"],
            "unstaged task paths",
        )
    )
    paths.update(
        _checked_git_z_paths(
            repo,
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            "untracked task paths",
        )
    )
    return sorted(path for path in paths if not _is_generated_noise_path(path))


def _require_task_context(repo: Path, cfg: dict, task_id: str) -> dict:
    _task_isolation(cfg)
    manifest = _active_task_manifest(repo)
    if not manifest:
        if _git_dir(repo) != _git_common_dir(repo):
            raise APError(
                "This linked worktree has no registered task manifest. "
                "return to the primary checkout and create or recover the task with task-start."
            )
        raise APError(
            "This project requires an isolated task worktree. "
            f"Run `python3 docs/tools/autopipeline/ap.py task-start {task_id}` from the main checkout, "
            "then continue in the returned worktree."
        )
    expected_task = _validate_task_id(task_id)
    actual_task = _text(manifest.get("task_id"))
    if actual_task != expected_task:
        raise APError(
            f"Task/worktree mismatch: command={expected_task}, worktree={actual_task or '(missing)'}."
        )
    registered = _read_json_object(_task_registry_path(repo, expected_task))
    if not registered:
        raise APError(f"Task registry entry is missing for {expected_task}; refusing to recreate it implicitly.")
    for field in ("task_id", "task_uuid", "task_branch", "worktree_path", "base_sha"):
        if _text(registered.get(field)) != _text(manifest.get(field)):
            raise APError(f"Task manifest/registry mismatch for {expected_task}: {field}")
    manifest = registered
    expected_path = Path(_text(manifest.get("worktree_path"))).resolve()
    if repo.resolve() != expected_path:
        raise APError(f"Task manifest belongs to {expected_path}, not {repo.resolve()}.")
    branch = _current_branch(repo)
    expected_branch = _text(manifest.get("task_branch"))
    if not branch or branch != expected_branch:
        raise APError(
            f"Task branch mismatch: current={branch or '(detached)'}, expected={expected_branch}."
        )
    if _text(manifest.get("state")) in {"integrated", "finished"}:
        raise APError(f"Task {expected_task} is already {_text(manifest.get('state'))}.")
    return manifest


@contextlib.contextmanager
def _repo_lock(repo: Path, name: str, timeout_s: float = 30.0) -> Iterator[None]:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or "repository"
    lock_path = _task_state_root(repo) / "locks" / f"{safe_name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            import fcntl  # type: ignore
        except ImportError as exc:  # pragma: no cover - current runtime is POSIX
            raise APError("Task locking requires a POSIX fcntl runtime.") from exc
        deadline = time.time() + max(0.0, timeout_s)
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() >= deadline:
                    raise APError(f"Timed out waiting for repository lock: {name}")
                time.sleep(0.1)
        handle.seek(0)
        handle.truncate()
        handle.write(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "host": socket.gethostname(),
                    "acquired_at": _now_iso(),
                    "name": name,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        handle.flush()
        yield
    finally:
        try:
            import fcntl  # type: ignore

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        handle.close()


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


_REQUIRED_ACCESS_FIELDS = [
    "access.project.frontend.url",
    "access.project.frontend.username",
    "access.project.frontend.password",
    "access.project.backend.url",
    "access.project.backend.username",
    "access.project.backend.password",
    "access.jenkins.frontend.url",
    "access.jenkins.frontend.username",
    "access.jenkins.frontend.password",
    "access.jenkins.backend.url",
    "access.jenkins.backend.username",
    "access.jenkins.backend.password",
    "access.gitlab.url",
    "access.gitlab.username",
    "access.gitlab.password",
    "access.nexus.frontend.url",
    "access.nexus.frontend.username",
    "access.nexus.frontend.password",
]


def _nested_config_value(cfg: dict, field: str) -> object:
    value: object = cfg
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _access_config_issues(cfg: dict) -> list[str]:
    issues: list[str] = []
    for field in _REQUIRED_ACCESS_FIELDS:
        value = _nested_config_value(cfg, field)
        if not isinstance(value, str) or not _is_explicit_fill(value):
            issues.append(f"{field} (must be an explicitly filled string, not blank/TODO)")
    for field in [name for name in _REQUIRED_ACCESS_FIELDS if name.endswith(".url")]:
        _validate_url_field(issues, field, _nested_config_value(cfg, field))
    return issues


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
_WORKFLOW_PROFILES = {"auto", "micro", "standard", "high-risk"}
_PROFILE_GATE_SCOPE = {"micro": "changed", "standard": "changed", "high-risk": "changed"}
_PROFILE_RANK = {"micro": 0, "standard": 1, "high-risk": 2}
_SCOPE_RANK = {"changed": 0, "standard": 1, "full": 2}
_DOC_PATH_PATTERNS = ["*.md", "docs/**"]
_DEFAULT_FULL_PATH_PATTERNS = [
    ".agents/**",
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


def _is_generated_noise_path(path: str) -> bool:
    return _path_matches(path, _GENERATED_NOISE_PATTERNS)


def _unique_paths(paths: list[str]) -> list[str]:
    seen = set()
    out = []
    for path in paths:
        normalized = path.replace("\\", "/").strip()
        if _is_generated_noise_path(normalized):
            continue
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
    manifest = _active_task_manifest(repo)
    effective_base = base_ref or (_text(manifest.get("base_sha")) if manifest else "") or _default_base_ref(repo)
    if effective_base:
        paths.extend(_git_lines(repo, ["git", "diff", "--name-only", "--diff-filter=ACDMRTUXB", f"{effective_base}...HEAD"]))
    paths.extend(_git_lines(repo, ["git", "diff", "--name-only", "--diff-filter=ACDMRTUXB"]))
    paths.extend(_git_lines(repo, ["git", "diff", "--cached", "--name-only", "--diff-filter=ACDMRTUXB"]))
    paths.extend(_git_lines(repo, ["git", "ls-files", "--others", "--exclude-standard"]))
    return _unique_paths(paths)


def _commit_changed_files(repo: Path, ref: str) -> list[str]:
    commit_ref = _text(ref) or "HEAD"
    result = run(
        [
            "git",
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "-r",
            "--diff-filter=ACMRTUXB",
            commit_ref,
        ],
        cwd=repo,
        check=False,
    )
    if result.returncode != 0:
        return []
    return _unique_paths([line.strip() for line in result.stdout.splitlines() if line.strip()])


def _cleanup_generated_noise(repo: Path, protected_paths: Optional[set[str]] = None) -> None:
    protected = {path.replace("\\", "/") for path in (protected_paths or set())}
    candidates = [
        rel
        for rel in _git_z_paths(
            repo,
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        )
        if _is_generated_noise_path(rel) and rel.replace("\\", "/") not in protected
    ]
    for rel in candidates:
        path = repo / rel
        if path.is_file():
            path.unlink(missing_ok=True)
    for rel in sorted(candidates, key=lambda item: item.count("/"), reverse=True):
        parent = (repo / rel).parent
        while parent != repo and parent.name == "__pycache__":
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


def _docs_only(paths: list[str]) -> bool:
    return bool(paths) and all(_path_matches(path, _DOC_PATH_PATTERNS) for path in paths)


def _tests_only(paths: list[str]) -> bool:
    non_docs = [path for path in paths if not _path_matches(path, _DOC_PATH_PATTERNS)]
    if not non_docs:
        return False
    return all(
        re.search(r"(^|[/_.-])(test|tests|spec|specs)([/_.-]|$)", path.lower())
        for path in non_docs
    )


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
    scope = (requested_scope or _text(gate_cfg.get("default_scope")) or "changed").lower()
    if scope not in _GATE_SCOPES:
        raise APError("gate scope must be one of: " + ", ".join(sorted(_GATE_SCOPES)))

    matching_rules = _matching_gate_rules(paths, gate_cfg)
    requested = "auto" if scope == "auto" else scope
    reason = "local development gate is fixed to changed/quick scope"
    if requested not in {"auto", "changed"}:
        reason += f"; ignored requested scope={requested}"
    return "changed", [reason], matching_rules


def _impact_summary(
    cfg: dict,
    repo: Path,
    requested_scope: str,
    base_ref: str = "",
    changed_paths: Optional[list[str]] = None,
) -> dict:
    paths = _changed_files(repo, base_ref=base_ref) if changed_paths is None else _unique_paths(changed_paths)
    docs_cfg = cfg.get("docs") or {}
    ignored_runtime_paths = _task_runtime_paths(repo, cfg, _active_task_manifest(repo)) | {
        _text(docs_cfg.get("evidence_log")) or "docs/tasks/evidence.jsonl",
        _text(docs_cfg.get("closure_log")) or "docs/tasks/closure-log.md",
        _text(_gate_cfg(cfg).get("profile_log")) or ".local/auto-coding-skill/gate-profile.jsonl",
    }
    ignored_runtime_paths = {
        path[2:] if path.startswith("./") else path
        for path in ignored_runtime_paths
    }
    paths = [path for path in paths if path not in ignored_runtime_paths]
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
    if summary.get("profile"):
        print(f"[impact] profile={summary['profile']}")
    if summary.get("effective_mode"):
        print(f"[impact] effective_mode={summary['effective_mode']}")
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


def _run_changed_gate(repo: Path, cfg: dict, paths: list[str]) -> list[str]:
    # The generic scaffold uses this command as its whole fast gate. The
    # built-in diff check below covers working tree, index, and task commits, so
    # do not execute the narrower configured spelling first as a duplicate.
    if _configured_command(cfg, "gate_changed").strip() == "git diff --check":
        print("[gate] gate_changed is handled by the built-in diff check")
        return []

    fallback_commands = ["gate_changed"]
    if _docs_only(paths):
        fallback_commands.append("docs_check")
    command = _run_first_configured_command(repo, cfg, fallback_commands)
    if command:
        return [command]

    if _docs_only(paths):
        print("[gate] docs-only change with no changed-gate command configured; running built-in post checks only.")
        return ["docs_only_builtin"]

    fallback = _run_first_configured_command(repo, cfg, ["quick_test"])
    if fallback:
        return [fallback]

    raise APError(
        "Changed gate has no fast command. Add commands.gate_changed or commands.quick_test. "
        "gate.rules commands are never executed by the automatic development flow."
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
    command = _run_first_configured_command(repo, cfg, ["gate_full", "full_gate"])
    if not command:
        raise APError(
            "Optional full diagnostic is under-configured. Add commands.gate_full or "
            "commands.full_gate when you explicitly want to run it."
        )
    return [command]


def _run_git_diff_check(repo: Path, cfg: dict) -> None:
    print("[diff-check] working tree + index + task commits")
    start = time.time()
    run(["git", "diff", "--check"], cwd=repo)
    run(["git", "diff", "--cached", "--check"], cwd=repo)
    manifest = _active_task_manifest(repo)
    base_sha = _text(manifest.get("base_sha")) if manifest else ""
    if base_sha:
        run(["git", "diff", "--check", f"{base_sha}...HEAD"], cwd=repo)
    _record_gate_profile(repo, cfg, "diff_check", "pass", time.time() - start)
    _record_evidence(repo, cfg, "diff_check", "pass")
    print("[diff-check] OK")


_DEFAULT_STRUCTURE_ALLOW_PATTERNS = [
    ".git/**",
    ".agents/skills/**",
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


def _verification_cfg(cfg: dict) -> dict:
    value = cfg.get("verification") or {}
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


def _verification_required(cfg: dict, key: str, default: bool = True) -> bool:
    verification_cfg = _verification_cfg(cfg)
    required_key = f"{key}_required"
    enabled_key = f"{key}_enabled"
    if required_key in verification_cfg:
        return _bool_config(verification_cfg.get(required_key), default)
    if enabled_key in verification_cfg:
        return _bool_config(verification_cfg.get(enabled_key), default)
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

    for path in _unique_paths(_git_lines(repo, ["git", "ls-files", "--others", "--exclude-standard"])):
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
    "archived",
    "completed",
    "deployed",
    "done",
    "closed",
    "dev-closed",
    "external",
    "pass",
    "passed",
    "fail",
    "failed",
    "partial",
    "superseded",
    "完成",
    "已完成",
    "关闭",
    "已关闭",
    "已部署",
    "已归档",
    "外部依赖",
    "已转外部依赖",
    "被替代",
    "已替代",
    "废弃",
    "已废弃",
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
    normalized = re.sub(r"\s+", " ", status).strip().lower().strip("`*_")
    first_token = re.split(r"[\s/，,;；。()（）]+", normalized, maxsplit=1)[0].strip("`*_")
    if first_token in _CLOSED_TASK_STATUSES or normalized in _CLOSED_TASK_STATUSES:
        return True
    return normalized.startswith((
        "local pass",
        "local verified",
        "本地通过",
        "本地验证通过",
    ))


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
    taskbook_archive = Path(repo, str(paths.get("taskbook_archive") or ""))
    closure_archive = Path(repo, str(paths.get("closure_archive") or ""))
    design_archive_dir = Path(repo, str(paths.get("design_archive_dir") or ""))

    taskbook_sections = 0
    if taskbook_archive.is_file():
        _preamble, sections = _split_markdown_sections(
            taskbook_archive.read_text(encoding="utf-8"),
            _TASKBOOK_ARCHIVE_HEADING_RE,
        )
        taskbook_sections = len(sections)

    closure_sections = 0
    if closure_archive.is_file():
        _preamble, sections = _split_markdown_sections(
            closure_archive.read_text(encoding="utf-8"),
            _CLOSURE_ARCHIVE_HEADING_RE,
        )
        closure_sections = len(sections)

    design_files = 0
    if design_archive_dir.is_dir():
        design_files = sum(1 for path in design_archive_dir.rglob("*") if path.is_file())

    entry = (
        f"## {period}\n"
        f"- Generated: {_now_iso()}\n"
        f"- Taskbook archive: `{paths.get('taskbook_archive', '')}` ({taskbook_sections} sections)\n"
        f"- Closure archive: `{paths.get('closure_archive', '')}` ({closure_sections} sections)\n"
        f"- Design archive: `{paths.get('design_archive_dir', '')}` ({design_files} files)\n"
    )
    archive_index.parent.mkdir(parents=True, exist_ok=True)
    existing = archive_index.read_text(encoding="utf-8") if archive_index.exists() else ""
    period_section = re.compile(
        rf"^##\s+{re.escape(period)}\s*$.*?(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    retained = period_section.sub("", existing).rstrip()
    if not retained:
        retained = "# Docs Archive Index"
    archive_index.write_text(retained + "\n\n" + entry, encoding="utf-8")
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
    active_task_ids = {_normalize_task_id(section["id"]) for section in active_taskbook_sections}
    conflicting_closure_sections = [
        section for section in closure_sections if _normalize_task_id(section["id"]) in active_task_ids
    ]
    archivable_closure_sections = [
        section for section in closure_sections if _normalize_task_id(section["id"]) not in active_task_ids
    ]
    closure_ids = {_normalize_task_id(section["id"]) for section in archivable_closure_sections}
    closed_task_ids = {_normalize_task_id(section["id"]) for section in closed_taskbook_sections}
    archived_task_ids = closed_task_ids | closure_ids
    blocking = [
        f"closure record {section['id']} exists but the taskbook section is still active; update taskbook status to Done/Closed or repair the stale closure before archiving"
        for section in conflicting_closure_sections
    ]

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
            "closure_sections": len(archivable_closure_sections),
            "blocked_closure_sections": len(conflicting_closure_sections),
            "design_files": len(design_files),
            "active_taskbook_sections_after": len(active_taskbook_sections),
        },
        "archived_task_ids": sorted(archived_task_ids),
        "active_task_conflicts": sorted(_normalize_task_id(section["id"]) for section in conflicting_closure_sections),
        "blocking": blocking,
        "taskbook_preamble": taskbook_preamble,
        "active_taskbook_sections": active_taskbook_sections,
        "closed_taskbook_sections": closed_taskbook_sections,
        "closure_preamble": closure_preamble,
        "closure_sections": archivable_closure_sections,
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
        "active_task_conflicts": result.get("active_task_conflicts"),
        "blocking": result.get("blocking"),
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

    if write and plan.get("blocking"):
        raise APError("docs-ledger-archive has blocking issue(s):\n- " + "\n- ".join(plan["blocking"]))

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
        _print_limited("[docs-ledger-archive] blocking", public_result.get("blocking") or [])

    if plan.get("blocking"):
        raise APError(f"docs-ledger-archive blocked with {len(plan['blocking'])} issue(s)")

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
    enforcement = _text(structure_cfg.get("enforcement")).lower() or "advisory"
    if enforcement not in {"advisory", "blocking"}:
        raise APError("structure.enforcement must be 'advisory' or 'blocking'")
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

    require_baseline = _bool_config(optimization_cfg.get("require_baseline_for_global_review"), True)
    if require_baseline:
        missing_docs = [
            f"{key} missing on disk: {rel_path}"
            for key, rel_path in _configured_structure_docs(cfg).items()
            if rel_path and not Path(repo, rel_path).exists()
        ]
        if selected_scope == "full":
            blocking.extend(missing_docs)
        else:
            warnings.extend(missing_docs)

    if enforcement == "advisory" and blocking:
        warnings.extend(f"{message} [advisory]" for message in blocking)
        blocking = []

    result = {
        "scope": selected_scope,
        "enforcement": enforcement,
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
        words = {word for word in re.split(r"[^a-z0-9]+", lower) if word}
        if _path_matches(path, _DEFAULT_FULL_PATH_PATTERNS):
            categories.add("release_or_tooling")
        if words & {"migration", "migrations", "schema", "database", "db", "sql"} or lower.endswith(".sql"):
            categories.add("db")
        if any(token in lower for token in ["api", "controller", "handler", "route", "server"]):
            categories.add("api")
        if words & {"auth", "authentication", "authorization", "permission", "permissions", "role", "roles", "tenant", "security"}:
            categories.add("auth")
        if words & {"payment", "payments", "billing", "invoice", "invoices", "checkout", "order", "orders"}:
            categories.add("payment")
        if words & {"upload", "uploads", "download", "downloads", "attachment", "attachments"}:
            categories.add("file_transfer")
        if words & {"nginx", "gateway", "ingress"} or {"reverse", "proxy"} <= words:
            categories.add("gateway")
        if "production" in words or "prod" in words and "config" in words or ".env.prod" in lower:
            categories.add("prod_config")
        if any(token in lower for token in ["page", "component", "view", "frontend", "miniapp", ".tsx", ".jsx", ".vue", ".scss", ".css"]):
            categories.add("ui")
        if any(token in lower for token in ["test", "spec", "__tests__"]):
            categories.add("test")
        if lower.startswith("docs/") or lower.endswith(".md"):
            categories.add("docs")
        if any(token in lower for token in ["domain", "service", "usecase", "repository", "infrastructure", "adapter", "shared", "utils"]):
            categories.add("structure")
    return _classification_for_categories(categories, len(paths))


def _classification_for_categories(categories: set[str], file_count: int) -> dict:
    return {
        "categories": sorted(categories),
        "needs_dd": bool(
            categories
            & {"api", "db", "auth", "payment", "file_transfer", "gateway", "prod_config", "release_or_tooling"}
        )
        or file_count > 12,
        "needs_adr": bool(categories & {"structure", "release_or_tooling"}) and not categories <= {"docs"},
        "needs_browser": "ui" in categories,
        "needs_jenkins": bool(
            categories & {"release_or_tooling", "db", "auth", "payment", "gateway", "prod_config"}
        ),
        "needs_target": bool(
            categories & {"api", "db", "auth", "payment", "file_transfer", "gateway", "prod_config", "ui"}
        ),
    }


def _classify_intent(intent: str) -> list[str]:
    value = _text(intent).lower()
    keyword_categories = {
        "db": ["database", "migration", "schema", "sql", "数据库", "数据迁移", "表结构"],
        "api": ["api", "controller", "endpoint", "接口", "控制器"],
        "auth": ["auth", "permission", "security", "登录", "认证", "鉴权", "权限", "安全"],
        "payment": ["payment", "billing", "checkout", "支付", "账单", "结算"],
        "file_transfer": ["upload", "download", "上传", "下载", "附件"],
        "gateway": ["gateway", "ingress", "nginx", "网关", "反向代理"],
        "prod_config": ["production config", "prod config", "生产配置"],
        "release_or_tooling": ["release", "deploy", "jenkins", "nexus", "发布", "部署", "构建"],
        "ui": ["frontend", "page", "component", "ui", "前端", "页面", "组件", "界面"],
        "test": ["test", "spec", "测试"],
        "docs": ["documentation", "docs", "文档"],
        "structure": ["refactor", "architecture", "重构", "架构", "分层"],
    }
    return sorted(
        category
        for category, keywords in keyword_categories.items()
        if any(keyword in value for keyword in keywords)
    )


def _normalize_workflow_profile(value: object, default: str = "auto") -> str:
    profile = _text(value).lower() or default
    if profile not in _WORKFLOW_PROFILES:
        raise APError("workflow.profile must be one of: " + ", ".join(sorted(_WORKFLOW_PROFILES)))
    return profile


def _configured_workflow_profile(cfg: dict) -> str:
    return _normalize_workflow_profile((cfg.get("workflow") or {}).get("profile"))


def _recommended_agents(profile: str, categories: set[str], classification: dict) -> list[str]:
    roles: list[str] = []
    for stage in _agent_execution_plan(profile, categories, classification)["stages"]:
        for role in stage["roles"]:
            if role != "main" and role not in roles:
                roles.append(role)
    return roles


def _agent_contract_shape() -> tuple[dict, list[str]]:
    return (
        {
            "common": [
                "contract_version",
                "node_id",
                "task_id",
                "role",
                "base_sha",
                "scope",
                "depends_on",
                "acceptance",
            ],
            "writer": ["task_branch", "worktree_path", "owned_paths"],
            "reviewer": [
                "task_id",
                "diff_base",
                "diff_head",
                "diff_fingerprint",
                "owning_fixer",
            ],
        },
        [
            "contract_version",
            "node_id",
            "role",
            "task_id",
            "base_sha",
            "status",
            "summary",
            "depends_on",
            "owned_paths",
            "changed_paths",
            "diff_fingerprint",
            "evidence",
            "findings",
            "verdict",
            "risks",
            "next_owner",
        ],
    )


def _validate_agent_plan(plan: dict) -> dict:
    required = {
        "contract_version",
        "contract_schema",
        "strategy",
        "policies",
        "assignment_contract",
        "result_contract",
        "stages",
        "constraints",
    }
    missing = sorted(required - set(plan))
    if missing or plan.get("contract_version") != _AGENT_CONTRACT_VERSION:
        raise APError("Invalid agent plan contract: " + (", ".join(missing) or "version"))
    if plan.get("contract_schema") != _AGENT_CONTRACT_SCHEMA:
        raise APError("Invalid agent plan schema path.")
    if not all(
        isinstance(stage, dict)
        and {"id", "mode", "roles", "depends_on"} <= set(stage)
        for stage in plan.get("stages") or []
    ):
        raise APError("Invalid agent plan stage contract.")
    return plan


def _agent_execution_plan(profile: str, categories: set[str], classification: dict) -> dict:
    assignment_contract, result_contract = _agent_contract_shape()
    if profile == "micro":
        return _validate_agent_plan({
            "contract_version": _AGENT_CONTRACT_VERSION,
            "contract_schema": _AGENT_CONTRACT_SCHEMA,
            "strategy": "main-only",
            "policies": {
                "one_writer_per_worktree": True,
                "path_ownership": "explicit-non-overlapping",
                "dependency_policy": "integrate-before-dependent-start",
                "review_feedback_owner": "main",
                "review_binding": "diff-fingerprint",
                "lifecycle_owner": "main",
                "gate_owner": "main",
            },
            "assignment_contract": assignment_contract,
            "result_contract": result_contract,
            "stages": [
                {
                    "id": "delivery",
                    "mode": "serial",
                    "roles": ["main"],
                    "depends_on": [],
                }
            ],
            "constraints": [
                "Do not create subagents when the task has no independent work worth delegating.",
                "The main agent owns the fast gate, Git integration, push, and cleanup.",
            ],
        })

    discovery_roles = ["explorer"]
    if categories & {"api", "release_or_tooling"}:
        discovery_roles.append("docs_researcher")
    if classification.get("needs_browser"):
        discovery_roles.append("browser_debugger")

    return _validate_agent_plan({
        "contract_version": _AGENT_CONTRACT_VERSION,
        "contract_schema": _AGENT_CONTRACT_SCHEMA,
        "strategy": "orchestrated-subagents",
        "policies": {
            "one_writer_per_worktree": True,
            "path_ownership": "explicit-non-overlapping",
            "dependency_policy": "integrate-before-dependent-start",
            "review_feedback_owner": "owning-fixer",
            "review_binding": "diff-fingerprint",
            "lifecycle_owner": "main",
            "gate_owner": "main",
        },
        "assignment_contract": assignment_contract,
        "result_contract": result_contract,
        "stages": [
            {
                "id": "decomposition",
                "mode": "serial",
                "roles": ["main"],
                "depends_on": [],
            },
            {
                "id": "discovery",
                "mode": "parallel",
                "roles": discovery_roles,
                "depends_on": ["decomposition"],
            },
            {
                "id": "design",
                "mode": "serial",
                "roles": ["main"],
                "depends_on": ["discovery"],
            },
            {
                "id": "delivery",
                "mode": "dependency-waves",
                "roles": ["fixer", "reviewer", "main"],
                "depends_on": ["design"],
                "scale": "one fixer per independent development unit in the current dependency layer",
                "wave_phases": [
                    {
                        "id": "implementation",
                        "mode": "parallel-isolated",
                        "roles": ["fixer"],
                    },
                    {
                        "id": "review",
                        "mode": "parallel-read-only",
                        "roles": ["reviewer"],
                        "feedback_to": "owning fixer",
                    },
                    {
                        "id": "gate-integrate",
                        "mode": "serial",
                        "roles": ["main"],
                    },
                ],
                "next_wave": "start only after every prerequisite in the next layer is integrated",
            },
            {
                "id": "closure",
                "mode": "serial",
                "roles": ["main"],
                "depends_on": ["delivery"],
            },
        ],
        "constraints": [
            "Delegate only independent bounded work and declare dependencies before dispatch.",
            "Every fixer owns exactly one registered task branch/worktree and an explicit path scope.",
            "Never run two writers in one worktree or let the main agent edit a fixer-owned worktree concurrently.",
            "Start a dependent write task only after its prerequisite has been integrated into the target branch.",
            "Subagents do not commit, push, integrate, or clean task branches.",
            "Reviewers inspect a stable diff; changes-requested returns to the owning fixer and any edit requires re-review.",
            "The main agent routes review feedback, runs the single fast gate for each write task, integrates in dependency order, pushes, and cleans branches.",
        ],
    })


def _resolve_execution_plan(
    cfg: dict,
    repo: Path,
    *,
    requested_scope: str = "",
    requested_profile: str = "",
    requested_mode: str = "",
    base_ref: str = "",
    changed_paths: Optional[list[str]] = None,
    planned_paths: Optional[list[str]] = None,
    intent: str = "",
) -> dict:
    impact = _impact_summary(
        cfg,
        repo,
        requested_scope=requested_scope,
        base_ref=base_ref,
        changed_paths=changed_paths,
    )
    paths = list(impact.get("changed_files") or [])
    normalized_planned_paths = sorted(
        {_normalize_owned_path(item) for item in (planned_paths or []) if _text(item)}
    )
    classification_inputs = [*paths, *normalized_planned_paths]
    classification = _classify_paths(classification_inputs)
    intent_categories = _classify_intent(intent)
    merged_categories = set(classification["categories"]) | set(intent_categories)
    classification = _classification_for_categories(merged_categories, len(classification_inputs))
    categories = set(classification["categories"])
    matching_rules = _matching_gate_rules(classification_inputs, _gate_cfg(cfg))
    configured_profile = _configured_workflow_profile(cfg)
    requested_profile_value = _normalize_workflow_profile(requested_profile) if requested_profile else ""
    configured_mode = _workflow_mode(cfg)
    requested_mode_value = _text(requested_mode).lower()
    if requested_mode_value and requested_mode_value != "dev":
        raise APError("workflow.mode must be 'dev'; use explicit diagnostic commands when requested.")

    detected_profile = "standard"
    profile_reasons: list[str] = []
    docs_only_paths = _docs_only(classification_inputs)
    docs_or_tests_only = bool(classification_inputs) and (
        (docs_only_paths and str(impact["selected_scope"]) != "full")
        or _tests_only(classification_inputs)
    )
    if docs_or_tests_only and str(impact["selected_scope"]) != "full":
        detected_profile = "micro"
        profile_reasons.append("only docs/test files changed")

    raw_rule_profiles = {_text(rule.get("profile")).lower() for rule in matching_rules if _text(rule.get("profile"))}
    invalid_rule_profiles = raw_rule_profiles - (_WORKFLOW_PROFILES - {"auto"})
    if invalid_rule_profiles:
        raise APError(
            "matched gate rule has invalid profile: " + ", ".join(sorted(invalid_rule_profiles))
        )
    rule_profiles = raw_rule_profiles
    if "micro" in rule_profiles and detected_profile == "standard":
        detected_profile = "micro"
        profile_reasons.append("matched gate rule with profile=micro")
    if "standard" in rule_profiles and detected_profile == "micro":
        detected_profile = "standard"
        profile_reasons.append("matched gate rule with profile=standard")

    high_categories = {
        "db",
        "auth",
        "payment",
        "file_transfer",
        "gateway",
        "prod_config",
        "release_or_tooling",
    }
    high_signals: list[str] = []
    if categories & high_categories and not docs_or_tests_only:
        high_signals.append("high-risk category: " + ", ".join(sorted(categories & high_categories)))
    if "high-risk" in rule_profiles:
        high_signals.append("matched gate rule with profile=high-risk")
    if len(classification_inputs) > 12 and not docs_or_tests_only:
        high_signals.append("change spans more than 12 files")

    if high_signals:
        detected_profile = "high-risk"
        profile_reasons.extend(high_signals)

    effective_profile = detected_profile if configured_profile == "auto" else configured_profile
    if configured_profile != "auto":
        profile_reasons.append(f"configured profile baseline: {configured_profile}")
    if requested_profile_value:
        requested_effective = detected_profile if requested_profile_value == "auto" else requested_profile_value
        configured_floor = None if configured_profile == "auto" else configured_profile
        if configured_floor and _PROFILE_RANK[requested_effective] < _PROFILE_RANK[configured_floor]:
            effective_profile = configured_floor
            profile_reasons.append(
                f"configured profile={configured_floor} cannot be downgraded to {requested_effective}"
            )
        else:
            effective_profile = requested_effective
    if detected_profile == "high-risk" and effective_profile != "high-risk":
        effective_profile = "high-risk"
        profile_reasons.append("high-risk signals cannot be downgraded")
    effective_mode = "dev"
    if not profile_reasons:
        profile_reasons.append(f"configured profile={configured_profile}")

    selected_scope = "changed"
    execution_reasons = list(impact.get("reasons") or [])
    execution_reasons.append("Jenkins/build/deploy and owner acceptance happen after coding completion")

    needs_jenkins = False
    needs_target = False
    needs_dd = bool(classification["needs_dd"] or effective_profile == "high-risk")

    agent_plan = _agent_execution_plan(effective_profile, categories, classification)
    return {
        **impact,
        "contract_version": _AGENT_CONTRACT_VERSION,
        "contract_schema": _AGENT_CONTRACT_SCHEMA,
        "planned_files": normalized_planned_paths,
        "classification_files": classification_inputs,
        "intent_provided": bool(_text(intent)),
        "intent_categories": intent_categories,
        "reasons": execution_reasons,
        "configured_profile": configured_profile,
        "requested_profile": requested_profile_value or None,
        "profile": effective_profile,
        "profile_reasons": profile_reasons,
        "configured_mode": configured_mode,
        "requested_mode": requested_mode_value or None,
        "effective_mode": effective_mode,
        "selected_scope": selected_scope,
        "categories": sorted(categories),
        "needs_dd": needs_dd,
        "needs_adr": classification["needs_adr"],
        "needs_browser": classification["needs_browser"],
        "needs_jenkins": needs_jenkins,
        "needs_target": needs_target,
        "recommended_agents": _recommended_agents(effective_profile, categories, classification),
        "agent_plan": agent_plan,
    }


def cmd_classify(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    intent_parts = [_text(getattr(args, "intent", ""))]
    intent_file = _text(getattr(args, "intent_file", ""))
    if intent_file:
        path = Path(intent_file)
        if not path.is_absolute():
            path = repo / path
        try:
            if path.stat().st_size > 65536:
                raise APError("--intent-file is limited to 64 KiB.")
            intent_parts.append(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise APError(f"Cannot read --intent-file: {path}: {exc}") from exc
    plan = _resolve_execution_plan(
        cfg,
        repo,
        requested_scope=_text(getattr(args, "scope", "")).lower(),
        requested_profile=_text(getattr(args, "profile", "")).lower(),
        requested_mode=_text(getattr(args, "mode", "")).lower(),
        base_ref=_text(getattr(args, "base", "")),
        planned_paths=list(getattr(args, "planned_path", []) or []),
        intent="\n".join(part for part in intent_parts if part),
    )
    risk = {"micro": "P3", "standard": "P2", "high-risk": "P1"}[plan["profile"]]
    commands: list[str] = []
    if plan["needs_dd"]:
        commands.append("python3 docs/tools/autopipeline/ap.py scaffold design --write")
    result = {
        **plan,
        "risk": risk,
        "recommended_commands": commands,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[classify] risk={risk}")
        print(f"[classify] profile={result['profile']}")
        print(f"[classify] effective_mode={result['effective_mode']}")
        print(f"[classify] selected_scope={result['selected_scope']}")
        print("[classify] categories=" + (", ".join(result["categories"]) or "(none)"))
        print("[classify] agents=" + (", ".join(result["recommended_agents"]) or "(main agent only)"))
        print(f"[classify] agent_strategy={result['agent_plan']['strategy']}")
        for stage in result["agent_plan"]["stages"]:
            print(
                "[classify] agent_stage="
                f"{stage['id']} mode={stage['mode']} roles={','.join(stage['roles'])} "
                f"depends_on={','.join(stage['depends_on']) or '-'}"
            )
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
    cfg = _load_cfg(repo)
    requested_scope = _text(getattr(args, "scope", "")).lower()
    if requested_scope not in {"", "auto", "changed"}:
        raise APError(
            "light-gate only runs the changed-scope fast gate. "
            "Use 'ap.py run gate_standard' or 'ap.py run gate_full' for an explicit diagnostic."
        )
    plan = _resolve_execution_plan(
        cfg,
        repo,
        requested_scope=requested_scope,
        requested_profile=_text(getattr(args, "profile", "")).lower(),
        requested_mode=_text(getattr(args, "mode", "")).lower(),
        base_ref=_text(getattr(args, "base", "")),
    )
    if getattr(args, "explain", False):
        _print_impact(plan)
        for reason in plan["profile_reasons"]:
            print(f"[impact] profile_reason: {reason}")

    selected_scope = "changed"
    paths = list(plan.get("changed_files") or [])
    executed = _run_changed_gate(repo, cfg, paths)

    _run_git_diff_check(repo, cfg)
    executed.append("diff_check")
    duration_s = time.time() - light_gate_start
    _record_gate_profile(repo, cfg, "light_gate", "pass", duration_s, scope=selected_scope, detail=", ".join(executed))
    _record_evidence(
        repo,
        cfg,
        "light_gate",
        "pass",
        {
            "profile": plan["profile"],
            "effective_mode": plan["effective_mode"],
            "scope": selected_scope,
            "executed": executed,
            "duration_s": round(duration_s, 3),
            "changed_files": paths,
        },
    )
    print(
        f"[light-gate] OK profile={plan['profile']} mode={plan['effective_mode']} "
        f"scope={selected_scope}: " + ", ".join(executed)
    )


def cmd_impact(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    summary = _resolve_execution_plan(
        cfg,
        repo,
        requested_scope=_text(getattr(args, "scope", "")).lower(),
        requested_profile=_text(getattr(args, "profile", "")).lower(),
        requested_mode=_text(getattr(args, "mode", "")).lower(),
        base_ref=_text(getattr(args, "base", "")),
    )
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
    docs_cfg = (cfg.get("docs") or {})
    runtime_cfg = (cfg.get("runtime") or {})
    structure_cfg = _structure_cfg(cfg)
    concurrency_cfg = _concurrency_cfg(cfg)

    missing: List[str] = []
    validation_errors: List[str] = []

    mode = str(workflow_cfg.get("mode") or "dev").strip().lower()
    profile = str(workflow_cfg.get("profile") or "auto").strip().lower()
    completion = str(workflow_cfg.get("completion") or "").strip().lower()
    if mode != "dev":
        missing.append("workflow.mode (must be dev; external verification is owner-managed)")
    if profile not in _WORKFLOW_PROFILES:
        missing.append("workflow.profile (must be auto, micro, standard, or high-risk)")
    if completion != "push":
        missing.append("workflow.completion (must be push)")
    isolation = _text(concurrency_cfg.get("isolation")).lower() or "worktree"
    if isolation != "worktree":
        validation_errors.append(
            "concurrency.isolation must be worktree; shared-checkout/legacy writes are no longer supported"
        )
    branch_prefix = _text(concurrency_cfg.get("branch_prefix")) or "codex/"
    if not branch_prefix.endswith("/"):
        validation_errors.append("concurrency.branch_prefix must end with '/'")
    elif run(
        ["git", "check-ref-format", "--branch", f"{branch_prefix}TASK"],
        cwd=repo,
        check=False,
    ).returncode != 0:
        validation_errors.append("concurrency.branch_prefix does not form a valid Git branch")
    if not str(project_cfg.get("name") or "").strip():
        missing.append("project.name")
    missing.extend(_access_config_issues(cfg))
    enforcement = _text(structure_cfg.get("enforcement")).lower()
    if enforcement and enforcement not in {"advisory", "blocking"}:
        validation_errors.append("structure.enforcement must be advisory or blocking")
    gate_cfg = _gate_cfg(cfg)
    raw_rules = gate_cfg.get("rules") or []
    rules_valid = isinstance(raw_rules, list)
    if not rules_valid:
        validation_errors.append("gate.rules must be a list")
        raw_rules = []
    for index, rule in enumerate(raw_rules):
        if not isinstance(rule, dict):
            rules_valid = False
            validation_errors.append(f"gate.rules[{index}] must be a mapping")
            continue
        rule_profile = _text(rule.get("profile")).lower()
        if rule_profile and rule_profile not in _WORKFLOW_PROFILES - {"auto"}:
            rules_valid = False
            validation_errors.append(
                f"gate.rules[{index}].profile must be micro, standard, or high-risk"
            )
        rule_scope = _text(rule.get("scope")).lower()
        if rule_scope and rule_scope not in {"changed", "standard", "full"}:
            rules_valid = False
            validation_errors.append(
                f"gate.rules[{index}].scope must be changed, standard, or full"
            )

    if not (_configured_command(cfg, "gate_changed") or _configured_command(cfg, "quick_test")):
        missing.append("fast gate command: commands.gate_changed or commands.quick_test")

    repo_docs = {
        "docs.taskbook": Path(repo, str(docs_cfg.get("taskbook", "docs/tasks/taskbook.md"))),
        "docs.closure_log": Path(repo, str(docs_cfg.get("closure_log", "docs/tasks/closure-log.md"))),
    }
    api_doc = Path(repo, str(docs_cfg.get("api_doc", "docs/interfaces/api.md")))
    api_change_log = Path(repo, str(docs_cfg.get("api_change_log", "docs/interfaces/api-change-log.md")))
    api_docs_enabled = (
        _bool_config(docs_cfg.get("api_docs_required"), False)
        if "api_docs_required" in docs_cfg
        else api_doc.exists() or api_change_log.exists()
    )
    if api_docs_enabled:
        repo_docs["docs.api_doc"] = api_doc
        repo_docs["docs.api_change_log"] = api_change_log
    for key, path in repo_docs.items():
        if not path.exists():
            validation_errors.append(f"{key} missing on disk: {path}")

    runtime_enabled = any(str(runtime_cfg.get(key) or "").strip() for key in ["docker_compose_file", "docker_service", "health_base_url", "health_path"])
    if runtime_enabled and not str(runtime_cfg.get("docker_compose_file") or "").strip():
        validation_errors.append("runtime config is partially enabled but runtime.docker_compose_file is missing")

    missing.extend(validation_errors)

    if missing:
        _record_evidence(repo, cfg, "doctor", "fail", {"issues": missing})
        raise APError("Doctor found blocking config issues:\n- " + "\n- ".join(missing))

    _record_evidence(
        repo,
        cfg,
        "doctor",
        "pass",
        {"mode": mode, "completion": completion, "access_fields": len(_REQUIRED_ACCESS_FIELDS)},
    )
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
    """Ensure enabled or already materialized API docs are complete."""
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    docs = (cfg.get("docs") or {})
    api_doc = Path(repo, str(docs.get("api_doc", "docs/interfaces/api.md")))
    change_log = Path(repo, str(docs.get("api_change_log", "docs/interfaces/api-change-log.md")))
    if "api_docs_required" in docs:
        required = _bool_config(docs.get("api_docs_required"), False)
    else:
        required = api_doc.exists() or change_log.exists()
    if not required:
        _record_evidence(repo, cfg, "verify_api_docs", "skipped", {"reason": "api_docs_required=false"})
        print("[verify-api-docs] skipped: optional API docs are not enabled")
        return
    missing = [p for p in [api_doc, change_log] if not p.exists()]
    if missing:
        raise APError(
            "Missing API docs: "
            + ", ".join([str(p) for p in missing])
            + ". Create them with `ap.py scaffold api --write`."
        )
    _record_evidence(repo, cfg, "verify_api_docs", "pass", {"api_doc": str(api_doc), "api_change_log": str(change_log)})
    print(f"[verify-api-docs] OK: {api_doc} + {change_log}")


def _validate_closure_result(effective_mode: str, result: str) -> None:
    mode = _text(effective_mode).lower()
    normalized_result = _text(result).upper()
    if mode == "dev" and normalized_result == "PASS":
        raise APError("Automatic coding closure uses DEV-CLOSED; owner acceptance is handled after push.")


def _validate_closure_evidence(result: str, verification_items: list[str]) -> None:
    if _text(result).upper() != "PASS":
        return
    meaningful = [
        _text(item)
        for item in verification_items
        if _text(item) and not _is_placeholder(item) and _text(item).lower() not in {"none", "n/a", "not run"}
    ]
    if not meaningful:
        raise APError("PASS requires at least one concrete --verification evidence item.")


def cmd_record_closure(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    context_manifest = _require_task_context(repo, cfg, args.task_id)
    plan = _resolve_execution_plan(
        cfg,
        repo,
        requested_profile=_text(getattr(args, "profile", "")).lower(),
        requested_mode=_text(getattr(args, "mode", "")).lower(),
    )
    if not plan.get("changed_files"):
        commit_paths = _commit_changed_files(repo, _text(getattr(args, "commit", "")) or "HEAD")
        if commit_paths:
            plan = _resolve_execution_plan(
                cfg,
                repo,
                requested_profile=_text(getattr(args, "profile", "")).lower(),
                requested_mode=_text(getattr(args, "mode", "")).lower(),
                changed_paths=commit_paths,
            )
    profile = str(plan["profile"])
    _validate_closure_result(str(plan["effective_mode"]), str(args.result))
    verification_items = list(args.verification or [])
    _validate_closure_evidence(str(args.result), verification_items)
    docs_cfg = (cfg.get("docs") or {})
    target_cfg = (cfg.get("target_env") or {})
    taskbook = Path(repo, str(docs_cfg.get("taskbook", "docs/tasks/taskbook.md")))
    manifest = context_manifest or _active_task_manifest(repo)
    closure_log = (
        _task_doc_path(repo, cfg, manifest, "closure")
        if manifest
        else Path(repo, str(docs_cfg.get("closure_log", "docs/tasks/closure-log.md")))
    )
    closure_log.parent.mkdir(parents=True, exist_ok=True)
    if not closure_log.exists():
        closure_log.write_text("# Closure Log\n\n", encoding="utf-8")

    task_id = args.task_id
    title = str(args.title or "").strip() or _infer_title(taskbook, task_id)
    timestamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    commit_value = _resolve_git_short_sha(repo, args.commit)
    target_env = str(args.target_env or target_cfg.get("name") or "").strip() or "owner-managed acceptance"
    verification_text = "; ".join(verification_items) if verification_items else "fast gate evidence not recorded"
    follow_up = str(args.follow_up or "").strip() or "none"
    jenkins_build = str(args.jenkins or "").strip() or "owner-managed after push"
    structure_check = str(getattr(args, "structure_check", "") or "").strip() or "not part of the fast local gate"
    lines = [
        f"## {task_id} — {title} — {timestamp}",
        f"- Task: {task_id}",
        f"- Commit: {commit_value}",
        f"- Fast Local Gate: {verification_text}",
        f"- External Build/Deploy: {jenkins_build}",
        f"- Owner Acceptance: {target_env}",
        f"- Effective Profile: {profile}",
        f"- Optional Structure Diagnostic: {structure_check}",
        f"- Result: {args.result}",
        f"- Follow-up: {follow_up}",
    ]
    if str(args.initial_commit or "").strip():
        lines.append(f"- Initial Commit: {args.initial_commit.strip()}")
    if str(args.jenkins_failure or "").strip():
        lines.append(f"- CI/Jenkins Failure: {args.jenkins_failure.strip()}")
    if str(args.fix_commit or "").strip():
        lines.append(f"- Fix Commit: {args.fix_commit.strip()}")

    with closure_log.open("a", encoding="utf-8") as f:
        if closure_log.stat().st_size > 0:
            f.write("\n")
        f.write("\n".join(lines))
        f.write("\n")
    if manifest:
        _update_active_task_status(repo, cfg, manifest, str(args.result))
    _record_evidence(
        repo,
        cfg,
        "record_closure",
        "pass",
        {
            "task_id": task_id,
            "result": args.result,
            "commit": commit_value,
            "profile": profile,
            "structure_check": structure_check,
        },
    )
    print(f"[record-closure] OK: {closure_log}")


def _task_remote_and_target(cfg: dict, args: argparse.Namespace) -> tuple[str, str, str]:
    concurrency_cfg = _concurrency_cfg(cfg)
    remote = _text(getattr(args, "remote", "")) or _text(concurrency_cfg.get("remote")) or "origin"
    target_branch = (
        _text(getattr(args, "target_branch", ""))
        or _text(concurrency_cfg.get("target_branch"))
    )
    base_ref = _text(getattr(args, "base", "")) or _text(concurrency_cfg.get("base_ref"))
    if not target_branch and base_ref.startswith(f"{remote}/"):
        target_branch = base_ref[len(remote) + 1 :]
    if not target_branch:
        branch = _current_branch(Path(args.repo).resolve())
        target_branch = branch or "dev"
    if not base_ref:
        base_ref = f"{remote}/{target_branch}"
    return remote, target_branch, base_ref


def _fetch_target(repo: Path, remote: str, target_branch: str) -> str:
    remote_ref = f"refs/remotes/{remote}/{target_branch}"
    run(
        [
            "git",
            "fetch",
            "--no-tags",
            remote,
            f"refs/heads/{target_branch}:{remote_ref}",
        ],
        cwd=repo,
    )
    return _resolve_commit(repo, remote_ref)


def _task_branch_prefix(cfg: dict) -> str:
    prefix = _text(_concurrency_cfg(cfg).get("branch_prefix")) or "codex/"
    if not prefix.endswith("/"):
        raise APError("concurrency.branch_prefix must end with '/'.")
    return prefix


def _task_worktree_path(repo: Path, cfg: dict, task_id: str, override: str = "") -> Path:
    raw_root = override or _text(_concurrency_cfg(cfg).get("worktree_root")) or "../.worktrees"
    root = Path(raw_root).expanduser()
    if not root.is_absolute():
        root = repo / root
    root = root.resolve()
    candidate = (root / repo.name / _validate_task_id(task_id)).resolve()
    if repo.resolve() == candidate or repo.resolve() in candidate.parents:
        raise APError("Task worktrees must live outside the primary repository directory.")
    return candidate


def _parse_null_config_entries(result, *, context: str) -> dict[str, list[str]]:
    if result.returncode == 1 and not result.stdout:
        return {}
    if result.returncode != 0:
        raise APError(
            f"Cannot inspect {context}: {result.stderr.strip() or result.stdout.strip()}"
        )
    entries: dict[str, list[str]] = {}
    for item in result.stdout.split("\0"):
        if not item:
            continue
        key, separator, value = item.partition("\n")
        if not separator or not key:
            raise APError(f"Malformed Git config entry while inspecting {context}: {item!r}")
        entries.setdefault(key, []).append(value)
    return entries


def _gitmodules_urls(repo: Path) -> dict[str, str]:
    path = repo / ".gitmodules"
    if not path.exists():
        return {}
    result = run(
        [
            "git",
            "config",
            "--null",
            "--file",
            str(path),
            "--get-regexp",
            r"^submodule\..*\.url$",
        ],
        cwd=repo,
        check=False,
    )
    entries = _parse_null_config_entries(result, context=f"submodule URLs in {path}")
    return {key: values[-1] for key, values in entries.items() if values}


def _common_submodule_config(repo: Path) -> dict[str, list[str]]:
    result = run(
        [
            "git",
            "config",
            "--null",
            "--local",
            "--get-regexp",
            r"^submodule\.",
        ],
        cwd=repo,
        check=False,
    )
    return _parse_null_config_entries(result, context="shared submodule config")


def _config_values(repo: Path, scope: str, key: str) -> list[str]:
    result = run(
        ["git", "config", "--null", scope, "--get-all", key],
        cwd=repo,
        check=False,
    )
    if result.returncode == 1 and not result.stdout:
        return []
    if result.returncode != 0:
        raise APError(
            f"Cannot inspect {scope} Git config {key!r}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return [value for value in result.stdout.split("\0") if value]


def _replace_config_values(repo: Path, scope: str, key: str, values: list[str]) -> None:
    removed = run(
        ["git", "config", scope, "--unset-all", key],
        cwd=repo,
        check=False,
    )
    if removed.returncode not in {0, 5}:
        raise APError(
            f"Cannot clear {scope} Git config {key!r}: "
            f"{removed.stderr.strip() or removed.stdout.strip()}"
        )
    for value in values:
        run(["git", "config", scope, "--add", key, value], cwd=repo)


def _enable_worktree_config(repo: Path) -> None:
    enabled = run(
        ["git", "config", "--local", "--bool", "--get", "extensions.worktreeConfig"],
        cwd=repo,
        check=False,
    )
    if enabled.returncode == 0 and enabled.stdout.strip() == "true":
        return
    run(["git", "config", "--local", "extensions.worktreeConfig", "true"], cwd=repo)


def _require_worktree_config(repo: Path) -> None:
    enabled = run(
        ["git", "config", "--local", "--bool", "--get", "extensions.worktreeConfig"],
        cwd=repo,
        check=False,
    )
    if enabled.returncode != 0 or enabled.stdout.strip() != "true":
        raise APError(
            "Git extensions.worktreeConfig is not enabled. Return to the control checkout and "
            "recreate or recover the task; task commands will not write shared config."
        )


def _default_submodule_remote_url(repo: Path) -> str:
    branch = _current_branch(repo)
    remote = ""
    if branch:
        configured = run(
            ["git", "config", "--get", f"branch.{branch}.remote"],
            cwd=repo,
            check=False,
        )
        if configured.returncode == 0:
            remote = configured.stdout.strip()
    if not remote:
        names = run(["git", "remote"], cwd=repo, check=False)
        if names.returncode != 0:
            raise APError(
                f"Cannot inspect Git remotes while resolving submodule URLs: {names.stderr.strip()}"
            )
        if "origin" in {line.strip() for line in names.stdout.splitlines()}:
            remote = "origin"
    if not remote or remote == ".":
        return str(repo.resolve())
    remote_url_result = run(
        ["git", "remote", "get-url", remote],
        cwd=repo,
        check=False,
    )
    if remote_url_result.returncode != 0 or not remote_url_result.stdout.strip():
        raise APError(f"Default submodule remote {remote!r} has no URL in {repo}.")
    return remote_url_result.stdout.strip()


def _resolve_submodule_url(repo: Path, raw_url: str) -> str:
    if not raw_url.startswith(("./", "../")):
        return raw_url
    remote_url = _default_submodule_remote_url(repo)
    has_explicit_scheme = bool(
        re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", remote_url)
        or remote_url.startswith("file:")
    )
    scp_like = (
        None
        if has_explicit_scheme
        else re.fullmatch(r"([^/:]+(?:@[^/:]+)?):(.*)", remote_url)
    )
    if scp_like is not None:
        prefix, remote_path = scp_like.groups()
        return f"{prefix}:{posixpath.normpath(posixpath.join(remote_path, raw_url))}"
    parsed = urllib.parse.urlsplit(remote_url)
    if parsed.scheme:
        resolved_path = posixpath.normpath(posixpath.join(parsed.path, raw_url))
        if parsed.path.startswith("/") and not resolved_path.startswith("/"):
            resolved_path = f"/{resolved_path}"
        return urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, resolved_path, parsed.query, parsed.fragment)
        )
    remote_path = Path(remote_url).expanduser()
    if not remote_path.is_absolute():
        remote_path = (repo / remote_path).resolve()
    return str(Path(os.path.normpath(os.path.join(str(remote_path), raw_url))))


def _seed_control_submodule_config(repo: Path) -> None:
    _enable_worktree_config(repo)
    for key, declared_url in _gitmodules_urls(repo).items():
        if _config_values(repo, "--worktree", key):
            continue
        effective = _config_values(repo, "--local", key)
        value = effective[-1] if effective else _resolve_submodule_url(repo, declared_url)
        _replace_config_values(repo, "--worktree", key, [value])


def _sync_task_submodule_config(
    control_repo: Path,
    worktree: Path,
    manifest: dict,
    *,
    initial: bool,
    check_common: bool,
) -> None:
    _require_worktree_config(control_repo)
    urls = _gitmodules_urls(worktree)
    control_urls = _gitmodules_urls(control_repo)
    previous_raw = manifest.get("submodule_config_claims")
    previous_claims = (
        {str(key): str(value) for key, value in previous_raw.items()}
        if isinstance(previous_raw, dict)
        else {}
    )
    claims: dict[str, str] = {}
    for key, declared_url in urls.items():
        value = _resolve_submodule_url(worktree, declared_url)
        if initial and control_urls.get(key) == declared_url:
            control_values = _config_values(control_repo, "--worktree", key)
            if control_values:
                value = control_values[-1]
        _replace_config_values(worktree, "--worktree", key, [value])
        claims[key] = value
        active_key = f"{key[:-len('.url')]}.active"
        _replace_config_values(worktree, "--worktree", active_key, ["true"])
        claims[active_key] = "true"

    for stale_key in sorted(set(previous_claims) - set(claims)):
        _replace_config_values(worktree, "--worktree", stale_key, [])

    manifest["submodule_config_claims"] = claims
    if not check_common:
        return
    baseline = manifest.get("common_submodule_config")
    baseline = baseline if isinstance(baseline, dict) else {}
    candidate_values: dict[str, set[str]] = {}
    for source in (previous_claims, claims):
        for key, value in source.items():
            candidate_values.setdefault(key, set()).add(value)
    for key, candidates in candidate_values.items():
        current = _config_values(control_repo, "--local", key)
        before_raw = baseline.get(key) or []
        before = [str(value) for value in before_raw] if isinstance(before_raw, list) else []
        if current != before:
            raise APError(
                "Shared submodule config changed after task-start; no common config was modified. "
                f"Resolve ownership before continuing: key={key!r}, before={before!r}, "
                f"current={current!r}, task_values={sorted(candidates)!r}"
            )


def _git_ref_exists(repo: Path, ref: str) -> bool:
    return run(["git", "show-ref", "--verify", "--quiet", ref], cwd=repo, check=False).returncode == 0


def _git_status(repo: Path) -> str:
    result = run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repo,
        check=False,
    )
    if result.returncode != 0:
        raise APError(f"Cannot inspect Git status for {repo}: {result.stderr.strip()}")
    return result.stdout.strip()


def _ignored_paths(repo: Path) -> list[str]:
    result = run(
        [
            "git",
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "--directory",
            "-z",
        ],
        cwd=repo,
        check=False,
    )
    if result.returncode != 0:
        raise APError(
            f"Cannot inspect ignored files for {repo}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return sorted(
        path.rstrip("/")
        for path in result.stdout.split("\0")
        if path.rstrip("/")
    )


def _pattern_may_match_descendant(directory: str, pattern_ref: str) -> bool:
    directory = directory.replace("\\", "/").lstrip("./").rstrip("/")
    pattern = _text(pattern_ref).replace("\\", "/").lstrip("./")
    if not directory or not pattern:
        return False
    if "/" not in pattern or pattern.startswith("**/"):
        return True
    wildcard = min(
        (index for token in ("*", "?", "[") if (index := pattern.find(token)) >= 0),
        default=len(pattern),
    )
    literal_prefix = pattern[:wildcard].rstrip("/")
    if not literal_prefix:
        return True
    return (
        literal_prefix == directory
        or literal_prefix.startswith(f"{directory}/")
        or directory.startswith(literal_prefix)
    )


def _expanded_ignored_paths(repo: Path, directory: str) -> list[str]:
    result = run(
        [
            "git",
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "-z",
            "--",
            directory,
        ],
        cwd=repo,
        check=False,
    )
    if result.returncode != 0:
        raise APError(
            f"Cannot inspect ignored directory {directory!r}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return sorted(path for path in result.stdout.split("\0") if path)


def _unsafe_ignored_paths(repo: Path, extra_patterns: list[str]) -> list[str]:
    patterns = list(_DEFAULT_DISPOSABLE_IGNORED_PATTERNS) + [
        _text(item) for item in extra_patterns if _text(item)
    ]
    unsafe: list[str] = []
    for path in _ignored_paths(repo):
        # Git deliberately collapses ignored directories (for example `.local/`).
        # A declared disposable subtree is safe without walking it; an ambiguous
        # parent is expanded so an allowed child cannot hide an unknown sibling.
        if _path_matches(path, patterns):
            continue
        if not any(_pattern_may_match_descendant(path, pattern) for pattern in patterns):
            unsafe.append(path)
            continue
        expanded = _expanded_ignored_paths(repo, path)
        unsafe.extend(item for item in expanded if not _path_matches(item, patterns))
        if not expanded:
            unsafe.append(path)
    return sorted(set(unsafe))


def _initialized_submodules(repo: Path) -> list[tuple[str, Path]]:
    result = run(
        [
            "git",
            "submodule",
            "foreach",
            "--quiet",
            "--recursive",
            'printf "%s\\0" "$displaypath"',
        ],
        cwd=repo,
        check=False,
    )
    if result.returncode != 0:
        raise APError(
            f"Cannot inspect initialized submodules for {repo}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    root = repo.resolve()
    submodules: list[tuple[str, Path]] = []
    for raw_path in result.stdout.split("\0"):
        rel = raw_path.replace("\\", "/").strip("/")
        if rel.startswith("./"):
            rel = rel[2:]
        if not rel:
            continue
        candidate = (root / rel).resolve()
        if root not in candidate.parents:
            raise APError(f"Initialized submodule resolves outside the task worktree: {rel}")
        submodules.append((rel, candidate))
    return sorted(set(submodules), key=lambda item: item[0])


def _stored_submodule_gitdirs(worktree: Path) -> tuple[set[Path], list[Path]]:
    modules_root = _git_dir(worktree) / "modules"
    if not modules_root.exists():
        return set(), []
    repositories: set[Path] = set()
    unknown: list[Path] = []

    def scan_container(container: Path) -> None:
        try:
            children = sorted(container.iterdir(), key=lambda item: item.name)
        except OSError:
            unknown.append(container)
            return
        for child in children:
            if child.is_symlink():
                unknown.append(child)
                continue
            if not child.is_dir():
                unknown.append(child)
                continue
            is_git_dir = (
                (child / "HEAD").is_file()
                and (child / "config").is_file()
                and (child / "objects").is_dir()
            )
            if is_git_dir:
                repositories.add(child.resolve())
                nested_modules = child / "modules"
                if nested_modules.exists():
                    scan_container(nested_modules)
                continue
            scan_container(child)

    scan_container(modules_root)
    return repositories, unknown


def _submodule_disposable_patterns(submodule_path: str, extra_patterns: list[str]) -> list[str]:
    prefix = submodule_path.replace("\\", "/").strip("/")
    patterns = [_text(item) for item in extra_patterns if _text(item)]
    for item in list(patterns):
        normalized = item.replace("\\", "/").lstrip("./").strip("/")
        if normalized == prefix:
            patterns.append("**")
        elif normalized.startswith(f"{prefix}/"):
            patterns.append(normalized[len(prefix) + 1 :])
    return patterns


def _submodule_local_only_commits(submodule: Path) -> list[str]:
    result = run(
        [
            "git",
            "rev-list",
            "--max-count=20",
            "--all",
            "--reflog",
            "--not",
            "--remotes",
        ],
        cwd=submodule,
        check=False,
    )
    if result.returncode != 0:
        raise APError(
            f"Cannot inspect local-only submodule history for {submodule}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _submodule_unmirrored_branches(submodule: Path) -> list[str]:
    result = run(
        [
            "git",
            "for-each-ref",
            "--format=%(refname)%09%(objectname)",
            "refs/heads",
            "refs/remotes",
        ],
        cwd=submodule,
        check=False,
    )
    if result.returncode != 0:
        raise APError(
            f"Cannot inspect submodule branches for {submodule}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    local: dict[str, str] = {}
    remote: dict[str, set[str]] = {}
    for line in result.stdout.splitlines():
        if "\t" not in line:
            continue
        ref, commit = line.split("\t", 1)
        if ref.startswith("refs/heads/"):
            local[ref[len("refs/heads/") :]] = commit
            continue
        if not ref.startswith("refs/remotes/"):
            continue
        remote_and_branch = ref[len("refs/remotes/") :]
        if "/" not in remote_and_branch:
            continue
        _, branch = remote_and_branch.split("/", 1)
        remote.setdefault(branch, set()).add(commit)
    return sorted(
        branch
        for branch, commit in local.items()
        if commit not in remote.get(branch, set())
    )


def _submodule_other_worktrees(submodule: Path) -> list[str]:
    result = run(
        ["git", "worktree", "list", "--porcelain", "-z"],
        cwd=submodule,
        check=False,
    )
    if result.returncode != 0:
        raise APError(
            f"Cannot inspect linked submodule worktrees for {submodule}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    current_paths = {submodule.resolve(), _git_dir(submodule).resolve()}
    others: list[str] = []
    for field in result.stdout.split("\0"):
        if not field.startswith("worktree "):
            continue
        raw_path = field[len("worktree ") :]
        candidate = Path(raw_path).resolve()
        if candidate not in current_paths:
            others.append(raw_path)
    return sorted(set(others))


def _refresh_submodule_remotes(submodule: Path) -> None:
    remotes = run(["git", "remote"], cwd=submodule, check=False)
    if remotes.returncode != 0:
        raise APError(
            f"Cannot inspect submodule remotes for {submodule}: "
            f"{remotes.stderr.strip() or remotes.stdout.strip()}"
        )
    names = [line.strip() for line in remotes.stdout.splitlines() if line.strip()]
    if not names:
        raise APError(
            f"Initialized submodule has no remote to verify before destructive cleanup: {submodule}"
        )
    for remote in names:
        fetched = run(
            [
                "git",
                "-c",
                "credential.interactive=never",
                "fetch",
                "--prune",
                "--no-tags",
                remote,
            ],
            cwd=submodule,
            check=False,
        )
        if fetched.returncode != 0:
            raise APError(
                f"Cannot refresh submodule remote {remote!r}; cleanup was blocked so Git history remains local.\n"
                f"{fetched.stdout}\n{fetched.stderr}"
            )


def _submodule_refs(submodule: Path) -> dict[str, str]:
    result = run(
        ["git", "for-each-ref", "--format=%(refname)%09%(objectname)", "refs"],
        cwd=submodule,
        check=False,
    )
    if result.returncode != 0:
        raise APError(
            f"Cannot snapshot submodule refs for {submodule}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    refs: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "\t" not in line:
            continue
        ref, object_id = line.split("\t", 1)
        if ref.startswith("refs/") and object_id:
            refs[ref] = object_id
    return refs


def _submodule_reflog_commits(submodule: Path) -> list[str]:
    result = run(
        ["git", "reflog", "show", "--all", "--format=%H"],
        cwd=submodule,
        check=False,
    )
    if result.returncode != 0:
        raise APError(
            f"Cannot snapshot submodule reflogs for {submodule}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    commits = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    commits.add(_resolve_commit(submodule, "HEAD"))
    return sorted(commits)


def _archive_submodule_git_state(
    control_repo: Path,
    manifest: dict,
    submodule_path: str,
    submodule: Path,
) -> dict:
    task_uuid = _text(manifest.get("task_uuid")) or uuid.uuid4().hex
    object_format_result = run(
        ["git", "rev-parse", "--show-object-format"],
        cwd=submodule,
        check=False,
    )
    if object_format_result.returncode != 0:
        raise APError(
            f"Cannot inspect submodule object format for {submodule_path}: "
            f"{object_format_result.stderr.strip() or object_format_result.stdout.strip()}"
        )
    object_format = object_format_result.stdout.strip() or "sha1"
    recovery_root = _task_state_root(control_repo) / "submodule-recovery"
    repo_key = hashlib.sha256(submodule_path.encode("utf-8")).hexdigest()[:20]
    recovery_repo = recovery_root / "repos" / f"{repo_key}-{object_format}.git"
    if not recovery_repo.exists():
        recovery_repo.parent.mkdir(parents=True, exist_ok=True)
        init_command = ["git", "init", "--bare", "--quiet"]
        if object_format != "sha1":
            init_command.append(f"--object-format={object_format}")
        init_command.append(str(recovery_repo))
        run(init_command, cwd=control_repo)
    bare = run(
        ["git", f"--git-dir={recovery_repo}", "rev-parse", "--is-bare-repository"],
        cwd=control_repo,
        check=False,
    )
    recovery_format = run(
        ["git", f"--git-dir={recovery_repo}", "rev-parse", "--show-object-format"],
        cwd=control_repo,
        check=False,
    )
    if (
        bare.returncode != 0
        or bare.stdout.strip() != "true"
        or recovery_format.returncode != 0
        or recovery_format.stdout.strip() != object_format
    ):
        raise APError(f"Invalid submodule recovery repository: {recovery_repo}")

    original_refs = _submodule_refs(submodule)
    reflog_commits = _submodule_reflog_commits(submodule)
    snapshot_id = uuid.uuid4().hex
    temporary_prefix = f"refs/auto-coding-recovery/{snapshot_id}/reflog"
    temporary_refs: dict[str, str] = {}
    try:
        for commit in reflog_commits:
            temporary_ref = f"{temporary_prefix}/{commit}"
            run(
                ["git", "update-ref", temporary_ref, commit, "0" * len(commit)],
                cwd=submodule,
            )
            temporary_refs[temporary_ref] = commit
        source_refs = _submodule_refs(submodule)
        destination_prefix = f"refs/tasks/{task_uuid}/{snapshot_id}"
        run(
            [
                "git",
                f"--git-dir={recovery_repo}",
                "fetch",
                "--no-tags",
                "--no-write-fetch-head",
                str(submodule),
                f"+refs/*:{destination_prefix}/*",
            ],
            cwd=control_repo,
        )
        archived_refs = run(
            [
                "git",
                f"--git-dir={recovery_repo}",
                "for-each-ref",
                "--format=%(refname)%09%(objectname)",
                destination_prefix,
            ],
            cwd=control_repo,
        )
        archived: dict[str, str] = {}
        for line in archived_refs.stdout.splitlines():
            if "\t" in line:
                ref, object_id = line.split("\t", 1)
                archived[ref] = object_id
        missing: list[str] = []
        for source_ref, object_id in source_refs.items():
            destination = f"{destination_prefix}/{source_ref[len('refs/'):]}"
            if archived.get(destination) != object_id:
                missing.append(source_ref)
        if missing:
            raise APError(
                f"Submodule recovery snapshot verification failed for {submodule_path}:\n- "
                + "\n- ".join(missing)
            )
        metadata_path = (
            recovery_root
            / "snapshots"
            / task_uuid
            / f"{repo_key}-{snapshot_id}.json"
        )
        _write_json_object(
            metadata_path,
            {
                "schema": 1,
                "created_at": _now_iso(),
                "task_id": _text(manifest.get("task_id")),
                "task_uuid": task_uuid,
                "submodule_path": submodule_path,
                "source_git_dir": str(_git_dir(submodule)),
                "recovery_repo": str(recovery_repo),
                "destination_prefix": destination_prefix,
                "refs": original_refs,
                "reflog_commits": reflog_commits,
            },
        )
    finally:
        for temporary_ref, commit in temporary_refs.items():
            run(
                ["git", "update-ref", "-d", temporary_ref, commit],
                cwd=submodule,
                check=False,
            )

    print(
        f"[task-cleanup] submodule recovery snapshot: {submodule_path} -> "
        f"{recovery_repo} ({destination_prefix})"
    )
    return {
        "submodule_path": submodule_path,
        "recovery_repo": str(recovery_repo),
        "destination_prefix": destination_prefix,
        "metadata_path": str(metadata_path),
    }


def _prepare_submodules_for_removal(
    control_repo: Path,
    manifest: dict,
    worktree: Path,
    extra_disposable_patterns: list[str],
) -> bool:
    submodules = _initialized_submodules(worktree)
    stored_gitdirs, unknown_store_paths = _stored_submodule_gitdirs(worktree)
    initialized_gitdirs = {_git_dir(submodule).resolve() for _, submodule in submodules}
    residual_gitdirs = sorted(stored_gitdirs - initialized_gitdirs)
    if residual_gitdirs or unknown_store_paths:
        details = [
            *(f"residual module Git directory: {path}" for path in residual_gitdirs),
            *(f"unrecognized module-store path: {path}" for path in unknown_store_paths[:20]),
        ]
        raise APError(
            "Task worktree has deinitialized, removed, or unrecognized submodule Git state that "
            "cannot be proven safe for forced removal. Reinitialize the submodule and rerun cleanup, "
            "or move/recover its Git data first; the task worktree and branch were retained:\n- "
            + "\n- ".join(details)
        )
    if not submodules:
        return False
    problems: list[str] = []
    for rel, submodule in submodules:
        other_worktrees = _submodule_other_worktrees(submodule)
        if other_worktrees:
            problems.append(
                f"{rel}: additional linked worktrees must be handled before cleanup:\n"
                + "\n".join(f"  - {path}" for path in other_worktrees)
            )
            continue
        try:
            _refresh_submodule_remotes(submodule)
        except APError as exc:
            problems.append(f"{rel}: {exc}")
            continue
        local_only_commits = _submodule_local_only_commits(submodule)
        if local_only_commits:
            problems.append(
                f"{rel}: local refs/reflogs contain commits not reachable from remote-tracking refs:\n"
                + "\n".join(f"  - {commit}" for commit in local_only_commits)
            )
            continue
        unmirrored_branches = _submodule_unmirrored_branches(submodule)
        if unmirrored_branches:
            problems.append(
                f"{rel}: local branches have no same-name remote-tracking ref at the same commit:\n"
                + "\n".join(f"  - {branch}" for branch in unmirrored_branches)
            )
            continue
        dirty = _git_status(submodule)
        if dirty:
            problems.append(f"{rel}: tracked or untracked changes:\n{dirty}")
            continue
        conflicts = run(["git", "ls-files", "-u"], cwd=submodule, check=False)
        if conflicts.returncode != 0:
            raise APError(
                f"Cannot inspect submodule conflicts for {rel}: "
                f"{conflicts.stderr.strip() or conflicts.stdout.strip()}"
            )
        if conflicts.stdout.strip():
            problems.append(f"{rel}: unresolved conflicts")
            continue
        unsafe_ignored = _unsafe_ignored_paths(
            submodule,
            _submodule_disposable_patterns(rel, extra_disposable_patterns),
        )
        if unsafe_ignored:
            rendered = "\n".join(f"  - {rel}/{path}" for path in unsafe_ignored)
            problems.append(f"{rel}: ignored files are not declared disposable:\n{rendered}")
    if problems:
        raise APError(
            "Task submodules contain data that cannot be discarded; refusing cleanup:\n- "
            + "\n- ".join(problems)
            + "\nPush or move local submodule history, commit/move working data, or add only "
            "disposable cache paths to concurrency.disposable_ignored; then rerun task-finish."
        )

    for rel, submodule in submodules:
        _archive_submodule_git_state(control_repo, manifest, rel, submodule)
    return True


def _task_doc_path(repo: Path, cfg: dict, manifest: dict, kind: str) -> Path:
    docs_cfg = cfg.get("docs") or {}
    task_id = _validate_task_id(_text(manifest.get("task_id")))
    if kind == "active":
        rel = _text(docs_cfg.get("active_task_dir")) or "docs/tasks/active"
        suffix = ".md"
    elif kind == "closure":
        rel = _text(docs_cfg.get("task_closure_dir")) or "docs/tasks/closures"
        suffix = ".md"
    elif kind == "evidence":
        rel = _text(docs_cfg.get("task_evidence_dir")) or "docs/tasks/evidence"
        suffix = ".jsonl"
    else:
        raise APError(f"Unknown task document kind: {kind}")
    return repo / rel / f"{task_id}{suffix}"


def _create_active_task_doc(repo: Path, cfg: dict, manifest: dict) -> None:
    path = _task_doc_path(repo, cfg, manifest, "active")
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"# Task {manifest['task_id']}",
                "",
                "- Status: Active",
                f"- Base: `{manifest['base_ref']}` (`{manifest['base_sha'][:12]}`)",
                f"- Target: `{manifest['remote']}/{manifest['target_branch']}`",
                f"- Branch: `{manifest['task_branch']}`",
                f"- Worktree: `{manifest['worktree_path']}`",
                f"- Orchestrator: {manifest.get('owner') or 'TODO'}",
                f"- Owning fixer: {(manifest.get('writer_lease') or {}).get('holder') or 'TODO'}",
                "- Owned paths: " + ", ".join(f"`{item}`" for item in manifest.get("owned_paths") or []),
                "- Depends on integrated tasks: "
                + (
                    ", ".join(
                        f"`{item}`@`{(manifest.get('prerequisite_shas') or {}).get(item, '')[:12]}`"
                        for item in manifest.get("depends_on") or []
                    )
                    or "none"
                ),
                "- Reviewer / stable diff: TODO",
                "- Review verdict: pending",
                "- Scope: TODO",
                "- Development acceptance: TODO",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _update_active_task_status(repo: Path, cfg: dict, manifest: dict, status: str) -> None:
    path = _task_doc_path(repo, cfg, manifest, "active")
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(r"(?m)^- Status: .*?$", f"- Status: {status}", text, count=1)
    if count == 0:
        updated = text.rstrip() + f"\n- Status: {status}\n"
    if updated != text:
        path.write_text(updated, encoding="utf-8")


def _rollback_fresh_task_worktree(
    repo: Path,
    worktree: Path,
    task_branch: str,
    expected_tip: str,
) -> bool:
    run(["git", "worktree", "unlock", str(worktree)], cwd=repo, check=False)
    removed = run(
        ["git", "worktree", "remove", "--force", str(worktree)],
        cwd=repo,
        check=False,
    )
    if removed.returncode == 0:
        run(
            ["git", "update-ref", "-d", f"refs/heads/{task_branch}", expected_tip],
            cwd=repo,
            check=False,
        )
    return removed.returncode == 0


def cmd_task_start(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    _task_isolation(cfg)
    access_issues = _access_config_issues(cfg)
    if access_issues:
        raise APError(
            "Project initialization is incomplete; fill docs/ENGINEERING.md before starting work:\n- "
            + "\n- ".join(access_issues)
        )
    task_id = _validate_task_id(args.task_id)
    _require_control_checkout(repo)
    remote, target_branch, base_ref = _task_remote_and_target(cfg, args)
    concurrency_cfg = _concurrency_cfg(cfg)
    timeout_s = float(concurrency_cfg.get("lock_timeout_sec") or 30)

    with (
        _repo_lock(repo, "integration", timeout_s=timeout_s),
        _repo_lock(repo, "task-registry", timeout_s=timeout_s),
    ):
        if _read_json_object(_task_registry_path(repo, task_id)):
            raise APError(f"Task is already registered: {task_id}")

        common_submodule_config = _common_submodule_config(repo)
        _seed_control_submodule_config(repo)
        task_uuid = uuid.uuid4().hex

        if not getattr(args, "no_fetch", False) and base_ref.startswith(f"{remote}/"):
            _fetch_target(repo, remote, target_branch)
        base_sha = _resolve_commit(repo, base_ref)
        owned_paths = sorted({_normalize_owned_path(item) for item in (args.owned_path or [])})
        if not owned_paths:
            raise APError("task-start requires at least one --owned-path.")
        depends_on: list[str] = []
        prerequisite_shas: dict[str, str] = {}
        for raw_dependency in args.depends_on or []:
            dependency, separator, sha = _text(raw_dependency).partition("=")
            dependency = _validate_task_id(dependency)
            if not separator or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", sha):
                raise APError("--depends-on must use TASK_ID=full_commit_SHA.")
            if dependency in prerequisite_shas and prerequisite_shas[dependency] != sha:
                raise APError(f"Conflicting prerequisite SHAs for {dependency}.")
            depends_on.append(dependency)
            prerequisite_shas[dependency] = sha
        depends_on = sorted(set(depends_on))
        dependency_contract = {
            "depends_on": depends_on,
            "prerequisite_shas": prerequisite_shas,
        }
        _require_dependencies(repo, dependency_contract, base_sha)
        owner = _text(getattr(args, "owner", "")) or _text(os.environ.get("CODEX_THREAD_ID"))
        if not owner:
            raise APError("task-start requires --owner or CODEX_THREAD_ID.")
        writer = _text(getattr(args, "writer", "")) or owner
        prefix = _task_branch_prefix(cfg)
        task_branch = f"{prefix}{task_id}"
        check_ref = run(["git", "check-ref-format", "--branch", task_branch], cwd=repo, check=False)
        if check_ref.returncode != 0:
            raise APError(f"Invalid task branch name: {task_branch}")
        if _git_ref_exists(repo, f"refs/heads/{task_branch}"):
            raise APError(f"Task branch already exists: {task_branch}. Run task-prune or choose another ID.")
        worktree = _task_worktree_path(repo, cfg, task_id, _text(getattr(args, "worktree_root", "")))
        if worktree.exists():
            raise APError(f"Task worktree path already exists: {worktree}")
        worktree.parent.mkdir(parents=True, exist_ok=True)
        run(
            [
                "git",
                "worktree",
                "add",
                "--no-track",
                "-b",
                task_branch,
                str(worktree),
                base_sha,
            ],
            cwd=repo,
        )
        run(
            ["git", "worktree", "lock", "--reason", f"auto-coding task {task_id}", str(worktree)],
            cwd=repo,
        )
        manifest = {
            "schema": 2,
            "task_id": task_id,
            "task_uuid": task_uuid,
            "owner": owner,
            "base_ref": base_ref,
            "base_sha": base_sha,
            "remote": remote,
            "target_branch": target_branch,
            "task_branch": task_branch,
            "worktree_path": str(worktree.resolve()),
            "control_worktree_path": str(repo.resolve()),
            "cleanup_policy": _cleanup_policy(cfg),
            "state": "active",
            "created_at": _now_iso(),
            "initial_untracked": [],
            "owned_paths": owned_paths,
            "depends_on": depends_on,
            "prerequisite_shas": prerequisite_shas,
            "writer_lease": {
                "holder": writer,
                "generation": 1,
                "state": "active",
                "acquired_at": _now_iso(),
            },
            "review": {
                "verdict": "pending",
                "diff_base": base_sha,
                "diff_head": "",
                "diff_fingerprint": "",
                "reviewer": "",
                "reviewed_at": "",
                "reason": "task started",
            },
            "claimed_paths": [],
            "remote_task_tip": "",
            "common_submodule_config": common_submodule_config,
        }
        try:
            _sync_task_submodule_config(
                repo,
                worktree,
                manifest,
                initial=True,
                check_common=True,
            )
        except APError as exc:
            rolled_back = _rollback_fresh_task_worktree(
                repo,
                worktree,
                task_branch,
                base_sha,
            )
            raise APError(
                f"Could not isolate task-local submodule config; fresh worktree rollback="
                f"{str(rolled_back).lower()}.\n{exc}"
            ) from exc
        initial_status = _git_status(worktree)
        initial_head = _resolve_commit(worktree, "HEAD")
        initial_branch = _current_branch(worktree)
        if initial_status or initial_head != base_sha or initial_branch != task_branch:
            rolled_back = _rollback_fresh_task_worktree(
                repo,
                worktree,
                task_branch,
                initial_head,
            )
            raise APError(
                "A checkout hook changed the new task worktree. The fresh worktree and branch were rolled "
                f"back={str(rolled_back).lower()} so hook-created content cannot be committed accidentally. "
                f"branch={initial_branch or '(detached)'} head={initial_head}\n{initial_status}"
            )
        _save_task_manifest(repo, manifest)
        _create_active_task_doc(worktree, cfg, manifest)

    print(f"[task-start] task={task_id}")
    print(f"[task-start] branch={task_branch}")
    print(f"[task-start] base={base_ref}@{base_sha}")
    print(f"[task-start] worktree={worktree}")
    print(f"[task-start] next: cd {worktree}")


def _task_status_payload(repo: Path, manifest: dict) -> dict:
    worktree = Path(_text(manifest.get("worktree_path")))
    task_branch = _text(manifest.get("task_branch"))
    local_ref = f"refs/heads/{task_branch}"
    tip = _resolve_commit(repo, local_ref) if _git_ref_exists(repo, local_ref) else ""
    remote = _text(manifest.get("remote")) or "origin"
    target = _text(manifest.get("target_branch"))
    remote_ref = f"refs/remotes/{remote}/{target}"
    merged = bool(
        tip
        and _git_ref_exists(repo, remote_ref)
        and run(["git", "merge-base", "--is-ancestor", tip, remote_ref], cwd=repo, check=False).returncode == 0
    )
    return {
        **manifest,
        "worktree_exists": worktree.exists(),
        "dirty": bool(_git_status(worktree)) if worktree.exists() else False,
        "local_branch_exists": bool(tip),
        "tip": tip,
        "merged_into_target": merged,
        "current_diff_fingerprint": _task_review_fingerprint(worktree, manifest)
        if worktree.exists()
        else "",
    }


def cmd_task_status(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    task_id = _text(getattr(args, "task_id", ""))
    manifests: list[dict] = []
    if task_id:
        manifests.append(_load_task_manifest(repo, _validate_task_id(task_id)))
    else:
        registry = _task_state_root(repo) / "tasks"
        for path in sorted(registry.glob("*.json")) if registry.exists() else []:
            payload = _read_json_object(path)
            if payload:
                manifests.append(_validate_task_manifest(repo, payload))
    statuses = [_task_status_payload(repo, manifest) for manifest in manifests]
    if args.json:
        print(json.dumps({"tasks": statuses}, ensure_ascii=False, indent=2))
        return
    if not statuses:
        print("[task-status] no registered tasks")
        return
    for status in statuses:
        print(
            f"[task-status] task={status['task_id']} state={status.get('state')} "
            f"branch={status.get('task_branch')} worktree={status.get('worktree_path')} "
            f"dirty={str(status['dirty']).lower()} merged={str(status['merged_into_target']).lower()}"
        )


def _task_lifecycle_context(repo: Path, cfg: dict, task_id: str) -> tuple[Path, Path, dict]:
    active = _active_task_manifest(repo)
    if active:
        manifest = _require_task_context(repo, cfg, task_id)
        return Path(_text(manifest.get("control_worktree_path"))).resolve(), repo, manifest
    manifest = _load_task_manifest(repo, task_id)
    _require_control_checkout(repo, manifest)
    return repo, Path(_text(manifest.get("worktree_path"))).resolve(), manifest


def cmd_task_review(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    task_id = _validate_task_id(args.task_id)
    control_repo, worktree, _ = _task_lifecycle_context(repo, cfg, task_id)
    timeout_s = float(_concurrency_cfg(cfg).get("lock_timeout_sec") or 30)
    with _repo_lock(control_repo, f"task-{task_id}", timeout_s=timeout_s):
        manifest = _load_task_manifest(control_repo, task_id)
        if _text(manifest.get("state")) not in {"active", "pushed", "integration-raced"}:
            raise APError(f"Task {task_id} is not reviewable in state={manifest.get('state')}.")
        if not worktree.exists():
            raise APError(f"Task worktree is missing: {worktree}")
        worktree_cfg = _load_cfg(worktree)
        unowned = _task_unowned_paths(worktree, worktree_cfg, manifest)
        if unowned:
            raise APError("Changes outside task owned_paths:\n- " + "\n- ".join(unowned))
        fingerprint = _task_review_fingerprint(worktree, manifest)
        supplied = _text(args.diff_fingerprint)
        if supplied != fingerprint:
            raise APError(
                f"Review fingerprint mismatch: supplied={supplied or '(missing)'}, current={fingerprint}."
            )
        reviewer = _text(getattr(args, "reviewer", "")) or _text(os.environ.get("CODEX_THREAD_ID"))
        if not reviewer:
            raise APError("task-review requires --reviewer or CODEX_THREAD_ID.")
        manifest["review"] = {
            "verdict": args.verdict,
            "diff_base": _text(manifest.get("base_sha")),
            "diff_head": _resolve_commit(worktree, "HEAD"),
            "diff_fingerprint": fingerprint,
            "reviewer": reviewer,
            "reviewed_at": _now_iso(),
            "reason": "",
        }
        _save_task_manifest(control_repo, manifest)
    print(f"[task-review] task={task_id} verdict={args.verdict} fingerprint={fingerprint}")


def cmd_task_handoff(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    task_id = _validate_task_id(args.task_id)
    control_repo, _, _ = _task_lifecycle_context(repo, cfg, task_id)
    actor = _text(os.environ.get("CODEX_THREAD_ID"))
    if not actor:
        raise APError("task-handoff requires CODEX_THREAD_ID for the current writer.")
    timeout_s = float(_concurrency_cfg(cfg).get("lock_timeout_sec") or 30)
    with _repo_lock(control_repo, f"task-{task_id}", timeout_s=timeout_s):
        manifest = _load_task_manifest(control_repo, task_id)
        if _text(manifest.get("state")) in {"integrated", "cleanup-pending"}:
            raise APError(f"Task {task_id} no longer accepts writer handoff.")
        lease = manifest.get("writer_lease") or {}
        generation = int(lease.get("generation") or 0)
        if _text(lease.get("holder")) != args.from_writer:
            raise APError("--from must match the current writer lease holder.")
        if actor not in {args.from_writer, _text(manifest.get("owner"))}:
            raise APError("Only the current writer or task lifecycle owner may hand off the task.")
        if args.generation is not None and args.generation != generation:
            raise APError(f"Writer lease generation changed: expected={args.generation}, current={generation}.")
        lease.update(
            {
                "holder": args.to_writer,
                "generation": generation + 1,
                "state": "active",
                "acquired_at": _now_iso(),
            }
        )
        manifest["writer_lease"] = lease
        _save_task_manifest(control_repo, manifest)
    print(f"[task-handoff] task={task_id} writer={args.to_writer} generation={generation + 1}")


def cmd_task_resume(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    task_id = _validate_task_id(args.task_id)
    manifest = _load_task_manifest(repo, task_id)
    _require_control_checkout(repo, manifest)
    _require_current_writer(manifest, args)
    worktree = Path(_text(manifest.get("worktree_path"))).resolve()
    timeout_s = float(_concurrency_cfg(cfg).get("lock_timeout_sec") or 30)
    with (
        _repo_lock(repo, "integration", timeout_s=timeout_s),
        _repo_lock(repo, f"task-{task_id}", timeout_s=timeout_s),
    ):
        manifest = _load_task_manifest(repo, task_id)
        _require_current_writer(manifest, args)
        if _text(manifest.get("state")) != "conflicted":
            raise APError(f"Task {task_id} is not awaiting conflict resume.")
        for marker in ("rebase-merge", "rebase-apply"):
            path = Path(run(["git", "rev-parse", "--git-path", marker], cwd=worktree).stdout.strip())
            if not path.is_absolute():
                path = worktree / path
            if path.exists():
                raise APError("Rebase is still in progress; resolve conflicts and run git rebase --continue first.")
        if _git_status(worktree):
            raise APError("Task worktree must be clean before task-resume.")
        target_sha = _text(manifest.get("rebase_target_sha"))
        if not target_sha or run(
            ["git", "merge-base", "--is-ancestor", target_sha, "HEAD"],
            cwd=worktree,
            check=False,
        ).returncode != 0:
            raise APError("Resolved task HEAD does not contain the recorded rebase target.")
        manifest["base_sha"] = target_sha
        manifest["base_ref"] = target_sha
        unowned = _task_unowned_paths(worktree, _load_cfg(worktree), manifest)
        if unowned:
            raise APError("Resolved rebase changed paths outside owned_paths:\n- " + "\n- ".join(unowned))
        _invalidate_task_review(manifest, "rebase conflict resolved; review again")
        manifest["state"] = "active"
        _save_task_manifest(repo, manifest)
        _push_current_task(worktree, manifest)
    print(f"[task-resume] task={task_id} state=pushed review=pending")


def cmd_task_submodule_sync(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    task_id = _validate_task_id(args.task_id)
    manifest = _require_task_context(repo, cfg, task_id)
    if not manifest:
        raise APError("task-submodule-sync requires a registered task worktree.")
    control_repo = Path(_text(manifest.get("control_worktree_path"))).resolve()
    timeout_s = float(_concurrency_cfg(cfg).get("lock_timeout_sec") or 30)
    with (
        _repo_lock(control_repo, "integration", timeout_s=timeout_s),
        _repo_lock(control_repo, f"task-{task_id}", timeout_s=timeout_s),
    ):
        manifest = _require_task_context(repo, cfg, task_id)
        if not manifest:
            raise APError("Task manifest disappeared while synchronizing submodule config.")
        _sync_task_submodule_config(
            control_repo,
            repo,
            manifest,
            initial=False,
            check_common=True,
        )
        _save_task_manifest(repo, manifest)
    url_count = sum(
        1 for key in (manifest.get("submodule_config_claims") or {}) if key.endswith(".url")
    )
    print(f"[task-submodule-sync] OK task={task_id} urls={url_count}")


def _remote_branch_tip(repo: Path, remote: str, branch: str) -> str:
    result = run(["git", "ls-remote", "--heads", remote, f"refs/heads/{branch}"], cwd=repo, check=False)
    if result.returncode != 0:
        raise APError(
            f"Cannot inspect remote branch {remote}/{branch}: {result.stderr.strip() or result.stdout.strip()}"
        )
    if not result.stdout.strip():
        return ""
    return result.stdout.split()[0]


def _branch_is_occupied(repo: Path, task_branch: str) -> bool:
    wanted = f"refs/heads/{task_branch}"
    return any(
        line.strip() == f"branch {wanted}"
        for line in run(["git", "worktree", "list", "--porcelain"], cwd=repo).stdout.splitlines()
    )


def _delete_remote_task_branch(repo: Path, manifest: dict) -> bool:
    remote = _text(manifest.get("remote")) or "origin"
    branch = _text(manifest.get("task_branch"))
    actual_tip = _remote_branch_tip(repo, remote, branch)
    if not actual_tip:
        return True
    expected_tip = _text(manifest.get("remote_task_tip"))
    if not expected_tip or actual_tip != expected_tip:
        print(
            f"[task-cleanup] WARN: remote branch retained because its tip changed: "
            f"{remote}/{branch}",
            file=sys.stderr,
        )
        return False
    result = run(
        [
            "git",
            "push",
            "--no-verify",
            f"--force-with-lease=refs/heads/{branch}:{expected_tip}",
            remote,
            f":refs/heads/{branch}",
        ],
        cwd=repo,
        check=False,
    )
    if result.returncode != 0:
        print(
            f"[task-cleanup] WARN: failed to delete remote task branch {remote}/{branch}: "
            f"{result.stderr.strip()}",
            file=sys.stderr,
        )
        return False
    return True


def _finish_registered_task(
    repo: Path,
    cfg: dict,
    manifest: dict,
    *,
    keep_remote: bool = False,
) -> dict:
    manifest = _validate_task_manifest(repo, manifest)
    task_id = _validate_task_id(_text(manifest.get("task_id")))
    worktree = Path(_text(manifest.get("worktree_path")))
    branch = _text(manifest.get("task_branch"))
    remote = _text(manifest.get("remote")) or "origin"
    target = _text(manifest.get("target_branch"))
    cleanup_policy = _manifest_cleanup_policy(manifest, cfg)

    if worktree.exists():
        worktree_manifest = _active_task_manifest(worktree)
        if not worktree_manifest or _text(worktree_manifest.get("task_uuid")) != _text(manifest.get("task_uuid")):
            raise APError(f"Task worktree manifest does not match the registry for {task_id}.")
        _sync_task_submodule_config(
            repo,
            worktree,
            manifest,
            initial=False,
            check_common=True,
        )
        _save_task_manifest(repo, manifest)
        unsafe_ignored = _unsafe_ignored_paths(
            worktree,
            list(cleanup_policy.get("disposable_ignored") or []),
        )
        if unsafe_ignored:
            raise APError(
                "Task worktree contains ignored files that are not declared disposable; refusing cleanup:\n- "
                + "\n- ".join(unsafe_ignored)
            )
        dirty = _git_status(worktree)
        if dirty:
            raise APError(f"Task worktree is dirty; refusing cleanup for {task_id}:\n{dirty}")
        conflicts = run(["git", "ls-files", "-u"], cwd=worktree).stdout.strip()
        if conflicts:
            raise APError(f"Task worktree has unresolved conflicts; refusing cleanup for {task_id}.")

    target_sha = _fetch_target(repo, remote, target)
    local_ref = f"refs/heads/{branch}"
    tip = _resolve_commit(repo, local_ref) if _git_ref_exists(repo, local_ref) else _text(manifest.get("integrated_sha"))
    if not tip:
        raise APError(f"Task branch is missing and no integrated commit was recorded: {branch}")
    if run(["git", "merge-base", "--is-ancestor", tip, target_sha], cwd=repo, check=False).returncode != 0:
        raise APError(
            f"Task branch is not merged into {remote}/{target}; refusing cleanup for {task_id}."
        )

    if worktree.exists():
        archived_submodules = _prepare_submodules_for_removal(
            repo,
            manifest,
            worktree,
            list(cleanup_policy.get("disposable_ignored") or []),
        )
        run(["git", "worktree", "unlock", str(worktree)], cwd=repo, check=False)
        remove_command = ["git", "worktree", "remove"]
        if archived_submodules:
            # Git requires --force for any worktree that has ever initialized a
            # submodule. Reaching this branch means root and recursive submodule
            # state was checked, unknown ignored data was rejected, additional
            # linked worktrees were excluded, and Git state was archived. Do not
            # run `submodule deinit` here: its config changes are shared with the
            # primary checkout.
            remove_command.append("--force")
        remove_command.append(str(worktree))
        run(remove_command, cwd=repo)
    if _branch_is_occupied(repo, branch):
        raise APError(f"Task branch is still checked out by a worktree: {branch}")
    if _git_ref_exists(repo, local_ref):
        current_tip = _resolve_commit(repo, local_ref)
        if current_tip != tip:
            raise APError(f"Task branch moved during cleanup: {branch}")
        run(["git", "update-ref", "-d", local_ref, tip], cwd=repo)

    delete_remote = bool(cleanup_policy.get("delete_remote_branch", True))
    remote_deleted = False
    if delete_remote and not keep_remote:
        remote_deleted = _delete_remote_task_branch(repo, manifest)
    cleanup_pending = delete_remote and not keep_remote and not remote_deleted
    if cleanup_pending:
        manifest["state"] = "cleanup-pending"
        manifest["integrated_sha"] = tip
        _save_task_manifest(repo, manifest)
    else:
        _delete_task_manifest(repo, manifest)
    run(["git", "worktree", "prune"], cwd=repo, check=False)
    return {
        "task_id": task_id,
        "tip": tip,
        "target": f"{remote}/{target}",
        "remote_branch_deleted": remote_deleted,
        "cleanup_pending": cleanup_pending,
    }


def cmd_task_finish(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    task_id = _validate_task_id(args.task_id)
    manifest = _load_task_manifest(repo, task_id)
    _require_control_checkout(repo, manifest)
    timeout_s = float(_concurrency_cfg(cfg).get("lock_timeout_sec") or 30)
    with (
        _repo_lock(repo, "integration", timeout_s=timeout_s),
        _repo_lock(repo, f"task-{task_id}", timeout_s=timeout_s),
    ):
        manifest = _load_task_manifest(repo, task_id)
        result = _finish_registered_task(
            repo,
            cfg,
            manifest,
            keep_remote=bool(getattr(args, "keep_remote", False)),
        )
    print(
        f"[task-finish] OK task={task_id} target={result['target']} "
        f"remote_branch_deleted={str(result['remote_branch_deleted']).lower()}"
    )


def cmd_task_integrate(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    task_id = _validate_task_id(args.task_id)
    manifest = _load_task_manifest(repo, task_id)
    _require_control_checkout(repo, manifest)
    _require_current_writer(manifest, args)
    worktree = Path(_text(manifest.get("worktree_path")))
    if repo.resolve() == worktree.resolve():
        raise APError("Run task-integrate from the primary/control checkout, not from the task worktree.")
    timeout_s = float(_concurrency_cfg(cfg).get("lock_timeout_sec") or 30)

    with (
        _repo_lock(repo, "integration", timeout_s=timeout_s),
        _repo_lock(repo, f"task-{task_id}", timeout_s=timeout_s),
    ):
        manifest = _load_task_manifest(repo, task_id)
        _require_current_writer(manifest, args)
        worktree = Path(_text(manifest.get("worktree_path")))
        if not worktree.exists():
            raise APError(f"Task worktree is missing: {worktree}")
        worktree_manifest = _active_task_manifest(worktree)
        if not worktree_manifest or _text(worktree_manifest.get("task_uuid")) != _text(manifest.get("task_uuid")):
            raise APError(f"Task worktree manifest does not match the registry for {task_id}.")
        _sync_task_submodule_config(
            repo,
            worktree,
            manifest,
            initial=False,
            check_common=True,
        )
        _save_task_manifest(repo, manifest)
        if _text(manifest.get("state")) not in {"pushed", "integration-raced"}:
            raise APError(f"Task {task_id} must be committed and pushed before integration.")
        dirty = _git_status(worktree)
        if dirty:
            raise APError(f"Task worktree is dirty; run commit-push before integration:\n{dirty}")

        remote = _text(manifest.get("remote")) or "origin"
        target = _text(manifest.get("target_branch"))
        task_cfg = _load_cfg(worktree)
        target_sha = _fetch_target(worktree, remote, target)
        _require_dependencies(worktree, manifest, target_sha)
        _require_approved_review(worktree, task_cfg, manifest)
        if target_sha == _text(manifest.get("base_sha")):
            rebase = None
        else:
            rebase = run(["git", "rebase", target_sha], cwd=worktree, check=False)
        if rebase is not None and rebase.returncode != 0:
            manifest["state"] = "conflicted"
            manifest["rebase_target_sha"] = target_sha
            _invalidate_task_review(manifest, "integration rebase conflicted")
            _save_task_manifest(repo, manifest)
            raise APError(
                f"Task integration rebase conflicted for {task_id}; resolve it only in {worktree}.\n"
                f"{rebase.stdout}\n{rebase.stderr}"
            )
        if rebase is not None:
            manifest["base_sha"] = target_sha
            manifest["base_ref"] = target_sha
            manifest["rebase_target_sha"] = ""
            _invalidate_task_review(manifest, "target changed and task was rebased; review again")
            manifest["state"] = "active"
            _save_task_manifest(repo, manifest)
            _push_current_task(worktree, manifest)
            raise APError(
                f"Task {task_id} was rebased onto {target_sha}; the task backup branch was updated. "
                "Run task-review again before final integration."
            )

        _sync_task_submodule_config(
            repo,
            worktree,
            manifest,
            initial=False,
            check_common=True,
        )
        _save_task_manifest(repo, manifest)

        manifest = _require_task_context(worktree, task_cfg, task_id) or manifest
        _require_current_writer(manifest, args)
        _require_approved_review(worktree, task_cfg, manifest)
        task_tip = _resolve_commit(worktree, "HEAD")
        if _resolve_commit(worktree, "HEAD") != task_tip:
            raise APError("HEAD moved before the target push; refusing to push.")
        if run(
            ["git", "merge-base", "--is-ancestor", target_sha, task_tip],
            cwd=worktree,
            check=False,
        ).returncode != 0:
            raise APError(f"Integration tip {task_tip} is not a descendant of target base {target_sha}.")
        push = run(
            [
                "git",
                "push",
                f"--force-with-lease=refs/heads/{target}:{target_sha}",
                remote,
                f"{task_tip}:refs/heads/{target}",
            ],
            cwd=worktree,
            check=False,
        )
        if push.returncode != 0:
            manifest["state"] = "integration-raced"
            manifest["integration_tip"] = task_tip
            _save_task_manifest(repo, manifest)
            raise APError(
                f"Target branch moved while integrating {task_id}. Re-run task-integrate to fetch and "
                f"rebase the new target.\n{push.stdout}\n{push.stderr}"
            )

        fresh_target = _fetch_target(worktree, remote, target)
        if run(
            ["git", "merge-base", "--is-ancestor", task_tip, fresh_target],
            cwd=worktree,
            check=False,
        ).returncode != 0:
            raise APError(
                f"Remote target verification mismatch after push: {task_tip} is not in {fresh_target}."
            )
        if _resolve_commit(worktree, "HEAD") != task_tip:
            raise APError("A push hook changed the task branch after integration; remote target is safe, local state needs review.")
        manifest["state"] = "integrated"
        manifest["integrated_sha"] = task_tip
        manifest["integration_base_sha"] = target_sha
        _save_task_manifest(repo, manifest)

        cleanup_enabled = bool(
            _manifest_cleanup_policy(manifest, cfg).get("cleanup_merged", True)
        )
        if cleanup_enabled and not getattr(args, "keep_worktree", False):
            result = _finish_registered_task(
                repo,
                cfg,
                manifest,
                keep_remote=bool(getattr(args, "keep_remote", False)),
            )
        else:
            result = {
                "task_id": task_id,
                "target": f"{remote}/{target}",
                "remote_branch_deleted": False,
            }

    print(
        f"[task-integrate] OK task={task_id} target={result['target']} commit={task_tip} "
        f"cleaned={str(cleanup_enabled and not getattr(args, 'keep_worktree', False)).lower()}"
    )


def _worktree_branches(repo: Path) -> set[str]:
    branches: set[str] = set()
    for line in run(["git", "worktree", "list", "--porcelain"], cwd=repo).stdout.splitlines():
        if line.startswith("branch refs/heads/"):
            branches.add(line[len("branch refs/heads/") :].strip())
    return branches


def cmd_task_prune(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    _require_control_checkout(repo)
    concurrency_cfg = _concurrency_cfg(cfg)
    remote = _text(concurrency_cfg.get("remote")) or "origin"
    target = _text(concurrency_cfg.get("target_branch")) or _current_branch(repo) or "dev"
    prefix = _task_branch_prefix(cfg)
    timeout_s = float(concurrency_cfg.get("lock_timeout_sec") or 30)
    removed: list[str] = []
    skipped: list[str] = []

    with _repo_lock(repo, "integration", timeout_s=timeout_s):
        registry = _task_state_root(repo) / "tasks"
        registered_branches: set[str] = set()
        for path in list(sorted(registry.glob("*.json"))) if registry.exists() else []:
            manifest = _read_json_object(path)
            if not manifest:
                continue
            manifest = _validate_task_manifest(repo, manifest)
            branch = _text(manifest.get("task_branch"))
            registered_branches.add(branch)
            task_id = _validate_task_id(_text(manifest.get("task_id")))
            try:
                with _repo_lock(repo, f"task-{task_id}", timeout_s=timeout_s):
                    manifest = _read_json_object(path)
                    if not manifest:
                        continue
                    manifest = _validate_task_manifest(repo, manifest)
                    branch = _text(manifest.get("task_branch"))
                    if _text(manifest.get("state")) not in {"integrated", "cleanup-pending"}:
                        skipped.append(f"{branch}: state={_text(manifest.get('state')) or 'unknown'}")
                        continue
                    result = _finish_registered_task(repo, cfg, manifest)
            except APError as exc:
                skipped.append(f"{branch}: {exc}")
            else:
                if result["cleanup_pending"]:
                    skipped.append(f"{branch}: remote cleanup pending")
                else:
                    removed.append(branch)

        target_sha = _fetch_target(repo, remote, target)
        occupied = _worktree_branches(repo)
        result = run(
            [
                "git",
                "for-each-ref",
                "--format=%(refname:short)\t%(objectname)",
                f"refs/heads/{prefix}",
            ],
            cwd=repo,
        )
        for line in result.stdout.splitlines():
            if not line.strip() or "\t" not in line:
                continue
            branch, tip = line.split("\t", 1)
            if branch in registered_branches:
                skipped.append(f"{branch}: registered task")
                continue
            if branch in occupied:
                skipped.append(f"{branch}: occupied")
                continue
            if run(["git", "merge-base", "--is-ancestor", tip, target_sha], cwd=repo, check=False).returncode != 0:
                skipped.append(f"{branch}: unmerged")
                continue
            run(["git", "update-ref", "-d", f"refs/heads/{branch}", tip], cwd=repo)
            removed.append(branch)

        for path in sorted(registry.glob("*.json")) if registry.exists() else []:
            manifest = _read_json_object(path)
            if not manifest:
                continue
            manifest = _validate_task_manifest(repo, manifest)
            if _text(manifest.get("state")) == "cleanup-pending":
                continue
            branch = _text(manifest.get("task_branch"))
            if _git_ref_exists(repo, f"refs/heads/{branch}"):
                continue
            worktree = Path(_text(manifest.get("worktree_path")))
            if worktree.exists():
                continue
            path.unlink(missing_ok=True)
        run(["git", "worktree", "prune"], cwd=repo, check=False)

    if args.json:
        print(json.dumps({"removed": removed, "skipped": skipped}, ensure_ascii=False, indent=2))
        return
    print(f"[task-prune] removed={len(removed)} skipped={len(skipped)}")
    for branch in removed:
        print(f"[task-prune] removed: {branch}")
    for detail in skipped:
        print(f"[task-prune] kept: {detail}")


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
            profile=str(getattr(args, "effective_profile", "") or getattr(args, "profile", "") or ""),
            structure_check=structure_check,
            initial_commit=args.initial_commit,
            jenkins_failure=args.jenkins_failure,
            fix_commit=args.fix_commit,
        )
    )


def _commit_exact_index(repo: Path, message: str) -> str:
    expected_parent = _resolve_commit(repo, "HEAD")
    expected_tree = run(["git", "write-tree"], cwd=repo).stdout.strip()
    run(["git", "commit", "-m", message], cwd=repo)
    commit_sha = _resolve_commit(repo, "HEAD")
    actual_tree = run(["git", "rev-parse", "HEAD^{tree}"], cwd=repo).stdout.strip()
    parents = run(["git", "show", "-s", "--format=%P", "HEAD"], cwd=repo).stdout.strip().split()
    post_commit_staged = _checked_git_z_paths(
        repo,
        [
            "git",
            "diff",
            "--cached",
            "--name-only",
            "-z",
            "--diff-filter=ACDMRTUXB",
        ],
        "post-commit staged paths",
    )
    post_commit_unstaged = _unstaged_task_paths(repo)
    if (
        parents != [expected_parent]
        or actual_tree != expected_tree
        or post_commit_staged
        or post_commit_unstaged
    ):
        raise APError(
            "Git hooks or another writer changed the commit or working tree after staging. "
            "The local commit was not pushed; inspect HEAD and rerun the gate before publishing."
        )
    return commit_sha


def _push_current_task(repo: Path, manifest: dict, expected_commit: str = "") -> str:
    commit_sha = expected_commit or _resolve_commit(repo, "HEAD")
    if _resolve_commit(repo, "HEAD") != commit_sha:
        raise APError("HEAD moved after the verified commit; refusing to push.")
    remote = _text(manifest.get("remote")) or "origin"
    task_branch = _text(manifest.get("task_branch"))
    remote_tip = _remote_branch_tip(repo, remote, task_branch)
    command = ["git", "push", "--set-upstream"]
    # This is an internal backup branch, not the final project push. The
    # configured pre-push hook runs once later for the target-branch push.
    command.append("--no-verify")
    if remote_tip and run(
        ["git", "merge-base", "--is-ancestor", remote_tip, "HEAD"],
        cwd=repo,
        check=False,
    ).returncode != 0:
        expected_tip = _text(manifest.get("remote_task_tip"))
        if not expected_tip or expected_tip != remote_tip:
            raise APError(
                f"Remote task branch moved unexpectedly: {remote}/{task_branch}. "
                "No force push was attempted."
            )
        command.append(f"--force-with-lease=refs/heads/{task_branch}:{expected_tip}")
    command.extend([remote, f"{commit_sha}:refs/heads/{task_branch}"])
    run(command, cwd=repo)
    if _resolve_commit(repo, "HEAD") != commit_sha:
        raise APError("A push hook changed HEAD. The verified task commit was pushed, but local state needs review.")
    pushed_tip = _remote_branch_tip(repo, remote, task_branch)
    if pushed_tip != commit_sha:
        raise APError(
            f"Remote task branch verification failed: expected {commit_sha}, got {pushed_tip or '(missing)'}."
        )
    manifest["state"] = "pushed"
    manifest["remote_task_tip"] = commit_sha
    manifest["last_commit"] = commit_sha
    manifest["claimed_paths"] = _changed_files(repo, _text(manifest.get("base_sha")))
    review = manifest.get("review") or {}
    if _text(review.get("verdict")) == "approved":
        review["diff_head"] = commit_sha
        review["diff_fingerprint"] = _task_review_fingerprint(repo, manifest)
        manifest["review"] = review
    _save_task_manifest(repo, manifest)
    return commit_sha


def _cmd_commit_push_locked(
    args: argparse.Namespace,
    repo: Path,
    cfg: dict,
    manifest: dict,
) -> None:
    control_repo = Path(_text(manifest.get("control_worktree_path"))).resolve()
    _sync_task_submodule_config(
        control_repo,
        repo,
        manifest,
        initial=False,
        check_common=False,
    )
    _save_task_manifest(repo, manifest)
    _require_current_writer(manifest, args)
    _require_dependencies(repo, manifest, _text(manifest.get("base_sha")))
    _require_approved_review(repo, cfg, manifest)
    cmd_doctor(
        argparse.Namespace(
            repo=str(repo),
            profile=_text(getattr(args, "profile", "")).lower(),
            mode=_text(getattr(args, "mode", "")).lower(),
        )
    )
    base_ref = _text(manifest.get("base_sha"))
    plan = _resolve_execution_plan(
        cfg,
        repo,
        requested_scope="",
        requested_profile=_text(getattr(args, "profile", "")).lower(),
        requested_mode=_text(getattr(args, "mode", "")).lower(),
        base_ref=base_ref,
    )
    mode = str(plan["effective_mode"])
    args.effective_profile = str(plan["profile"])
    if args.result:
        _validate_closure_result(mode, str(args.result))

    msg = args.msg
    structure_check_status = "not part of the fast local gate"

    before_gate = _task_content_fingerprint(repo, cfg, manifest)
    cmd_light_gate(
        argparse.Namespace(
            repo=str(repo),
            scope="changed",
            profile=plan["profile"],
            mode="dev",
            base=base_ref,
            explain=False,
        )
    )

    after_gate = _task_content_fingerprint(repo, cfg, manifest)
    if after_gate != before_gate:
        raise APError(
            "The gate changed task-owned files or another writer modified this worktree. "
            "Review the changes and rerun commit-push; no files were staged or restored."
        )
    manifest = _require_task_context(repo, cfg, args.task_id)
    _require_current_writer(manifest, args)
    _require_approved_review(repo, cfg, manifest)

    if _task_content_fingerprint(repo, cfg, manifest) != after_gate:
        raise APError(
            "Task-owned files changed after the gate. Review them and rerun commit-push; "
            "no files were staged or restored."
        )

    dev_verification = args.verification or [
        "fast changed-scope gate passed",
        "project commit/push hooks remain enabled",
    ]
    _record_commit_push_closure(
        repo,
        args,
        commit="generated by this commit-push run",
        jenkins="owner-managed after push",
        target_env="owner-managed acceptance",
        verification=dev_verification,
        result=args.result or "DEV-CLOSED",
        follow_up=args.follow_up or "Complete the push stage with task-integrate; do not wait for Jenkins.",
        structure_check=args.structure_check or structure_check_status,
    )

    protected = set(manifest.get("initial_untracked") or [])
    _cleanup_generated_noise(repo, protected_paths=protected)
    pre_stage_fingerprint = _task_content_fingerprint(repo, cfg, manifest)
    manifest = _require_task_context(repo, cfg, args.task_id)
    _require_current_writer(manifest, args)
    _require_approved_review(repo, cfg, manifest)
    if _task_content_fingerprint(repo, cfg, manifest) != pre_stage_fingerprint:
        raise APError("Task-owned files changed immediately before staging; refusing to commit.")
    task_paths = _task_commit_paths(repo)
    staged = _stage_exact_paths(repo, task_paths)
    if not staged:
        raise APError("Nothing to commit.")
    unstaged = _unstaged_task_paths(repo)
    if unstaged:
        raise APError(
            "Task-owned files changed while staging; refusing to commit:\n- " + "\n- ".join(unstaged)
        )
    manifest = _require_task_context(repo, cfg, args.task_id)

    committed_sha = _commit_exact_index(repo, msg)
    _push_current_task(repo, manifest, committed_sha)
    print(f"[commit-push] OK - profile={plan['profile']} mode={mode} scope={plan['selected_scope']}")


def cmd_commit_push(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    manifest = _require_task_context(repo, cfg, args.task_id)
    _require_current_writer(manifest, args)
    lock_name = f"task-{_validate_task_id(args.task_id)}"
    timeout_s = float(_concurrency_cfg(cfg).get("lock_timeout_sec") or 30)
    with _repo_lock(repo, lock_name, timeout_s=timeout_s):
        _cmd_commit_push_locked(args, repo, cfg, manifest)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="autopipeline")
    p.add_argument("--repo", default=".")
    sp = p.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("install")
    s.add_argument("--bridges", action="store_true")
    s.add_argument("--force", action="store_true")
    s.add_argument("--full", action="store_true", help="Also materialize all optional document templates")
    s.set_defaults(func=cmd_install)

    s = sp.add_parser("scaffold")
    s.add_argument("group", choices=scaffold_groups() + ["all"])
    s.add_argument("--write", action="store_true")
    s.add_argument("--force", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_scaffold)

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
    s.add_argument("--profile", choices=sorted(_WORKFLOW_PROFILES), default="")
    s.add_argument("--mode", choices=["dev"], default="")
    s.add_argument("--base")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_impact)

    s = sp.add_parser("classify")
    s.add_argument("--scope", choices=sorted(_GATE_SCOPES), default="")
    s.add_argument("--profile", choices=sorted(_WORKFLOW_PROFILES), default="")
    s.add_argument("--mode", choices=["dev"], default="")
    s.add_argument("--base")
    s.add_argument("--planned-path", action="append")
    s.add_argument("--intent")
    s.add_argument("--intent-file")
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
    s.add_argument("--scope", choices=["auto", "changed"], default="")
    s.add_argument("--profile", choices=sorted(_WORKFLOW_PROFILES), default="")
    s.add_argument("--mode", choices=["dev"], default="")
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
    s.add_argument("--ci-build", "--jenkins", dest="jenkins", metavar="CI_BUILD")
    s.add_argument("--target-env")
    s.add_argument("--verification", action="append")
    s.add_argument("--profile", choices=sorted(_WORKFLOW_PROFILES - {"auto"}))
    s.add_argument("--structure-check")
    s.add_argument("--result", choices=["DEV-CLOSED", "PASS", "FAIL", "PARTIAL"], required=True)
    s.add_argument("--follow-up")
    s.add_argument("--initial-commit")
    s.add_argument("--ci-failure", "--jenkins-failure", dest="jenkins_failure", metavar="CI_FAILURE")
    s.add_argument("--fix-commit")
    s.set_defaults(func=cmd_record_closure)

    s = sp.add_parser("task-start")
    s.add_argument("task_id")
    s.add_argument("--base")
    s.add_argument("--target-branch")
    s.add_argument("--remote")
    s.add_argument("--worktree-root")
    s.add_argument("--owner")
    s.add_argument("--writer")
    s.add_argument("--owned-path", action="append")
    s.add_argument("--depends-on", action="append", metavar="TASK_ID=SHA")
    s.add_argument("--no-fetch", action="store_true")
    s.set_defaults(func=cmd_task_start)

    s = sp.add_parser("task-status")
    s.add_argument("task_id", nargs="?")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_task_status)

    s = sp.add_parser("task-submodule-sync")
    s.add_argument("task_id")
    s.set_defaults(func=cmd_task_submodule_sync)

    s = sp.add_parser("task-review")
    s.add_argument("task_id")
    s.add_argument("--verdict", choices=["approved", "changes-requested"], required=True)
    s.add_argument("--diff-fingerprint", required=True)
    s.add_argument("--reviewer")
    s.set_defaults(func=cmd_task_review)

    s = sp.add_parser("task-handoff")
    s.add_argument("task_id")
    s.add_argument("--from", dest="from_writer", required=True)
    s.add_argument("--to", dest="to_writer", required=True)
    s.add_argument("--generation", type=int)
    s.set_defaults(func=cmd_task_handoff)

    s = sp.add_parser("task-resume")
    s.add_argument("task_id")
    s.add_argument("--writer")
    s.set_defaults(func=cmd_task_resume)

    s = sp.add_parser("task-integrate")
    s.add_argument("task_id")
    s.add_argument("--keep-worktree", action="store_true")
    s.add_argument("--keep-remote", action="store_true")
    s.add_argument("--writer")
    s.set_defaults(func=cmd_task_integrate)

    s = sp.add_parser("task-finish")
    s.add_argument("task_id")
    s.add_argument("--keep-remote", action="store_true")
    s.set_defaults(func=cmd_task_finish)

    s = sp.add_parser("task-prune")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_task_prune)

    s = sp.add_parser("commit-push")
    s.add_argument("task_id")
    s.add_argument("--title")
    s.add_argument("--msg", required=True)
    s.add_argument("--mode", choices=["dev"])
    s.add_argument("--profile", choices=sorted(_WORKFLOW_PROFILES))
    s.add_argument("--verification", action="append")
    s.add_argument("--structure-check")
    s.add_argument("--result", choices=["DEV-CLOSED", "PASS", "FAIL", "PARTIAL"])
    s.add_argument("--follow-up")
    s.add_argument("--initial-commit")
    s.add_argument("--ci-failure", "--jenkins-failure", dest="jenkins_failure", metavar="CI_FAILURE")
    s.add_argument("--fix-commit")
    s.add_argument("--writer")
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
