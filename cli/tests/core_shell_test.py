#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "src" / "auto-coding-skill" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import core  # noqa: E402


class RunShellTests(unittest.TestCase):
    def test_run_shell_uses_non_login_bash_and_inherits_environment(self) -> None:
        process = mock.Mock()
        process.wait.return_value = 0
        cwd = Path("/tmp/run-shell-test")
        with mock.patch.object(core.subprocess, "Popen", return_value=process) as popen:
            core.run_shell("sentinel", cwd=cwd)

        popen.assert_called_once_with(
            ["bash", "-c", "sentinel"],
            cwd=str(cwd),
            text=True,
            start_new_session=True,
        )

    def test_run_shell_preserves_caller_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="autocoding-shell-") as temp_name:
            root = Path(temp_name)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            sentinel = bin_dir / "path-sentinel"
            sentinel.write_text("#!/bin/sh\nprintf inherited > \"$1\"\n", encoding="utf-8")
            sentinel.chmod(0o755)
            result = root / "result.txt"
            profile_marker = root / "login-profile-ran"
            (root / ".bash_profile").write_text(
                f"export PATH=/usr/bin:/bin\n/usr/bin/touch '{profile_marker}'\n",
                encoding="utf-8",
            )
            inherited_path = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"
            with mock.patch.dict(
                os.environ,
                {"HOME": str(root), "PATH": inherited_path},
                clear=False,
            ):
                core.run_shell(f"path-sentinel '{result}'", cwd=root, timeout_s=5)

            self.assertEqual("inherited", result.read_text(encoding="utf-8"))
            self.assertFalse(profile_marker.exists())

    def test_run_shell_timeout_terminates_then_kills_process_group(self) -> None:
        process = mock.Mock(pid=4321)
        process.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="slow", timeout=1),
            subprocess.TimeoutExpired(cmd="slow", timeout=2),
            0,
        ]
        with (
            mock.patch.object(core.subprocess, "Popen", return_value=process),
            mock.patch.object(core.os, "killpg") as killpg,
        ):
            with self.assertRaises(core.APError) as context:
                core.run_shell("slow", timeout_s=1)

        self.assertIn("timed out after 1.0s", str(context.exception))
        self.assertEqual(
            [mock.call(4321, signal.SIGTERM), mock.call(4321, signal.SIGKILL)],
            killpg.call_args_list,
        )
        self.assertEqual(3, process.wait.call_count)


if __name__ == "__main__":
    unittest.main()
