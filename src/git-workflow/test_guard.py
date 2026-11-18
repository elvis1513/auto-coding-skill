"""Hermetic Git fixtures only: no product builds, network or target services."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


GUARD = Path(__file__).with_name("guard.py").resolve()


class VersionGateReached(Exception):
    pass


class VersionGateTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("guard_version_fixture", GUARD)
        self.guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.guard)

    def test_supported_git_version_variants_reach_the_installation_boundary(self):
        for text in ("git version 2.38.0", "git version 2.50.1.windows.1", "git version 2.39.5 (Apple Git-154)", "git version 2.51.0-rc0", "git version 10.0.GIT"):
            with self.subTest(text=text), patch.object(self.guard, "value", return_value=text), patch.object(self.guard, "state_dir", side_effect=VersionGateReached):
                with self.assertRaises(VersionGateReached):
                    self.guard.install()

    def test_unsupported_or_malformed_versions_never_reach_installation(self):
        for text in ("git version 2.37.9", "", "unrelated 2.50", "9" * 50000, "git version " + "9" * 50000):
            with self.subTest(text=text[:40]), patch.object(self.guard, "value", return_value=text), patch.object(self.guard, "state_dir") as stage:
                with self.assertRaises(self.guard.Rejected):
                    self.guard.install()
                stage.assert_not_called()


class GuardTest(unittest.TestCase):
    def setUp(self):
        scratch = GUARD.parents[2] / ".local" / "git-workflow-guard-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="fixture-", dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.main = self.root / "main"
        self.remote = self.root / "remote.git"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                        GIT_TERMINAL_PROMPT="0", PYTHONDONTWRITEBYTECODE="1")
        self.run_git(self.root, "init", "--bare", str(self.remote))
        self.run_git(self.root, "init", "-b", "dev", str(self.main))
        self.run_git(self.main, "config", "user.name", "Guard Fixture")
        self.run_git(self.main, "config", "user.email", "guard-fixture@example.invalid")
        self.run_git(self.main, "config", "commit.gpgsign", "false")
        self.run_git(self.main, "remote", "add", "origin", str(self.remote))
        self.commit(self.main, "seed")
        self.run_git(self.main, "push", "-u", "origin", "dev")
        self.base = self.run_git(self.main, "rev-parse", "HEAD").stdout.strip()

    def run_cmd(self, cwd, *args, ok=True, input=None):
        result = subprocess.run(args, cwd=cwd, env=self.env, text=True,
                                input=input, capture_output=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def run_git(self, cwd, *args, **kwargs):
        return self.run_cmd(cwd, "git", *args, **kwargs)

    def install(self):
        return self.run_cmd(self.main, sys.executable, str(GUARD), "install")

    def task(self, name="task"):
        path = self.root / name
        self.run_git(self.main, "worktree", "add", "-b", "codex/" + name,
                     str(path), "origin/dev")
        return path

    def commit(self, cwd, name, *options, ok=True):
        (cwd / (name + ".txt")).write_text(name + "\n")
        self.run_git(cwd, "add", "--", name + ".txt")
        return self.run_git(cwd, "commit", *options, "-m", name, ok=ok)

    def test_dev_commit_blocked_and_index_preserved(self):
        self.install()
        result = self.commit(self.main, "blocked", ok=False)
        self.assertIn("independent", result.stderr)
        self.assertEqual(self.run_git(self.main, "rev-parse", "HEAD").stdout.strip(), self.base)
        self.assertIn("blocked.txt", self.run_git(self.main, "diff", "--cached", "--name-only").stdout)

    def test_dev_no_verify_still_blocked_by_reference_transaction(self):
        self.install()
        result = self.commit(self.main, "blocked", "--no-verify", ok=False)
        self.assertIn("Direct development on dev", result.stderr)
        self.assertEqual(self.run_git(self.main, "rev-parse", "HEAD").stdout.strip(), self.base)

    def test_codex_branch_in_primary_checkout_is_not_isolation(self):
        self.install()
        self.run_git(self.main, "switch", "-c", "codex/fake")
        self.commit(self.main, "blocked", ok=False)
        self.commit(self.main, "blocked", "--no-verify", ok=False)

    def test_linked_non_codex_and_detached_commits_blocked(self):
        self.install()
        path = self.root / "other"
        self.run_git(self.main, "worktree", "add", "-b", "feature/other", str(path), "origin/dev")
        self.commit(path, "blocked", ok=False)
        self.run_git(path, "restore", "--staged", "blocked.txt")
        self.run_git(path, "switch", "--detach", "HEAD")
        self.commit(path, "blocked", ok=False)

    def test_codex_worktree_commit_and_push_to_dev(self):
        self.install()
        path = self.task()
        self.commit(path, "allowed")
        self.run_git(path, "push", "origin", "HEAD:refs/heads/dev")
        self.run_git(self.main, "merge", "--ff-only", "origin/dev")
        self.assertTrue((self.main / "allowed.txt").is_file())

    def test_primary_fast_forward_then_push(self):
        self.install()
        path = self.task()
        self.commit(path, "allowed")
        self.run_git(self.main, "merge", "--ff-only", "codex/task")
        self.run_git(self.main, "push", "origin", "dev")

    def test_pure_no_ff_integration_allowed(self):
        self.install()
        path = self.task()
        self.commit(path, "allowed")
        self.run_git(self.main, "merge", "--no-ff", "codex/task", "-m", "integrate task")
        self.run_git(self.main, "push", "origin", "dev")

    def test_extra_content_in_dev_merge_is_blocked(self):
        self.install()
        path = self.task()
        self.commit(path, "allowed")
        self.run_git(self.main, "merge", "--no-ff", "--no-commit", "codex/task")
        self.commit(self.main, "unrelated", ok=False)
        self.commit(self.main, "unrelated", "--no-verify", ok=False)

    def test_preexisting_isolated_task_is_preserved(self):
        path = self.task()
        self.commit(path, "already-working")
        before = self.run_git(path, "rev-parse", "HEAD").stdout
        self.install()
        self.assertEqual(before, self.run_git(path, "rev-parse", "HEAD").stdout)
        self.run_git(path, "push", "origin", "HEAD:dev")

    def test_preexisting_primary_dev_commit_is_not_grandfathered(self):
        self.commit(self.main, "direct-dev")
        self.install()
        self.run_git(self.main, "push", "origin", "dev", ok=False)

    def test_dev_delete_and_rewrite_blocked(self):
        self.install()
        path = self.task()
        self.commit(path, "allowed")
        self.run_git(self.main, "merge", "--ff-only", "codex/task")
        self.run_git(self.main, "update-ref", "refs/heads/dev", self.base, ok=False)
        self.run_git(self.main, "update-ref", "-d", "refs/heads/dev", ok=False)
        self.run_git(path, "push", "origin", ":dev", ok=False)

    def test_amend_and_rebase_keep_provenance(self):
        self.install()
        path = self.task()
        self.commit(path, "one")
        self.commit(path, "two", "--amend")
        other = self.task("other")
        self.commit(other, "remote-change")
        self.run_git(other, "push", "origin", "HEAD:dev")
        self.run_git(path, "rebase", "origin/dev")
        self.run_git(path, "push", "origin", "HEAD:dev")

    def test_merge_latest_dev_into_task(self):
        self.install()
        path, other = self.task(), self.task("other")
        self.commit(path, "one")
        self.commit(other, "other")
        self.run_git(other, "push", "origin", "HEAD:dev")
        self.run_git(path, "merge", "--no-edit", "origin/dev")
        self.run_git(path, "push", "origin", "HEAD:dev")

    def test_stale_push_requires_reconciliation(self):
        self.install()
        path, other = self.task(), self.task("other")
        self.commit(path, "one")
        self.commit(other, "other")
        self.run_git(other, "push", "origin", "HEAD:dev")
        self.run_git(path, "push", "--force", "origin", "HEAD:dev", ok=False)

    def test_existing_hook_runs_and_can_reject(self):
        hook_dir = self.main / "config" / "hooks"
        hook_dir.mkdir(parents=True)
        (hook_dir / "pre-commit").write_text("#!/bin/sh\necho original-hook >&2\nexit 19\n")
        (hook_dir / "pre-commit").chmod(0o755)
        self.run_git(self.main, "add", "config/hooks/pre-commit")
        self.run_git(self.main, "commit", "-m", "original hook")
        self.run_git(self.main, "push", "origin", "dev")
        self.run_git(self.main, "config", "core.hooksPath", "config/hooks")
        self.install()
        path = self.task()
        result = self.commit(path, "blocked-by-original", ok=False)
        self.assertIn("original-hook", result.stderr)
        self.run_cmd(self.main, sys.executable, str(GUARD), "uninstall")
        self.assertEqual(self.run_git(self.main, "config", "core.hooksPath").stdout.strip(), "config/hooks")
        self.assertTrue((hook_dir / "pre-commit").is_file())

    def test_install_preserves_other_worktree_dirty_files(self):
        path = self.task()
        (path / "unfinished.txt").write_text("owned by another conversation\n")
        self.run_git(path, "add", "unfinished.txt")
        before = self.run_git(path, "status", "--porcelain").stdout
        self.install()
        self.assertEqual(before, self.run_git(path, "status", "--porcelain").stdout)
        self.assertEqual((path / "unfinished.txt").read_text(), "owned by another conversation\n")

    def test_existing_pre_push_receives_original_stdin(self):
        hook = self.main / ".git/hooks/pre-push"
        hook.write_text("#!/bin/sh\nread local_ref local_sha remote_ref remote_sha\n"
                        '[ "$remote_ref" = refs/heads/dev ] || exit 31\n'
                        "echo chained-pre-push >&2\n")
        hook.chmod(0o755)
        self.install()
        path = self.task()
        self.commit(path, "allowed")
        result = self.run_git(path, "push", "origin", "HEAD:dev")
        self.assertIn("chained-pre-push", result.stderr)

    def test_fast_forward_from_another_clone_is_allowed(self):
        self.install()
        clone = self.root / "remote-developer"
        self.run_git(self.root, "clone", "--branch", "dev", str(self.remote), str(clone))
        self.run_git(clone, "config", "user.name", "Other Fixture")
        self.run_git(clone, "config", "user.email", "other@example.invalid")
        self.commit(clone, "remote-only")
        self.run_git(clone, "push", "origin", "dev")
        self.run_git(self.main, "fetch", "origin", "dev")
        self.run_git(self.main, "merge", "--ff-only", "origin/dev")

    def test_idempotent_install_status_and_uninstall(self):
        self.install()
        first = self.run_git(self.main, "config", "core.hooksPath").stdout
        self.install()
        self.assertEqual(first, self.run_git(self.main, "config", "core.hooksPath").stdout)
        status = self.run_cmd(self.main, sys.executable, str(GUARD), "status")
        self.assertTrue(json.loads(status.stdout)["ok"])
        self.run_cmd(self.main, sys.executable, str(GUARD), "uninstall")
        self.assertEqual(self.run_git(self.main, "config", "--get", "core.hooksPath", ok=False).returncode, 1)

    def test_new_task_push_inherits_already_accepted_remote_dev(self):
        self.install()
        clone = self.root / "remote-maintenance"
        self.run_git(self.root, "clone", "--branch", "dev", str(self.remote), str(clone))
        self.run_git(clone, "config", "user.name", "Remote Fixture")
        self.run_git(clone, "config", "user.email", "remote@example.invalid")
        self.commit(clone, "remote-maintenance")
        self.run_git(clone, "push", "origin", "dev")
        self.run_git(self.main, "fetch", "origin", "dev")
        path = self.task()
        self.commit(path, "isolated-feature")
        self.run_git(path, "push", "origin", "HEAD:refs/heads/codex/task")
        other = self.root / "other.git"
        self.run_git(self.root, "init", "--bare", str(other))
        self.run_git(self.main, "remote", "add", "other", str(other))
        rejected = self.run_git(path, "push", "other", "HEAD:refs/heads/codex/task", ok=False)
        self.assertIn("Unverified commit origin", rejected.stderr)

    def test_new_task_push_still_rejects_unverified_new_commits(self):
        self.install()
        path = self.task()
        self.commit(path, "isolated-feature")
        tree = self.run_git(path, "write-tree").stdout.strip()
        parent = self.run_git(path, "rev-parse", "HEAD").stdout.strip()
        unverified = self.run_git(path, "commit-tree", tree, "-p", parent,
                                  "-m", "uncertified fixture").stdout.strip()
        self.run_git(path, "update-ref", "refs/heads/codex/task", unverified)
        result = self.run_git(path, "push", "origin", "HEAD:refs/heads/codex/task", ok=False)
        self.assertIn("Unverified commit origin", result.stderr)

    def test_pack_refs_and_maintenance_leave_exact_live_heads(self):
        self.install()
        path = self.task()
        self.commit(path, "isolated")
        before = self.run_git(self.main, "show-ref", "--heads").stdout
        self.run_git(self.main, "pack-refs", "--all")
        self.assertFalse((self.main / ".git/refs/heads/dev").exists())
        self.run_git(self.main, "maintenance", "run", "--task=pack-refs")
        self.assertEqual(self.run_git(self.main, "show-ref", "--heads").stdout, before)
        self.commit(path, "second")
        updated = self.run_git(path, "rev-parse", "HEAD").stdout
        self.run_git(self.main, "pack-refs", "--all")
        self.assertEqual(self.run_git(path, "rev-parse", "HEAD").stdout, updated)

    def test_protect_dev_deletion_with_loose_packed_and_both(self):
        self.install()
        for mode in ("loose", "both", "packed"):
            if mode != "loose":
                self.run_git(self.main, "pack-refs", "--all", *(["--no-prune"] if mode == "both" else []))
            for old in ([], [self.base]):
                with self.subTest(mode=mode, old=bool(old)):
                    result = self.run_git(self.main, "update-ref", "-d", "refs/heads/dev", *old, ok=False)
                    self.assertIn("blocked", result.stderr)
                    self.assertEqual(self.run_git(self.main, "rev-parse", "dev").stdout.strip(), self.base)

    def test_new_clone_does_not_inherit_local_installation(self):
        self.install()
        clone = self.root / "ci-clone"
        self.run_git(self.root, "clone", "--branch", "dev", str(self.remote), str(clone))
        self.run_git(clone, "config", "--get", "core.hooksPath", ok=False)
        self.assertFalse((clone / ".git/codex-workflow-guard").exists())

    def test_upgrade_preserves_receipts_prior_hooks_and_dirty_task(self):
        self.install()
        task = self.task()
        self.commit(task, "receipt")
        (task / "pending").write_text("still editing")
        root = self.main / ".git/codex-workflow-guard"
        statefile = root / "state.json"
        old = json.loads(statefile.read_text())
        receipts = {p.name: p.read_bytes() for p in (root / "commits").iterdir()}
        statefile.write_text(json.dumps({**old, "version": 1}))
        self.install()
        state = json.loads(statefile.read_text())
        self.assertEqual(state["version"], 2)
        for key in ("baseline", "previous_hooks", "previous_local"):
            self.assertEqual(old[key], state[key])
        self.assertEqual(receipts, {p.name: p.read_bytes() for p in (root / "commits").iterdir()})
        self.assertEqual((task / "pending").read_text(), "still editing")
        hook = Path(state["hooks_path"]) / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 0\n")
        report = self.run_cmd(self.main, sys.executable, str(GUARD), "status", ok=False)
        self.assertFalse(json.loads(report.stdout)["hooks_match"])


if __name__ == "__main__":
    unittest.main()
