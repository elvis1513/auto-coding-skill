#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoPipeline Pro Max - Core helpers"""

from __future__ import annotations

import copy
import math
import os
import re
import signal
import shlex
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, Optional, Dict, Any

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

class APError(RuntimeError):
    pass


MANAGED_CONFIG_RELATIVE_PATH = Path("docs/ENGINEERING.md")
PROJECT_CONFIG_PATH = Path("docs/project/auto-coding-skill.yaml")
PROJECT_CONFIG_OVERLAY_RELATIVE_PATH = PROJECT_CONFIG_PATH
PROJECT_CONFIG_SCHEMA = "auto-coding-skill/project-config/v1"
MANAGED_CONFIG_FRONTMATTER_MAX_BYTES = 256 * 1024
PROJECT_CONFIG_OVERLAY_MAX_BYTES = 128 * 1024
PROJECT_CONFIG_MAX_YAML_DEPTH = 64
PROJECT_CONFIG_MAX_YAML_NODES = 10_000
PROJECT_CONFIG_PROTECTED_WORKFLOW_FIELDS = frozenset(
    {"skill_version", "mode", "completion"}
)


class _ConfigYamlViolation(RuntimeError):
    """Internal marker whose message never includes user-controlled YAML."""


def _is_windows_reparse_point(metadata: os.stat_result) -> bool:
    attributes = int(getattr(metadata, "st_file_attributes", 0) or 0)
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _file_identity(metadata: os.stat_result) -> tuple[int, int]:
    return int(metadata.st_dev), int(metadata.st_ino)


def runtime_requirements_path() -> Path:
    return Path(__file__).resolve().parents[1] / "requirements.txt"


def require_yaml() -> Any:
    if yaml is None:
        install = shlex.join(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--requirement",
                str(runtime_requirements_path()),
            ]
        )
        raise APError(
            f"PyYAML is missing from {sys.executable}. Run: {install}"
        )
    return yaml


def run(cmd: Iterable[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(list(cmd), cwd=str(cwd) if cwd else None, text=True, capture_output=True)
    if check and p.returncode != 0:
        raise APError(
            f"Command failed ({p.returncode}): {' '.join(cmd)}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}"
        )
    return p


def ensure_git_repo(repo: Path) -> None:
    try:
        run(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo)
    except APError as e:
        raise APError(f"Not a git repository: {repo}\n{e}") from e


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise APError(f"YAML not found: {path}")
    yaml_module = require_yaml()
    if path.suffix.lower() in {".md", ".markdown"}:
        text = path.read_text(encoding="utf-8")
        m = re.match(r"^---\s*\n(.*?)\n---\s*(\n|$)", text, flags=re.DOTALL)
        if not m:
            raise APError(
                f"Config markdown frontmatter not found: {path}\n"
                "Expected YAML frontmatter wrapped by '---' at top of file."
            )
        data = yaml_module.safe_load(m.group(1))
    else:
        with path.open("r", encoding="utf-8") as f:
            data = yaml_module.safe_load(f)
    return data or {}


def copy_tree(src: Path, dst: Path) -> None:
    if src.is_file():
        if src.name == ".DS_Store" or src.name.endswith(".pyc"):
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return
    for root, _, files in os.walk(src):
        root_p = Path(root)
        if "__pycache__" in root_p.parts:
            continue
        rel = root_p.relative_to(src)
        for fn in files:
            if fn == ".DS_Store" or fn.endswith(".pyc"):
                continue
            s = root_p / fn
            d = dst / rel / fn
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)


def http_get_status(url: str, timeout_s: int = 5) -> int:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def find_config(repo: Path) -> Path:
    """Find single source project config file."""
    candidates = [
        repo / MANAGED_CONFIG_RELATIVE_PATH,
    ]
    for c in candidates:
        if c.exists():
            return c
    raise APError(
        "Project config not found. Create docs/ENGINEERING.md "
        "and put commands + runtime + jenkins fields in YAML frontmatter."
    )


def _config_source_name(relative: Path) -> str:
    if relative == MANAGED_CONFIG_RELATIVE_PATH:
        return "Managed project configuration"
    return "Project configuration overlay"


def _read_project_config_file(
    repo: Path,
    relative: Path,
    *,
    max_bytes: int,
    require_eof: bool,
) -> bytes | None:
    """Read a bounded project-relative config without following in-repo links."""
    source = _config_source_name(relative)
    if relative.is_absolute() or not relative.parts or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise APError(f"{source} path is invalid.")
    if max_bytes <= 0:
        raise APError(f"{source} read bound is invalid.")

    repo = Path(repo)
    if os.name == "nt":
        try:
            repo_metadata = repo.lstat()
            if _is_windows_reparse_point(repo_metadata) or not stat.S_ISDIR(repo_metadata.st_mode):
                raise APError(f"{source} repository root must be a real directory.")
            checked_directories = [(repo, _file_identity(repo_metadata))]
            current = repo
            for part in relative.parts[:-1]:
                current = current / part
                if not os.path.lexists(current):
                    return None
                metadata = current.lstat()
                if _is_windows_reparse_point(metadata) or not stat.S_ISDIR(metadata.st_mode):
                    raise APError(f"{source} parent must be a real directory.")
                checked_directories.append((current, _file_identity(metadata)))
            target = current / relative.parts[-1]
            if not os.path.lexists(target):
                return None
            metadata = target.lstat()
            if _is_windows_reparse_point(metadata) or not stat.S_ISREG(metadata.st_mode):
                raise APError(f"{source} must be a regular non-symlink file.")
            if require_eof and metadata.st_size > max_bytes:
                raise APError(f"{source} exceeds its size limit.")
            with target.open("rb") as handle:
                opened = os.fstat(handle.fileno())
                if not stat.S_ISREG(opened.st_mode) or _file_identity(opened) != _file_identity(metadata):
                    raise APError(f"{source} changed during its safety check.")
                for directory, identity in checked_directories:
                    checked = directory.lstat()
                    if (
                        _is_windows_reparse_point(checked)
                        or not stat.S_ISDIR(checked.st_mode)
                        or _file_identity(checked) != identity
                    ):
                        raise APError(f"{source} parent changed during its safety check.")
                payload = handle.read(max_bytes + 1)
        except APError:
            raise
        except OSError as exc:
            raise APError(f"{source} could not be read safely.") from exc
    else:
        directory_flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptors: list[int] = []
        file_descriptor = -1
        try:
            current = os.open(repo, directory_flags)
            descriptors.append(current)
            for part in relative.parts[:-1]:
                try:
                    metadata = os.stat(part, dir_fd=current, follow_symlinks=False)
                except FileNotFoundError:
                    return None
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                    raise APError(f"{source} parent must be a real directory.")
                next_descriptor = os.open(part, directory_flags, dir_fd=current)
                descriptors.append(next_descriptor)
                current = next_descriptor
            try:
                metadata = os.stat(
                    relative.parts[-1],
                    dir_fd=current,
                    follow_symlinks=False,
                )
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                    raise APError(f"{source} must be a regular non-symlink file.")
                file_descriptor = os.open(
                    relative.parts[-1],
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=current,
                )
            except FileNotFoundError:
                return None
            metadata = os.fstat(file_descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise APError(f"{source} must be a regular non-symlink file.")
            if require_eof and metadata.st_size > max_bytes:
                raise APError(f"{source} exceeds its size limit.")
            with os.fdopen(file_descriptor, "rb") as handle:
                file_descriptor = -1
                payload = handle.read(max_bytes + 1)
        except APError:
            raise
        except OSError as exc:
            raise APError(f"{source} could not be read safely.") from exc
        finally:
            if file_descriptor >= 0:
                os.close(file_descriptor)
            for descriptor in reversed(descriptors):
                try:
                    os.close(descriptor)
                except OSError:
                    pass

    if require_eof and len(payload) > max_bytes:
        raise APError(f"{source} exceeds its size limit.")
    return payload


_FRONTMATTER_BYTES_RE = re.compile(
    rb"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)",
    flags=re.DOTALL,
)


def _decode_managed_frontmatter(payload: bytes) -> str:
    match = _FRONTMATTER_BYTES_RE.match(payload)
    if not match or match.end() > MANAGED_CONFIG_FRONTMATTER_MAX_BYTES:
        raise APError(
            "Managed project configuration must contain bounded YAML frontmatter at the file start."
        )
    try:
        return match.group(1).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise APError("Managed project configuration frontmatter must be UTF-8.") from exc


def _strict_yaml_mapping(text: str, source: str) -> Dict[str, Any]:
    yaml_module = require_yaml()
    merge_tag = "tag:yaml.org,2002:merge"

    class StrictConfigLoader(yaml_module.SafeLoader):
        def compose_node(self, parent: Any, index: Any) -> Any:
            event = self.peek_event()
            if isinstance(event, yaml_module.events.AliasEvent) or getattr(event, "anchor", None):
                raise _ConfigYamlViolation("alias")
            depth = getattr(self, "_project_config_depth", 0)
            nodes = getattr(self, "_project_config_nodes", 0) + 1
            if depth >= PROJECT_CONFIG_MAX_YAML_DEPTH or nodes > PROJECT_CONFIG_MAX_YAML_NODES:
                raise _ConfigYamlViolation("complexity")
            self._project_config_depth = depth + 1
            self._project_config_nodes = nodes
            try:
                return super().compose_node(parent, index)
            finally:
                self._project_config_depth = depth

        def construct_mapping(self, node: Any, deep: bool = False) -> Dict[str, Any]:
            if not isinstance(node, yaml_module.nodes.MappingNode):
                raise _ConfigYamlViolation("mapping")
            result: Dict[str, Any] = {}
            for key_node, value_node in node.value:
                if getattr(key_node, "tag", "") == merge_tag:
                    raise _ConfigYamlViolation("merge")
                key = self.construct_object(key_node, deep=deep)
                if not isinstance(key, str):
                    raise _ConfigYamlViolation("key")
                if key in result:
                    raise _ConfigYamlViolation("duplicate")
                result[key] = self.construct_object(value_node, deep=deep)
            return result

    try:
        value = yaml_module.load(text, Loader=StrictConfigLoader)
    except _ConfigYamlViolation as exc:
        messages = {
            "alias": "must not use YAML anchors or aliases.",
            "merge": "must not use YAML merge keys.",
            "mapping": "contains an invalid YAML mapping.",
            "key": "must use string YAML mapping keys.",
            "duplicate": "contains duplicate YAML keys.",
            "complexity": "exceeds the YAML complexity limit.",
        }
        raise APError(f"{source} {messages.get(str(exc), 'contains invalid YAML.')}") from None
    except Exception:
        raise APError(f"{source} contains invalid YAML.") from None

    if value is None:
        raise APError(f"{source} must not contain null values.")
    if not isinstance(value, dict):
        raise APError(f"{source} root must be a mapping.")
    _validate_config_value(value, source)
    return value


def _validate_config_value(value: Any, source: str) -> None:
    if value is None:
        raise APError(f"{source} must not contain null values.")
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise APError(f"{source} must use string YAML mapping keys.")
            _validate_config_string(key, source)
            _validate_config_value(nested, source)
        return
    if isinstance(value, list):
        for nested in value:
            _validate_config_value(nested, source)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise APError(f"{source} contains an unsupported scalar value.")
    if isinstance(value, str):
        _validate_config_string(value, source)
        return
    if not isinstance(value, (str, bool, int, float)):
        raise APError(f"{source} contains an unsupported scalar value.")


def _validate_config_string(value: str, source: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise APError(f"{source} contains an invalid Unicode string.") from None
    if any(
        (ord(char) < 0x20 and char not in {"\t", "\n", "\r"})
        or 0x7F <= ord(char) <= 0x9F
        for char in value
    ):
        raise APError(f"{source} contains an unsupported control character.")


def parse_managed_config_payload(payload: bytes) -> Dict[str, Any]:
    """Strictly parse a bounded managed ENGINEERING document already in memory."""
    frontmatter = _decode_managed_frontmatter(payload)
    return _strict_yaml_mapping(frontmatter, "Managed project configuration")


def load_managed_config(repo: Path) -> Dict[str, Any]:
    """Load the Skill-managed defaults from docs/ENGINEERING.md frontmatter."""
    payload = _read_project_config_file(
        repo,
        MANAGED_CONFIG_RELATIVE_PATH,
        max_bytes=MANAGED_CONFIG_FRONTMATTER_MAX_BYTES,
        require_eof=False,
    )
    if payload is None:
        raise APError("Managed project configuration was not found.")
    return parse_managed_config_payload(payload)


def parse_project_overrides_payload(payload: bytes) -> Dict[str, Any]:
    """Strictly parse a bounded project overlay already in memory."""
    if len(payload) > PROJECT_CONFIG_OVERLAY_MAX_BYTES:
        raise APError("Project configuration overlay exceeds its size limit.")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise APError("Project configuration overlay must be UTF-8.") from exc
    document = _strict_yaml_mapping(text, "Project configuration overlay")
    if set(document) != {"schema", "overrides"}:
        raise APError("Project configuration overlay has unsupported top-level wrapper fields.")
    if document.get("schema") != PROJECT_CONFIG_SCHEMA:
        raise APError("Project configuration overlay schema is unsupported.")
    overrides = document.get("overrides")
    if not isinstance(overrides, dict):
        raise APError("Project configuration overlay overrides must be a mapping.")
    workflow = overrides.get("workflow")
    if workflow is not None:
        if not isinstance(workflow, dict) or PROJECT_CONFIG_PROTECTED_WORKFLOW_FIELDS.intersection(
            workflow
        ):
            raise APError(
                "Project configuration overlay cannot override managed workflow fields."
            )
    return overrides


def load_project_overrides(repo: Path) -> Dict[str, Any]:
    """Load the optional project-owned overlay after validating its wrapper."""
    payload = _read_project_config_file(
        repo,
        PROJECT_CONFIG_OVERLAY_RELATIVE_PATH,
        max_bytes=PROJECT_CONFIG_OVERLAY_MAX_BYTES,
        require_eof=True,
    )
    if payload is None:
        return {}
    return parse_project_overrides_payload(payload)


def merge_project_config(
    defaults: Dict[str, Any],
    overrides: Dict[str, Any],
) -> Dict[str, Any]:
    """Recursively merge mappings; project scalars and lists replace defaults."""
    if not isinstance(defaults, dict) or not isinstance(overrides, dict):
        raise APError("Effective project configuration layers must be mappings.")
    _validate_config_value(defaults, "Managed project configuration")
    _validate_config_value(overrides, "Project configuration overlay")
    workflow = overrides.get("workflow")
    if workflow is not None:
        if not isinstance(workflow, dict) or PROJECT_CONFIG_PROTECTED_WORKFLOW_FIELDS.intersection(
            workflow
        ):
            raise APError(
                "Project configuration overlay cannot override managed workflow fields."
            )

    def merge(base: Dict[str, Any], project: Dict[str, Any]) -> Dict[str, Any]:
        result = copy.deepcopy(base)
        for key, value in project.items():
            current = result.get(key)
            if isinstance(current, dict) and isinstance(value, dict):
                result[key] = merge(current, value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    return merge(defaults, overrides)


def load_effective_config(repo: Path) -> Dict[str, Any]:
    """Return managed defaults merged with the project-owned overlay."""
    return merge_project_config(load_managed_config(repo), load_project_overrides(repo))


def run_shell(command: str, cwd: Optional[Path] = None, timeout_s: Optional[float] = None) -> None:
    """Run in the caller's environment and terminate the process group on timeout."""
    p = subprocess.Popen(
        ["bash", "-c", command],
        cwd=str(cwd) if cwd else None,
        text=True,
        start_new_session=True,
    )
    try:
        returncode = p.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        os.killpg(p.pid, signal.SIGTERM)
        try:
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
        raise APError(f"Command timed out after {timeout_s:.1f}s: {command}") from exc
    if returncode != 0:
        raise APError(f"Command failed ({returncode}): {command}")
