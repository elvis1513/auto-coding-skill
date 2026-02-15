#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoPipeline Pro Max - Core helpers"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Optional, Dict, Any

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

try:
    import requests  # type: ignore
except Exception:
    requests = None


class APError(RuntimeError):
    pass


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
    if yaml is None:
        raise APError(
            "PyYAML not installed. Install dependencies with: pip install pyyaml requests"
        )
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
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
    if requests is None:
        raise APError(
            "requests not installed. Install dependencies with: pip install pyyaml requests"
        )
    r = requests.get(url, timeout=timeout_s)
    return r.status_code


def find_config(repo: Path) -> Path:
    """Find autocoding config file (repo root preferred)."""
    candidates = [
        repo / "autocoding.config.yaml",
        repo / "docs" / "autocoding" / "config.yaml",
        repo / "docs" / "autocoding" / "config.yml",
    ]
    for c in candidates:
        if c.exists():
            return c
    # fall back to example if exists (for first-time users)
    ex = repo / "docs" / "autocoding" / "config.example.yaml"
    if ex.exists():
        return ex
    raise APError("autocoding config not found. Create autocoding.config.yaml (recommended) or docs/autocoding/config.yaml. Template: docs/autocoding/config.example.yaml")


def run_shell(command: str, cwd: Optional[Path] = None) -> None:
    """Run shell command via bash -lc for cross-tool compatibility."""
    p = subprocess.run(["bash", "-lc", command], cwd=str(cwd) if cwd else None, text=True)
    if p.returncode != 0:
        raise APError(f"Command failed ({p.returncode}): {command}")
