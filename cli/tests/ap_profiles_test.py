#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "cli" / "assets" / "skill" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import ap  # noqa: E402
from core import APError  # noqa: E402


def run(repo: Path, *args: str) -> None:
    subprocess.run(list(args), cwd=repo, check=True, text=True, capture_output=True)


def base_config() -> dict:
    return {
        "workflow": {"mode": "dev", "profile": "auto"},
        "project": {"name": "profile-test"},
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
        "verification": {"target_env_required": False, "jenkins_required": False},
        "docs": {
            "taskbook": "docs/tasks/taskbook.md",
            "closure_log": "docs/tasks/closure-log.md",
            "evidence_log": "docs/tasks/evidence.jsonl",
            "design_dir": "docs/design",
            "ledger_check_enabled": True,
        },
    }


class AutoCodingProfileTests(unittest.TestCase):
    def make_repo(self, change_path: str | None = None, config: dict | None = None) -> tuple[Path, dict]:
        temp = tempfile.TemporaryDirectory(prefix="autocoding-profile-")
        self.addCleanup(temp.cleanup)
        repo = Path(temp.name)
        cfg = config or base_config()
        run(repo, "git", "init", "-q")
        run(repo, "git", "config", "user.email", "test@example.com")
        run(repo, "git", "config", "user.name", "Auto Coding Test")
        self.write_config(repo, cfg)
        (repo / "docs" / "tasks").mkdir(parents=True, exist_ok=True)
        (repo / "docs" / "tasks" / "taskbook.md").write_text("# Taskbook\n", encoding="utf-8")
        (repo / "docs" / "tasks" / "closure-log.md").write_text("# Closure Log\n", encoding="utf-8")
        run(repo, "git", "add", "-A")
        run(repo, "git", "commit", "-qm", "baseline")
        if change_path:
            target = repo / change_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("change\n", encoding="utf-8")
        return repo, cfg

    @staticmethod
    def write_config(repo: Path, cfg: dict) -> None:
        path = repo / "docs" / "ENGINEERING.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\n" + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False) + "---\n# Engineering\n",
            encoding="utf-8",
        )

    def plan(self, repo: Path, cfg: dict, **kwargs: str) -> dict:
        return ap._resolve_execution_plan(cfg, repo, **kwargs)

    @staticmethod
    def commit_args(
        repo: Path,
        *,
        profile: str,
        mode: str,
        result: str,
    ) -> argparse.Namespace:
        return argparse.Namespace(
            repo=str(repo),
            task_id="T001",
            title="profile closure",
            msg="T001: profile closure",
            mode=mode,
            profile=profile,
            require_light_gate=False,
            require_runtime_health=False,
            require_jenkins=False,
            require_matrix=False,
            record_closure=False,
            job_name=None,
            job_url=None,
            multibranch_root_job=None,
            branch_name=None,
            build_number=None,
            max_builds=20,
            timeout_sec=1,
            poll_sec=1,
            allow_no_deploy=False,
            backend_path=None,
            frontend_path=None,
            backend_basic_auth=False,
            frontend_basic_auth=False,
            jenkins_build=None,
            target_env=None,
            verification=None,
            structure_check=None,
            result=result,
            follow_up=None,
            initial_commit=None,
            jenkins_failure=None,
            fix_commit=None,
        )

    @staticmethod
    def closure_args(
        repo: Path,
        *,
        result: str,
        profile: str = "",
        verification: list[str] | None = None,
    ) -> argparse.Namespace:
        return argparse.Namespace(
            repo=str(repo),
            task_id="T001",
            title="manual closure",
            commit="HEAD",
            jenkins=None,
            target_env=None,
            verification=["manual evidence"] if verification is None else verification,
            profile=profile,
            structure_check="passed",
            result=result,
            follow_up=None,
            initial_commit=None,
            jenkins_failure=None,
            fix_commit=None,
        )

    def test_docs_only_resolves_micro(self) -> None:
        repo, cfg = self.make_repo("docs/security-auth-notes.md")
        plan = self.plan(repo, cfg)
        self.assertEqual("micro", plan["profile"])
        self.assertEqual("changed", plan["selected_scope"])
        self.assertEqual("dev", plan["effective_mode"])
        self.assertEqual([], plan["recommended_agents"])

    def test_ordinary_code_resolves_standard(self) -> None:
        repo, cfg = self.make_repo("src/widget.py")
        (repo / "docs" / "tasks" / "evidence.jsonl").write_text("{}\n", encoding="utf-8")
        plan = self.plan(repo, cfg)
        self.assertEqual("standard", plan["profile"])
        self.assertEqual("standard", plan["selected_scope"])
        self.assertEqual("dev", plan["effective_mode"])
        self.assertEqual(["explorer", "fixer"], plan["recommended_agents"])

    def test_test_only_change_resolves_micro(self) -> None:
        repo, cfg = self.make_repo("tests/widget_test.py")
        (repo / "docs" / "tasks" / "evidence.jsonl").write_text("{}\n", encoding="utf-8")
        plan = self.plan(repo, cfg)
        self.assertEqual("micro", plan["profile"])
        self.assertEqual("changed", plan["selected_scope"])

    def test_sensitive_named_test_only_changes_stay_micro(self) -> None:
        for path in ["tests/auth_test.py", "tests/payment_spec.ts", "tests/upload_test.py"]:
            with self.subTest(path=path):
                repo, cfg = self.make_repo(path)
                plan = self.plan(repo, cfg)
                self.assertEqual("micro", plan["profile"])
                self.assertEqual("changed", plan["selected_scope"])
                self.assertEqual("dev", plan["effective_mode"])

    def test_high_risk_is_full_verify_and_cannot_be_downgraded(self) -> None:
        repo, cfg = self.make_repo("migrations/001.sql")
        plan = self.plan(repo, cfg, requested_profile="micro", requested_mode="dev")
        self.assertEqual("high-risk", plan["profile"])
        self.assertEqual("full", plan["selected_scope"])
        self.assertEqual("verify", plan["effective_mode"])
        self.assertTrue(plan["needs_dd"])
        self.assertIn("reviewer", plan["recommended_agents"])

    def test_verify_mode_forces_high_risk_full(self) -> None:
        repo, cfg = self.make_repo("src/widget.py")
        plan = self.plan(repo, cfg, requested_mode="verify")
        self.assertEqual("high-risk", plan["profile"])
        self.assertEqual("full", plan["selected_scope"])
        self.assertEqual("verify", plan["effective_mode"])

    def test_configured_high_risk_profile_cannot_be_downgraded_by_cli(self) -> None:
        cfg = base_config()
        cfg["workflow"] = {"mode": "dev", "profile": "high-risk"}
        repo, cfg = self.make_repo("src/widget.py", cfg)
        plan = self.plan(repo, cfg, requested_profile="micro", requested_mode="dev")
        self.assertEqual("high-risk", plan["profile"])
        self.assertEqual("full", plan["selected_scope"])
        self.assertEqual("verify", plan["effective_mode"])

    def test_configured_verify_mode_cannot_be_downgraded_by_cli(self) -> None:
        cfg = base_config()
        cfg["workflow"] = {"mode": "verify", "profile": "auto"}
        repo, cfg = self.make_repo("src/widget.py", cfg)
        plan = self.plan(repo, cfg, requested_profile="micro", requested_mode="dev")
        self.assertEqual("high-risk", plan["profile"])
        self.assertEqual("full", plan["selected_scope"])
        self.assertEqual("verify", plan["effective_mode"])

    def test_configured_micro_profile_applies_to_ordinary_code(self) -> None:
        cfg = base_config()
        cfg["workflow"] = {"mode": "dev", "profile": "micro"}
        repo, cfg = self.make_repo("src/widget.py", cfg)
        plan = self.plan(repo, cfg)
        self.assertEqual("micro", plan["profile"])
        self.assertEqual("changed", plan["selected_scope"])
        self.assertEqual("dev", plan["effective_mode"])

    def test_rule_can_raise_profile(self) -> None:
        cfg = base_config()
        cfg["gate"]["rules"] = [{"name": "sensitive", "paths": ["src/special/**"], "profile": "high-risk"}]
        repo, cfg = self.make_repo("src/special/value.py", cfg)
        plan = self.plan(repo, cfg)
        self.assertEqual("high-risk", plan["profile"])
        self.assertIn("matched gate rule with profile=high-risk", plan["profile_reasons"])

    def test_full_scope_rule_cannot_be_bypassed_by_explicit_scope(self) -> None:
        cfg = base_config()
        cfg["gate"]["rules"] = [{"name": "sensitive", "paths": ["src/sensitive/**"], "scope": "full"}]
        repo, cfg = self.make_repo("src/sensitive/value.py", cfg)
        plan = self.plan(repo, cfg, requested_scope="changed", requested_profile="micro", requested_mode="dev")
        self.assertEqual("high-risk", plan["profile"])
        self.assertEqual("full", plan["selected_scope"])
        self.assertEqual("verify", plan["effective_mode"])

    def test_custom_full_on_path_cannot_be_bypassed_by_explicit_scope(self) -> None:
        cfg = base_config()
        cfg["gate"]["full_on"] = {"paths": ["src/sensitive/**"]}
        repo, cfg = self.make_repo("src/sensitive/value.py", cfg)
        plan = self.plan(repo, cfg, requested_scope="changed", requested_profile="micro", requested_mode="dev")
        self.assertEqual("high-risk", plan["profile"])
        self.assertEqual("full", plan["selected_scope"])
        self.assertEqual("verify", plan["effective_mode"])

    def test_full_gate_never_falls_back_to_light(self) -> None:
        repo, _ = self.make_repo()
        marker = repo / "light-ran"
        cfg = {"commands": {"light_gate": f"touch {marker}"}}
        with self.assertRaises(APError):
            ap._run_full_gate(repo, cfg)
        self.assertFalse(marker.exists())

        cfg = {"commands": {"gate_full": f"touch {marker}"}}
        self.assertEqual(["gate_full"], ap._run_full_gate(repo, cfg))
        self.assertTrue(marker.exists())

    def test_structure_defaults_to_advisory_until_explicitly_blocking(self) -> None:
        cfg = base_config()
        cfg["structure"] = {
            "enabled": True,
            "max_file_lines_warn": 3,
            "max_file_lines_block": 5,
            "max_function_lines_warn": 0,
            "max_added_lines_to_large_file": 2,
            "layer_rules": {"enabled": False},
        }
        repo, cfg = self.make_repo("src/large.py", cfg)
        (repo / "src" / "large.py").write_text("\n".join(f"line {i}" for i in range(10)), encoding="utf-8")
        args = argparse.Namespace(repo=str(repo), scope="changed", base="", json=False)
        ap.cmd_structure_check(args)

        cfg["structure"]["enforcement"] = "blocking"
        self.write_config(repo, cfg)
        with self.assertRaises(APError):
            ap.cmd_structure_check(args)

    def test_doctor_validates_profile_values(self) -> None:
        cfg = base_config()
        cfg["workflow"]["profile"] = "extreme"
        cfg["gate"]["rules"] = [{"paths": ["src/**"], "profile": "unsafe"}]
        repo, _ = self.make_repo(config=cfg)
        with self.assertRaises(APError) as context:
            ap.cmd_doctor(argparse.Namespace(repo=str(repo)))
        message = str(context.exception)
        self.assertIn("workflow.profile", message)
        self.assertIn("gate.rules[0].profile", message)

    def test_doctor_rejects_invalid_rule_scope(self) -> None:
        cfg = base_config()
        cfg["docs"]["ledger_check_enabled"] = False
        cfg["gate"]["rules"] = [{"paths": ["src/**"], "scope": "ful"}]
        repo, _ = self.make_repo(config=cfg)
        with self.assertRaises(APError) as context:
            ap.cmd_doctor(argparse.Namespace(repo=str(repo)))
        self.assertIn("gate.rules[0].scope", str(context.exception))

    def test_doctor_requires_a_gate_executable_for_the_configured_profile(self) -> None:
        cases = [
            ("micro", {"gate_standard": "true"}, "gate_changed", "tests/widget_test.py"),
            ("standard", {"gate_changed": "true"}, "gate_standard", None),
            ("auto", {"gate_changed": "true"}, "gate_standard", None),
        ]
        for profile, commands, expected_field, change_path in cases:
            with self.subTest(profile=profile):
                cfg = base_config()
                cfg["workflow"]["profile"] = profile
                cfg["commands"] = commands
                cfg["docs"]["ledger_check_enabled"] = False
                repo, _ = self.make_repo(change_path, config=cfg)
                with self.assertRaises(APError) as context:
                    ap.cmd_doctor(argparse.Namespace(repo=str(repo)))
                self.assertIn(expected_field, str(context.exception))

    def test_doctor_accepts_health_only_target_verification(self) -> None:
        cfg = base_config()
        cfg["verification"]["target_env_required"] = True
        cfg["target_env"] = {
            "health_base_url": "https://example.test",
            "health_path": "/health",
        }
        repo, _ = self.make_repo(config=cfg)
        ap.cmd_doctor(argparse.Namespace(repo=str(repo)))

    def test_api_docs_required_false_is_an_authoritative_opt_out(self) -> None:
        cfg = base_config()
        cfg["docs"].update(
            {
                "api_docs_required": False,
                "api_doc": "docs/interfaces/api.md",
                "api_change_log": "docs/interfaces/api-change-log.md",
            }
        )
        repo, _ = self.make_repo(config=cfg)
        api_doc = repo / "docs" / "interfaces" / "api.md"
        api_doc.parent.mkdir(parents=True, exist_ok=True)
        api_doc.write_text("# Existing API\n", encoding="utf-8")
        ap.cmd_doctor(argparse.Namespace(repo=str(repo)))
        ap.cmd_verify_api_docs(argparse.Namespace(repo=str(repo)))

    def test_commit_push_rejects_result_incompatible_with_effective_mode(self) -> None:
        cases = [
            ("micro", "dev", "PASS"),
            ("high-risk", "verify", "DEV-CLOSED"),
        ]
        for profile, mode, result in cases:
            with self.subTest(profile=profile, mode=mode, result=result):
                repo, cfg = self.make_repo("src/widget.py")
                plan = {
                    "profile": profile,
                    "effective_mode": mode,
                    "selected_scope": "full" if mode == "verify" else "changed",
                }
                fake_run_result = subprocess.CompletedProcess([], 0, stdout="changed\n", stderr="")
                with (
                    mock.patch.object(ap, "ensure_git_repo"),
                    mock.patch.object(ap, "cmd_doctor"),
                    mock.patch.object(ap, "_load_cfg", return_value=cfg),
                    mock.patch.object(ap, "_resolve_execution_plan", return_value=plan),
                    mock.patch.object(ap, "cmd_light_gate"),
                    mock.patch.object(ap, "_cleanup_generated_noise"),
                    mock.patch.object(ap, "run", return_value=fake_run_result),
                ):
                    with self.assertRaises(APError):
                        ap.cmd_commit_push(
                            self.commit_args(repo, profile=profile, mode=mode, result=result)
                        )

    def test_manual_closure_infers_one_of_the_three_effective_profiles(self) -> None:
        repo, _ = self.make_repo("src/widget.py")
        ap.cmd_record_closure(self.closure_args(repo, result="DEV-CLOSED"))
        closure = (repo / "docs" / "tasks" / "closure-log.md").read_text(encoding="utf-8")
        self.assertIn("- Effective Profile: standard", closure)
        self.assertNotIn("(not recorded)", closure)

    def test_manual_closure_rejects_result_incompatible_with_inferred_mode(self) -> None:
        cases = [
            ("src/widget.py", "PASS"),
            ("migrations/001.sql", "DEV-CLOSED"),
        ]
        for path, result in cases:
            with self.subTest(path=path, result=result):
                repo, _ = self.make_repo(path)
                with self.assertRaises(APError):
                    ap.cmd_record_closure(self.closure_args(repo, result=result))

    def test_manual_pass_requires_concrete_verification_evidence(self) -> None:
        repo, _ = self.make_repo("src/widget.py")
        with self.assertRaises(APError) as context:
            ap.cmd_record_closure(
                self.closure_args(repo, result="PASS", profile="high-risk", verification=[])
            )
        self.assertIn("--verification", str(context.exception))

    def test_manual_closure_uses_commit_diff_after_high_risk_change_is_committed(self) -> None:
        repo, _ = self.make_repo("migrations/001.sql")
        run(repo, "git", "add", "-A")
        run(repo, "git", "commit", "-qm", "database migration")

        with self.assertRaises(APError):
            ap.cmd_record_closure(self.closure_args(repo, result="DEV-CLOSED"))

        ap.cmd_record_closure(
            self.closure_args(
                repo,
                result="PASS",
                verification=["gate_full: integration suite passed"],
            )
        )
        closure = (repo / "docs" / "tasks" / "closure-log.md").read_text(encoding="utf-8")
        self.assertIn("- Effective Profile: high-risk", closure)


if __name__ == "__main__":
    unittest.main()
