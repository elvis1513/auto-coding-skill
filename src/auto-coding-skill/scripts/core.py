#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoPipeline Pro Max - Core helpers"""

from __future__ import annotations

import os
import re
import signal
import shlex
import shutil
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
        repo / "docs" / "ENGINEERING.md",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise APError(
        "Project config not found. Create docs/ENGINEERING.md "
        "and put commands + runtime + jenkins fields in YAML frontmatter."
    )


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
