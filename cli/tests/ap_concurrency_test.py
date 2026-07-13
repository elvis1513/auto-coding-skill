#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
AP_SCRIPT = REPO_ROOT / "src" / "auto-coding-skill" / "scripts" / "ap.py"
_MISSING = object()


def command(
    cwd: Path,
    *args: str,
    check: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(args),
        cwd=cwd,
        check=False,
        text=True,
        input=input_text,
        capture_output=True,
        timeout=30,
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


def base_config(isolation: str | object = "worktree") -> dict:
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
            "default_scope": "auto",
            "fallback_scope": "standard",
            "full_on_unknown": True,
            "no_change_scope": "standard",
            "rules": [],
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

    def approve_task(self, repo: Path, task_id: str) -> str:
        status = self.ap(repo, "task-status", task_id, "--json")
        fingerprint = json.loads(status.stdout)["tasks"][0]["current_diff_fingerprint"]
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

    def commit_push(self, repo: Path, task_id: str, message: str) -> subprocess.CompletedProcess[str]:
        self.approve_task(repo, task_id)
        return self.ap(repo, "commit-push", task_id, "--msg", message)

    def task_worktree(self, repo: Path, task_id: str) -> Path:
        wanted = f"refs/heads/codex/{task_id}"
        current_path: Path | None = None
        for line in git_output(repo, "worktree", "list", "--porcelain").splitlines():
            if line.startswith("worktree "):
                current_path = Path(line.removeprefix("worktree "))
            elif line == f"branch {wanted}" and current_path is not None:
                return current_path
        self.fail(f"no worktree registered for {wanted}")

    def start_task(self, repo: Path, task_id: str) -> Path:
        result = self.ap(
            repo,
            "task-start",
            task_id,
            "--base",
            "origin/dev",
            "--owned-path",
            ".",
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
            "# Workflow\nRuntime changes require the full gate.\n",
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

    def install_hook(self, repo: Path, name: str, body: str) -> Path:
        common_dir = Path(git_output(repo, "rev-parse", "--git-common-dir"))
        if not common_dir.is_absolute():
            common_dir = (repo / common_dir).resolve()
        hook = common_dir / "hooks" / name
        hook.write_text("#!/bin/sh\nset -eu\n" + body, encoding="utf-8")
        hook.chmod(0o755)
        return hook

    def test_task_start_creates_external_worktree_manifest_and_status(self) -> None:
        _, repo, _ = self.make_repo()
        worktree = self.start_task(repo, "START-1")

        status = self.ap(repo, "task-status", "START-1")
        rendered_status = status.stdout + status.stderr
        self.assertIn("START-1", rendered_status)
        self.assertIn("codex/START-1", rendered_status)
        self.assertIn(str(worktree), rendered_status)

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
        active_task = (worktree / "docs" / "tasks" / "active" / "START-1.md").read_text(
            encoding="utf-8"
        )
        for field in [
            "Worktree:",
            "Orchestrator:",
            "Owning fixer:",
            "Owned paths:",
            "Depends on integrated tasks:",
            "Reviewer / stable diff:",
            "Review verdict:",
        ]:
            self.assertIn(field, active_task)

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
        owner = os.environ["CODEX_THREAD_ID"]
        self.ap(
            repo,
            "task-start",
            "LEASE-1",
            "--base",
            "origin/dev",
            "--owned-path",
            ".",
            "--writer",
            "fixer-label",
        )
        worktree = self.task_worktree(repo, "LEASE-1")
        (worktree / "lease.txt").write_text("ready\n", encoding="utf-8")
        self.approve_task(worktree, "LEASE-1")

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
            "1",
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
            "1",
            check=False,
        )
        self.assertNotEqual(0, stale.returncode)
        self.assertIn("generation changed", stale.stdout + stale.stderr)
        manifest = json.loads(self.registry_manifest_path(repo, "LEASE-1").read_text(encoding="utf-8"))
        self.assertEqual(owner, manifest["writer_lease"]["holder"])
        self.assertEqual(2, manifest["writer_lease"]["generation"])

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
        first = self.start_task(repo, "CROSS-1")
        second = self.start_task(repo, "CROSS-2")

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
        worktree = self.start_task(repo, "ISOLATED-1")
        second_worktree = self.start_task(repo, "ISOLATED-2")
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
        self.assertIn("?? docs/tasks/active/", second_status)
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
        deleting = self.start_task(repo, "DELETE-1")
        observer = self.start_task(repo, "DELETE-2")
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

        dirty_worktree = self.start_task(repo, "DIRTY-1")
        (dirty_worktree / "dirty.txt").write_text("not committed\n", encoding="utf-8")
        dirty = self.ap(repo, "task-finish", "DIRTY-1", check=False)
        self.assertNotEqual(0, dirty.returncode)
        self.assertTrue(dirty_worktree.exists())
        self.assert_local_branch(repo, "codex/DIRTY-1", True)
        self.assertTrue((dirty_worktree / "dirty.txt").exists())

        unmerged_worktree = self.start_task(repo, "UNMERGED-1")
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

        prune = self.ap(repo, "task-prune")
        self.assertIn("remote cleanup pending", prune.stdout + prune.stderr)
        self.assertTrue(manifest_path.exists())
        self.assert_remote_branch(remote, "codex/REMOTE-RACE", True)

        git(remote, "update-ref", "-d", "refs/heads/codex/REMOTE-RACE", changed_remote_tip)
        self.ap(repo, "task-prune")
        self.assertFalse(manifest_path.exists())
        self.assert_remote_branch(remote, "codex/REMOTE-RACE", False)

    def test_gate_mutation_aborts_before_staging_or_commit(self) -> None:
        _, repo, remote = self.make_repo()
        worktree = self.start_task(repo, "MUTATE-1")
        engineering = worktree / "docs" / "ENGINEERING.md"
        text = engineering.read_text(encoding="utf-8")
        text = text.replace("gate_changed: 'true'", "gate_changed: 'printf gate-change >> shared.txt'")
        engineering.write_text(text, encoding="utf-8")
        git(worktree, "add", "docs/ENGINEERING.md")
        git(worktree, "commit", "-qm", "configure mutating gate")
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
        self.assertIn("must be worktree", result.stdout + result.stderr)
        self.assertEqual(before, git_output(legacy_repo, "rev-parse", "HEAD"))
        self.assertEqual(
            "baseline",
            git_output(legacy_remote, "show", "refs/heads/dev:shared.txt"),
        )


if __name__ == "__main__":
    unittest.main()
