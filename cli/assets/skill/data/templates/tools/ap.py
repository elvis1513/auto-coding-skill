#!/usr/bin/env python3
"""Compatibility launcher for the project-local auto-coding runtime."""

import os
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[3]
scripts = [
    repo / ".agents" / "skills" / "auto-coding-skill" / "scripts" / "ap.py",
    Path.home() / ".agents" / "skills" / "auto-coding-skill" / "scripts" / "ap.py",
]
script = next((candidate for candidate in scripts if candidate.exists()), None)
if script is None:
    raise SystemExit("auto-coding runtime not found; run `autocoding init` first")
os.execv(sys.executable, [sys.executable, str(script), *sys.argv[1:]])
