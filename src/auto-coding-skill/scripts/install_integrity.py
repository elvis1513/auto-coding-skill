#!/usr/bin/env python3
"""Generate and verify the bounded auto-coding-skill install manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tomllib
from pathlib import Path
from typing import Any

from scaffold_templates import MANAGED_FRAMEWORK_DOCS, templates_for


SCHEMA_VERSION = 1
MANIFEST_PATH = Path(".agents/managed-install.json")
SKIPPED_NAMES = {"__pycache__", ".DS_Store"}
SKIPPED_SUFFIXES = {".pyc", ".pyo", ".pyd"}
STRATEGIES = {"exact", "normalized-agent", "managed-workflow"}


def _is_generated_noise(path: Path) -> bool:
    return any(part in SKIPPED_NAMES for part in path.parts) or path.suffix.lower() in SKIPPED_SUFFIXES


def _files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        (path for path in root.rglob("*") if path.is_file() and not _is_generated_noise(path.relative_to(root))),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_escaped(text: str, index: int) -> bool:
    slashes = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        slashes += 1
        index -= 1
    return slashes % 2 == 1


def _next_multiline_state(line: str, initial: str) -> str:
    state = initial
    quote = ""
    index = 0
    while index < len(line):
        if state:
            close = line.find(state, index)
            if close < 0:
                return state
            if state == '\"\"\"' and _is_escaped(line, close):
                index = close + 3
                continue
            state = ""
            index = close + 3
            continue
        if quote:
            if line[index] == quote and (quote == "'" or not _is_escaped(line, index)):
                quote = ""
            index += 1
            continue
        if line[index] == "#":
            return state
        triple = line[index:index + 3]
        if triple in {'\"\"\"', "'''"}:
            state = triple
            index += 3
            continue
        if line[index] in {'\"', "'"}:
            quote = line[index]
        index += 1
    return state


def normalize_managed_agent(text: str) -> str:
    """Remove the one supported top-level model override, preserving all other bytes."""
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"invalid managed agent TOML: {exc}") from exc
    if "model" in parsed and (not isinstance(parsed["model"], str) or not parsed["model"].strip()):
        raise ValueError("model must be a non-empty TOML string")
    lines = text.replace("\r\n", "\n").split("\n")
    matches: list[int] = []
    multiline = ""
    in_table = False
    pattern = re.compile(r"^\s*(?:model|\"model\"|'model')\s*=\s*(.+)$")
    for index, line in enumerate(lines):
        if not multiline:
            trimmed = line.lstrip()
            if trimmed.startswith("[") and not trimmed.startswith("[#"):
                in_table = True
            if not in_table and pattern.match(line):
                matches.append(index)
        multiline = _next_multiline_state(line, multiline)
    if len(matches) > 1:
        raise ValueError("model is defined more than once")
    if matches:
        del lines[matches[0]]
    return "\n".join(lines)


def managed_workflow_region(text: str) -> str:
    normalized = text.replace("\r\n", "\n")
    start = list(re.finditer(
        r"<!--\s*auto-coding-skill:managed-workflow:start\s+version=[0-9]+\.[0-9]+\.[0-9]+\s*-->",
        normalized,
    ))
    end = list(re.finditer(r"<!--\s*auto-coding-skill:managed-workflow:end\s*-->", normalized))
    if len(start) != 1 or len(end) != 1 or start[0].start() >= end[0].start():
        raise ValueError("managed workflow markers are missing or malformed")
    return normalized[start[0].start():end[0].end()]


def _entry(
    *,
    target: str,
    source: str,
    strategy: str,
    data: bytes,
    executable: bool,
    scope: str,
    version: str,
) -> dict[str, Any]:
    return {
        "path": target,
        "source": source,
        "ownership": strategy,
        "sha256": _sha256(data),
        "executable": executable,
        "scope": scope,
        "version": version,
    }


def build_manifest(skill_root: Path, agents_root: Path, version: str) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for source_path in _files(skill_root):
        rel = source_path.relative_to(skill_root).as_posix()
        entries.append(_entry(
            target=f".agents/skills/auto-coding-skill/{rel}",
            source=f"skill/{rel}",
            strategy="exact",
            data=source_path.read_bytes(),
            executable=bool(source_path.stat().st_mode & 0o111),
            scope="shared",
            version=version,
        ))
    for source_path in _files(agents_root):
        rel = source_path.relative_to(agents_root).as_posix()
        normalized = normalize_managed_agent(source_path.read_text(encoding="utf-8")).encode("utf-8")
        entries.append(_entry(
            target=f".agents/agents/{rel}",
            source=f"agents/{rel}",
            strategy="normalized-agent",
            data=normalized,
            executable=bool(source_path.stat().st_mode & 0o111),
            scope="shared",
            version=version,
        ))

    exact_project_sources = {
        "AGENTS.md": skill_root / "data/templates/bridges/AGENTS.md",
        "docs/tools/autopipeline/ap.py": skill_root / "data/templates/tools/ap.py",
    }
    for target, source_path in exact_project_sources.items():
        rel = source_path.relative_to(skill_root).as_posix()
        entries.append(_entry(
            target=target,
            source=f"skill/{rel}",
            strategy="exact",
            data=source_path.read_bytes(),
            executable=bool(source_path.stat().st_mode & 0o111),
            scope="project",
            version=version,
        ))

    engineering = skill_root / "data/templates/ENGINEERING.md"
    entries.append(_entry(
        target="docs/ENGINEERING.md",
        source="skill/data/templates/ENGINEERING.md#managed-workflow",
        strategy="managed-workflow",
        data=managed_workflow_region(engineering.read_text(encoding="utf-8")).encode("utf-8"),
        executable=bool(engineering.stat().st_mode & 0o111),
        scope="project",
        version=version,
    ))

    templates = templates_for("all")
    for target in sorted(MANAGED_FRAMEWORK_DOCS):
        entries.append(_entry(
            target=target,
            source=f"generated:scaffold_templates:{target}",
            strategy="exact",
            data=templates[target].encode("utf-8"),
            executable=False,
            scope="project",
            version=version,
        ))

    entries.sort(key=lambda item: item["path"])
    if len({item["path"] for item in entries}) != len(entries):
        raise ValueError("managed install manifest contains duplicate paths")
    return {
        "schema_version": SCHEMA_VERSION,
        "skill_version": version,
        "manifest_path": MANIFEST_PATH.as_posix(),
        "entries": entries,
        "managed_namespaces": [
            {"path": ".agents/skills/auto-coding-skill", "scope": "shared"},
            {"path": "docs/tools/autopipeline", "scope": "project"},
        ],
        "preserved": [
            ".agents/archive/**",
            ".agents/agents/* (except paths listed in entries)",
            "docs/project/**",
            "docs/architecture/structure-standard.md",
            "docs/architecture/adr/[0-9]*.md",
            "docs/design/*.md",
            "docs/interfaces/*.md",
            "docs/deployment/deploy-records/*.md",
            "docs/reviews/*.md",
        ],
    }


def render_manifest(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, ensure_ascii=False, separators=(",", ":")) + "\n"


def _safe_relative_path(raw: Any) -> Path:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise ValueError("path must be a non-empty POSIX relative path")
    path = Path(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("path must not be absolute or contain traversal")
    return path


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing manifest: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid manifest {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("managed install manifest schema_version must be 1")
    return value


def verify_managed_install(
    repo: Path,
    *,
    mode: str = "project",
    expected_version: str | None = None,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    repo = repo.resolve()
    errors: list[str] = []
    manifest_file = manifest_path or repo / MANIFEST_PATH
    try:
        manifest = _load_manifest(manifest_file)
    except ValueError as exc:
        return {"ok": False, "version": "", "checked": 0, "errors": [str(exc)]}

    version = manifest.get("skill_version")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        errors.append("manifest skill_version must be a semantic version")
        version = ""
    if expected_version and version != expected_version:
        errors.append(f"manifest version {version or '<invalid>'} does not match expected {expected_version}")
    if manifest.get("manifest_path") != MANIFEST_PATH.as_posix():
        errors.append(f"manifest_path must be {MANIFEST_PATH.as_posix()}")

    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list):
        return {"ok": False, "version": version, "checked": 0, "errors": errors + ["manifest entries must be a list"]}

    entries: list[tuple[dict[str, Any], Path]] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw_entries):
        label = f"entries[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be an object")
            continue
        try:
            rel = _safe_relative_path(entry.get("path"))
        except ValueError as exc:
            errors.append(f"{label}: {exc}")
            continue
        rel_text = rel.as_posix()
        if rel_text in seen:
            errors.append(f"duplicate managed path: {rel_text}")
            continue
        seen.add(rel_text)
        if entry.get("ownership") not in STRATEGIES:
            errors.append(f"{rel_text}: unknown ownership strategy")
        if entry.get("scope") not in {"shared", "project"}:
            errors.append(f"{rel_text}: scope must be shared or project")
        if entry.get("version") != version:
            errors.append(f"{rel_text}: entry version does not match manifest")
        if not isinstance(entry.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            errors.append(f"{rel_text}: invalid sha256")
        if not isinstance(entry.get("executable"), bool):
            errors.append(f"{rel_text}: executable must be boolean")
        entries.append((entry, rel))

    active_scopes = {"shared"} | ({"project"} if mode == "project" else set())
    checked = 0
    active_paths: set[str] = set()
    for entry, rel in entries:
        if entry.get("scope") not in active_scopes:
            continue
        target = repo / rel
        rel_text = rel.as_posix()
        active_paths.add(rel_text)
        if target.is_symlink():
            errors.append(f"{rel_text}: managed target must not be a symlink")
            continue
        if not target.is_file():
            errors.append(f"{rel_text}: managed file is missing")
            continue
        checked += 1
        try:
            strategy = entry.get("ownership")
            if strategy == "exact":
                material = target.read_bytes()
            elif strategy == "normalized-agent":
                material = normalize_managed_agent(target.read_text(encoding="utf-8")).encode("utf-8")
            elif strategy == "managed-workflow":
                material = managed_workflow_region(target.read_text(encoding="utf-8")).encode("utf-8")
            else:
                continue
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"{rel_text}: cannot normalize managed content: {exc}")
            continue
        if _sha256(material) != entry.get("sha256"):
            errors.append(f"{rel_text}: managed content drift")
        if os.name != "nt":
            actual_executable = bool(stat.S_IMODE(target.stat().st_mode) & 0o111)
            if actual_executable != entry.get("executable"):
                errors.append(f"{rel_text}: executable bit drift")

    namespaces = manifest.get("managed_namespaces")
    if not isinstance(namespaces, list):
        errors.append("managed_namespaces must be a list")
        namespaces = []
    for index, namespace in enumerate(namespaces):
        if not isinstance(namespace, dict) or namespace.get("scope") not in active_scopes:
            continue
        try:
            rel = _safe_relative_path(namespace.get("path"))
        except ValueError as exc:
            errors.append(f"managed_namespaces[{index}]: {exc}")
            continue
        root = repo / rel
        if not root.is_dir():
            errors.append(f"{rel.as_posix()}: managed namespace is missing")
            continue
        expected = {path for path in active_paths if path.startswith(rel.as_posix() + "/")}
        actual = {
            candidate.relative_to(repo).as_posix()
            for candidate in root.rglob("*")
            if (candidate.is_file() or candidate.is_symlink())
            and not _is_generated_noise(candidate.relative_to(root))
        }
        for extra in sorted(actual - expected):
            errors.append(f"{extra}: unexpected file in managed namespace")

    return {"ok": not errors, "version": version, "checked": checked, "errors": errors}


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate")
    generate.add_argument("--skill-root", required=True)
    generate.add_argument("--agents-root", required=True)
    generate.add_argument("--version", required=True)
    generate.add_argument("--output")
    verify = commands.add_parser("verify")
    verify.add_argument("--repo", required=True)
    verify.add_argument("--mode", choices=("project", "global"), default="project")
    verify.add_argument("--expected-version")
    verify.add_argument("--manifest")
    verify.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "generate":
        rendered = render_manifest(build_manifest(Path(args.skill_root), Path(args.agents_root), args.version))
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    result = verify_managed_install(
        Path(args.repo),
        mode=args.mode,
        expected_version=args.expected_version,
        manifest_path=Path(args.manifest) if args.manifest else None,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif result["ok"]:
        print(f"[install-integrity] OK version={result['version']} files={result['checked']}")
    else:
        print("[install-integrity] FAILED", file=sys.stderr)
        for error in result["errors"]:
            print(f"- {error}", file=sys.stderr)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
