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


class ProjectConfigResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="autocoding-config-")
        self.repo = Path(self.temporary.name)
        (self.repo / "docs" / "project").mkdir(parents=True)
        self.write_managed(
            """workflow:
  skill_version: "4.3.7"
  mode: dev
  profile: auto
  completion: push
project:
  name: sample
commands:
  project_fast: npm test
validation:
  enabled: true
  retries: 3
  routes:
    - paths: [src/**]
access:
  project:
    password: managed-secret
"""
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_managed(self, frontmatter: str, body: str = "# Managed\n") -> None:
        (self.repo / core.MANAGED_CONFIG_RELATIVE_PATH).write_text(
            f"---\n{frontmatter.rstrip()}\n---\n{body}",
            encoding="utf-8",
        )

    def write_overlay(self, overrides: str, schema: str = core.PROJECT_CONFIG_SCHEMA) -> None:
        (self.repo / core.PROJECT_CONFIG_OVERLAY_RELATIVE_PATH).write_text(
            f"schema: {schema}\noverrides:\n{overrides}",
            encoding="utf-8",
        )

    def assert_overlay_error(self, expected: str) -> None:
        with self.assertRaises(core.APError) as context:
            core.load_effective_config(self.repo)
        self.assertIn(expected, str(context.exception))

    def test_missing_overlay_keeps_managed_config_and_find_config_compatibility(self) -> None:
        effective = core.load_effective_config(self.repo)

        self.assertEqual("sample", effective["project"]["name"])
        self.assertEqual("4.3.7", effective["workflow"]["skill_version"])
        self.assertEqual(self.repo / "docs" / "ENGINEERING.md", core.find_config(self.repo))
        self.assertEqual({}, core.load_project_overrides(self.repo))

    def test_recursive_merge_treats_falsy_scalars_and_empty_lists_as_authoritative(self) -> None:
        self.write_overlay(
            """  workflow:
    profile: project-profile
  project:
    name: project-owned
  commands:
    project_fast: ''
  validation:
    enabled: false
    retries: 0
    routes: []
  added:
    nested: value
"""
        )

        effective = core.load_effective_config(self.repo)

        self.assertEqual("4.3.7", effective["workflow"]["skill_version"])
        self.assertEqual("dev", effective["workflow"]["mode"])
        self.assertEqual("project-profile", effective["workflow"]["profile"])
        self.assertEqual("push", effective["workflow"]["completion"])
        self.assertEqual("project-owned", effective["project"]["name"])
        self.assertEqual("", effective["commands"]["project_fast"])
        self.assertIs(effective["validation"]["enabled"], False)
        self.assertEqual(0, effective["validation"]["retries"])
        self.assertEqual([], effective["validation"]["routes"])
        self.assertEqual({"nested": "value"}, effective["added"])

    def test_overlay_payload_parser_matches_file_loader(self) -> None:
        self.write_overlay("  project:\n    name: project-owned\n  validation:\n    routes: []\n")
        payload = (self.repo / core.PROJECT_CONFIG_OVERLAY_RELATIVE_PATH).read_bytes()

        self.assertEqual(
            core.load_project_overrides(self.repo),
            core.parse_project_overrides_payload(payload),
        )

    def test_overlay_payload_parser_and_loader_both_reject_invalid_wrapper(self) -> None:
        payload = (
            f"schema: {core.PROJECT_CONFIG_SCHEMA}\n"
            "overrides: {}\n"
            "project: {}\n"
        ).encode("utf-8")
        (self.repo / core.PROJECT_CONFIG_OVERLAY_RELATIVE_PATH).write_bytes(payload)

        for label, load in (
            ("payload", lambda: core.parse_project_overrides_payload(payload)),
            ("file", lambda: core.load_project_overrides(self.repo)),
        ):
            with self.subTest(source=label):
                with self.assertRaisesRegex(core.APError, "unsupported top-level wrapper"):
                    load()

    def test_merge_does_not_mutate_either_layer(self) -> None:
        defaults = {"nested": {"managed": True}, "items": ["managed"]}
        overrides = {"nested": {"project": True}, "items": []}

        effective = core.merge_project_config(defaults, overrides)
        effective["nested"]["managed"] = False

        self.assertEqual({"nested": {"managed": True}, "items": ["managed"]}, defaults)
        self.assertEqual({"nested": {"project": True}, "items": []}, overrides)

    def test_rejects_null_values_in_both_layers(self) -> None:
        self.write_overlay("  commands:\n    project_fast:\n")
        self.assert_overlay_error("must not contain null")

        (self.repo / core.PROJECT_CONFIG_OVERLAY_RELATIVE_PATH).unlink()
        self.write_managed("workflow:\n  skill_version:\n")
        self.assert_overlay_error("must not contain null")

    def test_rejects_duplicate_keys_in_both_layers(self) -> None:
        self.write_overlay("  project:\n    name: one\n    name: two\n")
        self.assert_overlay_error("duplicate YAML keys")

        (self.repo / core.PROJECT_CONFIG_OVERLAY_RELATIVE_PATH).unlink()
        self.write_managed("project:\n  name: one\n  name: two\n")
        self.assert_overlay_error("duplicate YAML keys")

    def test_rejects_yaml_anchors_aliases_and_merge_keys(self) -> None:
        self.write_overlay("  project: &project\n    name: sample\n  copy: *project\n")
        self.assert_overlay_error("anchors or aliases")

        self.write_overlay("  project:\n    <<: {name: sample}\n")
        self.assert_overlay_error("merge keys")

    def test_rejects_unknown_wrapper_or_schema(self) -> None:
        overlay = self.repo / core.PROJECT_CONFIG_OVERLAY_RELATIVE_PATH
        overlay.write_text(
            f"schema: {core.PROJECT_CONFIG_SCHEMA}\noverrides: {{}}\nproject: {{}}\n",
            encoding="utf-8",
        )
        self.assert_overlay_error("unsupported top-level wrapper")

        self.write_overlay("  project: {}\n", schema="unexpected/v1")
        self.assert_overlay_error("schema is unsupported")

    def test_rejects_managed_workflow_fields_and_whole_workflow_replacement(self) -> None:
        for field, value in (
            ("skill_version", '"99.0.0"'),
            ("mode", "custom"),
            ("completion", "local-only"),
        ):
            with self.subTest(field=field):
                self.write_overlay(f"  workflow:\n    {field}: {value}\n")
                self.assert_overlay_error("cannot override managed workflow fields")

        self.write_overlay("  workflow: disabled\n")
        self.assert_overlay_error("cannot override managed workflow fields")

    @unittest.skipIf(os.name == "nt", "symlink setup is platform-dependent")
    def test_rejects_overlay_file_and_parent_symlinks(self) -> None:
        overlay = self.repo / core.PROJECT_CONFIG_OVERLAY_RELATIVE_PATH
        outside = self.repo / "outside.yaml"
        outside.write_text(
            f"schema: {core.PROJECT_CONFIG_SCHEMA}\noverrides: {{}}\n",
            encoding="utf-8",
        )
        overlay.symlink_to(outside)
        self.assert_overlay_error("regular non-symlink file")

        overlay.unlink()
        project_dir = self.repo / "docs" / "project"
        project_dir.rmdir()
        outside_dir = self.repo / "outside-project"
        outside_dir.mkdir()
        (outside_dir / "auto-coding-skill.yaml").write_text(
            f"schema: {core.PROJECT_CONFIG_SCHEMA}\noverrides: {{}}\n",
            encoding="utf-8",
        )
        project_dir.symlink_to(outside_dir, target_is_directory=True)
        self.assert_overlay_error("parent must be a real directory")

    def test_bounds_overlay_and_frontmatter_reads(self) -> None:
        overlay = self.repo / core.PROJECT_CONFIG_OVERLAY_RELATIVE_PATH
        overlay.write_bytes(b"x" * (core.PROJECT_CONFIG_OVERLAY_MAX_BYTES + 1))
        self.assert_overlay_error("exceeds its size limit")

        overlay.unlink()
        huge = "x" * core.MANAGED_CONFIG_FRONTMATTER_MAX_BYTES
        self.write_managed(f"project:\n  name: {huge}\n")
        self.assert_overlay_error("bounded YAML frontmatter")

    def test_rejects_excessive_yaml_nesting(self) -> None:
        indent = "  "
        lines = []
        for index in range(core.PROJECT_CONFIG_MAX_YAML_DEPTH + 1):
            lines.append(f"{indent}level{index}:")
            indent += "  "
        lines.append(f"{indent}value: bounded")
        self.write_overlay("\n".join(lines) + "\n")

        self.assert_overlay_error("YAML complexity limit")

    def test_large_managed_body_is_not_part_of_frontmatter_bound(self) -> None:
        self.write_managed(
            'workflow:\n  skill_version: "4.3.7"\n',
            body="x" * (core.MANAGED_CONFIG_FRONTMATTER_MAX_BYTES + 1),
        )

        self.assertEqual("4.3.7", core.load_effective_config(self.repo)["workflow"]["skill_version"])

    def test_yaml_failure_does_not_echo_content_or_absolute_path(self) -> None:
        secret = "NEVER_ECHO_THIS_SECRET"
        overlay = self.repo / core.PROJECT_CONFIG_OVERLAY_RELATIVE_PATH
        overlay.write_text(
            f"schema: {core.PROJECT_CONFIG_SCHEMA}\noverrides:\n  access: [{secret}\n",
            encoding="utf-8",
        )

        with self.assertRaises(core.APError) as context:
            core.load_effective_config(self.repo)

        message = str(context.exception)
        self.assertNotIn(secret, message)
        self.assertNotIn(str(self.repo), message)

    def test_yaml_constructor_failures_are_sanitized_as_aperror(self) -> None:
        cases = (
            ("bool", "!!bool BOOL_SECRET_SENTINEL", "BOOL_SECRET_SENTINEL"),
            ("int", "!!int INT_SECRET_SENTINEL", "INT_SECRET_SENTINEL"),
            ("huge-int", "9" * 5000, "9" * 64),
        )
        for label, value, forbidden in cases:
            with self.subTest(case=label):
                self.write_overlay(f"  value: {value}\n")
                with self.assertRaises(core.APError) as context:
                    core.load_effective_config(self.repo)

                message = str(context.exception)
                self.assertIn("contains invalid YAML", message)
                self.assertNotIn(forbidden, message)

    def test_rejects_surrogate_nul_and_escape_strings(self) -> None:
        cases = (
            ("surrogate", '"\\uD800"', "invalid Unicode string"),
            ("nul", '"\\0"', "unsupported control character"),
            ("escape", '"\\u001b[31m"', "unsupported control character"),
        )
        for label, value, expected in cases:
            with self.subTest(case=label):
                self.write_overlay(f"  value: {value}\n")
                self.assert_overlay_error(expected)


if __name__ == "__main__":
    unittest.main()
