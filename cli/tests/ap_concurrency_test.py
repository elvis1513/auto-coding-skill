#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
AP_SCRIPT = REPO_ROOT / "src" / "auto-coding-skill" / "scripts" / "ap.py"
_MISSING = object()
_TEST_OWNER = os.environ.get("CODEX_THREAD_ID") or "concurrency-test-owner"


def command(
    cwd: Path,
    *args: str,
    check: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("CODEX_THREAD_ID", _TEST_OWNER)
    env.setdefault("AUTOCODING_TEST_RUNNER_OVERRIDE", "1")
    result = subprocess.run(
        list(args),
        cwd=cwd,
        check=False,
        text=True,
        input=input_text,
        capture_output=True,
        timeout=30,
        env=env,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(args)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return command(cwd, "git", *args, check=check)


def git_output(cwd: Path, *args: str) -> str:
    return git(cwd, *args).stdout.strip()


def base_config(isolation: str | object = "adaptive") -> dict:
    config = {
        "workflow": {"mode": "dev", "profile": "auto", "completion": "push"},
        "project": {"name": "concurrency-test"},
        "access": {
            "project": {
                "frontend": {"url": "https://project-front.test", "username": "front", "password": "front-pass"},
                "backend": {"url": "https://project-back.test", "username": "back", "password": "back-pass"},
            },
            "jenkins": {
                "frontend": {"url": "https://jenkins-front.test", "username": "front", "password": "front-pass"},
                "backend": {"url": "https://jenkins-back.test", "username": "back", "password": "back-pass"},
            },
            "gitlab": {"url": "https://gitlab.test", "username": "git", "password": "git-pass"},
            "nexus": {
                "frontend": {"url": "https://nexus.test", "username": "nexus", "password": "nexus-pass"},
            },
        },
        "commands": {
            "gate_changed": "true",
            "gate_standard": "true",
            "gate_full": "true",
        },
        "gate": {
            "default_scope": "changed",
            "fallback_scope": "changed",
            "full_on_unknown": False,
            "no_change_scope": "changed",
            "rules": [],
        },
        "risk": {
            "rules": [
                {"name": "test-review", "paths": ["**"], "review": "required"},
            ],
        },
        "structure": {"enabled": False, "enforcement": "advisory"},
        "verification": {
            "target_env_required": False,
            "jenkins_required": False,
        },
        "docs": {
            "taskbook": "docs/tasks/taskbook.md",
            "closure_log": "docs/tasks/closure-log.md",
            "evidence_log": "docs/tasks/evidence.jsonl",
            "design_dir": "docs/design",
            "ledger_check_enabled": False,
        },
    }
    if isolation is not _MISSING:
        config["concurrency"] = {
            "isolation": isolation,
            "base_ref": "origin/dev",
            "target_branch": "dev",
            "branch_prefix": "codex/",
            # Tests replace this with an absolute path outside the primary checkout.
            "worktree_root": "",
            "cleanup_merged": True,
            "delete_remote_branch": True,
        }
    return config


class AutoCodingConcurrencyTests(unittest.TestCase):
    def make_repo(
        self,
        isolation: str | object = "worktree",
        *,
        require_review: bool = True,
    ) -> tuple[Path, Path, Path]:
        temp = tempfile.TemporaryDirectory(prefix="autocoding-concurrency-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        repo = root / "project"
        remote = root / "origin.git"
        worktrees = root / "worktrees"
        repo.mkdir()

        git(root, "init", "--bare", "-q", str(remote))
        git(repo, "init", "-q", "-b", "dev")
        git(repo, "config", "user.email", "test@example.com")
        git(repo, "config", "user.name", "Auto Coding Test")

        config = base_config(isolation)
        if not require_review:
            config["risk"]["rules"] = []
        if "concurrency" in config:
            config["concurrency"]["worktree_root"] = str(worktrees)
        engineering = repo / "docs" / "ENGINEERING.md"
        engineering.parent.mkdir(parents=True)
        engineering.write_text(
            "---\n"
            + yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
            + "---\n# Engineering\n",
            encoding="utf-8",
        )
        tasks = repo / "docs" / "tasks"
        tasks.mkdir(parents=True)
        (tasks / "taskbook.md").write_text("# Taskbook\n", encoding="utf-8")
        (tasks / "closure-log.md").write_text("# Closure Log\n", encoding="utf-8")
        (repo / "shared.txt").write_text("baseline\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "baseline")
        git(repo, "remote", "add", "origin", str(remote))
        git(repo, "push", "-qu", "origin", "dev")
        git(remote, "symbolic-ref", "HEAD", "refs/heads/dev")
        return root, repo, remote

    def ap(
        self,
        repo: Path,
        *args: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return command(
            repo,
            sys.executable,
            str(AP_SCRIPT),
            "--repo",
            str(repo),
            *args,
            check=check,
        )

    def ap_script(
        self,
        repo: Path,
        script: Path,
        *args: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return command(
            repo,
            sys.executable,
            str(script),
            "--repo",
            str(repo),
            *args,
            check=check,
        )

    def managed_runtime(self, root: Path, version: str = "4.3.6") -> Path:
        install_root = root / "managed-runtime"
        skill = install_root / ".agents" / "skills" / "auto-coding-skill"
        shutil.copytree(REPO_ROOT / "src" / "auto-coding-skill", skill)
        script = skill / "scripts" / "ap.py"
        relative = ".agents/skills/auto-coding-skill/scripts/ap.py"
        manifest = {
            "schema_version": 1,
            "skill_version": version,
            "manifest_path": ".agents/managed-install.json",
            "entries": [
                {
                    "path": relative,
                    "source": "skill/scripts/ap.py",
                    "ownership": "exact",
                    "sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
                    "executable": bool(script.stat().st_mode & 0o111),
                    "scope": "shared",
                    "version": version,
                }
            ],
            "managed_namespaces": [],
            "preserved": [],
        }
        manifest_path = install_root / ".agents" / "managed-install.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        return script

    def approve_task(self, repo: Path, task_id: str) -> str:
        issued = json.loads(
            self.ap(
                repo,
                "review-assignment",
                task_id,
                "--reviewer",
                "test-reviewer",
                "--json",
            ).stdout
        )
        fingerprint = issued["assignment"]["diff_fingerprint"]
        self.ap(
            repo,
            "task-review",
            task_id,
            "--verdict",
            "approved",
            "--diff-fingerprint",
            fingerprint,
            "--reviewer",
            "test-reviewer",
        )
        return fingerprint

    def claim_direct(self, repo: Path, *owned_paths: str) -> str:
        args: list[str] = ["classify", "--task-kind", "change", "--claim-direct", "--json"]
        for path in owned_paths:
            args.extend(["--planned-path", path])
        payload = json.loads(self.ap(repo, *args).stdout)
        return payload["direct_claim"]["id"]

    def commit_push(self, repo: Path, task_id: str, message: str) -> subprocess.CompletedProcess[str]:
        self.approve_task(repo, task_id)
        return self.ap(repo, "commit-push", task_id, "--msg", message)

    def artifact_reviewer_runner(
        self,
        root: Path,
        *tokens: str,
        runtime_script: Path = AP_SCRIPT,
    ) -> str:
        fake_reviewer = root / "fake-artifact-reviewer.py"
        fake_reviewer.write_text(
            "import hashlib, json, os, pathlib, subprocess, sys\n"
            "if os.environ.get('CODEX_THREAD_ID'):\n"
            "    raise SystemExit(9)\n"
            "assignment_path = pathlib.Path(os.environ['AUTOCODING_REVIEW_ASSIGNMENT'])\n"
            "assignment_bytes = assignment_path.read_bytes()\n"
            "if hashlib.sha256(assignment_bytes).hexdigest() != os.environ['AUTOCODING_REVIEW_ASSIGNMENT_SHA256']:\n"
            "    raise SystemExit(10)\n"
            "assignment = json.loads(assignment_bytes)\n"
            "artifact_path = pathlib.Path(assignment['diff_artifact_path'])\n"
            "emitted = subprocess.run([sys.executable, sys.argv[1], '--repo', str(pathlib.Path.cwd()), "
            "'review-artifact', '--file', str(assignment_path)], capture_output=True, check=False)\n"
            "if emitted.returncode != 0:\n"
            "    raise SystemExit(11)\n"
            "payload = emitted.stdout\n"
            "actual = hashlib.sha256(payload).hexdigest()\n"
            "if actual != assignment['diff_artifact_sha256']:\n"
            "    raise SystemExit(12)\n"
            "if os.environ.get('AUTOCODING_REVIEW_DIFF_ARTIFACT') != str(artifact_path):\n"
            "    raise SystemExit(13)\n"
            "if os.environ.get('AUTOCODING_REVIEW_DIFF_ARTIFACT_SHA256') != actual:\n"
            "    raise SystemExit(14)\n"
            "if int(os.environ['AUTOCODING_REVIEW_TIMEOUT_SECONDS']) not in (150, 360):\n"
            "    raise SystemExit(15)\n"
            "for token in sys.argv[2:]:\n"
            "    if token.encode('utf-8') not in payload:\n"
            "        raise SystemExit(16)\n"
            "print(json.dumps({'verdict': 'approved', 'summary': 'artifact reviewed', "
            "'evidence': ['diff_artifact_sha256=' + actual]}))\n",
            encoding="utf-8",
        )
        return json.dumps([sys.executable, str(fake_reviewer), str(runtime_script), *tokens])

    def task_worktree(self, repo: Path, task_id: str) -> Path:
        wanted = f"refs/heads/codex/{task_id}"
        current_path: Path | None = None
        for line in git_output(repo, "worktree", "list", "--porcelain").splitlines():
            if line.startswith("worktree "):
                current_path = Path(line.removeprefix("worktree "))
            elif line == f"branch {wanted}" and current_path is not None:
                return current_path
        self.fail(f"no worktree registered for {wanted}")

    def start_task(self, repo: Path, task_id: str, owned_path: str = ".") -> Path:
        result = self.ap(
            repo,
            "task-start",
            task_id,
            "--base",
            "origin/dev",
            "--owned-path",
            owned_path,
            "--isolated",
            "--review-required",
        )
        worktree = self.task_worktree(repo, task_id)
        self.assertIn(task_id, result.stdout + result.stderr)
        self.assertTrue(worktree.is_dir())
        self.assertNotEqual(repo.resolve(), worktree.resolve())
        self.assertNotIn(repo.resolve(), worktree.resolve().parents)
        self.assertEqual(f"codex/{task_id}", git_output(worktree, "branch", "--show-current"))
        return worktree

    def assert_local_branch(self, repo: Path, branch: str, exists: bool) -> None:
        result = git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False)
        self.assertEqual(exists, result.returncode == 0, branch)

    def assert_remote_branch(self, remote: Path, branch: str, exists: bool) -> None:
        result = git(
            remote,
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}",
            check=False,
        )
        self.assertEqual(exists, result.returncode == 0, branch)

    def assert_rejected_without_mutation(
        self,
        repo: Path,
        *args: str,
    ) -> subprocess.CompletedProcess[str]:
        before_head = git_output(repo, "rev-parse", "HEAD")
        before_status = git_output(repo, "status", "--porcelain=v1", "--untracked-files=all")
        result = self.ap(repo, *args, check=False)
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before_head, git_output(repo, "rev-parse", "HEAD"))
        self.assertEqual(
            before_status,
            git_output(repo, "status", "--porcelain=v1", "--untracked-files=all"),
        )
        return result

    def test_task_start_rejects_unknown_full_gate_policy_before_creating_branch(self) -> None:
        _, repo, _ = self.make_repo()
        (repo / "AGENTS.md").write_text(
            "# Workflow\n- High-risk work\n  must run the real full gate before push.\n",
            encoding="utf-8",
        )
        result = self.ap(
            repo,
            "task-start",
            "POLICY-START",
            "--base",
            "origin/dev",
            "--owned-path",
            ".",
            check=False,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("AGENTS.md:2", result.stdout + result.stderr)
        self.assert_local_branch(repo, "codex/POLICY-START", False)

    def test_task_start_rejects_owner_and_writer_that_conflict_with_runtime_identity(self) -> None:
        _, repo, _ = self.make_repo()
        for field in ("owner", "writer"):
            with self.subTest(field=field):
                task_id = f"IDENTITY-{field.upper()}"
                rejected = self.ap(
                    repo,
                    "task-start",
                    task_id,
                    "--base",
                    "origin/dev",
                    "--owned-path",
                    "shared.txt",
                    "--isolated",
                    "--review-required",
                    f"--{field}",
                    "different-runtime-actor",
                    check=False,
                )
                self.assertNotEqual(0, rejected.returncode)
                self.assertIn("does not match CODEX_THREAD_ID", rejected.stdout + rejected.stderr)
                self.assertFalse(self.registry_manifest_path(repo, task_id).exists())
                self.assert_local_branch(repo, f"codex/{task_id}", False)

    def test_task_start_rejects_legacy_gate_yaml_before_creating_branch(self) -> None:
        _, repo, _ = self.make_repo()
        engineering = repo / "docs" / "ENGINEERING.md"
        text = engineering.read_text(encoding="utf-8").replace(
            "  full_on_unknown: false\n",
            "  full_on_unknown: true\n  full_on:\n  - prod_config\n",
        ).replace(
            "  rules: []\n",
            "  rules:\n  - match:\n    - Jenkinsfile\n    scope: full\n    commands:\n    - gate_full\n",
        )
        engineering.write_text(text, encoding="utf-8")
        result = self.ap(
            repo,
            "task-start",
            "POLICY-YAML",
            "--base",
            "origin/dev",
            "--owned-path",
            ".",
            check=False,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("gate.full_on", result.stdout + result.stderr)
        self.assertIn("gate.rules[0].scope", result.stdout + result.stderr)
        self.assert_local_branch(repo, "codex/POLICY-YAML", False)

    def test_commit_push_rejects_policy_added_after_task_start(self) -> None:
        _, repo, _ = self.make_repo()
        worktree = self.start_task(repo, "POLICY-PUSH")
        (worktree / "AGENTS.md").write_text(
            "# Workflow\nRuntime changes require the full gate.\n",
            encoding="utf-8",
        )
        self.approve_task(worktree, "POLICY-PUSH")
        result = self.ap(
            worktree,
            "commit-push",
            "POLICY-PUSH",
            "--msg",
            "POLICY-PUSH: blocked",
            check=False,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("AGENTS.md:2", result.stdout + result.stderr)
        self.assertEqual("", git_output(worktree, "diff", "--cached", "--name-only"))

    def manifest_payloads(self, repo: Path) -> list[dict]:
        common_dir_raw = git_output(repo, "rev-parse", "--git-common-dir")
        common_dir = Path(common_dir_raw)
        if not common_dir.is_absolute():
            common_dir = (repo / common_dir).resolve()
        payloads: list[dict] = []
        for candidate in common_dir.rglob("*.json"):
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                payloads.append(payload)
        return payloads

    def registry_manifest_path(self, repo: Path, task_id: str) -> Path:
        common_dir = Path(git_output(repo, "rev-parse", "--git-common-dir"))
        if not common_dir.is_absolute():
            common_dir = (repo / common_dir).resolve()
        return common_dir / "auto-coding-skill" / "tasks" / f"{task_id}.json"

    def shorten_review_deadline(
        self,
        repo: Path,
        task_id: str,
        issued: dict,
        seconds: int = 2,
    ) -> None:
        deadline = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=seconds)
        assignment = issued["assignment"]
        assignment["deadline_at"] = deadline.isoformat()
        assignment["issued_at"] = (deadline - timedelta(seconds=150)).isoformat()
        assignment_path = Path(issued["assignment_path"])
        assignment_path.write_text(json.dumps(assignment, indent=2) + "\n", encoding="utf-8")
        manifest_path = self.registry_manifest_path(repo, task_id)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["review"]["issued_at"] = assignment["issued_at"]
        manifest["review"]["deadline_at"] = assignment["deadline_at"]
        manifest["review"]["assignment_sha256"] = hashlib.sha256(
            assignment_path.read_bytes()
        ).hexdigest()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    def install_hook(self, repo: Path, name: str, body: str) -> Path:
        common_dir = Path(git_output(repo, "rev-parse", "--git-common-dir"))
        if not common_dir.is_absolute():
            common_dir = (repo / common_dir).resolve()
        hook = common_dir / "hooks" / name
        hook.write_text("#!/bin/sh\nset -eu\n" + body, encoding="utf-8")
        hook.chmod(0o755)
        return hook

    def update_config(self, repo: Path, update) -> None:
        engineering = repo / "docs" / "ENGINEERING.md"
        raw = engineering.read_text(encoding="utf-8")
        _, frontmatter, body = raw.split("---", 2)
        config = yaml.safe_load(frontmatter)
        update(config)
        engineering.write_text(
            "---\n"
            + yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
            + "---"
            + body,
            encoding="utf-8",
        )
        git(repo, "add", "docs/ENGINEERING.md")
        git(repo, "commit", "-qm", "update test workflow config")
        git(repo, "push", "-q", "origin", "dev")

    def test_task_start_creates_external_worktree_manifest_and_status(self) -> None:
        _, repo, _ = self.make_repo()
        worktree = self.start_task(repo, "START-1")

        status = self.ap(repo, "task-status", "START-1")
        rendered_status = status.stdout + status.stderr
        self.assertIn("START-1", rendered_status)
        self.assertIn("codex/START-1", rendered_status)
        self.assertIn(str(worktree), rendered_status)
        status_payload = json.loads(
            self.ap(repo, "task-status", "START-1", "--json").stdout
        )["tasks"][0]
        self.assertFalse(status_payload["has_task_commits"])
        self.assertFalse(status_payload["merged_into_target"])

        serialized_payloads = [json.dumps(item, sort_keys=True) for item in self.manifest_payloads(repo)]
        self.assertTrue(
            any(
                "START-1" in payload
                and "codex/START-1" in payload
                and str(worktree) in payload
                for payload in serialized_payloads
            ),
            "task-start must persist a task manifest in the Git common directory",
        )
        self.assertFalse(
            (worktree / "docs" / "tasks" / "active" / "START-1.md").exists(),
            "4.0 machine state must not create tracked active-task documents",
        )

    def test_clean_serial_task_uses_direct_branch_and_no_diff_is_noop(self) -> None:
        _, repo, remote = self.make_repo("adaptive", require_review=False)
        worktrees_before = git_output(repo, "worktree", "list", "--porcelain")
        unnecessary = self.ap(
            repo,
            "task-start",
            "DIRECT-SKIP",
            "--base",
            "origin/dev",
            "--owned-path",
            "shared.txt",
            check=False,
        )
        self.assertNotEqual(0, unnecessary.returncode)
        self.assertIn("does not need a machine task lifecycle", unnecessary.stdout + unnecessary.stderr)
        self.assertFalse(self.registry_manifest_path(repo, "DIRECT-SKIP").exists())
        start = self.ap(
            repo,
            "task-start",
            "DIRECT-1",
            "--base",
            "origin/dev",
            "--owned-path",
            "shared.txt",
            "--force-lifecycle",
        )
        self.assertIn("execution_mode=direct", start.stdout)
        self.assertEqual(worktrees_before, git_output(repo, "worktree", "list", "--porcelain"))
        self.assert_local_branch(repo, "codex/DIRECT-1", False)
        status = json.loads(self.ap(repo, "task-status", "DIRECT-1", "--json").stdout)["tasks"][0]
        self.assertEqual("direct", status["execution_mode"])
        self.assertFalse(status["has_task_commits"])
        self.assertFalse(status["merged_into_target"])
        self.assertFalse((repo / "docs" / "tasks" / "active" / "DIRECT-1.md").exists())

        (repo / "shared.txt").write_text("direct\n", encoding="utf-8")
        pushed = self.ap(repo, "commit-push", "DIRECT-1", "--msg", "DIRECT-1: update")
        self.assertIn("execution_mode=direct", pushed.stdout)
        self.assertEqual("direct", git_output(remote, "show", "refs/heads/dev:shared.txt"))
        self.assertFalse(self.registry_manifest_path(repo, "DIRECT-1").exists())

        before = git_output(repo, "rev-parse", "HEAD")
        self.ap(repo, "task-start", "DIRECT-NOOP", "--owned-path", "shared.txt", "--force-lifecycle")
        noop = self.ap(repo, "commit-push", "DIRECT-NOOP", "--msg", "DIRECT-NOOP: none")
        self.assertIn("NOOP", noop.stdout)
        self.assertEqual(before, git_output(repo, "rev-parse", "HEAD"))
        self.assertFalse(self.registry_manifest_path(repo, "DIRECT-NOOP").exists())

    def test_commit_push_accepts_already_staged_deletion(self) -> None:
        _, repo, remote = self.make_repo()
        worktree = self.start_task(repo, "STAGED-DELETE", "shared.txt")
        (worktree / "shared.txt").unlink()
        git(worktree, "add", "-A", "--", "shared.txt")
        self.approve_task(worktree, "STAGED-DELETE")

        result = self.ap(
            worktree,
            "commit-push",
            "STAGED-DELETE",
            "--msg",
            "STAGED-DELETE: remove shared file",
        )

        self.assertIn("commit-push", result.stdout)
        self.assertNotEqual(
            0,
            git(
                remote,
                "cat-file",
                "-e",
                "refs/heads/codex/STAGED-DELETE:shared.txt",
                check=False,
            ).returncode,
        )
        self.assertEqual("", git_output(worktree, "status", "--short"))

    def test_staged_rename_requires_ownership_of_both_paths(self) -> None:
        _, repo, remote = self.make_repo()
        worktree = self.start_task(repo, "RENAME-DENY", "renamed.txt")
        git(worktree, "mv", "shared.txt", "renamed.txt")
        status = json.loads(self.ap(worktree, "task-status", "RENAME-DENY", "--json").stdout)
        fingerprint = status["tasks"][0]["current_diff_fingerprint"]

        denied = self.ap(
            worktree,
            "task-review",
            "RENAME-DENY",
            "--verdict",
            "approved",
            "--diff-fingerprint",
            fingerprint,
            "--reviewer",
            "test-reviewer",
            check=False,
        )

        self.assertNotEqual(0, denied.returncode)
        self.assertIn("shared.txt", denied.stdout + denied.stderr)
        self.assert_remote_branch(remote, "codex/RENAME-DENY", False)

        _, allowed_repo, allowed_remote = self.make_repo()
        started = self.ap(
            allowed_repo,
            "task-start",
            "RENAME-ALLOW",
            "--base",
            "origin/dev",
            "--owned-path",
            "shared.txt",
            "--owned-path",
            "renamed.txt",
            "--isolated",
            "--review-required",
        )
        self.assertIn("RENAME-ALLOW", started.stdout)
        allowed_worktree = self.task_worktree(allowed_repo, "RENAME-ALLOW")
        git(allowed_worktree, "mv", "shared.txt", "renamed.txt")
        self.commit_push(allowed_worktree, "RENAME-ALLOW", "RENAME-ALLOW: rename shared file")
        self.assertEqual(
            "baseline",
            git_output(allowed_remote, "show", "refs/heads/codex/RENAME-ALLOW:renamed.txt"),
        )
        self.assertNotEqual(
            0,
            git(
                allowed_remote,
                "cat-file",
                "-e",
                "refs/heads/codex/RENAME-ALLOW:shared.txt",
                check=False,
            ).returncode,
        )

    def test_commit_push_stages_mixed_index_and_worktree_state(self) -> None:
        _, repo, remote = self.make_repo()
        worktree = self.start_task(repo, "MIXED-STAGE")
        (worktree / "shared.txt").write_text("staged-v1\n", encoding="utf-8")
        git(worktree, "add", "shared.txt")
        (worktree / "shared.txt").write_text("worktree-v2\n", encoding="utf-8")
        (worktree / "new-file.txt").write_text("new\n", encoding="utf-8")

        self.commit_push(worktree, "MIXED-STAGE", "MIXED-STAGE: commit final task state")

        ref = "refs/heads/codex/MIXED-STAGE"
        self.assertEqual("worktree-v2", git_output(remote, "show", f"{ref}:shared.txt"))
        self.assertEqual("new", git_output(remote, "show", f"{ref}:new-file.txt"))

    def test_final_gate_receipt_reuses_manual_pass_and_commit_retry(self) -> None:
        root, repo, remote = self.make_repo()
        gate_count = root / "gate-count"
        self.update_config(
            repo,
            lambda config: config["commands"].update(
                {"gate_changed": f"printf x >> {gate_count}"}
            ),
        )
        worktree = self.start_task(repo, "GATE-REUSE", "shared.txt")
        (worktree / "shared.txt").write_text("validated\n", encoding="utf-8")
        self.ap(worktree, "light-gate", "--scope", "changed")
        self.assertEqual("x", gate_count.read_text(encoding="utf-8"))
        self.approve_task(worktree, "GATE-REUSE")
        common_dir = Path(git_output(worktree, "rev-parse", "--git-common-dir"))
        if not common_dir.is_absolute():
            common_dir = (worktree / common_dir).resolve()
        fail_once = common_dir / "precommit-failed-once"
        self.install_hook(
            repo,
            "pre-commit",
            f'if [ ! -f "{fail_once}" ]; then touch "{fail_once}"; exit 1; fi\n',
        )

        first = self.ap(
            worktree,
            "commit-push",
            "GATE-REUSE",
            "--msg",
            "GATE-REUSE: validated change",
            check=False,
        )
        self.assertNotEqual(0, first.returncode)
        self.assertIn("REUSED", first.stdout + first.stderr)
        second = self.ap(
            worktree,
            "commit-push",
            "GATE-REUSE",
            "--msg",
            "GATE-REUSE: validated change",
        )
        self.assertIn("REUSED", second.stdout + second.stderr)
        self.assertEqual("x", gate_count.read_text(encoding="utf-8"))
        self.assertEqual(
            "validated",
            git_output(remote, "show", "refs/heads/codex/GATE-REUSE:shared.txt"),
        )

    def test_final_gate_receipt_invalidates_when_content_changes(self) -> None:
        root, repo, _ = self.make_repo()
        gate_count = root / "gate-count-invalidated"
        self.update_config(
            repo,
            lambda config: config["commands"].update(
                {"gate_changed": f"printf x >> {gate_count}"}
            ),
        )
        worktree = self.start_task(repo, "GATE-INVALIDATE", "shared.txt")
        (worktree / "shared.txt").write_text("first\n", encoding="utf-8")
        self.ap(worktree, "light-gate", "--scope", "changed")
        (worktree / "shared.txt").write_text("second\n", encoding="utf-8")
        self.approve_task(worktree, "GATE-INVALIDATE")

        result = self.ap(
            worktree,
            "commit-push",
            "GATE-INVALIDATE",
            "--msg",
            "GATE-INVALIDATE: use current content",
        )

        self.assertNotIn("REUSED", result.stdout + result.stderr)
        self.assertEqual("xx", gate_count.read_text(encoding="utf-8"))

    def test_task_scope_add_expands_direct_scope_idempotently(self) -> None:
        _, repo, remote = self.make_repo("adaptive", require_review=False)
        self.ap(
            repo,
            "task-start",
            "SCOPE-DIRECT",
            "--owned-path",
            "shared.txt",
            "--force-lifecycle",
        )
        expanded = self.ap(
            repo,
            "task-scope-add",
            "SCOPE-DIRECT",
            "--owned-path",
            "future.txt",
            "--json",
        )
        payload = json.loads(expanded.stdout)
        self.assertEqual("expanded", payload["status"])
        self.assertEqual(2, payload["scope_revision"])
        noop = json.loads(
            self.ap(
                repo,
                "task-scope-add",
                "SCOPE-DIRECT",
                "--owned-path",
                "future.txt",
                "--json",
            ).stdout
        )
        self.assertEqual("noop", noop["status"])
        self.assertEqual(2, noop["scope_revision"])

        (repo / "future.txt").write_text("future\n", encoding="utf-8")
        self.ap(
            repo,
            "commit-push",
            "SCOPE-DIRECT",
            "--msg",
            "SCOPE-DIRECT: add future file",
        )
        self.assertEqual("future", git_output(remote, "show", "refs/heads/dev:future.txt"))

    def test_task_scope_add_invalidates_review_and_blocks_conflicts(self) -> None:
        _, repo, _ = self.make_repo()
        first = self.start_task(repo, "SCOPE-FIRST", "shared.txt")
        self.start_task(repo, "SCOPE-SECOND", "second-owned.txt")
        (first / "shared.txt").write_text("reviewed\n", encoding="utf-8")
        old_fingerprint = self.approve_task(first, "SCOPE-FIRST")

        expanded = json.loads(
            self.ap(
                first,
                "task-scope-add",
                "SCOPE-FIRST",
                "--owned-path",
                "future.txt",
                "--json",
            ).stdout
        )
        self.assertEqual(2, expanded["scope_revision"])
        status = json.loads(self.ap(first, "task-status", "SCOPE-FIRST", "--json").stdout)["tasks"][0]
        self.assertEqual("pending", status["review"]["verdict"])
        self.assertNotEqual(old_fingerprint, status["current_diff_fingerprint"])
        stale = self.ap(
            first,
            "task-review",
            "SCOPE-FIRST",
            "--verdict",
            "approved",
            "--diff-fingerprint",
            old_fingerprint,
            "--reviewer",
            "test-reviewer",
            check=False,
        )
        self.assertNotEqual(0, stale.returncode)

        conflict = self.ap(
            first,
            "task-scope-add",
            "SCOPE-FIRST",
            "--owned-path",
            "second-owned.txt",
            check=False,
        )
        self.assertNotEqual(0, conflict.returncode)
        self.assertIn("SCOPE-SECOND", conflict.stdout + conflict.stderr)

    def test_task_scope_add_escalates_risk_without_moving_worktrees(self) -> None:
        _, repo, _ = self.make_repo("adaptive", require_review=False)
        self.ap(
            repo,
            "task-start",
            "SCOPE-RISK",
            "--owned-path",
            "shared.txt",
            "--force-lifecycle",
        )
        before = git_output(repo, "worktree", "list", "--porcelain")
        expanded = json.loads(
            self.ap(
                repo,
                "task-scope-add",
                "SCOPE-RISK",
                "--owned-path",
                "backend/auth/token.go",
                "--json",
            ).stdout
        )
        self.assertEqual("high-risk", expanded["effective_profile"])
        self.assertTrue(expanded["review_required"])
        self.assertEqual(before, git_output(repo, "worktree", "list", "--porcelain"))

    def test_unnecessary_lifecycle_rejects_before_access_or_fetch_checks(self) -> None:
        _, repo, _ = self.make_repo("adaptive", require_review=False)
        engineering = repo / "docs" / "ENGINEERING.md"
        text = engineering.read_text(encoding="utf-8")
        engineering.write_text(text.replace("front-pass", "CHANGE_ME", 1), encoding="utf-8")
        git(repo, "add", "docs/ENGINEERING.md")
        git(repo, "commit", "-qm", "invalidate access for preflight test")
        git(repo, "push", "-q", "origin", "dev")

        result = self.ap(
            repo,
            "task-start",
            "DIRECT-PREFLIGHT",
            "--base",
            "origin/branch-that-must-not-be-fetched",
            "--owned-path",
            "shared.txt",
            check=False,
        )
        output = result.stdout + result.stderr
        self.assertNotEqual(0, result.returncode)
        self.assertIn("does not need a machine task lifecycle", output)
        self.assertNotIn("initialization is incomplete", output)

    def test_continue_direct_can_adopt_owned_changes_for_new_review_lifecycle(self) -> None:
        root, repo, remote = self.make_repo("adaptive", require_review=False)
        claim = self.claim_direct(repo, "shared.txt")
        (repo / "shared.txt").write_text("continued direct\n", encoding="utf-8")
        started = self.ap(
            repo,
            "task-start",
            "DIRECT-CONTINUE",
            "--owned-path",
            "shared.txt",
            "--continue-direct",
            "--direct-claim",
            claim,
            "--review-required",
        )
        self.assertIn("execution_mode=direct", started.stdout)
        status = json.loads(
            self.ap(repo, "task-status", "DIRECT-CONTINUE", "--json").stdout
        )["tasks"][0]
        self.assertEqual("direct", status["execution_mode"])
        missing_reviewer = self.ap(
            repo,
            "task-review",
            "DIRECT-CONTINUE",
            "--verdict",
            "approved",
            "--diff-fingerprint",
            status["current_diff_fingerprint"],
            check=False,
        )
        self.assertNotEqual(0, missing_reviewer.returncode)
        self.assertIn("explicit --reviewer", missing_reviewer.stdout + missing_reviewer.stderr)
        runner = self.artifact_reviewer_runner(root, "continued direct")
        reviewed = json.loads(
            self.ap(
                repo,
                "review-run",
                "DIRECT-CONTINUE",
                "--reviewer",
                "direct-reviewer",
                "--runner-command-json",
                runner,
                "--json",
            ).stdout
        )
        self.assertEqual("approved", reviewed["verdict"])
        assignment_path = Path(
            json.loads(
                self.registry_manifest_path(repo, "DIRECT-CONTINUE").read_text(encoding="utf-8")
            )["review"]["assignment_path"]
        )
        pushed = self.ap(
            repo,
            "commit-push",
            "DIRECT-CONTINUE",
            "--msg",
            "DIRECT-CONTINUE: update",
        )
        self.assertIn("execution_mode=direct", pushed.stdout)
        self.assertEqual("continued direct", git_output(remote, "show", "refs/heads/dev:shared.txt"))
        self.assertFalse(assignment_path.parent.exists())

        claim = self.claim_direct(repo, "shared.txt")
        (repo / "shared.txt").write_text("owned again\n", encoding="utf-8")
        (repo / "unrelated.txt").write_text("unknown\n", encoding="utf-8")
        rejected = self.ap(
            repo,
            "task-start",
            "DIRECT-CONTINUE-BLOCKED",
            "--owned-path",
            "shared.txt",
            "--continue-direct",
            "--direct-claim",
            claim,
            "--review-required",
            check=False,
        )
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("unrelated.txt", rejected.stdout + rejected.stderr)
        self.assertFalse(self.registry_manifest_path(repo, "DIRECT-CONTINUE-BLOCKED").exists())

    def test_reviewer_cannot_be_current_writer(self) -> None:
        _, repo, _ = self.make_repo()
        self.ap(
            repo,
            "task-start",
            "SELF-REVIEW",
            "--base",
            "origin/dev",
            "--owned-path",
            "src",
            "--isolated",
            "--review-required",
        )
        worktree = self.task_worktree(repo, "SELF-REVIEW")
        payload = worktree / "src" / "payload.txt"
        payload.parent.mkdir(parents=True, exist_ok=True)
        payload.write_text("changed\n", encoding="utf-8")
        self.ap(
            repo,
            "task-handoff",
            "SELF-REVIEW",
            "--from",
            _TEST_OWNER,
            "--to",
            "self-reviewer",
            "--generation",
            "1",
        )
        status = json.loads(
            self.ap(worktree, "task-status", "SELF-REVIEW", "--json").stdout
        )["tasks"][0]
        rejected = self.ap(
            worktree,
            "task-review",
            "SELF-REVIEW",
            "--verdict",
            "approved",
            "--diff-fingerprint",
            status["current_diff_fingerprint"],
            "--reviewer",
            "self-reviewer",
            check=False,
        )
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("writer lease holder", rejected.stdout + rejected.stderr)

    def test_review_assignment_is_deadline_bound_and_idempotent(self) -> None:
        _, repo, _ = self.make_repo()
        worktree = self.start_task(repo, "REVIEW-DEADLINE", "shared.txt")
        (worktree / "shared.txt").write_text("review me\n", encoding="utf-8")

        first = json.loads(
            self.ap(
                worktree,
                "review-assignment",
                "REVIEW-DEADLINE",
                "--reviewer",
                "reviewer-1",
                "--json",
            ).stdout
        )
        second = json.loads(
            self.ap(
                worktree,
                "review-assignment",
                "REVIEW-DEADLINE",
                "--reviewer",
                "reviewer-1",
                "--json",
            ).stdout
        )
        self.assertEqual(first, second)
        assignment = first["assignment"]
        self.assertEqual("focused", assignment["review_depth"])
        self.assertEqual(150, assignment["timeout_seconds"])
        self.assertEqual(1, assignment["scope_revision"])
        self.assertTrue(Path(first["assignment_path"]).is_file())
        assignment_path = Path(first["assignment_path"])
        artifact_path = Path(assignment["diff_artifact_path"])
        artifact = artifact_path.read_bytes()
        self.assertEqual(assignment_path.parent, artifact_path.parent)
        self.assertEqual(0o600, assignment_path.stat().st_mode & 0o777)
        self.assertEqual(0o600, artifact_path.stat().st_mode & 0o777)
        self.assertEqual(hashlib.sha256(artifact).hexdigest(), assignment["diff_artifact_sha256"])
        self.assertEqual("git-binary-patch-v1", assignment["diff_artifact_format"])
        self.assertIn(b"review me", artifact)
        emitted = self.ap(
            worktree,
            "review-artifact",
            "--file",
            str(assignment_path),
        )
        self.assertEqual(artifact, emitted.stdout.encode("utf-8"))
        issued = datetime.fromisoformat(assignment["issued_at"])
        deadline = datetime.fromisoformat(assignment["deadline_at"])
        self.assertEqual(150, int((deadline - issued).total_seconds()))

        artifact_path.write_bytes(artifact + b"tampered\n")
        tampered = self.ap(
            worktree,
            "review-assignment",
            "REVIEW-DEADLINE",
            "--reviewer",
            "reviewer-1",
            check=False,
        )
        self.assertNotEqual(0, tampered.returncode)
        self.assertIn("SHA-256 mismatch", tampered.stdout + tampered.stderr)

    def test_review_assignment_hash_binding_rejects_assignment_file_tampering(self) -> None:
        _, repo, _ = self.make_repo()
        worktree = self.start_task(repo, "REVIEW-ASSIGNMENT-HASH", "shared.txt")
        (worktree / "shared.txt").write_text("hash-bound review\n", encoding="utf-8")
        issued = json.loads(
            self.ap(
                worktree,
                "review-assignment",
                "REVIEW-ASSIGNMENT-HASH",
                "--reviewer",
                "reviewer-hash",
                "--json",
            ).stdout
        )
        assignment_path = Path(issued["assignment_path"])
        original = assignment_path.read_bytes()
        manifest = json.loads(
            self.registry_manifest_path(repo, "REVIEW-ASSIGNMENT-HASH").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            hashlib.sha256(original).hexdigest(),
            manifest["review"]["assignment_sha256"],
        )

        assignment_path.write_bytes(original + b" \n")
        rejected = self.ap(
            worktree,
            "review-assignment",
            "REVIEW-ASSIGNMENT-HASH",
            "--reviewer",
            "reviewer-hash",
            check=False,
        )
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("assignment SHA-256 mismatch", rejected.stdout + rejected.stderr)

    def test_review_assignment_rejects_symlinked_review_root(self) -> None:
        root, repo, _ = self.make_repo()
        worktree = self.start_task(repo, "REVIEW-SYMLINK", "shared.txt")
        (worktree / "shared.txt").write_text("must stay git local\n", encoding="utf-8")
        review_root = self.registry_manifest_path(repo, "REVIEW-SYMLINK").parent.parent / "reviews"
        task_review_dir = review_root / "REVIEW-SYMLINK"
        if task_review_dir.exists():
            task_review_dir.rmdir()
        if review_root.exists():
            review_root.rmdir()
        outside = root / "outside-reviews"
        outside.mkdir()
        review_root.symlink_to(outside, target_is_directory=True)

        rejected = self.ap(
            worktree,
            "review-assignment",
            "REVIEW-SYMLINK",
            "--reviewer",
            "reviewer-symlink",
            check=False,
        )
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("symlinked Git-local review storage", rejected.stdout + rejected.stderr)
        self.assertFalse((outside / "REVIEW-SYMLINK").exists())

    def test_review_snapshot_covers_git_states_without_mutating_main_index_or_objects(self) -> None:
        _, repo, _ = self.make_repo()
        (repo / "delete-me.txt").write_text("delete me\n", encoding="utf-8")
        git(repo, "add", "delete-me.txt")
        git(repo, "commit", "-qm", "add deletion fixture")
        git(repo, "push", "-q", "origin", "dev")
        worktree = self.start_task(repo, "REVIEW-GIT-STATES", ".")
        (worktree / "delete-me.txt").unlink()
        shared = worktree / "shared.txt"
        shared.write_text("executable review\n", encoding="utf-8")
        shared.chmod(shared.stat().st_mode | 0o111)
        (worktree / "binary-review.bin").write_bytes(b"\x00\x01binary-review\xff" * 32)
        (worktree / "review-link").symlink_to("shared.txt")
        index_path = Path(git_output(worktree, "rev-parse", "--git-path", "index"))
        if not index_path.is_absolute():
            index_path = (worktree / index_path).resolve()
        index_before = index_path.read_bytes()
        objects_before = git_output(worktree, "count-objects", "-v")

        issued = json.loads(
            self.ap(
                worktree,
                "review-assignment",
                "REVIEW-GIT-STATES",
                "--reviewer",
                "reviewer-git-states",
                "--json",
            ).stdout
        )
        patch = Path(issued["assignment"]["diff_artifact_path"]).read_bytes()
        self.assertIn(b"deleted file mode 100644", patch)
        self.assertIn(b"old mode 100644", patch)
        self.assertIn(b"new mode 100755", patch)
        self.assertIn(b"new file mode 120000", patch)
        self.assertIn(b"GIT binary patch", patch)
        self.assertEqual(index_before, index_path.read_bytes())
        self.assertEqual(objects_before, git_output(worktree, "count-objects", "-v"))
        self.assertFalse(list(Path(issued["assignment_path"]).parent.glob(".snapshot-*")))

    def test_review_snapshot_stops_and_cleans_when_stream_limit_is_exceeded(self) -> None:
        _, repo, _ = self.make_repo()
        worktree = self.start_task(repo, "REVIEW-SIZE-LIMIT", "shared.txt")
        # The input itself stays below the test limit while the Git patch
        # headers plus body exceed it, exercising the streaming PIPE cutoff.
        (worktree / "shared.txt").write_text("small\n", encoding="utf-8")
        previous = os.environ.get("AUTOCODING_REVIEW_ARTIFACT_MAX_BYTES")
        os.environ["AUTOCODING_REVIEW_ARTIFACT_MAX_BYTES"] = "128"
        try:
            rejected = self.ap(
                worktree,
                "review-assignment",
                "REVIEW-SIZE-LIMIT",
                "--reviewer",
                "reviewer-size",
                check=False,
            )
        finally:
            if previous is None:
                os.environ.pop("AUTOCODING_REVIEW_ARTIFACT_MAX_BYTES", None)
            else:
                os.environ["AUTOCODING_REVIEW_ARTIFACT_MAX_BYTES"] = previous
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("safety limit", rejected.stdout + rejected.stderr)
        review_dir = (
            self.registry_manifest_path(repo, "REVIEW-SIZE-LIMIT").parent.parent
            / "reviews"
            / "REVIEW-SIZE-LIMIT"
        )
        self.assertFalse(list(review_dir.glob(".snapshot-*")))
        self.assertFalse(list(review_dir.glob("*.assignment.json")))
        self.assertFalse(list(review_dir.glob("*.patch")))

    def test_review_snapshot_rejects_oversized_input_before_creating_temp_objects(self) -> None:
        _, repo, _ = self.make_repo()
        worktree = self.start_task(repo, "REVIEW-INPUT-LIMIT", "shared.txt")
        (worktree / "shared.txt").write_text("x" * 4096 + "\n", encoding="utf-8")
        objects_before = git_output(worktree, "count-objects", "-v")
        previous = os.environ.get("AUTOCODING_REVIEW_ARTIFACT_MAX_BYTES")
        os.environ["AUTOCODING_REVIEW_ARTIFACT_MAX_BYTES"] = "128"
        try:
            rejected = self.ap(
                worktree,
                "review-assignment",
                "REVIEW-INPUT-LIMIT",
                "--reviewer",
                "reviewer-input-size",
                check=False,
            )
        finally:
            if previous is None:
                os.environ.pop("AUTOCODING_REVIEW_ARTIFACT_MAX_BYTES", None)
            else:
                os.environ["AUTOCODING_REVIEW_ARTIFACT_MAX_BYTES"] = previous
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("snapshot input exceeds", rejected.stdout + rejected.stderr)
        review_dir = (
            self.registry_manifest_path(repo, "REVIEW-INPUT-LIMIT").parent.parent
            / "reviews"
            / "REVIEW-INPUT-LIMIT"
        )
        self.assertFalse(review_dir.exists())
        self.assertEqual(objects_before, git_output(worktree, "count-objects", "-v"))

    def test_review_run_supervises_separate_process_and_records_result_once(self) -> None:
        root, repo, _ = self.make_repo()
        worktree = self.start_task(repo, "REVIEW-RUN", ".")
        (worktree / "shared.txt").write_text("staged tracked review token\n", encoding="utf-8")
        git(worktree, "add", "shared.txt")
        (worktree / "untracked-review.txt").write_text(
            "untracked review token\n",
            encoding="utf-8",
        )
        runner = self.artifact_reviewer_runner(
            root,
            "staged tracked review token",
            "untracked review token",
        )
        completed = self.ap(
            worktree,
            "review-run",
            "REVIEW-RUN",
            "--reviewer",
            "reviewer-runtime",
            "--runner-command-json",
            runner,
            "--json",
        )
        result = json.loads(completed.stdout)
        self.assertEqual("approved", result["verdict"])
        self.assertEqual("artifact reviewed", result["summary"])

        status = json.loads(
            self.ap(worktree, "task-status", "REVIEW-RUN", "--json").stdout
        )["tasks"][0]
        review = status["review"]
        self.assertEqual("approved", review["verdict"])
        self.assertEqual("completed", review["runtime_state"])
        self.assertEqual("reviewer-runtime", review["reviewer"])
        self.assertEqual(0, review["runtime_exit_code"])
        result_path = Path(review["runtime_result_path"])
        receipt_path = Path(review["runtime_receipt_path"])
        self.assertEqual(0o600, result_path.stat().st_mode & 0o777)
        self.assertEqual(0o600, receipt_path.stat().st_mode & 0o777)
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual("completed", receipt["status"])
        self.assertRegex(receipt["result_sha256"], r"^[0-9a-f]{64}$")

        repeated = self.ap(
            worktree,
            "review-run",
            "REVIEW-RUN",
            "--reviewer",
            "reviewer-runtime",
            "--runner-command-json",
            runner,
            check=False,
        )
        self.assertNotEqual(0, repeated.returncode)
        self.assertIn("already complete", repeated.stdout + repeated.stderr)

        tampered_payload = json.loads(result_path.read_text())
        tampered_payload["summary"] = "tampered after review"
        result_path.write_text(json.dumps(tampered_payload) + "\n", encoding="utf-8")
        tampered = self.ap(
            worktree,
            "task-review",
            "REVIEW-RUN",
            "--verdict",
            "approved",
            "--diff-fingerprint",
            status["current_diff_fingerprint"],
            "--reviewer",
            "reviewer-runtime",
            check=False,
        )
        self.assertNotEqual(0, tampered.returncode)
        self.assertIn("result changed", tampered.stdout + tampered.stderr)

    def test_review_run_retries_clean_exit_without_event_and_rejects_approved_file(self) -> None:
        root, repo, _ = self.make_repo()
        worktree = self.start_task(repo, "REVIEW-NO-EVENT", "shared.txt")
        (worktree / "shared.txt").write_text("review without event\n", encoding="utf-8")
        counter = root / "attempt-count.txt"
        runner_path = root / "no-event-reviewer.py"
        runner_path.write_text(
            "import json, os\n"
            "from pathlib import Path\n"
            f"counter = Path({str(counter)!r})\n"
            "counter.write_text(str(int(counter.read_text() or '0') + 1) if counter.exists() else '1')\n"
            "Path(os.environ['AUTOCODING_REVIEW_RESULT']).write_text(json.dumps({'verdict': 'approved'}) + '\\n')\n",
            encoding="utf-8",
        )
        rejected = self.ap(
            worktree,
            "review-run",
            "REVIEW-NO-EVENT",
            "--reviewer",
            "reviewer-no-event",
            "--runner-command-json",
            json.dumps([sys.executable, str(runner_path)]),
            check=False,
        )
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("runtime-unavailable", rejected.stdout + rejected.stderr)
        self.assertEqual("2", counter.read_text())
        status = json.loads(
            self.ap(worktree, "task-status", "REVIEW-NO-EVENT", "--json").stdout
        )["tasks"][0]
        self.assertEqual("runtime-unavailable", status["review"]["runtime_state"])
        self.assertEqual("blocked", status["review"]["verdict"])

    def test_substantive_result_written_before_timeout_cannot_be_bypassed(self) -> None:
        root, repo, _ = self.make_repo()
        worktree = self.start_task(repo, "REVIEW-SUBSTANTIVE", "shared.txt")
        (worktree / "shared.txt").write_text("substantive finding\n", encoding="utf-8")
        issued = json.loads(
            self.ap(
                worktree,
                "review-assignment",
                "REVIEW-SUBSTANTIVE",
                "--reviewer",
                "reviewer-substantive",
                "--json",
            ).stdout
        )
        self.shorten_review_deadline(repo, "REVIEW-SUBSTANTIVE", issued)
        runner_path = root / "substantive-reviewer.py"
        runner_path.write_text(
            "import json, os, time\n"
            "from pathlib import Path\n"
            "result = Path(os.environ['AUTOCODING_REVIEW_RESULT'])\n"
            "result.write_text(json.dumps({'verdict': 'changes-requested', 'summary': 'real defect'}) + '\\n')\n"
            "result.chmod(0o600)\n"
            "print(json.dumps({'type': 'turn.started'}), flush=True)\n"
            "time.sleep(30)\n",
            encoding="utf-8",
        )
        timed_out = self.ap(
            worktree,
            "review-run",
            "REVIEW-SUBSTANTIVE",
            "--reviewer",
            "reviewer-substantive",
            "--runner-command-json",
            json.dumps([sys.executable, str(runner_path)]),
            check=False,
        )
        self.assertNotEqual(0, timed_out.returncode)
        self.assertIn("cannot be bypassed", timed_out.stdout + timed_out.stderr)
        status = json.loads(
            self.ap(worktree, "task-status", "REVIEW-SUBSTANTIVE", "--json").stdout
        )["tasks"][0]
        review = status["review"]
        self.assertEqual("changes-requested", review["verdict"])
        self.assertEqual("blocked", review["runtime_state"])
        receipt = json.loads(Path(review["runtime_receipt_path"]).read_text())
        self.assertEqual("blocked", receipt["status"])
        self.assertEqual("changes-requested", receipt["verdict"])
        self.assertEqual(1, len(receipt["attempts"]))
        bypass = self.ap(
            worktree,
            "review-runtime-override",
            "REVIEW-SUBSTANTIVE",
            "--diff-fingerprint",
            status["current_diff_fingerprint"],
            "--authorized-by",
            "product-owner",
            "--authorization-ref",
            "conversation-substantive",
            "--reason",
            "A substantive Reviewer result must remain blocking.",
            "--evidence",
            "reviewer returned changes requested",
            "--confirm-runtime-bypass",
            check=False,
        )
        self.assertNotEqual(0, bypass.returncode)
        self.assertIn("allowed only after", bypass.stdout + bypass.stderr)

    def test_substantive_result_survives_nonzero_reviewer_exit(self) -> None:
        root, repo, _ = self.make_repo()
        worktree = self.start_task(repo, "REVIEW-NONZERO", "shared.txt")
        (worktree / "shared.txt").write_text("nonzero substantive finding\n", encoding="utf-8")
        runner_path = root / "nonzero-substantive-reviewer.py"
        runner_path.write_text(
            "import json, os\n"
            "from pathlib import Path\n"
            "result = Path(os.environ['AUTOCODING_REVIEW_RESULT'])\n"
            "result.write_text(json.dumps({'verdict': 'changes-requested', 'summary': 'specific defect'}) + '\\n')\n"
            "result.chmod(0o600)\n"
            "print(json.dumps({'type': 'turn.started'}), flush=True)\n"
            "raise SystemExit(7)\n",
            encoding="utf-8",
        )
        rejected = self.ap(
            worktree,
            "review-run",
            "REVIEW-NONZERO",
            "--reviewer",
            "reviewer-nonzero",
            "--runner-command-json",
            json.dumps([sys.executable, str(runner_path)]),
            check=False,
        )
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("cannot be bypassed", rejected.stdout + rejected.stderr)
        status = json.loads(
            self.ap(worktree, "task-status", "REVIEW-NONZERO", "--json").stdout
        )["tasks"][0]
        review = status["review"]
        self.assertEqual("changes-requested", review["verdict"])
        self.assertEqual("blocked", review["runtime_state"])
        self.assertEqual(7, review["runtime_exit_code"])
        result = json.loads(Path(review["runtime_result_path"]).read_text())
        self.assertEqual("specific defect", result["summary"])
        receipt = json.loads(Path(review["runtime_receipt_path"]).read_text())
        self.assertEqual("blocked", receipt["status"])
        self.assertEqual("changes-requested", receipt["verdict"])
        self.assertEqual(7, receipt["exit_code"])

    def test_substantive_agent_message_before_timeout_cannot_be_bypassed(self) -> None:
        root, repo, _ = self.make_repo()
        worktree = self.start_task(repo, "REVIEW-EVENT-FINDING", "shared.txt")
        (worktree / "shared.txt").write_text("event finding\n", encoding="utf-8")
        issued = json.loads(
            self.ap(
                worktree,
                "review-assignment",
                "REVIEW-EVENT-FINDING",
                "--reviewer",
                "reviewer-event-finding",
                "--json",
            ).stdout
        )
        self.shorten_review_deadline(repo, "REVIEW-EVENT-FINDING", issued)
        runner_path = root / "event-finding-reviewer.py"
        runner_path.write_text(
            "import json, sys, time\n"
            "result = json.dumps({'verdict': 'blocked', 'summary': 'event-only defect'})\n"
            "print(json.dumps({'type': 'turn.started'}), flush=True)\n"
            "sys.stdout.write(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': result}}))\n"
            "sys.stdout.flush()\n"
            "time.sleep(30)\n",
            encoding="utf-8",
        )
        timed_out = self.ap(
            worktree,
            "review-run",
            "REVIEW-EVENT-FINDING",
            "--reviewer",
            "reviewer-event-finding",
            "--runner-command-json",
            json.dumps([sys.executable, str(runner_path)]),
            check=False,
        )
        self.assertNotEqual(0, timed_out.returncode)
        self.assertIn("cannot be bypassed", timed_out.stdout + timed_out.stderr)
        status = json.loads(
            self.ap(worktree, "task-status", "REVIEW-EVENT-FINDING", "--json").stdout
        )["tasks"][0]
        self.assertEqual("blocked", status["review"]["verdict"])
        self.assertEqual("blocked", status["review"]["runtime_state"])
        result = json.loads(Path(status["review"]["runtime_result_path"]).read_text())
        self.assertEqual("event-only defect", result["summary"])

    def test_blocked_runtime_cannot_be_reassigned_or_overwritten_as_approved(self) -> None:
        root, repo, _ = self.make_repo()
        worktree = self.start_task(repo, "REVIEW-BLOCKED", "shared.txt")
        (worktree / "shared.txt").write_text("review is blocked\n", encoding="utf-8")
        blocked_reviewer = root / "blocked-reviewer.py"
        blocked_reviewer.write_text(
            "import json\n"
            "print(json.dumps({'verdict': 'blocked', 'summary': 'missing evidence'}))\n",
            encoding="utf-8",
        )
        runner = json.dumps([sys.executable, str(blocked_reviewer)])
        blocked = self.ap(
            worktree,
            "review-run",
            "REVIEW-BLOCKED",
            "--reviewer",
            "reviewer-blocked",
            "--runner-command-json",
            runner,
            check=False,
        )
        self.assertNotEqual(0, blocked.returncode)
        self.assertIn("Reviewer returned blocked", blocked.stdout + blocked.stderr)
        status = json.loads(
            self.ap(worktree, "task-status", "REVIEW-BLOCKED", "--json").stdout
        )["tasks"][0]
        self.assertEqual("blocked", status["review"]["verdict"])
        self.assertEqual("blocked", status["review"]["runtime_state"])

        reassigned = self.ap(
            worktree,
            "review-assignment",
            "REVIEW-BLOCKED",
            "--reviewer",
            "reviewer-blocked",
            check=False,
        )
        self.assertNotEqual(0, reassigned.returncode)
        self.assertIn("already complete or consumed", reassigned.stdout + reassigned.stderr)
        overwritten = self.ap(
            worktree,
            "task-review",
            "REVIEW-BLOCKED",
            "--verdict",
            "approved",
            "--diff-fingerprint",
            status["current_diff_fingerprint"],
            "--reviewer",
            "reviewer-blocked",
            check=False,
        )
        self.assertNotEqual(0, overwritten.returncode)
        self.assertIn("runtime state=blocked", overwritten.stdout + overwritten.stderr)
        bypass = self.ap(
            worktree,
            "review-runtime-override",
            "REVIEW-BLOCKED",
            "--diff-fingerprint",
            status["current_diff_fingerprint"],
            "--authorized-by",
            "product-owner",
            "--authorization-ref",
            "conversation-blocked",
            "--reason",
            "User cannot override a substantive Reviewer blocked verdict.",
            "--evidence",
            "reviewer returned blocked",
            "--confirm-runtime-bypass",
            check=False,
        )
        self.assertNotEqual(0, bypass.returncode)
        self.assertIn("allowed only after", bypass.stdout + bypass.stderr)

    def test_known_432_artifact_access_block_gets_one_immutable_managed_retry(self) -> None:
        root, repo, _ = self.make_repo()
        managed_script = self.managed_runtime(root)
        worktree = self.start_task(repo, "REVIEW-MANAGED-RETRY", "shared.txt")
        (worktree / "shared.txt").write_text("managed retry payload\n", encoding="utf-8")
        common_dir = Path(git_output(repo, "rev-parse", "--git-common-dir"))
        if not common_dir.is_absolute():
            common_dir = (repo / common_dir).resolve()
        state_root = common_dir / "auto-coding-skill"
        blocked_reviewer = root / "known-artifact-access-block.py"
        blocked_reviewer.write_text(
            "import json\n"
            f"state_root = {str(state_root)!r}\n"
            "print(json.dumps({"
            "'verdict': 'blocked', "
            "'summary': 'Review could not begin because review-artifact failed before emitting the immutable patch.', "
            "'evidence': ['review-artifact exited 2: Cannot protect Git-local review storage at ' + state_root + ': Operation not permitted.'], "
            "'risks': ['The immutable patch was not emitted or substantively reviewed.']}))\n",
            encoding="utf-8",
        )
        blocked = self.ap(
            worktree,
            "review-run",
            "REVIEW-MANAGED-RETRY",
            "--reviewer",
            "managed-retry-reviewer",
            "--runner-command-json",
            json.dumps([sys.executable, str(blocked_reviewer)]),
            check=False,
        )
        self.assertNotEqual(0, blocked.returncode)
        manifest_path = self.registry_manifest_path(repo, "REVIEW-MANAGED-RETRY")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["skill_version"] = "4.3.2"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        prior_review = manifest["review"]
        prior_paths = [
            Path(prior_review["assignment_path"]),
            Path(prior_review["diff_artifact_path"]),
            Path(prior_review["runtime_result_path"]),
            Path(prior_review["runtime_receipt_path"]),
            Path(prior_review["runtime_event_log_path"]),
        ]
        prior_bytes = {path: path.read_bytes() for path in prior_paths}
        fingerprint = prior_review["diff_fingerprint"]

        authorized = json.loads(
            self.ap_script(
                worktree,
                managed_script,
                "review-runtime-retry",
                "REVIEW-MANAGED-RETRY",
                "--diff-fingerprint",
                fingerprint,
                "--reason-code",
                "managed-review-artifact-access",
                "--confirm-managed-runtime-retry",
                "--json",
            ).stdout
        )
        self.assertEqual("retry-authorized", authorized["status"])
        self.assertEqual("retry-v4.3.6", authorized["retry_token"])
        audit_path = Path(authorized["audit_path"])
        self.assertEqual(0o600, audit_path.stat().st_mode & 0o777)
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        self.assertEqual("4.3.2", audit["task_skill_version"])
        self.assertEqual(hashlib.sha256(prior_bytes[prior_paths[2]]).hexdigest(), audit["prior_result_sha256"])

        runner = self.artifact_reviewer_runner(
            root,
            "managed retry payload",
            runtime_script=managed_script,
        )
        reviewed = json.loads(
            self.ap_script(
                worktree,
                managed_script,
                "review-run",
                "REVIEW-MANAGED-RETRY",
                "--reviewer",
                "managed-retry-reviewer",
                "--runner-command-json",
                runner,
                "--json",
            ).stdout
        )
        self.assertEqual("approved", reviewed["verdict"])
        for path, original in prior_bytes.items():
            self.assertEqual(original, path.read_bytes(), str(path))
        status = json.loads(
            self.ap_script(
                worktree,
                managed_script,
                "task-status",
                "REVIEW-MANAGED-RETRY",
                "--json",
            ).stdout
        )["tasks"][0]
        retry_review = status["review"]
        self.assertEqual("approved", retry_review["verdict"])
        self.assertIn(".retry-v4.3.6.result.json", retry_review["runtime_result_path"])
        retry_receipt = json.loads(Path(retry_review["runtime_receipt_path"]).read_text())
        self.assertEqual("retry-v4.3.6", retry_receipt["runtime_retry_token"])
        self.assertEqual(authorized["audit_sha256"], retry_receipt["runtime_retry_audit_sha256"])

        repeated = self.ap_script(
            worktree,
            managed_script,
            "review-runtime-retry",
            "REVIEW-MANAGED-RETRY",
            "--diff-fingerprint",
            fingerprint,
            "--reason-code",
            "managed-review-artifact-access",
            "--confirm-managed-runtime-retry",
            check=False,
        )
        self.assertNotEqual(0, repeated.returncode)

    def test_434_retry_artifact_access_block_gets_one_fixed_runtime_repair(self) -> None:
        root, repo, _ = self.make_repo()
        managed_434 = self.managed_runtime(root / "runtime-434", "4.3.4")
        managed_fixed = self.managed_runtime(root / "runtime-fixed", "4.3.6")
        worktree = self.start_task(repo, "REVIEW-RETRY-REPAIR", "shared.txt")
        (worktree / "shared.txt").write_text("repair retry payload\n", encoding="utf-8")
        common_dir = Path(git_output(repo, "rev-parse", "--git-common-dir"))
        if not common_dir.is_absolute():
            common_dir = (repo / common_dir).resolve()
        state_root = common_dir / "auto-coding-skill"
        blocked_reviewer = root / "repair-artifact-access-block.py"
        blocked_reviewer.write_text(
            "import json\n"
            f"state_root = {str(state_root)!r}\n"
            "print(json.dumps({"
            "'verdict': 'blocked', "
            "'summary': 'Review could not begin because review-artifact failed to verify and emit the immutable patch.', "
            "'evidence': ['review-artifact exited with: Cannot protect Git-local review storage: ' + state_root + ': [Errno 1] Operation not permitted'], "
            "'risks': ['The SHA-256-bound frozen diff was not emitted or reviewed, so no substantive correctness or security conclusion is available.']}))\n",
            encoding="utf-8",
        )
        blocked_runner = json.dumps([sys.executable, str(blocked_reviewer)])
        self.ap(
            worktree,
            "review-run",
            "REVIEW-RETRY-REPAIR",
            "--reviewer",
            "repair-reviewer",
            "--runner-command-json",
            blocked_runner,
            check=False,
        )
        manifest_path = self.registry_manifest_path(repo, "REVIEW-RETRY-REPAIR")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["skill_version"] = "4.3.2"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        fingerprint = manifest["review"]["diff_fingerprint"]
        first_retry = json.loads(
            self.ap_script(
                worktree,
                managed_434,
                "review-runtime-retry",
                "REVIEW-RETRY-REPAIR",
                "--diff-fingerprint",
                fingerprint,
                "--reason-code",
                "managed-review-artifact-access",
                "--confirm-managed-runtime-retry",
                "--json",
            ).stdout
        )
        self.assertEqual("retry-v4.3.4", first_retry["retry_token"])
        self.ap_script(
            worktree,
            managed_434,
            "review-run",
            "REVIEW-RETRY-REPAIR",
            "--reviewer",
            "repair-reviewer",
            "--runner-command-json",
            blocked_runner,
            check=False,
        )
        blocked_status = json.loads(
            self.ap_script(
                worktree,
                managed_434,
                "task-status",
                "REVIEW-RETRY-REPAIR",
                "--json",
            ).stdout
        )["tasks"][0]
        old_review = blocked_status["review"]
        old_evidence_paths = [
            Path(old_review["runtime_retry_audit_path"]),
            Path(old_review["runtime_result_path"]),
            Path(old_review["runtime_receipt_path"]),
            Path(old_review["runtime_event_log_path"]),
        ]
        old_evidence = {path: path.read_bytes() for path in old_evidence_paths}

        repaired = json.loads(
            self.ap_script(
                worktree,
                managed_fixed,
                "review-runtime-retry",
                "REVIEW-RETRY-REPAIR",
                "--diff-fingerprint",
                fingerprint,
                "--reason-code",
                "managed-review-artifact-access",
                "--confirm-managed-runtime-retry",
                "--json",
            ).stdout
        )
        self.assertEqual("retry-v4.3.6", repaired["retry_token"])
        repair_audit = json.loads(Path(repaired["audit_path"]).read_text(encoding="utf-8"))
        self.assertEqual("retry-v4.3.4", repair_audit["superseded_retry_token"])
        self.assertEqual("blocked", repair_audit["superseded_retry_state"])
        reviewed = json.loads(
            self.ap_script(
                worktree,
                managed_fixed,
                "review-run",
                "REVIEW-RETRY-REPAIR",
                "--reviewer",
                "repair-reviewer",
                "--runner-command-json",
                self.artifact_reviewer_runner(
                    root,
                    "repair retry payload",
                    runtime_script=managed_fixed,
                ),
                "--json",
            ).stdout
        )
        self.assertEqual("approved", reviewed["verdict"])
        for path, original in old_evidence.items():
            self.assertEqual(original, path.read_bytes(), str(path))

    def test_managed_retry_rejects_a_substantive_blocked_result(self) -> None:
        root, repo, _ = self.make_repo()
        managed_script = self.managed_runtime(root)
        worktree = self.start_task(repo, "REVIEW-RETRY-FINDING", "shared.txt")
        (worktree / "shared.txt").write_text("substantive retry rejection\n", encoding="utf-8")
        reviewer = root / "substantive-block.py"
        reviewer.write_text(
            "import json\n"
            "print(json.dumps({'verdict': 'blocked', 'summary': 'real correctness defect', "
            "'findings': ['P1: incorrect authorization check'], "
            "'risks': ['Production authorization can be bypassed.']}))\n",
            encoding="utf-8",
        )
        self.ap(
            worktree,
            "review-run",
            "REVIEW-RETRY-FINDING",
            "--reviewer",
            "finding-reviewer",
            "--runner-command-json",
            json.dumps([sys.executable, str(reviewer)]),
            check=False,
        )
        manifest_path = self.registry_manifest_path(repo, "REVIEW-RETRY-FINDING")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["skill_version"] = "4.3.2"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        rejected = self.ap_script(
            worktree,
            managed_script,
            "review-runtime-retry",
            "REVIEW-RETRY-FINDING",
            "--diff-fingerprint",
            manifest["review"]["diff_fingerprint"],
            "--reason-code",
            "managed-review-artifact-access",
            "--confirm-managed-runtime-retry",
            check=False,
        )
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("not the exact non-substantive", rejected.stdout + rejected.stderr)

    def test_review_run_retries_runtime_unavailable_and_allows_bound_user_override(self) -> None:
        root, repo, _ = self.make_repo()
        worktree = self.start_task(repo, "REVIEW-TIMEOUT", "shared.txt")
        (worktree / "shared.txt").write_text("review me slowly\n", encoding="utf-8")
        issued = json.loads(
            self.ap(
                worktree,
                "review-assignment",
                "REVIEW-TIMEOUT",
                "--reviewer",
                "reviewer-timeout",
                "--json",
            ).stdout
        )
        self.shorten_review_deadline(repo, "REVIEW-TIMEOUT", issued, seconds=5)

        slow_reviewer = root / "slow-reviewer.py"
        slow_reviewer.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        started = time.monotonic()
        previous_startup_timeout = os.environ.get("AUTOCODING_REVIEW_STARTUP_TIMEOUT_SECONDS")
        os.environ["AUTOCODING_REVIEW_STARTUP_TIMEOUT_SECONDS"] = "0.1"
        try:
            timed_out = self.ap(
                worktree,
                "review-run",
                "REVIEW-TIMEOUT",
                "--reviewer",
                "reviewer-timeout",
                "--runner-command-json",
                json.dumps([sys.executable, str(slow_reviewer)]),
                check=False,
            )
        finally:
            if previous_startup_timeout is None:
                os.environ.pop("AUTOCODING_REVIEW_STARTUP_TIMEOUT_SECONDS", None)
            else:
                os.environ["AUTOCODING_REVIEW_STARTUP_TIMEOUT_SECONDS"] = previous_startup_timeout
        elapsed = time.monotonic() - started
        self.assertNotEqual(0, timed_out.returncode)
        self.assertLess(elapsed, 6.0)
        self.assertIn("runtime-unavailable", timed_out.stdout + timed_out.stderr)
        status = json.loads(
            self.ap(worktree, "task-status", "REVIEW-TIMEOUT", "--json").stdout
        )["tasks"][0]
        self.assertEqual("blocked", status["review"]["verdict"])
        self.assertEqual("runtime-unavailable", status["review"]["runtime_state"])
        receipt = json.loads(Path(status["review"]["runtime_receipt_path"]).read_text())
        self.assertEqual(2, receipt["schema"])
        self.assertEqual("runtime-unavailable", receipt["status"])
        self.assertEqual(2, len(receipt["attempts"]))
        self.assertRegex(receipt["event_log_sha256"], r"^[0-9a-f]{64}$")

        receipt_path = Path(status["review"]["runtime_receipt_path"])
        original_receipt = receipt_path.read_bytes()
        tampered_receipt = json.loads(original_receipt)
        tampered_receipt["failure_kind"] = "tampered-before-override"
        receipt_path.write_text(json.dumps(tampered_receipt) + "\n", encoding="utf-8")
        rejected_receipt = self.ap(
            worktree,
            "review-runtime-override",
            "REVIEW-TIMEOUT",
            "--diff-fingerprint",
            status["current_diff_fingerprint"],
            "--authorized-by",
            "product-owner",
            "--authorization-ref",
            "conversation-pre-tamper",
            "--reason",
            "Tampered pre-override evidence must be rejected.",
            "--evidence",
            "targeted tests passed",
            "--confirm-runtime-bypass",
            check=False,
        )
        self.assertNotEqual(0, rejected_receipt.returncode)
        self.assertIn("changed after failure finalization", rejected_receipt.stdout + rejected_receipt.stderr)
        receipt_path.write_bytes(original_receipt)

        event_log_path = Path(status["review"]["runtime_event_log_path"])
        original_event_log = event_log_path.read_bytes()
        event_log_path.write_bytes(original_event_log + b'{"event_type":"tampered"}\n')
        rejected_event = self.ap(
            worktree,
            "review-runtime-override",
            "REVIEW-TIMEOUT",
            "--diff-fingerprint",
            status["current_diff_fingerprint"],
            "--authorized-by",
            "product-owner",
            "--authorization-ref",
            "conversation-event-tamper",
            "--reason",
            "Tampered event evidence must be rejected before override.",
            "--evidence",
            "targeted tests passed",
            "--confirm-runtime-bypass",
            check=False,
        )
        self.assertNotEqual(0, rejected_event.returncode)
        self.assertIn("event log changed", rejected_event.stdout + rejected_event.stderr)
        event_log_path.write_bytes(original_event_log)

        override = json.loads(
            self.ap(
                worktree,
                "review-runtime-override",
                "REVIEW-TIMEOUT",
                "--diff-fingerprint",
                status["current_diff_fingerprint"],
                "--authorized-by",
                "product-owner",
                "--authorization-ref",
                "conversation-2026-07-17",
                "--reason",
                "User accepted the exhausted Reviewer runtime failure.",
                "--evidence",
                "targeted tests passed",
                "--confirm-runtime-bypass",
                "--json",
            ).stdout
        )
        self.assertEqual("runtime-bypassed", override["verdict"])
        bypassed_status = json.loads(
            self.ap(worktree, "task-status", "REVIEW-TIMEOUT", "--json").stdout
        )["tasks"][0]
        self.assertEqual("runtime-bypassed", bypassed_status["review"]["verdict"])
        self.assertEqual("runtime-bypassed", bypassed_status["review"]["runtime_state"])

        receipt_path = Path(bypassed_status["review"]["runtime_receipt_path"])
        original_receipt = receipt_path.read_bytes()
        tampered_receipt = json.loads(original_receipt)
        tampered_receipt["failure_kind"] = "tampered"
        receipt_path.write_text(json.dumps(tampered_receipt) + "\n", encoding="utf-8")
        rejected_tamper = self.ap(
            worktree,
            "commit-push",
            "REVIEW-TIMEOUT",
            "--msg",
            "test: reject tampered runtime bypass",
            check=False,
        )
        self.assertNotEqual(0, rejected_tamper.returncode)
        self.assertIn("receipt SHA-256", rejected_tamper.stdout + rejected_tamper.stderr)
        receipt_path.write_bytes(original_receipt)

        pushed = self.ap(
            worktree,
            "commit-push",
            "REVIEW-TIMEOUT",
            "--msg",
            "test: allow bound runtime bypass",
        )
        self.assertIn("commit-push", pushed.stdout + pushed.stderr)

    def test_task_review_requires_assignment_and_exact_head(self) -> None:
        _, repo, _ = self.make_repo()
        worktree = self.start_task(repo, "REVIEW-HEAD", "shared.txt")
        (worktree / "shared.txt").write_text("review me\n", encoding="utf-8")
        status = json.loads(
            self.ap(worktree, "task-status", "REVIEW-HEAD", "--json").stdout
        )["tasks"][0]
        missing = self.ap(
            worktree,
            "task-review",
            "REVIEW-HEAD",
            "--verdict",
            "approved",
            "--diff-fingerprint",
            status["current_diff_fingerprint"],
            "--reviewer",
            "reviewer-1",
            check=False,
        )
        self.assertNotEqual(0, missing.returncode)
        self.assertIn("must use review-assignment", missing.stdout + missing.stderr)

        issued = json.loads(
            self.ap(
                worktree,
                "review-assignment",
                "REVIEW-HEAD",
                "--reviewer",
                "reviewer-1",
                "--json",
            ).stdout
        )["assignment"]
        git(worktree, "add", "shared.txt")
        git(worktree, "commit", "-qm", "manual task commit")
        stale = self.ap(
            worktree,
            "task-review",
            "REVIEW-HEAD",
            "--verdict",
            "approved",
            "--diff-fingerprint",
            issued["diff_fingerprint"],
            "--reviewer",
            "reviewer-1",
            check=False,
        )
        self.assertNotEqual(0, stale.returncode)
        self.assertIn("HEAD is stale", stale.stdout + stale.stderr)

    def test_expired_review_assignment_cannot_be_renewed_or_approved(self) -> None:
        _, repo, _ = self.make_repo()
        worktree = self.start_task(repo, "REVIEW-EXPIRED", "shared.txt")
        (worktree / "shared.txt").write_text("review me\n", encoding="utf-8")
        issued = json.loads(
            self.ap(
                worktree,
                "review-assignment",
                "REVIEW-EXPIRED",
                "--reviewer",
                "reviewer-1",
                "--json",
            ).stdout
        )
        assignment_path = Path(issued["assignment_path"])
        assignment = issued["assignment"]
        past_deadline = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=1)
        assignment["deadline_at"] = past_deadline.isoformat()
        assignment["issued_at"] = (past_deadline - timedelta(seconds=150)).isoformat()
        assignment_path.write_text(json.dumps(assignment, indent=2) + "\n", encoding="utf-8")

        manifest_path = self.registry_manifest_path(repo, "REVIEW-EXPIRED")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["review"]["issued_at"] = assignment["issued_at"]
        manifest["review"]["deadline_at"] = assignment["deadline_at"]
        manifest["review"]["assignment_sha256"] = hashlib.sha256(
            assignment_path.read_bytes()
        ).hexdigest()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        renewed = self.ap(
            worktree,
            "review-assignment",
            "REVIEW-EXPIRED",
            "--reviewer",
            "reviewer-1",
            check=False,
        )
        self.assertNotEqual(0, renewed.returncode)
        self.assertIn("timed out", renewed.stdout + renewed.stderr)
        approved = self.ap(
            worktree,
            "task-review",
            "REVIEW-EXPIRED",
            "--verdict",
            "approved",
            "--diff-fingerprint",
            assignment["diff_fingerprint"],
            "--reviewer",
            "reviewer-1",
            check=False,
        )
        self.assertNotEqual(0, approved.returncode)
        self.assertIn("deadline expired", approved.stdout + approved.stderr)

    def test_schema_one_task_status_fails_closed_with_migration_recovery(self) -> None:
        _, repo, _ = self.make_repo()
        self.start_task(repo, "LEGACY-SCHEMA")
        registry = self.registry_manifest_path(repo, "LEGACY-SCHEMA")
        payload = json.loads(registry.read_text(encoding="utf-8"))
        payload["schema"] = 1
        for field in [
            "owned_paths",
            "depends_on",
            "prerequisite_shas",
            "writer_lease",
            "review",
        ]:
            payload.pop(field, None)
        registry.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        result = self.ap(repo, "task-status", "LEGACY-SCHEMA", check=False)
        rendered = result.stdout + result.stderr
        self.assertNotEqual(0, result.returncode)
        self.assertIn("legacy schema-1 task", rendered)
        self.assertIn("cannot safely infer or claim owned_paths", rendered)
        self.assertIn("previously installed runtime", rendered)
        self.assertIn("restore the 3.0.0 runtime", rendered)

    def test_owned_paths_are_required_and_unowned_changes_are_rejected(self) -> None:
        _, repo, remote = self.make_repo()
        missing = self.ap(
            repo,
            "task-start",
            "NO-OWNED",
            "--base",
            "origin/dev",
            check=False,
        )
        self.assertNotEqual(0, missing.returncode)
        self.assertIn("owned-path", (missing.stdout + missing.stderr).lower())
        self.assert_remote_branch(remote, "codex/NO-OWNED", False)

        self.ap(
            repo,
            "task-start",
            "OWNED-ONLY",
            "--base",
            "origin/dev",
            "--owned-path",
            "src/owned",
        )
        worktree = self.task_worktree(repo, "OWNED-ONLY")
        outside = worktree / "src" / "outside.txt"
        outside.parent.mkdir(parents=True)
        outside.write_text("outside\n", encoding="utf-8")
        status = self.ap(worktree, "task-status", "OWNED-ONLY", "--json")
        fingerprint = json.loads(status.stdout)["tasks"][0]["current_diff_fingerprint"]
        review = self.ap(
            worktree,
            "task-review",
            "OWNED-ONLY",
            "--verdict",
            "approved",
            "--diff-fingerprint",
            fingerprint,
            check=False,
        )
        self.assertNotEqual(0, review.returncode)
        self.assertIn("outside task owned_paths", review.stdout + review.stderr)

    def test_approved_fingerprint_expires_when_owned_diff_changes(self) -> None:
        _, repo, remote = self.make_repo()
        worktree = self.start_task(repo, "STALE-REVIEW")
        payload = worktree / "payload.txt"
        payload.write_text("reviewed\n", encoding="utf-8")
        registry = self.registry_manifest_path(repo, "STALE-REVIEW")
        manifest = json.loads(registry.read_text(encoding="utf-8"))
        owner = manifest["owner"]
        manifest["owner"] = "another-lifecycle-owner"
        registry.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        status = self.ap(worktree, "task-status", "STALE-REVIEW", "--json")
        fingerprint = json.loads(status.stdout)["tasks"][0]["current_diff_fingerprint"]
        non_owner_review = self.ap(
            worktree,
            "task-review",
            "STALE-REVIEW",
            "--verdict",
            "approved",
            "--diff-fingerprint",
            fingerprint,
            check=False,
        )
        self.assertNotEqual(0, non_owner_review.returncode)
        self.assertIn("lifecycle owner", non_owner_review.stdout + non_owner_review.stderr)
        manifest["owner"] = owner
        registry.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.approve_task(worktree, "STALE-REVIEW")
        payload.write_text("changed after review\n", encoding="utf-8")

        result = self.ap(
            worktree,
            "commit-push",
            "STALE-REVIEW",
            "--msg",
            "STALE-REVIEW: must fail",
            check=False,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("fingerprint is stale", result.stdout + result.stderr)
        self.assert_remote_branch(remote, "codex/STALE-REVIEW", False)

    def test_writer_lease_requires_match_and_owner_handoff_uses_generation_cas(self) -> None:
        _, repo, _ = self.make_repo()
        owner = _TEST_OWNER
        self.ap(
            repo,
            "task-start",
            "LEASE-1",
            "--base",
            "origin/dev",
            "--owned-path",
            ".",
        )
        worktree = self.task_worktree(repo, "LEASE-1")
        (worktree / "lease.txt").write_text("ready\n", encoding="utf-8")
        self.approve_task(worktree, "LEASE-1")

        self.ap(
            repo,
            "task-handoff",
            "LEASE-1",
            "--from",
            owner,
            "--to",
            "fixer-label",
            "--generation",
            "1",
        )

        mismatch = self.ap(
            worktree,
            "commit-push",
            "LEASE-1",
            "--msg",
            "LEASE-1: wrong writer",
            check=False,
        )
        self.assertNotEqual(0, mismatch.returncode)
        self.assertIn("writer lease mismatch", (mismatch.stdout + mismatch.stderr).lower())

        spoofed = self.ap(
            worktree,
            "commit-push",
            "LEASE-1",
            "--msg",
            "LEASE-1: spoofed writer",
            "--writer",
            "fixer-label",
            check=False,
        )
        self.assertNotEqual(0, spoofed.returncode)
        self.assertIn("actor identity cannot be overridden", spoofed.stdout + spoofed.stderr)

        self.ap(
            repo,
            "task-handoff",
            "LEASE-1",
            "--from",
            "fixer-label",
            "--to",
            owner,
            "--generation",
            "2",
        )
        stale = self.ap(
            repo,
            "task-handoff",
            "LEASE-1",
            "--from",
            owner,
            "--to",
            "next-writer",
            "--generation",
            "2",
            check=False,
        )
        self.assertNotEqual(0, stale.returncode)
        self.assertIn("generation changed", stale.stdout + stale.stderr)
        manifest = json.loads(self.registry_manifest_path(repo, "LEASE-1").read_text(encoding="utf-8"))
        self.assertEqual(owner, manifest["writer_lease"]["holder"])
        self.assertEqual(3, manifest["writer_lease"]["generation"])

    def test_dependency_sha_must_already_be_in_task_base(self) -> None:
        _, repo, _ = self.make_repo()
        tree = git_output(repo, "rev-parse", "HEAD^{tree}")
        orphan = git_output(repo, "commit-tree", tree, "-m", "unintegrated prerequisite")
        result = self.ap(
            repo,
            "task-start",
            "DEPENDENT-1",
            "--base",
            "origin/dev",
            "--owned-path",
            ".",
            "--depends-on",
            f"UPSTREAM-1={orphan}",
            check=False,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("not integrated", result.stdout + result.stderr)

    def test_target_advance_rebases_then_requires_review_before_integration(self) -> None:
        _, repo, remote = self.make_repo()
        worktree = self.start_task(repo, "REBASE-REVIEW")
        (worktree / "task.txt").write_text("task\n", encoding="utf-8")
        self.commit_push(worktree, "REBASE-REVIEW", "REBASE-REVIEW: ready")

        (repo / "upstream.txt").write_text("upstream\n", encoding="utf-8")
        git(repo, "add", "upstream.txt")
        git(repo, "commit", "-qm", "advance target")
        git(repo, "push", "-q", "origin", "dev")

        rebased = self.ap(repo, "task-integrate", "REBASE-REVIEW", check=False)
        self.assertNotEqual(0, rebased.returncode)
        self.assertIn("review again", rebased.stdout + rebased.stderr)
        manifest = json.loads(self.registry_manifest_path(repo, "REBASE-REVIEW").read_text(encoding="utf-8"))
        self.assertEqual("pushed", manifest["state"])
        self.assertEqual("pending", manifest["review"]["verdict"])
        self.assertNotEqual(
            0,
            git(remote, "cat-file", "-e", "refs/heads/dev:task.txt", check=False).returncode,
        )

        self.approve_task(worktree, "REBASE-REVIEW")
        self.ap(repo, "task-integrate", "REBASE-REVIEW")
        self.assertEqual("task", git_output(remote, "show", "refs/heads/dev:task.txt"))

    def test_rebase_conflict_can_resume_only_then_requires_fresh_review(self) -> None:
        _, repo, remote = self.make_repo()
        worktree = self.start_task(repo, "RESUME-1")
        (worktree / "shared.txt").write_text("task side\n", encoding="utf-8")
        self.commit_push(worktree, "RESUME-1", "RESUME-1: ready")

        (repo / "shared.txt").write_text("target side\n", encoding="utf-8")
        git(repo, "add", "shared.txt")
        git(repo, "commit", "-qm", "conflicting target change")
        git(repo, "push", "-q", "origin", "dev")

        conflict = self.ap(repo, "task-integrate", "RESUME-1", check=False)
        self.assertNotEqual(0, conflict.returncode)
        self.assertIn("rebase conflicted", conflict.stdout + conflict.stderr)
        manifest = json.loads(self.registry_manifest_path(repo, "RESUME-1").read_text(encoding="utf-8"))
        self.assertEqual("conflicted", manifest["state"])
        self.assertEqual("pending", manifest["review"]["verdict"])

        (worktree / "shared.txt").write_text("resolved\n", encoding="utf-8")
        git(worktree, "add", "shared.txt")
        git(worktree, "-c", "core.editor=true", "rebase", "--continue")
        self.ap(repo, "task-resume", "RESUME-1")
        manifest = json.loads(self.registry_manifest_path(repo, "RESUME-1").read_text(encoding="utf-8"))
        self.assertEqual("pushed", manifest["state"])
        self.assertEqual("pending", manifest["review"]["verdict"])

        self.approve_task(worktree, "RESUME-1")
        self.ap(repo, "task-integrate", "RESUME-1")
        self.assertEqual("resolved", git_output(remote, "show", "refs/heads/dev:shared.txt"))

    def test_task_start_rolls_back_checkout_hook_side_effects(self) -> None:
        hook_bodies = {
            "untracked": (
                'root="$(git rev-parse --show-toplevel)"\n'
                'printf "hook data\\n" > "$root/hook-created.txt"\n'
            ),
            "clean-commit": (
                'root="$(git rev-parse --show-toplevel)"\n'
                'printf "hook commit\\n" > "$root/hook-created.txt"\n'
                'git -C "$root" add hook-created.txt\n'
                'git -C "$root" commit --no-verify -qm "checkout hook commit"\n'
            ),
        }
        for label, body in hook_bodies.items():
            with self.subTest(label=label):
                root, repo, _ = self.make_repo()
                self.install_hook(repo, "post-checkout", body)
                task_id = f"HOOK-{label.upper()}"

                result = self.ap(
                    repo,
                    "task-start",
                    task_id,
                    "--base",
                    "origin/dev",
                    "--owned-path",
                    ".",
                    check=False,
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn("hook", (result.stdout + result.stderr).lower())
                self.assert_local_branch(repo, f"codex/{task_id}", False)
                self.assertFalse(self.registry_manifest_path(repo, task_id).exists())
                self.assertNotIn(
                    f"refs/heads/codex/{task_id}",
                    git_output(repo, "worktree", "list", "--porcelain"),
                )
                self.assertFalse((root / "worktrees" / repo.name / task_id).exists())

    def test_control_commands_are_rejected_from_another_task_worktree(self) -> None:
        _, repo, _ = self.make_repo()
        first = self.start_task(repo, "CROSS-1", "cross/one")
        second = self.start_task(repo, "CROSS-2", "cross/two")

        commands = [
            ("task-integrate", "CROSS-1"),
            ("task-finish", "CROSS-1"),
            ("task-prune",),
            ("task-start", "CROSS-3"),
        ]
        for args in commands:
            with self.subTest(command=args[0]):
                before = {
                    "control_head": git_output(repo, "rev-parse", "HEAD"),
                    "control_status": git_output(repo, "status", "--porcelain=v1"),
                    "first_head": git_output(first, "rev-parse", "HEAD"),
                    "first_status": git_output(first, "status", "--porcelain=v1"),
                    "second_head": git_output(second, "rev-parse", "HEAD"),
                    "second_status": git_output(second, "status", "--porcelain=v1"),
                    "worktrees": git_output(repo, "worktree", "list", "--porcelain"),
                }
                result = self.ap(second, *args, check=False)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("control", (result.stdout + result.stderr).lower())
                after = {
                    "control_head": git_output(repo, "rev-parse", "HEAD"),
                    "control_status": git_output(repo, "status", "--porcelain=v1"),
                    "first_head": git_output(first, "rev-parse", "HEAD"),
                    "first_status": git_output(first, "status", "--porcelain=v1"),
                    "second_head": git_output(second, "rev-parse", "HEAD"),
                    "second_status": git_output(second, "status", "--porcelain=v1"),
                    "worktrees": git_output(repo, "worktree", "list", "--porcelain"),
                }
                self.assertEqual(before, after)

    def test_task_start_rejects_overlapping_active_owned_paths(self) -> None:
        _, repo, _ = self.make_repo()
        first = self.start_task(repo, "OWNER-1", "backend")
        result = self.ap(
            repo,
            "task-start",
            "OWNER-2",
            "--base",
            "origin/dev",
            "--owned-path",
            "backend/api",
            "--isolated",
            check=False,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("overlap active task OWNER-1", result.stdout + result.stderr)
        self.assertTrue(first.exists())
        self.assertFalse(self.registry_manifest_path(repo, "OWNER-2").exists())
        self.assert_local_branch(repo, "codex/OWNER-2", False)

    def test_task_start_rejects_terminal_ledger_lifecycle_and_multi_writer(self) -> None:
        _, repo, _ = self.make_repo()
        terminal = self.ap(
            repo,
            "task-start",
            "LEDGER-END",
            "--base",
            "origin/dev",
            "--owned-path",
            "docs/tasks/closure-log.md",
            check=False,
        )
        self.assertNotEqual(0, terminal.returncode)
        self.assertIn("terminal maintenance", terminal.stdout + terminal.stderr)
        self.assertFalse(self.registry_manifest_path(repo, "LEDGER-END").exists())

        multi = self.ap(
            repo,
            "task-start",
            "MULTI-1",
            "--base",
            "origin/dev",
            "--owned-path",
            "frontend",
            "--writers",
            "2",
            check=False,
        )
        self.assertNotEqual(0, multi.returncode)
        self.assertIn("exactly one writer lease", multi.stdout + multi.stderr)
        self.assertFalse(self.registry_manifest_path(repo, "MULTI-1").exists())

    def test_missing_task_manifest_is_rejected_in_linked_worktree(self) -> None:
        _, repo, remote = self.make_repo("worktree")
        worktree = self.start_task(repo, "NO-MANIFEST")
        git_dir = Path(git_output(worktree, "rev-parse", "--git-dir"))
        if not git_dir.is_absolute():
            git_dir = (worktree / git_dir).resolve()
        (git_dir / "auto-coding-skill-task.json").unlink()
        before = git_output(worktree, "rev-parse", "HEAD")
        (worktree / "payload.txt").write_text("must not publish\n", encoding="utf-8")

        result = self.ap(
            worktree,
            "commit-push",
            "NO-MANIFEST",
            "--msg",
            "NO-MANIFEST: must fail",
            check=False,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("manifest", (result.stdout + result.stderr).lower())
        self.assertEqual(before, git_output(worktree, "rev-parse", "HEAD"))
        self.assert_remote_branch(remote, "codex/NO-MANIFEST", False)

    def test_corrupt_manifest_cannot_redirect_cleanup_to_control_branch(self) -> None:
        _, repo, remote = self.make_repo()
        worktree = self.start_task(repo, "CORRUPT-1")
        registry = self.registry_manifest_path(repo, "CORRUPT-1")
        worktree_git_dir = Path(git_output(worktree, "rev-parse", "--git-dir"))
        if not worktree_git_dir.is_absolute():
            worktree_git_dir = (worktree / worktree_git_dir).resolve()
        worktree_manifest = worktree_git_dir / "auto-coding-skill-task.json"
        payload = json.loads(registry.read_text(encoding="utf-8"))
        payload["task_branch"] = "dev"
        rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        registry.write_text(rendered, encoding="utf-8")
        worktree_manifest.write_text(rendered, encoding="utf-8")
        local_dev = git_output(repo, "rev-parse", "refs/heads/dev")
        remote_dev = git_output(remote, "rev-parse", "refs/heads/dev")

        result = self.ap(repo, "task-finish", "CORRUPT-1", check=False)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("invalid task branch", (result.stdout + result.stderr).lower())
        self.assertEqual(local_dev, git_output(repo, "rev-parse", "refs/heads/dev"))
        self.assertEqual(remote_dev, git_output(remote, "rev-parse", "refs/heads/dev"))
        self.assertTrue(worktree.exists())
        self.assert_local_branch(repo, "codex/CORRUPT-1", True)

    def test_commit_push_requires_matching_manifest_and_isolated_worktree(self) -> None:
        _, repo, remote = self.make_repo()
        worktree = self.start_task(repo, "ISOLATED-1", "task-only.txt")
        second_worktree = self.start_task(repo, "ISOLATED-2", "second-task-only.txt")
        (worktree / "task-only.txt").write_text("task change\n", encoding="utf-8")
        (second_worktree / "second-task-only.txt").write_text(
            "second task change\n",
            encoding="utf-8",
        )
        (repo / "shared.txt").write_text("primary checkout change\n", encoding="utf-8")

        mismatch = self.assert_rejected_without_mutation(
            worktree,
            "commit-push",
            "ANOTHER-TASK",
            "--msg",
            "ANOTHER-TASK: must fail",
        )
        self.assertIn("task", (mismatch.stdout + mismatch.stderr).lower())

        primary = self.assert_rejected_without_mutation(
            repo,
            "commit-push",
            "ISOLATED-1",
            "--msg",
            "ISOLATED-1: must fail from primary checkout",
        )
        self.assertIn("worktree", (primary.stdout + primary.stderr).lower())

        second_status = git(second_worktree, "status", "--short").stdout
        self.assertIn("?? second-task-only.txt", second_status)
        self.approve_task(worktree, "ISOLATED-1")
        self.approve_task(second_worktree, "ISOLATED-2")
        with ThreadPoolExecutor(max_workers=2) as pool:
            first_commit = pool.submit(
                self.ap,
                worktree,
                "commit-push",
                "ISOLATED-1",
                "--msg",
                "ISOLATED-1: isolated change",
            )
            second_commit = pool.submit(
                self.ap,
                second_worktree,
                "commit-push",
                "ISOLATED-2",
                "--msg",
                "ISOLATED-2: independent change",
            )
            first_commit.result()
            second_commit.result()

        self.assert_remote_branch(remote, "codex/ISOLATED-1", True)
        task_ref = "refs/heads/codex/ISOLATED-1"
        self.assertEqual(
            "task change",
            git_output(remote, "show", f"{task_ref}:task-only.txt"),
        )
        self.assertEqual("baseline", git_output(remote, "show", f"{task_ref}:shared.txt"))
        self.assertNotEqual(
            0,
            git(
                remote,
                "cat-file",
                "-e",
                f"{task_ref}:second-task-only.txt",
                check=False,
            ).returncode,
        )
        self.assertEqual("primary checkout change\n", (repo / "shared.txt").read_text(encoding="utf-8"))
        self.assertEqual(" M shared.txt\n", git(repo, "status", "--short").stdout)
        second_ref = "refs/heads/codex/ISOLATED-2"
        self.assertEqual(
            "second task change",
            git_output(remote, "show", f"{second_ref}:second-task-only.txt"),
        )
        self.assertNotEqual(
            0,
            git(remote, "cat-file", "-e", f"{second_ref}:task-only.txt", check=False).returncode,
        )

    def test_task_integrate_from_primary_pushes_target_and_cleans_task_refs(self) -> None:
        root, repo, remote = self.make_repo()
        gate_marker = root / "gate-invocations"
        commit_hook_marker = root / "commit-hook-invocations"
        push_hook_marker = root / "push-hook-invocations"
        engineering = repo / "docs" / "ENGINEERING.md"
        original = engineering.read_text(encoding="utf-8")
        configured = original.replace(
            "gate_changed: 'true'",
            f"gate_changed: 'printf x >> {gate_marker}'",
        )
        self.assertNotEqual(original, configured)
        engineering.write_text(configured, encoding="utf-8")
        git(repo, "add", "docs/ENGINEERING.md")
        git(repo, "commit", "-qm", "configure observable fast gate")
        git(repo, "push", "-q", "origin", "dev")
        self.install_hook(repo, "pre-commit", f"printf c >> '{commit_hook_marker}'\n")
        self.install_hook(repo, "pre-push", f"printf p >> '{push_hook_marker}'\n")

        worktree = self.start_task(repo, "INTEGRATE-1")
        (worktree / "integrated.txt").write_text("integrated\n", encoding="utf-8")
        self.commit_push(worktree, "INTEGRATE-1", "INTEGRATE-1: ready")
        review_dir = Path(
            json.loads(
                self.registry_manifest_path(repo, "INTEGRATE-1").read_text(encoding="utf-8")
            )["review"]["assignment_path"]
        ).parent
        self.assertTrue(review_dir.is_dir())
        task_commit = git_output(worktree, "rev-parse", "HEAD")
        self.assertEqual("c", commit_hook_marker.read_text(encoding="utf-8"))
        self.assertFalse(
            push_hook_marker.exists(),
            "the internal backup push must not duplicate the final pre-push hook",
        )

        rejected = self.ap(worktree, "task-integrate", "INTEGRATE-1", check=False)
        self.assertNotEqual(0, rejected.returncode)
        self.assertTrue(worktree.exists())
        self.assert_remote_branch(remote, "codex/INTEGRATE-1", True)

        (repo / "shared.txt").write_text("primary work stays untouched\n", encoding="utf-8")
        self.ap(repo, "task-integrate", "INTEGRATE-1")

        self.assertEqual("integrated", git_output(remote, "show", "refs/heads/dev:integrated.txt"))
        self.assertEqual(
            "primary work stays untouched\n",
            (repo / "shared.txt").read_text(encoding="utf-8"),
        )
        self.assertFalse(worktree.exists())
        self.assert_local_branch(repo, "codex/INTEGRATE-1", False)
        self.assert_remote_branch(remote, "codex/INTEGRATE-1", False)
        self.assertFalse(review_dir.exists())
        self.assertEqual("x", gate_marker.read_text(encoding="utf-8"), "push flow must run the fast gate exactly once")
        self.assertEqual("c", commit_hook_marker.read_text(encoding="utf-8"), "push flow must create exactly one hook-visible commit")
        self.assertEqual("p", push_hook_marker.read_text(encoding="utf-8"), "the final target push hook must run exactly once")
        self.assertEqual(task_commit, git_output(remote, "rev-parse", "refs/heads/dev"), "integration must not create a second evidence commit")

    def test_task_integrate_rejects_legacy_gate_failed_state(self) -> None:
        _, repo, remote = self.make_repo()
        worktree = self.start_task(repo, "FAILED-GATE")
        (worktree / "must-not-integrate.txt").write_text("blocked\n", encoding="utf-8")
        self.commit_push(worktree, "FAILED-GATE", "FAILED-GATE: staged task")
        registry = self.registry_manifest_path(repo, "FAILED-GATE")
        payload = json.loads(registry.read_text(encoding="utf-8"))
        payload["state"] = "gate-failed"
        registry.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        result = self.ap(repo, "task-integrate", "FAILED-GATE", check=False)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("committed and pushed", (result.stdout + result.stderr).lower())
        self.assertTrue(worktree.exists())
        self.assertNotEqual(
            0,
            git(remote, "cat-file", "-e", "refs/heads/dev:must-not-integrate.txt", check=False).returncode,
        )

    def test_task_finish_keep_remote_reports_retained_branch(self) -> None:
        _, repo, remote = self.make_repo()
        worktree = self.start_task(repo, "KEEP-REMOTE")
        (worktree / "kept.txt").write_text("kept remotely\n", encoding="utf-8")
        self.commit_push(worktree, "KEEP-REMOTE", "KEEP-REMOTE: ready")
        self.ap(repo, "task-integrate", "KEEP-REMOTE", "--keep-worktree")

        finish = self.ap(repo, "task-finish", "KEEP-REMOTE", "--keep-remote")

        self.assertIn("remote_branch_deleted=false", finish.stdout + finish.stderr)
        self.assertFalse(worktree.exists())
        self.assert_local_branch(repo, "codex/KEEP-REMOTE", False)
        self.assert_remote_branch(remote, "codex/KEEP-REMOTE", True)
        self.assertFalse(self.registry_manifest_path(repo, "KEEP-REMOTE").exists())

    def test_task_deletion_is_isolated_and_committed_only_on_its_task_branch(self) -> None:
        _, repo, remote = self.make_repo()
        deleting = self.start_task(repo, "DELETE-1", "shared.txt")
        observer = self.start_task(repo, "DELETE-2", "observer.txt")
        (deleting / "shared.txt").unlink()
        (observer / "observer.txt").write_text("observer\n", encoding="utf-8")

        self.commit_push(deleting, "DELETE-1", "DELETE-1: delete shared file")

        deleted_ref = "refs/heads/codex/DELETE-1"
        self.assertNotEqual(
            0,
            git(remote, "cat-file", "-e", f"{deleted_ref}:shared.txt", check=False).returncode,
        )
        self.assertEqual("baseline\n", (repo / "shared.txt").read_text(encoding="utf-8"))
        self.assertEqual("baseline\n", (observer / "shared.txt").read_text(encoding="utf-8"))
        self.assertTrue((observer / "observer.txt").exists())

    def test_task_finish_refuses_dirty_or_unmerged_tasks(self) -> None:
        _, repo, _ = self.make_repo()

        dirty_worktree = self.start_task(repo, "DIRTY-1", "dirty.txt")
        (dirty_worktree / "dirty.txt").write_text("not committed\n", encoding="utf-8")
        dirty = self.ap(repo, "task-finish", "DIRTY-1", check=False)
        self.assertNotEqual(0, dirty.returncode)
        self.assertTrue(dirty_worktree.exists())
        self.assert_local_branch(repo, "codex/DIRTY-1", True)
        self.assertTrue((dirty_worktree / "dirty.txt").exists())

        unmerged_worktree = self.start_task(repo, "UNMERGED-1", "unmerged.txt")
        (unmerged_worktree / "unmerged.txt").write_text("committed only on task\n", encoding="utf-8")
        git(unmerged_worktree, "add", "unmerged.txt")
        git(unmerged_worktree, "commit", "-qm", "unmerged task commit")
        unmerged = self.ap(repo, "task-finish", "UNMERGED-1", check=False)
        self.assertNotEqual(0, unmerged.returncode)
        self.assertTrue(unmerged_worktree.exists())
        self.assert_local_branch(repo, "codex/UNMERGED-1", True)
        self.assertEqual("unmerged task commit", git_output(unmerged_worktree, "log", "-1", "--format=%s"))

    def test_task_prune_only_removes_merged_unoccupied_codex_branches(self) -> None:
        root, repo, _ = self.make_repo()
        git(repo, "branch", "codex/merged-free", "dev")
        git(repo, "branch", "feature/merged-free", "dev")

        git(repo, "branch", "codex/unmerged-free", "dev")
        unmerged_path = root / "unmerged-worktree"
        git(repo, "worktree", "add", "-q", str(unmerged_path), "codex/unmerged-free")
        (unmerged_path / "unique.txt").write_text("unique\n", encoding="utf-8")
        git(unmerged_path, "add", "unique.txt")
        git(unmerged_path, "commit", "-qm", "unique unmerged commit")
        git(repo, "worktree", "remove", str(unmerged_path))

        git(repo, "branch", "codex/merged-occupied", "dev")
        occupied_path = root / "occupied-worktree"
        git(repo, "worktree", "add", "-q", str(occupied_path), "codex/merged-occupied")

        self.ap(repo, "task-prune")

        self.assert_local_branch(repo, "codex/merged-free", False)
        self.assert_local_branch(repo, "codex/unmerged-free", True)
        self.assert_local_branch(repo, "codex/merged-occupied", True)
        self.assert_local_branch(repo, "feature/merged-free", True)
        self.assertTrue(occupied_path.exists())

    def test_task_prune_finishes_registered_integrated_worktree(self) -> None:
        _, repo, remote = self.make_repo()
        worktree = self.start_task(repo, "PRUNE-REGISTERED")
        (worktree / "registered.txt").write_text("registered\n", encoding="utf-8")
        self.commit_push(worktree, "PRUNE-REGISTERED", "PRUNE-REGISTERED: ready")
        self.ap(
            repo,
            "task-integrate",
            "PRUNE-REGISTERED",
            "--keep-worktree",
        )
        self.assertTrue(worktree.exists())
        self.assert_local_branch(repo, "codex/PRUNE-REGISTERED", True)

        self.ap(repo, "task-prune")

        self.assertFalse(worktree.exists())
        self.assert_local_branch(repo, "codex/PRUNE-REGISTERED", False)
        self.assert_remote_branch(remote, "codex/PRUNE-REGISTERED", False)

    def test_task_prune_removes_orphan_git_local_review_artifacts(self) -> None:
        _, repo, _ = self.make_repo()
        worktree = self.start_task(repo, "PRUNE-REVIEW-ORPHAN", "shared.txt")
        (worktree / "shared.txt").write_text("orphan review\n", encoding="utf-8")
        issued = json.loads(
            self.ap(
                worktree,
                "review-assignment",
                "PRUNE-REVIEW-ORPHAN",
                "--reviewer",
                "reviewer-orphan",
                "--json",
            ).stdout
        )
        review_dir = Path(issued["assignment_path"]).parent
        self.assertTrue(review_dir.is_dir())
        git(repo, "worktree", "unlock", str(worktree))
        git(repo, "worktree", "remove", "--force", str(worktree))
        self.registry_manifest_path(repo, "PRUNE-REVIEW-ORPHAN").unlink()

        self.ap(repo, "task-prune")

        self.assertFalse(review_dir.exists())
        self.assert_local_branch(repo, "codex/PRUNE-REVIEW-ORPHAN", False)

    def test_cleanup_blocks_unknown_ignored_data_but_allows_runtime_evidence(self) -> None:
        _, repo, remote = self.make_repo()
        (repo / ".gitignore").write_text(".env\n.local/\n", encoding="utf-8")
        git(repo, "add", ".gitignore")
        git(repo, "commit", "-qm", "ignore local runtime files")
        git(repo, "push", "-q", "origin", "dev")

        worktree = self.start_task(repo, "IGNORED-1")
        (worktree / "payload.txt").write_text("ready\n", encoding="utf-8")
        self.commit_push(worktree, "IGNORED-1", "IGNORED-1: ready")
        self.ap(repo, "task-integrate", "IGNORED-1", "--keep-worktree")

        (worktree / ".env").write_text("must survive\n", encoding="utf-8")
        blocked = self.ap(repo, "task-finish", "IGNORED-1", check=False)
        self.assertNotEqual(0, blocked.returncode)
        self.assertIn(".env", blocked.stdout + blocked.stderr)
        self.assertTrue(worktree.exists())
        self.assertEqual("must survive\n", (worktree / ".env").read_text(encoding="utf-8"))

        (worktree / ".env").unlink()
        runtime_evidence = worktree / ".local" / "auto-coding-skill" / "gate.jsonl"
        runtime_evidence.parent.mkdir(parents=True, exist_ok=True)
        runtime_evidence.write_text("runtime evidence\n", encoding="utf-8")
        self.ap(repo, "task-finish", "IGNORED-1")

        self.assertFalse(worktree.exists())
        self.assert_local_branch(repo, "codex/IGNORED-1", False)
        self.assert_remote_branch(remote, "codex/IGNORED-1", False)
        self.assertFalse(self.registry_manifest_path(repo, "IGNORED-1").exists())

    def test_cleanup_safely_deinitializes_submodules_and_preserves_unknown_data(self) -> None:
        root, repo, remote = self.make_repo()
        module = root / "module-source"
        module.mkdir()
        git(module, "init", "-q", "-b", "main")
        git(module, "config", "user.email", "module@example.com")
        git(module, "config", "user.name", "Module Author")
        (module / ".gitignore").write_text(".secret\n.local/\n", encoding="utf-8")
        (module / "module.txt").write_text("module baseline\n", encoding="utf-8")
        git(module, "add", "-A")
        git(module, "commit", "-qm", "module baseline")

        git(
            repo,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            str(module),
            "vendor/module",
        )
        git(repo, "commit", "-qam", "add submodule")
        git(repo, "push", "-q", "origin", "dev")
        primary_submodule_status = git_output(
            repo,
            "submodule",
            "status",
            "--",
            "vendor/module",
        )
        primary_submodule_url = git_output(repo, "config", "--get", "submodule.vendor/module.url")
        self.assertFalse(primary_submodule_status.startswith("-"))

        worktree = self.start_task(repo, "SUBMODULE-1")
        git(
            worktree,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "update",
            "--init",
            "--recursive",
        )
        (worktree / "payload.txt").write_text("ready\n", encoding="utf-8")
        self.commit_push(worktree, "SUBMODULE-1", "SUBMODULE-1: ready")
        self.ap(repo, "task-integrate", "SUBMODULE-1", "--keep-worktree")

        task_module = worktree / "vendor" / "module"
        baseline = git_output(task_module, "rev-parse", "HEAD")

        extra_worktree = root / "submodule-extra-worktree"
        git(
            task_module,
            "worktree",
            "add",
            "-q",
            "-b",
            "extra-check",
            str(extra_worktree),
            baseline,
        )
        (extra_worktree / "module.txt").write_text("external dirty data\n", encoding="utf-8")
        extra_blocked = self.ap(repo, "task-finish", "SUBMODULE-1", check=False)
        self.assertNotEqual(0, extra_blocked.returncode)
        self.assertIn("additional linked worktrees", extra_blocked.stdout + extra_blocked.stderr)
        self.assertEqual(
            "external dirty data\n",
            (extra_worktree / "module.txt").read_text(encoding="utf-8"),
        )
        self.assertEqual("M module.txt", git_output(extra_worktree, "status", "--short"))
        self.assertTrue(worktree.exists())
        self.assert_local_branch(repo, "codex/SUBMODULE-1", True)

        (extra_worktree / "module.txt").write_text("module baseline\n", encoding="utf-8")
        git(task_module, "worktree", "remove", str(extra_worktree))
        extra_tip = git_output(task_module, "rev-parse", "refs/heads/extra-check")
        git(task_module, "update-ref", "-d", "refs/heads/extra-check", extra_tip)

        git(task_module, "checkout", "-qb", "hidden")
        git(task_module, "config", "user.email", "test@example.com")
        git(task_module, "config", "user.name", "Auto Coding Test")
        (task_module / "hidden.txt").write_text("local-only history\n", encoding="utf-8")
        git(task_module, "add", "hidden.txt")
        git(task_module, "commit", "-qm", "hidden local commit")
        hidden_commit = git_output(task_module, "rev-parse", "HEAD")
        git(task_module, "checkout", "-q", "--detach", baseline)
        self.assertEqual("", git_output(worktree, "status", "--porcelain=v1"))
        self.assertEqual("", git_output(task_module, "status", "--porcelain=v1"))

        hidden = self.ap(repo, "task-finish", "SUBMODULE-1", check=False)
        self.assertNotEqual(0, hidden.returncode)
        self.assertIn("local refs/reflogs", hidden.stdout + hidden.stderr)
        self.assertEqual(hidden_commit, git_output(task_module, "rev-parse", "refs/heads/hidden"))
        self.assertTrue(worktree.exists())
        self.assert_local_branch(repo, "codex/SUBMODULE-1", True)

        git(task_module, "push", "-q", "origin", "refs/heads/hidden:refs/heads/hidden")
        git(
            task_module,
            "fetch",
            "-q",
            "origin",
            "refs/heads/hidden:refs/remotes/origin/hidden",
        )

        git(module, "update-ref", "-d", "refs/heads/hidden", hidden_commit)
        git(module, "reflog", "expire", "--expire=now", "--all")
        git(module, "gc", "--prune=now")
        stale = self.ap(repo, "task-finish", "SUBMODULE-1", check=False)
        self.assertNotEqual(0, stale.returncode)
        self.assertIn("local refs/reflogs", stale.stdout + stale.stderr)
        self.assertEqual(hidden_commit, git_output(task_module, "rev-parse", "refs/heads/hidden"))
        self.assertTrue(worktree.exists())

        git(task_module, "push", "-q", "origin", "refs/heads/hidden:refs/heads/hidden")
        git(
            task_module,
            "fetch",
            "-q",
            "origin",
            "refs/heads/hidden:refs/remotes/origin/hidden",
        )

        secret = task_module / ".secret"
        secret.write_text("must survive\n", encoding="utf-8")
        blocked = self.ap(repo, "task-finish", "SUBMODULE-1", check=False)
        self.assertNotEqual(0, blocked.returncode)
        self.assertIn("vendor/module/.secret", blocked.stdout + blocked.stderr)
        self.assertEqual("must survive\n", secret.read_text(encoding="utf-8"))
        self.assertTrue(worktree.exists())
        self.assert_local_branch(repo, "codex/SUBMODULE-1", True)

        secret.unlink()
        runtime_evidence = (
            worktree / "vendor" / "module" / ".local" / "auto-coding-skill" / "gate.jsonl"
        )
        runtime_evidence.parent.mkdir(parents=True, exist_ok=True)
        runtime_evidence.write_text("disposable runtime data\n", encoding="utf-8")
        self.ap(repo, "task-finish", "SUBMODULE-1")

        self.assertFalse(worktree.exists())
        self.assert_local_branch(repo, "codex/SUBMODULE-1", False)
        self.assert_remote_branch(remote, "codex/SUBMODULE-1", False)
        self.assertFalse(self.registry_manifest_path(repo, "SUBMODULE-1").exists())
        self.assertEqual("module baseline\n", (module / "module.txt").read_text(encoding="utf-8"))
        self.assertEqual(
            primary_submodule_status,
            git_output(repo, "submodule", "status", "--", "vendor/module"),
        )
        self.assertEqual(
            primary_submodule_url,
            git_output(repo, "config", "--get", "submodule.vendor/module.url"),
        )
        self.assertEqual("", git_output(repo / "vendor" / "module", "status", "--porcelain=v1"))

        git(module, "update-ref", "-d", "refs/heads/hidden", hidden_commit)
        git(module, "reflog", "expire", "--expire=now", "--all")
        git(module, "gc", "--prune=now")
        self.assertNotEqual(
            0,
            git(module, "cat-file", "-e", f"{hidden_commit}^{{commit}}", check=False).returncode,
        )
        recovery_root = (
            self.registry_manifest_path(repo, "SUBMODULE-1").parents[1]
            / "submodule-recovery"
        )
        recovery_repos = sorted((recovery_root / "repos").glob("*.git"))
        self.assertTrue(recovery_repos)
        self.assertTrue(
            any(
                command(
                    repo,
                    "git",
                    f"--git-dir={candidate}",
                    "cat-file",
                    "-e",
                    f"{hidden_commit}^{{commit}}",
                    check=False,
                ).returncode
                == 0
                for candidate in recovery_repos
            ),
            "durable recovery storage must retain submodule commits after remote deletion",
        )
        self.assertTrue(list((recovery_root / "snapshots").rglob("*.json")))

    def test_submodule_urls_are_worktree_local_and_common_changes_are_not_overwritten(self) -> None:
        root, repo, _ = self.make_repo()
        module = root / "config-module-source"
        module.mkdir()
        git(module, "init", "-q", "-b", "main")
        git(module, "config", "user.email", "module@example.com")
        git(module, "config", "user.name", "Module Author")
        (module / "module.txt").write_text("module baseline\n", encoding="utf-8")
        git(module, "add", "module.txt")
        git(module, "commit", "-qm", "module baseline")
        module_b = root / "config-module-source-b"
        git(root, "clone", "-q", str(module), str(module_b))
        git(
            repo,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            str(module),
            "vendor/module",
        )
        git(repo, "commit", "-qam", "add initially uninitialized submodule")
        git(repo, "push", "-q", "origin", "dev")
        git(repo, "submodule", "-q", "deinit", "-f", "--", "vendor/module")
        git(repo, "config", "--local", "--unset-all", "submodule.vendor/module.url", check=False)
        git(repo, "config", "--local", "--unset-all", "submodule.vendor/module.active", check=False)
        before_status = git_output(repo, "submodule", "status", "--", "vendor/module")
        self.assertTrue(before_status.startswith("-"))

        worktree = self.start_task(repo, "SUBMODULE-CONFIG")
        self.assertEqual(
            str(module),
            git_output(worktree, "config", "--worktree", "--get", "submodule.vendor/module.url"),
        )
        gitmodules = worktree / ".gitmodules"
        gitmodules.write_text(
            gitmodules.read_text(encoding="utf-8").replace(str(module), str(module_b)),
            encoding="utf-8",
        )
        git(
            worktree,
            "config",
            "--local",
            "submodule.vendor/module.url",
            str(module_b),
        )
        git(worktree, "config", "--local", "submodule.vendor/module.active", "true")
        conflict = self.ap(worktree, "task-submodule-sync", "SUBMODULE-CONFIG", check=False)
        self.assertNotEqual(0, conflict.returncode)
        self.assertIn("shared submodule config changed", (conflict.stdout + conflict.stderr).lower())
        self.assertEqual(
            str(module_b),
            git_output(repo, "config", "--local", "--get", "submodule.vendor/module.url"),
        )
        git(repo, "config", "--local", "--unset-all", "submodule.vendor/module.url")
        git(repo, "config", "--local", "--unset-all", "submodule.vendor/module.active")
        self.ap(worktree, "task-submodule-sync", "SUBMODULE-CONFIG")
        self.assertEqual(
            str(module_b),
            git_output(worktree, "config", "--worktree", "--get", "submodule.vendor/module.url"),
        )
        self.assertNotEqual(
            0,
            git(repo, "config", "--local", "--get", "submodule.vendor/module.url", check=False).returncode,
        )

        git(
            worktree,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "update",
            "--init",
            "--recursive",
        )
        self.assertEqual(
            str(module_b),
            git_output(worktree / "vendor" / "module", "remote", "get-url", "origin"),
        )
        self.assertNotEqual(
            0,
            git(repo, "config", "--local", "--get", "submodule.vendor/module.url", check=False).returncode,
        )
        self.assertNotEqual(
            0,
            git(repo, "config", "--local", "--get", "submodule.vendor/module.active", check=False).returncode,
        )
        (worktree / "payload.txt").write_text("ready\n", encoding="utf-8")
        self.commit_push(worktree, "SUBMODULE-CONFIG", "SUBMODULE-CONFIG: ready")
        self.ap(repo, "task-integrate", "SUBMODULE-CONFIG")

        self.assertEqual(before_status, git_output(repo, "submodule", "status", "--", "vendor/module"))
        self.assertNotEqual(
            0,
            git(repo, "config", "--local", "--get", "submodule.vendor/module.url", check=False).returncode,
        )

    def test_relative_submodule_url_uses_task_base_instead_of_control_checkout(self) -> None:
        root, repo, super_remote = self.make_repo()
        module_source = root / "relative-module-source"
        module_source.mkdir()
        git(module_source, "init", "-q", "-b", "main")
        git(module_source, "config", "user.email", "module@example.com")
        git(module_source, "config", "user.name", "Module Author")
        (module_source / "module.txt").write_text("module baseline\n", encoding="utf-8")
        git(module_source, "add", "module.txt")
        git(module_source, "commit", "-qm", "module baseline")
        module_a = root / "module-a.git"
        module_b = root / "module-b.git"
        git(root, "clone", "-q", "--bare", str(module_source), str(module_a))
        git(root, "clone", "-q", "--bare", str(module_source), str(module_b))

        git(
            repo,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            str(module_a),
            "vendor/module",
        )
        gitmodules = repo / ".gitmodules"
        gitmodules.write_text(
            gitmodules.read_text(encoding="utf-8").replace(str(module_a), "../module-a.git"),
            encoding="utf-8",
        )
        git(repo, "commit", "-qam", "add relative submodule URL")
        git(repo, "push", "-q", "origin", "dev")
        git(repo, "submodule", "-q", "deinit", "-f", "--", "vendor/module")
        git(repo, "config", "--local", "--unset-all", "submodule.vendor/module.url", check=False)
        git(repo, "config", "--local", "--unset-all", "submodule.vendor/module.active", check=False)

        git(repo, "branch", "alternate", "dev")
        alternate = root / "alternate-base"
        git(repo, "worktree", "add", "-q", str(alternate), "alternate")
        alternate_gitmodules = alternate / ".gitmodules"
        alternate_gitmodules.write_text(
            alternate_gitmodules.read_text(encoding="utf-8").replace(
                "../module-a.git",
                "../module-b.git",
            ),
            encoding="utf-8",
        )
        git(alternate, "commit", "-qam", "use alternate relative submodule URL")
        git(alternate, "push", "-q", "origin", "alternate")
        git(repo, "worktree", "remove", str(alternate))
        upstream_root = root / "upstream"
        upstream_root.mkdir()
        upstream_super = upstream_root / "super.git"
        git(root, "clone", "-q", "--bare", str(super_remote), str(upstream_super))
        git(repo, "remote", "add", "upstream", str(upstream_super))

        self.ap(
            repo,
            "task-start",
            "RELATIVE-BASE",
            "--base",
            "upstream/alternate",
            "--target-branch",
            "alternate",
            "--remote",
            "upstream",
            "--owned-path",
            ".",
        )
        worktree = self.task_worktree(repo, "RELATIVE-BASE")
        self.assertIn("../module-b.git", (worktree / ".gitmodules").read_text(encoding="utf-8"))
        self.assertEqual(
            module_b.resolve(),
            Path(
                git_output(
                    worktree,
                    "config",
                    "--worktree",
                    "--get",
                    "submodule.vendor/module.url",
                )
            ).resolve(),
        )
        git(
            worktree,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "update",
            "--init",
            "--recursive",
        )
        self.assertEqual(
            module_b.resolve(),
            Path(
                git_output(worktree / "vendor" / "module", "remote", "get-url", "origin")
            ).resolve(),
        )
        self.assertNotEqual(
            0,
            git(repo, "config", "--local", "--get", "submodule.vendor/module.url", check=False).returncode,
        )

    def test_cleanup_blocks_deinitialized_residual_submodule_git_history(self) -> None:
        root, repo, remote = self.make_repo()
        for name in ("a", "b"):
            module = root / f"residual-module-{name}"
            module.mkdir()
            git(module, "init", "-q", "-b", "main")
            git(module, "config", "user.email", f"{name}@example.com")
            git(module, "config", "user.name", f"Module {name.upper()}")
            (module / "module.txt").write_text(f"module {name}\n", encoding="utf-8")
            git(module, "add", "module.txt")
            git(module, "commit", "-qm", f"module {name} baseline")
            git(
                repo,
                "-c",
                "protocol.file.allow=always",
                "submodule",
                "add",
                "-q",
                str(module),
                f"vendor/{name}",
            )
        git(repo, "commit", "-qam", "add residual-state submodules")
        git(repo, "push", "-q", "origin", "dev")

        worktree = self.start_task(repo, "SUBMODULE-RESIDUAL")
        git(
            worktree,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "update",
            "--init",
            "--recursive",
        )
        (worktree / "payload.txt").write_text("ready\n", encoding="utf-8")
        self.commit_push(worktree, "SUBMODULE-RESIDUAL", "SUBMODULE-RESIDUAL: ready")
        self.ap(repo, "task-integrate", "SUBMODULE-RESIDUAL", "--keep-worktree")

        module_b = worktree / "vendor" / "b"
        baseline = git_output(module_b, "rev-parse", "HEAD")
        git(module_b, "config", "user.email", "test@example.com")
        git(module_b, "config", "user.name", "Auto Coding Test")
        git(module_b, "checkout", "-qb", "hidden")
        (module_b / "hidden.txt").write_text("local-only residual history\n", encoding="utf-8")
        git(module_b, "add", "hidden.txt")
        git(module_b, "commit", "-qm", "hidden residual commit")
        hidden_commit = git_output(module_b, "rev-parse", "HEAD")
        module_b_git_dir = Path(git_output(module_b, "rev-parse", "--git-dir"))
        if not module_b_git_dir.is_absolute():
            module_b_git_dir = (module_b / module_b_git_dir).resolve()
        git(module_b, "checkout", "-q", "--detach", baseline)
        git(worktree, "submodule", "-q", "deinit", "-f", "--", "vendor/b")
        module_b_url = git_output(
            repo,
            "config",
            "--file",
            str(repo / ".gitmodules"),
            "--get",
            "submodule.vendor/b.url",
        )
        git(repo, "config", "--local", "submodule.vendor/b.url", module_b_url)
        git(repo, "config", "--local", "submodule.vendor/b.active", "true")
        self.assertFalse((worktree / "vendor" / "b" / ".git").exists())
        self.assertEqual(
            hidden_commit,
            command(
                repo,
                "git",
                f"--git-dir={module_b_git_dir}",
                "rev-parse",
                "refs/heads/hidden",
            ).stdout.strip(),
        )

        blocked = self.ap(repo, "task-finish", "SUBMODULE-RESIDUAL", check=False)
        self.assertNotEqual(0, blocked.returncode)
        self.assertIn("residual module Git directory", blocked.stdout + blocked.stderr)
        self.assertTrue(worktree.exists())
        self.assertTrue(module_b_git_dir.exists())
        self.assertEqual(
            hidden_commit,
            command(
                repo,
                "git",
                f"--git-dir={module_b_git_dir}",
                "rev-parse",
                "refs/heads/hidden",
            ).stdout.strip(),
        )
        self.assert_local_branch(repo, "codex/SUBMODULE-RESIDUAL", True)
        self.assert_remote_branch(remote, "codex/SUBMODULE-RESIDUAL", True)
        self.assertTrue(self.registry_manifest_path(repo, "SUBMODULE-RESIDUAL").exists())
        self.assertTrue((worktree / "vendor" / "a" / ".git").exists())

    def test_changed_remote_task_branch_stays_cleanup_pending_until_safe_retry(self) -> None:
        root, repo, remote = self.make_repo()
        worktree = self.start_task(repo, "REMOTE-RACE")
        (worktree / "payload.txt").write_text("ready\n", encoding="utf-8")
        self.commit_push(worktree, "REMOTE-RACE", "REMOTE-RACE: ready")
        review_dir = Path(
            json.loads(
                self.registry_manifest_path(repo, "REMOTE-RACE").read_text(encoding="utf-8")
            )["review"]["assignment_path"]
        ).parent
        self.ap(repo, "task-integrate", "REMOTE-RACE", "--keep-worktree")

        attacker = root / "attacker"
        git(root, "clone", "-q", str(remote), str(attacker))
        git(attacker, "config", "user.email", "other@example.com")
        git(attacker, "config", "user.name", "Other Writer")
        git(attacker, "checkout", "-qb", "remote-race", "origin/codex/REMOTE-RACE")
        (attacker / "other.txt").write_text("other writer\n", encoding="utf-8")
        git(attacker, "add", "other.txt")
        git(attacker, "commit", "-qm", "other writer advances task branch")
        git(attacker, "push", "-q", "origin", "HEAD:refs/heads/codex/REMOTE-RACE")
        changed_remote_tip = git_output(remote, "rev-parse", "refs/heads/codex/REMOTE-RACE")

        finish = self.ap(repo, "task-finish", "REMOTE-RACE")
        self.assertIn("remote_branch_deleted=false", finish.stdout + finish.stderr)
        self.assertFalse(worktree.exists())
        self.assert_local_branch(repo, "codex/REMOTE-RACE", False)
        self.assertEqual(
            changed_remote_tip,
            git_output(remote, "rev-parse", "refs/heads/codex/REMOTE-RACE"),
        )
        manifest_path = self.registry_manifest_path(repo, "REMOTE-RACE")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("cleanup-pending", manifest["state"])
        self.assertTrue(review_dir.is_dir())

        prune = self.ap(repo, "task-prune")
        self.assertIn("remote cleanup pending", prune.stdout + prune.stderr)
        self.assertTrue(manifest_path.exists())
        self.assert_remote_branch(remote, "codex/REMOTE-RACE", True)

        git(remote, "update-ref", "-d", "refs/heads/codex/REMOTE-RACE", changed_remote_tip)
        self.ap(repo, "task-prune")
        self.assertFalse(manifest_path.exists())
        self.assertFalse(review_dir.exists())
        self.assert_remote_branch(remote, "codex/REMOTE-RACE", False)

    def test_gate_mutation_aborts_before_staging_or_commit(self) -> None:
        _, repo, remote = self.make_repo()
        self.update_config(
            repo,
            lambda config: config["commands"].update(
                {"gate_changed": "printf gate-change >> shared.txt"}
            ),
        )
        worktree = self.start_task(repo, "MUTATE-1")
        before = git_output(worktree, "rev-parse", "HEAD")
        (worktree / "task.txt").write_text("task\n", encoding="utf-8")
        self.approve_task(worktree, "MUTATE-1")

        result = self.ap(
            worktree,
            "commit-push",
            "MUTATE-1",
            "--msg",
            "MUTATE-1: must abort",
            check=False,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("gate changed", (result.stdout + result.stderr).lower())
        self.assertEqual(before, git_output(worktree, "rev-parse", "HEAD"))
        self.assertEqual("", git_output(worktree, "diff", "--cached", "--name-only"))
        self.assert_remote_branch(remote, "codex/MUTATE-1", False)

    def test_post_commit_hook_mutation_prevents_push(self) -> None:
        _, repo, remote = self.make_repo()
        worktree = self.start_task(repo, "COMMIT-HOOK")
        self.install_hook(
            repo,
            "post-commit",
            'root="$(git rev-parse --show-toplevel)"\n'
            'printf "hook mutation\\n" > "$root/hook-after.txt"\n',
        )
        before = git_output(worktree, "rev-parse", "HEAD")
        (worktree / "payload.txt").write_text("payload\n", encoding="utf-8")
        self.approve_task(worktree, "COMMIT-HOOK")

        result = self.ap(
            worktree,
            "commit-push",
            "COMMIT-HOOK",
            "--msg",
            "COMMIT-HOOK: must stay local",
            check=False,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("not pushed", (result.stdout + result.stderr).lower())
        self.assertNotEqual(before, git_output(worktree, "rev-parse", "HEAD"))
        self.assertEqual("hook mutation\n", (worktree / "hook-after.txt").read_text(encoding="utf-8"))
        self.assert_remote_branch(remote, "codex/COMMIT-HOOK", False)

    def test_missing_config_defaults_to_worktree_and_legacy_is_rejected(self) -> None:
        _, default_repo, _ = self.make_repo(_MISSING)
        (default_repo / "shared.txt").write_text("must stay isolated\n", encoding="utf-8")
        default_commit = self.assert_rejected_without_mutation(
            default_repo,
            "commit-push",
            "DEFAULT-1",
            "--msg",
            "DEFAULT-1: must start first",
        )
        self.assertIn("task-start", (default_commit.stdout + default_commit.stderr).lower())
        default_repo.joinpath("shared.txt").write_text("baseline\n", encoding="utf-8")
        self.start_task(default_repo, "DEFAULT-1")

        _, legacy_repo, legacy_remote = self.make_repo("legacy")
        before = git_output(legacy_repo, "rev-parse", "HEAD")
        (legacy_repo / "shared.txt").write_text("legacy shared checkout\n", encoding="utf-8")
        result = self.ap(
            legacy_repo,
            "commit-push",
            "LEGACY-1",
            "--msg",
            "LEGACY-1: must be rejected",
            check=False,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("must be adaptive or worktree", result.stdout + result.stderr)
        self.assertEqual(before, git_output(legacy_repo, "rev-parse", "HEAD"))
        self.assertEqual(
            "baseline",
            git_output(legacy_remote, "show", "refs/heads/dev:shared.txt"),
        )


if __name__ == "__main__":
    unittest.main()
