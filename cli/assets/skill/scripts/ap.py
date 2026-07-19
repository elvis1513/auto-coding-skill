#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoPipeline Pro Max - repo automation CLI (python)"""

from __future__ import annotations

import argparse
import ast
import base64
import contextlib
import hashlib
import datetime as _dt
import fnmatch
import hmac
import io
import json
import os
import posixpath
import queue
import re
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import urllib.parse
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Iterator, Optional, List

from core import (
    APError,
    PROJECT_CONFIG_PATH,
    PROJECT_CONFIG_SCHEMA,
    copy_tree,
    ensure_git_repo,
    http_get_status,
    load_effective_config,
    load_managed_config,
    load_project_overrides,
    merge_project_config,
    parse_managed_config_payload,
    parse_project_overrides_payload,
    require_yaml,
    run,
    run_shell,
)
from install_integrity import verify_managed_install
from scaffold_templates import (
    MANAGED_FRAMEWORK_DOCS,
    PROJECT_FEEDBACK_PATTERNS,
    PROJECT_OWNED_DOC_ROOTS,
    scaffold_groups,
    templates_for,
)


_JENKINS_CRUMB_CACHE: dict[tuple[str, str], dict[str, str]] = {}
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
_FOCUSED_REVIEW_TIMEOUT_SECONDS = 150
_DEEP_REVIEW_TIMEOUT_SECONDS = 360
_REVIEW_STARTUP_TIMEOUT_SECONDS = 30.0
_REVIEW_RUNTIME_ATTEMPT_LIMIT = 2
_REVIEW_RUNTIME_FIELDS = (
    "runtime_state",
    "runtime_started_at",
    "runtime_finished_at",
    "runtime_result_path",
    "runtime_exit_code",
    "runtime_command_sha256",
    "runtime_receipt_path",
    "runtime_event_log_path",
    "runtime_receipt_sha256",
    "runtime_event_log_sha256",
    "runtime_result_sha256",
    "runtime_attempt_count",
    "runtime_failure_kind",
    "runtime_override_path",
    "runtime_override_sha256",
)
_REVIEW_OUTPUT_MAX_BYTES = 1024 * 1024
_REVIEW_DIFF_ARTIFACT_FORMAT = "git-binary-patch-v1"
_REVIEW_DIFF_ARTIFACT_MAX_BYTES = 64 * 1024 * 1024
_REVIEW_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FEEDBACK_SCHEMAS = {
    "auto-coding-skill-feedback/v1",
    "auto-coding-skill-feedback/v2",
}
_FEEDBACK_COLLECTION_SCHEMA = "auto-coding-skill-feedback-collection/v2"
_FEEDBACK_RESOLUTION_SCHEMA = "auto-coding-skill-feedback-resolutions/v1"
_FEEDBACK_RESOLUTION_POLICY = Path("data/policies/feedback-resolutions-v1.json")
_FEEDBACK_RESOLUTION_MAX_BYTES = 64 * 1024
_FEEDBACK_REPORT_MAX_BYTES = 16 * 1024
_FEEDBACK_PROJECT_MAX_REPORTS = 100
_FEEDBACK_PROJECT_MAX_ENTRIES = 200
_FEEDBACK_COLLECTION_MAX_BYTES = 1024 * 1024
_FEEDBACK_COLLECTION_MAX_REPORTS = 500
_FEEDBACK_COLLECTION_MAX_PROJECTS = 100
_PROJECT_CONFIG_RELATIVE = PROJECT_CONFIG_PATH
_INSTALL_TRANSACTION_RELATIVE = Path(".agents/.auto-coding-skill-install-transaction")
_EFFECTIVE_CONFIG_PATHS = {
    "docs/ENGINEERING.md",
    _PROJECT_CONFIG_RELATIVE.as_posix(),
}
_FEEDBACK_V1_FIELDS = (
    "schema",
    "report_id",
    "status",
    "created_at",
    "project",
    "observed_skill_version",
    "component",
    "kind",
    "impact",
    "origin_surface",
    "suspected_scope",
    "signature",
    "export",
)
_FEEDBACK_V2_FIELDS = (
    *_FEEDBACK_V1_FIELDS,
    "updated_at",
    "last_verified_skill_version",
    "resolution",
)
_FEEDBACK_STATUSES = {"open", "needs-evidence", "accepted", "duplicate", "resolved", "rejected"}
_FEEDBACK_ACTIVE_STATUSES = {"open", "needs-evidence", "accepted"}
_FEEDBACK_KINDS = {"defect", "gap"}
_FEEDBACK_IMPACTS = {"blocking", "degraded", "minor"}
_FEEDBACK_ORIGIN_SURFACES = {
    "managed-template",
    "managed-script",
    "managed-agent",
    "cli",
    "installer",
}
_FEEDBACK_RESOLUTIONS = {
    "pending",
    "fixed",
    "duplicate",
    "project-config",
    "environment",
    "not-shared",
    "not-reproducible",
    "wont-fix",
}
_FEEDBACK_CATALOG_DISPOSITIONS = {
    "fixed",
    "project-config",
    "environment",
    "duplicate",
    "rejected",
}
_FEEDBACK_HEADINGS = (
    "Symptom",
    "Expected",
    "Minimal reproduction",
    "Evidence",
    "Workaround",
    "Why shared",
)
_FEEDBACK_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_FEEDBACK_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FEEDBACK_SIGNATURE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_FEEDBACK_FILENAME_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9]+(?:-[a-z0-9]+)*-[0-9a-f]{8}\.md$"
)
_FEEDBACK_SENSITIVE_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bAuthorization\s*:\s*Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"https?://[^\s/:@]+:[^\s/@]+@", re.IGNORECASE),
    re.compile(r"(?:^|[\s`])/(?:Users|home)/[^/\s]+/"),
    re.compile(r"\b[A-Za-z]:\\Users\\[^\\\s]+\\", re.IGNORECASE),
)
_FEEDBACK_SEMVER_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_DEEP_REVIEW_CATEGORIES = {
    "api",
    "auth",
    "db",
    "file_transfer",
    "gateway",
    "payment",
    "prod_config",
}


class _ReviewerRuntimeFailure(RuntimeError):
    """Base class for supervised Reviewer runtime failures with safe diagnostics."""

    def __init__(self, message: str, diagnostics: Optional[dict] = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}
        self.stdout = _text(self.diagnostics.get("stdout"))
        self.stderr = _text(self.diagnostics.get("stderr"))


class _ReviewerRuntimeTimeout(_ReviewerRuntimeFailure):
    """Raised after the supervised Reviewer process group has been stopped."""

    def __init__(self, diagnostics: Optional[dict] = None) -> None:
        super().__init__(
            "Reviewer analysis exceeded its assignment deadline.",
            diagnostics,
        )


class _ReviewerRuntimeUnavailable(_ReviewerRuntimeFailure):
    """Raised when no semantic Reviewer event arrives during startup."""

    def __init__(self, diagnostics: Optional[dict] = None) -> None:
        super().__init__(
            "Reviewer runtime produced no semantic event before its startup deadline.",
            diagnostics,
        )


class _ReviewerRuntimeOutputLimit(_ReviewerRuntimeFailure):
    """Raised after bounded Reviewer output exceeds the private diagnostic limit."""

    def __init__(self, diagnostics: Optional[dict] = None) -> None:
        super().__init__("Reviewer runtime output exceeded its bounded limit.", diagnostics)


class _ReviewerRuntimeInternalError(_ReviewerRuntimeFailure):
    """Raised after an internal supervision failure has stopped the process group."""

    def __init__(self, diagnostics: Optional[dict] = None) -> None:
        super().__init__("Reviewer runtime supervision failed safely.", diagnostics)


def _review_startup_timeout_seconds() -> float:
    raw = _text(os.environ.get("AUTOCODING_REVIEW_STARTUP_TIMEOUT_SECONDS"))
    if not raw:
        return _REVIEW_STARTUP_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise APError(
            "AUTOCODING_REVIEW_STARTUP_TIMEOUT_SECONDS must be a positive number."
        ) from exc
    if value <= 0:
        raise APError(
            "AUTOCODING_REVIEW_STARTUP_TIMEOUT_SECONDS must be a positive number."
        )
    return min(value, _REVIEW_STARTUP_TIMEOUT_SECONDS)


def _review_diff_artifact_limit() -> int:
    raw = _text(os.environ.get("AUTOCODING_REVIEW_ARTIFACT_MAX_BYTES"))
    if not raw:
        return _REVIEW_DIFF_ARTIFACT_MAX_BYTES
    try:
        requested = int(raw)
    except ValueError as exc:
        raise APError("AUTOCODING_REVIEW_ARTIFACT_MAX_BYTES must be a positive integer.") from exc
    if requested < 1:
        raise APError("AUTOCODING_REVIEW_ARTIFACT_MAX_BYTES must be a positive integer.")
    return min(requested, _REVIEW_DIFF_ARTIFACT_MAX_BYTES)
_RECOMMENDED_FINAL_COMMAND_SECONDS = 120.0
_RECOMMENDED_FINAL_TOTAL_SECONDS = 180.0
_FINAL_GATE_CACHE_SCHEMA = 1
_FINAL_GATE_CACHE_ALGORITHM = "final-gate-v1"
_WORKFLOW_MIGRATION_POLICY = Path("data/policies/workflow-migrations-v1.json")
_FALLBACK_WORKFLOW_MIGRATION_POLICY = {
    "schema_version": 1,
    "managed_versions": {"agents": "4.3.3", "engineering": "4.3.3"},
    "known_official_engineering_body_sha256": [
        "d1306cc626e8baf8c83c953b760fd771066de2bf125168eca3a7b7d6ff2b87a2",
        "305931c6edef770033a4f1970b00e5fb1c1728351856a173dbfa497daf563021",
        "198d675361337bc272880154266b3eb1f50e3f82f3c6ab04b2e559cd18d8c7b4",
    ],
    "known_official_fragments": [],
    "conflict_rules": [
        {
            "id": "mandatory-high-risk-full",
            "paths": ["AGENTS.md", "docs/ENGINEERING.md"],
            "pattern": r"^(?:.*(?:high[- ]risk|高风险).*(?:must|required|requires|必须|需).*(?:full(?:[ -]gate)?|gate_full|verify|验证).*)$",
            "flags": "im",
            "message": "normal development must not require a full/verify gate",
        },
        {
            "id": "mandatory-change-full",
            "paths": ["AGENTS.md", "docs/ENGINEERING.md"],
            "pattern": r"^(?:.*(?:changes?|变更).*(?:require|required|requires|必须).*(?:full(?:[ -]gate)?|gate_full).*)$",
            "flags": "im",
            "message": "changed files must not automatically require a full gate",
        },
    ],
    "dependency_recovery": {
        "allowed_gate": "gate_changed",
        "requires_locked_dependency": True,
        "retry_same_gate_only": True,
        "forbid_full_gate_recovery": True,
    },
}
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
        raise APError("Health URL config incomplete. Fill the project configuration overlay.")
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
    docs_cfg = cfg.get("docs") or {}
    if manifest and _bool_config(docs_cfg.get("track_task_evidence"), False):
        task_dir = _text(docs_cfg.get("task_evidence_dir")) or "docs/tasks/evidence"
        return Path(repo, task_dir, f"{manifest['task_id']}.jsonl")
    if _bool_config(docs_cfg.get("track_evidence"), False) and _text(docs_cfg.get("evidence_log")):
        return Path(repo, _text(docs_cfg.get("evidence_log")))
    return _task_state_root(repo) / "evidence.jsonl"


def _gate_profile_path(repo: Path, cfg: dict) -> Path:
    gate_cfg = _gate_cfg(cfg)
    rel = _text(gate_cfg.get("profile_log"))
    return Path(repo, rel) if rel else _task_state_root(repo) / "gate-profile.jsonl"


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


def _run_configured_command(
    repo: Path,
    cfg: dict,
    name: str,
    *,
    timeout_s: Optional[float] = None,
) -> bool:
    commands = (cfg.get("commands") or {})
    command = str(commands.get(name) or "").strip()
    if not command:
        return False
    print(f"[run] {name}: {command}")
    start = time.time()
    try:
        run_shell(command, cwd=repo, timeout_s=timeout_s)
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


def _jenkins_access_cfg(cfg: dict, component: str) -> dict:
    access = cfg.get("access") or {}
    jenkins = access.get("jenkins") or {}
    value = jenkins.get(component) or {}
    return value if isinstance(value, dict) else {}


def _configured_jenkins_components(cfg: dict) -> list[str]:
    return [
        component
        for component in ("frontend", "backend")
        if any(
            _is_explicit_fill(value)
            for value in _jenkins_access_cfg(cfg, component).values()
        )
    ]


def _require_http_url(field: str, value: object) -> str:
    raw = _text(value).rstrip("/")
    parsed = urllib.parse.urlparse(raw)
    if not _is_explicit_fill(raw) or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise APError(f"Missing or invalid {field}; fill an http/https URL in the project configuration overlay.")
    return raw


def _resolve_jenkins_component(
    cfg: dict,
    requested: str = "",
    explicit_job_url: str = "",
) -> str:
    component = _text(requested).lower()
    configured = _configured_jenkins_components(cfg)
    if component:
        if component not in {"frontend", "backend"}:
            raise APError("Jenkins component must be frontend or backend.")
        if component not in configured:
            raise APError(f"Missing access.jenkins.{component} configuration.")
        return component
    explicit = _text(explicit_job_url).rstrip("/")
    if explicit:
        matches = [
            candidate
            for candidate in configured
            if _text(_jenkins_access_cfg(cfg, candidate).get("url")).rstrip("/") == explicit
        ]
        if len(matches) == 1:
            return matches[0]
    if len(configured) == 1:
        return configured[0]
    if len(configured) > 1:
        identities: set[tuple[str, str, str]] = set()
        for candidate in configured:
            lane = _jenkins_access_cfg(cfg, candidate)
            try:
                secret = _resolve_secret(f"access.jenkins.{candidate}", lane, "password")
            except APError:
                break
            identities.add(
                (
                    _text(lane.get("url")).rstrip("/"),
                    _text(lane.get("username")),
                    secret,
                )
            )
        if len(identities) == 1:
            return configured[0]
        raise APError(
            "Multiple access.jenkins endpoints are configured; pass --component frontend or backend."
        )
    return ""


def _jenkins_auth_config(cfg: dict, component: str = "") -> tuple[str, dict, str, str]:
    if component:
        lane = _jenkins_access_cfg(cfg, component)
        if not _is_explicit_fill(lane.get("username")):
            raise APError(f"Missing access.jenkins.{component}.username.")
        return f"access.jenkins.{component}", lane, "username", "password"

    jenkins_cfg = (cfg.get("jenkins") or {})
    credential_pairs = [
        ("api_user", "api_password"),
        ("ui_username", "ui_password"),
    ]
    errors: list[str] = []
    for user_field, secret_field in credential_pairs:
        user = _text(jenkins_cfg.get(user_field))
        if _is_explicit_fill(user):
            try:
                _resolve_secret("jenkins", jenkins_cfg, secret_field)
            except APError as exc:
                errors.append(str(exc))
                continue
            return "jenkins", jenkins_cfg, user_field, secret_field
    detail = "\n- " + "\n- ".join(errors) if errors else ""
    raise APError(
        "Missing Jenkins API credentials. Configure jenkins.api_user with "
        "jenkins.api_password or jenkins.api_password_env, or configure "
        "jenkins.ui_username with jenkins.ui_password or jenkins.ui_password_env."
        + detail
    )


def _jenkins_basic_auth_headers(cfg: dict, component: str = "") -> dict:
    section_name, section_cfg, user_field, secret_field = _jenkins_auth_config(cfg, component)
    user = _text(section_cfg.get(user_field))
    secret = _resolve_secret(section_name, section_cfg, secret_field)
    raw = f"{user}:{secret}".encode("utf-8")
    auth = base64.b64encode(raw).decode("ascii")
    return {"Authorization": f"Basic {auth}"}


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


def _jenkins_root_url(cfg: dict, job_url: str = "", component: str = "") -> str:
    jenkins_cfg = (cfg.get("jenkins") or {})
    lane_url = _text(_jenkins_access_cfg(cfg, component).get("url")) if component else ""
    base_url = "" if component else str(jenkins_cfg.get("base_url") or "").strip().rstrip("/")
    if base_url:
        return base_url

    source = str(job_url or lane_url or jenkins_cfg.get("job_url") or "").strip().rstrip("/")
    if not source:
        return ""
    if "/job/" in source:
        return source.split("/job/", 1)[0].rstrip("/")
    return source


def _jenkins_crumb_api_url(cfg: dict, job_url: str = "", component: str = "") -> str:
    root = _jenkins_root_url(cfg, job_url=job_url, component=component)
    if not root:
        return ""
    return root.rstrip("/") + "/crumbIssuer/api/json"


def _jenkins_crumb_headers(
    cfg: dict,
    job_url: str = "",
    timeout_s: int = 15,
    component: str = "",
) -> dict:
    crumb_url = _jenkins_crumb_api_url(cfg, job_url=job_url, component=component)
    if not crumb_url:
        return {}
    _, auth_cfg, user_field, _ = _jenkins_auth_config(cfg, component)
    cache_key = (crumb_url, _text(auth_cfg.get(user_field)))
    cached = _JENKINS_CRUMB_CACHE.get(cache_key)
    if cached:
        return dict(cached)

    headers = {"Accept": "application/json"}
    headers.update(_jenkins_basic_auth_headers(cfg, component))
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
    _JENKINS_CRUMB_CACHE[cache_key] = crumb_headers
    return dict(crumb_headers)


def _jenkins_api_get_json(
    url: str,
    cfg: dict,
    timeout_s: int = 15,
    allow_404: bool = False,
    component: str = "",
) -> Optional[dict]:
    headers = {"Accept": "application/json"}
    headers.update(_jenkins_basic_auth_headers(cfg, component))
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = _http_error_body(exc)
        if exc.code == 404 and allow_404:
            return None
        if exc.code == 403:
            crumb_headers = _jenkins_crumb_headers(
                cfg,
                job_url=url,
                timeout_s=timeout_s,
                component=component,
            )
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
                    "Fill jenkins.base_url in the project configuration overlay if needed."
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


def _resolve_jenkins_job_url(
    cfg: dict,
    job_name: str = "",
    job_url: str = "",
    component: str = "",
) -> str:
    jenkins_cfg = (cfg.get("jenkins") or {})
    explicit_url = str(job_url or "").strip()
    requested_name = str(job_name or "").strip()
    configured_url = (
        _text(_jenkins_access_cfg(cfg, component).get("url"))
        if component
        else str(jenkins_cfg.get("job_url") or "").strip()
    )
    base_url = _jenkins_root_url(cfg, component=component)

    if explicit_url:
        return explicit_url.rstrip("/")
    if requested_name:
        if base_url:
            return _jenkins_job_url_from_name(base_url, requested_name)
        raise APError(
            f"Cannot resolve Jenkins job URL for job '{requested_name}'. "
            "Pass --job-url, or fill the selected Jenkins endpoint in the project configuration overlay."
        )
    if configured_url:
        return configured_url.rstrip("/")
    raise APError(
        "Missing Jenkins job location. Fill access.jenkins.<component>.url or "
        "legacy jenkins.job_url, or pass --job-url / --job-name explicitly."
    )


def _resolve_jenkins_job_candidates(
    cfg: dict,
    repo: Path,
    git_ref: str = "",
    job_name: str = "",
    job_url: str = "",
    multibranch_root_job: str = "",
    branch_name: str = "",
    component: str = "",
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
    configured_url = (
        _text(_jenkins_access_cfg(cfg, component).get("url"))
        if component
        else str(jenkins_cfg.get("job_url") or "").strip()
    )

    if effective_branch:
        if explicit_url:
            return _jenkins_branch_job_urls(explicit_url, effective_branch)
        if effective_root:
            base_url = _jenkins_root_url(cfg, component=component)
            return _jenkins_branch_job_urls(_jenkins_job_url_from_name(base_url, effective_root), effective_branch)
        if explicit_name:
            base_url = _jenkins_root_url(cfg, component=component)
            return _jenkins_branch_job_urls(_jenkins_job_url_from_name(base_url, explicit_name), effective_branch)
        if configured_url:
            return _jenkins_branch_job_urls(configured_url, effective_branch)
        raise APError(
            "Missing Jenkins multibranch root job location. Pass --job-url / --job-name together with "
            "--branch-name, or pass --multibranch-root-job with a configured Jenkins endpoint."
        )

    return [
        _resolve_jenkins_job_url(
            cfg,
            job_name=job_name,
            job_url=job_url,
            component=component,
        )
    ]


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


_CORE_DOC_TEMPLATES: list[Path] = []


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
        return {"project_fast": "npm run test:changed"}
    return {}


def _mapping(value: object) -> dict:
    return value if isinstance(value, dict) else {}


_NO_CONFIG_DIFF = object()


def _config_values_equal(left: object, right: object) -> bool:
    """Compare parsed configuration without Python's bool/number coercions."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _config_values_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _config_values_equal(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    return left == right


def _config_semantic_diff(current: object, base: object, path: tuple[str, ...] = ()) -> object:
    """Return only project-owned values, excluding the managed release identity."""
    if path == ("workflow", "skill_version"):
        return _NO_CONFIG_DIFF
    if isinstance(current, dict) and isinstance(base, dict):
        result: dict = {}
        for key, value in current.items():
            field_path = (*path, str(key))
            if key not in base:
                if field_path != ("workflow", "skill_version"):
                    result[key] = json.loads(json.dumps(value))
                continue
            difference = _config_semantic_diff(value, base[key], field_path)
            if difference is not _NO_CONFIG_DIFF:
                result[key] = difference
        return result if result else _NO_CONFIG_DIFF
    if not _config_values_equal(current, base):
        return json.loads(json.dumps(current))
    return _NO_CONFIG_DIFF


def _config_difference_conflicts(
    difference: object,
    current: object,
    effective: object,
    path: tuple[str, ...] = (),
) -> list[str]:
    """Find legacy project values not preserved exactly by an existing overlay."""
    if difference is _NO_CONFIG_DIFF:
        return []
    if isinstance(difference, dict):
        if not isinstance(current, dict) or not isinstance(effective, dict):
            return [".".join(path) or "(root)"]
        conflicts: list[str] = []
        for key, value in difference.items():
            field_path = (*path, str(key))
            if key not in current or key not in effective:
                conflicts.append(".".join(field_path))
                continue
            conflicts.extend(
                _config_difference_conflicts(
                    value,
                    current[key],
                    effective[key],
                    field_path,
                )
            )
        return conflicts
    return [] if _config_values_equal(current, effective) else [".".join(path) or "(root)"]


_INSTALLED_ENGINEERING_TEMPLATE = Path(
    ".agents/skills/auto-coding-skill/data/templates/ENGINEERING.md"
)
_INSTALLED_MANIFEST = Path(".agents/managed-install.json")


def _installed_template_config(repo: Path) -> dict | None:
    relative = _INSTALLED_ENGINEERING_TEMPLATE
    payload = _safe_read_project_file(repo, relative, max_bytes=1024 * 1024)
    if payload is None:
        return None
    manifest_payload = _safe_read_project_file(repo, _INSTALLED_MANIFEST, max_bytes=4 * 1024 * 1024)
    if manifest_payload is None:
        raise APError(
            "Cannot trust the installed default template without .agents/managed-install.json; "
            "no files were written."
        )

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if not isinstance(key, str) or key in result:
                raise ValueError("invalid manifest mapping")
            result[key] = value
        return result

    try:
        manifest = json.loads(
            manifest_payload.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise APError("Installed managed manifest is invalid; no files were written.") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or manifest.get("manifest_path") != _INSTALLED_MANIFEST.as_posix()
        or not isinstance(manifest.get("entries"), list)
    ):
        raise APError("Installed managed manifest is invalid; no files were written.")
    if len(manifest["entries"]) > 10000:
        raise APError("Installed managed manifest has too many entries; no files were written.")
    matches = [
        entry
        for entry in manifest["entries"]
        if isinstance(entry, dict) and entry.get("path") == relative.as_posix()
    ]
    manifest_version = _text(manifest.get("skill_version"))
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", manifest_version):
        raise APError("Installed managed manifest has an invalid Skill version; no files were written.")
    if len(matches) != 1:
        raise APError("Installed default template is not bound by the managed manifest; no files were written.")
    entry = matches[0]
    expected_hash = _text(entry.get("sha256"))
    if (
        entry.get("ownership") != "exact"
        or entry.get("source") != "skill/data/templates/ENGINEERING.md"
        or entry.get("version") != manifest_version
        or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
        or hashlib.sha256(payload).hexdigest() != expected_hash
    ):
        raise APError("Installed default template failed its managed manifest identity check; no files were written.")
    config = parse_managed_config_payload(payload)
    config_version = _text(_mapping(config.get("workflow")).get("skill_version"))
    if config_version != manifest_version:
        raise APError("Installed default template version is not bound to its manifest; no files were written.")
    return config


def _render_project_overlay(overrides: dict) -> bytes:
    document = {"schema": PROJECT_CONFIG_SCHEMA, "overrides": overrides}
    dumped = require_yaml().safe_dump(document, allow_unicode=True, sort_keys=False)
    payload = dumped.encode("utf-8")
    # The installer must never create an overlay that its own runtime rejects.
    parse_project_overrides_payload(payload)
    return payload


def _project_config_convergence_plan(repo: Path, template: Path) -> dict:
    template_payload = template.read_bytes()
    template_cfg = parse_managed_config_payload(template_payload)
    try:
        template_text = template_payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise APError("Managed Skill template must be UTF-8.") from exc
    current_payload = _safe_read_project_file(
        repo,
        Path("docs/ENGINEERING.md"),
        max_bytes=1024 * 1024,
    )
    current_cfg: dict | None = None
    current_text = ""
    if current_payload is not None:
        try:
            current_text = current_payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise APError("Managed project configuration must be UTF-8.") from exc
        current_cfg = parse_managed_config_payload(current_payload)

    # Always validate an existing overlay before any installer write. Its bytes
    # are project-owned and are never normalized by ordinary convergence.
    overlay_payload = _safe_read_project_file(
        repo,
        _PROJECT_CONFIG_RELATIVE,
        max_bytes=128 * 1024,
    )
    overrides = (
        parse_project_overrides_payload(overlay_payload)
        if overlay_payload is not None
        else {}
    )
    old_base = None
    if current_cfg is not None:
        # A completed target document is self-identical to the trusted source
        # template, so retry does not depend on the previous install manifest.
        # Legacy/custom documents still require a manifest-bound old base.
        old_base = (
            template_cfg
            if current_payload == template_payload
            else _installed_template_config(repo)
        )
    overlay_output: bytes | None = None
    migrated_paths: list[str] = []

    if overlay_payload is None:
        if current_cfg is not None and old_base is None:
            current_version = _text(_mapping(current_cfg.get("workflow")).get("skill_version"))
            template_version = _text(_mapping(template_cfg.get("workflow")).get("skill_version"))
            if current_version != template_version:
                raise APError(
                    "Cannot migrate project configuration without its installed default template; "
                    "no files were written. Restore the current .agents Skill copy or create the "
                    "project overlay explicitly."
                )
            old_base = template_cfg
        difference = (
            _config_semantic_diff(current_cfg, old_base or template_cfg)
            if current_cfg is not None
            else _NO_CONFIG_DIFF
        )
        overrides = difference if isinstance(difference, dict) else {}
        if current_cfg is not None:
            semantic_base = old_base or template_cfg
            current_version = _text(_mapping(current_cfg.get("workflow")).get("skill_version"))
            base_version = _text(_mapping(semantic_base.get("workflow")).get("skill_version"))
            if current_version != base_version:
                raise APError(
                    "Installed default template version does not match docs/ENGINEERING.md; "
                    "no files were written."
                )
            if not _config_values_equal(
                merge_project_config(semantic_base, overrides),
                current_cfg,
            ):
                raise APError(
                    "Project configuration migration could not prove semantic equivalence; "
                    "no files were written."
                )
        project_cfg = overrides.setdefault("project", {})
        if not isinstance(project_cfg, dict):
            raise APError("Legacy project.project must be a mapping before configuration migration.")
        if not _text(project_cfg.get("name")):
            project_cfg["name"] = repo.name
        if current_cfg is None:
            inferred = _inferred_gate_commands(repo)
            if inferred:
                overrides.setdefault("commands", {}).update(inferred)
        # Validate protected fields and merge behavior before writing the new file.
        merge_project_config(template_cfg, overrides)
        overlay_output = _render_project_overlay(overrides)
        migrated_paths = sorted(_flatten_config_paths(overrides))
    elif current_cfg is not None:
        if old_base is None:
            raise APError(
                "Cannot verify an existing project overlay without the installed default template; "
                "no files were written."
            )
        current_version = _text(_mapping(current_cfg.get("workflow")).get("skill_version"))
        base_version = _text(_mapping(old_base.get("workflow")).get("skill_version"))
        if current_version != base_version:
            raise APError(
                "Installed default template version does not match docs/ENGINEERING.md; "
                "no files were written."
            )
        legacy_difference = _config_semantic_diff(current_cfg, old_base)
        legacy_overrides = legacy_difference if isinstance(legacy_difference, dict) else {}
        if not _config_values_equal(
            merge_project_config(old_base, legacy_overrides),
            current_cfg,
        ):
            raise APError(
                "Legacy project configuration cannot be represented as additive overrides; "
                "no files were written. Restore the deleted default field or create an explicit "
                "project overlay after reconciling the intended value."
            )
        legacy_effective = merge_project_config(old_base, overrides)
        conflicts = _config_difference_conflicts(
            legacy_difference,
            current_cfg,
            legacy_effective,
        )
        if conflicts:
            raise APError(
                "Existing project overlay conflicts with legacy project configuration; "
                "no files were written. Preserve these paths exactly in "
                "docs/project/auto-coding-skill.yaml: "
                + ", ".join(sorted(conflicts))
            )
        merge_project_config(template_cfg, overrides)

    return {
        "engineering_output": template_text,
        "engineering_current": current_text,
        "overlay_current": overlay_payload,
        "overlay_output": overlay_output,
        "migrated_paths": migrated_paths,
    }


def _flatten_config_paths(value: object, prefix: tuple[str, ...] = ()) -> list[str]:
    if not isinstance(value, dict) or not value:
        return [".".join(prefix)] if prefix else []
    result: list[str] = []
    for key, nested in value.items():
        result.extend(_flatten_config_paths(nested, (*prefix, str(key))))
    return result


def _sha256_payload(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


_ARCHIVE_TARGET_ATTEMPTS = 64


def _select_project_archive_target(
    repo: Path,
    preferred: str | Path,
    payload: bytes,
    *,
    legacy_digest_payload: bytes | None = None,
) -> tuple[Path, bool]:
    """Select an archive path without ever treating different bytes as archived."""
    preferred_rel = _safe_project_relative_path(preferred)
    payload_digest = hashlib.sha256(payload).hexdigest()
    legacy_digest = hashlib.sha256(
        payload if legacy_digest_payload is None else legacy_digest_payload
    ).hexdigest()[:12]
    preferred_suffix = preferred_rel.suffix
    legacy_candidate = preferred_rel.with_name(
        f"{preferred_rel.stem}-{legacy_digest}{preferred_suffix}"
    )
    path_digest = hashlib.sha256(preferred_rel.as_posix().encode("utf-8")).hexdigest()[:12]
    compact_stem = f".autocoding-archive-{path_digest}-{payload_digest}"

    candidates = [preferred_rel]
    try:
        if len(os.fsencode(legacy_candidate.name)) <= 240:
            candidates.append(legacy_candidate)
    except UnicodeEncodeError:
        pass
    candidates.append(preferred_rel.with_name(f"{compact_stem}{preferred_suffix}"))
    candidates.extend(
        preferred_rel.with_name(f"{compact_stem}-{attempt}{preferred_suffix}")
        for attempt in range(2, _ARCHIVE_TARGET_ATTEMPTS + 1)
    )

    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.as_posix()
        if key in seen:
            continue
        seen.add(key)
        archived = _safe_read_project_file(repo, candidate)
        if archived is None:
            return candidate, True
        if archived == payload:
            return candidate, False
    raise APError(
        "Cannot allocate a collision-free project archive target without overwriting "
        f"different content: {preferred_rel.as_posix()}"
    )


def cmd_project_config_prepare(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    template = _skill_root() / "data" / "templates" / "ENGINEERING.md"
    plan = _project_config_convergence_plan(repo, template)
    write = bool(args.write)
    current = plan["engineering_current"].encode("utf-8")
    engineering_output = plan["engineering_output"].encode("utf-8")
    overlay = plan["overlay_output"] or plan["overlay_current"]
    if overlay is None:
        raise APError("Project configuration prepare did not produce an overlay; no files were written.")
    finalize_required = bool(current and current != engineering_output)
    if finalize_required:
        template_cfg = parse_managed_config_payload(engineering_output)
        version = _text(_mapping(template_cfg.get("workflow")).get("skill_version")) or "current"
        archive_payload = (
            f"# Archived ENGINEERING.md before auto-coding-skill {version}\n\n"
            "Historical and non-authoritative. Project configuration was migrated to "
            "docs/project/auto-coding-skill.yaml.\n\n---\n\n"
        ).encode("utf-8") + current
        _select_project_archive_target(
            repo,
            Path(".agents/archive/auto-coding-skill") / version / "docs/ENGINEERING.md",
            archive_payload,
            legacy_digest_payload=current,
        )
    actions: list[dict] = []
    if plan["overlay_output"] is not None:
        actions.append({"action": "create", "path": _PROJECT_CONFIG_RELATIVE.as_posix()})
        if write:
            _safe_create_project_file(repo, _PROJECT_CONFIG_RELATIVE, overlay)
    if not current:
        actions.append({"action": "create", "path": "docs/ENGINEERING.md"})
        if write:
            _safe_write_project_file(repo, Path("docs/ENGINEERING.md"), engineering_output)
    elif finalize_required:
        actions.append({
            "action": "defer-replace",
            "path": "docs/ENGINEERING.md",
            "detail": "replace only after the effective-config runtime is installed",
        })
    result = {
        "mode": "write" if write else "plan",
        "actions": actions,
        "finalize_required": finalize_required,
        "engineering_before_sha256": _sha256_payload(current),
        "overlay_sha256": _sha256_payload(overlay),
        "template_sha256": _sha256_payload(engineering_output),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    for item in actions:
        print(f"[project-config-prepare] {item['action']}: {item['path']}")


def cmd_project_config_finalize(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    template = _skill_root() / "data" / "templates" / "ENGINEERING.md"
    template_payload = template.read_bytes()
    current = _safe_read_project_file(repo, Path("docs/ENGINEERING.md"), max_bytes=1024 * 1024)
    overlay = _safe_read_project_file(repo, _PROJECT_CONFIG_RELATIVE, max_bytes=128 * 1024)
    expected = {
        "engineering": _text(args.engineering_sha256),
        "overlay": _text(args.overlay_sha256),
        "template": _text(args.template_sha256),
    }
    if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in expected.values()):
        raise APError("Project configuration finalize requires valid SHA-256 bindings.")
    if current is None or overlay is None:
        raise APError("Prepared project configuration inputs are missing; no files were written.")
    actual = {
        "engineering": _sha256_payload(current),
        "overlay": _sha256_payload(overlay),
        "template": _sha256_payload(template_payload),
    }
    mismatched = [name for name in expected if expected[name] != actual[name]]
    if mismatched:
        raise APError(
            "Prepared project configuration changed before finalize; no files were written: "
            + ", ".join(mismatched)
        )
    # Validate the final layers before replacing the legacy managed document.
    template_cfg = parse_managed_config_payload(template_payload)
    overrides = parse_project_overrides_payload(overlay)
    merge_project_config(template_cfg, overrides)
    version = _text(_mapping(template_cfg.get("workflow")).get("skill_version")) or "current"
    archive_payload = (
        f"# Archived ENGINEERING.md before auto-coding-skill {version}\n\n"
        "Historical and non-authoritative. Project configuration was migrated to "
        "docs/project/auto-coding-skill.yaml.\n\n---\n\n"
    ).encode("utf-8") + current
    archive, archive_required = _select_project_archive_target(
        repo,
        Path(".agents/archive/auto-coding-skill") / version / "docs/ENGINEERING.md",
        archive_payload,
        legacy_digest_payload=current,
    )
    actions: list[dict] = []
    if archive_required:
        actions.append({"action": "archive", "path": archive.as_posix()})
        if args.write:
            _safe_create_project_file(repo, archive, archive_payload)
    if current != template_payload:
        actions.append({"action": "replace", "path": "docs/ENGINEERING.md"})
        if args.write:
            _safe_write_project_file(repo, Path("docs/ENGINEERING.md"), template_payload)
    result = {"mode": "write" if args.write else "plan", "actions": actions}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    for item in actions:
        print(f"[project-config-finalize] {item['action']}: {item['path']}")


_PROJECT_ARTIFACT_ROOTS = tuple(Path(value) for value in PROJECT_OWNED_DOC_ROOTS)


def _safe_project_relative_path(rel: str | Path) -> Path:
    value = Path(rel)
    if value.is_absolute() or not value.parts or any(part in {"", ".", ".."} for part in value.parts):
        raise APError(f"Unsafe project-relative path: {rel}")
    return value


def _is_windows_reparse_point(metadata: os.stat_result) -> bool:
    attributes = int(getattr(metadata, "st_file_attributes", 0) or 0)
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _project_path_identity(metadata: os.stat_result) -> tuple[int, int]:
    return int(metadata.st_dev), int(metadata.st_ino)


def _validate_windows_project_directories(
    relative: Path,
    directories: list[tuple[Path, tuple[int, int]]],
) -> None:
    for directory, identity in directories:
        metadata = directory.lstat()
        if (
            _is_windows_reparse_point(metadata)
            or not stat.S_ISDIR(metadata.st_mode)
            or _project_path_identity(metadata) != identity
        ):
            raise APError(f"Project path parent changed during its safety check: {relative}")


def _windows_project_path_snapshot(
    repo: Path,
    relative: Path,
    *,
    create_parents: bool,
) -> tuple[Path, list[tuple[Path, tuple[int, int]]], bool]:
    repo = Path(repo)
    repo_metadata = repo.lstat()
    if _is_windows_reparse_point(repo_metadata) or not stat.S_ISDIR(repo_metadata.st_mode):
        raise APError(f"Project repository root must be a real directory: {relative}")

    directories = [(repo, _project_path_identity(repo_metadata))]
    current = repo
    for index, part in enumerate(relative.parts[:-1]):
        current = current / part
        if not os.path.lexists(current):
            if not create_parents:
                _validate_windows_project_directories(relative, directories)
                remaining = Path(*relative.parts[index + 1 :])
                return current / remaining, directories, False
            _validate_windows_project_directories(relative, directories)
            try:
                current.mkdir()
            except FileExistsError:
                # A concurrent creator is acceptable only when the result is
                # still a real directory and all previously checked parents
                # retain their identities.
                pass
        _validate_windows_project_directories(relative, directories)
        metadata = current.lstat()
        if _is_windows_reparse_point(metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise APError(f"Project path component must be a real directory: {relative}")
        directories.append((current, _project_path_identity(metadata)))

    _validate_windows_project_directories(relative, directories)
    return current / relative.parts[-1], directories, True


def _fallback_safe_project_path(
    repo: Path,
    rel: str | Path,
    *,
    create_parents: bool = False,
) -> Path:
    relative = _safe_project_relative_path(rel)
    try:
        target, _, _ = _windows_project_path_snapshot(
            Path(repo),
            relative,
            create_parents=create_parents,
        )
        return target
    except APError:
        raise
    except OSError as exc:
        raise APError(f"Cannot access project path safely: {relative}") from exc


def _inject_project_file_parent_swap(repo: Path, relative: Path) -> None:
    if os.environ.get("AUTOCODING_TEST_MODE") != "1":
        return
    if os.environ.get("AUTOCODING_TEST_PROJECT_FILE_SWAP_PATH") != relative.as_posix():
        return
    if relative.parent == Path("."):
        raise APError("Project file parent-swap test requires a nested project path.")
    external = Path(os.environ.get("AUTOCODING_TEST_PROJECT_FILE_SWAP_EXTERNAL", ""))
    backup = Path(os.environ.get("AUTOCODING_TEST_PROJECT_FILE_SWAP_BACKUP", ""))
    target = Path(repo) / relative.parent
    if (
        not external.is_absolute()
        or not backup.is_absolute()
        or not external.is_dir()
        or external.is_symlink()
        or os.path.lexists(backup)
    ):
        raise APError("Invalid project file parent-swap test fixture.")
    target.rename(backup)
    target.symlink_to(external, target_is_directory=True)


@contextlib.contextmanager
def _open_project_parent(repo: Path, rel: str | Path, *, create: bool = False):
    relative = _safe_project_relative_path(rel)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptors: list[int] = []
    bindings: list[tuple[int, str, tuple[int, int]]] = []
    root_identity: tuple[int, int] | None = None

    def validate_bindings() -> None:
        assert root_identity is not None
        root_metadata = Path(repo).lstat()
        if (
            _is_windows_reparse_point(root_metadata)
            or not stat.S_ISDIR(root_metadata.st_mode)
            or _project_path_identity(root_metadata) != root_identity
        ):
            raise APError(f"Project repository root changed during its safety check: {relative}")
        for parent_fd, name, identity in bindings:
            metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or _project_path_identity(metadata) != identity
            ):
                raise APError(f"Project path parent changed during its safety check: {relative}")

    try:
        current = os.open(repo, directory_flags)
        descriptors.append(current)
        root_metadata = os.fstat(current)
        if not stat.S_ISDIR(root_metadata.st_mode):
            raise APError(f"Project repository root must be a real directory: {relative}")
        root_identity = _project_path_identity(root_metadata)
        missing = False
        for part in relative.parts[:-1]:
            try:
                metadata = os.stat(part, dir_fd=current, follow_symlinks=False)
            except FileNotFoundError:
                if not create:
                    missing = True
                    break
                os.mkdir(part, 0o755, dir_fd=current)
                metadata = os.stat(part, dir_fd=current, follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise APError(f"Project path component must be a real directory: {relative}")
            next_descriptor = os.open(part, directory_flags, dir_fd=current)
            opened = os.fstat(next_descriptor)
            identity = _project_path_identity(opened)
            if not stat.S_ISDIR(opened.st_mode) or identity != _project_path_identity(metadata):
                os.close(next_descriptor)
                raise APError(f"Project path parent changed during its safety check: {relative}")
            bindings.append((current, part, identity))
            descriptors.append(next_descriptor)
            current = next_descriptor
        _inject_project_file_parent_swap(Path(repo), relative)
        validate_bindings()
        yield (None if missing else current), relative.parts[-1]
        validate_bindings()
    except OSError as exc:
        raise APError(f"Cannot access project path safely: {relative}") from exc
    finally:
        for descriptor in reversed(descriptors):
            with contextlib.suppress(OSError):
                os.close(descriptor)


def _safe_read_project_file(
    repo: Path,
    rel: str | Path,
    *,
    max_bytes: int | None = None,
) -> bytes | None:
    relative = _safe_project_relative_path(rel)
    if max_bytes is not None and max_bytes <= 0:
        raise APError("max_bytes must be positive")
    if os.name == "nt":
        try:
            target, directories, parents_exist = _windows_project_path_snapshot(
                Path(repo),
                relative,
                create_parents=False,
            )
            if not parents_exist or not os.path.lexists(target):
                _validate_windows_project_directories(relative, directories)
                return None
            metadata = target.lstat()
            if _is_windows_reparse_point(metadata) or not stat.S_ISREG(metadata.st_mode):
                raise APError(f"Project file must be a regular non-symlink file: {relative}")
            identity = _project_path_identity(metadata)
            if max_bytes is not None and metadata.st_size > max_bytes:
                raise APError(f"Project file exceeds {max_bytes} bytes: {relative}")
            with target.open("rb") as handle:
                opened = os.fstat(handle.fileno())
                checked = target.lstat()
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or _project_path_identity(opened) != identity
                    or _is_windows_reparse_point(checked)
                    or not stat.S_ISREG(checked.st_mode)
                    or _project_path_identity(checked) != identity
                ):
                    raise APError(f"Project file changed during its safety check: {relative}")
                _validate_windows_project_directories(relative, directories)
                payload = handle.read() if max_bytes is None else handle.read(max_bytes + 1)
                opened_after = os.fstat(handle.fileno())
                checked_after = target.lstat()
                if (
                    not stat.S_ISREG(opened_after.st_mode)
                    or _project_path_identity(opened_after) != identity
                    or _is_windows_reparse_point(checked_after)
                    or not stat.S_ISREG(checked_after.st_mode)
                    or _project_path_identity(checked_after) != identity
                ):
                    raise APError(f"Project file changed while it was read: {relative}")
                _validate_windows_project_directories(relative, directories)
            if max_bytes is not None and len(payload) > max_bytes:
                raise APError(f"Project file exceeds {max_bytes} bytes: {relative}")
            return payload
        except APError:
            raise
        except OSError as exc:
            raise APError(f"Cannot read project file safely: {relative}") from exc
    with _open_project_parent(repo, relative) as (parent_fd, leaf):
        if parent_fd is None:
            return None
        descriptor = -1
        try:
            descriptor = os.open(leaf, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise APError(f"Project file must be a regular non-symlink file: {relative}") from exc
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise APError(f"Project file must be a regular non-symlink file: {relative}")
            if max_bytes is not None and metadata.st_size > max_bytes:
                raise APError(f"Project file exceeds {max_bytes} bytes: {relative}")
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                payload = handle.read() if max_bytes is None else handle.read(max_bytes + 1)
            if max_bytes is not None and len(payload) > max_bytes:
                raise APError(f"Project file exceeds {max_bytes} bytes: {relative}")
            return payload
        finally:
            if descriptor >= 0:
                os.close(descriptor)


@contextlib.contextmanager
def _open_project_directory(repo: Path, rel: str | Path):
    relative = _safe_project_relative_path(rel)
    if os.name == "nt":
        try:
            target, directories, complete = _windows_project_path_snapshot(
                Path(repo),
                relative,
                create_parents=False,
            )
        except OSError as exc:
            raise APError(f"Cannot access project directory safely: {relative}") from exc
        if not complete or not os.path.lexists(target):
            yield None
            return
        metadata = target.lstat()
        if _is_windows_reparse_point(metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise APError(f"Project directory must be a real directory: {relative}")
        identity = _project_path_identity(metadata)
        _validate_windows_project_directories(relative, directories)
        try:
            yield target
        finally:
            try:
                checked = target.lstat()
                _validate_windows_project_directories(relative, directories)
            except OSError as exc:
                raise APError(f"Project directory changed during its safety check: {relative}") from exc
            if (
                _is_windows_reparse_point(checked)
                or not stat.S_ISDIR(checked.st_mode)
                or _project_path_identity(checked) != identity
            ):
                raise APError(f"Project directory changed during its safety check: {relative}")
        return
    with _open_project_parent(repo, relative) as (parent_fd, leaf):
        if parent_fd is None:
            yield None
            return
        descriptor = -1
        try:
            descriptor = os.open(
                leaf,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            yield None
            return
        except OSError as exc:
            raise APError(f"Project directory must be a real directory: {relative}") from exc
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISDIR(metadata.st_mode):
                raise APError(f"Project directory must be a real directory: {relative}")
            yield descriptor
        finally:
            if descriptor >= 0:
                os.close(descriptor)


def _safe_write_project_file(repo: Path, rel: str | Path, payload: bytes) -> None:
    relative = _safe_project_relative_path(rel)
    if os.name == "nt":
        temporary: Path | None = None
        try:
            target, directories, _ = _windows_project_path_snapshot(
                Path(repo),
                relative,
                create_parents=True,
            )
            _inject_project_file_parent_swap(Path(repo), relative)
            target_identity: tuple[int, int] | None = None
            if os.path.lexists(target):
                metadata = target.lstat()
                if _is_windows_reparse_point(metadata) or not stat.S_ISREG(metadata.st_mode):
                    raise APError(f"Project file must be a regular non-symlink file: {relative}")
                target_identity = _project_path_identity(metadata)
            _validate_windows_project_directories(relative, directories)

            temporary = target.with_name(f".{target.name}.autocoding-{uuid.uuid4().hex}")
            with temporary.open("xb") as handle:
                opened = os.fstat(handle.fileno())
                checked = temporary.lstat()
                temporary_identity = _project_path_identity(opened)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or _is_windows_reparse_point(checked)
                    or not stat.S_ISREG(checked.st_mode)
                    or _project_path_identity(checked) != temporary_identity
                ):
                    raise APError(f"Temporary project file is unsafe: {relative}")
                _validate_windows_project_directories(relative, directories)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                opened_after = os.fstat(handle.fileno())
                checked_after = temporary.lstat()
                if (
                    not stat.S_ISREG(opened_after.st_mode)
                    or _project_path_identity(opened_after) != temporary_identity
                    or _is_windows_reparse_point(checked_after)
                    or not stat.S_ISREG(checked_after.st_mode)
                    or _project_path_identity(checked_after) != temporary_identity
                ):
                    raise APError(f"Temporary project file changed while writing: {relative}")
                _validate_windows_project_directories(relative, directories)

            if target_identity is None:
                if os.path.lexists(target):
                    raise APError(f"Project file appeared while writing: {relative}")
            else:
                checked_target = target.lstat()
                if (
                    _is_windows_reparse_point(checked_target)
                    or not stat.S_ISREG(checked_target.st_mode)
                    or _project_path_identity(checked_target) != target_identity
                ):
                    raise APError(f"Project file changed while writing: {relative}")
            _validate_windows_project_directories(relative, directories)
            os.replace(temporary, target)
            replaced = target.lstat()
            if (
                _is_windows_reparse_point(replaced)
                or not stat.S_ISREG(replaced.st_mode)
                or _project_path_identity(replaced) != temporary_identity
            ):
                raise APError(f"Project file changed after replacement: {relative}")
            _validate_windows_project_directories(relative, directories)
        except APError:
            if temporary is not None:
                with contextlib.suppress(OSError):
                    temporary.unlink()
            raise
        except OSError as exc:
            if temporary is not None:
                with contextlib.suppress(OSError):
                    temporary.unlink()
            raise APError(f"Cannot write project file safely: {relative}") from exc
        return
    with _open_project_parent(repo, relative, create=True) as (parent_fd, leaf):
        assert parent_fd is not None
        temporary = f".{leaf}.autocoding-{uuid.uuid4().hex}"
        descriptor = -1
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o644,
                dir_fd=parent_fd,
            )
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, leaf, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        except OSError as exc:
            with contextlib.suppress(OSError):
                os.unlink(temporary, dir_fd=parent_fd)
            raise APError(f"Cannot write project file safely: {relative}") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)


def _safe_create_project_file(repo: Path, rel: str | Path, payload: bytes) -> None:
    """Atomically publish a new project file without replacing a concurrent creator."""
    relative = _safe_project_relative_path(rel)
    if os.name == "nt":
        temporary: Path | None = None
        try:
            target, directories, _ = _windows_project_path_snapshot(
                Path(repo),
                relative,
                create_parents=True,
            )
            _inject_project_file_parent_swap(Path(repo), relative)
            _validate_windows_project_directories(relative, directories)
            temporary = target.with_name(f".{target.name}.autocoding-{uuid.uuid4().hex}")
            with temporary.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_metadata = os.fstat(handle.fileno())
                checked_temporary = temporary.lstat()
                temporary_identity = _project_path_identity(temporary_metadata)
                if (
                    not stat.S_ISREG(temporary_metadata.st_mode)
                    or _is_windows_reparse_point(checked_temporary)
                    or not stat.S_ISREG(checked_temporary.st_mode)
                    or _project_path_identity(checked_temporary) != temporary_identity
                ):
                    raise APError(f"Temporary project file is unsafe: {relative}")
                _validate_windows_project_directories(relative, directories)
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError as exc:
                raise APError(f"Project file appeared before create-only publish: {relative}") from exc
            checked_target = target.lstat()
            if (
                _is_windows_reparse_point(checked_target)
                or not stat.S_ISREG(checked_target.st_mode)
                or _project_path_identity(checked_target) != temporary_identity
            ):
                raise APError(f"Project file changed during create-only publish: {relative}")
            _validate_windows_project_directories(relative, directories)
        except APError:
            raise
        except OSError as exc:
            raise APError(f"Cannot create project file safely: {relative}") from exc
        finally:
            if temporary is not None:
                with contextlib.suppress(OSError):
                    temporary.unlink()
        return

    with _open_project_parent(repo, relative, create=True) as (parent_fd, leaf):
        assert parent_fd is not None
        temporary = f".{leaf}.autocoding-{uuid.uuid4().hex}"
        descriptor = -1
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o644,
                dir_fd=parent_fd,
            )
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            temporary_metadata = os.stat(
                temporary,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            if stat.S_ISLNK(temporary_metadata.st_mode) or not stat.S_ISREG(
                temporary_metadata.st_mode
            ):
                raise APError(f"Temporary project file is unsafe: {relative}")
            temporary_identity = _project_path_identity(temporary_metadata)
            try:
                os.link(
                    temporary,
                    leaf,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise APError(f"Project file appeared before create-only publish: {relative}") from exc
            published = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
            if (
                stat.S_ISLNK(published.st_mode)
                or not stat.S_ISREG(published.st_mode)
                or _project_path_identity(published) != temporary_identity
            ):
                raise APError(f"Project file changed during create-only publish: {relative}")
        except APError:
            raise
        except OSError as exc:
            raise APError(f"Cannot create project file safely: {relative}") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            with contextlib.suppress(OSError):
                os.unlink(temporary, dir_fd=parent_fd)


def _safe_chmod_project_file(repo: Path, rel: str | Path, mode: int) -> None:
    relative = _safe_project_relative_path(rel)
    if mode < 0 or mode > 0o777:
        raise APError(f"Project file mode must be between 000 and 777: {relative}")
    if os.name == "nt":
        try:
            target, directories, complete = _windows_project_path_snapshot(
                Path(repo),
                relative,
                create_parents=False,
            )
            _inject_project_file_parent_swap(Path(repo), relative)
            if not complete or not os.path.lexists(target):
                raise APError(f"Project file is missing: {relative}")
            metadata = target.lstat()
            if _is_windows_reparse_point(metadata) or not stat.S_ISREG(metadata.st_mode):
                raise APError(f"Project file must be a regular non-symlink file: {relative}")
            identity = _project_path_identity(metadata)
            _validate_windows_project_directories(relative, directories)
            os.chmod(target, mode, follow_symlinks=False)
            checked = target.lstat()
            _validate_windows_project_directories(relative, directories)
            if (
                _is_windows_reparse_point(checked)
                or not stat.S_ISREG(checked.st_mode)
                or _project_path_identity(checked) != identity
            ):
                raise APError(f"Project file changed while setting its mode: {relative}")
        except APError:
            raise
        except OSError as exc:
            raise APError(f"Cannot set project file mode safely: {relative}") from exc
        return

    with _open_project_parent(repo, relative) as (parent_fd, leaf):
        if parent_fd is None:
            raise APError(f"Project file is missing: {relative}")
        descriptor = -1
        try:
            descriptor = os.open(
                leaf,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_fd,
            )
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise APError(f"Project file must be a regular non-symlink file: {relative}")
            os.fchmod(descriptor, mode)
            checked = os.fstat(descriptor)
            if _project_path_identity(checked) != _project_path_identity(metadata):
                raise APError(f"Project file changed while setting its mode: {relative}")
        except APError:
            raise
        except OSError as exc:
            raise APError(f"Cannot set project file mode safely: {relative}") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)


_INTERNAL_PROJECT_FILE_MAX_BYTES = 32 * 1024 * 1024
_INTERNAL_PROJECT_CHMOD_MAX_BYTES = 1024 * 1024
_INTERNAL_PROJECT_CHMOD_MAX_ENTRIES = 4096


def cmd_project_file_safe(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    operation = _text(args.operation).lower()
    relative: Path | None = None
    if operation != "chmod-batch":
        relative = _safe_project_relative_path(args.path)
    if operation in {"write", "create"}:
        assert relative is not None
        payload = sys.stdin.buffer.read(_INTERNAL_PROJECT_FILE_MAX_BYTES + 1)
        if len(payload) > _INTERNAL_PROJECT_FILE_MAX_BYTES:
            raise APError(
                f"Internal project file payload exceeds {_INTERNAL_PROJECT_FILE_MAX_BYTES} bytes: {relative}"
            )
        if operation == "create":
            _safe_create_project_file(repo, relative, payload)
        else:
            _safe_write_project_file(repo, relative, payload)
        if _text(args.mode):
            try:
                mode = int(_text(args.mode), 8)
            except ValueError as exc:
                raise APError("Internal project write requires an octal --mode") from exc
            _safe_chmod_project_file(repo, relative, mode)
    elif operation == "chmod":
        assert relative is not None
        try:
            mode = int(_text(args.mode), 8)
        except ValueError as exc:
            raise APError("Internal project chmod requires an octal --mode") from exc
        _safe_chmod_project_file(repo, relative, mode)
    elif operation == "chmod-batch":
        payload = sys.stdin.buffer.read(_INTERNAL_PROJECT_CHMOD_MAX_BYTES + 1)
        if len(payload) > _INTERNAL_PROJECT_CHMOD_MAX_BYTES:
            raise APError("Internal project chmod batch exceeds its size limit")
        try:
            entries = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise APError("Internal project chmod batch must be valid UTF-8 JSON") from exc
        if not isinstance(entries, list) or len(entries) > _INTERNAL_PROJECT_CHMOD_MAX_ENTRIES:
            raise APError("Internal project chmod batch has an invalid entry count")
        mutations: list[tuple[Path, int]] = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict) or set(entry) != {"path", "mode"}:
                raise APError(f"Internal project chmod batch entry {index} is invalid")
            mode_text = entry.get("mode")
            path_text = entry.get("path")
            if not isinstance(mode_text, str) or not re.fullmatch(r"[0-7]{3}", mode_text):
                raise APError(f"Internal project chmod batch entry {index} has an invalid mode")
            if not isinstance(path_text, str) or not path_text:
                raise APError(f"Internal project chmod batch entry {index} has an invalid path")
            mutations.append(
                (_safe_project_relative_path(path_text), int(mode_text, 8))
            )
        for mutation_path, mutation_mode in mutations:
            _safe_chmod_project_file(repo, mutation_path, mutation_mode)
    else:
        raise APError(f"Unsupported internal project file operation: {operation}")
    if args.json:
        result = {"operation": operation, "ok": True}
        if relative is not None:
            result["path"] = relative.as_posix()
        else:
            result["entry_count"] = len(mutations)
        print(json.dumps(result))


def _directory_handle_identity(handle: int | Path) -> tuple[int, int]:
    metadata = os.fstat(handle) if isinstance(handle, int) else handle.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or (not isinstance(handle, int) and _is_windows_reparse_point(metadata))
    ):
        raise APError("Install I/O requires real project directories.")
    return _project_path_identity(metadata)


def _safe_ensure_project_directory(repo: Path, rel: str | Path) -> None:
    relative = _safe_project_relative_path(rel)
    if os.name == "nt":
        try:
            target, directories, _ = _windows_project_path_snapshot(
                Path(repo),
                relative,
                create_parents=True,
            )
            _validate_windows_project_directories(relative, directories)
            try:
                target.mkdir()
            except FileExistsError:
                pass
            metadata = target.lstat()
            if _is_windows_reparse_point(metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise APError(f"Project directory must be a real directory: {relative}")
            _validate_windows_project_directories(relative, directories)
        except APError:
            raise
        except OSError as exc:
            raise APError(f"Cannot create project directory safely: {relative}") from exc
        return
    with _open_project_parent(repo, relative, create=True) as (parent_fd, leaf):
        assert parent_fd is not None
        try:
            os.mkdir(leaf, 0o755, dir_fd=parent_fd)
        except FileExistsError:
            pass
        metadata = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise APError(f"Project directory must be a real directory: {relative}")


def _require_bound_project_directory(
    repo: Path,
    relative: Path,
    handle: int | Path,
    identity: tuple[int, int],
) -> None:
    opened = os.fstat(handle) if isinstance(handle, int) else handle.lstat()
    if not stat.S_ISDIR(opened.st_mode) or _project_path_identity(opened) != identity:
        raise APError(f"Install I/O directory handle changed: {relative}")
    target = repo / relative
    try:
        current = target.lstat()
    except OSError as exc:
        raise APError(f"Install I/O project parent changed: {relative}") from exc
    if (
        _is_windows_reparse_point(current)
        or not stat.S_ISDIR(current.st_mode)
        or _project_path_identity(current) != identity
    ):
        raise APError(f"Install I/O project parent changed: {relative}")


def _inject_install_io_parent_swap(repo: Path, phase: str) -> None:
    if os.environ.get("AUTOCODING_TEST_MODE") != "1":
        return
    if os.environ.get("AUTOCODING_TEST_INSTALL_IO_SWAP_PHASE") != phase:
        return
    relative_text = os.environ.get("AUTOCODING_TEST_INSTALL_IO_SWAP_PARENT", "")
    external_text = os.environ.get("AUTOCODING_TEST_INSTALL_IO_SWAP_EXTERNAL", "")
    backup_text = os.environ.get("AUTOCODING_TEST_INSTALL_IO_SWAP_BACKUP", "")
    relative = _safe_project_relative_path(relative_text)
    target = repo / relative
    external = Path(external_text)
    backup = Path(backup_text)
    if (
        not external.is_absolute()
        or not backup.is_absolute()
        or not external.is_dir()
        or external.is_symlink()
        or os.path.lexists(backup)
    ):
        raise APError("Invalid install I/O parent-swap test fixture.")
    target.rename(backup)
    target.symlink_to(external, target_is_directory=True)


def _open_directory_at(parent_fd: int, name: str) -> int:
    descriptor = os.open(
        name,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=parent_fd,
    )
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        os.close(descriptor)
        raise APError(f"Install I/O path must be a real directory: {name}")
    return descriptor


def _remove_tree_at(parent_fd: int, name: str, *, missing_ok: bool = False) -> None:
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        if missing_ok:
            return
        raise
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise APError(f"Install I/O refuses a symlink or non-directory tree: {name}")
    if not getattr(shutil.rmtree, "avoids_symlink_attacks", False):
        raise APError("This Python runtime cannot remove project trees without symlink attacks.")
    shutil.rmtree(name, dir_fd=parent_fd)


def _copy_file_between_fds(
    source_parent_fd: int,
    source_name: str,
    destination_parent_fd: int,
    destination_name: str,
) -> None:
    source_fd = -1
    destination_fd = -1
    temporary = f".{destination_name}.autocoding-{uuid.uuid4().hex}"
    try:
        source_fd = os.open(
            source_name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=source_parent_fd,
        )
        source_metadata = os.fstat(source_fd)
        if not stat.S_ISREG(source_metadata.st_mode):
            raise APError(f"Install I/O source must be a regular file: {source_name}")
        destination_fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            stat.S_IMODE(source_metadata.st_mode),
            dir_fd=destination_parent_fd,
        )
        while True:
            block = os.read(source_fd, 1024 * 1024)
            if not block:
                break
            view = memoryview(block)
            while view:
                written = os.write(destination_fd, view)
                view = view[written:]
        os.fsync(destination_fd)
        os.close(destination_fd)
        destination_fd = -1
        os.replace(
            temporary,
            destination_name,
            src_dir_fd=destination_parent_fd,
            dst_dir_fd=destination_parent_fd,
        )
    except APError:
        raise
    except OSError as exc:
        raise APError(f"Cannot copy install transaction file safely: {destination_name}") from exc
    finally:
        if source_fd >= 0:
            os.close(source_fd)
        if destination_fd >= 0:
            os.close(destination_fd)
        with contextlib.suppress(OSError):
            os.unlink(temporary, dir_fd=destination_parent_fd)


def _copy_directory_contents_fd(source_fd: int, destination_fd: int) -> None:
    for name in sorted(os.listdir(source_fd)):
        metadata = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
            os.mkdir(name, stat.S_IMODE(metadata.st_mode), dir_fd=destination_fd)
            source_child = _open_directory_at(source_fd, name)
            destination_child = _open_directory_at(destination_fd, name)
            try:
                _copy_directory_contents_fd(source_child, destination_child)
            finally:
                os.close(destination_child)
                os.close(source_child)
        elif stat.S_ISREG(metadata.st_mode):
            _copy_file_between_fds(source_fd, name, destination_fd, name)
        else:
            raise APError(f"Install I/O refuses a non-regular tree entry: {name}")


def _copy_directory_at(
    source_parent_fd: int,
    source_name: str,
    destination_parent_fd: int,
    destination_name: str,
) -> None:
    source_fd = _open_directory_at(source_parent_fd, source_name)
    destination_fd = -1
    try:
        source_metadata = os.fstat(source_fd)
        os.mkdir(destination_name, stat.S_IMODE(source_metadata.st_mode), dir_fd=destination_parent_fd)
        destination_fd = _open_directory_at(destination_parent_fd, destination_name)
        try:
            _copy_directory_contents_fd(source_fd, destination_fd)
        except BaseException:
            os.close(destination_fd)
            destination_fd = -1
            with contextlib.suppress(OSError, APError):
                _remove_tree_at(destination_parent_fd, destination_name, missing_ok=True)
            raise
        finally:
            if destination_fd >= 0:
                os.close(destination_fd)
    finally:
        os.close(source_fd)


def _unlink_file_at(parent_fd: int, name: str, *, missing_ok: bool = False) -> None:
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        if missing_ok:
            return
        raise
    if stat.S_ISDIR(metadata.st_mode):
        raise APError(f"Install I/O refuses to unlink a directory as a file: {name}")
    os.unlink(name, dir_fd=parent_fd)


def _install_io_owner(repo: Path) -> dict:
    payload = _safe_read_project_file(
        repo,
        _INSTALL_TRANSACTION_RELATIVE / "owner.json",
        max_bytes=4096,
    )
    if payload is None:
        raise APError("Install I/O requires a valid transaction owner.")
    try:
        owner = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise APError("Install I/O transaction owner is invalid.") from exc
    return _mapping(owner)


def _require_install_io_access(repo: Path, operation: str) -> None:
    owner = _install_io_owner(repo)
    token = os.environ.get("AUTOCODING_INSTALL_TRANSACTION_TOKEN", "")
    expected = _text(owner.get("token_sha256"))
    if re.fullmatch(r"[0-9a-f]{64}", token) and re.fullmatch(r"[0-9a-f]{64}", expected):
        actual = hashlib.sha256(token.encode("ascii")).hexdigest()
        if hmac.compare_digest(actual, expected):
            return
    if operation in {"recover", "complete"}:
        try:
            pid = int(owner.get("pid"))
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        except PermissionError as exc:
            raise APError("Install I/O recovery owner is still active.") from exc
        except (TypeError, ValueError, OSError) as exc:
            raise APError("Install I/O recovery owner cannot be verified.") from exc
        raise APError("Install I/O recovery owner is still active.")
    raise APError("Install I/O requires the active installer token.")


def _cmd_install_io_posix(args: argparse.Namespace, repo: Path) -> None:
    operation = _text(args.operation).lower()
    if operation in {"switch", "recover"}:
        _safe_ensure_project_directory(repo, Path(".agents/skills"))
    if operation == "recover":
        _safe_ensure_project_directory(repo, Path("docs"))
    with contextlib.ExitStack() as stack:
        agents = stack.enter_context(_open_project_directory(repo, Path(".agents")))
        transaction = stack.enter_context(
            _open_project_directory(repo, _INSTALL_TRANSACTION_RELATIVE)
        )
        if not isinstance(agents, int) or not isinstance(transaction, int):
            raise APError("Install I/O project directories are missing.")
        bindings: list[tuple[Path, int, tuple[int, int]]] = [
            (Path(".agents"), agents, _directory_handle_identity(agents)),
            (_INSTALL_TRANSACTION_RELATIVE, transaction, _directory_handle_identity(transaction)),
        ]
        skills: int | None = None
        docs: int | None = None
        if operation in {"switch", "recover"}:
            skills = stack.enter_context(_open_project_directory(repo, Path(".agents/skills")))
            if not isinstance(skills, int):
                raise APError("Install I/O skills directory is missing.")
            bindings.append((Path(".agents/skills"), skills, _directory_handle_identity(skills)))
        if operation == "recover":
            docs = stack.enter_context(_open_project_directory(repo, Path("docs")))
            if not isinstance(docs, int):
                raise APError("Install I/O docs directory is missing.")
            bindings.append((Path("docs"), docs, _directory_handle_identity(docs)))

        _inject_install_io_parent_swap(repo, operation)
        for relative, handle, identity in bindings:
            _require_bound_project_directory(repo, relative, handle, identity)

        if operation == "switch":
            assert skills is not None
            _remove_tree_at(skills, "auto-coding-skill", missing_ok=True)
            os.rename(
                "new-skill",
                "auto-coding-skill",
                src_dir_fd=transaction,
                dst_dir_fd=skills,
            )
            _copy_file_between_fds(transaction, "new-manifest.json", agents, "managed-install.json")
        elif operation == "recover":
            assert skills is not None and docs is not None
            _remove_tree_at(skills, "auto-coding-skill", missing_ok=True)
            if args.old_skill_present:
                _copy_directory_at(transaction, "old-skill", skills, "auto-coding-skill")
            if args.old_manifest_present:
                _copy_file_between_fds(transaction, "old-manifest.json", agents, "managed-install.json")
            else:
                _unlink_file_at(agents, "managed-install.json", missing_ok=True)
            if args.old_engineering_present:
                _copy_file_between_fds(transaction, "old-ENGINEERING.md", docs, "ENGINEERING.md")
            else:
                _unlink_file_at(docs, "ENGINEERING.md", missing_ok=True)
        elif operation == "complete":
            completed = f".auto-coding-skill-install-completed-{os.getpid()}-{uuid.uuid4().hex}"
            os.rename(
                _INSTALL_TRANSACTION_RELATIVE.name,
                completed,
                src_dir_fd=agents,
                dst_dir_fd=agents,
            )
            _remove_tree_at(agents, completed)
        else:
            raise APError(f"Unsupported install I/O operation: {operation}")


def _cmd_install_io_windows(args: argparse.Namespace, repo: Path) -> None:
    operation = _text(args.operation).lower()
    if operation in {"switch", "recover"}:
        _safe_ensure_project_directory(repo, Path(".agents/skills"))
    if operation == "recover":
        _safe_ensure_project_directory(repo, Path("docs"))
    transaction = repo / _INSTALL_TRANSACTION_RELATIVE
    skills = repo / ".agents" / "skills"
    agents = repo / ".agents"
    docs = repo / "docs"
    snapshots: list[tuple[Path, tuple[int, int]]] = []
    for directory in [agents, transaction, *([skills] if operation in {"switch", "recover"} else []), *([docs] if operation == "recover" else [])]:
        metadata = directory.lstat()
        if _is_windows_reparse_point(metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise APError(f"Install I/O project directory is unsafe: {directory.relative_to(repo)}")
        snapshots.append((directory, _project_path_identity(metadata)))
    _inject_install_io_parent_swap(repo, operation)

    def validate() -> None:
        for directory, identity in snapshots:
            metadata = directory.lstat()
            if (
                _is_windows_reparse_point(metadata)
                or not stat.S_ISDIR(metadata.st_mode)
                or _project_path_identity(metadata) != identity
            ):
                raise APError(f"Install I/O project parent changed: {directory.relative_to(repo)}")

    validate()
    if operation == "switch":
        target = skills / "auto-coding-skill"
        if os.path.lexists(target):
            shutil.rmtree(target)
        os.replace(transaction / "new-skill", target)
        _safe_write_project_file(repo, Path(".agents/managed-install.json"), (transaction / "new-manifest.json").read_bytes())
    elif operation == "recover":
        target = skills / "auto-coding-skill"
        if os.path.lexists(target):
            shutil.rmtree(target)
        if args.old_skill_present:
            shutil.copytree(transaction / "old-skill", target, symlinks=True)
        if args.old_manifest_present:
            _safe_write_project_file(repo, Path(".agents/managed-install.json"), (transaction / "old-manifest.json").read_bytes())
        elif os.path.lexists(agents / "managed-install.json"):
            (agents / "managed-install.json").unlink()
        if args.old_engineering_present:
            _safe_write_project_file(repo, Path("docs/ENGINEERING.md"), (transaction / "old-ENGINEERING.md").read_bytes())
        elif os.path.lexists(docs / "ENGINEERING.md"):
            (docs / "ENGINEERING.md").unlink()
    elif operation == "complete":
        completed = agents / f".auto-coding-skill-install-completed-{os.getpid()}-{uuid.uuid4().hex}"
        os.replace(transaction, completed)
        shutil.rmtree(completed)
    else:
        raise APError(f"Unsupported install I/O operation: {operation}")
    validate()


def cmd_install_io(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    operation = _text(args.operation).lower()
    _require_install_io_access(repo, operation)
    if os.name == "nt":
        _cmd_install_io_windows(args, repo)
    else:
        _cmd_install_io_posix(args, repo)
    if args.json:
        print(json.dumps({"operation": operation, "ok": True}))


def _managed_scaffold_convergence(
    repo: Path,
    selected: dict[str, str],
    version: str,
    *,
    write: bool,
) -> list[dict]:
    actions: list[dict] = []
    for rel, canonical in sorted(selected.items()):
        if rel not in MANAGED_FRAMEWORK_DOCS:
            continue
        current = _safe_read_project_file(repo, rel)
        expected = canonical.encode("utf-8")
        if current == expected:
            continue
        if current is not None:
            archive_rel, archive_required = _select_project_archive_target(
                repo,
                Path(".agents") / "archive" / "auto-coding-skill" / version / rel,
                current,
                legacy_digest_payload=current,
            )
            if archive_required:
                actions.append({"action": "archive", "path": archive_rel.as_posix()})
                if write:
                    _safe_create_project_file(repo, archive_rel, current)
        actions.append({"action": "create" if current is None else "replace", "path": rel})
        if write:
            _safe_write_project_file(repo, rel, expected)
    return actions


def _is_allowed_project_doc(rel: Path, candidate: Path | None = None) -> bool:
    if rel == _PROJECT_CONFIG_RELATIVE:
        return candidate is None or (candidate.is_file() and not candidate.is_symlink())
    if any(rel.match(pattern) for pattern in PROJECT_FEEDBACK_PATTERNS):
        return candidate is None or (candidate.is_file() and not candidate.is_symlink())
    return any(rel == root or root in rel.parents for root in _PROJECT_ARTIFACT_ROOTS)


def cmd_project_converge(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    template = _skill_root() / "data" / "templates" / "ENGINEERING.md"
    engineering = repo / "docs" / "ENGINEERING.md"
    config_plan = _project_config_convergence_plan(repo, template)
    output = config_plan["engineering_output"]
    current = config_plan["engineering_current"]
    changed = current != output
    actions: list[dict] = []
    version = _text(_mapping(_read_frontmatter_markdown(template)[0].get("workflow")).get("skill_version")) or "current"
    managed_templates = templates_for("all")
    managed_plan = _managed_scaffold_convergence(repo, managed_templates, version, write=False)

    def archive_previous(source_path: Path, content: str, label: str) -> None:
        archive = (
            Path(".agents") / "archive" / "auto-coding-skill" / version
            / source_path.relative_to(repo)
        )
        content_bytes = content.encode("utf-8")
        archive, archive_required = _select_project_archive_target(
            repo,
            archive,
            content_bytes,
            legacy_digest_payload=content_bytes,
        )
        if not archive_required:
            return
        actions.append({"action": "archive", "path": archive.as_posix(), "detail": label})
        if args.write:
            _safe_create_project_file(repo, archive, content_bytes)

    def archive_extra(source_path: Path, label: str) -> None:
        source_rel = source_path.relative_to(repo)
        content = _safe_read_project_file(repo, source_rel)
        if content is None:
            raise APError(f"Project file disappeared during convergence: {source_rel.as_posix()}")
        archive, archive_required = _select_project_archive_target(
            repo,
            Path(".agents") / "archive" / "auto-coding-skill" / version / source_rel,
            content,
            legacy_digest_payload=content,
        )
        if archive_required:
            actions.append({"action": "archive", "path": archive.as_posix(), "detail": label})
            if args.write:
                _safe_create_project_file(repo, archive, content)

    if changed and current:
        archive_header = (
            f"# Archived ENGINEERING.md before auto-coding-skill {version}\n\n"
            "Historical and non-authoritative. Do not use this file as workflow policy.\n\n---\n\n"
        )
        archive_previous(engineering, archive_header + current, "previous project configuration")
    if config_plan["overlay_output"] is not None:
        actions.append({
            "action": "create",
            "path": _PROJECT_CONFIG_RELATIVE.as_posix(),
            "detail": (
                "project-owned effective-config overlay; migrated "
                f"{len(config_plan['migrated_paths'])} value paths"
            ),
        })
        if args.write:
            _safe_create_project_file(
                repo,
                _PROJECT_CONFIG_RELATIVE,
                config_plan["overlay_output"],
            )
    if changed:
        actions.append({
            "action": "create" if not current else "replace",
            "path": "docs/ENGINEERING.md",
        })
        if args.write:
            _safe_write_project_file(repo, Path("docs/ENGINEERING.md"), output.encode("utf-8"))

    for rel, canonical in sorted(templates_for("all").items()):
        if rel in MANAGED_FRAMEWORK_DOCS:
            continue
        target = repo / rel
        existing_payload = _safe_read_project_file(repo, rel)
        try:
            existing = existing_payload.decode("utf-8") if existing_payload is not None else ""
        except UnicodeDecodeError as exc:
            raise APError(f"Project documentation must be UTF-8: {rel}") from exc
        managed = rel in MANAGED_FRAMEWORK_DOCS
        if existing and (not managed or existing == canonical):
            continue
        if existing:
            archive_previous(target, existing, "previous managed documentation template")
        actions.append({"action": "create" if not existing else "replace", "path": rel})
        if args.write:
            _safe_write_project_file(repo, rel, canonical.encode("utf-8"))

    actions.extend(
        _managed_scaffold_convergence(repo, managed_templates, version, write=True)
        if args.write
        else managed_plan
    )

    allowed_docs = {
        Path("docs/ENGINEERING.md"),
        Path("docs/tools/autopipeline/ap.py"),
        _PROJECT_CONFIG_RELATIVE,
        *(Path(rel) for rel in templates_for("all")),
    }
    docs_root = repo / "docs"
    if docs_root.exists():
        for candidate in sorted(docs_root.rglob("*")):
            try:
                candidate_metadata = candidate.lstat()
            except OSError as exc:
                raise APError("Cannot inspect active project documentation safely") from exc
            if stat.S_ISDIR(candidate_metadata.st_mode) and not _is_windows_reparse_point(candidate_metadata):
                continue
            rel = candidate.relative_to(repo)
            if _is_windows_reparse_point(candidate_metadata) or not stat.S_ISREG(candidate_metadata.st_mode):
                raise APError(
                    "Active project documentation must contain only real directories and "
                    f"regular non-symlink files: {rel.as_posix()}"
                )
            if rel in allowed_docs or _is_allowed_project_doc(rel, candidate):
                continue
            archive_extra(candidate, "removed from the exact docs framework")
            actions.append({"action": "delete", "path": rel.as_posix()})
            if args.write:
                candidate.unlink()
        if args.write:
            for directory in sorted(
                (item for item in docs_root.rglob("*") if item.is_dir()),
                key=lambda item: len(item.parts),
                reverse=True,
            ):
                try:
                    directory.rmdir()
                except OSError:
                    pass

    result = {"changed": bool(actions), "mode": "write" if args.write else "plan", "actions": actions}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    for action in actions:
        print(f"[project-converge] {action['action']}: {action['path']}")
    if not actions:
        print("[project-converge] OK: already current")


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
        current = _safe_read_project_file(repo, rel)
        if current is not None and not force:
            actions.append({"path": rel, "action": "exists"})
            continue
        action = "write" if write else "would-write"
        actions.append({"path": rel, "action": action})
        if write:
            _safe_write_project_file(repo, rel, content.encode("utf-8"))

    result = {"group": group, "mode": "write" if write else "plan", "actions": actions}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    for item in actions:
        print(f"[scaffold] {item['action']}: {item['path']}")
    if not write:
        print("[scaffold] plan only; re-run with --write to create missing files")


def cmd_managed_scaffold_converge(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    group = str(args.group or "").strip().lower()
    selected = templates_for(group)
    write = bool(args.write)
    template = _skill_root() / "data" / "templates" / "ENGINEERING.md"
    version = _text(_mapping(_read_frontmatter_markdown(template)[0].get("workflow")).get("skill_version")) or "current"
    actions = _managed_scaffold_convergence(repo, selected, version, write=write)
    result = {"group": group, "mode": "write" if write else "plan", "actions": actions}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    for item in actions:
        print(f"[managed-scaffold-converge] {item['action']}: {item['path']}")


_CONFIG_STATUS_FIELDS: tuple[tuple[str, tuple[str, ...], bool, bool], ...] = (
    ("workflow.skill_version", ("workflow", "skill_version"), False, True),
    ("workflow.mode", ("workflow", "mode"), False, True),
    ("workflow.profile", ("workflow", "profile"), False, True),
    ("workflow.completion", ("workflow", "completion"), False, True),
    ("project.name", ("project", "name"), False, True),
    ("concurrency.isolation", ("concurrency", "isolation"), False, True),
    ("concurrency.base_ref", ("concurrency", "base_ref"), False, True),
    ("concurrency.target_branch", ("concurrency", "target_branch"), False, True),
    ("concurrency.branch_prefix", ("concurrency", "branch_prefix"), False, True),
    ("concurrency.worktree_root", ("concurrency", "worktree_root"), False, True),
    ("concurrency.cleanup_merged", ("concurrency", "cleanup_merged"), False, True),
    ("concurrency.delete_remote_branch", ("concurrency", "delete_remote_branch"), False, True),
    ("concurrency.disposable_ignored", ("concurrency", "disposable_ignored"), True, False),
    ("validation.on_unmapped", ("validation", "on_unmapped"), False, True),
    ("validation.max_command_seconds", ("validation", "max_command_seconds"), False, True),
    ("validation.max_total_seconds", ("validation", "max_total_seconds"), False, True),
    ("validation.routes", ("validation", "routes"), True, False),
    ("risk.rules", ("risk", "rules"), True, False),
    ("docs.framework", ("docs", "framework"), False, True),
    ("access.project.frontend.url", ("access", "project", "frontend", "url"), False, False),
    ("access.project.frontend.username", ("access", "project", "frontend", "username"), False, False),
    ("access.project.frontend.password", ("access", "project", "frontend", "password"), False, False),
    ("access.project.backend.url", ("access", "project", "backend", "url"), False, False),
    ("access.project.backend.username", ("access", "project", "backend", "username"), False, False),
    ("access.project.backend.password", ("access", "project", "backend", "password"), False, False),
    ("access.jenkins.frontend.url", ("access", "jenkins", "frontend", "url"), False, False),
    ("access.jenkins.frontend.username", ("access", "jenkins", "frontend", "username"), False, False),
    ("access.jenkins.frontend.password", ("access", "jenkins", "frontend", "password"), False, False),
    ("access.jenkins.backend.url", ("access", "jenkins", "backend", "url"), False, False),
    ("access.jenkins.backend.username", ("access", "jenkins", "backend", "username"), False, False),
    ("access.jenkins.backend.password", ("access", "jenkins", "backend", "password"), False, False),
    ("access.gitlab.url", ("access", "gitlab", "url"), False, False),
    ("access.gitlab.username", ("access", "gitlab", "username"), False, False),
    ("access.gitlab.password", ("access", "gitlab", "password"), False, False),
    ("access.nexus.frontend.url", ("access", "nexus", "frontend", "url"), False, False),
    ("access.nexus.frontend.username", ("access", "nexus", "frontend", "username"), False, False),
    ("access.nexus.frontend.password", ("access", "nexus", "frontend", "password"), False, False),
)


def _config_value(cfg: dict, path: tuple[str, ...]) -> tuple[bool, object]:
    current: object = cfg
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return False, ""
        current = current[key]
    return True, current


def _config_status_report(repo: Path) -> dict:
    cfg = load_effective_config(repo)
    fields: dict[str, dict] = {}
    for label, path, sequence, expose_value in _CONFIG_STATUS_FIELDS:
        present, value = _config_value(cfg, path)
        if label.startswith("access.") or label in {"project.name", "docs.framework"}:
            configured = isinstance(value, str) and _is_explicit_fill(value)
        elif sequence:
            configured = isinstance(value, list) and bool(value)
        else:
            configured = bool(present and (
                len(value) > 0 if isinstance(value, (list, dict, str)) else value is not None
            ))
        state = {
            "present": present,
            "configured": bool(present and configured),
        }
        if sequence:
            state["item_count"] = len(value) if isinstance(value, list) else -1
        if expose_value and present and isinstance(value, (str, bool, int, float)):
            state["value"] = value
        fields[label] = state
    commands = _mapping(cfg.get("commands"))
    overlay_payload = _safe_read_project_file(
        repo,
        _PROJECT_CONFIG_RELATIVE,
        max_bytes=128 * 1024,
    )
    contract = cmd_doctor(
        argparse.Namespace(repo=str(repo), collect=True, quiet=True, record=False)
    )
    report = {
        "schema": "auto-coding-skill/effective-config-status/v1",
        "managed_version": _text(_mapping(cfg.get("workflow")).get("skill_version")),
        "project_overlay": {
            "path": _PROJECT_CONFIG_RELATIVE.as_posix(),
            "present": overlay_payload is not None,
            "schema": PROJECT_CONFIG_SCHEMA if overlay_payload is not None else "",
        },
        "project": {"name": _text(_mapping(cfg.get("project")).get("name"))},
        "fields": fields,
        "commands": {
            "configured_names": sorted(
                str(name)
                for name, value in commands.items()
                if isinstance(name, str) and isinstance(value, str) and value.strip()
            )
        },
        "risk_rule_count": len(_mapping(cfg.get("risk")).get("rules") or [])
        if isinstance(_mapping(cfg.get("risk")).get("rules") or [], list)
        else -1,
        "validation_route_count": len(_mapping(cfg.get("validation")).get("routes") or [])
        if isinstance(_mapping(cfg.get("validation")).get("routes") or [], list)
        else -1,
        "policy_issues": _workflow_policy_issues(repo, cfg),
        "contract_valid": not bool(contract["issues"]),
        "contract_issues": contract["issues"],
        "contract_advisories": contract["advisories"],
    }
    canonical = json.dumps(report, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    report["redacted_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return report


def cmd_config_effective(args: argparse.Namespace) -> None:
    report = _config_status_report(Path(args.repo).resolve())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print(f"[config] managed_version={report['managed_version'] or '(missing)'}")
    print(
        "[config] project_overlay="
        + ("valid" if report["project_overlay"]["present"] else "missing")
    )
    print(f"[config] project={report['project']['name'] or '(missing)'}")
    print(f"[config] contract_valid={str(report['contract_valid']).lower()}")
    print(f"[config] redacted_sha256={report['redacted_sha256']}")


def cmd_install(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    templates = _skill_root() / "data" / "templates"
    config_convergence = _project_config_convergence_plan(
        repo,
        templates / "ENGINEERING.md",
    )

    planned_copies: list[tuple[Path, Path]] = []
    for rel in _CORE_DOC_TEMPLATES:
        planned_copies.append((templates / "docs" / rel, repo / "docs" / rel))

    if args.bridges:
        planned_copies.append((templates / "bridges" / "AGENTS.md", repo / "AGENTS.md"))

    tools_dir = repo / "docs" / "tools" / "autopipeline"
    planned_copies.append((templates / "tools" / "ap.py", tools_dir / "ap.py"))

    engineering = repo / "docs" / "ENGINEERING.md"
    conflicts: list[Path] = [engineering] if config_convergence["engineering_current"] else []
    planned_files: list[tuple[Path, Path]] = []
    for src, dst in planned_copies:
        if src.is_file():
            planned_files.append((src, dst))
            continue
        for source_file in _iter_files(src):
            planned_files.append((source_file, dst / source_file.relative_to(src)))
    for _, dst in planned_files:
        if _safe_read_project_file(repo, dst.relative_to(repo)) is not None:
            conflicts.append(dst)
    if conflicts and not args.force:
        conflict_list = "\n".join(f"- {_repo_rel(repo, path)}" for path in conflicts[:20])
        extra = "" if len(conflicts) <= 20 else f"\n- ... and {len(conflicts) - 20} more"
        raise APError(
            "Install would overwrite existing files:\n"
            f"{conflict_list}{extra}\n"
            "For existing projects, run `autocoding init` or an explicit `autocoding sync`. "
            "Use `install --force` only when intentionally resetting generated docs/tooling."
        )

    for src, dst in planned_files:
        _safe_write_project_file(repo, dst.relative_to(repo), src.read_bytes())

    if config_convergence["overlay_output"] is not None:
        _safe_create_project_file(
            repo,
            _PROJECT_CONFIG_RELATIVE,
            config_convergence["overlay_output"],
        )
    _safe_write_project_file(
        repo,
        Path("docs/ENGINEERING.md"),
        config_convergence["engineering_output"].encode("utf-8"),
    )
    cmd_scaffold(
        argparse.Namespace(repo=str(repo), group="feedback", write=True, force=args.force, json=False)
    )
    if args.full:
        cmd_scaffold(
            argparse.Namespace(repo=str(repo), group="all", write=True, force=args.force, json=False)
        )

    layout = "full" if args.full else "minimal"
    print(f"[install] OK: {layout} scaffold installed into {repo}")
    print(
        "[install] Next: fill every access.* URL, username, and password in "
        "docs/project/auto-coding-skill.yaml, run doctor, and commit that file into Git."
    )


def cmd_upgrade(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    write = bool(args.write) and not bool(args.dry_run)
    if write:
        raise APError(
            "Project-local `ap.py upgrade --write` was retired in favor of the "
            "transactional installer. Run `autocoding init` for one project or "
            "`autocoding sync --projects <path[,path...]>` for explicit projects. "
            "Use `ap.py upgrade --dry-run` only as a read-only legacy diagnostic."
        )
    source_root = _find_skill_asset_root(repo)
    templates = source_root / "data" / "templates"
    template_engineering = templates / "ENGINEERING.md"
    template_agents = templates / "bridges" / "AGENTS.md"
    actions: list[dict] = []
    managed_version = _text(
        _mapping(_read_frontmatter_markdown(template_engineering)[0].get("workflow")).get("skill_version")
    ) or "current"
    feedback_templates = templates_for("feedback")
    feedback_plan = _managed_scaffold_convergence(
        repo, feedback_templates, managed_version, write=False
    )

    registry = _task_state_root(repo) / "tasks"
    active_manifests = sorted(registry.glob("*.json")) if registry.exists() else []
    if active_manifests:
        names = ", ".join(path.name for path in active_manifests)
        raise APError(
            "Upgrade refused because registered tasks are still active: "
            f"{names}. Finish, integrate, or clean them with the installed runtime first; "
            "workflow semantics must not change mid-task."
        )

    config_convergence = _project_config_convergence_plan(repo, template_engineering)

    def add_action(kind: str, path: Path, action: str, detail: str = "") -> None:
        actions.append({
            "kind": kind,
            "path": _repo_rel(repo, path),
            "action": action,
            "detail": detail,
        })

    # Complete policy discovery before the first write. Known official fragments
    # are safe migration inputs; every remaining match is project-owned and must
    # be handled explicitly instead of being overwritten by a partial upgrade.
    workflow_plans = _workflow_policy_plans(repo)
    # Root AGENTS.md is a whole-file managed bridge in 4.1. Unknown legacy text
    # is archived and replaced, so only ENGINEERING policy conflicts block the
    # upgrade preflight.
    workflow_issues = [
        issue
        for plan in workflow_plans
        if plan["path"] == "docs/ENGINEERING.md"
        for issue in plan["issues"]
    ]
    if workflow_issues:
        raise APError(
            "Upgrade preflight found unknown workflow policy conflicts; no files were written:\n- "
            + "\n- ".join(workflow_issues)
        )
    workflow_plan_by_path = {plan["path"]: plan for plan in workflow_plans}
    engineering_plan = workflow_plan_by_path["docs/ENGINEERING.md"]
    if engineering_plan.get("official_body_hash") and template_engineering.exists():
        current = engineering_plan["original"]
        frontmatter = _frontmatter_span(current, "docs/ENGINEERING.md")
        _, template_body = _read_frontmatter_markdown(template_engineering)
        body_start = frontmatter[1] if frontmatter else 0
        engineering_plan["output"] = current[:body_start] + template_body

    section_migrations = [
        item
        for item in engineering_plan.get("migrations") or []
        if _text(item.get("id")).startswith("engineering-section-")
    ]
    if section_migrations and engineering_plan.get("original"):
        version_match = re.search(
            r"auto-coding-skill:managed-workflow:start\s+version=([0-9]+\.[0-9]+\.[0-9]+)",
            template_engineering.read_text(encoding="utf-8"),
        )
        version = version_match.group(1) if version_match else "current"
        archive_header = (
            f"# Archived ENGINEERING.md before auto-coding-skill {version} docs convergence\n\n"
            "This file is historical and non-authoritative. Known duplicate workflow sections\n"
            "were removed from docs/ENGINEERING.md. Move still-current configuration into\n"
            "docs/project/auto-coding-skill.yaml and durable facts into docs/project/.\n\n---\n\n"
        )
        archive_content = archive_header + engineering_plan["original"]
        archive_rel, archive_required = _select_project_archive_target(
            repo,
            Path(".agents/archive/auto-coding-skill") / version / "workflow/ENGINEERING.md",
            archive_content.encode("utf-8"),
            legacy_digest_payload=engineering_plan["original"].encode("utf-8"),
        )
        archive = repo / archive_rel
        if archive_required:
            add_action("policy", archive, "archive", "before duplicate workflow section cleanup")
            if write:
                _safe_create_project_file(repo, archive_rel, archive_content.encode("utf-8"))

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
                add_action("skill", dst, "delete", "stale file in fully managed Skill copy")
                if write:
                    dst.unlink()
    else:
        add_action("skill", project_skill, "create", "install runtime required by the project launcher")
        if write:
            copy_tree(source_root, project_skill)

    agents_path = repo / "AGENTS.md"
    canonical_agents = template_agents.read_text(encoding="utf-8") if template_agents.exists() else ""
    current_agents = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
    if canonical_agents and current_agents != canonical_agents:
        agents_version_match = re.search(
            r"auto-coding-skill:managed-agents:start\s+version=([0-9]+\.[0-9]+\.[0-9]+)",
            canonical_agents,
        )
        agents_version = agents_version_match.group(1) if agents_version_match else "current"
        if current_agents:
            archive_header = (
                f"# Archived AGENTS.md before auto-coding-skill {agents_version}\n\n"
                "This file is historical and non-authoritative. The root AGENTS.md is fully managed.\n"
                "Move project configuration into docs/project/auto-coding-skill.yaml and facts into docs/project/,\n"
                "without copying workflow rules back into the root AGENTS.md.\n\n---\n\n"
            )
            archive_content = archive_header + current_agents
            archive_rel, archive_required = _select_project_archive_target(
                repo,
                Path(".agents/archive/auto-coding-skill") / agents_version / "AGENTS.md",
                archive_content.encode("utf-8"),
                legacy_digest_payload=current_agents.encode("utf-8"),
            )
            archive = repo / archive_rel
            if archive_required:
                add_action("policy", archive, "archive", "historical and non-authoritative")
                if write:
                    _safe_create_project_file(repo, archive_rel, archive_content.encode("utf-8"))
        add_action("policy", agents_path, "replace", "fully managed canonical AGENTS.md")
        if write:
            agents_path.write_text(canonical_agents, encoding="utf-8")

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

    feedback_actions = (
        _managed_scaffold_convergence(repo, feedback_templates, managed_version, write=True)
        if write
        else feedback_plan
    )
    for item in feedback_actions:
        actions.append({
            "kind": "doc",
            "path": item["path"],
            "action": item["action"],
            "detail": "managed Skill feedback template",
        })

    engineering = repo / "docs" / "ENGINEERING.md"
    if config_convergence["overlay_output"] is not None:
        add_action(
            "config",
            repo / _PROJECT_CONFIG_RELATIVE,
            "create",
            f"migrate {len(config_convergence['migrated_paths'])} project-owned value paths",
        )
        if write:
            _safe_create_project_file(
                repo,
                _PROJECT_CONFIG_RELATIVE,
                config_convergence["overlay_output"],
            )
    engineering_output = config_convergence["engineering_output"]
    engineering_current = config_convergence["engineering_current"]
    if engineering_current != engineering_output:
        add_action(
            "config",
            engineering,
            "create" if not engineering_current else "replace",
            "managed default configuration",
        )
        if write:
            _safe_write_project_file(repo, Path("docs/ENGINEERING.md"), engineering_output.encode("utf-8"))
    else:
        add_action("config", engineering, "ok")

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
    _require_no_install_transaction(repo)
    return load_effective_config(repo)


def _require_no_install_transaction(repo: Path, *, allow_installer: bool = False) -> None:
    transaction = repo / _INSTALL_TRANSACTION_RELATIVE
    if not os.path.lexists(transaction):
        return
    if allow_installer:
        _require_active_install_transaction(repo)
        return
    raise APError(
        "An interrupted auto-coding-skill install transaction requires recovery. "
        "Run autocoding init or a single-project autocoding sync before using or modifying the project runtime."
    )


def _require_active_install_transaction(repo: Path) -> dict:
    transaction = repo / _INSTALL_TRANSACTION_RELATIVE
    if not os.path.lexists(transaction):
        raise APError("Internal project mutation requires an active install transaction.")
    token = os.environ.get("AUTOCODING_INSTALL_TRANSACTION_TOKEN", "")
    if not re.fullmatch(r"[0-9a-f]{64}", token):
        raise APError("Internal project mutation requires the active installer token.")
    owner_payload = _safe_read_project_file(
        repo,
        _INSTALL_TRANSACTION_RELATIVE / "owner.json",
        max_bytes=4096,
    )
    state_payload = _safe_read_project_file(
        repo,
        _INSTALL_TRANSACTION_RELATIVE / "state.json",
        max_bytes=64 * 1024,
    )
    if owner_payload is None or state_payload is None:
        raise APError("Internal project mutation requires a complete active install transaction.")
    try:
        owner = json.loads(owner_payload.decode("utf-8"))
        state = json.loads(state_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise APError("Active install transaction metadata is invalid.") from exc
    actual = hashlib.sha256(token.encode("ascii")).hexdigest()
    owner_hash = _text(_mapping(owner).get("token_sha256"))
    state_owner_hash = _text(_mapping(state).get("owner_token_sha256"))
    internal_hash = _text(_mapping(state).get("internal_token_sha256"))
    if not all(
        re.fullmatch(r"[0-9a-f]{64}", value)
        and hmac.compare_digest(value, actual)
        for value in (owner_hash, state_owner_hash, internal_hash)
    ):
        raise APError("Internal project mutation token does not match the active transaction.")
    return _mapping(state)


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


def _load_workflow_migration_policy(repo: Path) -> dict:
    policy_path = _find_skill_asset_root(repo) / _WORKFLOW_MIGRATION_POLICY
    if policy_path.exists():
        try:
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise APError(f"Invalid workflow migration policy: {policy_path}: {exc}") from exc
    else:
        # Keep installed runtimes fail-closed during a rolling package update. The
        # packaged policy is authoritative once present; this fallback intentionally
        # knows no removable fragments, so only an explicit policy can auto-migrate.
        policy = json.loads(json.dumps(_FALLBACK_WORKFLOW_MIGRATION_POLICY))

    if not isinstance(policy, dict) or policy.get("schema_version") != 1:
        raise APError(f"Unsupported workflow migration policy schema: {policy_path}")
    for field in [
        "known_official_engineering_body_sha256",
        "known_official_fragments",
        "conflict_rules",
    ]:
        if not isinstance(policy.get(field), list):
            raise APError(f"Workflow migration policy field must be a list: {field}")
    for index, fragment in enumerate(policy["known_official_fragments"]):
        if not isinstance(fragment, dict):
            raise APError(f"Workflow migration policy fragment[{index}] must be an object")
        if fragment.get("match") not in {"exact-line", "exact-block", "heading-section"}:
            raise APError(f"Workflow migration policy fragment[{index}] has invalid match mode")
        if not _text(fragment.get("id")) or not isinstance(fragment.get("paths"), list):
            raise APError(f"Workflow migration policy fragment[{index}] is incomplete")
        if not isinstance(fragment.get("text"), str) or not fragment["text"].strip():
            raise APError(f"Workflow migration policy fragment[{index}] has empty text")
        if "replacement" in fragment and not isinstance(fragment.get("replacement"), str):
            raise APError(f"Workflow migration policy fragment[{index}] replacement must be text")
    for index, rule in enumerate(policy["conflict_rules"]):
        if not isinstance(rule, dict):
            raise APError(f"Workflow migration policy conflict_rules[{index}] must be an object")
        flags = _text(rule.get("flags"))
        if set(flags) - {"i", "m"}:
            raise APError(f"Workflow migration policy conflict_rules[{index}] has invalid flags")
        if not _text(rule.get("id")) or not isinstance(rule.get("paths"), list):
            raise APError(f"Workflow migration policy conflict_rules[{index}] is incomplete")
        try:
            re.compile(_text(rule.get("pattern")), _workflow_regex_flags(flags))
        except re.error as exc:
            raise APError(
                f"Workflow migration policy conflict_rules[{index}] has invalid regex: {exc}"
            ) from exc
    return policy


def _workflow_regex_flags(raw: str) -> int:
    flags = 0
    if "i" in raw:
        flags |= re.IGNORECASE
    if "m" in raw:
        flags |= re.MULTILINE
    return flags


def _blank_text_span(text: str, start: int, end: int) -> str:
    return text[:start] + "".join("\n" if char == "\n" else " " for char in text[start:end]) + text[end:]


def _merge_text_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _managed_document_span(text: str, kind: str, rel: str) -> Optional[tuple[int, int]]:
    token = f"auto-coding-skill:managed-{kind}"
    raw_starts = text.count(f"{token}:start")
    raw_ends = text.count(f"{token}:end")
    if raw_starts == 0 and raw_ends == 0:
        return None
    start_re = re.compile(
        rf"<!--\s*{re.escape(token)}:start(?:\s+version=[0-9]+\.[0-9]+\.[0-9]+)?\s*-->"
    )
    end_re = re.compile(rf"<!--\s*{re.escape(token)}:end\s*-->")
    starts = list(start_re.finditer(text))
    ends = list(end_re.finditer(text))
    if raw_starts != 1 or raw_ends != 1 or len(starts) != 1 or len(ends) != 1:
        raise APError(f"Malformed managed {kind} markers in {rel}")
    if starts[0].start() >= ends[0].start():
        raise APError(f"Out-of-order managed {kind} markers in {rel}")
    return starts[0].start(), ends[0].end()


def _sync_managed_workflow_text(current: str, template: str) -> str:
    """Install the canonical managed workflow while preserving project facts."""
    template_span = _managed_document_span(template, "workflow", "template ENGINEERING.md")
    if not template_span:
        raise APError("Packaged ENGINEERING template has no managed workflow block")
    block = template[template_span[0]:template_span[1]]
    current_span = _managed_document_span(current, "workflow", "docs/ENGINEERING.md")
    if current_span:
        return current[:current_span[0]] + block + current[current_span[1]:]

    frontmatter = _frontmatter_span(current, "docs/ENGINEERING.md")
    body_start = frontmatter[1] if frontmatter else 0
    body = current[body_start:]
    heading = re.search(r"^# Engineering Workflow[^\n]*(?:\n|$)", body, flags=re.MULTILINE)
    insertion = body_start + (heading.end() if heading else 0)
    before = current[:insertion]
    after = current[insertion:]
    if before and not before.endswith("\n"):
        before += "\n"
    if after and not after.startswith("\n"):
        after = "\n" + after
    return before + block + after


def _frontmatter_span(text: str, rel: str) -> Optional[tuple[int, int]]:
    if not text.startswith("---\n"):
        return None
    match = re.match(r"^---\n[\s\S]*?\n---(?:\n|$)", text)
    if not match:
        raise APError(f"Malformed Markdown frontmatter in {rel}")
    return 0, match.end()


def _known_fragment_spans(
    visible: str,
    rel: str,
    policy: dict,
) -> list[tuple[int, int, str, int, str, str]]:
    found: list[tuple[int, int, str, int, str, str]] = []
    for fragment in policy.get("known_official_fragments") or []:
        if rel not in fragment.get("paths", []):
            continue
        fragment_id = _text(fragment.get("id"))
        replacement = str(fragment.get("replacement") or "")
        match_mode = _text(fragment.get("match"))
        expected = str(fragment.get("text") or "").replace("\r\n", "\n")
        if fragment.get("match") == "heading-section":
            lines = visible.splitlines(keepends=True)
            offsets: list[int] = []
            cursor = 0
            for line in lines:
                offsets.append(cursor)
                cursor += len(line)
            for index, line in enumerate(lines):
                heading = re.match(r"^\s*(#{1,6})\s+(.+?)\s*#*\s*$", line.rstrip("\n"))
                if not heading or heading.group(2).strip() != expected.strip():
                    continue
                level = len(heading.group(1))
                end_index = index + 1
                while end_index < len(lines):
                    next_heading = re.match(r"^\s*(#{1,6})\s+", lines[end_index])
                    if next_heading and len(next_heading.group(1)) <= level:
                        break
                    end_index += 1
                end = offsets[end_index] if end_index < len(offsets) else len(visible)
                start = offsets[index]
                found.append((start, end, fragment_id, visible.count("\n", 0, start) + 1, replacement, match_mode))
            continue
        if fragment.get("match") == "exact-line":
            cursor = 0
            for line in visible.splitlines(keepends=True):
                content = line.rstrip("\n")
                if content.strip() == expected.strip():
                    found.append((cursor, cursor + len(line), fragment_id, visible.count("\n", 0, cursor) + 1, replacement, match_mode))
                cursor += len(line)
            continue
        cursor = 0
        while True:
            start = visible.find(expected, cursor)
            if start < 0:
                break
            end = start + len(expected)
            found.append((start, end, fragment_id, visible.count("\n", 0, start) + 1, replacement, match_mode))
            cursor = end
    section_spans = [
        (start, end)
        for start, end, _, _, _, match_mode in found
        if match_mode == "heading-section"
    ]
    return [
        item
        for item in found
        if item[5] == "heading-section"
        or not any(start <= item[0] and item[1] <= end for start, end in section_spans)
    ]


def _workflow_document_plan(repo: Path, rel: str, policy: dict) -> dict:
    path = repo / rel
    if not path.exists():
        return {"path": rel, "original": "", "output": "", "migrations": [], "issues": []}
    original = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    protected: list[tuple[int, int]] = []
    if rel == "docs/ENGINEERING.md":
        frontmatter = _frontmatter_span(original, rel)
        if frontmatter:
            protected.append(frontmatter)
        managed = _managed_document_span(original, "workflow", rel)
    else:
        managed = _managed_document_span(original, "agents", rel)
    if managed:
        protected.append(managed)

    visible = original
    for start, end in protected:
        visible = _blank_text_span(visible, start, end)

    official_body_hash = ""
    if rel == "docs/ENGINEERING.md" and managed is None:
        body_start = protected[0][1] if protected else 0
        body = original[body_start:]
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if digest in set(policy.get("known_official_engineering_body_sha256") or []):
            official_body_hash = digest
            visible = _blank_text_span(visible, body_start, len(visible))

    known = _known_fragment_spans(visible, rel, policy)
    known_spans = _merge_text_spans([(start, end) for start, end, _, _, _, _ in known])
    scan_text = visible
    for start, end in known_spans:
        scan_text = _blank_text_span(scan_text, start, end)

    issues: list[str] = []
    candidates = _workflow_scan_candidates(scan_text)
    seen_issues: set[tuple[str, int]] = set()
    for rule in policy.get("conflict_rules") or []:
        if rel not in rule.get("paths", []):
            continue
        regex = re.compile(_text(rule.get("pattern")), _workflow_regex_flags(_text(rule.get("flags"))))
        for candidate, line in candidates:
            match = regex.search(candidate)
            if not match or (_text(rule.get("id")), line) in seen_issues:
                continue
            seen_issues.add((_text(rule.get("id")), line))
            message = _text(rule.get("message")) or "conflicts with the fast development workflow"
            issues.append(f"{rel}:{line} [{_text(rule.get('id'))}] {message}")

    output = original
    for start, end, _, _, replacement, match_mode in sorted(known, reverse=True):
        if replacement and match_mode == "exact-line" and output[start:end].endswith("\n"):
            replacement = replacement + "\n"
        output = output[:start] + replacement + output[end:]
    migrations = [
        {"id": fragment_id, "line": line}
        for _, _, fragment_id, line, _, _ in known
    ]
    if official_body_hash:
        migrations.append({"id": f"official-body:{official_body_hash}", "line": 1})
    return {
        "path": rel,
        "original": original,
        "output": output,
        "migrations": migrations,
        "issues": issues,
        "official_body_hash": official_body_hash,
    }


def _workflow_policy_plans(repo: Path, policy: Optional[dict] = None) -> list[dict]:
    effective = policy or _load_workflow_migration_policy(repo)
    return [
        _workflow_document_plan(repo, "AGENTS.md", effective),
        _workflow_document_plan(repo, "docs/ENGINEERING.md", effective),
    ]


def _workflow_scan_candidates(text: str) -> list[tuple[str, int]]:
    lines = text.split("\n")
    candidates: list[tuple[str, int]] = [(line, index + 1) for index, line in enumerate(lines)]
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if re.match(r"^\s*(?:[-+*]|\d+\.)\s+", line):
            end = index + 1
            while end < len(lines) and re.match(r"^\s{2,}\S", lines[end]) and not re.match(
                r"^\s*(?:[-+*]|\d+\.)\s+", lines[end]
            ):
                end += 1
            if end > index + 1:
                candidates.append((" ".join(lines[index:end]), index + 1))
            continue
        if re.match(r"^\s*(?:#|\||```|~~~)", line):
            continue
        end = index + 1
        while end < len(lines) and lines[end].strip() and not re.match(
            r"^\s*(?:#|\||```|~~~|[-+*]|\d+\.)\s*", lines[end]
        ):
            end += 1
        if end > index + 1:
            candidates.append((" ".join(lines[index:end]), index + 1))
    return candidates


def _legacy_gate_config_issues(cfg: dict) -> list[str]:
    issues: list[str] = []
    gate_cfg = cfg.get("gate") or {}
    if not isinstance(gate_cfg, dict):
        return ["effective configuration gate must be a mapping"]
    if "full_on" in gate_cfg:
        issues.append("effective configuration gate.full_on is legacy automatic full escalation; run autocoding init")
    if _bool_config(gate_cfg.get("full_on_unknown"), False):
        issues.append("effective configuration gate.full_on_unknown=true is legacy automatic full escalation; run autocoding init")
    rules = gate_cfg.get("rules") or []
    if isinstance(rules, list):
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                continue
            for key in ["scope", "commands"]:
                if key in rule:
                    issues.append(
                        f"effective configuration gate.rules[{index}].{key} is legacy automatic gate escalation; run autocoding init"
                    )
    return issues


def _workflow_policy_issues(repo: Path, cfg: Optional[dict] = None) -> list[str]:
    issues: list[str] = []
    for plan in _workflow_policy_plans(repo):
        issues.extend(plan["issues"])
        for migration in plan["migrations"]:
            issues.append(
                f"{plan['path']}:{migration['line']} [{migration['id']}] known legacy workflow rule; "
                "run `autocoding init` or an explicit `autocoding sync`"
            )
    issues.extend(_legacy_gate_config_issues(cfg if cfg is not None else _load_cfg(repo)))
    return issues


def _require_workflow_policy_clean(repo: Path, cfg: Optional[dict] = None) -> None:
    issues = _workflow_policy_issues(repo, cfg)
    if issues:
        raise APError("Workflow policy conflicts block normal development:\n- " + "\n- ".join(issues))


def _parse_frontmatter_markdown_text(text: str, path: Path) -> tuple[dict, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*(\n|$)(.*)$", text, flags=re.DOTALL)
    if not m:
        raise APError(f"Markdown frontmatter not found: {path}")
    data = require_yaml().safe_load(m.group(1)) or {}
    return data, m.group(3)


def _read_frontmatter_markdown(path: Path) -> tuple[dict, str]:
    if not path.exists():
        return {}, ""
    return _parse_frontmatter_markdown_text(path.read_text(encoding="utf-8"), path)


def _write_frontmatter_markdown(path: Path, data: dict, body: str) -> None:
    dumped = require_yaml().safe_dump(data, allow_unicode=True, sort_keys=False).strip()
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


def _feedback_error(path: Path, message: str) -> APError:
    return APError(f"Invalid Skill feedback report {path}: {message}")


def _feedback_scalar(data: dict, field: str, path: Path) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise _feedback_error(path, f"{field} must be a non-empty string")
    return value.strip()


def _feedback_timestamp(value: object, path: Path, field: str) -> str:
    if isinstance(value, _dt.datetime):
        return value.isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    if not isinstance(value, str) or not value.strip():
        raise _feedback_error(path, f"{field} must be an ISO-8601 date or timestamp")
    raw = value.strip()
    try:
        if "T" in raw or " " in raw:
            _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            _dt.date.fromisoformat(raw)
    except ValueError as exc:
        raise _feedback_error(path, f"{field} must be an ISO-8601 date or timestamp") from exc
    return raw


def _parse_feedback_report(payload: bytes, path: Path) -> dict:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _feedback_error(path, "file must be UTF-8") from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in text:
        raise _feedback_error(path, "file must be plain Markdown text")
    if any(pattern.search(text) for pattern in _FEEDBACK_SENSITIVE_PATTERNS):
        raise _feedback_error(path, "report contains sensitive or machine-specific evidence; redact it")
    match = re.match(r"^---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)(.*)$", text, flags=re.DOTALL)
    if not match:
        raise _feedback_error(path, "YAML frontmatter is required")
    try:
        data = require_yaml().safe_load(match.group(1))
    except Exception as exc:
        raise _feedback_error(path, "YAML frontmatter is not safe and valid") from exc
    if not isinstance(data, dict):
        raise _feedback_error(path, "YAML frontmatter must be a flat mapping")
    if any(not isinstance(key, str) for key in data):
        raise _feedback_error(path, "frontmatter field names must be strings")
    schema_value = _feedback_scalar(data, "schema", path)
    if schema_value not in _FEEDBACK_SCHEMAS:
        raise _feedback_error(path, "schema must be auto-coding-skill-feedback/v1 or /v2")
    expected_fields = _FEEDBACK_V2_FIELDS if schema_value.endswith("/v2") else _FEEDBACK_V1_FIELDS
    unknown = sorted(set(data) - set(expected_fields))
    missing = [field for field in expected_fields if field not in data]
    if unknown:
        raise _feedback_error(path, "unknown frontmatter fields are not allowed")
    if missing:
        raise _feedback_error(path, f"missing frontmatter fields: {', '.join(missing)}")
    if any(isinstance(value, (dict, list, tuple, set)) for value in data.values()):
        raise _feedback_error(path, "frontmatter values must be scalars")

    metadata: dict[str, str] = {}
    metadata["schema"] = schema_value
    report_id = _feedback_scalar(data, "report_id", path)
    if not _FEEDBACK_SAFE_ID_RE.fullmatch(report_id):
        raise _feedback_error(path, "report_id must be a safe identifier")
    metadata["report_id"] = report_id
    status_value = _feedback_scalar(data, "status", path)
    if status_value not in _FEEDBACK_STATUSES:
        raise _feedback_error(path, "status is not supported")
    metadata["status"] = status_value
    metadata["created_at"] = _feedback_timestamp(data.get("created_at"), path, "created_at")
    metadata["updated_at"] = (
        _feedback_timestamp(data.get("updated_at"), path, "updated_at")
        if schema_value.endswith("/v2")
        else metadata["created_at"]
    )
    project_value = _feedback_scalar(data, "project", path)
    if not _FEEDBACK_SAFE_ID_RE.fullmatch(project_value):
        raise _feedback_error(path, "project must be a safe identifier")
    metadata["project"] = project_value
    version = _feedback_scalar(data, "observed_skill_version", path)
    if not _FEEDBACK_SEMVER_RE.fullmatch(version):
        raise _feedback_error(path, "observed_skill_version must be valid SemVer")
    metadata["observed_skill_version"] = version
    if schema_value.endswith("/v2"):
        last_verified = _feedback_scalar(data, "last_verified_skill_version", path)
        if not _FEEDBACK_SEMVER_RE.fullmatch(last_verified):
            raise _feedback_error(path, "last_verified_skill_version must be valid SemVer")
    else:
        last_verified = version
    metadata["last_verified_skill_version"] = last_verified
    component = _feedback_scalar(data, "component", path)
    if not _FEEDBACK_SLUG_RE.fullmatch(component):
        raise _feedback_error(path, "component must be a lowercase kebab-case slug")
    metadata["component"] = component
    kind = _feedback_scalar(data, "kind", path)
    if kind not in _FEEDBACK_KINDS:
        raise _feedback_error(path, "kind is not supported")
    metadata["kind"] = kind
    impact = _feedback_scalar(data, "impact", path)
    if impact not in _FEEDBACK_IMPACTS:
        raise _feedback_error(path, "impact is not supported")
    metadata["impact"] = impact
    origin_surface = _feedback_scalar(data, "origin_surface", path)
    if origin_surface not in _FEEDBACK_ORIGIN_SURFACES:
        raise _feedback_error(path, "origin_surface is not supported")
    metadata["origin_surface"] = origin_surface
    suspected_scope = _feedback_scalar(data, "suspected_scope", path)
    if suspected_scope != "shared":
        raise _feedback_error(path, "suspected_scope must be shared")
    metadata["suspected_scope"] = suspected_scope
    signature = _feedback_scalar(data, "signature", path)
    if not _FEEDBACK_SIGNATURE_RE.fullmatch(signature):
        raise _feedback_error(path, "signature must be sha256 followed by 64 lowercase hex characters")
    metadata["signature"] = signature
    if schema_value.endswith("/v2"):
        resolution = _feedback_scalar(data, "resolution", path)
        if resolution not in _FEEDBACK_RESOLUTIONS:
            raise _feedback_error(path, "resolution is not supported")
        if status_value in _FEEDBACK_ACTIVE_STATUSES and resolution != "pending":
            raise _feedback_error(path, "active status requires resolution=pending")
        if status_value == "resolved" and resolution != "fixed":
            raise _feedback_error(path, "status=resolved requires resolution=fixed")
        if status_value == "duplicate" and resolution != "duplicate":
            raise _feedback_error(path, "status=duplicate requires resolution=duplicate")
        if status_value == "rejected" and resolution not in {
            "project-config",
            "environment",
            "not-shared",
            "not-reproducible",
            "wont-fix",
        }:
            raise _feedback_error(path, "status=rejected requires a supported rejected resolution")
    elif status_value in _FEEDBACK_ACTIVE_STATUSES:
        resolution = "pending"
    elif status_value == "resolved":
        resolution = "fixed"
    elif status_value == "duplicate":
        resolution = "duplicate"
    else:
        resolution = "not-shared"
    metadata["resolution"] = resolution
    export_value = _feedback_scalar(data, "export", path)
    if export_value != "metadata-only":
        raise _feedback_error(path, "export must be metadata-only")
    metadata["export"] = export_value

    body_lines = match.group(2).splitlines()
    titles = [line[2:].strip() for line in body_lines if line.startswith("# ")]
    if len(titles) != 1 or not titles[0]:
        raise _feedback_error(path, "body must contain exactly one non-empty level-one title")
    for heading in _FEEDBACK_HEADINGS:
        if body_lines.count(f"## {heading}") != 1:
            raise _feedback_error(path, f"body must contain exactly one '## {heading}' heading")
    heading_positions = [body_lines.index(f"## {heading}") for heading in _FEEDBACK_HEADINGS]
    if heading_positions != sorted(heading_positions):
        raise _feedback_error(path, "body headings must use the canonical order")
    for index, heading in enumerate(_FEEDBACK_HEADINGS):
        start = heading_positions[index] + 1
        end = heading_positions[index + 1] if index + 1 < len(heading_positions) else len(body_lines)
        if not any(line.strip() for line in body_lines[start:end]):
            raise _feedback_error(path, f"body section '{heading}' must not be empty")
    return metadata


def _read_feedback_report(
    directory_fd: int | Path,
    name: str,
    display_path: Path,
) -> tuple[bytes, int, tuple[int, int]]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    target = directory_fd / name if isinstance(directory_fd, Path) else None
    target_identity: tuple[int, int] | None = None
    try:
        if target is not None:
            checked = target.lstat()
            if _is_windows_reparse_point(checked) or not stat.S_ISREG(checked.st_mode):
                raise _feedback_error(display_path, "report must be a regular non-symlink file")
            target_identity = _project_path_identity(checked)
        descriptor = (
            os.open(target, flags)
            if isinstance(directory_fd, Path)
            else os.open(name, flags, dir_fd=directory_fd)
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or (target_identity is not None and _project_path_identity(metadata) != target_identity)
        ):
            raise _feedback_error(display_path, "report must be a regular non-symlink file")
        if target is not None:
            checked = target.lstat()
            if (
                _is_windows_reparse_point(checked)
                or not stat.S_ISREG(checked.st_mode)
                or _project_path_identity(checked) != target_identity
            ):
                raise _feedback_error(display_path, "report changed during its safety check")
        if metadata.st_size > _FEEDBACK_REPORT_MAX_BYTES:
            raise _feedback_error(display_path, f"report exceeds {_FEEDBACK_REPORT_MAX_BYTES} bytes")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            payload = handle.read(_FEEDBACK_REPORT_MAX_BYTES + 1)
        if target is not None:
            checked = target.lstat()
            if (
                _is_windows_reparse_point(checked)
                or not stat.S_ISREG(checked.st_mode)
                or _project_path_identity(checked) != target_identity
            ):
                raise _feedback_error(display_path, "report changed while it was read")
    except APError:
        raise
    except OSError as exc:
        raise _feedback_error(display_path, "report could not be read safely") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(payload) > _FEEDBACK_REPORT_MAX_BYTES:
        raise _feedback_error(display_path, f"report exceeds {_FEEDBACK_REPORT_MAX_BYTES} bytes")
    return payload, len(payload), (int(metadata.st_dev), int(metadata.st_ino))


def _feedback_project_root(raw: str) -> Path:
    try:
        root = Path(raw).expanduser().resolve(strict=True)
    except OSError as exc:
        raise APError(f"Skill feedback project does not exist: {raw}") from exc
    if not root.is_dir():
        raise APError(f"Skill feedback project is not a directory: {raw}")
    return root


def _feedback_configured_project(root: Path) -> tuple[str, str]:
    config = load_effective_config(root)
    name = _text(_mapping(config.get("project")).get("name"))
    if not _FEEDBACK_SAFE_ID_RE.fullmatch(name):
        raise APError("Effective project.name must be a safe non-empty identifier for feedback")
    version = _text(_mapping(config.get("workflow")).get("skill_version"))
    if not _FEEDBACK_SEMVER_RE.fullmatch(version):
        raise APError("Effective workflow.skill_version must be valid SemVer for feedback")
    return name, version


def _feedback_release_at_least(current: str, required: str) -> bool:
    def parts(value: str) -> tuple[tuple[int, int, int], bool]:
        match = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)(?:-([^+]+))?(?:\+.+)?", value)
        if not match:
            raise APError("Skill feedback version comparison requires valid SemVer")
        return tuple(int(match.group(index)) for index in range(1, 4)), bool(match.group(4))

    current_core, current_prerelease = parts(current)
    required_core, required_prerelease = parts(required)
    if current_core != required_core:
        return current_core > required_core
    if current_prerelease != required_prerelease:
        return not current_prerelease
    return current == required or (not current_prerelease and not required_prerelease)


def _load_feedback_resolution_catalog() -> dict[str, dict[str, str]]:
    path = _skill_root() / _FEEDBACK_RESOLUTION_POLICY
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise APError("Managed Skill feedback resolution catalog is missing") from exc
    if _is_windows_reparse_point(metadata) or not stat.S_ISREG(metadata.st_mode):
        raise APError("Managed Skill feedback resolution catalog must be a regular non-symlink file")
    if metadata.st_size > _FEEDBACK_RESOLUTION_MAX_BYTES:
        raise APError("Managed Skill feedback resolution catalog exceeds its size limit")
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, json.JSONDecodeError) as exc:
        raise APError("Managed Skill feedback resolution catalog is invalid") from exc
    if not isinstance(value, dict) or set(value) != {"schema", "entries"}:
        raise APError("Managed Skill feedback resolution catalog has an invalid top-level contract")
    if value.get("schema") != _FEEDBACK_RESOLUTION_SCHEMA or not isinstance(value.get("entries"), list):
        raise APError("Managed Skill feedback resolution catalog schema is invalid")
    catalog: dict[str, dict[str, str]] = {}
    ordered_signatures: list[str] = []
    for index, raw in enumerate(value["entries"]):
        if not isinstance(raw, dict):
            raise APError(f"Managed Skill feedback resolution entry {index} must be an object")
        allowed = {"signature", "disposition", "effective_skill_version", "canonical_signature"}
        if set(raw) - allowed or not {"signature", "disposition", "effective_skill_version"}.issubset(raw):
            raise APError(f"Managed Skill feedback resolution entry {index} has invalid fields")
        if any(not isinstance(item, str) or not item.strip() for item in raw.values()):
            raise APError(f"Managed Skill feedback resolution entry {index} values must be non-empty strings")
        signature = raw["signature"].strip()
        disposition = raw["disposition"].strip()
        effective = raw["effective_skill_version"].strip()
        if not _FEEDBACK_SIGNATURE_RE.fullmatch(signature):
            raise APError(f"Managed Skill feedback resolution entry {index} has an invalid signature")
        if disposition not in _FEEDBACK_CATALOG_DISPOSITIONS:
            raise APError(f"Managed Skill feedback resolution entry {index} has an invalid disposition")
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", effective):
            raise APError(f"Managed Skill feedback resolution entry {index} has an invalid release version")
        canonical = _text(raw.get("canonical_signature"))
        if disposition == "duplicate":
            if not _FEEDBACK_SIGNATURE_RE.fullmatch(canonical) or canonical == signature:
                raise APError(f"Managed Skill feedback resolution entry {index} needs a distinct canonical signature")
        elif canonical:
            raise APError(f"Managed Skill feedback resolution entry {index} cannot set canonical_signature")
        if signature in catalog:
            raise APError("Managed Skill feedback resolution catalog contains duplicate signatures")
        entry = {
            "signature": signature,
            "disposition": disposition,
            "effective_skill_version": effective,
        }
        if canonical:
            entry["canonical_signature"] = canonical
        catalog[signature] = entry
        ordered_signatures.append(signature)
    if ordered_signatures != sorted(ordered_signatures):
        raise APError("Managed Skill feedback resolution entries must be sorted by signature")
    return catalog


def _collect_project_feedback(
    root: Path,
) -> tuple[list[dict], int, tuple[int, int] | None, set[tuple[int, int]], str, str]:
    reports_relative = Path("docs/skill-feedback/reports")
    configured_project, installed_skill_version = _feedback_configured_project(root)
    with _open_project_directory(root, reports_relative) as directory_fd:
        if directory_fd is None:
            return [], 0, None, set(), configured_project, installed_skill_version
        directory_metadata = (
            directory_fd.stat() if isinstance(directory_fd, Path) else os.fstat(directory_fd)
        )
        directory_identity = (int(directory_metadata.st_dev), int(directory_metadata.st_ino))
        try:
            entries = os.listdir(directory_fd)
        except OSError as exc:
            raise APError("Cannot list Skill feedback reports safely") from exc
        if len(entries) > _FEEDBACK_PROJECT_MAX_ENTRIES:
            raise APError(
                f"Skill feedback directory exceeds {_FEEDBACK_PROJECT_MAX_ENTRIES} entries"
            )
        candidates: list[str] = []
        for name in entries:
            if not name.endswith(".md"):
                continue
            if not _FEEDBACK_FILENAME_RE.fullmatch(name):
                raise APError("Skill feedback directory contains an invalid Markdown filename")
            try:
                metadata = (
                    (directory_fd / name).stat(follow_symlinks=False)
                    if isinstance(directory_fd, Path)
                    else os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                )
            except OSError as exc:
                raise APError("Cannot inspect Skill feedback report safely") from exc
            if _is_windows_reparse_point(metadata) or not stat.S_ISREG(metadata.st_mode):
                raise APError(f"Skill feedback report must be a regular non-symlink file: {name}")
            candidates.append(name)
        candidates.sort()
        if len(candidates) > _FEEDBACK_PROJECT_MAX_REPORTS:
            raise APError(
                f"Skill feedback project exceeds {_FEEDBACK_PROJECT_MAX_REPORTS} reports"
            )

        reports: list[dict] = []
        total_bytes = 0
        file_identities: set[tuple[int, int]] = set()
        for name in candidates:
            display_path = reports_relative / name
            payload, size, file_identity = _read_feedback_report(directory_fd, name, display_path)
            if file_identity in file_identities:
                raise APError("Skill feedback project contains duplicate physical report files")
            file_identities.add(file_identity)
            report = _parse_feedback_report(payload, display_path)
            if report["project"] != configured_project:
                raise _feedback_error(
                    display_path,
                    "project must equal effective project.name",
            )
            report["source_path"] = display_path.as_posix()
            report["size_bytes"] = size
            reports.append(report)
            total_bytes += size
        return (
            reports,
            total_bytes,
            directory_identity,
            file_identities,
            configured_project,
            installed_skill_version,
        )


def _feedback_lifecycle(
    report: dict,
    installed_skill_version: str,
    catalog: dict[str, dict[str, str]],
) -> tuple[str, str, dict[str, str] | None]:
    if report["status"] not in _FEEDBACK_ACTIVE_STATUSES:
        return "closed", "none", catalog.get(report["signature"])
    catalog_entry = catalog.get(report["signature"])
    if catalog_entry:
        effective = catalog_entry["effective_skill_version"]
        if not _feedback_release_at_least(installed_skill_version, effective):
            return "upgrade-due", "upgrade-project-then-verify", catalog_entry
        disposition = catalog_entry["disposition"]
        if disposition == "fixed":
            if report["last_verified_skill_version"] == installed_skill_version:
                return "regression-current", "none", catalog_entry
            if _feedback_release_at_least(report["last_verified_skill_version"], effective):
                return (
                    "recheck-due",
                    "reproduce-on-installed-version-and-update-or-close",
                    catalog_entry,
                )
            return "verification-due", "verify-fix-then-resolve-or-delete", catalog_entry
        if disposition == "project-config":
            return (
                "reroute-due",
                "move-to-docs/project/auto-coding-skill.yaml-then-reject-or-delete",
                catalog_entry,
            )
        return "closure-due", "update-closed-status-or-delete", catalog_entry
    if report["last_verified_skill_version"] != installed_skill_version:
        return "recheck-due", "reproduce-on-installed-version-and-update-or-close", None
    return "active-current", "none", None


def _feedback_groups(reports: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for report in reports:
        grouped.setdefault(report["signature"], []).append(report)
    groups: list[dict] = []
    for signature, items in sorted(grouped.items()):
        projects = sorted({item["project"] for item in items})
        group_source_projects = sorted({item["source_project"] for item in items})
        groups.append(
            {
                "signature": signature,
                "report_count": len(items),
                "project_count": len(group_source_projects),
                "projects": projects,
                "source_projects": group_source_projects,
                "report_ids": [item["report_id"] for item in items],
                "cross_project": len(group_source_projects) > 1,
            }
        )
    return groups


def _feedback_collection_result(raw_projects: list[str]) -> dict:
    if not raw_projects:
        raise APError("feedback-collect requires at least one explicit --project")
    catalog = _load_feedback_resolution_catalog()
    roots: list[Path] = []
    seen_roots: set[str] = set()
    for raw in raw_projects:
        root = _feedback_project_root(raw)
        key = str(root)
        if key not in seen_roots:
            seen_roots.add(key)
            roots.append(root)
    if len(roots) > _FEEDBACK_COLLECTION_MAX_PROJECTS:
        raise APError(
            f"Skill feedback collection exceeds {_FEEDBACK_COLLECTION_MAX_PROJECTS} projects"
        )

    reports: list[dict] = []
    total_bytes = 0
    source_projects: list[dict[str, str]] = []
    seen_report_directories: set[tuple[int, int]] = set()
    seen_report_files: set[tuple[int, int]] = set()
    seen_configured_projects: set[str] = set()
    for index, root in enumerate(roots, start=1):
        source_id = f"project-{index}"
        (
            project_reports,
            project_bytes,
            directory_identity,
            file_identities,
            configured_project,
            installed_skill_version,
        ) = _collect_project_feedback(root)
        if directory_identity is not None:
            if directory_identity in seen_report_directories:
                raise APError("Explicit projects resolve to the same Skill feedback report directory")
            seen_report_directories.add(directory_identity)
        if seen_report_files.intersection(file_identities):
            raise APError("Explicit projects contain the same physical Skill feedback report file")
        seen_report_files.update(file_identities)
        if configured_project in seen_configured_projects:
            raise APError("Explicit projects must have distinct effective project.name values")
        seen_configured_projects.add(configured_project)
        source_descriptor = {
            "source_project": source_id,
            "project": configured_project,
            "skill_version": installed_skill_version,
        }
        source_projects.append(source_descriptor)
        total_bytes += project_bytes
        if total_bytes > _FEEDBACK_COLLECTION_MAX_BYTES:
            raise APError(
                f"Skill feedback collection exceeds {_FEEDBACK_COLLECTION_MAX_BYTES} bytes"
            )
        if len(reports) + len(project_reports) > _FEEDBACK_COLLECTION_MAX_REPORTS:
            raise APError(
                f"Skill feedback collection exceeds {_FEEDBACK_COLLECTION_MAX_REPORTS} reports"
            )
        for report in project_reports:
            report["source_project"] = source_id
            report["installed_skill_version"] = installed_skill_version
            lifecycle, recommended_action, catalog_entry = _feedback_lifecycle(
                report,
                installed_skill_version,
                catalog,
            )
            report["lifecycle"] = lifecycle
            report["recommended_action"] = recommended_action
            if catalog_entry:
                report["catalog_disposition"] = catalog_entry["disposition"]
                report["catalog_effective_skill_version"] = catalog_entry["effective_skill_version"]
                if catalog_entry.get("canonical_signature"):
                    report["catalog_canonical_signature"] = catalog_entry["canonical_signature"]
        reports.extend(project_reports)

    reports.sort(key=lambda item: (item["signature"], item["project"], item["report_id"], item["source_path"]))
    triage_reports = [
        report
        for report in reports
        if report["lifecycle"] in {"active-current", "regression-current"}
    ]
    groups = _feedback_groups(triage_reports)
    cross_project = [group for group in groups if group["cross_project"]]
    lifecycle_counts = {
        lifecycle: sum(1 for report in reports if report["lifecycle"] == lifecycle)
        for lifecycle in sorted({report["lifecycle"] for report in reports})
    }
    action_required = [
        {
            key: report[key]
            for key in (
                "source_project",
                "project",
                "report_id",
                "source_path",
                "signature",
                "installed_skill_version",
                "last_verified_skill_version",
                "lifecycle",
                "recommended_action",
                "catalog_disposition",
                "catalog_effective_skill_version",
                "catalog_canonical_signature",
            )
            if key in report
        }
        for report in reports
        if report["recommended_action"] != "none"
    ]
    return {
        "schema": _FEEDBACK_COLLECTION_SCHEMA,
        "projects": source_projects,
        "report_count": len(reports),
        "active_report_count": len(triage_reports),
        "closed_report_count": lifecycle_counts.get("closed", 0),
        "action_required_count": len(action_required),
        "total_bytes": total_bytes,
        "lifecycle_counts": lifecycle_counts,
        "action_required": action_required,
        "metadata": reports,
        "groups": groups,
        "cross_project": cross_project,
    }


def cmd_feedback_collect(args: argparse.Namespace) -> None:
    raw_projects = list(args.project or [])
    result = _feedback_collection_result(raw_projects)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(
        f"[feedback-collect] projects={len(result['projects'])} reports={result['report_count']} "
        f"active={result['active_report_count']} closed={result['closed_report_count']} "
        f"actions={result['action_required_count']} groups={len(result['groups'])} "
        f"cross_project={len(result['cross_project'])} bytes={result['total_bytes']}"
    )
    for item in result["action_required"]:
        print(
            f"[feedback-collect] action={item['recommended_action']} "
            f"project={item['project']} report={item['report_id']} lifecycle={item['lifecycle']}"
        )
    for group in result["groups"]:
        print(
            f"[feedback-collect] signature={group['signature']} "
            f"cross_project={str(group['cross_project']).lower()} "
            f"projects={','.join(group['projects'])} reports={','.join(group['report_ids'])}"
        )


_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_DIRECT_CLAIM_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _concurrency_cfg(cfg: dict) -> dict:
    value = cfg.get("concurrency")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise APError("concurrency must be a mapping")
    return value


def _task_isolation(cfg: dict) -> str:
    isolation = _text(_concurrency_cfg(cfg).get("isolation")).lower() or "adaptive"
    if isolation not in {"adaptive", "worktree"}:
        raise APError(
            "concurrency.isolation must be adaptive or worktree; legacy shared-checkout mode is unsupported"
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


def _direct_claim_path(repo: Path, claim_id: str) -> Path:
    value = _text(claim_id)
    if not _DIRECT_CLAIM_ID_RE.fullmatch(value):
        raise APError("Direct claim ID must be a 32-character lowercase hexadecimal token.")
    return _task_state_root(repo) / "direct-claims" / f"{value}.json"


def _active_direct_claims(repo: Path) -> list[dict]:
    root = _task_state_root(repo) / "direct-claims"
    if not root.exists():
        return []
    active: list[dict] = []
    for path in sorted(root.glob("*.json")):
        payload = _read_json_object(path)
        if payload is None:
            raise APError(
                f"Direct claim registry is unreadable or invalid JSON: {path}. "
                "Refusing to assume the checkout has no active writer."
            )
        try:
            schema = int(payload.get("schema") or 0)
        except (TypeError, ValueError) as exc:
            raise APError(f"Direct claim registry has an invalid schema: {path}") from exc
        claim_id = _text(payload.get("claim_id"))
        worktree_value = _text(payload.get("worktree_path"))
        owned_paths = payload.get("owned_paths")
        if (
            schema != 1
            or _text(payload.get("state")) != "active"
            or claim_id != path.stem
            or not _DIRECT_CLAIM_ID_RE.fullmatch(claim_id)
            or not _text(payload.get("owner"))
            or not _text(payload.get("base_sha"))
            or not _text(payload.get("branch"))
            or not worktree_value
            or not isinstance(owned_paths, list)
            or not owned_paths
            or not all(isinstance(item, str) and _text(item) for item in owned_paths)
        ):
            raise APError(
                f"Direct claim registry is malformed: {path}. "
                "Refusing to assume the checkout has no active writer."
            )
        worktree = Path(worktree_value).resolve()
        valid_checkout = worktree.exists()
        if valid_checkout:
            try:
                valid_checkout = bool(
                    _text(payload.get("base_sha")) == _resolve_commit(worktree, "HEAD")
                    and _text(payload.get("branch")) == _current_branch(worktree)
                )
            except APError:
                valid_checkout = False
        if not valid_checkout:
            path.unlink(missing_ok=True)
            continue
        active.append(payload)
    return active


def _create_direct_claim(repo: Path, cfg: dict, owned_paths: list[str], owner: str) -> dict:
    normalized = sorted({_normalize_owned_path(item) for item in owned_paths if _text(item)})
    if not normalized:
        raise APError("A direct claim requires at least one planned path.")
    if not _text(owner):
        raise APError("A direct claim requires --claim-owner or CODEX_THREAD_ID.")
    if _task_isolation(cfg) != "adaptive":
        raise APError("Direct claims are available only with concurrency.isolation=adaptive.")
    if _working_tree_paths(repo):
        raise APError("A direct claim must be created while the checkout is clean, before the first write.")
    if _has_registered_active_task(repo):
        raise APError("A registered active task already owns repository writes.")
    branch = _current_branch(repo)
    if not branch:
        raise APError("A direct claim requires a named current branch.")
    timeout_s = float(_concurrency_cfg(cfg).get("lock_timeout_sec") or 30)
    with (
        _repo_lock(repo, "integration", timeout_s=timeout_s),
        _repo_lock(repo, "task-registry", timeout_s=timeout_s),
        _repo_lock(repo, "direct-claim", timeout_s=timeout_s),
    ):
        if _working_tree_paths(repo):
            raise APError("Checkout changed while acquiring the direct claim; isolate instead.")
        if _has_registered_active_task(repo):
            raise APError("A registered active task acquired repository writes.")
        existing = _active_direct_claims(repo)
        base_sha = _resolve_commit(repo, "HEAD")
        worktree_path = str(repo.resolve())
        if existing:
            raise APError(
                "Another direct writer already owns this checkout: "
                + ", ".join(
                    f"{_text(item.get('owner'))}:{_text(item.get('claim_id'))}"
                    for item in existing
                )
            )
        claim_id = uuid.uuid4().hex
        payload = {
            "schema": 1,
            "claim_id": claim_id,
            "state": "active",
            "owner": _text(owner),
            "base_sha": base_sha,
            "branch": branch,
            "worktree_path": worktree_path,
            "owned_paths": normalized,
            "created_at": _now_iso(),
        }
        _write_json_object(_direct_claim_path(repo, claim_id), payload)
        return payload


def _require_direct_claim(repo: Path, claim_id: str, planned_paths: list[str]) -> dict:
    if not _text(claim_id):
        raise APError(
            "--continue-direct requires --direct-claim from a clean pre-write classify --claim-direct."
        )
    payload = _read_json_object(_direct_claim_path(repo, claim_id)) or {}
    normalized = sorted({_normalize_owned_path(item) for item in planned_paths if _text(item)})
    if int(payload.get("schema") or 0) != 1 or _text(payload.get("state")) != "active":
        raise APError("Direct claim is missing, consumed, or invalid.")
    if normalized != sorted(payload.get("owned_paths") or []):
        raise APError("Continued direct paths must exactly match the clean pre-write direct claim.")
    if _text(payload.get("base_sha")) != _resolve_commit(repo, "HEAD"):
        raise APError("Direct claim base HEAD changed; use an isolated task instead.")
    if _text(payload.get("branch")) != _current_branch(repo):
        raise APError("Direct claim branch changed; use an isolated task instead.")
    if Path(_text(payload.get("worktree_path"))).resolve() != repo.resolve():
        raise APError("Direct claim belongs to another checkout.")
    actor = _text(os.environ.get("CODEX_THREAD_ID"))
    if actor and actor != _text(payload.get("owner")):
        raise APError("Direct claim belongs to another writer.")
    dirty = _working_tree_paths(repo)
    outside = [path for path in dirty if not _path_is_owned(path, normalized)]
    if outside:
        raise APError("Changes outside the clean direct claim:\n- " + "\n- ".join(outside))
    return payload


def _consume_direct_claim(repo: Path, claim_id: str) -> None:
    if _text(claim_id):
        _direct_claim_path(repo, claim_id).unlink(missing_ok=True)


def _has_registered_active_task(repo: Path) -> bool:
    registry = _task_state_root(repo) / "tasks"
    if not registry.exists():
        return False
    for path in sorted(registry.glob("*.json")):
        payload = _read_json_object(path)
        if payload is None:
            raise APError(
                f"Task registry is unreadable or invalid JSON: {path}. "
                "Refusing to assume the checkout has no active writer."
            )
        state = _text(payload.get("state"))
        if not state:
            raise APError(
                f"Task registry has no state: {path}. "
                "Refusing to assume the checkout has no active writer."
            )
        if state not in {"integrated", "cleanup-pending"}:
            return True
    return False


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
    try:
        schema = int(manifest.get("schema") or 1)
    except (TypeError, ValueError) as exc:
        raise APError(f"Task {task_id} has an invalid manifest schema.") from exc
    if schema < 2:
        raise APError(
            f"Task {task_id} is a legacy schema-1 task. This runtime cannot safely infer or claim "
            "owned_paths for an in-flight task. Finish or clean it with the previously installed "
            "runtime before running autocoding sync, or restore the 3.0.0 runtime."
        )
    execution_mode = _text(manifest.get("execution_mode")).lower() or "isolated"
    if execution_mode not in {"direct", "isolated"}:
        raise APError(f"Task {task_id} has an invalid execution_mode: {execution_mode!r}")
    task_uuid = _text(manifest.get("task_uuid"))
    if not re.fullmatch(r"[0-9a-f]{32}", task_uuid):
        raise APError(f"Invalid task manifest UUID for {task_id}; refusing Git operations.")
    task_branch = _text(manifest.get("task_branch"))
    if (execution_mode == "isolated" and not task_branch.endswith(f"/{task_id}")) or run(
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
    if execution_mode == "direct" and worktree != control:
        raise APError(f"Direct task {task_id} must use its control checkout.")
    if execution_mode == "isolated" and (
        worktree == control or control in worktree.parents or worktree in control.parents
    ):
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
        "blocked",
        "runtime-bypassed",
    }:
        raise APError(f"Task {task_id} has an invalid review contract.")
    review_required = manifest.get("review_required", schema < 3)
    if not isinstance(review_required, bool):
        raise APError(f"Task {task_id} has an invalid review_required flag.")
    try:
        scope_revision = int(manifest.get("scope_revision") or 1)
    except (TypeError, ValueError) as exc:
        raise APError(f"Task {task_id} has an invalid scope_revision.") from exc
    if scope_revision < 1:
        raise APError(f"Task {task_id} has an invalid scope_revision.")
    effective_profile = _text(manifest.get("effective_profile"))
    if effective_profile and effective_profile not in (_WORKFLOW_PROFILES - {"auto"}):
        raise APError(f"Task {task_id} has an invalid effective_profile.")
    review_depth = _text(manifest.get("review_depth"))
    if review_depth and review_depth not in {"none", "focused", "deep"}:
        raise APError(f"Task {task_id} has an invalid review_depth.")
    if "review_timeout_seconds" in manifest:
        timeout_value = manifest.get("review_timeout_seconds")
        if isinstance(timeout_value, bool) or not isinstance(timeout_value, int) or timeout_value < 0:
            raise APError(f"Task {task_id} has an invalid review_timeout_seconds.")
    if "design_required" in manifest and not isinstance(manifest.get("design_required"), bool):
        raise APError(f"Task {task_id} has an invalid design_required flag.")
    if "scope_history" in manifest and not isinstance(manifest.get("scope_history"), list):
        raise APError(f"Task {task_id} has an invalid scope_history.")
    return manifest


def _load_task_manifest(repo: Path, task_id: str) -> dict:
    path = _task_registry_path(repo, task_id)
    manifest = _read_json_object(path)
    if not manifest:
        raise APError(
            f"Task is not registered: {task_id}. Run `ap.py task-start {task_id}` first."
        )
    return _validate_task_manifest(repo, manifest, task_id)


def _save_task_manifest(repo: Path, manifest: dict, *, strict_worktree: bool = False) -> None:
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
                if strict_worktree:
                    raise


def _guard_review_directory(path: Path, common_dir: Path, *, create: bool) -> None:
    if path.is_symlink():
        raise APError(f"Refusing symlinked Git-local review storage: {path}")
    if path.exists():
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise APError(f"Cannot inspect Git-local review storage: {path}: {exc}") from exc
        if not stat.S_ISDIR(metadata.st_mode):
            raise APError(f"Git-local review storage must be a directory: {path}")
    elif create:
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            _guard_review_directory(path, common_dir, create=False)
        except OSError as exc:
            raise APError(f"Cannot create Git-local review storage: {path}: {exc}") from exc
    try:
        resolved = path.resolve()
        resolved.relative_to(common_dir)
    except (OSError, ValueError) as exc:
        raise APError(f"Git-local review storage escapes the Git common directory: {path}") from exc
    if os.name == "posix" and path.exists():
        try:
            metadata = path.lstat()
            if metadata.st_uid != os.geteuid():
                raise APError(f"Git-local review storage must be owned by the current user: {path}")
            if create:
                path.chmod(0o700)
                metadata = path.lstat()
            if stat.S_IMODE(metadata.st_mode) != 0o700:
                raise APError(f"Git-local review storage must use mode 0700: {path}")
        except APError:
            raise
        except OSError as exc:
            action = "protect" if create else "verify"
            raise APError(f"Cannot {action} Git-local review storage: {path}: {exc}") from exc


def _task_review_root(repo: Path, *, create: bool = False) -> Path:
    common_dir = _git_common_dir(repo).resolve()
    state_root = common_dir / "auto-coding-skill"
    review_root = state_root / "reviews"
    _guard_review_directory(state_root, common_dir, create=create)
    if state_root.exists():
        _guard_review_directory(review_root, common_dir, create=create)
    return review_root


def _task_review_dir(repo: Path, task_id: str, *, create: bool = False) -> Path:
    common_dir = _git_common_dir(repo).resolve()
    review_root = _task_review_root(repo, create=create)
    review_dir = review_root / _validate_task_id(task_id)
    if review_root.exists():
        _guard_review_directory(review_dir, common_dir, create=create)
    return review_dir


def _process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _cleanup_stale_review_snapshots(root: Path, *, legacy_root: bool = False) -> None:
    if not root.exists() or root.is_symlink():
        return
    now = time.time()
    for candidate in sorted(root.glob(".snapshot-*")):
        if not candidate.is_dir() or candidate.is_symlink():
            continue
        match = re.fullmatch(r"\.snapshot-(\d+)-[A-Za-z0-9_-]+", candidate.name)
        if match and _process_is_running(int(match.group(1))):
            continue
        if not match:
            try:
                age_seconds = now - candidate.stat().st_mtime
            except OSError:
                continue
            if not legacy_root or age_seconds < 3600:
                continue
        try:
            shutil.rmtree(candidate)
        except OSError as exc:
            raise APError(f"Cannot remove stale Git-local review snapshot: {candidate}: {exc}") from exc


def _delete_task_review_artifacts(repo: Path, task_id: str) -> None:
    review_dir = _task_review_dir(repo, task_id)
    if review_dir.is_symlink():
        raise APError(f"Refusing to remove symlinked Git-local review state: {review_dir}")
    if not review_dir.exists():
        return
    try:
        shutil.rmtree(review_dir)
    except OSError as exc:
        raise APError(f"Cannot remove Git-local review state: {review_dir}: {exc}") from exc


def _delete_task_manifest(repo: Path, manifest: dict) -> None:
    task_id = _validate_task_id(_text(manifest.get("task_id")))
    registry_path = _task_registry_path(repo, task_id)
    try:
        registry_path.unlink(missing_ok=True)
    except OSError as exc:
        raise APError(f"Cannot remove task registry state: {registry_path}: {exc}") from exc

    # Registry deletion is the authoritative lifecycle transition. Review
    # evidence is deliberately removed afterwards so a registry failure never
    # leaves a live task without the immutable artifact that justified it. If
    # artifact cleanup fails, task-prune can safely retry it as orphaned state.
    worktree_value = _text(manifest.get("worktree_path"))
    if worktree_value and Path(worktree_value).exists():
        _clear_final_gate_receipt(Path(worktree_value))
    try:
        _delete_task_review_artifacts(repo, task_id)
    except APError as exc:
        print(
            f"[task-cleanup] warning: registry removed but Git-local review state remains for task-prune: {exc}",
            file=sys.stderr,
        )


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
    """Return one fail-closed Git status snapshot, including both rename endpoints."""
    result = run(
        [
            "git",
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
            "--no-renames",
        ],
        cwd=repo,
        check=False,
    )
    if result.returncode != 0:
        raise APError(
            "Cannot inspect working tree status; refusing a direct execution plan: "
            + (result.stderr.strip() or result.stdout.strip() or "git status failed")
        )
    paths: set[str] = set()
    entries = result.stdout.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        record_type = entry[:1]
        if record_type == "1":
            fields = entry.split(" ", 8)
            path = fields[8] if len(fields) == 9 else ""
        elif record_type == "2":
            fields = entry.split(" ", 9)
            path = fields[9] if len(fields) == 10 else ""
            if index >= len(entries) or not entries[index]:
                raise APError(
                    "Cannot parse renamed Git path; refusing a direct execution plan."
                )
            paths.add(entries[index])
            index += 1
        elif record_type == "u":
            fields = entry.split(" ", 10)
            path = fields[10] if len(fields) == 11 else ""
        elif entry.startswith("? "):
            path = entry[2:]
        else:
            path = ""
        if not path:
            raise APError(
                "Cannot parse Git working tree status; refusing a direct execution plan."
            )
        paths.add(path)
    return sorted(path.replace("\\", "/") for path in paths if path)


def _task_runtime_paths(repo: Path, cfg: dict, manifest: Optional[dict]) -> set[str]:
    docs_cfg = cfg.get("docs") or {}
    gate_cfg = _gate_cfg(cfg)
    paths = {
        _text(gate_cfg.get("profile_log")) or ".local/auto-coding-skill/gate-profile.jsonl",
    }
    if manifest and _bool_config(docs_cfg.get("track_task_evidence"), False):
        task_id = _validate_task_id(_text(manifest.get("task_id")))
        evidence_dir = _text(docs_cfg.get("task_evidence_dir")) or "docs/tasks/evidence"
        paths.add(f"{evidence_dir.rstrip('/')}/{task_id}.jsonl")
    else:
        paths.add(".local/auto-coding-skill/evidence.jsonl")
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
            ["git", "diff", "--cached", "--no-renames", "--binary", "--no-ext-diff", "--", *batch],
            cwd=repo,
            check=False,
        )
        digest.update(cached.stdout.encode("utf-8", errors="surrogateescape"))
        unstaged = run(
            ["git", "diff", "--no-renames", "--binary", "--no-ext-diff", "--", *batch],
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


def _final_gate_receipt_path(repo: Path) -> Path:
    return _git_dir(repo) / "auto-coding-skill-final-gate.json"


def _clear_final_gate_receipt(repo: Path) -> None:
    try:
        _final_gate_receipt_path(repo).unlink(missing_ok=True)
    except APError:
        return


def _final_gate_identity(
    repo: Path,
    cfg: dict,
    manifest: dict,
    plan: dict,
    base_ref: str,
) -> tuple[dict, str]:
    paths = list(plan.get("changed_files") or [])
    validation_plan = _validation_plan(cfg, paths)
    _validate_validation_plan(cfg, validation_plan)
    command_hashes = {
        name: hashlib.sha256(_configured_command(cfg, name).encode("utf-8")).hexdigest()
        for name in validation_plan["commands"]
    }
    plan_payload = {
        "scope": plan.get("selected_scope"),
        "profile": plan.get("profile"),
        "effective_mode": plan.get("effective_mode"),
        "paths": validation_plan["paths"],
        "commands": validation_plan["commands"],
        "command_hashes": command_hashes,
        "command_timeouts": validation_plan["command_timeouts"],
        "matched_routes": validation_plan["matched_routes"],
        "coverage": validation_plan["coverage"],
        "unmapped": validation_plan["unmapped"],
        "docs_only": validation_plan["docs_only"],
        "compatibility_fallback": validation_plan["compatibility_fallback"],
        "on_unmapped": _text(_validation_cfg(cfg).get("on_unmapped")).lower() or "error",
        "budget": _final_gate_budget(cfg),
        "diff_check": "working-index-base-v1",
    }
    plan_sha256 = hashlib.sha256(
        json.dumps(plan_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    resolved_base = _resolve_commit(repo, base_ref or _text(manifest.get("base_sha")) or "HEAD")
    identity = {
        "algorithm": _FINAL_GATE_CACHE_ALGORITHM,
        "skill_version": _text((cfg.get("workflow") or {}).get("skill_version")),
        "task_id": _text(manifest.get("task_id")),
        "task_uuid": _text(manifest.get("task_uuid")),
        "worktree_path": str(repo.resolve()),
        "branch": _current_branch(repo),
        "base_sha": resolved_base,
        "head_sha": _resolve_commit(repo, "HEAD"),
        "scope_revision": int(manifest.get("scope_revision") or 1),
        "owned_paths": sorted(manifest.get("owned_paths") or []),
        "writer_generation": int((manifest.get("writer_lease") or {}).get("generation") or 0),
        "plan_sha256": plan_sha256,
    }
    return identity, _task_content_fingerprint(repo, cfg, manifest)


def _record_final_gate_receipt(
    repo: Path,
    cfg: dict,
    manifest: dict,
    plan: dict,
    base_ref: str,
    executed: list[str],
) -> None:
    identity, fingerprint = _final_gate_identity(repo, cfg, manifest, plan, base_ref)
    _write_json_object(
        _final_gate_receipt_path(repo),
        {
            "schema": _FINAL_GATE_CACHE_SCHEMA,
            "kind": "final_changed_scope_gate",
            "status": "pass",
            "identity": identity,
            "content_fingerprints": [fingerprint],
            "executed": list(executed),
            "passed_at": _now_iso(),
        },
    )


def _reuse_final_gate_receipt(
    repo: Path,
    cfg: dict,
    manifest: dict,
    plan: dict,
    base_ref: str,
) -> Optional[dict]:
    receipt = _read_json_object(_final_gate_receipt_path(repo)) or {}
    if (
        int(receipt.get("schema") or 0) != _FINAL_GATE_CACHE_SCHEMA
        or _text(receipt.get("kind")) != "final_changed_scope_gate"
        or _text(receipt.get("status")) != "pass"
    ):
        return None
    identity, fingerprint = _final_gate_identity(repo, cfg, manifest, plan, base_ref)
    if receipt.get("identity") != identity:
        return None
    allowed = receipt.get("content_fingerprints") or []
    if not isinstance(allowed, list) or fingerprint not in allowed:
        return None
    return receipt


def _extend_final_gate_receipt(
    repo: Path,
    cfg: dict,
    manifest: dict,
    plan: dict,
    base_ref: str,
) -> None:
    receipt = _read_json_object(_final_gate_receipt_path(repo)) or {}
    identity, fingerprint = _final_gate_identity(repo, cfg, manifest, plan, base_ref)
    if (
        int(receipt.get("schema") or 0) != _FINAL_GATE_CACHE_SCHEMA
        or _text(receipt.get("kind")) != "final_changed_scope_gate"
        or _text(receipt.get("status")) != "pass"
        or receipt.get("identity") != identity
    ):
        raise APError("The successful final-gate receipt no longer matches the staged task state.")
    allowed = list(receipt.get("content_fingerprints") or [])
    if fingerprint not in allowed:
        allowed.append(fingerprint)
    receipt["content_fingerprints"] = allowed
    _write_json_object(_final_gate_receipt_path(repo), receipt)


def _staged_paths(repo: Path) -> list[str]:
    return sorted(
        set(
            _checked_git_z_paths(
                repo,
                [
                    "git",
                    "diff",
                    "--cached",
                    "--no-renames",
                    "--name-only",
                    "-z",
                    "--diff-filter=ACDMRTUXB",
                ],
                "staged task paths",
            )
        )
    )


def _exact_stage_plan(repo: Path, paths: list[str], *, dry_run: bool) -> tuple[list[str], list[str]]:
    expected = sorted(set(path for path in paths if path))
    expected_set = set(expected)
    staged = _staged_paths(repo)
    pending = _unstaged_task_paths(repo)
    unexpected = sorted((set(staged) | set(pending)) - expected_set)
    if unexpected:
        raise APError(
            "Refusing to commit paths outside the current task:\n- " + "\n- ".join(unexpected)
        )
    if dry_run:
        for start in range(0, len(pending), 100):
            run(
                ["git", "add", "--dry-run", "-A", "--", *pending[start : start + 100]],
                cwd=repo,
            )
    return expected, pending


def _preflight_exact_paths(repo: Path, paths: list[str]) -> None:
    _exact_stage_plan(repo, paths, dry_run=True)


def _stage_exact_paths(repo: Path, paths: list[str]) -> list[str]:
    expected, pending = _exact_stage_plan(repo, paths, dry_run=False)
    for start in range(0, len(pending), 100):
        run(["git", "add", "-A", "--", *pending[start : start + 100]], cwd=repo)
    staged = _staged_paths(repo)
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


def _owned_paths_overlap(left: list[str], right: list[str]) -> bool:
    for first in left:
        first = _normalize_owned_path(first)
        for second in right:
            second = _normalize_owned_path(second)
            if (
                first == "."
                or second == "."
                or first == second
                or first.startswith(second.rstrip("/") + "/")
                or second.startswith(first.rstrip("/") + "/")
            ):
                return True
    return False


_TERMINAL_LEDGER_PATTERNS = [
    "docs/tasks/taskbook.md",
    "docs/tasks/closure-log.md",
    "docs/tasks/archive-index.md",
    "docs/tasks/archives/**",
    "docs/tasks/closures/**",
    "docs/archive/design/**",
]


def _is_terminal_ledger_maintenance(paths: list[str]) -> bool:
    return bool(paths) and all(_path_matches(path, _TERMINAL_LEDGER_PATTERNS) for path in paths)


def _task_managed_paths(cfg: dict, manifest: dict) -> list[str]:
    if int(manifest.get("schema") or 2) >= 3:
        return []
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
            [
                "git",
                "diff",
                "--no-renames",
                "--name-only",
                "-z",
                "--diff-filter=ACDMRTUXB",
                base_sha,
                "--",
            ],
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


def _task_staging_paths(repo: Path, cfg: dict, manifest: dict) -> list[str]:
    paths = _task_commit_paths(repo)
    owned = [_normalize_owned_path(item) for item in manifest.get("owned_paths") or []]
    managed = set(_task_managed_paths(cfg, manifest))
    unowned = [
        path
        for path in paths
        if path not in managed and not _path_is_owned(path, owned)
    ]
    if unowned:
        raise APError("Changes outside task owned_paths:\n- " + "\n- ".join(unowned))
    return paths


def _review_snapshot_git(
    repo: Path,
    arguments: list[str],
    env: dict[str, str],
) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=str(repo),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise APError(
            f"Cannot capture immutable task review snapshot ({completed.returncode}): "
            f"git {' '.join(arguments)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed.stdout


def _task_review_paths(repo: Path, manifest: dict, cfg: Optional[dict] = None) -> list[str]:
    base_sha = _text(manifest.get("base_sha"))
    owned = [_normalize_owned_path(item) for item in manifest.get("owned_paths") or []]
    managed = set(_task_managed_paths(cfg or _load_cfg(repo), manifest))
    return [
        path
        for path in _task_changed_paths_from_base(repo, base_sha)
        if path not in managed and _path_is_owned(path, owned)
    ]


def _task_review_fingerprint_for_tree(manifest: dict, paths: list[str], tree_sha: str) -> str:
    base_sha = _text(manifest.get("base_sha"))
    owned = [_normalize_owned_path(item) for item in manifest.get("owned_paths") or []]
    digest = hashlib.sha256()
    digest.update(
        (
            f"contract:{_AGENT_CONTRACT_VERSION}\nbase:{base_sha}\n"
            f"scope_revision:{int(manifest.get('scope_revision') or 1)}\n"
        ).encode("utf-8")
    )
    for owned_path in owned:
        digest.update(f"owned:{owned_path}\0".encode("utf-8", errors="surrogateescape"))
    for rel in paths:
        digest.update(f"path:{rel}\0".encode("utf-8", errors="surrogateescape"))
    digest.update(f"tree:{tree_sha}\0".encode("ascii"))
    return digest.hexdigest()


def _require_bounded_review_snapshot_input(repo: Path, paths: list[str]) -> None:
    limit = _review_diff_artifact_limit()
    total = 0
    for rel in paths:
        path = repo / rel
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise APError(f"Cannot size review snapshot input {rel}: {exc}") from exc
        if stat.S_ISREG(metadata.st_mode):
            total += metadata.st_size
        elif stat.S_ISLNK(metadata.st_mode):
            try:
                total += len(os.readlink(path).encode("utf-8", errors="surrogateescape"))
            except OSError as exc:
                raise APError(f"Cannot size review snapshot symlink {rel}: {exc}") from exc
        if total > limit:
            raise APError(
                "Task-owned review snapshot input exceeds the 64 MiB safety limit; "
                "narrow the task-owned scope or use a project-specific large-artifact review path."
            )


def _task_review_snapshot(
    repo: Path,
    manifest: dict,
    cfg: Optional[dict] = None,
    *,
    include_patch: bool = False,
) -> dict:
    base_sha = _text(manifest.get("base_sha"))
    paths = _task_review_paths(repo, manifest, cfg)
    _require_bounded_review_snapshot_input(repo, paths)
    task_id = _validate_task_id(_text(manifest.get("task_id")))
    review_root = _task_review_dir(repo, task_id, create=True)
    _cleanup_stale_review_snapshots(review_root)
    snapshot_root = Path(
        tempfile.mkdtemp(prefix=f".snapshot-{os.getpid()}-", dir=review_root)
    )
    if os.name == "posix":
        snapshot_root.chmod(0o700)
    index_path = snapshot_root / "index"
    object_dir = snapshot_root / "objects"
    object_dir.mkdir(mode=0o700)
    env = os.environ.copy()
    inherited_alternates = _text(env.get("GIT_ALTERNATE_OBJECT_DIRECTORIES"))
    alternates = [str((_git_common_dir(repo) / "objects").resolve())]
    if inherited_alternates:
        alternates.append(inherited_alternates)
    env.update(
        {
            "GIT_INDEX_FILE": str(index_path),
            "GIT_OBJECT_DIRECTORY": str(object_dir),
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": os.pathsep.join(alternates),
            "GIT_PAGER": "cat",
        }
    )
    try:
        _review_snapshot_git(repo, ["read-tree", base_sha], env)
        for start in range(0, len(paths), 100):
            _review_snapshot_git(
                repo,
                ["add", "-A", "--", *paths[start : start + 100]],
                env,
            )
        tree_sha = _text(_review_snapshot_git(repo, ["write-tree"], env))
        if not tree_sha:
            raise APError("Cannot capture immutable task review snapshot tree.")
        patch = b""
        if include_patch:
            patch_path = snapshot_root / "review.patch"
            patch_arguments = [
                "git",
                "diff",
                "--binary",
                "--full-index",
                "--no-renames",
                "--no-ext-diff",
                "--no-textconv",
                "--no-color",
                "--diff-algorithm=myers",
                "--no-indent-heuristic",
                "--src-prefix=a/",
                "--dst-prefix=b/",
                base_sha,
                tree_sha,
                "--",
            ]
            patch_limit = _review_diff_artifact_limit()
            stderr_path = snapshot_root / "review.stderr"
            process: Optional[subprocess.Popen[bytes]] = None
            try:
                with patch_path.open("wb") as handle, stderr_path.open("wb") as stderr_handle:
                    process = subprocess.Popen(
                        patch_arguments,
                        cwd=str(repo),
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=stderr_handle,
                    )
                    if process.stdout is None:
                        raise APError("Cannot capture immutable task review patch output.")
                    patch_size = 0
                    while True:
                        chunk = process.stdout.read(64 * 1024)
                        if not chunk:
                            break
                        patch_size += len(chunk)
                        if patch_size > patch_limit:
                            if process.poll() is None:
                                process.terminate()
                                try:
                                    process.wait(timeout=2)
                                except subprocess.TimeoutExpired:
                                    process.kill()
                                    process.wait(timeout=2)
                            raise APError(
                                "Immutable task review patch exceeds the 64 MiB safety limit; "
                                "narrow the task-owned scope or review the large artifact through a project-specific path."
                            )
                        handle.write(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
                    returncode = process.wait()
            except OSError as exc:
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait()
                raise APError(f"Cannot render immutable task review patch: {exc}") from exc
            if returncode != 0:
                raise APError(
                    "Cannot render immutable task review patch "
                    f"({returncode}): {stderr_path.read_text(encoding='utf-8', errors='replace')}"
                )
            patch = patch_path.read_bytes()
    finally:
        try:
            shutil.rmtree(snapshot_root)
        except OSError as exc:
            raise APError(
                f"Cannot remove temporary Git-local review snapshot state: {snapshot_root}: {exc}"
            ) from exc

    return {
        "fingerprint": _task_review_fingerprint_for_tree(manifest, paths, tree_sha),
        "tree_sha": tree_sha,
        "paths": paths,
        "patch": patch,
        "patch_sha256": hashlib.sha256(patch).hexdigest() if include_patch else "",
    }


def _task_review_fingerprint(repo: Path, manifest: dict, cfg: Optional[dict] = None) -> str:
    return _text(_task_review_snapshot(repo, manifest, cfg).get("fingerprint"))


def _staged_task_review_fingerprint(repo: Path, manifest: dict, cfg: Optional[dict] = None) -> str:
    tree_sha = _text(run(["git", "write-tree"], cwd=repo).stdout)
    if not tree_sha:
        raise APError("Cannot bind the staged task tree to its approved review.")
    return _task_review_fingerprint_for_tree(
        manifest,
        _task_review_paths(repo, manifest, cfg),
        tree_sha,
    )


def _require_staged_review_matches(repo: Path, cfg: dict, manifest: dict) -> None:
    if not bool(manifest.get("review_required", int(manifest.get("schema") or 2) < 3)):
        return
    approved = _text((manifest.get("review") or {}).get("diff_fingerprint"))
    staged = _staged_task_review_fingerprint(repo, manifest, cfg)
    if staged != approved:
        raise APError(
            "The exact staged tree does not match the immutable review clearance snapshot; refusing to commit."
        )


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
    explicit = _text(getattr(args, field, ""))
    runtime_actor = _text(os.environ.get("CODEX_THREAD_ID"))
    if explicit and runtime_actor and explicit != runtime_actor:
        raise APError(
            f"Explicit --{field.replace('_', '-')} does not match CODEX_THREAD_ID; "
            "actor identity cannot be overridden."
        )
    actor = runtime_actor or explicit
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


def _validate_review_runtime_override(repo: Path, manifest: dict, fingerprint: str) -> dict:
    review = manifest.get("review") or {}
    override_path = _review_runtime_override_path(
        repo,
        _text(manifest.get("task_id")),
        fingerprint,
    ).resolve()
    if Path(_text(review.get("runtime_override_path"))).resolve() != override_path:
        raise APError("Reviewer runtime override path does not match Git-local task state.")
    override_sha256 = _text(review.get("runtime_override_sha256"))
    payload_bytes = _read_private_review_file(override_path, "runtime override")
    if hashlib.sha256(payload_bytes).hexdigest() != override_sha256:
        raise APError("Reviewer runtime override SHA-256 binding is invalid.")
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise APError("Reviewer runtime override is invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise APError("Reviewer runtime override must contain one JSON object.")
    expected = {
        "schema": 1,
        "task_id": _text(manifest.get("task_id")),
        "diff_fingerprint": fingerprint,
        "assignment_sha256": _text(review.get("assignment_sha256")),
        "diff_artifact_sha256": _text(review.get("diff_artifact_sha256")),
        "runtime_receipt_path": _text(review.get("runtime_receipt_path")),
    }
    mismatched = [field for field, value in expected.items() if payload.get(field) != value]
    if mismatched:
        raise APError(
            "Reviewer runtime override does not match task state: " + ", ".join(mismatched)
        )
    if payload.get("user_authorized") is not True:
        raise APError("Reviewer runtime override lacks explicit user authorization.")
    if not _text(payload.get("authorized_by")) or not _text(payload.get("reason")):
        raise APError("Reviewer runtime override authorization audit is incomplete.")
    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or not evidence or not all(
        isinstance(item, str) and item for item in evidence
    ):
        raise APError("Reviewer runtime override requires non-empty evidence.")
    receipt_path = Path(_text(payload.get("runtime_receipt_path"))).resolve()
    expected_result_path, expected_receipt_path = _review_runtime_paths(
        repo,
        _text(manifest.get("task_id")),
        fingerprint,
    )
    del expected_result_path
    if receipt_path != expected_receipt_path.resolve():
        raise APError("Reviewer runtime override receipt path is not canonical.")
    receipt_sha256 = _private_review_file_sha256(receipt_path, "runtime receipt")
    if receipt_sha256 != _text(payload.get("runtime_receipt_sha256")):
        raise APError("Reviewer runtime override receipt SHA-256 binding is invalid.")
    failure_state = _text(payload.get("runtime_failure_state"))
    if failure_state not in {"runtime-unavailable", "analysis-timed-out"}:
        raise APError("Reviewer runtime override cannot cover this failure state.")
    assignment_path = Path(_text(review.get("assignment_path"))).resolve()
    assignment = _load_bound_review_assignment(repo, manifest, assignment_path)
    receipt = _validate_bound_review_runtime_receipt(
        repo,
        manifest,
        assignment,
        receipt_path,
        failure_state,
    )
    if _text(receipt.get("status")) != failure_state:
        raise APError("Reviewer runtime override failure state does not match its receipt.")
    if failure_state == "runtime-unavailable" and len(receipt.get("attempts") or []) != _REVIEW_RUNTIME_ATTEMPT_LIMIT:
        raise APError("Reviewer runtime-unavailable override requires exhausted startup attempts.")
    return payload


def _require_approved_review(repo: Path, cfg: dict, manifest: dict) -> str:
    unowned = _task_unowned_paths(repo, cfg, manifest)
    if unowned:
        raise APError("Changes outside task owned_paths:\n- " + "\n- ".join(unowned))
    fingerprint = _task_review_fingerprint(repo, manifest)
    if not bool(manifest.get("review_required", int(manifest.get("schema") or 2) < 3)):
        return fingerprint
    review = manifest.get("review") or {}
    verdict = _text(review.get("verdict"))
    if verdict not in {"approved", "runtime-bypassed"}:
        raise APError(
            "Task review must be approved or carry an explicit runtime bypass before commit-push or integration."
        )
    if _text(review.get("diff_fingerprint")) != fingerprint:
        raise APError("Approved review fingerprint is stale for the current owned diff.")
    if _text(review.get("diff_base")) != _text(manifest.get("base_sha")):
        raise APError("Approved review base is stale for the current task base.")
    assignment_path = _text(review.get("assignment_path"))
    if not assignment_path:
        raise APError("Approved review has no immutable diff assignment.")
    expected_assignment_path = _review_assignment_path(
        repo,
        _text(manifest.get("task_id")),
        fingerprint,
    ).resolve()
    if Path(assignment_path).resolve() != expected_assignment_path:
        raise APError("Approved review assignment path does not match Git-local task state.")
    assignment = _load_bound_review_assignment(
        repo,
        manifest,
        expected_assignment_path,
    )
    for field in ("diff_artifact_path", "diff_artifact_sha256", "diff_artifact_format"):
        if assignment.get(field) != review.get(field):
            raise APError(f"Approved review {field} binding does not match its assignment.")
    _validate_review_diff_artifact(repo, assignment)
    if verdict == "runtime-bypassed":
        _validate_review_runtime_override(repo, manifest, fingerprint)
    return fingerprint


def _reconcile_task_risk(repo: Path, cfg: dict, manifest: dict) -> None:
    changed_paths = _task_changed_paths_from_base(repo, _text(manifest.get("base_sha")))
    plan = _resolve_execution_plan(
        cfg,
        repo,
        changed_paths=changed_paths,
        planned_paths=list(manifest.get("owned_paths") or []),
        requested_task_kind="change",
    )
    old_profile = _text(manifest.get("effective_profile")) or (
        "high-risk" if bool(manifest.get("review_required")) else "standard"
    )
    planned_profile = _text(plan.get("profile")) or "standard"
    effective_profile = (
        planned_profile
        if _PROFILE_RANK[planned_profile] > _PROFILE_RANK[old_profile]
        else old_profile
    )
    review_required = bool(manifest.get("review_required") or plan.get("review_required"))
    design_required = bool(manifest.get("design_required") or plan.get("design_required"))
    review_depth, review_timeout_seconds = _normalized_task_review_policy(
        review_required,
        manifest.get("review_depth"),
        plan.get("review_depth"),
    )
    escalated = (
        effective_profile != old_profile
        or review_required != bool(manifest.get("review_required"))
        or design_required != bool(manifest.get("design_required"))
        or review_depth != (_text(manifest.get("review_depth")) or "none")
        or review_timeout_seconds != int(manifest.get("review_timeout_seconds") or 0)
    )
    if not escalated:
        return
    manifest["effective_profile"] = effective_profile
    manifest["review_required"] = review_required
    manifest["design_required"] = design_required
    manifest["review_depth"] = review_depth
    manifest["review_timeout_seconds"] = review_timeout_seconds
    _invalidate_task_review(manifest, "actual changed paths raised task risk; review again")
    _clear_final_gate_receipt(repo)
    _save_task_manifest(repo, manifest)
    raise APError(
        "Actual changed paths raised task risk. Complete any necessary design/review and retry "
        f"commit-push: profile={effective_profile}, review_required={str(review_required).lower()}."
    )


def _unstaged_task_paths(repo: Path) -> list[str]:
    paths = set(
        _checked_git_z_paths(
            repo,
            ["git", "diff", "--no-renames", "--name-only", "-z", "--diff-filter=ACDMRTUXB"],
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
            "This checkout has no active task. "
            f"Run `python3 docs/tools/autopipeline/ap.py task-start {task_id}` from the main checkout, "
            "then continue in the current checkout or returned worktree."
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
    for field in (
        "task_id",
        "task_uuid",
        "task_branch",
        "worktree_path",
        "base_sha",
        "scope_revision",
    ):
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
    common_dir = _git_common_dir(repo).resolve()
    state_root = common_dir / "auto-coding-skill"
    lock_root = state_root / "locks"
    _guard_review_directory(state_root, common_dir, create=True)
    _guard_review_directory(lock_root, common_dir, create=True)
    lock_path = lock_root / f"{safe_name}.lock"
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
_TASK_KINDS = {"none", "read_only", "change", "terminal_maintenance"}
_REQUESTED_TASK_KINDS = (_TASK_KINDS - {"none"}) | {"auto"}
_PROFILE_GATE_SCOPE = {"micro": "changed", "standard": "changed", "high-risk": "changed"}
_PROFILE_RANK = {"micro": 0, "standard": 1, "high-risk": 2}
_SCOPE_RANK = {"changed": 0, "standard": 1, "full": 2}
_DOC_PATH_PATTERNS = ["*.md", "docs/**"]
_DEFAULT_FULL_PATH_PATTERNS = [
    ".agents/**",
    "AGENTS.md",
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
    _PROJECT_CONFIG_RELATIVE.as_posix(),
    "docs/tools/autopipeline/**",
    "package.json",
    "**/package.json",
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
    gate_cfg = cfg.get("gate")
    if gate_cfg is None:
        return {}
    if not isinstance(gate_cfg, dict):
        raise APError("gate must be a mapping")
    return gate_cfg


def _risk_cfg(cfg: dict) -> dict:
    value = cfg.get("risk")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise APError("risk must be a mapping")
    return value


def _validation_cfg(cfg: dict) -> dict:
    value = cfg.get("validation")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise APError("validation must be a mapping")
    return value


def _positive_seconds(value: object, default: float, label: str) -> float:
    if value in {None, ""}:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise APError(f"{label} must be a positive number") from exc
    if parsed <= 0:
        raise APError(f"{label} must be a positive number")
    return parsed


def _final_gate_budget(cfg: dict) -> dict[str, float]:
    validation_cfg = _validation_cfg(cfg)
    command_seconds = _positive_seconds(
        validation_cfg.get("max_command_seconds"),
        _RECOMMENDED_FINAL_COMMAND_SECONDS,
        "validation.max_command_seconds",
    )
    total_seconds = _positive_seconds(
        validation_cfg.get("max_total_seconds"),
        _RECOMMENDED_FINAL_TOTAL_SECONDS,
        "validation.max_total_seconds",
    )
    if command_seconds > total_seconds:
        raise APError("validation.max_command_seconds cannot exceed validation.max_total_seconds")
    return {"command_seconds": command_seconds, "total_seconds": total_seconds}


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


def _run_configured_command_list(
    repo: Path,
    cfg: dict,
    names: list,
    *,
    deadline: Optional[float] = None,
    command_timeout_s: Optional[float] = None,
    command_timeouts: Optional[dict[str, float]] = None,
) -> list[str]:
    executed: list[str] = []
    missing: list[str] = []
    for name_ref in names:
        name = _command_name(name_ref)
        if not name:
            continue
        if _configured_command(cfg, name):
            timeout_s = command_timeout_s
            route_timeout = (command_timeouts or {}).get(name)
            if route_timeout is not None:
                timeout_s = min(timeout_s, route_timeout) if timeout_s is not None else route_timeout
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise APError(
                        "Final changed-scope gate timed out: exceeded its total time budget before "
                        f"commands.{name}; narrow validation.routes"
                    )
                timeout_s = min(timeout_s, remaining) if timeout_s is not None else remaining
            _run_configured_command(repo, cfg, name, timeout_s=timeout_s)
            executed.append(name)
        else:
            missing.append(name)
    if missing:
        raise APError("Validation route references missing commands: " + ", ".join(missing))
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


def _effective_change_base(repo: Path, base_ref: str = "") -> str:
    manifest = _active_task_manifest(repo)
    return base_ref or (_text(manifest.get("base_sha")) if manifest else "") or _default_base_ref(repo)


def _changed_files(repo: Path, base_ref: str = "") -> list[str]:
    paths: list[str] = []
    effective_base = _effective_change_base(repo, base_ref)
    if effective_base:
        paths.extend(_git_lines(repo, ["git", "diff", "--no-renames", "--name-only", "--diff-filter=ACDMRTUXB", f"{effective_base}...HEAD"]))
    paths.extend(_git_lines(repo, ["git", "diff", "--no-renames", "--name-only", "--diff-filter=ACDMRTUXB"]))
    paths.extend(_git_lines(repo, ["git", "diff", "--cached", "--no-renames", "--name-only", "--diff-filter=ACDMRTUXB"]))
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
            "--no-renames",
            "--name-only",
            "-r",
            "--diff-filter=ACDMRTUXB",
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
    return bool(paths) and all(
        path not in _EFFECTIVE_CONFIG_PATHS
        and _path_matches(path, _DOC_PATH_PATTERNS)
        for path in paths
    )


def _tests_only(paths: list[str]) -> bool:
    non_docs = [path for path in paths if not _path_matches(path, _DOC_PATH_PATTERNS)]
    if not non_docs:
        return False
    return all(
        re.search(r"(^|[/_.-])(test|tests|spec|specs)([/_.-]|$)", path.lower())
        for path in non_docs
    )


def _gate_rules(gate_cfg: dict) -> list[dict]:
    rules = gate_cfg.get("rules", [])
    if not isinstance(rules, list):
        raise APError("gate.rules must be a list")
    validated: list[dict] = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise APError(f"gate.rules[{index}] must be a mapping")
        profile = _text(rule.get("profile")).lower()
        if profile and profile not in _WORKFLOW_PROFILES - {"auto"}:
            raise APError(
                f"gate.rules[{index}].profile must be micro, standard, or high-risk"
            )
        if "scope" in rule:
            raise APError(
                f"gate.rules[{index}].scope is legacy automatic gate escalation; run autocoding init"
            )
        if "commands" in rule:
            raise APError(
                f"gate.rules[{index}].commands is legacy automatic gate escalation; run autocoding init"
            )
        validated.append(rule)
    return validated


def _risk_rules(cfg: dict) -> list[dict]:
    rules = _risk_cfg(cfg).get("rules", [])
    if not isinstance(rules, list):
        raise APError("risk.rules must be a list")
    current: list[dict] = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise APError(f"risk.rules[{index}] must be a mapping")
        if not _as_list(rule.get("paths")):
            raise APError(f"risk.rules[{index}].paths must not be empty")
        profile = _text(rule.get("profile")).lower()
        if profile and profile not in _WORKFLOW_PROFILES - {"auto"}:
            raise APError(
                f"risk.rules[{index}].profile must be micro, standard, or high-risk"
            )
        current.append(rule)
    # Keep reading 3.x gate.rules while projects migrate.  They remain planning
    # metadata only and never execute validation commands.
    return current or _gate_rules(_gate_cfg(cfg))


def _matching_gate_rules(paths: list[str], gate_cfg: dict) -> list[dict]:
    matches = []
    for rule in _gate_rules(gate_cfg):
        patterns = _as_list(rule.get("paths"))
        if patterns and any(_path_matches(path, patterns) for path in paths):
            matches.append(rule)
    return matches


def _matching_risk_rules(paths: list[str], cfg: dict) -> list[dict]:
    matches: list[dict] = []
    for rule in _risk_rules(cfg):
        patterns = _as_list(rule.get("paths"))
        if patterns and any(_path_matches(path, patterns) for path in paths):
            matches.append(rule)
    return matches


def _validation_routes(cfg: dict) -> list[dict]:
    routes = _validation_cfg(cfg).get("routes", [])
    if not isinstance(routes, list):
        raise APError("validation.routes must be a list")
    validated: list[dict] = []
    for index, route in enumerate(routes):
        if not isinstance(route, dict):
            raise APError(f"validation.routes[{index}] must be a mapping")
        if not _as_list(route.get("paths")):
            raise APError(f"validation.routes[{index}].paths must not be empty")
        if not [_command_name(item) for item in _as_list(route.get("commands"))]:
            raise APError(f"validation.routes[{index}].commands must not be empty")
        validated.append(route)
    return validated


def _validation_route_matches(path: str, route: dict) -> bool:
    patterns = _as_list(route.get("paths"))
    excludes = _as_list(route.get("exclude"))
    return bool(patterns) and _path_matches(path, patterns) and not _path_matches(path, excludes)


def _validation_plan(cfg: dict, paths: list[str]) -> dict:
    """Resolve one deterministic changed-scope validation plan.

    Risk rules deliberately live under ``risk.rules``.  Validation routes are a
    separate execution surface so classification cannot silently turn into an
    expensive full gate and a documentation check cannot masquerade as code
    validation.
    """
    normalized = _unique_paths(paths)
    routes = _validation_routes(cfg)
    command_names: list[str] = []
    command_timeouts: dict[str, float] = {}
    matched_routes: list[str] = []
    builtins: list[str] = []
    coverage: dict[str, list[str]] = {}
    unmapped: list[str] = []

    for path in normalized:
        names: list[str] = []
        if path in _EFFECTIVE_CONFIG_PATHS:
            builtin_name = "effective-config"
            names.append(builtin_name)
            if builtin_name not in builtins:
                builtins.append(builtin_name)
            if builtin_name not in matched_routes:
                matched_routes.append(builtin_name)
        for index, route in enumerate(routes):
            if not _validation_route_matches(path, route):
                continue
            route_name = _text(route.get("name")) or f"route-{index + 1}"
            route_timeout: Optional[float] = None
            if route.get("timeout_seconds") not in {None, ""}:
                route_timeout = _positive_seconds(
                    route.get("timeout_seconds"),
                    1.0,
                    f"validation.routes[{index}].timeout_seconds",
                )
            names.append(route_name)
            if route_name not in matched_routes:
                matched_routes.append(route_name)
            for command_ref in _as_list(route.get("commands")):
                command_name = _command_name(command_ref)
                if command_name and command_name not in command_names:
                    command_names.append(command_name)
                if command_name and route_timeout is not None:
                    current_timeout = command_timeouts.get(command_name)
                    command_timeouts[command_name] = (
                        min(current_timeout, route_timeout)
                        if current_timeout is not None
                        else route_timeout
                    )
        coverage[path] = names
        if not names and not _path_matches(path, _DOC_PATH_PATTERNS):
            unmapped.append(path)

    validation_cfg = _validation_cfg(cfg)
    compatibility_command = ""
    project_validation_paths = [
        path
        for path in normalized
        if path not in _EFFECTIVE_CONFIG_PATHS
        and not _path_matches(path, _DOC_PATH_PATTERNS)
    ]
    if not routes and project_validation_paths:
        compatibility_command = _command_name(validation_cfg.get("fallback_command"))
        if not compatibility_command and _configured_command(cfg, "gate_changed"):
            compatibility_command = "gate_changed"
        if compatibility_command:
            command_names.append(compatibility_command)
            matched_routes.append("3.x-compatibility-fallback")
            unmapped = []

    on_unmapped = _text(validation_cfg.get("on_unmapped")).lower() or "error"
    if on_unmapped not in {"error", "fallback"}:
        raise APError("validation.on_unmapped must be error or fallback")
    if unmapped and on_unmapped == "fallback":
        fallback = _command_name(validation_cfg.get("fallback_command"))
        if fallback and fallback not in command_names:
            command_names.append(fallback)
            matched_routes.append("unmapped-fallback")
            unmapped = []

    return {
        "paths": normalized,
        "commands": command_names,
        "command_timeouts": command_timeouts,
        "matched_routes": matched_routes,
        "builtins": builtins,
        "coverage": coverage,
        "unmapped": unmapped,
        "docs_only": _docs_only(normalized),
        "compatibility_fallback": compatibility_command,
    }


def _validate_validation_plan(cfg: dict, plan: dict) -> None:
    missing = [name for name in plan["commands"] if not _configured_command(cfg, name)]
    if missing:
        raise APError("Validation route references missing commands: " + ", ".join(missing))
    if plan["unmapped"]:
        raise APError(
            "Changed code paths have no validation route:\n- "
            + "\n- ".join(plan["unmapped"])
            + "\nAdd validation.routes entries in docs/project/auto-coding-skill.yaml."
        )
    if plan["paths"] and not plan["docs_only"] and not plan["commands"] and not plan["builtins"]:
        raise APError(
            "Changed code has no fast validation command. Add validation.routes with project-native commands."
        )


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


def _select_structure_scope(
    cfg: dict,
    repo: Path,
    requested_scope: str,
    base_ref: str,
) -> str:
    """Keep repository-wide structure scans explicit while honoring them."""
    requested = _text(requested_scope).lower()
    if requested == "full":
        return "full"
    impact = _impact_summary(
        cfg,
        repo,
        requested_scope=requested,
        base_ref=base_ref,
    )
    return str(impact["selected_scope"])


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
    scope, reasons, _ = _select_gate_scope(cfg, requested_scope, paths)
    matching_rules = _matching_risk_rules(paths, cfg)
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


def _run_changed_gate(
    repo: Path,
    cfg: dict,
    paths: list[str],
    *,
    deadline: Optional[float] = None,
    command_timeout_s: Optional[float] = None,
) -> list[str]:
    contract = cmd_doctor(
        argparse.Namespace(repo=str(repo), collect=True, quiet=True, record=False)
    )
    if contract["issues"]:
        raise APError(
            "Effective project configuration contract is invalid:\n- "
            + "\n- ".join(contract["issues"])
        )
    plan = _validation_plan(cfg, paths)
    _validate_validation_plan(cfg, plan)
    if not paths:
        print("[validation] no changed files; no project command needed")
        return ["no_changes"]
    if plan["docs_only"] and not plan["commands"]:
        print("[validation] docs-only change; built-in diff check is sufficient")
        return ["docs_only_builtin"]
    if plan["compatibility_fallback"]:
        print(
            "[validation] WARN: using 3.x compatibility fallback; migrate to validation.routes",
            file=sys.stderr,
        )
    executed = list(plan["builtins"])
    if plan["builtins"]:
        print("[validation] effective project configuration contract is valid")
    executed.extend(_run_configured_command_list(
        repo,
        cfg,
        plan["commands"],
        deadline=deadline,
        command_timeout_s=command_timeout_s,
        command_timeouts=plan["command_timeouts"],
    ))
    print(
        "[validation] routes="
        + (", ".join(plan["matched_routes"]) or "(none)")
        + " commands="
        + (", ".join(executed) or "(none)")
    )
    return executed


def cmd_validation_map_check(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    explicit_paths = list(getattr(args, "path", []) or [])
    if explicit_paths:
        paths = _unique_paths(explicit_paths)
    elif bool(getattr(args, "tracked", False)):
        paths = _tracked_files(repo)
    else:
        paths = _changed_files(repo, _text(getattr(args, "base", "")))
    plan = _validation_plan(cfg, paths)
    _validate_validation_plan(cfg, plan)
    result = {
        "paths": plan["paths"],
        "commands": plan["commands"],
        "command_timeouts": plan["command_timeouts"],
        "matched_routes": plan["matched_routes"],
        "builtins": plan["builtins"],
        "coverage": plan["coverage"],
        "docs_only": plan["docs_only"],
    }
    if bool(getattr(args, "json", False)):
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(
        f"[validation-map] OK paths={len(plan['paths'])} "
        f"routes={len(plan['matched_routes'])} commands={len(plan['commands'])}"
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
    ".agents/archive/**",
    ".agents/agents/**",
    ".agents/managed-install.json",
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
    r"^\s*(?:export\s+)?(?:async\s+)?(?:def|function)\s+[A-Za-z_][\w]*\b"
    r"|^\s*func\s+(?:\([^)]*\)\s*)?[A-Za-z_][\w]*\b"
    r"|^\s*(?:public|private|protected|static|final|async|\s)+\s*[\w<>\[\], ?]+\s+[A-Za-z_]\w*\s*\([^;]*\)\s*\{"
    r"|^\s*(?:export\s+)?(?:const|let|var)\s+[A-Za-z_]\w*\s*=\s*(?:async\s+)?"
    r"(?:\([^)]*\)|[A-Za-z_]\w*)\s*(?::\s*[^=]+)?=>"
)
_ARROW_DECLARATION_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+[A-Za-z_]\w*\s*=\s*(?:async\s+)?"
)
_ARROW_FUNCTION_BODY_RE = re.compile(r"=>\s*(?::\s*[^=]+)?\{")
_IMPORT_PATTERNS = [
    re.compile(r"^\s*import\s+(?:.+?\s+from\s+)?[\"']([^\"']+)[\"']"),
    re.compile(r"\brequire\(\s*[\"']([^\"']+)[\"']\s*\)"),
    re.compile(r"\bimport\(\s*[\"']([^\"']+)[\"']\s*\)"),
    re.compile(r"^\s*from\s+([A-Za-z_][\w.]*)\s+import\b"),
    re.compile(
        r"^\s*import\s+(?:static\s+)?"
        r"([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\.\*)?)"
        r"(?:\s+as\s+[A-Za-z_]\w*)?\s*;?\s*"
        r"(?://.*|/\*.*)?$"
    ),
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
    value = cfg.get("structure")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise APError("structure must be a mapping")
    return value


def _optimization_cfg(cfg: dict) -> dict:
    value = cfg.get("optimization")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise APError("optimization must be a mapping")
    return value


def _verification_cfg(cfg: dict) -> dict:
    value = cfg.get("verification")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise APError("verification must be a mapping")
    return value


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
        paths = _unique_paths(
            _tracked_files(repo)
            + _git_lines(repo, ["git", "ls-files", "--others", "--exclude-standard"])
        )
    else:
        paths = _changed_files(repo, base_ref=base_ref)
    return [
        path
        for path in paths
        if (repo / path).is_file() and _is_structure_candidate(path, structure_cfg)
    ]


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


def _ensure_structure_deadline(deadline: Optional[float]) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise APError("Final changed-scope gate timed out during structure check.")


_JSX_TAG_RE = re.compile(r"</?>|</?[A-Za-z_$][A-Za-z0-9_.$:-]*(?:\s[^<>]*?)?/?>")
_JSX_NONCODE_RE = re.compile(
    r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|//.*|/\*.*?\*/'''
)


def _mask_jsx_noncode(text: str) -> str:
    masked = list(_JSX_NONCODE_RE.sub(lambda match: " " * len(match.group(0)), text))
    for index, char in enumerate(masked):
        if char != "/":
            continue
        prefix = "".join(masked[:index]).rstrip()
        regex_context = prefix.endswith(("=", "(", "[", "{", ",", ":", ";", "!", "?")) or bool(
            re.search(r"\b(?:return|case|throw|yield)\s*$", prefix)
        )
        if not regex_context:
            continue
        terminator = _regex_line_terminator(text, index)
        if terminator is None:
            continue
        suffix = terminator + 1
        while suffix < len(text) and text[suffix] in "dgimsuvy":
            suffix += 1
        masked[index:suffix] = " " * (suffix - index)
    return "".join(masked)


def _jsx_prefix_has_open_tag(text: str) -> bool:
    masked = _mask_jsx_noncode(text)
    depth = 0
    expression_depth = 0
    cursor = 0
    for match in _JSX_TAG_RE.finditer(masked):
        for char in masked[cursor:match.start()]:
            if depth <= 0:
                continue
            if char == "{":
                expression_depth += 1
            elif char == "}" and expression_depth > 0:
                expression_depth -= 1
        token = match.group(0)
        if token.startswith("</"):
            depth = max(0, depth - 1)
        elif token != "</>" and not token.endswith("/>"):
            previous = masked[:match.start()].rstrip()
            following = masked[match.end():].lstrip()
            if (
                previous
                and (previous[-1].isalnum() or previous[-1] in {"_", "$"})
                and (
                    depth == 0
                    or expression_depth > 0
                    or following.startswith(("(", ".", "?."))
                )
            ):
                cursor = match.end()
                continue
            depth += 1
        if depth == 0:
            expression_depth = 0
        cursor = match.end()
    return depth > 0


def _regex_line_terminator(line: str, index: int) -> Optional[int]:
    escaped = False
    char_class = False
    for char_index in range(index + 1, len(line)):
        char = line[char_index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "[":
            char_class = True
        elif char == "]":
            char_class = False
        elif char == "/" and not char_class:
            suffix_index = char_index + 1
            while suffix_index < len(line) and line[suffix_index] in "dgimsuvy":
                suffix_index += 1
            if suffix_index < len(line) and (
                line[suffix_index].isalnum() or line[suffix_index] in {"_", "$"}
            ):
                return None
            token_index = suffix_index
            while token_index < len(line) and line[token_index].isspace():
                token_index += 1
            if token_index < len(line) and (
                line[token_index].isalnum() or line[token_index] in {"_", "$"}
            ):
                token = re.match(r"[A-Za-z_$][A-Za-z0-9_$]*", line[token_index:])
                if token is None or token.group(0) not in {"as", "in", "instanceof", "satisfies"}:
                    return None
            return char_index
    return None


def _looks_like_regex_start(line: str, index: int) -> bool:
    prefix = line[:index].rstrip()
    next_char = line[index + 1] if index + 1 < len(line) else ""
    terminator = _regex_line_terminator(line, index)
    if terminator is None:
        return False
    closing_tag = re.match(r"/[A-Za-z_$][A-Za-z0-9_.$:-]*\s*>", line[index:])
    keyword_context = bool(re.search(r"\b(?:return|case|throw|yield)\s*$", prefix))
    operator_context = prefix.endswith(("=", "(", "[", "{", ",", ":", ";", "!", "?", "<", ">", "=>"))
    if prefix.endswith("<") and closing_tag:
        before_less_than = prefix[:-1].rstrip()
        operand_context = bool(re.search(r"(?:[A-Za-z0-9_$\]\)}'\"`]|\+\+|--)$", before_less_than))
        tag_end = index + closing_tag.end()
        between = line[tag_end:terminator]
        terminator_next = line[terminator + 1] if terminator + 1 < len(line) else ""
        if (
            _jsx_prefix_has_open_tag(before_less_than)
            or not operand_context
            or (between and not between.strip())
            or terminator_next in {"/", "*"}
        ):
            return False
    if next_char == ">":
        if not prefix:
            return False
        if prefix.endswith("<"):
            before_less_than = prefix[:-1].rstrip()
            if not re.search(r"(?:[A-Za-z0-9_$\]\)}'\"`]|\+\+|--)$", before_less_than):
                return False
        elif not (operator_context or keyword_context):
            return False
    if not prefix or operator_context:
        return True
    return keyword_context


def _python_function_end(
    lines: list[str],
    start: int,
    threshold: int,
    deadline: Optional[float],
) -> tuple[int, bool]:
    """Best-effort range for temporarily invalid Python during an edit."""
    indent = len(lines[start]) - len(lines[start].lstrip())
    limit = min(len(lines), start + threshold + 1)
    body_start: Optional[int] = None
    for index in range(start, limit):
        if (index - start) % 32 == 0:
            _ensure_structure_deadline(deadline)
        header = re.search(r"\)\s*(?:->\s*.*?)?\s*:", lines[index])
        if not header:
            continue
        tail = lines[index][header.end() :].strip()
        if tail and not tail.startswith("#"):
            return index + 1, False
        body_start = index + 1
        break
    if body_start is None:
        return limit, limit < len(lines)

    end = body_start
    for index in range(body_start, limit):
        if (index - body_start) % 32 == 0:
            _ensure_structure_deadline(deadline)
        stripped = lines[index].strip()
        if not stripped or stripped.startswith("#"):
            continue
        current_indent = len(lines[index]) - len(lines[index].lstrip())
        if current_indent <= indent:
            return end, False
        end = index + 1
    return limit if limit < len(lines) else end, limit < len(lines)


def _python_function_ranges(
    lines: list[str],
    threshold: int,
    deadline: Optional[float],
) -> list[tuple[int, int, bool]]:
    _ensure_structure_deadline(deadline)
    try:
        tree = ast.parse("\n".join(lines))
    except (SyntaxError, ValueError):
        ranges = []
        for start, line in enumerate(lines):
            if not re.match(r"^\s*(?:async\s+)?def\s+[A-Za-z_]\w*\b", line):
                continue
            end, truncated = _python_function_end(lines, start, threshold, deadline)
            ranges.append((start, end, truncated))
        return ranges

    _ensure_structure_deadline(deadline)
    ranges = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = max(0, int(node.lineno) - 1)
        end = int(getattr(node, "end_lineno", 0) or node.lineno)
        ranges.append((start, end, False))
    return sorted(ranges)


def _find_arrow_locations(
    lines: list[str],
    start: int,
    deadline: Optional[float],
) -> list[tuple[int, int]]:
    """Find a declaration's top-level arrow candidates with exact columns."""
    state = "code"
    escaped = False
    regex_char_class = False
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    angle_depth = 0
    locations: list[tuple[int, int]] = []
    indent = len(lines[start]) - len(lines[start].lstrip())
    limit = min(len(lines), start + 200)
    equals = lines[start].find("=")
    for line_index in range(start, limit):
        if (line_index - start) % 32 == 0:
            _ensure_structure_deadline(deadline)
        line = lines[line_index]
        if line_index > start:
            stripped = line.strip()
            current_indent = len(line) - len(line.lstrip())
            if stripped and current_indent <= indent and not (
                paren_depth or bracket_depth or brace_depth or angle_depth
            ):
                return locations
        char_index = equals + 1 if line_index == start and equals >= 0 else 0
        while char_index < len(line):
            char = line[char_index]
            next_char = line[char_index + 1] if char_index + 1 < len(line) else ""
            if state == "block_comment":
                if char == "*" and next_char == "/":
                    state = "code"
                    char_index += 2
                    continue
                char_index += 1
                continue
            if state == "regex":
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == "[":
                    regex_char_class = True
                elif char == "]":
                    regex_char_class = False
                elif char == "/" and not regex_char_class:
                    state = "code"
                char_index += 1
                continue
            if state in {"single_quote", "double_quote", "backtick"}:
                quote = {"single_quote": "'", "double_quote": '"', "backtick": "`"}[state]
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    state = "code"
                char_index += 1
                continue
            if char == "/" and next_char == "/":
                break
            if char == "/" and next_char == "*":
                state = "block_comment"
                char_index += 2
                continue
            if char == "/" and _looks_like_regex_start(line, char_index):
                state = "regex"
                regex_char_class = False
                escaped = False
                char_index += 1
                continue
            if char in {"'", '"', "`"}:
                state = {"'": "single_quote", '"': "double_quote", "`": "backtick"}[char]
                escaped = False
            elif char == "(":
                paren_depth += 1
            elif char == ")":
                paren_depth = max(0, paren_depth - 1)
            elif char == "[":
                bracket_depth += 1
            elif char == "]":
                bracket_depth = max(0, bracket_depth - 1)
            elif char == "<" and not (paren_depth or bracket_depth or brace_depth):
                angle_depth += 1
            elif char == ">" and angle_depth and not (paren_depth or bracket_depth or brace_depth):
                angle_depth -= 1
            elif char == "{":
                brace_depth += 1
            elif char == "}":
                brace_depth = max(0, brace_depth - 1)
            elif char == "=" and next_char == ">":
                if not (paren_depth or bracket_depth or brace_depth or angle_depth):
                    locations.append((line_index, char_index))
                char_index += 2
                continue
            elif char == ";" and not (paren_depth or bracket_depth or brace_depth or angle_depth):
                return locations
            char_index += 1
        if line_index > start:
            stripped = line.strip()
            current_indent = len(line) - len(line.lstrip())
            if stripped and current_indent <= indent and not (paren_depth or bracket_depth or brace_depth or angle_depth):
                return locations
    return locations


def _arrow_body_kind(lines: list[str], arrow_location: tuple[int, int]) -> str:
    arrow_line, arrow_column = arrow_location
    for line_index in range(arrow_line, min(len(lines), arrow_line + 20)):
        text = lines[line_index][arrow_column + 2 :] if line_index == arrow_line else lines[line_index]
        stripped = text.strip()
        if not stripped or stripped.startswith(("//", "/*", "*")):
            continue
        return "block" if stripped.startswith("{") else "expression"
    return "expression"


def _looks_like_return_type_brace(line: str, index: int) -> bool:
    prefix = line[:index].rstrip()
    return bool(re.search(r"\b(?:struct|interface)\s*$", prefix))


def _brace_function_end(
    lines: list[str],
    start: int,
    threshold: int,
    deadline: Optional[float],
    arrow_location: Optional[tuple[int, int]] = None,
    suffix: str = "",
) -> Optional[tuple[int, bool]]:
    depth = 0
    opened = False
    state = "code"
    escaped = False
    regex_char_class = False
    paren_depth = 0
    bracket_depth = 0
    type_brace_depth = 0
    arrow_seen = arrow_location is None
    typescript_declaration = arrow_location is None and suffix in {".ts", ".tsx"}
    ts_phase = "before_params"
    ts_pre_angle_depth = ts_pre_brace_depth = 0
    ts_type_angle_depth = ts_type_paren_depth = ts_type_bracket_depth = 0
    ts_type_brace_depth = 0
    ts_type_expects_operand = True
    limit = min(len(lines), start + threshold + 1)

    for line_index in range(start, limit):
        if (line_index - start) % 32 == 0:
            _ensure_structure_deadline(deadline)
        line = lines[line_index]
        char_index = 0
        while char_index < len(line):
            char = line[char_index]
            next_char = line[char_index + 1] if char_index + 1 < len(line) else ""

            if state == "block_comment":
                if char == "*" and next_char == "/":
                    state = "code"
                    char_index += 2
                    continue
                char_index += 1
                continue
            if state == "regex":
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == "[":
                    regex_char_class = True
                elif char == "]":
                    regex_char_class = False
                elif char == "/" and not regex_char_class:
                    state = "code"
                char_index += 1
                continue
            if state in {"single_quote", "double_quote"}:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif (state == "single_quote" and char == "'") or (
                    state == "double_quote" and char == '"'
                ):
                    state = "code"
                char_index += 1
                continue
            if state == "backtick":
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == "`":
                    state = "code"
                char_index += 1
                continue

            if char == "/" and next_char == "/":
                break
            if char == "/" and next_char == "*":
                state = "block_comment"
                char_index += 2
                continue
            if char == "/" and _looks_like_regex_start(line, char_index):
                state = "regex"
                regex_char_class = False
                escaped = False
                char_index += 1
                continue
            if char == "=" and next_char == ">":
                if arrow_location == (line_index, char_index):
                    arrow_seen = True
                if typescript_declaration and ts_phase == "return_type":
                    ts_type_expects_operand = True
                char_index += 2
                continue
            if typescript_declaration and not opened:
                if char in {"'", '"', "`"}:
                    state = {"'": "single_quote", '"': "double_quote", "`": "backtick"}[char]
                    escaped = False
                    if ts_phase == "return_type":
                        ts_type_expects_operand = False
                    char_index += 1
                    continue
                if ts_phase == "before_params":
                    if ts_pre_brace_depth > 0:
                        if char == "{":
                            ts_pre_brace_depth += 1
                        elif char == "}":
                            ts_pre_brace_depth -= 1
                    elif char == "<":
                        ts_pre_angle_depth += 1
                    elif char == ">":
                        ts_pre_angle_depth = max(0, ts_pre_angle_depth - 1)
                    elif char == "{":
                        ts_pre_brace_depth = 1
                    elif char == "(" and ts_pre_angle_depth == 0:
                        ts_phase = "params"
                        paren_depth = 1
                elif ts_phase == "params":
                    if char == "(":
                        paren_depth += 1
                    elif char == ")":
                        paren_depth = max(0, paren_depth - 1)
                        if paren_depth == 0:
                            ts_phase = "after_params"
                elif ts_phase == "after_params":
                    if char == ":":
                        ts_phase = "return_type"
                        ts_type_expects_operand = True
                    elif char == "{":
                        opened = True
                        depth = 1
                    elif char == ";":
                        return None
                elif ts_type_brace_depth > 0:
                    if char == "{":
                        ts_type_brace_depth += 1
                    elif char == "}":
                        ts_type_brace_depth -= 1
                        if ts_type_brace_depth == 0:
                            ts_type_expects_operand = False
                elif char == "{":
                    if (
                        ts_type_angle_depth
                        or ts_type_paren_depth
                        or ts_type_bracket_depth
                        or ts_type_expects_operand
                    ):
                        ts_type_brace_depth = 1
                        ts_type_expects_operand = False
                    else:
                        opened = True
                        depth = 1
                elif char == "<":
                    ts_type_angle_depth += 1
                    ts_type_expects_operand = True
                elif char == ">":
                    ts_type_angle_depth = max(0, ts_type_angle_depth - 1)
                    ts_type_expects_operand = False
                elif char == "(":
                    ts_type_paren_depth += 1
                    ts_type_expects_operand = True
                elif char == ")":
                    ts_type_paren_depth = max(0, ts_type_paren_depth - 1)
                    ts_type_expects_operand = False
                elif char == "[":
                    ts_type_bracket_depth += 1
                    ts_type_expects_operand = True
                elif char == "]":
                    ts_type_bracket_depth = max(0, ts_type_bracket_depth - 1)
                    ts_type_expects_operand = False
                elif char in "|&?:,.=":
                    ts_type_expects_operand = True
                elif char.isalpha() or char in {"_", "$"}:
                    word_match = re.match(r"[A-Za-z_$][\w$]*", line[char_index:])
                    word = word_match.group(0) if word_match else char
                    ts_type_expects_operand = word in {
                        "abstract", "asserts", "extends", "in", "infer", "is",
                        "keyof", "new", "readonly", "typeof", "unique",
                    }
                    char_index += len(word)
                    continue
                elif char.isdigit():
                    ts_type_expects_operand = False
                elif char == ";" and not (
                    ts_type_angle_depth or ts_type_paren_depth or ts_type_bracket_depth
                ):
                    return None
                char_index += 1
                continue
            if char == "'":
                state = "single_quote"
                escaped = False
            elif char == '"':
                state = "double_quote"
                escaped = False
            elif char == "`":
                state = "backtick"
                escaped = False
            elif not opened and char == "(":
                paren_depth += 1
            elif not opened and char == ")":
                paren_depth = max(0, paren_depth - 1)
            elif not opened and char == "[":
                bracket_depth += 1
            elif not opened and char == "]":
                bracket_depth = max(0, bracket_depth - 1)
            elif char == "{":
                if not opened:
                    if not arrow_seen:
                        char_index += 1
                        continue
                    if arrow_location is None and (paren_depth > 0 or bracket_depth > 0):
                        char_index += 1
                        continue
                    if type_brace_depth > 0:
                        type_brace_depth += 1
                        char_index += 1
                        continue
                    if arrow_location is None and _looks_like_return_type_brace(line, char_index):
                        type_brace_depth = 1
                        char_index += 1
                        continue
                opened = True
                depth += 1
            elif char == "}" and not opened and type_brace_depth > 0:
                type_brace_depth -= 1
            elif char == "}" and opened:
                depth -= 1
                if depth == 0:
                    return line_index + 1, False
            char_index += 1
    if limit < len(lines):
        return limit, True
    return None


_EXPRESSION_CONTINUATION_SUFFIXES = (
    "?", ":", ".", ",", "+", "-", "*", "/", "%", "&&", "||", "??", "=>",
)
_EXPRESSION_CONTINUATION_PREFIXES = (
    ".", "?.", "+", "-", "*", "/", "%", "&&", "||", "??", "?", ":", ",",
)
def _expression_arrow_end(
    lines: list[str],
    start: int,
    arrow_location: tuple[int, int],
    threshold: int,
    deadline: Optional[float],
    suffix: str,
) -> tuple[int, bool]:
    indent = len(lines[start]) - len(lines[start].lstrip())
    limit = min(len(lines), start + threshold + 1)
    state = "code"
    escaped = False
    regex_char_class = False
    paren_depth = bracket_depth = brace_depth = 0
    jsx_mode = False
    jsx_depth = 0
    saw_jsx_tag = False
    arrow_line, arrow_column = arrow_location

    for line_index in range(arrow_line, limit):
        if (line_index - arrow_line) % 32 == 0:
            _ensure_structure_deadline(deadline)
        line = lines[line_index]
        char_index = arrow_column + 2 if line_index == arrow_line else 0
        visible: list[str] = []
        top_level_semicolon = False
        while char_index < len(line):
            char = line[char_index]
            next_char = line[char_index + 1] if char_index + 1 < len(line) else ""
            if state == "block_comment":
                if char == "*" and next_char == "/":
                    state = "code"
                    char_index += 2
                    continue
                char_index += 1
                continue
            if state == "regex":
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == "[":
                    regex_char_class = True
                elif char == "]":
                    regex_char_class = False
                elif char == "/" and not regex_char_class:
                    state = "code"
                char_index += 1
                continue
            if state in {"single_quote", "double_quote", "backtick"}:
                quote = {"single_quote": "'", "double_quote": '"', "backtick": "`"}[state]
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    state = "code"
                char_index += 1
                continue
            if char == "/" and next_char == "/":
                break
            if char == "/" and next_char == "*":
                state = "block_comment"
                char_index += 2
                continue
            jsx_token_slash = (
                suffix in {".jsx", ".tsx"}
                and jsx_mode
                and brace_depth == 0
                and (
                    next_char == ">"
                    or (char_index > 0 and line[char_index - 1] == "<")
                )
            )
            if char == "/" and not jsx_token_slash and _looks_like_regex_start(line, char_index):
                state = "regex"
                regex_char_class = False
                escaped = False
                visible.append(" ")
                char_index += 1
                continue
            if char in {"'", '"', "`"}:
                state = {"'": "single_quote", '"': "double_quote", "`": "backtick"}[char]
                escaped = False
                visible.append(" ")
            else:
                visible.append(char)
                if char == "(":
                    paren_depth += 1
                elif char == ")":
                    paren_depth = max(0, paren_depth - 1)
                elif char == "[":
                    bracket_depth += 1
                elif char == "]":
                    bracket_depth = max(0, bracket_depth - 1)
                elif char == "{":
                    brace_depth += 1
                elif char == "}":
                    brace_depth = max(0, brace_depth - 1)
                elif char == ";" and not (paren_depth or bracket_depth or brace_depth):
                    top_level_semicolon = True
            char_index += 1

        code = "".join(visible).strip()
        if suffix in {".jsx", ".tsx"} and not jsx_mode and code.startswith("<") and not code.startswith(("<=", "<<")):
            jsx_mode = True
        if jsx_mode:
            for match in _JSX_TAG_RE.finditer(code):
                token = match.group(0)
                saw_jsx_tag = True
                if token.startswith("</"):
                    jsx_depth = max(0, jsx_depth - 1)
                elif token not in {"</>"} and not token.endswith("/>"):
                    jsx_depth += 1

        if paren_depth or bracket_depth or brace_depth or jsx_depth > 0:
            continue
        if top_level_semicolon:
            return line_index + 1, False
        if jsx_mode and saw_jsx_tag:
            return line_index + 1, False

        next_index = line_index + 1
        while next_index < len(lines) and not lines[next_index].strip():
            next_index += 1
        if next_index >= len(lines):
            return line_index + 1, False
        next_text = lines[next_index].strip()
        next_indent = len(lines[next_index]) - len(lines[next_index].lstrip())
        if code.endswith(_EXPRESSION_CONTINUATION_SUFFIXES):
            continue
        if next_indent > indent:
            continue
        if next_text.startswith(_EXPRESSION_CONTINUATION_PREFIXES):
            continue
        if jsx_mode and next_text.startswith(("</", ">")):
            continue
        return line_index + 1, False

    return limit, limit < len(lines)


def _function_size_warnings(
    path: str,
    lines: list[str],
    threshold: int,
    deadline: Optional[float] = None,
) -> list[str]:
    if threshold <= 0:
        return []
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        ranges = _python_function_ranges(lines, threshold, deadline)
    else:
        candidates: dict[int, list[Optional[tuple[int, int]]]] = {}
        claimed_arrow_lines: set[int] = set()
        for index, line in enumerate(lines):
            if index % 256 == 0:
                _ensure_structure_deadline(deadline)
            if _ARROW_DECLARATION_RE.search(line):
                arrow_locations = _find_arrow_locations(lines, index, deadline)
                if arrow_locations:
                    candidates[index] = list(arrow_locations)
                    claimed_arrow_lines.update(location[0] for location in arrow_locations)
                    continue
            if Path(path).name == "Jenkinsfile":
                if re.match(r"^\s*def\s+[A-Za-z_]\w*\s*\(", line):
                    candidates[index] = [None]
            elif _FUNCTION_START_RE.search(line):
                candidates[index] = [None]
            elif index not in claimed_arrow_lines:
                arrow_matches = list(_ARROW_FUNCTION_BODY_RE.finditer(line))
                if arrow_matches:
                    candidates[index] = [(index, match.start()) for match in arrow_matches]

        ranges = []
        for start, arrow_locations in sorted(candidates.items()):
            _ensure_structure_deadline(deadline)
            candidate_ranges: list[tuple[int, bool]] = []
            for arrow_location in arrow_locations:
                if arrow_location is not None and _arrow_body_kind(lines, arrow_location) == "expression":
                    candidate_ranges.append(
                        _expression_arrow_end(
                            lines, start, arrow_location, threshold, deadline, suffix
                        )
                    )
                    continue
                result = _brace_function_end(
                    lines,
                    start,
                    threshold,
                    deadline,
                    arrow_location=arrow_location,
                    suffix=suffix,
                )
                if result is not None:
                    candidate_ranges.append(result)
            if candidate_ranges:
                end, truncated = max(candidate_ranges, key=lambda item: (item[0], item[1]))
                ranges.append((start, end, truncated))

    warnings: list[str] = []
    for start, end, truncated in ranges:
        size = end - start
        if size <= threshold:
            continue
        qualifier = "at least " if truncated else ""
        warnings.append(
            f"{path}:{start + 1} function-like block has {qualifier}{size} lines (warn>{threshold})"
        )
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
    base_ref = str(getattr(args, "base", "") or "")
    deadline = getattr(args, "deadline", None)
    selected_scope = _select_structure_scope(cfg, repo, requested_scope, base_ref)

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
    block_warnings = enforcement == "blocking" and _bool_config(
        structure_cfg.get("block_warnings"), False
    )
    layer_cfg = _layer_rules_config(structure_cfg)
    block_layer_violations = _bool_config(layer_cfg.get("block"), True)

    paths = _structure_paths_for_scope(repo, selected_scope, base_ref, structure_cfg)
    added_by_path = _added_lines_by_path(repo, base_ref=base_ref) if selected_scope != "full" else {}

    blocking: list[str] = []
    warnings: list[str] = []
    inspected = 0

    for path in paths:
        _ensure_structure_deadline(deadline)
        lines = _read_text_lines(repo, path)
        if lines is None:
            continue
        inspected += 1
        line_count = len(lines)
        accepted_debt = _is_structure_accepted_debt(path, structure_cfg)
        block_path_size_warnings = block_warnings and not accepted_debt
        if block_file_lines > 0 and line_count > block_file_lines:
            message = f"{path} has {line_count} lines (block>{block_file_lines}); split responsibilities before adding more work"
            if accepted_debt:
                warnings.append(message + " [accepted_debt_paths]")
            else:
                blocking.append(message)
        elif warn_file_lines > 0 and line_count > warn_file_lines:
            message = (
                f"{path} has {line_count} lines (warn>{warn_file_lines}); "
                "prefer extraction before extending it"
            )
            (blocking if block_path_size_warnings else warnings).append(message)

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

        function_warnings = _function_size_warnings(
            path,
            lines,
            warn_function_lines,
            deadline=deadline,
        )
        (blocking if block_path_size_warnings else warnings).extend(function_warnings)
        boundary_issues = _structure_boundary_issues(path, lines, structure_cfg)
        _ensure_structure_deadline(deadline)
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
        "block_warnings": block_warnings,
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


def _run_structure_check_for_gate(
    repo: Path,
    cfg: dict,
    selected_scope: str,
    base_ref: str,
    *,
    deadline: Optional[float] = None,
    command_timeout_s: Optional[float] = None,
) -> list[str]:
    if not _structure_gate_enabled(cfg):
        return []
    if _configured_command(cfg, "structure_check"):
        timeout_s = command_timeout_s
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise APError("Final changed-scope gate budget exhausted before structure check.")
            timeout_s = min(timeout_s, remaining) if timeout_s is not None else remaining
        _run_configured_command(repo, cfg, "structure_check", timeout_s=timeout_s)
        return ["structure_check"]
    cmd_structure_check(
        argparse.Namespace(
            repo=str(repo),
            scope=selected_scope,
            base=base_ref,
            json=False,
            deadline=deadline,
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
    overrides = json.loads(json.dumps(load_project_overrides(repo)))
    effective_structure = _mapping(cfg.get("structure"))
    existing = [
        str(item)
        for item in _as_list(effective_structure.get("accepted_debt_paths"))
        if str(item).strip()
    ]
    added = [path for path in paths if path not in existing]
    if added:
        structure_cfg = overrides.setdefault("structure", {})
        if not isinstance(structure_cfg, dict):
            raise APError("Project structure override must be a mapping")
        structure_cfg["accepted_debt_paths"] = existing + added
        overlay_payload = _render_project_overlay(overrides)
        if _safe_read_project_file(repo, _PROJECT_CONFIG_RELATIVE) is None:
            _safe_create_project_file(repo, _PROJECT_CONFIG_RELATIVE, overlay_payload)
        else:
            _safe_write_project_file(repo, _PROJECT_CONFIG_RELATIVE, overlay_payload)
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
                "path": _PROJECT_CONFIG_RELATIVE.as_posix(),
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
        parts = [part for part in lower.replace("\\", "/").strip("/").split("/") if part]
        directories = set(parts[:-1])
        suffix = Path(lower).suffix
        semantic_path_words = words
        project_documentation_or_managed_skill = bool(directories & {".agents", "docs"})
        if (
            suffix in {".ddl", ".sql"}
            or directories & {"alembic", "flyway", "liquibase", "prisma"}
            or (
                semantic_path_words & {"database", "databases", "db", "schema", "schemas", "sql"}
                and not project_documentation_or_managed_skill
            )
            or (
                semantic_path_words & {"migration", "migrations"}
                and not project_documentation_or_managed_skill
                and "workflow" not in semantic_path_words
            )
        ):
            categories.add("db")
        if any(token in lower for token in ["api", "controller", "handler", "route", "server"]):
            categories.add("api")
        if words & {
            "auth", "authentication", "authorization", "permission", "permissions",
            "role", "roles", "tenant", "security", "login", "session", "sessions",
            "token", "tokens", "jwt", "oauth", "oidc", "sso", "password", "passwords",
            "credential", "credentials",
        }:
            categories.add("auth")
        if words & {"payment", "payments", "billing", "invoice", "invoices", "checkout"}:
            categories.add("payment")
        if words & {"upload", "uploads", "download", "downloads", "attachment", "attachments"}:
            categories.add("file_transfer")
        if words & {"nginx", "gateway", "ingress"} or {"reverse", "proxy"} <= words:
            categories.add("gateway")
        if "production" in words or "prod" in words and "config" in words or ".env.prod" in lower:
            categories.add("prod_config")
        if _is_ui_path(path):
            categories.add("ui")
        if any(token in lower for token in ["test", "spec", "__tests__"]):
            categories.add("test")
        if lower.startswith("docs/") or lower.endswith(".md"):
            categories.add("docs")
        if any(token in lower for token in ["domain", "service", "usecase", "repository", "infrastructure", "adapter", "shared", "utils"]):
            categories.add("structure")
    return _classification_for_categories(categories, len(paths))


_UI_PATH_SEGMENTS = {"frontend", "miniapp", "page", "pages", "component", "components", "view", "views"}
_UI_FILE_SUFFIXES = {".css", ".jsx", ".scss", ".tsx", ".vue"}


def _is_ui_path(path: str) -> bool:
    """Classify UI paths by exact directory semantics or UI-only extensions."""
    normalized = path.replace("\\", "/").strip("/").lower()
    directories = [part for part in normalized.split("/")[:-1] if part]
    return Path(normalized).suffix.lower() in _UI_FILE_SUFFIXES or any(part in _UI_PATH_SEGMENTS for part in directories)


def _classification_for_categories(categories: set[str], file_count: int) -> dict:
    return {
        "categories": sorted(categories),
        "needs_dd": bool(
            categories
            & {"api", "db", "auth", "payment", "file_transfer", "gateway", "prod_config", "release_or_tooling"}
        ),
        # Path names and file counts do not justify a durable architecture
        # record. The model or an explicit project rule decides.
        "needs_adr": False,
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
        "db": [
            "database", "db migration", "data migration", "database migration",
            "database schema", "table schema", "sql", "数据库", "数据迁移", "表结构",
        ],
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


def _high_confidence_intent_categories(intent: str) -> set[str]:
    value = _text(intent).lower()
    signals = {
        "db": [
            "database", "db migration", "data migration", "database migration",
            "database schema", "table schema", "ddl", "sql", "table structure",
            "数据迁移", "数据库迁移", "表结构", "数据库结构",
        ],
        "auth": [
            "authorization", "permission", "security boundary", "token validation",
            "session validation", "access control", "鉴权", "权限", "安全边界",
            "令牌校验", "会话校验", "访问控制",
        ],
        "payment": [
            "settlement", "refund", "charge", "transaction", "billing", "ledger",
            "payment idempotency", "结算", "退款", "扣款", "交易", "账单", "资金", "支付幂等",
        ],
        "file_transfer": [
            "upload validation", "download authorization", "file validation", "path traversal",
            "上传校验", "下载权限", "文件校验", "路径穿越",
        ],
        "gateway": [
            "gateway config", "ingress config", "nginx config", "reverse proxy config",
            "网关配置", "入口配置", "反向代理配置",
        ],
        "prod_config": ["production config", "prod config", "生产配置"],
        "release_or_tooling": [
            "release pipeline", "deployment pipeline", "jenkins pipeline", "publish workflow",
            "发布流程", "部署流水线", "构建流水线", "发布工作流",
        ],
    }
    return {
        category
        for category, keywords in signals.items()
        if any(keyword in value for keyword in keywords)
    }


_MECHANICAL_CHANGE_SIGNALS = (
    "mechanical", "rename only", "move only", "pure rename", "pure move", "no behavior change",
    "without behavior change", "behavior unchanged", "source of truth unchanged", "contract unchanged",
    "仅改名", "只改名", "仅移动", "只移动", "不改变行为", "行为不变", "机械同步", "机械变更", "契约不变", "事实源不变",
)
_SEMANTIC_CHANGE_SIGNALS = (
    "semantic change", "change behavior", "behavior change", "new behavior", "architecture change", "contract change", "schema change",
    "语义变更", "行为变更", "改变行为", "新增行为", "架构变更", "契约变更", "模式变更",
)


def _intent_change_nature(intent: str) -> str:
    value = _text(intent).lower()
    if not value:
        return "unknown"
    semantic_value = re.sub(r"\b(?:not\s+(?:a\s+)?|non[- ]?|isn't\s+)mechanical\b|(?:不是|并非|非)机械(?:变更|同步)?", " ", value)
    mechanical = [] if semantic_value != value else [signal for signal in _MECHANICAL_CHANGE_SIGNALS if signal in value]
    for signal in mechanical:
        semantic_value = semantic_value.replace(signal, " ")
    for pattern in [r"\bno\s+.{0,16}\bbehavior\s+change\b", r"不改变.{0,16}行为"]:
        if re.search(pattern, semantic_value):
            mechanical.append(pattern)
            semantic_value = re.sub(pattern, " ", semantic_value)
    if any(signal in semantic_value for signal in _SEMANTIC_CHANGE_SIGNALS) or re.search(
        r"\b(?:change|changes|changed|changing|modify|modifies|modified|modifying|alter|alters|altered|altering|update|updates|updated|updating)\b.{0,40}\b(?:behaviors?|semantics?|architecture|contracts?|schemas?)\b"
        r"|\b(?:behaviors?|semantics?|architecture|contracts?|schemas?)\b.{0,24}\b(?:change|changes|changed|changing)\b|(?:修改|调整|改变|新增|更新).{0,32}(?:行为|语义|架构|契约|模式)|(?:行为|语义|架构|契约|模式).{0,16}(?:变化|变更|调整)", semantic_value
    ):
        return "semantic"
    if mechanical:
        return "mechanical"
    return "unknown"


def _pure_exact_git_rename(repo: Path, base_ref: str, changed_paths: list[str]) -> bool:
    common = ["--name-status", "-z", "-M100%", "--diff-filter=ACDMRTUXB"]
    commands = [["git", "diff", *common], ["git", "diff", "--cached", *common]]
    effective_base = _effective_change_base(repo, base_ref)
    if effective_base:
        commands.insert(0, ["git", "diff", *common, f"{effective_base}...HEAD"])
    entries: list[tuple[str, tuple[str, ...]]] = []
    for command in commands:
        result = run(command, cwd=repo, check=False)
        if result.returncode != 0:
            return False
        tokens = [token for token in result.stdout.split("\0") if token]
        index = 0
        while index < len(tokens):
            status = tokens[index]
            width = 2 if status[:1] in {"R", "C"} else 1
            paths = tokens[index + 1 : index + 1 + width]
            if len(paths) != width:
                return False
            entries.append((status, tuple(path.replace("\\", "/") for path in paths)))
            index += width + 1
    renamed = {path for status, paths in entries if status == "R100" for path in paths}
    changed = {path.replace("\\", "/") for path in changed_paths if _text(path)}
    return bool(entries) and all(status == "R100" for status, _ in entries) and renamed == changed


def _classify_change_nature(
    repo: Path,
    *,
    base_ref: str,
    changed_paths: list[str],
    intent: str,
    inspect_git: bool,
) -> str:
    intent_nature = _intent_change_nature(intent)
    if intent_nature != "semantic" and inspect_git and changed_paths and _pure_exact_git_rename(repo, base_ref, changed_paths):
        return "mechanical"
    return intent_nature


def _resolve_task_kind(
    requested: str,
    paths: list[str],
    intent: str,
) -> str:
    value = _text(requested).lower().replace("-", "_") or "auto"
    if value not in _REQUESTED_TASK_KINDS:
        raise APError("task kind must be one of: " + ", ".join(sorted(_REQUESTED_TASK_KINDS)))
    if _is_terminal_ledger_maintenance(paths):
        if value in {"change", "read_only"}:
            return value
        return "terminal_maintenance"
    normalized_intent = _text(intent).lower()
    terminal_action = bool(
        re.search(r"\b(archive|close|reconcile)\b", normalized_intent)
        or any(keyword in normalized_intent for keyword in ["归档", "对账", "收口"])
    )
    terminal_subject = bool(
        re.search(r"\b(closure|ledger|task\s+records?|taskbook)\b", normalized_intent)
        or any(keyword in normalized_intent for keyword in ["台账", "任务记录", "关闭记录"])
    )
    if terminal_action and terminal_subject:
        detected = "terminal_maintenance"
    elif paths:
        detected = "change"
    elif not normalized_intent:
        detected = "none"
    else:
        detected = ""
    if value == "terminal_maintenance" and detected != "terminal_maintenance":
        raise APError(
            "terminal_maintenance is valid only for task ledger/closure/archive reconciliation; "
            "code or unrelated documentation paths require task-kind=change"
        )
    if value != "auto":
        return value
    if detected:
        return detected
    english_change = re.search(
        r"\b(add|build|change|create|delete|deploy|develop|fix|implement|migrate|optimize|publish|refactor|release|remove|rename|resolve|update|upgrade)\b",
        normalized_intent,
    )
    chinese_change = any(
        keyword in normalized_intent
        for keyword in [
            "修改", "新增", "删除", "修复", "解决", "整改", "实现", "迁移", "发布",
            "重构", "改名", "升级", "优化", "完善", "补充", "清理", "落地", "提交", "推送",
        ]
    )
    return "change" if english_change or chinese_change else "read_only"


def _optional_agent_candidates(
    *,
    task_kind: str,
    intent: str,
    categories: set[str],
    cross_module: bool,
    profile: str,
) -> list[str]:
    if task_kind not in {"read_only", "change"}:
        return []
    value = _text(intent).lower()
    roles: list[str] = []
    if task_kind == "read_only" or cross_module or profile == "high-risk":
        roles.append("explorer")
    if any(
        keyword in value
        for keyword in [
            "documentation", "docs", "framework", "library", "official", "sdk", "version",
            "依赖", "官方", "文档", "框架", "版本",
        ]
    ):
        roles.append("docs_researcher")
    if "ui" in categories and any(
        keyword in value
        for keyword in ["broken", "bug", "error", "fail", "fix", "reproduce", "报错", "复现", "失败", "异常", "修复"]
    ):
        roles.append("browser_debugger")
    return roles


def _normalize_workflow_profile(value: object, default: str = "auto") -> str:
    profile = _text(value).lower() or default
    if profile not in _WORKFLOW_PROFILES:
        raise APError("workflow.profile must be one of: " + ", ".join(sorted(_WORKFLOW_PROFILES)))
    return profile


def _configured_workflow_profile(cfg: dict) -> str:
    return _normalize_workflow_profile((cfg.get("workflow") or {}).get("profile"))


def _recommended_agents(
    profile: str,
    categories: set[str],
    classification: dict,
    *,
    parallel_writers: int = 1,
    review_required: bool = False,
    review_policy: Optional[dict] = None,
) -> list[str]:
    roles: list[str] = []
    for stage in _agent_execution_plan(
        profile,
        categories,
        classification,
        parallel_writers=parallel_writers,
        review_required=review_required,
        review_policy=review_policy,
    )["stages"]:
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
            "writer": ["execution_mode", "owned_paths", "task_branch/worktree_path when isolated"],
            "reviewer": [
                "task_id",
                "diff_base",
                "diff_head",
                "diff_fingerprint",
                "diff_artifact_path",
                "diff_artifact_sha256",
                "diff_artifact_format",
                "owning_fixer",
                "review_depth",
                "timeout_seconds",
                "issued_at",
                "deadline_at",
                "scope_revision",
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


_ORCHESTRATION_SCHEMA_CACHE: Optional[dict] = None


def _orchestration_schema() -> dict:
    global _ORCHESTRATION_SCHEMA_CACHE
    if _ORCHESTRATION_SCHEMA_CACHE is None:
        path = Path(__file__).resolve().parents[1] / _AGENT_CONTRACT_SCHEMA
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise APError(f"Cannot load orchestration contract schema: {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise APError(f"Orchestration contract schema must be an object: {path}")
        _ORCHESTRATION_SCHEMA_CACHE = payload
    return _ORCHESTRATION_SCHEMA_CACHE


def _contract_ref(root: dict, ref: str) -> dict:
    if not ref.startswith("#/"):
        raise APError(f"Unsupported orchestration contract reference: {ref}")
    current: object = root
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            raise APError(f"Broken orchestration contract reference: {ref}")
        current = current[token]
    if not isinstance(current, dict):
        raise APError(f"Orchestration contract reference is not an object: {ref}")
    return current


def _contract_type_matches(value: object, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "null": value is None,
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
    }.get(expected, False)


def _contract_equal(left: object, right: object) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    return left == right


def _contract_validation_errors(
    fragment: dict,
    value: object,
    root: dict,
    path: str,
) -> list[str]:
    errors: list[str] = []
    if "$ref" in fragment:
        errors.extend(
            _contract_validation_errors(
                _contract_ref(root, _text(fragment["$ref"])), value, root, path
            )
        )

    expected_types = fragment.get("type")
    if expected_types is not None:
        choices = expected_types if isinstance(expected_types, list) else [expected_types]
        if not all(isinstance(item, str) for item in choices) or not any(
            _contract_type_matches(value, item) for item in choices
        ):
            errors.append(f"{path}: expected type {choices}")
            return errors

    if "const" in fragment and not _contract_equal(value, fragment["const"]):
        errors.append(f"{path}: expected constant {fragment['const']!r}")
    if "enum" in fragment and not any(
        _contract_equal(value, item) for item in fragment["enum"]
    ):
        errors.append(f"{path}: value is outside the allowed enum")

    if isinstance(value, str):
        if len(value) < int(fragment.get("minLength") or 0):
            errors.append(f"{path}: string is too short")
        pattern = fragment.get("pattern")
        if pattern and not re.search(str(pattern), value):
            errors.append(f"{path}: string does not match {pattern!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in fragment and value < fragment["minimum"]:
            errors.append(f"{path}: number is below minimum {fragment['minimum']}")
        if "maximum" in fragment and value > fragment["maximum"]:
            errors.append(f"{path}: number exceeds maximum {fragment['maximum']}")

    if isinstance(value, list):
        if "maxItems" in fragment and len(value) > int(fragment["maxItems"]):
            errors.append(f"{path}: too many array items")
        item_schema = fragment.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(
                    _contract_validation_errors(item_schema, item, root, f"{path}[{index}]")
                )

    if isinstance(value, dict):
        required = fragment.get("required") or []
        missing = sorted(item for item in required if item not in value)
        if missing:
            errors.append(f"{path}: missing " + ", ".join(missing))
        properties = fragment.get("properties") or {}
        if fragment.get("additionalProperties") is False:
            unexpected = sorted(set(value) - set(properties))
            if unexpected:
                errors.append(f"{path}: unexpected " + ", ".join(unexpected))
        for key, child in properties.items():
            if key in value and isinstance(child, dict):
                errors.extend(
                    _contract_validation_errors(child, value[key], root, f"{path}.{key}")
                )

    condition = fragment.get("if")
    if isinstance(condition, dict) and not _contract_validation_errors(
        condition, value, root, path
    ):
        then = fragment.get("then")
        if isinstance(then, dict):
            errors.extend(_contract_validation_errors(then, value, root, path))

    for child in fragment.get("allOf") or []:
        if isinstance(child, dict):
            errors.extend(_contract_validation_errors(child, value, root, path))
    return errors


def _validate_orchestration_contract(kind: str, payload: dict) -> dict:
    definitions = {
        "assignment": "agentAssignment",
        "result": "agentResult",
        "agentPlan": "agentPlan",
        "classify": "classifyResult",
    }
    definition = definitions.get(kind)
    if not definition:
        raise APError(f"Unknown orchestration contract kind: {kind}")
    root = _orchestration_schema()
    errors = _contract_validation_errors(root["$defs"][definition], payload, root, "$")

    role = _text(payload.get("role"))
    if kind == "assignment" and role == "reviewer":
        if _text(payload.get("node_id")) == _text(payload.get("owning_fixer")):
            errors.append("$.node_id: reviewer must differ from owning_fixer")
        timing_fields = ("issued_at", "deadline_at", "timeout_seconds")
        timing_values = [payload.get(field) for field in timing_fields]
        if any(value is not None for value in timing_values):
            if not all(value is not None for value in timing_values):
                errors.append("$: reviewer timing fields must be supplied together")
            else:
                try:
                    issued_at = _parse_iso_timestamp(payload.get("issued_at"), "issued_at")
                    deadline_at = _parse_iso_timestamp(payload.get("deadline_at"), "deadline_at")
                    timeout_seconds = int(payload.get("timeout_seconds"))
                    expected_timeout = {
                        "focused": _FOCUSED_REVIEW_TIMEOUT_SECONDS,
                        "deep": _DEEP_REVIEW_TIMEOUT_SECONDS,
                    }.get(_text(payload.get("review_depth")))
                    if expected_timeout is not None and timeout_seconds != expected_timeout:
                        errors.append(
                            "$.timeout_seconds: must match the fixed "
                            f"{_text(payload.get('review_depth'))} review budget {expected_timeout}"
                        )
                    if deadline_at <= issued_at:
                        errors.append("$.deadline_at: must be after issued_at")
                    elif int((deadline_at - issued_at).total_seconds()) != timeout_seconds:
                        errors.append("$.deadline_at: interval must equal timeout_seconds")
                except (APError, TypeError, ValueError) as exc:
                    errors.append(f"$: invalid reviewer timing contract: {exc}")
    if kind == "result":
        owned_paths = payload.get("owned_paths")
        changed_paths = payload.get("changed_paths")
        if role == "fixer" and isinstance(owned_paths, list) and isinstance(changed_paths, list):
            owned = [_normalize_owned_path(item) for item in payload.get("owned_paths") or []]
            outside = [
                path
                for path in payload.get("changed_paths") or []
                if isinstance(path, str)
                if not _path_is_owned(path, owned)
            ]
            if outside:
                errors.append(
                    "$.changed_paths: fixer paths exceed owned_paths: " + ", ".join(outside)
                )
        if role == "reviewer" and _text(payload.get("verdict")) in {"approved", "changes-requested"}:
            if not re.fullmatch(r"[0-9a-f]{64}", _text(payload.get("diff_fingerprint"))):
                errors.append(
                    "$.diff_fingerprint: reviewer verdict must bind to a 64-character fingerprint"
                )
    errors = list(dict.fromkeys(errors))
    if errors:
        raise APError("Contract validation failed:\n- " + "\n- ".join(errors))
    return payload


def _reviewer_result_template(assignment: dict, verdict: str) -> dict:
    """Build a complete Reviewer result without guessing review evidence or findings."""
    _validate_orchestration_contract("assignment", assignment)
    if _text(assignment.get("role")) != "reviewer":
        raise APError("Reviewer result templates require a reviewer assignment.")
    normalized_verdict = _text(verdict).lower()
    if normalized_verdict not in {"approved", "changes-requested", "blocked"}:
        raise APError(
            "Reviewer result verdict must be approved, changes-requested, or blocked."
        )
    fingerprint = _text(assignment.get("diff_fingerprint"))
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise APError(
            "Reviewer result templates require a non-empty 64-character diff fingerprint."
        )
    status = "blocked" if normalized_verdict == "blocked" else "completed"
    next_owner = (
        _text(assignment.get("owning_fixer"))
        if normalized_verdict == "changes-requested"
        else "main"
    )
    summaries = {
        "approved": "Review completed with no blocking findings.",
        "changes-requested": "Review completed with changes requested.",
        "blocked": "Review could not be completed.",
    }
    result = {
        "contract_version": _AGENT_CONTRACT_VERSION,
        "node_id": _text(assignment.get("node_id")),
        "role": "reviewer",
        "task_id": _text(assignment.get("task_id")),
        "base_sha": _text(assignment.get("base_sha")),
        "status": status,
        "summary": summaries[normalized_verdict],
        "depends_on": list(assignment.get("depends_on") or []),
        "owned_paths": [],
        "changed_paths": [],
        "diff_fingerprint": fingerprint,
        "evidence": [],
        "findings": [],
        "verdict": normalized_verdict,
        "risks": [],
        "next_owner": next_owner,
    }
    return _validate_orchestration_contract("result", result)


def _normalize_reviewer_runtime_result(assignment: dict, payload: dict) -> dict:
    """Normalize presentation fields while refusing assignment-binding spoofing."""
    if not isinstance(payload, dict):
        raise APError("Reviewer runtime output must be one JSON object.")
    verdict = _text(payload.get("verdict")).lower()
    if verdict not in {"approved", "changes-requested", "blocked"}:
        raise APError(
            "Reviewer runtime output must include verdict=approved, changes-requested, or blocked."
        )
    result = _reviewer_result_template(assignment, verdict)
    binding_fields = {
        "contract_version": result["contract_version"],
        "node_id": result["node_id"],
        "role": result["role"],
        "task_id": result["task_id"],
        "base_sha": result["base_sha"],
        "diff_fingerprint": result["diff_fingerprint"],
    }
    mismatched = [
        field
        for field, expected in binding_fields.items()
        if field in payload and payload.get(field) != expected
    ]
    if mismatched:
        raise APError(
            "Reviewer runtime result does not match its assignment: "
            + ", ".join(mismatched)
        )
    if "summary" in payload:
        if not isinstance(payload["summary"], str):
            raise APError("Reviewer runtime result summary must be a string.")
        result["summary"] = payload["summary"]
    for field in ("evidence", "findings", "risks"):
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise APError(f"Reviewer runtime result {field} must be an array of strings.")
        result[field] = value
    return _validate_orchestration_contract("result", result)


def _reviewer_agent_config(worktree: Path) -> dict:
    candidates = [
        worktree / ".agents" / "agents" / "reviewer.toml",
        _skill_root().parent.parent / "agents" / "reviewer.toml",
    ]
    for path in candidates:
        try:
            payload = tomllib.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise APError(f"Cannot load managed Reviewer Agent config: {path}: {exc}") from exc
        instructions = _text(payload.get("developer_instructions"))
        if instructions:
            model = _text(payload.get("model"))
            if model and any(char in model for char in "\0\r\n"):
                raise APError(f"Managed Reviewer model contains invalid characters: {path}")
            return {
                "instructions": instructions,
                "model": model,
                "config_path": str(path),
            }
    return {
        "instructions": (
            "Act as an independent read-only code reviewer. Review only the supplied "
            "assignment and return one JSON object with an approved, changes-requested, "
            "or blocked verdict. Do not modify files."
        ),
        "model": "",
        "config_path": "",
    }


def _reviewer_agent_instructions(worktree: Path) -> str:
    return _text(_reviewer_agent_config(worktree).get("instructions"))


def _codex_reviewer_command(
    worktree: Path,
    assignment_path: Path,
    result_path: Path,
    *,
    review_depth: str = "deep",
) -> list[str]:
    codex = shutil.which("codex")
    if not codex:
        raise APError(
            "The supervised Reviewer runtime requires the Codex CLI on PATH. "
            "Install Codex or run review-assignment and use another deadline-capable host."
        )
    agent_config = _reviewer_agent_config(worktree)
    instructions = _text(agent_config.get("instructions"))
    model = _text(agent_config.get("model"))
    depth = _text(review_depth).lower()
    if depth not in {"focused", "deep"}:
        raise APError(f"Unsupported Reviewer depth: {review_depth!r}")
    reasoning_effort = "high" if depth == "focused" else "xhigh"
    runtime_python = os.path.abspath(sys.executable)
    runtime_script = Path(__file__).resolve()
    artifact_command = shlex.join(
        [
            runtime_python,
            str(runtime_script),
            "review-artifact",
            "--file",
            str(assignment_path),
        ]
    )
    template_command = shlex.join(
        [
            runtime_python,
            str(runtime_script),
            "agent-result-template",
            "--file",
            str(assignment_path),
        ]
    )
    prompt = (
        f"Review the exact assignment at {assignment_path}. "
        f"Before analysis, run `{artifact_command}`; it verifies diff_artifact_path, "
        "mode 0600, and diff_artifact_sha256, then emits the immutable patch. "
        "Review that emitted patch and never substitute a live git diff or diff_base..diff_head. "
        "Stay inside its identity and deadline. Use "
        f"`{template_command} --verdict approved` when useful, replacing `approved` "
        "with `changes-requested` or `blocked` when appropriate. "
        "Return only one JSON object as the final response; do not modify files."
    )
    command = [
        codex,
        "-a",
        "never",
        "exec",
        "--json",
        "--color",
        "never",
        "--ephemeral",
        "--ignore-user-config",
        "-C",
        str(worktree),
        "-s",
        "read-only",
        "-c",
        f'model_reasoning_effort="{reasoning_effort}"',
        "-c",
        "developer_instructions=" + json.dumps(instructions, ensure_ascii=False),
        "-o",
        str(result_path),
    ]
    if model:
        command.extend(["--model", model])
    command.append(prompt)
    return command


def _terminate_reviewer_process(process: subprocess.Popen[str]) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            process.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            pass
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                break
            except PermissionError:
                break
            time.sleep(0.05)
        try:
            os.killpg(process.pid, 0)
        except (ProcessLookupError, PermissionError):
            pass
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        return
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


def _reviewer_diagnostic_categories(value: str) -> list[str]:
    lowered = value.lower()
    patterns = {
        "authentication": ("unauthorized", "forbidden", "login", "401", "403"),
        "model-discovery": ("available models", "model list", "model unavailable"),
        "network-disconnect": ("stream disconnected", "connection reset", "connection closed"),
        "permission": ("operation not permitted", "permission denied", "readonly database"),
        "rate-limit": ("rate limit", "too many requests", "429"),
        "state-database": ("state_", "sqlite", "database"),
        "timeout": ("timed out", "timeout"),
        "tls": ("tls", "certificate", "handshake eof"),
    }
    return sorted(
        category
        for category, needles in patterns.items()
        if any(needle in lowered for needle in needles)
    )


def _reviewer_event_metadata(stream: str, line: str, timestamp: str) -> tuple[dict, bool]:
    encoded = line.encode("utf-8", errors="replace")
    record = {
        "timestamp": timestamp,
        "stream": stream,
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }
    if stream == "stderr":
        record["event_type"] = "diagnostic"
        record["categories"] = _reviewer_diagnostic_categories(line)
        return record, False
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        record["event_type"] = "stdout-non-json"
        return record, False
    if not isinstance(payload, dict):
        record["event_type"] = "stdout-non-object"
        return record, False
    event_type = _text(payload.get("type")) or "unknown-json-event"
    record["event_type"] = event_type
    item = payload.get("item")
    if isinstance(item, dict) and _text(item.get("type")):
        record["item_type"] = _text(item.get("type"))
    semantic = event_type != "thread.started"
    return record, semantic


def _reviewer_phase(event_type: str) -> str:
    if event_type == "thread.started":
        return "runtime-started"
    if event_type == "turn.started":
        return "analysis-started"
    if event_type.startswith("item."):
        return "analyzing"
    if event_type == "turn.completed":
        return "finalizing"
    if event_type in {"error", "turn.failed"}:
        return "runtime-error"
    return "runtime-event"


def _append_reviewer_output(parts: list[str], current_bytes: int, value: str) -> int:
    encoded = value.encode("utf-8", errors="replace")
    if current_bytes + len(encoded) > _REVIEW_OUTPUT_MAX_BYTES:
        raise _ReviewerRuntimeOutputLimit()
    parts.append(value)
    return current_bytes + len(encoded)


def _reviewer_stream_reader(
    stream: object,
    stream_name: str,
    output_queue: queue.Queue,
    stop_event: threading.Event,
    semantic_seen: threading.Event,
) -> None:
    def emit(raw: bytes) -> None:
        line = raw.decode("utf-8", errors="replace")
        timestamp = _now_iso()
        if stream_name == "stdout" and _reviewer_event_metadata(
            stream_name,
            line,
            timestamp,
        )[1]:
            semantic_seen.set()
        while not stop_event.is_set():
            try:
                output_queue.put((stream_name, line, timestamp), timeout=0.05)
                return
            except queue.Full:
                continue

    try:
        if os.name == "posix":
            descriptor = stream.fileno()  # type: ignore[attr-defined]
            os.set_blocking(descriptor, False)
            pending = b""
            while not stop_event.is_set():
                try:
                    chunk = os.read(descriptor, 65536)
                except (BlockingIOError, InterruptedError):
                    stop_event.wait(0.02)
                    continue
                if not chunk:
                    break
                pending += chunk
                while b"\n" in pending:
                    raw, pending = pending.split(b"\n", 1)
                    emit(raw + b"\n")
                if len(pending) > _REVIEW_OUTPUT_MAX_BYTES:
                    emit(pending)
                    pending = b""
            if pending and not stop_event.is_set():
                emit(pending)
        else:
            while not stop_event.is_set():
                raw = stream.readline(_REVIEW_OUTPUT_MAX_BYTES + 1)  # type: ignore[attr-defined]
                if raw == b"":
                    break
                emit(raw)
    except (OSError, ValueError):
        pass
    finally:
        while not stop_event.is_set():
            try:
                output_queue.put((stream_name, None, _now_iso()), timeout=0.05)
                break
            except queue.Full:
                continue


def _reviewer_attempt_diagnostics(
    *,
    started_at: str,
    finished_at: str,
    stdout: str,
    stderr: str,
    first_event_at: str,
    last_event_at: str,
    last_event_type: str,
    event_count: int,
    phase: str,
    exit_code: Optional[int],
) -> dict:
    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "first_event_at": first_event_at,
        "last_event_at": last_event_at,
        "last_event_type": last_event_type,
        "event_count": event_count,
        "phase": phase,
        "exit_code": exit_code,
        "stdout_bytes": len(stdout.encode("utf-8", errors="replace")),
        "stderr_bytes": len(stderr.encode("utf-8", errors="replace")),
        "stdout_sha256": hashlib.sha256(stdout.encode("utf-8", errors="replace")).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr.encode("utf-8", errors="replace")).hexdigest(),
        "diagnostic_categories": _reviewer_diagnostic_categories(stderr),
        "stdout": stdout,
        "stderr": stderr,
    }


def _run_supervised_reviewer_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: float,
    startup_timeout_seconds: Optional[float] = None,
    event_writer: Optional[object] = None,
) -> tuple[subprocess.CompletedProcess[str], dict]:
    if timeout_seconds <= 0:
        raise _ReviewerRuntimeTimeout()
    startup_timeout = min(
        startup_timeout_seconds or _review_startup_timeout_seconds(),
        timeout_seconds,
    )
    started_at = _now_iso()
    started_monotonic = time.monotonic()
    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            bufsize=0,
            start_new_session=True,
        )
    except OSError as exc:
        diagnostics = _reviewer_attempt_diagnostics(
            started_at=started_at,
            finished_at=_now_iso(),
            stdout="",
            stderr=str(exc),
            first_event_at="",
            last_event_at="",
            last_event_type="",
            event_count=0,
            phase="spawn-failed",
            exit_code=None,
        )
        raise _ReviewerRuntimeUnavailable(diagnostics) from exc
    if process.stdout is None or process.stderr is None:
        _terminate_reviewer_process(process)
        raise _ReviewerRuntimeUnavailable()

    output_queue: queue.Queue = queue.Queue(maxsize=256)
    stop_event = threading.Event()
    semantic_seen = threading.Event()
    readers = [
        threading.Thread(
            target=_reviewer_stream_reader,
            args=(process.stdout, "stdout", output_queue, stop_event, semantic_seen),
            name=f"reviewer-stream-{process.pid}-stdout",
            daemon=True,
        ),
        threading.Thread(
            target=_reviewer_stream_reader,
            args=(process.stderr, "stderr", output_queue, stop_event, semantic_seen),
            name=f"reviewer-stream-{process.pid}-stderr",
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()

    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    stdout_bytes = 0
    stderr_bytes = 0
    closed_streams: set[str] = set()
    first_event_at = ""
    last_event_at = ""
    last_event_type = ""
    event_count = 0
    phase = "starting"
    failure: Optional[type[_ReviewerRuntimeFailure]] = None
    supervision_error: Optional[Exception] = None

    def consume(item: tuple[str, Optional[str], str], *, write_event: bool = True) -> None:
        nonlocal stdout_bytes, stderr_bytes, first_event_at, last_event_at
        nonlocal last_event_type, event_count, phase
        stream_name, line, timestamp = item
        if line is None:
            closed_streams.add(stream_name)
            return
        if stream_name == "stdout":
            stdout_bytes = _append_reviewer_output(stdout_parts, stdout_bytes, line)
        else:
            stderr_bytes = _append_reviewer_output(stderr_parts, stderr_bytes, line)
        record, semantic = _reviewer_event_metadata(stream_name, line, timestamp)
        if write_event and event_writer is not None:
            event_writer.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            event_writer.flush()
        if stream_name == "stdout" and record["event_type"] not in {
            "stdout-non-json",
            "stdout-non-object",
        }:
            event_count += 1
            last_event_at = timestamp
            last_event_type = _text(record.get("event_type"))
            phase = _reviewer_phase(last_event_type)
            if semantic and not first_event_at:
                first_event_at = timestamp

    try:
        while len(closed_streams) < 2 or process.poll() is None:
            try:
                item = output_queue.get(timeout=0.05)
            except queue.Empty:
                item = None
            if item is not None:
                consume(item)
            elapsed = time.monotonic() - started_monotonic
            if elapsed >= timeout_seconds:
                failure = _ReviewerRuntimeTimeout
                break
            if (
                not first_event_at
                and not semantic_seen.is_set()
                and elapsed >= startup_timeout
            ):
                failure = _ReviewerRuntimeUnavailable
                break
    except _ReviewerRuntimeOutputLimit:
        failure = _ReviewerRuntimeOutputLimit
    except (OSError, ValueError) as exc:
        failure = _ReviewerRuntimeInternalError
        supervision_error = exc
        phase = "supervision-failed"
    finally:
        if failure is not None or process.poll() is None:
            try:
                _terminate_reviewer_process(process)
            except OSError as exc:
                failure = _ReviewerRuntimeInternalError
                supervision_error = supervision_error or exc
                phase = "process-cleanup-failed"
        tail_deadline = time.monotonic() + 0.5
        while any(reader.is_alive() for reader in readers) and time.monotonic() < tail_deadline:
            try:
                item = output_queue.get(timeout=0.02)
            except queue.Empty:
                continue
            try:
                consume(item, write_event=supervision_error is None)
            except _ReviewerRuntimeOutputLimit:
                failure = _ReviewerRuntimeOutputLimit
            except (OSError, ValueError) as exc:
                failure = _ReviewerRuntimeInternalError
                supervision_error = supervision_error or exc
                phase = "supervision-failed"
        stop_event.set()
        drain_deadline = time.monotonic() + 2
        while any(reader.is_alive() for reader in readers) and time.monotonic() < drain_deadline:
            try:
                item = output_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                consume(item, write_event=supervision_error is None)
            except _ReviewerRuntimeOutputLimit:
                failure = _ReviewerRuntimeOutputLimit
            except (OSError, ValueError) as exc:
                failure = _ReviewerRuntimeInternalError
                supervision_error = supervision_error or exc
                phase = "supervision-failed"
        for reader in readers:
            reader.join(timeout=0.2)
        if not any(reader.is_alive() for reader in readers):
            for stream in (process.stdout, process.stderr):
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass
        while True:
            try:
                item = output_queue.get_nowait()
            except queue.Empty:
                break
            try:
                consume(item, write_event=supervision_error is None)
            except _ReviewerRuntimeOutputLimit:
                failure = _ReviewerRuntimeOutputLimit
            except (OSError, ValueError) as exc:
                failure = _ReviewerRuntimeInternalError
                supervision_error = supervision_error or exc
                phase = "supervision-failed"

    if any(reader.is_alive() for reader in readers):
        failure = _ReviewerRuntimeInternalError
        phase = "reader-cleanup-failed"
    if failure is _ReviewerRuntimeUnavailable and first_event_at:
        failure = _ReviewerRuntimeTimeout

    stdout = "".join(stdout_parts)
    stderr = "".join(stderr_parts)
    diagnostics = _reviewer_attempt_diagnostics(
        started_at=started_at,
        finished_at=_now_iso(),
        stdout=stdout,
        stderr=stderr,
        first_event_at=first_event_at,
        last_event_at=last_event_at,
        last_event_type=last_event_type,
        event_count=event_count,
        phase=phase,
        exit_code=process.returncode,
    )
    if failure is not None:
        error = failure(diagnostics)
        if supervision_error is not None:
            raise error from supervision_error
        raise error
    if not first_event_at:
        raise _ReviewerRuntimeUnavailable(diagnostics)
    completed = subprocess.CompletedProcess(
        command,
        int(process.returncode or 0),
        stdout,
        stderr,
    )
    return completed, diagnostics


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
        "optional_roles",
    }
    missing = sorted(required - set(plan))
    if missing:
        raise APError("Invalid agent plan contract: " + ", ".join(missing))
    _validate_orchestration_contract("agentPlan", plan)
    return plan


def _review_execution_policy(
    *,
    review_required: bool,
    categories: set[str],
    cross_module: bool,
    parallel_writers: int,
) -> dict:
    if not review_required:
        return {
            "depth": "none",
            "agent": "",
            "timeout_seconds": 0,
            "analysis_attempt_limit": 0,
        }
    deep = bool(
        cross_module
        or parallel_writers > 1
        or categories & _DEEP_REVIEW_CATEGORIES
    )
    return {
        "depth": "deep" if deep else "focused",
        "agent": "reviewer",
        "timeout_seconds": (
            _DEEP_REVIEW_TIMEOUT_SECONDS if deep else _FOCUSED_REVIEW_TIMEOUT_SECONDS
        ),
        "analysis_attempt_limit": 1,
    }


def _normalized_task_review_policy(
    review_required: bool,
    *depth_candidates: object,
) -> tuple[str, int]:
    if not review_required:
        return "none", 0
    depth_rank = {"none": 0, "focused": 1, "deep": 2}
    depth = "focused"
    for candidate in depth_candidates:
        normalized = _text(candidate).lower()
        if depth_rank.get(normalized, 0) > depth_rank[depth]:
            depth = normalized
    timeout_seconds = (
        _DEEP_REVIEW_TIMEOUT_SECONDS if depth == "deep" else _FOCUSED_REVIEW_TIMEOUT_SECONDS
    )
    return depth, timeout_seconds


def _agent_execution_plan(
    profile: str,
    categories: set[str],
    classification: dict,
    *,
    parallel_writers: int = 1,
    review_required: bool = False,
    review_policy: Optional[dict] = None,
    optional_roles: Optional[list[str]] = None,
) -> dict:
    assignment_contract, result_contract = _agent_contract_shape()
    optional_roles = list(dict.fromkeys(optional_roles or []))
    review_policy = dict(review_policy or {})
    # Optional roles are candidates, never automatic stages. The model selects
    # them only when expected benefit exceeds coordination cost.
    discovery_roles: list[str] = []

    policies = {
        "one_writer_per_worktree": True,
        "workspace_isolation": "adaptive-clean-current-or-isolated",
        "path_ownership": "explicit-only-for-isolated-or-delegated-work",
        "dependency_policy": "integrate-before-dependent-start",
        "review_feedback_owner": "owning-fixer" if review_required else "main",
        "review_binding": "diff-fingerprint-when-required",
        "review_depth": _text(review_policy.get("depth")) or "none",
        "review_agent": _text(review_policy.get("agent")),
        "review_timeout_seconds": int(review_policy.get("timeout_seconds") or 0),
        "review_analysis_attempt_limit": int(
            review_policy.get("analysis_attempt_limit") or 0
        ),
        "lifecycle_owner": "main",
        "gate_owner": "main",
    }
    constraints = [
        "Delegate only when independent work has a clear latency or expertise benefit.",
        "A clean single-writer checkout stays on its current branch; dirty or parallel work is isolated.",
        "Never run two writers in one worktree.",
        "The main agent runs one final changed-scope gate, pushes, and cleans only temporary branches actually created.",
    ]
    if review_required:
        constraints.append(
            "Run one bounded review analysis over the supplied diff and relevant evidence; "
            "a timeout is blocked, never approved, and JSON formatting repair must reuse the same analysis."
        )

    if parallel_writers <= 1 and not discovery_roles and not review_required:
        stages = [{"id": "delivery", "mode": "serial", "roles": ["main"], "depends_on": []}]
        strategy = "main-only"
    else:
        stages = [
            {"id": "decomposition", "mode": "serial", "roles": ["main"], "depends_on": []}
        ]
        previous = "decomposition"
        if discovery_roles:
            stages.append(
                {
                    "id": "discovery",
                    "mode": "parallel" if len(discovery_roles) > 1 else "serial",
                    "roles": discovery_roles,
                    "depends_on": [previous],
                }
            )
            previous = "discovery"
        delivery_roles = ["main"]
        delivery_mode = "serial"
        if parallel_writers > 1:
            delivery_roles = ["fixer", "main"]
            delivery_mode = "parallel-isolated"
        if review_required:
            delivery_roles.append(_text(review_policy.get("agent")) or "reviewer")
        stages.append(
            {
                "id": "delivery",
                "mode": delivery_mode,
                "roles": delivery_roles,
                "depends_on": [previous],
            }
        )
        strategy = "orchestrated-subagents"

    return _validate_agent_plan({
        "contract_version": _AGENT_CONTRACT_VERSION,
        "contract_schema": _AGENT_CONTRACT_SCHEMA,
        "strategy": strategy,
        "policies": policies,
        "assignment_contract": assignment_contract,
        "result_contract": result_contract,
        "optional_roles": optional_roles,
        "stages": stages,
        "constraints": constraints,
    })


def _mechanism_plan(
    *,
    task_kind: str,
    execution_mode: str,
    review_required: bool,
    design_required: bool,
    parallel_writers: int,
) -> dict:
    universe = [
        "analysis",
        "targeted_consistency_check",
        "durable_design",
        "task_lifecycle",
        "worktree",
        "read_only_subagents",
        "parallel_fixers",
        "independent_review",
        "final_changed_scope_gate",
        "commit_push",
    ]
    required: list[str] = []
    optional: list[str] = []
    if task_kind == "read_only":
        required = ["analysis"]
        optional = ["read_only_subagents"]
    elif task_kind == "terminal_maintenance":
        required = ["analysis", "targeted_consistency_check", "commit_push"]
    elif task_kind == "change":
        required = ["analysis"]
        if design_required:
            required.append("durable_design")
        else:
            optional.append("durable_design")
        if execution_mode == "isolated":
            required.extend(["task_lifecycle", "worktree"])
        elif review_required:
            required.append("task_lifecycle")
        if parallel_writers > 1:
            required.append("parallel_fixers")
        if review_required:
            required.append("independent_review")
        else:
            optional.append("independent_review")
        optional.append("read_only_subagents")
        required.extend(["final_changed_scope_gate", "commit_push"])
    ordered = list(dict.fromkeys(required))
    optional = [item for item in dict.fromkeys(optional) if item not in ordered]
    forbidden = [item for item in universe if item not in ordered and item not in optional]
    return {
        "required": ordered,
        "optional_when_beneficial": optional,
        "forbidden": forbidden,
        # 4.1 compatibility: old clients treat only truly forbidden mechanisms
        # as not required; model-selectable mechanisms remain available.
        "not_required": forbidden,
        "lifecycle_required": "task_lifecycle" in ordered,
        "rule": (
            "run required mechanisms; select optional mechanisms only when expected value exceeds "
            "coordination cost; reclassify before changing writer count; do not run forbidden "
            "mechanisms unless the user explicitly overrides; direct/worktree decisions apply only "
            "to the reported workspace snapshot and require reclassification if it changes"
        ),
    }


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
    parallel_writers: int = 1,
    requested_task_kind: str = "",
    continue_direct: bool = False,
    direct_claim_id: str = "",
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
    task_kind = _resolve_task_kind(requested_task_kind, classification_inputs, intent)
    change_nature = _classify_change_nature(
        repo,
        base_ref=base_ref,
        changed_paths=paths,
        intent=intent,
        inspect_git=changed_paths is None,
    )
    path_classification = _classify_paths(classification_inputs)
    path_categories = set(path_classification["categories"])
    intent_categories = _classify_intent(intent)
    high_confidence_intent_categories = _high_confidence_intent_categories(intent)
    merged_categories = path_categories | set(intent_categories)
    classification = _classification_for_categories(merged_categories, len(classification_inputs))
    categories = set(classification["categories"])
    matching_rules = _matching_risk_rules(classification_inputs, cfg)
    configured_profile = _configured_workflow_profile(cfg)
    requested_profile_value = _normalize_workflow_profile(requested_profile) if requested_profile else ""
    configured_mode = _workflow_mode(cfg)
    requested_mode_value = _text(requested_mode).lower()
    if requested_mode_value and requested_mode_value != "dev":
        raise APError("workflow.mode must be 'dev'; use explicit diagnostic commands when requested.")

    detected_profile = "standard"
    profile_reasons: list[str] = []
    docs_only_paths = _docs_only(classification_inputs)
    docs_or_tests_only = "release_or_tooling" not in path_categories and bool(classification_inputs) and (
        (docs_only_paths and str(impact["selected_scope"]) != "full")
        or _tests_only(classification_inputs)
    )
    terminal_maintenance = task_kind == "terminal_maintenance"
    if task_kind in {"read_only", "terminal_maintenance", "none"}:
        detected_profile = "micro"
        profile_reasons.append(f"task kind: {task_kind}")
    elif docs_or_tests_only and str(impact["selected_scope"]) != "full":
        detected_profile = "micro"
        profile_reasons.append("only docs/test files changed")

    raw_rule_profiles = {_text(rule.get("profile")).lower() for rule in matching_rules if _text(rule.get("profile"))}
    invalid_rule_profiles = raw_rule_profiles - (_WORKFLOW_PROFILES - {"auto"})
    if invalid_rule_profiles:
        raise APError(
            "matched gate rule has invalid profile: " + ", ".join(sorted(invalid_rule_profiles))
        )
    rule_profiles = raw_rule_profiles
    if task_kind == "change" and "micro" in rule_profiles and detected_profile == "standard":
        detected_profile = "micro"
        profile_reasons.append("matched gate rule with profile=micro")
    if task_kind == "change" and "standard" in rule_profiles and detected_profile == "micro":
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
    default_high_path_categories: set[str] = set()
    path_category_sets: list[set[str]] = []
    for path in classification_inputs:
        per_path = set(_classify_paths([path])["categories"])
        path_category_sets.append(per_path)
        default_high_path_categories.update(
            per_path & {"db", "gateway", "prod_config", "release_or_tooling"}
        )
        if "ui" not in per_path:
            default_high_path_categories.update(
                per_path & {"auth", "payment", "file_transfer"}
            )
    intent_risk_candidates = sorted(set(intent_categories) & high_categories)
    all_planned_code_paths_are_ui = bool(path_category_sets) and all(
        "ui" in per_path or per_path <= {"docs", "test"}
        for per_path in path_category_sets
    )
    default_high_intent_categories = set(high_confidence_intent_categories)
    if all_planned_code_paths_are_ui:
        default_high_intent_categories.difference_update({"auth", "payment", "file_transfer"})
    high_signals: list[str] = []
    if task_kind == "change" and default_high_path_categories and not docs_or_tests_only:
        high_signals.append(
            "high-risk path category: " + ", ".join(sorted(default_high_path_categories))
        )
    if task_kind == "change" and "high-risk" in rule_profiles:
        high_signals.append("matched gate rule with profile=high-risk")
    if task_kind == "change" and default_high_intent_categories and not docs_or_tests_only:
        high_signals.append(
            "high-confidence risk intent: " + ", ".join(sorted(default_high_intent_categories))
        )
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

    try:
        writer_count = max(1, int(parallel_writers or 1))
    except (TypeError, ValueError) as exc:
        raise APError("parallel writer count must be a positive integer") from exc
    module_roots = {
        path.split("/", 1)[0]
        for path in classification_inputs
        if path and not _path_matches(path, _DOC_PATH_PATTERNS)
    }
    cross_module = len(module_roots) > 1
    rule_review = any(
        _text(rule.get("review")).lower() in {"required", "true", "yes"}
        for rule in matching_rules
    )
    rule_design = any(
        _text(rule.get("design")).lower() in {"required", "true", "yes"}
        for rule in matching_rules
    )
    cross_module_contract_risk = bool(
        cross_module
        and categories & {"api", "db", "auth", "payment", "file_transfer", "gateway", "prod_config"}
    )
    review_required = bool(
        task_kind == "change"
        and (effective_profile == "high-risk" or writer_count > 1 or cross_module_contract_risk or rule_review)
    )
    design_required = bool(
        task_kind == "change"
        and (
            rule_design
            or (
                effective_profile == "high-risk"
                and cross_module
                and change_nature != "mechanical"
            )
        )
    )
    dirty_paths = _working_tree_paths(repo)
    workspace_dirty = bool(dirty_paths)
    dirty_outside_plan = [
        path for path in dirty_paths if not _path_is_owned(path, normalized_planned_paths)
    ] if normalized_planned_paths else list(dirty_paths)
    registered_active_writer = _has_registered_active_task(repo)
    configured_isolation = _task_isolation(cfg)
    if continue_direct and task_kind != "change":
        raise APError("--continue-direct is valid only for task-kind=change")
    if continue_direct and not normalized_planned_paths:
        raise APError("--continue-direct requires every current task path via --planned-path")
    direct_claim = (
        _require_direct_claim(repo, direct_claim_id, normalized_planned_paths)
        if continue_direct
        else {}
    )
    other_direct_claims = [
        item
        for item in _active_direct_claims(repo)
        if _text(item.get("claim_id")) != _text(direct_claim_id)
    ]
    active_writer = bool(registered_active_writer or other_direct_claims)
    continued_direct = bool(
        continue_direct
        and direct_claim
        and configured_isolation == "adaptive"
        and writer_count == 1
        and not active_writer
        and not dirty_outside_plan
    )
    if task_kind != "change":
        execution_mode = "none"
    elif continued_direct:
        execution_mode = "direct"
    elif configured_isolation == "worktree" or writer_count > 1 or workspace_dirty or active_writer:
        execution_mode = "isolated"
    else:
        execution_mode = "direct"
    execution_reasons.append(
        "execution mode is adaptive: clean single-writer work is direct; dirty or parallel work is isolated"
    )
    if continued_direct:
        execution_reasons.append(
            "continued direct mode: all current dirty paths are covered by declared planned paths"
        )

    needs_jenkins = False
    needs_target = False
    needs_dd = design_required

    optional_agents = _optional_agent_candidates(
        task_kind=task_kind,
        intent=intent,
        categories=categories,
        cross_module=cross_module,
        profile=effective_profile,
    )
    review_policy = _review_execution_policy(
        review_required=review_required,
        categories=categories,
        cross_module=cross_module,
        parallel_writers=writer_count,
    )
    agent_plan = _agent_execution_plan(
        effective_profile,
        categories,
        classification,
        parallel_writers=writer_count,
        review_required=review_required,
        review_policy=review_policy,
        optional_roles=optional_agents,
    )
    mechanism_plan = _mechanism_plan(
        task_kind=task_kind,
        execution_mode=execution_mode,
        review_required=review_required,
        design_required=design_required,
        parallel_writers=writer_count,
    )
    return {
        **impact,
        "contract_version": _AGENT_CONTRACT_VERSION,
        "contract_schema": _AGENT_CONTRACT_SCHEMA,
        "planned_files": normalized_planned_paths,
        "classification_files": classification_inputs,
        "intent_provided": bool(_text(intent)),
        "change_nature": change_nature,
        "task_kind": task_kind,
        "intent_categories": intent_categories,
        "intent_risk_candidates": intent_risk_candidates,
        "high_confidence_intent_categories": sorted(high_confidence_intent_categories),
        "reasons": execution_reasons,
        "configured_profile": configured_profile,
        "requested_profile": requested_profile_value or None,
        "profile": effective_profile,
        "profile_reasons": profile_reasons,
        "configured_mode": configured_mode,
        "requested_mode": requested_mode_value or None,
        "effective_mode": effective_mode,
        "execution_mode": execution_mode,
        "terminal_maintenance": terminal_maintenance,
        "repo": str(repo),
        "workspace_dirty": workspace_dirty,
        "dirty_paths": dirty_paths,
        "dirty_outside_plan": dirty_outside_plan,
        "continued_direct": continued_direct,
        "active_writer": active_writer,
        "parallel_writers": writer_count,
        "cross_module": cross_module,
        "review_required": review_required,
        "review_depth": review_policy["depth"],
        "review_agent": review_policy["agent"],
        "review_timeout_seconds": review_policy["timeout_seconds"],
        "review_analysis_attempt_limit": review_policy["analysis_attempt_limit"],
        "design_required": design_required,
        "selected_scope": selected_scope,
        "categories": sorted(categories),
        "needs_dd": needs_dd,
        "needs_adr": classification["needs_adr"],
        "needs_browser": classification["needs_browser"],
        "needs_jenkins": needs_jenkins,
        "needs_target": needs_target,
        "recommended_agents": _recommended_agents(
            effective_profile,
            categories,
            classification,
            parallel_writers=writer_count,
            review_required=review_required,
            review_policy=review_policy,
        ),
        "optional_agents": optional_agents,
        "agent_plan": agent_plan,
        "mechanism_plan": mechanism_plan,
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
    claim_direct = bool(getattr(args, "claim_direct", False))
    continue_direct = bool(getattr(args, "continue_direct", False))
    direct_claim_id = _text(getattr(args, "direct_claim", ""))
    if claim_direct and continue_direct:
        raise APError("--claim-direct and --continue-direct are mutually exclusive.")
    plan = _resolve_execution_plan(
        cfg,
        repo,
        requested_scope=_text(getattr(args, "scope", "")).lower(),
        requested_profile=_text(getattr(args, "profile", "")).lower(),
        requested_mode=_text(getattr(args, "mode", "")).lower(),
        base_ref=_text(getattr(args, "base", "")),
        planned_paths=list(getattr(args, "planned_path", []) or []),
        intent="\n".join(part for part in intent_parts if part),
        parallel_writers=int(getattr(args, "writers", 1) or 1),
        requested_task_kind=_text(getattr(args, "task_kind", "")),
        continue_direct=continue_direct,
        direct_claim_id=_text(getattr(args, "direct_claim", "")),
    )
    direct_claim: dict = {}
    if claim_direct:
        if plan["task_kind"] != "change" or plan["execution_mode"] != "direct":
            raise APError("--claim-direct requires a clean adaptive single-writer change plan.")
        direct_claim = _create_direct_claim(
            repo,
            cfg,
            list(plan.get("planned_files") or []),
            _actor_id(args, "claim_owner"),
        )
    risk = {"micro": "P3", "standard": "P2", "high-risk": "P1"}[plan["profile"]]
    commands: list[str] = []
    if plan["needs_dd"]:
        commands.append("python3 docs/tools/autopipeline/ap.py scaffold design --write")
    result = {
        **plan,
        "risk": risk,
        "recommended_commands": commands,
        "direct_claim": (
            {
                "id": _text(direct_claim.get("claim_id")),
                "base_sha": _text(direct_claim.get("base_sha")),
                "owned_paths": list(direct_claim.get("owned_paths") or []),
            }
            if direct_claim
            else None
        ),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[classify] risk={risk}")
        print(f"[classify] task_kind={result['task_kind']}")
        print(f"[classify] profile={result['profile']}")
        print(f"[classify] effective_mode={result['effective_mode']}")
        print(f"[classify] repo={result['repo']}")
        print(f"[classify] workspace_dirty={str(result['workspace_dirty']).lower()}")
        print(
            "[classify] dirty_paths="
            + json.dumps(result["dirty_paths"], ensure_ascii=False, separators=(",", ":"))
        )
        print(f"[classify] active_writer={str(result['active_writer']).lower()}")
        print(f"[classify] execution_mode={result['execution_mode']}")
        print(f"[classify] review_required={str(result['review_required']).lower()}")
        print(f"[classify] review_depth={result['review_depth']}")
        print(f"[classify] review_agent={result['review_agent'] or '(none)'}")
        print(f"[classify] review_timeout_seconds={result['review_timeout_seconds']}")
        print(
            "[classify] review_analysis_attempt_limit="
            f"{result['review_analysis_attempt_limit']}"
        )
        print(f"[classify] design_required={str(result['design_required']).lower()}")
        print(f"[classify] change_nature={result['change_nature']}")
        print(f"[classify] selected_scope={result['selected_scope']}")
        print("[classify] categories=" + (", ".join(result["categories"]) or "(none)"))
        print("[classify] agents=" + (", ".join(result["recommended_agents"]) or "(main agent only)"))
        print(
            "[classify] optional_agents="
            + (", ".join(result["optional_agents"]) or "(none)")
        )
        print(f"[classify] agent_strategy={result['agent_plan']['strategy']}")
        print(
            "[classify] required_mechanisms="
            + (", ".join(result["mechanism_plan"]["required"]) or "(none)")
        )
        print(
            "[classify] optional_when_beneficial="
            + (", ".join(result["mechanism_plan"]["optional_when_beneficial"]) or "(none)")
        )
        print(
            "[classify] forbidden="
            + (", ".join(result["mechanism_plan"]["forbidden"]) or "(none)")
        )
        if direct_claim:
            print(f"[classify] direct_claim={direct_claim['claim_id']}")
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


def _agent_contract_payload(repo: Path, args: argparse.Namespace) -> dict:
    raw = _text(getattr(args, "payload", ""))
    source = _text(getattr(args, "file", ""))
    if source:
        if source == "-":
            raw = sys.stdin.read(1048577)
        else:
            path = Path(source)
            if not path.is_absolute():
                path = repo / path
            try:
                if path.stat().st_size > 1048576:
                    raise APError("Agent contract payload is limited to 1 MiB.")
                raw = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise APError(f"Cannot read agent contract payload: {path}: {exc}") from exc
    if len(raw.encode("utf-8")) > 1048576:
        raise APError("Agent contract payload is limited to 1 MiB.")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise APError(f"Agent contract payload is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise APError("Agent contract payload must be a JSON object.")
    return payload


def cmd_agent_contract_check(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    payload = _agent_contract_payload(repo, args)
    _validate_orchestration_contract(args.kind, payload)
    result = {"valid": True, "kind": args.kind}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[agent-contract-check] OK kind={args.kind}")


def cmd_agent_result_template(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    assignment = _agent_contract_payload(repo, args)
    result = _reviewer_result_template(assignment, args.verdict)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_run(args: argparse.Namespace) -> None:
    """
    Run any configured gate command by name.
    Commands are read from the effective managed-default plus project-overlay configuration.
    """
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    commands = (cfg.get("commands") or {})
    name = args.name
    if name not in commands:
        raise APError(
            f"Command not configured: commands.{name}. "
            "Edit docs/project/auto-coding-skill.yaml. "
            f"Available: {', '.join(commands.keys()) or '(none)'}"
        )
    cmd = str(commands.get(name) or "").strip()
    if not cmd:
        raise APError(f"Command is blank: commands.{name}. Edit docs/project/auto-coding-skill.yaml.")
    print(f"[run] {name}: {cmd}")
    run_shell(cmd, cwd=repo)
    print(f"[run] OK: {name}")


def cmd_light_gate(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    light_gate_start = time.time()
    monotonic_start = time.monotonic()
    cfg = _load_cfg(repo)
    manifest = _active_task_manifest(repo)
    if manifest:
        manifest = _require_task_context(repo, cfg, _text(manifest.get("task_id")))
        _clear_final_gate_receipt(repo)
    before_fingerprint = _task_content_fingerprint(repo, cfg, manifest)
    budget = _final_gate_budget(cfg)
    deadline = monotonic_start + budget["total_seconds"]
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
    executed = _run_changed_gate(
        repo,
        cfg,
        paths,
        deadline=deadline,
        command_timeout_s=budget["command_seconds"],
    )
    executed.extend(
        _run_structure_check_for_gate(
            repo,
            cfg,
            selected_scope,
            _text(getattr(args, "base", "")),
            deadline=deadline,
            command_timeout_s=budget["command_seconds"],
        )
    )

    _run_git_diff_check(repo, cfg)
    if time.monotonic() > deadline:
        raise APError(
            f"Final changed-scope gate timed out after {budget['total_seconds']:.0f}s; "
            "narrow validation.routes and keep slower checks explicit"
        )
    executed.append("diff_check")
    after_fingerprint = _task_content_fingerprint(repo, cfg, manifest)
    if after_fingerprint != before_fingerprint:
        _clear_final_gate_receipt(repo)
        raise APError("The final gate changed task content; inspect the diff before retrying.")
    if manifest:
        _record_final_gate_receipt(
            repo,
            cfg,
            manifest,
            plan,
            _text(getattr(args, "base", "")) or _text(manifest.get("base_sha")),
            executed,
        )
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


def _target_endpoint_config(
    cfg: dict,
    component: str,
) -> tuple[str, dict, str, str, str]:
    access = cfg.get("access") or {}
    project = access.get("project") or {}
    lane = project.get(component) or {}
    if isinstance(lane, dict) and any(_is_explicit_fill(value) for value in lane.values()):
        base_url = _require_http_url(f"access.project.{component}.url", lane.get("url"))
        return f"access.project.{component}", lane, base_url, "username", "password"
    legacy = cfg.get("target_env") or {}
    base_field = f"{component}_base_url"
    base_url = _require_http_url(f"target_env.{base_field}", legacy.get(base_field))
    return (
        "target_env",
        legacy,
        base_url,
        f"{component}_username",
        f"{component}_password",
    )


def _wait_for_health_url(scope: str, url: str, timeout_s: int) -> None:
    _require_http_url(f"{scope} health URL", url)
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


def cmd_wait_health(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    scope = args.scope
    requested_timeout = int(getattr(args, "timeout_sec", 0) or 0)
    if scope == "runtime":
        runtime_cfg = cfg.get("runtime") or {}
        base_url = _require_http_url("runtime.health_base_url", runtime_cfg.get("health_base_url"))
        url = _join_url(base_url, runtime_cfg.get("health_path"))
        timeout_s = requested_timeout or int(runtime_cfg.get("startup_timeout_sec") or 120)
    else:
        target_cfg = cfg.get("target_env") or {}
        explicit_path = _text(getattr(args, "path", ""))
        legacy_base = _text(target_cfg.get("health_base_url"))
        legacy_path = _text(target_cfg.get("health_path"))
        if explicit_path:
            component = _text(getattr(args, "component", "")) or "backend"
            _, _, base_url, _, _ = _target_endpoint_config(cfg, component)
            url = _join_url(base_url, explicit_path)
        elif legacy_base and legacy_path:
            base_url = _require_http_url("target_env.health_base_url", legacy_base)
            url = _join_url(base_url, legacy_path)
        else:
            raise APError(
                "Target health check requires --component and --path for access.project, "
                "or legacy target_env.health_base_url plus target_env.health_path."
            )
        timeout_s = requested_timeout or int((cfg.get("jenkins") or {}).get("deploy_timeout_sec") or 120)
    _wait_for_health_url(scope, url, timeout_s)


def cmd_verify_target(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    requested = {
        "backend": list(args.backend_path or []),
        "frontend": list(args.frontend_path or []),
    }
    target_cfg = cfg.get("target_env") or {}
    legacy_health_base = _text(target_cfg.get("health_base_url"))
    legacy_health_path = _text(target_cfg.get("health_path"))
    if not any(requested.values()) and not (legacy_health_base and legacy_health_path):
        raise APError(
            "verify-target requires --backend-path or --frontend-path when no legacy target health check is configured."
        )

    planned_checks: list[tuple[str, str, dict[str, str]]] = []
    for component in ("backend", "frontend"):
        paths = requested[component]
        if not paths:
            continue
        section_name, section_cfg, base_url, user_field, secret_field = _target_endpoint_config(
            cfg,
            component,
        )
        headers: dict[str, str] = {}
        if bool(getattr(args, f"{component}_basic_auth")):
            username = _text(section_cfg.get(user_field))
            if not _is_explicit_fill(username):
                raise APError(f"Missing {section_name}.{user_field} for basic auth.")
            password = _resolve_secret(section_name, section_cfg, secret_field)
            headers = _basic_auth_header(username, password)
        for path in paths:
            url = _join_url(base_url, path)
            _require_http_url(f"{component} target URL", url)
            planned_checks.append((component, url, headers))

    health_url = ""
    if legacy_health_base or legacy_health_path:
        if not (legacy_health_base and legacy_health_path):
            raise APError(
                "Legacy target health config requires both target_env.health_base_url and target_env.health_path."
            )
        health_base = _require_http_url("target_env.health_base_url", legacy_health_base)
        health_url = _join_url(health_base, legacy_health_path)

    if health_url:
        timeout_s = int((cfg.get("jenkins") or {}).get("deploy_timeout_sec") or 120)
        _wait_for_health_url("target", health_url, timeout_s)

    checks: List[str] = []
    for component, url, headers in planned_checks:
        status, body = _http_get(url, headers=headers, timeout_s=10)
        if not (200 <= status < 400):
            raise APError(
                f"{component.title()} target verification failed: {url} -> {status}\n{body[:400]}"
            )
        checks.append(f"{component}:{url}->{status}")

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

    configured_components = _configured_jenkins_components(cfg)
    if configured_components:
        requested = _text(getattr(args, "component", "all")).lower() or "all"
        selected = ("frontend", "backend") if requested == "all" else (requested,)
        checked: list[str] = []
        for component in selected:
            lane = _jenkins_access_cfg(cfg, component)
            _require_http_url(f"access.jenkins.{component}.url", lane.get("url"))
            if not _is_explicit_fill(lane.get("username")):
                raise APError(f"Missing access.jenkins.{component}.username.")
            _resolve_secret(f"access.jenkins.{component}", lane, "password")
            checked.append(component)
        _record_evidence(
            repo,
            cfg,
            "verify_jenkins",
            "pass",
            {"jenkinsfile": str(jenkinsfile), "components": checked},
        )
        print(f"[verify-jenkins] OK: {jenkinsfile} components={','.join(checked)}")
        return

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


def cmd_doctor(args: argparse.Namespace) -> dict | None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    collect = bool(getattr(args, "collect", False))
    quiet = bool(getattr(args, "quiet", False))
    record = bool(getattr(args, "record", True))
    workflow_cfg = (cfg.get("workflow") or {})
    project_cfg = (cfg.get("project") or {})
    docs_cfg = (cfg.get("docs") or {})
    runtime_cfg = (cfg.get("runtime") or {})
    structure_cfg = _structure_cfg(cfg)
    concurrency_cfg = _concurrency_cfg(cfg)

    missing: List[str] = []
    validation_errors: List[str] = []
    advisories: List[str] = []
    validation_errors.extend(_workflow_policy_issues(repo, cfg))

    raw_mode = workflow_cfg.get("mode", "dev")
    raw_profile = workflow_cfg.get("profile", "auto")
    raw_completion = workflow_cfg.get("completion", "")
    if not isinstance(raw_mode, str):
        validation_errors.append("workflow.mode must be a string")
    if not isinstance(raw_profile, str):
        validation_errors.append("workflow.profile must be a string")
    if not isinstance(raw_completion, str):
        validation_errors.append("workflow.completion must be a string")
    mode = raw_mode.strip().lower() if isinstance(raw_mode, str) else ""
    profile = raw_profile.strip().lower() if isinstance(raw_profile, str) else ""
    completion = raw_completion.strip().lower() if isinstance(raw_completion, str) else ""
    skill_version = _text(workflow_cfg.get("skill_version"))
    if mode != "dev":
        missing.append("workflow.mode (must be dev; external verification is owner-managed)")
    if profile not in _WORKFLOW_PROFILES:
        missing.append("workflow.profile (must be auto, micro, standard, or high-risk)")
    if completion != "push":
        missing.append("workflow.completion (must be push)")
    if skill_version.startswith("4.1") and _text(docs_cfg.get("framework")) != "engineering-centered":
        missing.append("docs.framework (must be engineering-centered for auto-coding-skill 4.1)")
    raw_isolation = concurrency_cfg.get("isolation", "adaptive")
    if not isinstance(raw_isolation, str):
        validation_errors.append("concurrency.isolation must be a string")
        isolation = ""
    else:
        isolation = raw_isolation.strip().lower() or "adaptive"
    if isolation and isolation not in {"adaptive", "worktree"}:
        validation_errors.append(
            "concurrency.isolation must be adaptive or worktree; legacy shared-checkout mode is unsupported"
        )
    raw_branch_prefix = concurrency_cfg.get("branch_prefix", "codex/")
    if not isinstance(raw_branch_prefix, str):
        validation_errors.append("concurrency.branch_prefix must be a string")
        branch_prefix = ""
    else:
        branch_prefix = raw_branch_prefix.strip() or "codex/"
    if branch_prefix and not branch_prefix.endswith("/"):
        validation_errors.append("concurrency.branch_prefix must end with '/'")
    elif branch_prefix and run(
        ["git", "check-ref-format", "--branch", f"{branch_prefix}TASK"],
        cwd=repo,
        check=False,
    ).returncode != 0:
        validation_errors.append("concurrency.branch_prefix does not form a valid Git branch")
    raw_project_name = project_cfg.get("name")
    if raw_project_name is not None and not isinstance(raw_project_name, str):
        validation_errors.append("project.name must be a string")
    if not isinstance(raw_project_name, str) or not raw_project_name.strip():
        missing.append("project.name")
    missing.extend(_access_config_issues(cfg))
    raw_enforcement = structure_cfg.get("enforcement")
    if raw_enforcement is not None and not isinstance(raw_enforcement, str):
        validation_errors.append("structure.enforcement must be a string")
        enforcement = ""
    else:
        enforcement = raw_enforcement.strip().lower() if isinstance(raw_enforcement, str) else ""
    if enforcement and enforcement not in {"advisory", "blocking"}:
        validation_errors.append("structure.enforcement must be advisory or blocking")
    raw_block_warnings = structure_cfg.get("block_warnings")
    if "block_warnings" in structure_cfg and not isinstance(raw_block_warnings, bool):
        validation_errors.append("structure.block_warnings must be a boolean")
    elif raw_block_warnings is True and enforcement != "blocking":
        advisories.append(
            "structure.block_warnings has no effect unless structure.enforcement=blocking"
        )
    gate_cfg = _gate_cfg(cfg)
    if "full_on" in gate_cfg:
        validation_errors.append("gate.full_on is legacy automatic full escalation; run autocoding init")
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
        if "scope" in rule:
            rules_valid = False
            validation_errors.append(
                f"gate.rules[{index}].scope is legacy automatic gate escalation; run autocoding init"
            )
        if "commands" in rule:
            rules_valid = False
            validation_errors.append(
                f"gate.rules[{index}].commands is legacy automatic gate escalation; run autocoding init"
            )

    risk_rules = _risk_cfg(cfg).get("rules") or []
    if not isinstance(risk_rules, list):
        validation_errors.append("risk.rules must be a list")
        risk_rules = []
    for index, rule in enumerate(risk_rules):
        if not isinstance(rule, dict):
            validation_errors.append(f"risk.rules[{index}] must be a mapping")
            continue
        if not _as_list(rule.get("paths")):
            validation_errors.append(f"risk.rules[{index}].paths must not be empty")
        rule_profile = _text(rule.get("profile")).lower()
        if rule_profile and rule_profile not in _WORKFLOW_PROFILES - {"auto"}:
            validation_errors.append(
                f"risk.rules[{index}].profile must be micro, standard, or high-risk"
            )

    validation_cfg = _validation_cfg(cfg)
    raw_on_unmapped = validation_cfg.get("on_unmapped", "error")
    if not isinstance(raw_on_unmapped, str):
        validation_errors.append("validation.on_unmapped must be a string")
        on_unmapped = ""
    else:
        on_unmapped = raw_on_unmapped.strip().lower() or "error"
    if on_unmapped and on_unmapped not in {"error", "fallback"}:
        validation_errors.append("validation.on_unmapped must be error or fallback")
    try:
        final_budget = _final_gate_budget(cfg)
        if final_budget["command_seconds"] > _RECOMMENDED_FINAL_COMMAND_SECONDS:
            advisories.append(
                "validation.max_command_seconds exceeds the recommended 120s default; "
                "keep the affected-scope route targeted"
            )
        if final_budget["total_seconds"] > _RECOMMENDED_FINAL_TOTAL_SECONDS:
            advisories.append(
                "validation.max_total_seconds exceeds the recommended 180s default; "
                "keep the final gate bounded to affected scope"
            )
    except APError as exc:
        validation_errors.append(str(exc))
        final_budget = {
            "command_seconds": _RECOMMENDED_FINAL_COMMAND_SECONDS,
            "total_seconds": _RECOMMENDED_FINAL_TOTAL_SECONDS,
        }
    routes = validation_cfg.get("routes") or []
    if not isinstance(routes, list):
        validation_errors.append("validation.routes must be a list")
        routes = []
    for index, route in enumerate(routes):
        if not isinstance(route, dict):
            validation_errors.append(f"validation.routes[{index}] must be a mapping")
            continue
        if not _as_list(route.get("paths")):
            validation_errors.append(f"validation.routes[{index}].paths must not be empty")
        commands = [_command_name(item) for item in _as_list(route.get("commands"))]
        if not commands:
            validation_errors.append(f"validation.routes[{index}].commands must not be empty")
        for command_name in commands:
            if command_name and not _configured_command(cfg, command_name):
                validation_errors.append(
                    f"validation.routes[{index}] references missing commands.{command_name}"
                )
        if "timeout_seconds" in route:
            try:
                route_timeout = _positive_seconds(
                    route.get("timeout_seconds"),
                    final_budget["command_seconds"],
                    f"validation.routes[{index}].timeout_seconds",
                )
                if route_timeout > final_budget["command_seconds"]:
                    advisories.append(
                        f"validation.routes[{index}].timeout_seconds exceeds max_command_seconds "
                        "and will be capped"
                    )
            except APError as exc:
                validation_errors.append(str(exc))
    fallback_name = _command_name(validation_cfg.get("fallback_command"))
    if on_unmapped == "fallback" and not fallback_name:
        validation_errors.append(
            "validation.fallback_command is required when validation.on_unmapped=fallback"
        )
    if fallback_name and not _configured_command(cfg, fallback_name):
        validation_errors.append(
            f"validation.fallback_command references missing commands.{fallback_name}"
        )
    if not routes and not (_configured_command(cfg, "gate_changed") or fallback_name):
        validation_errors.append(
            "validation.routes is empty and no 3.x commands.gate_changed compatibility fallback exists"
        )
    tracked_validation_paths = [
        path
        for path in _tracked_files(repo)
        if not _path_matches(
            path,
            [
                "*.md",
                "docs/**",
                ".agents/**",
                ".local/**",
                "AGENTS.md",
            ],
        )
    ]
    if tracked_validation_paths:
        try:
            tracked_plan = _validation_plan(cfg, tracked_validation_paths)
            _validate_validation_plan(cfg, tracked_plan)
        except APError as exc:
            validation_errors.append(f"tracked validation coverage: {exc}")

    repo_docs: dict[str, Path] = {}
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

    version_match = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)", skill_version)
    integrity_required = bool(
        version_match
        and tuple(int(part) for part in version_match.groups()) >= (4, 1, 9)
    )
    manifest_exists = (repo / ".agents" / "managed-install.json").is_file()
    if integrity_required or manifest_exists:
        integrity = verify_managed_install(
            repo,
            mode="project",
            expected_version=skill_version or None,
        )
        validation_errors.extend(
            f"install integrity: {issue}" for issue in integrity["errors"]
        )

    if (
        isinstance(raw_project_name, str)
        and _FEEDBACK_SAFE_ID_RE.fullmatch(raw_project_name.strip())
        and _FEEDBACK_SEMVER_RE.fullmatch(skill_version)
        and (repo / "docs" / "skill-feedback" / "reports").exists()
    ):
        try:
            feedback = _feedback_collection_result([str(repo)])
        except APError:
            advisories.append(
                "Skill feedback metadata needs maintenance; run "
                "autocoding feedback --projects . --json for the bounded diagnostic"
            )
        else:
            if feedback["action_required_count"]:
                advisories.append(
                    f"{feedback['action_required_count']} Skill feedback report(s) need recheck, "
                    "closure, upgrade, or project-overlay routing; run "
                    "autocoding feedback --projects . --json"
                )

    missing.extend(validation_errors)

    if missing:
        if record:
            _record_evidence(repo, cfg, "doctor", "fail", {"issues": missing})
        if collect:
            return {"issues": missing, "advisories": advisories}
        raise APError("Doctor found blocking config issues:\n- " + "\n- ".join(missing))

    if record:
        _record_evidence(
            repo,
            cfg,
            "doctor",
            "pass",
            {"mode": mode, "completion": completion, "access_fields": len(_REQUIRED_ACCESS_FIELDS)},
        )
    if collect:
        return {"issues": [], "advisories": advisories}
    if not quiet:
        for advisory in advisories:
            print(f"[doctor] WARN: {advisory}")
        print("[doctor] OK")
    return None


def cmd_verify_jenkins_build(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    cfg = _load_cfg(repo)
    jenkins_cfg = (cfg.get("jenkins") or {})
    component = _resolve_jenkins_component(
        cfg,
        _text(getattr(args, "component", "")),
        _text(args.job_url),
    )
    if component:
        lane = _jenkins_access_cfg(cfg, component)
        _require_http_url(f"access.jenkins.{component}.url", lane.get("url"))
        _jenkins_auth_config(cfg, component)
        _resolve_secret(f"access.jenkins.{component}", lane, "password")
    git_ref = str(args.git_ref or "HEAD").strip()
    candidate_job_urls = _resolve_jenkins_job_candidates(
        cfg,
        repo,
        git_ref=git_ref,
        job_name=args.job_name,
        job_url=args.job_url,
        multibranch_root_job=args.multibranch_root_job,
        branch_name=args.branch_name,
        component=component,
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
        or (_jenkins_access_cfg(cfg, component).get("url") if component else "")
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
                payload = _jenkins_api_get_json(
                    api_url,
                    cfg,
                    allow_404=True,
                    component=component,
                )
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
            payload = _jenkins_api_get_json(
                api_url,
                cfg,
                allow_404=True,
                component=component,
            )
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
    _require_control_checkout(repo)
    task_id = _validate_task_id(args.task_id)
    owned_paths = sorted({_normalize_owned_path(item) for item in (args.owned_path or [])})
    if not owned_paths:
        raise APError("task-start requires at least one --owned-path.")
    if _is_terminal_ledger_maintenance(owned_paths):
        raise APError(
            "Pure taskbook/closure/archive reconciliation is terminal maintenance and must not "
            "create another task lifecycle. Run the targeted document check, commit once, and push."
        )
    writer_count = max(1, int(getattr(args, "writers", 1) or 1))
    if writer_count != 1:
        raise APError(
            "task-start creates exactly one writer lease and one worktree. Start each parallel "
            "writer as its own task ID; use --writers only with classify for planning."
        )
    continue_direct = bool(getattr(args, "continue_direct", False))
    direct_claim_id = _text(getattr(args, "direct_claim", ""))
    explicit_lifecycle = bool(
        getattr(args, "isolated", False)
        or getattr(args, "review_required", False)
        or getattr(args, "force_lifecycle", False)
        or continue_direct
    )
    # Validate legacy workflow policy before planning reads gate/risk rules so
    # task-start reports the complete migration set and remains zero-write.
    _require_workflow_policy_clean(repo, cfg)
    preflight_plan = _resolve_execution_plan(
        cfg,
        repo,
        planned_paths=owned_paths,
        parallel_writers=writer_count,
        requested_task_kind="change",
        continue_direct=continue_direct,
        direct_claim_id=direct_claim_id,
    )
    if continue_direct and preflight_plan["execution_mode"] != "direct":
        detail = ", ".join(preflight_plan["dirty_outside_plan"]) or "policy or active-writer conflict"
        raise APError(
            "Cannot continue the existing direct task because isolation is still required: "
            + detail
        )
    if not preflight_plan["mechanism_plan"]["lifecycle_required"] and not explicit_lifecycle:
        raise APError(
            "This clean serial task does not need a machine task lifecycle. Work directly on "
            "the current branch, run the routed final gate, commit, and push. Use task-start "
            "only when classify requires isolation/review or the user explicitly requests it."
        )

    owner = _actor_id(args, "owner")
    runtime_actor = _text(os.environ.get("CODEX_THREAD_ID"))
    explicit_writer = _text(getattr(args, "writer", ""))
    writer = _actor_id(args, "writer") if runtime_actor or explicit_writer else owner

    configured_isolation = _task_isolation(cfg)
    access_issues = _access_config_issues(cfg)
    if access_issues:
        raise APError(
            "Project initialization is incomplete; fill docs/project/auto-coding-skill.yaml before starting work:\n- "
            + "\n- ".join(access_issues)
        )
    remote, target_branch, base_ref = _task_remote_and_target(cfg, args)
    concurrency_cfg = _concurrency_cfg(cfg)
    timeout_s = float(concurrency_cfg.get("lock_timeout_sec") or 30)

    with (
        _repo_lock(repo, "integration", timeout_s=timeout_s),
        _repo_lock(repo, "task-registry", timeout_s=timeout_s),
    ):
        for claim in _active_direct_claims(repo):
            if _text(claim.get("claim_id")) == direct_claim_id:
                continue
            claim_paths = list(claim.get("owned_paths") or [])
            if _owned_paths_overlap(owned_paths, claim_paths):
                raise APError(
                    "Owned paths overlap an active direct claim held by "
                    f"{_text(claim.get('owner')) or '(unknown)'}: "
                    + ", ".join(claim_paths)
                )
        if _read_json_object(_task_registry_path(repo, task_id)):
            raise APError(f"Task is already registered: {task_id}")

        task_uuid = uuid.uuid4().hex

        if not getattr(args, "no_fetch", False) and base_ref.startswith(f"{remote}/"):
            _fetch_target(repo, remote, target_branch)
        base_sha = _resolve_commit(repo, base_ref)
        registry_dir = _task_state_root(repo) / "tasks"
        for manifest_path in sorted(registry_dir.glob("*.json")) if registry_dir.exists() else []:
            active_manifest = _read_json_object(manifest_path) or {}
            if _text(active_manifest.get("state")) in {"integrated", "cleanup-pending"}:
                continue
            active_owned = active_manifest.get("owned_paths") or []
            if isinstance(active_owned, list) and _owned_paths_overlap(owned_paths, active_owned):
                active_id = _text(active_manifest.get("task_id")) or manifest_path.stem
                raise APError(
                    f"Owned paths overlap active task {active_id}: "
                    + ", ".join(active_owned)
                    + ". Split ownership into non-overlapping task units or finish the active writer first."
                )
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
        plan = _resolve_execution_plan(
            cfg,
            repo,
            planned_paths=owned_paths,
            parallel_writers=writer_count,
            requested_task_kind="change",
            continue_direct=continue_direct,
            direct_claim_id=direct_claim_id,
        )
        if not plan["mechanism_plan"]["lifecycle_required"] and not explicit_lifecycle:
            raise APError(
                "This clean serial task does not need a machine task lifecycle. Work directly on "
                "the current branch, run the routed final gate, commit, and push. Use task-start "
                "only when classify requires isolation/review or the user explicitly requests it."
            )
        review_required = bool(getattr(args, "review_required", False) or plan["review_required"])
        review_depth, review_timeout_seconds = _normalized_task_review_policy(
            review_required,
            plan.get("review_depth"),
            getattr(args, "review_depth", ""),
        )
        registry_dir = _task_state_root(repo) / "tasks"
        other_active = any(
            _text((payload or {}).get("state"))
            not in {"", "integrated", "cleanup-pending"}
            for payload in (
                _read_json_object(path)
                for path in sorted(registry_dir.glob("*.json"))
            )
        ) if registry_dir.exists() else False
        current_branch = _current_branch(repo)
        task_paths = _task_commit_paths(repo)
        direct_changes_owned = bool(
            continue_direct
            and all(_path_is_owned(path, owned_paths) for path in task_paths)
        )
        direct = bool(
            configured_isolation == "adaptive"
            and not bool(getattr(args, "isolated", False))
            and writer_count == 1
            and not other_active
            and (not task_paths or direct_changes_owned)
            and current_branch
            and current_branch == target_branch
        )
        if continue_direct and not direct:
            raise APError(
                "Cannot register continued direct work on this checkout; verify target branch, "
                "owned paths, active writers, and concurrency.isolation"
            )
        if direct:
            direct_base = _resolve_commit(repo, "HEAD")
            manifest = {
                "schema": 3,
                "skill_version": _text((cfg.get("workflow") or {}).get("skill_version")),
                "execution_mode": "direct",
                "review_required": review_required,
                "task_id": task_id,
                "task_uuid": task_uuid,
                "owner": owner,
                "base_ref": "HEAD",
                "base_sha": direct_base,
                "remote": remote,
                "target_branch": current_branch,
                "task_branch": current_branch,
                "worktree_path": str(repo.resolve()),
                "control_worktree_path": str(repo.resolve()),
                "cleanup_policy": _cleanup_policy(cfg),
                "state": "active",
                "created_at": _now_iso(),
                "initial_untracked": [],
                "owned_paths": owned_paths,
                "scope_revision": 1,
                "effective_profile": plan["profile"],
                "design_required": bool(plan["design_required"]),
                "review_depth": review_depth,
                "review_timeout_seconds": review_timeout_seconds,
                "scope_history": [],
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
                    "diff_base": direct_base,
                    "diff_head": "",
                    "diff_fingerprint": "",
                    "reviewer": "",
                    "reviewed_at": "",
                    "reason": "review required" if review_required else "review not required",
                },
                "claimed_paths": [],
                "remote_task_tip": "",
                "common_submodule_config": {},
            }
            _save_task_manifest(repo, manifest)
            _consume_direct_claim(repo, direct_claim_id)
            print(f"[task-start] task={task_id}")
            print("[task-start] execution_mode=direct")
            print(f"[task-start] branch={current_branch}")
            print(f"[task-start] base=HEAD@{direct_base}")
            print(f"[task-start] worktree={repo}")
            print("[task-start] no temporary branch or worktree created")
            return

        common_submodule_config = _common_submodule_config(repo)
        _seed_control_submodule_config(repo)
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
            "schema": 3,
            "skill_version": _text((cfg.get("workflow") or {}).get("skill_version")),
            "execution_mode": "isolated",
            "review_required": review_required,
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
            "scope_revision": 1,
            "effective_profile": plan["profile"],
            "design_required": bool(plan["design_required"]),
            "review_depth": review_depth,
            "review_timeout_seconds": review_timeout_seconds,
            "scope_history": [],
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

    print(f"[task-start] task={task_id}")
    print("[task-start] execution_mode=isolated")
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
    base_sha = _text(manifest.get("base_sha"))
    has_task_commits = bool(
        tip
        and base_sha
        and tip != base_sha
        and run(
            ["git", "merge-base", "--is-ancestor", base_sha, tip],
            cwd=repo,
            check=False,
        ).returncode
        == 0
    )
    merged = bool(
        has_task_commits
        and _git_ref_exists(repo, remote_ref)
        and run(["git", "merge-base", "--is-ancestor", tip, remote_ref], cwd=repo, check=False).returncode == 0
    )
    review = manifest.get("review") or {}
    deadline_at = _text(review.get("deadline_at"))
    review_seconds_remaining: Optional[int] = None
    review_deadline_expired = False
    if deadline_at:
        try:
            remaining = (
                _parse_iso_timestamp(deadline_at, "deadline_at")
                - _dt.datetime.now(_dt.timezone.utc)
            ).total_seconds()
            seconds = int(remaining)
            review_seconds_remaining = max(0, seconds)
            review_deadline_expired = remaining < 0
        except APError:
            review_deadline_expired = True
            review_seconds_remaining = 0
    return {
        **manifest,
        "worktree_exists": worktree.exists(),
        "dirty": bool(_git_status(worktree)) if worktree.exists() else False,
        "local_branch_exists": bool(tip),
        "tip": tip,
        "has_task_commits": has_task_commits,
        "merged_into_target": merged,
        "review_deadline_expired": review_deadline_expired,
        "review_seconds_remaining": review_seconds_remaining,
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
            f"dirty={str(status['dirty']).lower()} commits="
            f"{str(status['has_task_commits']).lower()} "
            f"merged={str(status['merged_into_target']).lower()}"
        )


def _task_lifecycle_context(repo: Path, cfg: dict, task_id: str) -> tuple[Path, Path, dict]:
    active = _active_task_manifest(repo)
    if active:
        manifest = _require_task_context(repo, cfg, task_id)
        return Path(_text(manifest.get("control_worktree_path"))).resolve(), repo, manifest
    manifest = _load_task_manifest(repo, task_id)
    _require_control_checkout(repo, manifest)
    return repo, Path(_text(manifest.get("worktree_path"))).resolve(), manifest


def cmd_task_scope_add(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    task_id = _validate_task_id(args.task_id)
    additions = sorted({_normalize_owned_path(item) for item in (args.owned_path or [])})
    if not additions:
        raise APError("task-scope-add requires at least one --owned-path.")
    control_repo, worktree, _ = _task_lifecycle_context(repo, cfg, task_id)
    timeout_s = float(_concurrency_cfg(cfg).get("lock_timeout_sec") or 30)
    result: dict = {}
    with (
        _repo_lock(control_repo, "integration", timeout_s=timeout_s),
        _repo_lock(control_repo, "task-registry", timeout_s=timeout_s),
        _repo_lock(control_repo, "direct-claim", timeout_s=timeout_s),
        _repo_lock(control_repo, f"task-{task_id}", timeout_s=timeout_s),
    ):
        manifest = _load_task_manifest(control_repo, task_id)
        _require_current_writer(manifest, args)
        if int(manifest.get("schema") or 0) < 3:
            raise APError("task-scope-add requires a schema-3 task created by the current workflow.")
        if _text(manifest.get("state")) != "active":
            raise APError(
                f"Task {task_id} cannot expand scope in state={manifest.get('state')}; start a new task."
            )
        lease_generation = int((manifest.get("writer_lease") or {}).get("generation") or 0)
        requested_generation = getattr(args, "lease_generation", None)
        if requested_generation is not None and requested_generation != lease_generation:
            raise APError(
                f"Writer lease generation changed: expected={requested_generation}, current={lease_generation}."
            )
        if not worktree.exists():
            raise APError(f"Task worktree is missing: {worktree}")
        if _resolve_commit(worktree, "HEAD") != _text(manifest.get("base_sha")):
            raise APError("task-scope-add is allowed only before the task creates a commit.")
        if _text(manifest.get("last_commit")) or _text(manifest.get("remote_task_tip")):
            raise APError("task-scope-add cannot extend a task that already committed or pushed work.")

        current = sorted({_normalize_owned_path(item) for item in manifest.get("owned_paths") or []})
        new_paths = [path for path in additions if not _path_is_owned(path, current)]
        if not new_paths:
            result = {
                "task_id": task_id,
                "status": "noop",
                "scope_revision": int(manifest.get("scope_revision") or 1),
                "owned_paths": current,
            }
        else:
            proposed = sorted(set(current) | set(new_paths))
            for claim in _active_direct_claims(control_repo):
                claim_paths = list(claim.get("owned_paths") or [])
                if _owned_paths_overlap(proposed, claim_paths):
                    raise APError(
                        "Expanded scope overlaps active direct claim held by "
                        f"{_text(claim.get('owner')) or '(unknown)'}: "
                        + ", ".join(claim_paths)
                    )
            registry_dir = _task_state_root(control_repo) / "tasks"
            for path in sorted(registry_dir.glob("*.json")) if registry_dir.exists() else []:
                other = _read_json_object(path) or {}
                if _text(other.get("task_id")) == task_id:
                    continue
                if _text(other.get("state")) in {"", "integrated", "cleanup-pending"}:
                    continue
                other_owned = other.get("owned_paths") or []
                if isinstance(other_owned, list) and _owned_paths_overlap(proposed, other_owned):
                    raise APError(
                        f"Expanded scope overlaps active task {_text(other.get('task_id')) or path.stem}: "
                        + ", ".join(other_owned)
                    )

            worktree_cfg = _load_cfg(worktree)
            existing_unowned = _task_unowned_paths(worktree, worktree_cfg, manifest)
            implicit_adoptions = sorted(path for path in existing_unowned if path not in set(new_paths))
            if implicit_adoptions:
                raise APError(
                    "Existing unowned changes must be added as exact --owned-path values before scope expansion:\n- "
                    + "\n- ".join(implicit_adoptions)
                )
            changed_paths = _task_changed_paths_from_base(
                worktree,
                _text(manifest.get("base_sha")),
            )
            plan = _resolve_execution_plan(
                worktree_cfg,
                worktree,
                changed_paths=changed_paths,
                planned_paths=proposed,
                intent=_text(getattr(args, "intent", "")),
                requested_task_kind="change",
            )
            old_profile = _text(manifest.get("effective_profile")) or (
                "high-risk" if bool(manifest.get("review_required")) else "standard"
            )
            planned_profile = _text(plan.get("profile")) or "standard"
            effective_profile = (
                planned_profile
                if _PROFILE_RANK[planned_profile] > _PROFILE_RANK[old_profile]
                else old_profile
            )
            old_manifest = json.loads(json.dumps(manifest))
            revision = int(manifest.get("scope_revision") or 1) + 1
            manifest["owned_paths"] = proposed
            manifest["scope_revision"] = revision
            manifest["effective_profile"] = effective_profile
            manifest["review_required"] = bool(
                manifest.get("review_required")
                or plan.get("review_required")
                or bool(getattr(args, "review_required", False))
            )
            manifest["design_required"] = bool(
                manifest.get("design_required") or plan.get("design_required")
            )
            review_depth, review_timeout_seconds = _normalized_task_review_policy(
                bool(manifest["review_required"]),
                manifest.get("review_depth"),
                plan.get("review_depth"),
            )
            manifest["review_depth"] = review_depth
            manifest["review_timeout_seconds"] = review_timeout_seconds
            manifest["claimed_paths"] = []
            history = list(manifest.get("scope_history") or [])
            history.append(
                {
                    "revision": revision,
                    "added_paths": new_paths,
                    "adopted_dirty_paths": existing_unowned,
                    "actor": _text(getattr(args, "writer", ""))
                    or _text(os.environ.get("CODEX_THREAD_ID")),
                    "updated_at": _now_iso(),
                    "previous_profile": old_profile,
                    "effective_profile": effective_profile,
                }
            )
            manifest["scope_history"] = history
            _invalidate_task_review(manifest, "task scope expanded; review and final gate must run again")
            _clear_final_gate_receipt(worktree)
            try:
                _save_task_manifest(control_repo, manifest, strict_worktree=True)
            except Exception:
                _save_task_manifest(control_repo, old_manifest)
                raise
            registered = _load_task_manifest(control_repo, task_id)
            mirrored = _read_json_object(_worktree_manifest_path(worktree)) or {}
            for field in ("task_uuid", "scope_revision", "owned_paths", "review_required"):
                if registered.get(field) != mirrored.get(field):
                    raise APError(f"Task scope manifest synchronization failed for field: {field}")
            result = {
                "task_id": task_id,
                "status": "expanded",
                "scope_revision": revision,
                "owned_paths": proposed,
                "added_paths": new_paths,
                "effective_profile": effective_profile,
                "review_required": manifest["review_required"],
                "design_required": manifest["design_required"],
            }
    if bool(getattr(args, "json", False)):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["status"] == "noop":
        print(
            f"[task-scope-add] NOOP task={task_id} "
            f"scope_revision={result['scope_revision']}"
        )
    else:
        print(
            f"[task-scope-add] OK task={task_id} scope_revision={result['scope_revision']} "
            f"profile={result['effective_profile']} review_required="
            f"{str(result['review_required']).lower()} added={','.join(result['added_paths'])}"
        )


def _parse_iso_timestamp(value: object, field: str) -> _dt.datetime:
    raw = _text(value)
    try:
        parsed = _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise APError(f"Invalid {field} timestamp in review assignment: {raw!r}.") from exc
    if parsed.tzinfo is None:
        raise APError(f"Review assignment {field} must include a timezone.")
    return parsed.astimezone(_dt.timezone.utc)


def _review_assignment_path(control_repo: Path, task_id: str, fingerprint: str) -> Path:
    if not _REVIEW_SHA256_RE.fullmatch(_text(fingerprint)):
        raise APError("Review fingerprint must be a lowercase SHA-256 value.")
    return _task_review_dir(control_repo, task_id) / f"{fingerprint}.assignment.json"


def _review_diff_artifact_path(control_repo: Path, task_id: str, fingerprint: str) -> Path:
    if not _REVIEW_SHA256_RE.fullmatch(_text(fingerprint)):
        raise APError("Review fingerprint must be a lowercase SHA-256 value.")
    return _task_review_dir(control_repo, task_id) / f"{fingerprint}.patch"


def _guard_review_file_parent(path: Path) -> None:
    task_dir = path.parent
    review_root = task_dir.parent
    state_root = review_root.parent
    common_dir = state_root.parent.resolve()
    if review_root.name != "reviews" or state_root.name != "auto-coding-skill":
        raise APError(f"Review file path is outside canonical Git-local storage: {path}")
    for directory in (state_root, review_root, task_dir):
        _guard_review_directory(directory, common_dir, create=False)
    try:
        task_dir.resolve().relative_to(common_dir)
    except (OSError, ValueError) as exc:
        raise APError(f"Review file path escapes the Git common directory: {path}") from exc
    if path.is_symlink():
        raise APError(f"Refusing symlinked Git-local review file: {path}")


def _write_private_bytes(path: Path, payload: bytes) -> None:
    _guard_review_file_parent(path)
    temporary_name = f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    if os.name == "posix":
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        directory_fd = -1
        try:
            directory_fd = os.open(path.parent, directory_flags)
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=directory_fd,
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(
                temporary_name,
                path.name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
            os.fsync(directory_fd)
        except OSError as exc:
            if directory_fd >= 0:
                try:
                    os.unlink(temporary_name, dir_fd=directory_fd)
                except OSError:
                    pass
            raise APError(f"Cannot protect Git-local review state: {path}: {exc}") from exc
        finally:
            if directory_fd >= 0:
                os.close(directory_fd)
        return

    temporary = path.with_name(temporary_name)
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise APError(f"Cannot protect Git-local review state: {path}: {exc}") from exc


def _read_private_review_file(path: Path, label: str) -> bytes:
    _guard_review_file_parent(path)
    if os.name == "posix":
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        directory_fd = -1
        file_fd = -1
        try:
            directory_fd = os.open(path.parent, directory_flags)
            file_fd = os.open(
                path.name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
            metadata = os.fstat(file_fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise APError(f"Review {label} must be a regular Git-local file: {path}")
            if stat.S_IMODE(metadata.st_mode) != 0o600:
                raise APError(f"Review {label} must use mode 0600: {path}")
            with os.fdopen(file_fd, "rb") as handle:
                file_fd = -1
                return handle.read()
        except APError:
            raise
        except OSError as exc:
            raise APError(f"Cannot read review {label}: {path}: {exc}") from exc
        finally:
            if file_fd >= 0:
                os.close(file_fd)
            if directory_fd >= 0:
                os.close(directory_fd)

    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
            raise APError(f"Review {label} must be a regular Git-local file: {path}")
        return path.read_bytes()
    except APError:
        raise
    except OSError as exc:
        raise APError(f"Cannot read review {label}: {path}: {exc}") from exc


def _read_verified_private_review_file(path: Path, expected_sha256: str, label: str) -> bytes:
    if not _REVIEW_SHA256_RE.fullmatch(_text(expected_sha256)):
        raise APError(f"Review {label} has an invalid SHA-256 binding.")
    payload = _read_private_review_file(path, label)
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != expected_sha256:
        raise APError(
            f"Review {label} SHA-256 mismatch: expected={expected_sha256}, actual={actual_sha256}."
        )
    return payload


def _review_assignment_file_sha256(path: Path) -> str:
    return hashlib.sha256(_read_private_review_file(path, "assignment")).hexdigest()


def _read_private_review_json(path: Path, label: str) -> Optional[dict]:
    try:
        payload = json.loads(_read_private_review_file(path, label).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _load_bound_review_assignment(
    control_repo: Path,
    manifest: dict,
    assignment_path: Path,
) -> dict:
    review = manifest.get("review") or {}
    fingerprint = _text(review.get("diff_fingerprint"))
    expected_path = _review_assignment_path(
        control_repo,
        _text(manifest.get("task_id")),
        fingerprint,
    ).resolve()
    if assignment_path.resolve() != expected_path:
        raise APError("Review assignment path does not match canonical Git-local task state.")
    if _text(review.get("assignment_path")) and Path(_text(review.get("assignment_path"))).resolve() != expected_path:
        raise APError("Review assignment manifest path does not match canonical Git-local task state.")
    expected_sha256 = _text(review.get("assignment_sha256"))
    if not _REVIEW_SHA256_RE.fullmatch(expected_sha256):
        raise APError("Review assignment has no valid manifest SHA-256 binding.")
    payload = _read_private_review_file(expected_path, "assignment")
    if len(payload) > 1024 * 1024:
        raise APError("Review assignment exceeds the 1 MiB contract limit.")
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != expected_sha256:
        raise APError(
            f"Review assignment SHA-256 mismatch: expected={expected_sha256}, actual={actual_sha256}."
        )
    try:
        assignment = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise APError("Review assignment file is invalid JSON.") from exc
    if not isinstance(assignment, dict):
        raise APError("Review assignment file must contain one JSON object.")
    _validate_orchestration_contract("assignment", assignment)
    if _text(assignment.get("task_id")) != _text(manifest.get("task_id")):
        raise APError("Review assignment task identity does not match its manifest.")
    if _text(assignment.get("diff_fingerprint")) != fingerprint:
        raise APError("Review assignment fingerprint does not match its manifest.")
    return assignment


def _persist_review_diff_artifact(path: Path, payload: bytes, expected_sha256: str) -> None:
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise APError("Generated review diff artifact SHA-256 is inconsistent.")
    if path.exists() or path.is_symlink():
        existing = _read_verified_private_review_file(path, expected_sha256, "diff artifact")
        if existing != payload:
            raise APError("Existing immutable review diff artifact does not match the current snapshot.")
        return
    _write_private_bytes(path, payload)
    _read_verified_private_review_file(path, expected_sha256, "diff artifact")


def _validate_review_diff_artifact(control_repo: Path, assignment: dict) -> bytes:
    task_id = _validate_task_id(_text(assignment.get("task_id")))
    fingerprint = _text(assignment.get("diff_fingerprint"))
    expected_path = _review_diff_artifact_path(control_repo, task_id, fingerprint).resolve()
    supplied_path = Path(_text(assignment.get("diff_artifact_path"))).resolve()
    if supplied_path != expected_path:
        raise APError("Review diff artifact path does not match canonical Git-local task state.")
    if _text(assignment.get("diff_artifact_format")) != _REVIEW_DIFF_ARTIFACT_FORMAT:
        raise APError("Review diff artifact format is unsupported.")
    return _read_verified_private_review_file(
        expected_path,
        _text(assignment.get("diff_artifact_sha256")),
        "diff artifact",
    )


def _task_review_policy(cfg: dict, worktree: Path, manifest: dict) -> tuple[str, int]:
    changed_paths = _task_changed_paths_from_base(worktree, _text(manifest.get("base_sha")))
    plan = _resolve_execution_plan(
        cfg,
        worktree,
        changed_paths=changed_paths,
        planned_paths=list(manifest.get("owned_paths") or []),
        requested_task_kind="change",
    )
    return _normalized_task_review_policy(
        True,
        manifest.get("review_depth"),
        plan.get("review_depth"),
    )


def cmd_review_assignment(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    task_id = _validate_task_id(args.task_id)
    control_repo, worktree, _ = _task_lifecycle_context(repo, cfg, task_id)
    timeout_s = float(_concurrency_cfg(cfg).get("lock_timeout_sec") or 30)
    with _repo_lock(control_repo, f"task-{task_id}", timeout_s=timeout_s):
        manifest = _load_task_manifest(control_repo, task_id)
        lifecycle_actor = _text(os.environ.get("CODEX_THREAD_ID"))
        if not lifecycle_actor or lifecycle_actor != _text(manifest.get("owner")):
            raise APError("Only the task lifecycle owner may issue a review assignment.")
        if _text(manifest.get("state")) not in {"active", "pushed", "integration-raced"}:
            raise APError(f"Task {task_id} is not reviewable in state={manifest.get('state')}.")
        if not bool(manifest.get("review_required")):
            raise APError(f"Task {task_id} does not require an independent review assignment.")
        if not worktree.exists():
            raise APError(f"Task worktree is missing: {worktree}")
        worktree_cfg = _load_cfg(worktree)
        unowned = _task_unowned_paths(worktree, worktree_cfg, manifest)
        if unowned:
            raise APError("Changes outside task owned_paths:\n- " + "\n- ".join(unowned))
        changed_paths = _task_changed_paths_from_base(
            worktree,
            _text(manifest.get("base_sha")),
        )
        changed_owned_paths = [
            path
            for path in changed_paths
            if _path_is_owned(path, list(manifest.get("owned_paths") or []))
        ]
        if not changed_owned_paths:
            raise APError("Cannot issue a review assignment before the task has an owned diff.")
        reviewer = _text(args.reviewer)
        if not reviewer or any(char in reviewer for char in "\0\r\n"):
            raise APError("Reviewer identity is empty or contains invalid characters.")
        owner = _text(manifest.get("owner"))
        owning_fixer = _text((manifest.get("writer_lease") or {}).get("holder")) or owner
        if reviewer in {owner, owning_fixer}:
            raise APError("Independent reviewer must differ from lifecycle owner and owning fixer.")
        snapshot = _task_review_snapshot(
            worktree,
            manifest,
            worktree_cfg,
            include_patch=True,
        )
        fingerprint = _text(snapshot.get("fingerprint"))
        patch = snapshot.get("patch")
        if not isinstance(patch, bytes) or not patch:
            raise APError("Cannot issue a review assignment for an empty immutable diff snapshot.")
        artifact_sha256 = _text(snapshot.get("patch_sha256"))
        artifact_path = _review_diff_artifact_path(control_repo, task_id, fingerprint)
        _persist_review_diff_artifact(artifact_path, patch, artifact_sha256)
        depth, review_timeout = _task_review_policy(worktree_cfg, worktree, manifest)
        issued = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
        deadline = issued + _dt.timedelta(seconds=review_timeout)
        assignment = {
            "contract_version": _AGENT_CONTRACT_VERSION,
            "node_id": reviewer,
            "task_id": task_id,
            "role": "reviewer",
            "base_sha": _text(manifest.get("base_sha")),
            "scope": f"Review the task-owned diff for {task_id}",
            "depends_on": [owning_fixer],
            "acceptance": [
                "Verify diff_artifact_sha256 and review only the immutable diff artifact.",
                "Return the complete 16-field reviewer result bound to diff_fingerprint.",
            ],
            "execution_mode": _text(manifest.get("execution_mode")),
            "task_branch": _text(manifest.get("task_branch")),
            "worktree_path": str(worktree.resolve()),
            "owned_paths": list(manifest.get("owned_paths") or []),
            "diff_base": _text(manifest.get("base_sha")),
            "diff_head": _resolve_commit(worktree, "HEAD"),
            "diff_fingerprint": fingerprint,
            "diff_artifact_path": str(artifact_path.resolve()),
            "diff_artifact_sha256": artifact_sha256,
            "diff_artifact_format": _REVIEW_DIFF_ARTIFACT_FORMAT,
            "owning_fixer": owning_fixer,
            "review_depth": depth,
            "timeout_seconds": review_timeout,
            "issued_at": issued.isoformat(),
            "deadline_at": deadline.isoformat(),
            "scope_revision": int(manifest.get("scope_revision") or 1),
        }
        _validate_orchestration_contract("assignment", assignment)
        assignment_path = _review_assignment_path(control_repo, task_id, fingerprint)
        prior_review = manifest.get("review") or {}
        if (
            _text(prior_review.get("diff_fingerprint")) == fingerprint
            and (
                _text(prior_review.get("verdict"))
                in {"approved", "changes-requested", "blocked"}
                or _text(prior_review.get("runtime_state"))
                or _text(prior_review.get("runtime_receipt_path"))
            )
        ):
            raise APError(
                "The single review attempt for this diff fingerprint is already complete or consumed."
            )
        if assignment_path.exists() or assignment_path.is_symlink():
            if (
                _text(prior_review.get("diff_fingerprint")) == fingerprint
                and _text(prior_review.get("assignment_sha256"))
            ):
                existing_assignment = _load_bound_review_assignment(
                    control_repo,
                    manifest,
                    assignment_path,
                )
            else:
                existing_assignment = _read_private_review_json(
                    assignment_path,
                    "assignment",
                )
        else:
            existing_assignment = None
        if existing_assignment:
            _validate_orchestration_contract("assignment", existing_assignment)
            expected_fields = {
                "contract_version": assignment["contract_version"],
                "task_id": task_id,
                "role": "reviewer",
                "base_sha": assignment["base_sha"],
                "scope": assignment["scope"],
                "depends_on": assignment["depends_on"],
                "acceptance": assignment["acceptance"],
                "execution_mode": assignment["execution_mode"],
                "task_branch": assignment["task_branch"],
                "worktree_path": assignment["worktree_path"],
                "owned_paths": assignment["owned_paths"],
                "diff_base": assignment["diff_base"],
                "diff_head": assignment["diff_head"],
                "diff_fingerprint": fingerprint,
                "diff_artifact_path": assignment["diff_artifact_path"],
                "diff_artifact_sha256": assignment["diff_artifact_sha256"],
                "diff_artifact_format": assignment["diff_artifact_format"],
                "owning_fixer": owning_fixer,
                "review_depth": assignment["review_depth"],
                "timeout_seconds": assignment["timeout_seconds"],
                "scope_revision": assignment["scope_revision"],
            }
            mismatched = [
                field
                for field, expected in expected_fields.items()
                if existing_assignment.get(field) != expected
            ]
            if mismatched:
                raise APError(
                    "Existing review assignment does not match current task state: "
                    + ", ".join(mismatched)
                )
            if _text(existing_assignment.get("node_id")) != reviewer:
                raise APError(
                    "This diff fingerprint already has a reviewer assignment; "
                    "the single review attempt cannot be reassigned."
                )
            existing_issued = _parse_iso_timestamp(
                existing_assignment.get("issued_at"),
                "issued_at",
            )
            _validate_review_diff_artifact(control_repo, existing_assignment)
            existing_deadline = _parse_iso_timestamp(
                existing_assignment.get("deadline_at"),
                "deadline_at",
            )
            if int((existing_deadline - existing_issued).total_seconds()) != review_timeout:
                raise APError("Existing review assignment deadline does not match its fixed timeout.")
            if _text(prior_review.get("diff_fingerprint")) == fingerprint:
                expected_prior_fields = {
                    "assignment_path": str(assignment_path),
                    "issued_at": existing_assignment["issued_at"],
                    "deadline_at": existing_assignment["deadline_at"],
                }
                prior_mismatches = [
                    field
                    for field, expected in expected_prior_fields.items()
                    if prior_review.get(field) != expected
                ]
                if prior_mismatches:
                    raise APError(
                        "Existing review assignment does not match its manifest timing: "
                        + ", ".join(prior_mismatches)
                    )
            if _dt.datetime.now(_dt.timezone.utc) > existing_deadline:
                raise APError(
                    "Review attempt timed out and is blocked for this diff fingerprint; "
                    "do not renew it without a semantic diff/scope change or explicit user authorization."
                )
            assignment = existing_assignment
            depth = _text(assignment.get("review_depth"))
            review_timeout = int(assignment.get("timeout_seconds") or 0)
        elif (
            _text(prior_review.get("diff_fingerprint")) == fingerprint
            and _text(prior_review.get("deadline_at"))
        ):
            if _text(prior_review.get("reviewer")) != reviewer:
                raise APError(
                    "This diff fingerprint already has a reviewer assignment; "
                    "the single review attempt cannot be reassigned."
                )
            issued = _parse_iso_timestamp(prior_review.get("issued_at"), "issued_at")
            deadline = _parse_iso_timestamp(prior_review.get("deadline_at"), "deadline_at")
            if _dt.datetime.now(_dt.timezone.utc) > deadline:
                raise APError(
                    "Review attempt timed out and is blocked for this diff fingerprint; "
                    "do not renew it without a semantic diff/scope change or explicit user authorization."
                )
            assignment["issued_at"] = issued.isoformat()
            assignment["deadline_at"] = deadline.isoformat()
            assignment["timeout_seconds"] = int((deadline - issued).total_seconds())
            _validate_orchestration_contract("assignment", assignment)
            _write_private_json(assignment_path, assignment)
            depth = _text(assignment.get("review_depth"))
            review_timeout = int(assignment.get("timeout_seconds") or 0)
        else:
            _write_private_json(assignment_path, assignment)
        assignment_sha256 = _review_assignment_file_sha256(assignment_path)
        manifest["review_depth"] = depth
        manifest["review_timeout_seconds"] = review_timeout
        review_state = {
            "verdict": "pending",
            "diff_base": assignment["diff_base"],
            "diff_head": assignment["diff_head"],
            "diff_fingerprint": fingerprint,
            "reviewer": reviewer,
            "reviewed_at": "",
            "reason": "review assignment issued",
            "assignment_path": str(assignment_path),
            "assignment_sha256": assignment_sha256,
            "diff_artifact_path": assignment["diff_artifact_path"],
            "diff_artifact_sha256": assignment["diff_artifact_sha256"],
            "diff_artifact_format": assignment["diff_artifact_format"],
            "issued_at": assignment["issued_at"],
            "deadline_at": assignment["deadline_at"],
        }
        if _text(prior_review.get("diff_fingerprint")) == fingerprint:
            for field in _REVIEW_RUNTIME_FIELDS:
                if field in prior_review:
                    review_state[field] = prior_review[field]
        manifest["review"] = review_state
        _save_task_manifest(control_repo, manifest)
    if bool(getattr(args, "json", False)):
        print(
            json.dumps(
                {"assignment_path": str(assignment_path), "assignment": assignment},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"[review-assignment] task={task_id} reviewer={reviewer} depth={depth}")
        print(f"[review-assignment] timeout_seconds={review_timeout}")
        print(f"[review-assignment] assignment={assignment_path}")


def cmd_review_artifact(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    assignment_path = Path(args.file).resolve()
    task_id = _validate_task_id(assignment_path.parent.name)
    manifest = _load_task_manifest(repo, task_id)
    assignment = _load_bound_review_assignment(repo, manifest, assignment_path)
    assigned_worktree = Path(_text(assignment.get("worktree_path"))).resolve()
    if assigned_worktree != repo:
        raise APError(
            f"Review artifact must be read from its assigned worktree: expected={assigned_worktree}, current={repo}."
        )
    if _dt.datetime.now(_dt.timezone.utc) >= _parse_iso_timestamp(
        assignment.get("deadline_at"),
        "deadline_at",
    ):
        raise APError("Review assignment deadline expired before diff artifact access.")
    payload = _validate_review_diff_artifact(repo, assignment)
    sys.stdout.flush()
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def _write_private_json(path: Path, payload: dict) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _write_private_bytes(path, encoded)


def _review_runtime_paths(
    control_repo: Path,
    task_id: str,
    fingerprint: str,
) -> tuple[Path, Path]:
    if not _REVIEW_SHA256_RE.fullmatch(_text(fingerprint)):
        raise APError("Review fingerprint must be a lowercase SHA-256 value.")
    root = _task_review_dir(control_repo, task_id, create=True)
    return root / f"{fingerprint}.result.json", root / f"{fingerprint}.run.json"


def _review_runtime_event_log_path(
    control_repo: Path,
    task_id: str,
    fingerprint: str,
) -> Path:
    if not _REVIEW_SHA256_RE.fullmatch(_text(fingerprint)):
        raise APError("Review fingerprint must be a lowercase SHA-256 value.")
    root = _task_review_dir(control_repo, task_id, create=True)
    return root / f"{fingerprint}.events.jsonl"


def _review_runtime_override_path(
    control_repo: Path,
    task_id: str,
    fingerprint: str,
) -> Path:
    if not _REVIEW_SHA256_RE.fullmatch(_text(fingerprint)):
        raise APError("Review fingerprint must be a lowercase SHA-256 value.")
    root = _task_review_dir(control_repo, task_id, create=True)
    return root / f"{fingerprint}.override.json"


def _open_private_review_event_log(path: Path):
    _guard_review_file_parent(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        if os.name == "posix":
            os.fchmod(descriptor, 0o600)
        return os.fdopen(descriptor, "w", encoding="utf-8", buffering=1)
    except OSError as exc:
        raise APError(f"Cannot create private Reviewer event log: {path}: {exc}") from exc


def _private_review_file_sha256(path: Path, label: str) -> str:
    payload = _read_private_review_file(path, label)
    return hashlib.sha256(payload).hexdigest()


def _reviewer_cli_version(command: list[str], runner_kind: str) -> str:
    if runner_kind != "codex" or not command:
        return "test-override"
    try:
        completed = subprocess.run(
            [command[0], "--version"],
            check=False,
            text=True,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    return _text(completed.stdout) or _text(completed.stderr) or "unknown"


def _reviewer_command_metadata(command: list[str], runner_kind: str) -> dict:
    model = "runtime-default"
    reasoning_effort = "unknown"
    for index, argument in enumerate(command):
        if argument in {"-m", "--model"} and index + 1 < len(command):
            model = command[index + 1]
        match = re.fullmatch(r'model_reasoning_effort="?([^"=]+)"?', argument)
        if match:
            reasoning_effort = match.group(1)
    return {
        "runner_kind": runner_kind,
        "cli_path": command[0] if command else "",
        "cli_version": _reviewer_cli_version(command, runner_kind),
        "model": model,
        "reasoning_effort": reasoning_effort,
    }


def _safe_reviewer_attempt(diagnostics: dict, attempt: int, status: str) -> dict:
    return {
        "attempt": attempt,
        "status": status,
        "started_at": _text(diagnostics.get("started_at")),
        "finished_at": _text(diagnostics.get("finished_at")),
        "first_event_at": _text(diagnostics.get("first_event_at")),
        "last_event_at": _text(diagnostics.get("last_event_at")),
        "last_event_type": _text(diagnostics.get("last_event_type")),
        "event_count": int(diagnostics.get("event_count") or 0),
        "phase": _text(diagnostics.get("phase")) or "unknown",
        "exit_code": diagnostics.get("exit_code"),
        "stdout_bytes": int(diagnostics.get("stdout_bytes") or 0),
        "stderr_bytes": int(diagnostics.get("stderr_bytes") or 0),
        "stdout_sha256": _text(diagnostics.get("stdout_sha256")),
        "stderr_sha256": _text(diagnostics.get("stderr_sha256")),
        "diagnostic_categories": list(diagnostics.get("diagnostic_categories") or []),
    }


def _validate_review_runtime_receipt(receipt: dict) -> dict:
    if int(receipt.get("schema") or 0) == 1:
        return receipt
    if int(receipt.get("schema") or 0) != 2:
        raise APError("Reviewer runtime receipt has an unsupported schema.")
    required_strings = (
        "task_id",
        "reviewer",
        "diff_fingerprint",
        "assignment_sha256",
        "diff_artifact_sha256",
        "command_sha256",
        "runner_kind",
        "cli_path",
        "cli_version",
        "model",
        "reasoning_effort",
        "event_log_path",
        "status",
        "started_at",
    )
    missing = [field for field in required_strings if not _text(receipt.get(field))]
    if missing:
        raise APError("Reviewer runtime receipt is missing: " + ", ".join(missing))
    attempts = receipt.get("attempts")
    if not isinstance(attempts, list) or len(attempts) > _REVIEW_RUNTIME_ATTEMPT_LIMIT:
        raise APError("Reviewer runtime receipt has an invalid attempts list.")
    allowed_statuses = {
        "starting",
        "retrying",
        "runtime-unavailable",
        "analysis-timed-out",
        "output-limit",
        "failed",
        "result-invalid",
        "blocked",
        "completed",
    }
    if _text(receipt.get("status")) not in allowed_statuses:
        raise APError("Reviewer runtime receipt has an invalid status.")
    for index, attempt in enumerate(attempts, start=1):
        if not isinstance(attempt, dict) or int(attempt.get("attempt") or 0) != index:
            raise APError("Reviewer runtime receipt attempts are not sequential.")
        if "stderr_tail" in attempt:
            raise APError("Reviewer runtime receipt cannot persist raw stderr text.")
        for field in ("stdout_bytes", "stderr_bytes", "event_count"):
            value = attempt.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise APError(f"Reviewer runtime receipt attempt {field} is invalid.")
    return receipt


def _review_command_sha256(command: list[str]) -> str:
    digest = hashlib.sha256()
    for argument in command:
        digest.update(argument.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
    return digest.hexdigest()


def _bounded_reviewer_output(value: str, label: str) -> str:
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) > _REVIEW_OUTPUT_MAX_BYTES:
        raise APError(f"Reviewer {label} exceeded {_REVIEW_OUTPUT_MAX_BYTES} bytes; refusing oversized output.")
    return value


def _read_bounded_reviewer_bytes(path: Path) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            os.close(descriptor)
            raise APError(f"Reviewer result must be a regular file: {path}")
        with os.fdopen(descriptor, "rb") as handle:
            payload = handle.read(_REVIEW_OUTPUT_MAX_BYTES + 1)
    except OSError as exc:
        raise APError(f"Cannot read Reviewer result: {path}: {exc}") from exc
    if len(payload) > _REVIEW_OUTPUT_MAX_BYTES:
        raise APError(f"Reviewer result exceeded {_REVIEW_OUTPUT_MAX_BYTES} bytes; refusing oversized output.")
    return payload


def _read_bounded_reviewer_output(path: Path) -> str:
    return _read_bounded_reviewer_bytes(path).decode("utf-8", errors="strict")


def _review_result_file_sha256(path: Path) -> str:
    return hashlib.sha256(_read_bounded_reviewer_bytes(path)).hexdigest()


def _substantive_reviewer_result(path: Path, assignment: dict) -> Optional[dict]:
    if path.is_symlink():
        raise APError("Refusing a symlinked Reviewer result.")
    if not path.exists():
        return None
    try:
        payload = json.loads(_read_bounded_reviewer_output(path))
        result = _normalize_reviewer_runtime_result(assignment, payload)
    except (APError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if _text(result.get("verdict")) in {"blocked", "changes-requested"}:
        return result
    return None


def _substantive_reviewer_event_result(stdout: str, assignment: dict) -> Optional[dict]:
    substantive: Optional[dict] = None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
            item = event.get("item") if isinstance(event, dict) else None
            if not isinstance(item, dict) or _text(item.get("type")) != "agent_message":
                continue
            payload = json.loads(_text(item.get("text")))
            result = _normalize_reviewer_runtime_result(assignment, payload)
        except (APError, json.JSONDecodeError, TypeError):
            continue
        verdict = _text(result.get("verdict"))
        if verdict == "blocked":
            substantive = result
        elif verdict == "changes-requested" and substantive is None:
            substantive = result
    return substantive


def _update_review_runtime(
    control_repo: Path,
    task_id: str,
    fingerprint: str,
    *,
    updates: dict,
    receipt_path: Path,
    receipt_updates: dict,
) -> dict:
    cfg = _load_cfg(control_repo)
    timeout_s = float(_concurrency_cfg(cfg).get("lock_timeout_sec") or 30)
    with _repo_lock(control_repo, f"task-{task_id}", timeout_s=timeout_s):
        manifest = _load_task_manifest(control_repo, task_id)
        review = dict(manifest.get("review") or {})
        if _text(review.get("diff_fingerprint")) != fingerprint:
            raise APError("Reviewer runtime assignment became stale while the process was running.")
        review.update(updates)
        manifest["review"] = review
        receipt = _read_json_object(receipt_path) or {}
        receipt.update(receipt_updates)
        _validate_review_runtime_receipt(receipt)
        _write_private_json(receipt_path, receipt)
        review["runtime_receipt_sha256"] = _private_review_file_sha256(
            receipt_path,
            "runtime receipt",
        )
        if _REVIEW_SHA256_RE.fullmatch(_text(receipt.get("event_log_sha256"))):
            review["runtime_event_log_sha256"] = _text(receipt.get("event_log_sha256"))
        if _REVIEW_SHA256_RE.fullmatch(_text(receipt.get("result_sha256"))):
            review["runtime_result_sha256"] = _text(receipt.get("result_sha256"))
        _save_task_manifest(control_repo, manifest)
        return manifest


def _validate_bound_review_runtime_receipt(
    control_repo: Path,
    manifest: dict,
    assignment: dict,
    receipt_path: Path,
    expected_status: str,
) -> dict:
    review = manifest.get("review") or {}
    task_id = _text(manifest.get("task_id"))
    fingerprint = _text(review.get("diff_fingerprint"))
    expected_result_path, expected_receipt_path = _review_runtime_paths(
        control_repo,
        task_id,
        fingerprint,
    )
    if receipt_path.resolve() != expected_receipt_path.resolve():
        raise APError("Reviewer runtime receipt path is not canonical.")
    payload = _read_private_review_file(receipt_path, "runtime receipt")
    try:
        receipt = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise APError("Reviewer runtime receipt is invalid JSON.") from exc
    if not isinstance(receipt, dict):
        raise APError("Reviewer runtime receipt must contain one JSON object.")
    _validate_review_runtime_receipt(receipt)
    expected = {
        "task_id": task_id,
        "reviewer": _text(review.get("reviewer")),
        "diff_fingerprint": fingerprint,
        "assignment_path": _text(review.get("assignment_path")),
        "assignment_sha256": _text(review.get("assignment_sha256")),
        "diff_artifact_path": _text(assignment.get("diff_artifact_path")),
        "diff_artifact_sha256": _text(assignment.get("diff_artifact_sha256")),
        "result_path": str(expected_result_path),
        "command_sha256": _text(review.get("runtime_command_sha256")),
        "event_log_path": str(
            _review_runtime_event_log_path(control_repo, task_id, fingerprint)
        ),
        "status": expected_status,
    }
    mismatched = [field for field, value in expected.items() if receipt.get(field) != value]
    if mismatched:
        raise APError(
            "Reviewer runtime receipt does not match task state: " + ", ".join(mismatched)
        )
    receipt_sha256 = hashlib.sha256(payload).hexdigest()
    if receipt_sha256 != _text(review.get("runtime_receipt_sha256")):
        raise APError("Reviewer runtime receipt changed after failure finalization.")
    event_log_path = Path(_text(receipt.get("event_log_path"))).resolve()
    event_log_sha256 = _private_review_file_sha256(event_log_path, "event log")
    if event_log_sha256 != _text(receipt.get("event_log_sha256")) or event_log_sha256 != _text(
        review.get("runtime_event_log_sha256")
    ):
        raise APError("Reviewer runtime event log changed after failure finalization.")
    result_sha256 = _text(receipt.get("result_sha256"))
    if result_sha256 and (
        _review_result_file_sha256(expected_result_path) != result_sha256
        or result_sha256 != _text(review.get("runtime_result_sha256"))
    ):
        raise APError("Reviewer runtime result changed after failure finalization.")
    return receipt


def _blocked_reviewer_runtime_result(
    assignment: dict,
    reason: str,
    evidence: list[str],
) -> dict:
    result = _reviewer_result_template(assignment, "blocked")
    result["summary"] = reason
    result["evidence"] = evidence
    return _validate_orchestration_contract("result", result)


def cmd_review_run(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    task_id = _validate_task_id(args.task_id)
    reviewer = _text(args.reviewer)
    with contextlib.redirect_stdout(io.StringIO()):
        cmd_review_assignment(
            argparse.Namespace(
                repo=str(repo),
                task_id=task_id,
                reviewer=reviewer,
                json=False,
            )
        )

    control_repo, worktree, _ = _task_lifecycle_context(repo, cfg, task_id)
    manifest = _load_task_manifest(control_repo, task_id)
    review = manifest.get("review") or {}
    assignment_path = Path(_text(review.get("assignment_path"))).resolve()
    assignment = _load_bound_review_assignment(
        control_repo,
        manifest,
        assignment_path,
    )
    fingerprint = _text(assignment.get("diff_fingerprint"))
    assignment_sha256 = _text((manifest.get("review") or {}).get("assignment_sha256"))
    _validate_review_diff_artifact(control_repo, assignment)
    if _task_review_fingerprint(worktree, manifest, _load_cfg(worktree)) != fingerprint:
        raise APError("Review assignment is stale; the task-owned working tree changed before Reviewer start.")
    result_path, receipt_path = _review_runtime_paths(control_repo, task_id, fingerprint)

    command_override = _text(getattr(args, "runner_command_json", ""))
    if command_override:
        if _text(os.environ.get("AUTOCODING_TEST_RUNNER_OVERRIDE")) != "1":
            raise APError(
                "--runner-command-json is test-only; set AUTOCODING_TEST_RUNNER_OVERRIDE=1 "
                "inside the isolated test harness."
            )
        try:
            command_value = json.loads(command_override)
        except json.JSONDecodeError as exc:
            raise APError("--runner-command-json must be a JSON array of argv strings.") from exc
        if not isinstance(command_value, list) or not command_value or not all(
            isinstance(item, str) and item for item in command_value
        ):
            raise APError("--runner-command-json must be a non-empty JSON array of argv strings.")
        command = command_value
        runner_kind = "test-override"
    else:
        command = _codex_reviewer_command(
            worktree,
            assignment_path,
            result_path,
            review_depth=_text(assignment.get("review_depth")) or "focused",
        )
        runner_kind = "codex"
    command_sha256 = _review_command_sha256(command)
    command_metadata = _reviewer_command_metadata(command, runner_kind)
    started_at = _now_iso()
    event_log_path = _review_runtime_event_log_path(control_repo, task_id, fingerprint)
    receipt = {
        "schema": 2,
        "task_id": task_id,
        "reviewer": reviewer,
        "diff_fingerprint": fingerprint,
        "assignment_path": str(assignment_path),
        "assignment_sha256": assignment_sha256,
        "diff_artifact_path": _text(assignment.get("diff_artifact_path")),
        "diff_artifact_sha256": _text(assignment.get("diff_artifact_sha256")),
        "result_path": str(result_path),
        "command_sha256": command_sha256,
        **command_metadata,
        "event_log_path": str(event_log_path),
        "event_log_sha256": "",
        "attempts": [],
        "failure_kind": "",
        "status": "starting",
        "started_at": started_at,
        "finished_at": "",
        "exit_code": None,
    }
    timeout_s = float(_concurrency_cfg(_load_cfg(control_repo)).get("lock_timeout_sec") or 30)
    with _repo_lock(control_repo, f"task-{task_id}", timeout_s=timeout_s):
        manifest = _load_task_manifest(control_repo, task_id)
        current_review = dict(manifest.get("review") or {})
        if _text(current_review.get("diff_fingerprint")) != fingerprint:
            raise APError("Review assignment became stale before Reviewer runtime start.")
        assignment = _load_bound_review_assignment(
            control_repo,
            manifest,
            assignment_path,
        )
        _validate_review_diff_artifact(control_repo, assignment)
        if _task_review_fingerprint(worktree, manifest, _load_cfg(worktree)) != fingerprint:
            raise APError("Review assignment is stale; the task-owned working tree changed before Reviewer start.")
        if _text(current_review.get("runtime_state")) or receipt_path.exists():
            raise APError(
                "The supervised Reviewer runtime has already started for this diff fingerprint."
            )
        deadline = _parse_iso_timestamp(assignment.get("deadline_at"), "deadline_at")
        if _dt.datetime.now(_dt.timezone.utc) >= deadline:
            raise APError("Review assignment deadline expired before Reviewer runtime start.")
        if result_path.exists() or result_path.is_symlink():
            raise APError("Reviewer runtime result already exists before the first attempt.")
        if event_log_path.exists() or event_log_path.is_symlink():
            raise APError("Reviewer runtime event log already exists for this diff fingerprint.")
        event_log = _open_private_review_event_log(event_log_path)
        try:
            _validate_review_runtime_receipt(receipt)
            _write_private_json(receipt_path, receipt)
        except Exception:
            event_log.close()
            event_log_path.unlink(missing_ok=True)
            raise
        current_review.update(
            {
                "runtime_state": "starting",
                "runtime_started_at": started_at,
                "runtime_finished_at": "",
                "runtime_result_path": str(result_path),
                "runtime_exit_code": None,
                "runtime_command_sha256": command_sha256,
                "runtime_receipt_path": str(receipt_path),
                "runtime_event_log_path": str(event_log_path),
                "runtime_attempt_count": 0,
                "runtime_failure_kind": "",
            }
        )
        manifest["review"] = current_review
        _save_task_manifest(control_repo, manifest)

    env = os.environ.copy()
    env.pop("CODEX_THREAD_ID", None)
    env.update(
        {
            "AUTOCODING_REVIEW_ASSIGNMENT": str(assignment_path),
            "AUTOCODING_REVIEW_ASSIGNMENT_SHA256": assignment_sha256,
            "AUTOCODING_REVIEW_DIFF_ARTIFACT": _text(assignment.get("diff_artifact_path")),
            "AUTOCODING_REVIEW_DIFF_ARTIFACT_SHA256": _text(assignment.get("diff_artifact_sha256")),
            "AUTOCODING_REVIEW_RESULT": str(result_path),
            "AUTOCODING_REVIEW_DEADLINE": _text(assignment.get("deadline_at")),
            "AUTOCODING_REVIEW_TIMEOUT_SECONDS": str(int(assignment.get("timeout_seconds") or 0)),
        }
    )
    deadline = _parse_iso_timestamp(assignment.get("deadline_at"), "deadline_at")
    attempts: list[dict] = []
    completed: Optional[subprocess.CompletedProcess[str]] = None
    runtime_failure: Optional[_ReviewerRuntimeFailure] = None
    failure_kind = ""
    substantive_result: Optional[dict] = None

    def observed_substantive_result() -> bool:
        nonlocal substantive_result, runtime_failure, failure_kind
        try:
            substantive_result = _substantive_reviewer_result(result_path, assignment)
            if substantive_result is None and runtime_failure is not None:
                substantive_result = _substantive_reviewer_event_result(
                    runtime_failure.stdout,
                    assignment,
                )
        except APError:
            runtime_failure = _ReviewerRuntimeInternalError(
                {"phase": "result-inspection-failed"}
            )
            failure_kind = "supervision-error"
            return True
        return substantive_result is not None

    for attempt_number in range(1, _REVIEW_RUNTIME_ATTEMPT_LIMIT + 1):
        remaining = (deadline - _dt.datetime.now(_dt.timezone.utc)).total_seconds()
        if remaining <= 0:
            runtime_failure = _ReviewerRuntimeTimeout()
            failure_kind = "analysis-timeout"
            break
        if attempt_number > 1:
            if result_path.is_symlink():
                event_log.close()
                raise APError("Refusing a symlinked Reviewer result before retry.")
            result_path.unlink(missing_ok=True)
        try:
            completed, diagnostics = _run_supervised_reviewer_process(
                command,
                cwd=worktree,
                env=env,
                timeout_seconds=remaining,
                startup_timeout_seconds=_review_startup_timeout_seconds(),
                event_writer=event_log,
            )
            attempts.append(
                _safe_reviewer_attempt(
                    diagnostics,
                    attempt_number,
                    "completed" if completed.returncode == 0 else "failed",
                )
            )
            break
        except _ReviewerRuntimeUnavailable as exc:
            runtime_failure = exc
            failure_kind = "runtime-unavailable"
            attempts.append(
                _safe_reviewer_attempt(exc.diagnostics, attempt_number, failure_kind)
            )
            if observed_substantive_result():
                break
            if attempt_number < _REVIEW_RUNTIME_ATTEMPT_LIMIT:
                _update_review_runtime(
                    control_repo,
                    task_id,
                    fingerprint,
                    updates={
                        "runtime_state": "retrying",
                        "runtime_attempt_count": attempt_number,
                        "runtime_failure_kind": failure_kind,
                    },
                    receipt_path=receipt_path,
                    receipt_updates={
                        "status": "retrying",
                        "attempts": attempts,
                        "failure_kind": failure_kind,
                    },
                )
                continue
            break
        except _ReviewerRuntimeTimeout as exc:
            runtime_failure = exc
            failure_kind = "analysis-timeout"
            attempts.append(
                _safe_reviewer_attempt(exc.diagnostics, attempt_number, failure_kind)
            )
            observed_substantive_result()
            break
        except _ReviewerRuntimeOutputLimit as exc:
            runtime_failure = exc
            failure_kind = "output-limit"
            attempts.append(
                _safe_reviewer_attempt(exc.diagnostics, attempt_number, failure_kind)
            )
            observed_substantive_result()
            break
        except _ReviewerRuntimeInternalError as exc:
            runtime_failure = exc
            failure_kind = "supervision-error"
            attempts.append(
                _safe_reviewer_attempt(exc.diagnostics, attempt_number, failure_kind)
            )
            observed_substantive_result()
            break

    event_log.close()
    event_log_sha256 = _private_review_file_sha256(event_log_path, "event log")
    if runtime_failure is not None:
        finished_at = _now_iso()
        if substantive_result is not None:
            _write_private_json(result_path, substantive_result)
            result_sha256 = _review_result_file_sha256(result_path)
            _update_review_runtime(
                control_repo,
                task_id,
                fingerprint,
                updates={
                    "verdict": substantive_result["verdict"],
                    "reason": "substantive Reviewer result observed before runtime failure",
                    "runtime_state": "blocked",
                    "runtime_finished_at": finished_at,
                    "runtime_exit_code": None,
                    "runtime_attempt_count": len(attempts),
                    "runtime_failure_kind": failure_kind,
                },
                receipt_path=receipt_path,
                receipt_updates={
                    "status": "blocked",
                    "finished_at": finished_at,
                    "exit_code": None,
                    "verdict": substantive_result["verdict"],
                    "result_sha256": result_sha256,
                    "attempts": attempts,
                    "failure_kind": failure_kind,
                    "event_log_sha256": event_log_sha256,
                },
            )
            print(json.dumps(substantive_result, ensure_ascii=False, indent=2))
            raise APError(
                "Reviewer produced a substantive result before runtime failure; it cannot be bypassed."
            ) from runtime_failure
        runtime_state = (
            "runtime-unavailable"
            if failure_kind == "runtime-unavailable"
            else "analysis-timed-out"
            if failure_kind == "analysis-timeout"
            else "failed"
        )
        result = _blocked_reviewer_runtime_result(
            assignment,
            (
                "Reviewer runtime was unavailable before analysis started."
                if failure_kind == "runtime-unavailable"
                else "Reviewer analysis reached its fixed deadline and was terminated."
                if failure_kind == "analysis-timeout"
                else "Reviewer runtime exceeded its bounded output limit."
                if failure_kind == "output-limit"
                else "Reviewer runtime supervision failed safely."
            ),
            [
                f"runtime_failure_kind={failure_kind}",
                f"runtime_attempt_count={len(attempts)}",
                f"event_log_sha256={event_log_sha256}",
            ],
        )
        _write_private_json(result_path, result)
        result_sha256 = _review_result_file_sha256(result_path)
        _update_review_runtime(
            control_repo,
            task_id,
            fingerprint,
            updates={
                "verdict": "blocked",
                "reason": f"reviewer {failure_kind}",
                "runtime_state": runtime_state,
                "runtime_finished_at": finished_at,
                "runtime_exit_code": None,
                "runtime_attempt_count": len(attempts),
                "runtime_failure_kind": failure_kind,
            },
            receipt_path=receipt_path,
            receipt_updates={
                "status": (
                    "runtime-unavailable"
                    if failure_kind == "runtime-unavailable"
                    else "analysis-timed-out"
                    if failure_kind == "analysis-timeout"
                    else "output-limit"
                    if failure_kind == "output-limit"
                    else "failed"
                ),
                "finished_at": finished_at,
                "exit_code": None,
                "attempts": attempts,
                "failure_kind": failure_kind,
                "event_log_sha256": event_log_sha256,
                "result_sha256": result_sha256,
            },
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if runtime_state in {"runtime-unavailable", "analysis-timed-out"}:
            raise APError(
                f"Reviewer {failure_kind}; review is blocked unless an explicit runtime override is recorded."
            ) from runtime_failure
        raise APError(f"Reviewer {failure_kind}; review is blocked.") from runtime_failure

    if completed is None:
        raise APError("Reviewer runtime ended without a process result.")
    finished_at = _now_iso()
    if completed.returncode != 0:
        substantive_result = _substantive_reviewer_result(result_path, assignment)
        if substantive_result is None:
            try:
                substantive_result = _substantive_reviewer_event_result(
                    _bounded_reviewer_output(completed.stdout, "stdout"),
                    assignment,
                )
            except APError:
                substantive_result = None
        if substantive_result is not None:
            _write_private_json(result_path, substantive_result)
            result_sha256 = _review_result_file_sha256(result_path)
            _update_review_runtime(
                control_repo,
                task_id,
                fingerprint,
                updates={
                    "verdict": substantive_result["verdict"],
                    "reason": "substantive Reviewer result observed before nonzero process exit",
                    "runtime_state": "blocked",
                    "runtime_finished_at": finished_at,
                    "runtime_exit_code": completed.returncode,
                    "runtime_attempt_count": len(attempts),
                    "runtime_failure_kind": "process-exit",
                },
                receipt_path=receipt_path,
                receipt_updates={
                    "status": "blocked",
                    "finished_at": finished_at,
                    "exit_code": completed.returncode,
                    "verdict": substantive_result["verdict"],
                    "attempts": attempts,
                    "failure_kind": "process-exit",
                    "event_log_sha256": event_log_sha256,
                    "result_sha256": result_sha256,
                },
            )
            print(json.dumps(substantive_result, ensure_ascii=False, indent=2))
            raise APError(
                "Reviewer produced a substantive result before nonzero process exit; "
                "it cannot be bypassed."
            )
        result = _blocked_reviewer_runtime_result(
            assignment,
            "Reviewer runtime exited unsuccessfully.",
            [f"runner_exit_code={completed.returncode}"],
        )
        _write_private_json(result_path, result)
        result_sha256 = _review_result_file_sha256(result_path)
        _update_review_runtime(
            control_repo,
            task_id,
            fingerprint,
            updates={
                "verdict": "blocked",
                "reason": "reviewer runtime failed",
                "runtime_state": "failed",
                "runtime_finished_at": finished_at,
                "runtime_exit_code": completed.returncode,
                "runtime_attempt_count": len(attempts),
                "runtime_failure_kind": "process-exit",
            },
            receipt_path=receipt_path,
            receipt_updates={
                "status": "failed",
                "finished_at": finished_at,
                "exit_code": completed.returncode,
                "attempts": attempts,
                "failure_kind": "process-exit",
                "event_log_sha256": event_log_sha256,
                "result_sha256": result_sha256,
            },
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise APError(
            f"Reviewer runtime failed with exit code {completed.returncode}; review is blocked."
        )

    try:
        stdout = _bounded_reviewer_output(completed.stdout, "stdout")
        _bounded_reviewer_output(completed.stderr, "stderr")
        raw = _read_bounded_reviewer_output(result_path) if result_path.exists() else stdout
        payload = json.loads(raw)
        result = _normalize_reviewer_runtime_result(assignment, payload)
    except (APError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        result = _blocked_reviewer_runtime_result(
            assignment,
            "Reviewer runtime returned an invalid result.",
            ["result_contract_valid=false"],
        )
        _write_private_json(result_path, result)
        result_sha256 = _review_result_file_sha256(result_path)
        _update_review_runtime(
            control_repo,
            task_id,
            fingerprint,
            updates={
                "verdict": "blocked",
                "reason": "invalid reviewer runtime result",
                "runtime_state": "failed",
                "runtime_finished_at": finished_at,
                "runtime_exit_code": completed.returncode,
                "runtime_attempt_count": len(attempts),
                "runtime_failure_kind": "result-invalid",
            },
            receipt_path=receipt_path,
            receipt_updates={
                "status": "result-invalid",
                "finished_at": finished_at,
                "exit_code": completed.returncode,
                "attempts": attempts,
                "failure_kind": "result-invalid",
                "event_log_sha256": event_log_sha256,
                "result_sha256": result_sha256,
            },
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise APError(f"Reviewer runtime result is invalid; review is blocked: {exc}") from exc

    _write_private_json(result_path, result)
    result_sha256 = _review_result_file_sha256(result_path)
    runtime_state = "blocked" if result["verdict"] == "blocked" else "completed"
    _update_review_runtime(
        control_repo,
        task_id,
        fingerprint,
        updates={
            "verdict": "blocked" if result["verdict"] == "blocked" else "pending",
            "reason": "reviewer reported blocked" if result["verdict"] == "blocked" else "",
            "runtime_state": runtime_state,
            "runtime_finished_at": finished_at,
            "runtime_exit_code": completed.returncode,
            "runtime_attempt_count": len(attempts),
            "runtime_failure_kind": "",
        },
        receipt_path=receipt_path,
        receipt_updates={
            "status": runtime_state,
            "finished_at": finished_at,
            "exit_code": completed.returncode,
            "verdict": result["verdict"],
            "result_sha256": result_sha256,
            "attempts": attempts,
            "failure_kind": "",
            "event_log_sha256": event_log_sha256,
        },
    )
    if result["verdict"] == "blocked":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise APError("Reviewer returned blocked; task-review was not recorded.")

    with contextlib.redirect_stdout(io.StringIO()):
        cmd_task_review(
            argparse.Namespace(
                repo=str(repo),
                task_id=task_id,
                verdict=result["verdict"],
                diff_fingerprint=fingerprint,
                reviewer=reviewer,
            )
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_review_runtime_override(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    task_id = _validate_task_id(args.task_id)
    control_repo, worktree, _ = _task_lifecycle_context(repo, cfg, task_id)
    if not bool(getattr(args, "confirm_runtime_bypass", False)):
        raise APError("Runtime bypass requires --confirm-runtime-bypass.")
    authorized_by = _text(getattr(args, "authorized_by", ""))
    authorization_ref = _text(getattr(args, "authorization_ref", ""))
    reason = _text(getattr(args, "reason", ""))
    evidence = list(getattr(args, "evidence", None) or [])
    for label, value in (
        ("authorized-by", authorized_by),
        ("authorization-ref", authorization_ref),
        ("reason", reason),
    ):
        if not value or any(char in value for char in "\0\r\n"):
            raise APError(f"--{label} must be non-empty and single-line.")
    if len(reason) < 12:
        raise APError("--reason must explain the exceptional delivery decision.")
    if not evidence or not all(
        isinstance(item, str) and item and not any(char in item for char in "\0\r\n")
        for item in evidence
    ):
        raise APError("Runtime bypass requires at least one single-line --evidence value.")

    timeout_s = float(_concurrency_cfg(cfg).get("lock_timeout_sec") or 30)
    with _repo_lock(control_repo, f"task-{task_id}", timeout_s=timeout_s):
        manifest = _load_task_manifest(control_repo, task_id)
        lifecycle_actor = _text(os.environ.get("CODEX_THREAD_ID"))
        if not lifecycle_actor or lifecycle_actor != _text(manifest.get("owner")):
            raise APError("Only the task lifecycle owner may record a Reviewer runtime bypass.")
        if _text(manifest.get("state")) not in {"active", "pushed", "integration-raced"}:
            raise APError(f"Task {task_id} cannot accept a runtime bypass in state={manifest.get('state')}.")
        review = dict(manifest.get("review") or {})
        runtime_state = _text(review.get("runtime_state"))
        if runtime_state not in {"runtime-unavailable", "analysis-timed-out"}:
            raise APError(
                "Runtime bypass is allowed only after exhausted runtime-unavailable or analysis-timed-out state."
            )
        fingerprint = _task_review_fingerprint(worktree, manifest, _load_cfg(worktree))
        supplied = _text(args.diff_fingerprint)
        if supplied != fingerprint or _text(review.get("diff_fingerprint")) != fingerprint:
            raise APError(
                f"Runtime bypass fingerprint mismatch: supplied={supplied or '(missing)'}, current={fingerprint}."
            )
        assignment_path = Path(_text(review.get("assignment_path"))).resolve()
        assignment = _load_bound_review_assignment(control_repo, manifest, assignment_path)
        _validate_review_diff_artifact(control_repo, assignment)
        receipt_path = Path(_text(review.get("runtime_receipt_path"))).resolve()
        _, expected_receipt_path = _review_runtime_paths(
            control_repo,
            task_id,
            fingerprint,
        )
        if receipt_path != expected_receipt_path.resolve():
            raise APError("Reviewer runtime receipt path is not canonical.")
        receipt = _validate_bound_review_runtime_receipt(
            control_repo,
            manifest,
            assignment,
            receipt_path,
            runtime_state,
        )
        if int(receipt.get("schema") or 0) != 2:
            raise APError("Runtime bypass requires a schema-2 Reviewer receipt.")
        if runtime_state == "runtime-unavailable" and len(receipt.get("attempts") or []) != _REVIEW_RUNTIME_ATTEMPT_LIMIT:
            raise APError("Runtime-unavailable bypass requires exhausted startup attempts.")
        override_path = _review_runtime_override_path(control_repo, task_id, fingerprint)
        if override_path.exists() or override_path.is_symlink():
            raise APError("Reviewer runtime override already exists for this diff fingerprint.")
        payload = {
            "schema": 1,
            "task_id": task_id,
            "diff_fingerprint": fingerprint,
            "assignment_sha256": _text(review.get("assignment_sha256")),
            "diff_artifact_sha256": _text(review.get("diff_artifact_sha256")),
            "runtime_receipt_path": str(receipt_path),
            "runtime_receipt_sha256": _private_review_file_sha256(
                receipt_path,
                "runtime receipt",
            ),
            "runtime_failure_state": runtime_state,
            "user_authorized": True,
            "authorized_by": authorized_by,
            "authorization_ref": authorization_ref,
            "authorized_at": _now_iso(),
            "lifecycle_owner": lifecycle_actor,
            "reason": reason,
            "evidence": evidence,
        }
        _write_private_json(override_path, payload)
        override_sha256 = _private_review_file_sha256(override_path, "runtime override")
        review.update(
            {
                "verdict": "runtime-bypassed",
                "reason": reason,
                "reviewed_at": payload["authorized_at"],
                "runtime_state": "runtime-bypassed",
                "runtime_override_path": str(override_path),
                "runtime_override_sha256": override_sha256,
            }
        )
        manifest["review"] = review
        _save_task_manifest(control_repo, manifest)
    result = {
        "task_id": task_id,
        "verdict": "runtime-bypassed",
        "diff_fingerprint": fingerprint,
        "authorized_by": authorized_by,
        "authorization_ref": authorization_ref,
        "override_path": str(override_path),
        "override_sha256": override_sha256,
    }
    if bool(getattr(args, "json", False)):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"[review-runtime-override] task={task_id} verdict=runtime-bypassed "
            f"fingerprint={fingerprint}"
        )


def cmd_task_review(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    task_id = _validate_task_id(args.task_id)
    control_repo, worktree, _ = _task_lifecycle_context(repo, cfg, task_id)
    timeout_s = float(_concurrency_cfg(cfg).get("lock_timeout_sec") or 30)
    with _repo_lock(control_repo, f"task-{task_id}", timeout_s=timeout_s):
        manifest = _load_task_manifest(control_repo, task_id)
        lifecycle_actor = _text(os.environ.get("CODEX_THREAD_ID"))
        if not lifecycle_actor or lifecycle_actor != _text(manifest.get("owner")):
            raise APError("Only the task lifecycle owner may record a review verdict.")
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
        if bool(manifest.get("review_required")):
            if not _text(getattr(args, "reviewer", "")):
                raise APError("Independent review requires an explicit --reviewer identity.")
            if reviewer == _text(manifest.get("owner")):
                raise APError("Independent reviewer identity must differ from the task lifecycle owner.")
            writer = _text((manifest.get("writer_lease") or {}).get("holder"))
            if reviewer == writer:
                raise APError("Independent reviewer identity must differ from the current writer lease holder.")
        assigned_review = manifest.get("review") or {}
        if bool(manifest.get("review_required")) and not all(
            _text(assigned_review.get(field))
            for field in (
                "assignment_path",
                "assignment_sha256",
                "reviewer",
                "diff_fingerprint",
                "diff_artifact_path",
                "diff_artifact_sha256",
                "diff_artifact_format",
                "deadline_at",
            )
        ):
            raise APError(
                "Review-required tasks must use review-assignment before task-review."
            )
        assigned_reviewer = _text(assigned_review.get("reviewer"))
        if assigned_reviewer and reviewer != assigned_reviewer:
            raise APError(
                f"Review verdict reviewer mismatch: assigned={assigned_reviewer}, supplied={reviewer}."
            )
        assigned_fingerprint = _text(assigned_review.get("diff_fingerprint"))
        if assigned_fingerprint and assigned_fingerprint != fingerprint:
            raise APError("Review assignment is stale; issue a new assignment for the current diff.")
        assigned_head = _text(assigned_review.get("diff_head"))
        current_head = _resolve_commit(worktree, "HEAD")
        if assigned_head and assigned_head != current_head:
            raise APError("Review assignment HEAD is stale for the current task.")
        assignment_path = _text(assigned_review.get("assignment_path"))
        assignment: Optional[dict] = None
        if assignment_path:
            expected_assignment_path = _review_assignment_path(
                control_repo,
                task_id,
                fingerprint,
            ).resolve()
            if Path(assignment_path).resolve() != expected_assignment_path:
                raise APError("Review assignment path does not match Git-local task state.")
            assignment = _load_bound_review_assignment(
                control_repo,
                manifest,
                expected_assignment_path,
            )
            expected_assignment_fields = {
                "task_id": task_id,
                "base_sha": _text(manifest.get("base_sha")),
                "diff_base": _text(manifest.get("base_sha")),
                "diff_head": current_head,
                "diff_fingerprint": fingerprint,
                "diff_artifact_path": str(
                    _review_diff_artifact_path(control_repo, task_id, fingerprint).resolve()
                ),
                "diff_artifact_sha256": _text(assigned_review.get("diff_artifact_sha256")),
                "diff_artifact_format": _REVIEW_DIFF_ARTIFACT_FORMAT,
                "node_id": reviewer,
                "owning_fixer": _text((manifest.get("writer_lease") or {}).get("holder")),
                "issued_at": _text(assigned_review.get("issued_at")),
                "deadline_at": _text(assigned_review.get("deadline_at")),
            }
            mismatched = [
                field
                for field, expected in expected_assignment_fields.items()
                if assignment.get(field) != expected
            ]
            if mismatched:
                raise APError(
                    "Review assignment does not match the recorded task state: "
                    + ", ".join(mismatched)
                )
            _validate_review_diff_artifact(control_repo, assignment)
            if int(assignment.get("scope_revision") or 0) != int(
                manifest.get("scope_revision") or 1
            ):
                raise APError("Review assignment scope revision is stale.")
        runtime_state = _text(assigned_review.get("runtime_state"))
        if runtime_state:
            if runtime_state != "completed":
                raise APError(
                    f"Reviewer runtime state={runtime_state} cannot be recorded by task-review."
                )
            if assignment is None:
                raise APError("Reviewer runtime result has no validated assignment.")
            if assigned_review.get("runtime_exit_code") != 0:
                raise APError("Reviewer runtime did not exit successfully.")
            expected_result_path, expected_receipt_path = _review_runtime_paths(
                control_repo,
                task_id,
                fingerprint,
            )
            result_path = Path(_text(assigned_review.get("runtime_result_path"))).resolve()
            receipt_path = Path(_text(assigned_review.get("runtime_receipt_path"))).resolve()
            if result_path != expected_result_path.resolve():
                raise APError("Reviewer runtime result path does not match Git-local task state.")
            if receipt_path != expected_receipt_path.resolve():
                raise APError("Reviewer runtime receipt path does not match Git-local task state.")
            try:
                result_payload = json.loads(_read_bounded_reviewer_output(result_path))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise APError("Reviewer runtime result file is invalid JSON.") from exc
            if not isinstance(result_payload, dict):
                raise APError("Reviewer runtime result file must contain one JSON object.")
            _validate_orchestration_contract("result", result_payload)
            normalized_result = _normalize_reviewer_runtime_result(assignment, result_payload)
            if result_payload != normalized_result:
                raise APError("Reviewer runtime result file is not the canonical bound result.")
            if _text(result_payload.get("verdict")) != _text(args.verdict):
                raise APError(
                    "Reviewer runtime verdict does not match the requested task-review verdict."
                )
            receipt = _validate_bound_review_runtime_receipt(
                control_repo,
                manifest,
                assignment,
                receipt_path,
                "completed",
            )
            if int(receipt.get("schema") or 0) == 2:
                expected_event_log_path = _review_runtime_event_log_path(
                    control_repo,
                    task_id,
                    fingerprint,
                ).resolve()
                if Path(_text(receipt.get("event_log_path"))).resolve() != expected_event_log_path:
                    raise APError("Reviewer runtime event log path is not canonical.")
                if Path(_text(assigned_review.get("runtime_event_log_path"))).resolve() != expected_event_log_path:
                    raise APError("Reviewer runtime event log manifest binding is invalid.")
                if _private_review_file_sha256(expected_event_log_path, "event log") != _text(
                    receipt.get("event_log_sha256")
                ):
                    raise APError("Reviewer runtime event log SHA-256 binding is invalid.")
            expected_receipt = {
                "task_id": task_id,
                "reviewer": reviewer,
                "diff_fingerprint": fingerprint,
                "assignment_sha256": _text(assigned_review.get("assignment_sha256")),
                "diff_artifact_path": _text(assignment.get("diff_artifact_path")),
                "diff_artifact_sha256": _text(assignment.get("diff_artifact_sha256")),
                "result_path": str(expected_result_path),
                "status": "completed",
                "verdict": _text(args.verdict),
                "result_sha256": _review_result_file_sha256(result_path),
            }
            receipt_mismatches = [
                field
                for field, expected in expected_receipt.items()
                if receipt.get(field) != expected
            ]
            if receipt_mismatches:
                raise APError(
                    "Reviewer runtime receipt does not bind the recorded result: "
                    + ", ".join(receipt_mismatches)
                )
        deadline_at = _text(assigned_review.get("deadline_at"))
        completed_at = _dt.datetime.now(_dt.timezone.utc)
        if (
            _text(assigned_review.get("runtime_state")) == "completed"
            and _text(assigned_review.get("runtime_finished_at"))
        ):
            completed_at = _parse_iso_timestamp(
                assigned_review.get("runtime_finished_at"),
                "runtime_finished_at",
            )
        if deadline_at and completed_at > _parse_iso_timestamp(deadline_at, "deadline_at"):
            raise APError(
                "Review assignment deadline expired; the single review attempt is blocked."
            )
        review_state = {
            "verdict": args.verdict,
            "diff_base": _text(manifest.get("base_sha")),
            "diff_head": _resolve_commit(worktree, "HEAD"),
            "diff_fingerprint": fingerprint,
            "reviewer": reviewer,
            "reviewed_at": _now_iso(),
            "reason": "",
            "assignment_path": assignment_path,
            "assignment_sha256": _text(assigned_review.get("assignment_sha256")),
            "diff_artifact_path": _text(assigned_review.get("diff_artifact_path")),
            "diff_artifact_sha256": _text(assigned_review.get("diff_artifact_sha256")),
            "diff_artifact_format": _text(assigned_review.get("diff_artifact_format")),
            "issued_at": _text(assigned_review.get("issued_at")),
            "deadline_at": deadline_at,
            "review_depth": _text(manifest.get("review_depth")),
            "review_timeout_seconds": int(manifest.get("review_timeout_seconds") or 0),
        }
        for field in _REVIEW_RUNTIME_FIELDS:
            if field in assigned_review:
                review_state[field] = assigned_review[field]
        manifest["review"] = review_state
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
    if _text(manifest.get("execution_mode")).lower() == "direct":
        timeout_s = float(_concurrency_cfg(cfg).get("lock_timeout_sec") or 30)
        with (
            _repo_lock(repo, "integration", timeout_s=timeout_s),
            _repo_lock(repo, f"task-{task_id}", timeout_s=timeout_s),
        ):
            manifest = _load_task_manifest(repo, task_id)
            if repo.resolve() != Path(_text(manifest.get("worktree_path"))).resolve():
                raise APError("Run task-finish for a direct task from its current checkout.")
            if _task_commit_paths(repo) or _resolve_commit(repo, "HEAD") != _text(manifest.get("base_sha")):
                raise APError("Direct task still has changes or commits; use commit-push instead of task-finish.")
            _clear_direct_task(repo, manifest)
        print(f"[task-finish] OK task={task_id} execution_mode=direct no temporary branch existed")
        return
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
    if _text(manifest.get("execution_mode")).lower() == "direct":
        raise APError("Direct tasks push their current target branch in commit-push and do not use task-integrate.")
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


def _worktree_task_ids(repo: Path) -> set[str]:
    task_ids: set[str] = set()
    for line in run(["git", "worktree", "list", "--porcelain"], cwd=repo).stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        worktree = Path(line[len("worktree ") :].strip())
        payload = _active_task_manifest(worktree) if worktree.exists() else None
        if not payload:
            continue
        try:
            task_ids.add(_validate_task_id(_text(payload.get("task_id"))))
        except APError:
            continue
    return task_ids


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
            _delete_task_manifest(repo, manifest)
        run(["git", "worktree", "prune"], cwd=repo, check=False)

        active_worktree_tasks = _worktree_task_ids(repo)
        review_root = _task_review_root(repo)
        _cleanup_stale_review_snapshots(review_root, legacy_root=True)
        for review_dir in sorted(review_root.iterdir()) if review_root.exists() else []:
            if not review_dir.is_dir() or review_dir.is_symlink():
                continue
            try:
                orphan_task_id = _validate_task_id(review_dir.name)
            except APError:
                continue
            if _task_registry_path(repo, orphan_task_id).exists() or orphan_task_id in active_worktree_tasks:
                continue
            with _repo_lock(repo, f"task-{orphan_task_id}", timeout_s=timeout_s):
                if _task_registry_path(repo, orphan_task_id).exists():
                    continue
                if orphan_task_id in _worktree_task_ids(repo):
                    continue
                _delete_task_review_artifacts(repo, orphan_task_id)

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
    if _text(review.get("verdict")) in {"approved", "runtime-bypassed"}:
        review["diff_head"] = commit_sha
        review["diff_fingerprint"] = _task_review_fingerprint(repo, manifest)
        manifest["review"] = review
    _save_task_manifest(repo, manifest)
    return commit_sha


def _clear_direct_task(repo: Path, manifest: dict) -> None:
    active_path = _worktree_manifest_path(repo)
    active = _read_json_object(active_path)
    removed_active = False
    if active and _text(active.get("task_uuid")) == _text(manifest.get("task_uuid")):
        try:
            active_path.unlink(missing_ok=True)
            removed_active = True
        except OSError as exc:
            raise APError(f"Cannot remove direct task checkout state: {active_path}: {exc}") from exc
    try:
        _delete_task_manifest(repo, manifest)
    except APError as exc:
        if removed_active and active:
            try:
                _write_json_object(active_path, active)
            except (APError, OSError) as restore_exc:
                raise APError(
                    f"Direct task cleanup failed ({exc}) and its checkout state could not be restored: "
                    f"{restore_exc}"
                ) from restore_exc
        raise


def _cmd_direct_commit_push_locked(
    args: argparse.Namespace,
    repo: Path,
    cfg: dict,
    manifest: dict,
) -> None:
    _require_current_writer(manifest, args)
    _require_dependencies(repo, manifest, _text(manifest.get("base_sha")))
    _reconcile_task_risk(repo, cfg, manifest)
    _require_approved_review(repo, cfg, manifest)
    branch = _current_branch(repo)
    target = _text(manifest.get("target_branch"))
    if branch != target:
        raise APError(f"Direct task branch changed: current={branch or '(detached)'}, expected={target}.")
    working_paths = _task_commit_paths(repo)
    head = _resolve_commit(repo, "HEAD")
    pending_commit = _text(manifest.get("last_commit"))
    if not working_paths and not (pending_commit and pending_commit == head):
        if head != _text(manifest.get("base_sha")):
            raise APError(
                "Direct task HEAD moved without a recorded commit-push result; refusing to guess ownership."
            )
        _clear_direct_task(repo, manifest)
        print(f"[commit-push] NOOP task={manifest['task_id']} execution_mode=direct; no changes")
        return

    if pending_commit and pending_commit == head and not working_paths:
        commit_sha = pending_commit
        plan = _resolve_execution_plan(cfg, repo, base_ref=_text(manifest.get("base_sha")))
    else:
        task_paths = _task_staging_paths(repo, cfg, manifest)
        _preflight_exact_paths(repo, task_paths)
        cmd_doctor(
            argparse.Namespace(
                repo=str(repo),
                profile=_text(getattr(args, "profile", "")).lower(),
                mode=_text(getattr(args, "mode", "")).lower(),
            )
        )
        plan = _resolve_execution_plan(
            cfg,
            repo,
            requested_profile=_text(getattr(args, "profile", "")).lower(),
            requested_mode=_text(getattr(args, "mode", "")).lower(),
            base_ref=_text(manifest.get("base_sha")),
        )
        before_gate = _task_content_fingerprint(repo, cfg, manifest)
        receipt = _reuse_final_gate_receipt(
            repo,
            cfg,
            manifest,
            plan,
            _text(manifest.get("base_sha")),
        )
        if receipt:
            print(
                "[light-gate] REUSED task="
                f"{manifest['task_id']} passed_at={receipt.get('passed_at')}"
            )
        else:
            cmd_light_gate(
                argparse.Namespace(
                    repo=str(repo),
                    scope="changed",
                    profile=plan["profile"],
                    mode="dev",
                    base=_text(manifest.get("base_sha")),
                    explain=False,
                )
            )
        after_gate = _task_content_fingerprint(repo, cfg, manifest)
        if after_gate != before_gate:
            raise APError("The final gate changed direct-task files; inspect them and retry commit-push.")
        manifest = _require_task_context(repo, cfg, args.task_id)
        _require_current_writer(manifest, args)
        _require_approved_review(repo, cfg, manifest)
        task_paths = _task_staging_paths(repo, cfg, manifest)
        staged = _stage_exact_paths(repo, task_paths)
        if not staged:
            _clear_direct_task(repo, manifest)
            print(f"[commit-push] NOOP task={manifest['task_id']} execution_mode=direct; no changes")
            return
        unstaged = _unstaged_task_paths(repo)
        if unstaged:
            raise APError("Direct-task files changed while staging; refusing to commit:\n- " + "\n- ".join(unstaged))
        _require_staged_review_matches(repo, cfg, manifest)
        _extend_final_gate_receipt(
            repo,
            cfg,
            manifest,
            plan,
            _text(manifest.get("base_sha")),
        )
        commit_sha = _commit_exact_index(repo, args.msg)
        manifest["state"] = "push-pending"
        manifest["last_commit"] = commit_sha
        _save_task_manifest(repo, manifest)
    remote = _text(manifest.get("remote")) or "origin"
    push = run(
        ["git", "push", "--set-upstream", remote, f"{commit_sha}:refs/heads/{target}"],
        cwd=repo,
        check=False,
    )
    if push.returncode != 0:
        raise APError(
            f"Direct target push failed; the local commit is preserved on {branch}.\n"
            f"{push.stdout}\n{push.stderr}"
        )
    remote_tip = _remote_branch_tip(repo, remote, target)
    if remote_tip != commit_sha:
        raise APError(
            f"Direct target verification failed: expected {commit_sha}, got {remote_tip or '(missing)'}"
        )
    _clear_direct_task(repo, manifest)
    print(
        f"[commit-push] OK task={manifest['task_id']} execution_mode=direct "
        f"profile={plan['profile']} scope=changed commit={commit_sha}"
    )


def _cmd_commit_push_locked(
    args: argparse.Namespace,
    repo: Path,
    cfg: dict,
    manifest: dict,
) -> None:
    if _text(manifest.get("execution_mode")).lower() == "direct":
        _cmd_direct_commit_push_locked(args, repo, cfg, manifest)
        return
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
    _reconcile_task_risk(repo, cfg, manifest)
    _require_approved_review(repo, cfg, manifest)
    working_paths = _task_commit_paths(repo)
    head = _resolve_commit(repo, "HEAD")
    pending_commit = _text(manifest.get("last_commit"))
    if pending_commit and pending_commit == head and not working_paths:
        plan = _resolve_execution_plan(cfg, repo, base_ref=_text(manifest.get("base_sha")))
        _push_current_task(repo, manifest, pending_commit)
        print(
            f"[commit-push] OK - profile={plan['profile']} mode={plan['effective_mode']} "
            f"scope={plan['selected_scope']} commit={pending_commit}"
        )
        return
    protected = set(manifest.get("initial_untracked") or [])
    _cleanup_generated_noise(repo, protected_paths=protected)
    task_paths = _task_staging_paths(repo, cfg, manifest)
    _preflight_exact_paths(repo, task_paths)
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
    before_gate = _task_content_fingerprint(repo, cfg, manifest)
    receipt = _reuse_final_gate_receipt(repo, cfg, manifest, plan, base_ref)
    if receipt:
        print(
            "[light-gate] REUSED task="
            f"{manifest['task_id']} passed_at={receipt.get('passed_at')}"
        )
    else:
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

    pre_stage_fingerprint = _task_content_fingerprint(repo, cfg, manifest)
    manifest = _require_task_context(repo, cfg, args.task_id)
    _require_current_writer(manifest, args)
    _require_approved_review(repo, cfg, manifest)
    if _task_content_fingerprint(repo, cfg, manifest) != pre_stage_fingerprint:
        raise APError("Task-owned files changed immediately before staging; refusing to commit.")
    task_paths = _task_staging_paths(repo, cfg, manifest)
    staged = _stage_exact_paths(repo, task_paths)
    if not staged:
        raise APError("Nothing to commit.")
    unstaged = _unstaged_task_paths(repo)
    if unstaged:
        raise APError(
            "Task-owned files changed while staging; refusing to commit:\n- " + "\n- ".join(unstaged)
        )
    _require_staged_review_matches(repo, cfg, manifest)
    manifest = _require_task_context(repo, cfg, args.task_id)
    _extend_final_gate_receipt(repo, cfg, manifest, plan, base_ref)

    committed_sha = _commit_exact_index(repo, msg)
    manifest["state"] = "push-pending"
    manifest["last_commit"] = committed_sha
    _save_task_manifest(repo, manifest)
    _push_current_task(repo, manifest, committed_sha)
    print(f"[commit-push] OK - profile={plan['profile']} mode={mode} scope={plan['selected_scope']}")


def cmd_commit_push(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    ensure_git_repo(repo)
    cfg = _load_cfg(repo)
    _require_workflow_policy_clean(repo, cfg)
    manifest = _require_task_context(repo, cfg, args.task_id)
    _require_current_writer(manifest, args)
    lock_name = f"task-{_validate_task_id(args.task_id)}"
    timeout_s = float(_concurrency_cfg(cfg).get("lock_timeout_sec") or 30)
    with _repo_lock(repo, lock_name, timeout_s=timeout_s):
        manifest = _require_task_context(repo, cfg, args.task_id)
        _require_current_writer(manifest, args)
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

    s = sp.add_parser("managed-scaffold-converge", help=argparse.SUPPRESS)
    s.add_argument("group", choices=scaffold_groups())
    s.add_argument("--write", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_managed_scaffold_converge)

    s = sp.add_parser("upgrade")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--write", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_upgrade)

    s = sp.add_parser("project-converge", help=argparse.SUPPRESS)
    s.add_argument("--write", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_project_converge)

    s = sp.add_parser("project-config-prepare", help=argparse.SUPPRESS)
    s.add_argument("--write", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_project_config_prepare)

    s = sp.add_parser("project-config-finalize", help=argparse.SUPPRESS)
    s.add_argument("--write", action="store_true")
    s.add_argument("--json", action="store_true")
    s.add_argument("--engineering-sha256", required=True)
    s.add_argument("--overlay-sha256", required=True)
    s.add_argument("--template-sha256", required=True)
    s.set_defaults(func=cmd_project_config_finalize)

    s = sp.add_parser("project-file-safe", help=argparse.SUPPRESS)
    s.add_argument("operation", choices=["write", "create", "chmod", "chmod-batch"])
    s.add_argument("--path", default="")
    s.add_argument("--mode", default="")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_project_file_safe)

    s = sp.add_parser("install-io", help=argparse.SUPPRESS)
    s.add_argument("operation", choices=["switch", "recover", "complete"])
    s.add_argument("--old-skill-present", action="store_true")
    s.add_argument("--old-manifest-present", action="store_true")
    s.add_argument("--old-engineering-present", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_install_io)

    s = sp.add_parser(
        "config-effective",
        help="Show a redacted summary of managed defaults plus project overrides",
    )
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_config_effective)

    s = sp.add_parser(
        "feedback-collect",
        help="Read bounded metadata-only Skill feedback reports from explicit projects",
    )
    s.add_argument("--project", action="append", required=True)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_feedback_collect)

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
    s.add_argument("--task-kind", choices=sorted(_REQUESTED_TASK_KINDS), default="auto")
    s.add_argument("--claim-direct", action="store_true")
    s.add_argument("--claim-owner")
    s.add_argument("--continue-direct", action="store_true")
    s.add_argument("--direct-claim")
    s.add_argument("--writers", type=int, default=1)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_classify)

    s = sp.add_parser("agent-contract-check")
    s.add_argument("--kind", choices=["assignment", "result", "agentPlan", "classify"], required=True)
    source = s.add_mutually_exclusive_group(required=True)
    source.add_argument("--file")
    source.add_argument("--payload")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_agent_contract_check)

    s = sp.add_parser(
        "agent-result-template",
        help="Generate a complete reviewer result from a validated assignment",
    )
    source = s.add_mutually_exclusive_group(required=True)
    source.add_argument("--file")
    source.add_argument("--payload")
    s.add_argument(
        "--verdict",
        choices=["approved", "changes-requested", "blocked"],
        required=True,
    )
    s.set_defaults(func=cmd_agent_result_template)

    s = sp.add_parser("validation-map-check")
    s.add_argument("--base")
    s.add_argument("--path", action="append")
    s.add_argument("--tracked", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_validation_map_check)

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
    s.add_argument("--component", choices=["frontend", "backend"], default="backend")
    s.add_argument("--path")
    s.add_argument("--timeout-sec", type=int)
    s.set_defaults(func=cmd_wait_health)

    s = sp.add_parser("verify-jenkins")
    s.add_argument("--component", choices=["all", "frontend", "backend"], default="all")
    s.set_defaults(func=cmd_verify_jenkins)

    s = sp.add_parser("verify-jenkins-build")
    s.add_argument("--component", choices=["frontend", "backend"])
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
    s.add_argument("--writers", type=int, default=1)
    s.add_argument("--isolated", action="store_true")
    s.add_argument("--review-required", action="store_true")
    s.add_argument("--review-depth", choices=["focused", "deep"])
    s.add_argument("--continue-direct", action="store_true")
    s.add_argument("--direct-claim")
    s.add_argument(
        "--force-lifecycle",
        action="store_true",
        help="Use only when the user explicitly requests lifecycle tracking for clean serial work",
    )
    s.add_argument("--owned-path", action="append")
    s.add_argument("--depends-on", action="append", metavar="TASK_ID=SHA")
    s.add_argument("--no-fetch", action="store_true")
    s.set_defaults(func=cmd_task_start)

    s = sp.add_parser("task-status")
    s.add_argument("task_id", nargs="?")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_task_status)

    s = sp.add_parser("task-scope-add")
    s.add_argument("task_id")
    s.add_argument("--owned-path", action="append", required=True)
    s.add_argument("--writer")
    s.add_argument("--lease-generation", type=int)
    s.add_argument("--intent")
    s.add_argument("--review-required", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_task_scope_add)

    s = sp.add_parser(
        "review-assignment",
        help="Generate and persist a deadline-bound reviewer assignment for a registered task",
    )
    s.add_argument("task_id")
    s.add_argument("--reviewer", required=True)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_review_assignment)

    s = sp.add_parser(
        "review-artifact",
        help="Verify and emit the immutable Git-local diff artifact for a reviewer assignment",
    )
    s.add_argument("--file", required=True)
    s.set_defaults(func=cmd_review_artifact)

    s = sp.add_parser(
        "review-run",
        help="Run the independent Codex Reviewer under the assignment's fixed runtime deadline",
    )
    s.add_argument("task_id")
    s.add_argument("--reviewer", required=True)
    s.add_argument("--json", action="store_true")
    s.add_argument("--runner-command-json", help=argparse.SUPPRESS)
    s.set_defaults(func=cmd_review_run)

    s = sp.add_parser(
        "review-runtime-override",
        help="Record an explicit user-authorized bypass for an exhausted Reviewer runtime failure",
    )
    s.add_argument("task_id")
    s.add_argument("--diff-fingerprint", required=True)
    s.add_argument("--authorized-by", required=True)
    s.add_argument("--authorization-ref", required=True)
    s.add_argument("--reason", required=True)
    s.add_argument("--evidence", action="append", required=True)
    s.add_argument("--confirm-runtime-bypass", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_review_runtime_override)

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
        repo = Path(args.repo).resolve()
        tokenized_write = (
            args.cmd == "project-file-safe"
            or (
                args.cmd in {
                    "managed-scaffold-converge",
                    "project-config-finalize",
                    "project-converge",
                }
                and bool(getattr(args, "write", False))
            )
        )
        if args.cmd == "install-io":
            pass
        elif tokenized_write:
            _require_active_install_transaction(repo)
        elif args.cmd != "config-effective":
            _require_no_install_transaction(repo)
        args.func(args)
        return 0
    except APError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
