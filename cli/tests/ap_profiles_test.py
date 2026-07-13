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
        "workflow": {"mode": "dev", "profile": "auto", "completion": "push"},
        "concurrency": {"isolation": "worktree"},
        "project": {"name": "profile-test"},
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

    @staticmethod
    def record_closure(repo: Path, args: argparse.Namespace) -> Path:
        with mock.patch.object(ap, "_require_task_context", return_value={"task_id": args.task_id}):
            ap.cmd_record_closure(args)
        return repo / "docs" / "tasks" / "closures" / f"{args.task_id}.md"

    def test_docs_only_resolves_micro(self) -> None:
        repo, cfg = self.make_repo("docs/security-auth-notes.md")
        plan = self.plan(repo, cfg)
        self.assertEqual("micro", plan["profile"])
        self.assertEqual("changed", plan["selected_scope"])
        self.assertEqual("dev", plan["effective_mode"])
        self.assertEqual([], plan["recommended_agents"])
        self.assertEqual("main-only", plan["agent_plan"]["strategy"])

    def test_ordinary_code_resolves_standard(self) -> None:
        repo, cfg = self.make_repo("src/widget.py")
        (repo / "docs" / "tasks" / "evidence.jsonl").write_text("{}\n", encoding="utf-8")
        plan = self.plan(repo, cfg)
        self.assertEqual("standard", plan["profile"])
        self.assertEqual("changed", plan["selected_scope"])
        self.assertEqual("dev", plan["effective_mode"])
        self.assertEqual(["explorer", "fixer", "reviewer"], plan["recommended_agents"])
        agent_plan = plan["agent_plan"]
        self.assertEqual("orchestrated-subagents", agent_plan["strategy"])
        self.assertEqual(
            ["decomposition", "discovery", "design", "delivery", "closure"],
            [stage["id"] for stage in agent_plan["stages"]],
        )
        self.assertTrue(agent_plan["policies"]["one_writer_per_worktree"])
        self.assertEqual("explicit-non-overlapping", agent_plan["policies"]["path_ownership"])
        self.assertEqual(
            "integrate-before-dependent-start",
            agent_plan["policies"]["dependency_policy"],
        )
        self.assertEqual("owning-fixer", agent_plan["policies"]["review_feedback_owner"])
        self.assertEqual("diff-fingerprint", agent_plan["policies"]["review_binding"])
        self.assertEqual("main", agent_plan["policies"]["lifecycle_owner"])
        self.assertIn("owned_paths", agent_plan["assignment_contract"]["writer"])
        self.assertIn("diff_fingerprint", agent_plan["assignment_contract"]["reviewer"])
        self.assertIn("diff_fingerprint", agent_plan["result_contract"])
        delivery = next(stage for stage in agent_plan["stages"] if stage["id"] == "delivery")
        self.assertEqual("dependency-waves", delivery["mode"])
        self.assertEqual(
            ["implementation", "review", "gate-integrate"],
            [phase["id"] for phase in delivery["wave_phases"]],
        )
        self.assertIn("integrated", delivery["next_wave"])

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

    def test_high_risk_changes_keep_fast_dev_gate(self) -> None:
        repo, cfg = self.make_repo("migrations/001.sql")
        plan = self.plan(repo, cfg, requested_profile="micro", requested_mode="dev")
        self.assertEqual("high-risk", plan["profile"])
        self.assertEqual("changed", plan["selected_scope"])
        self.assertEqual("dev", plan["effective_mode"])
        self.assertTrue(plan["needs_dd"])
        self.assertIn("reviewer", plan["recommended_agents"])
        self.assertFalse(plan["needs_jenkins"])
        self.assertFalse(plan["needs_target"])

    def test_ui_api_discovery_roles_run_in_one_parallel_stage(self) -> None:
        repo, cfg = self.make_repo("src/api/settings-page.tsx")
        plan = self.plan(repo, cfg)
        discovery = next(stage for stage in plan["agent_plan"]["stages"] if stage["id"] == "discovery")
        self.assertEqual("parallel", discovery["mode"])
        self.assertEqual(
            ["explorer", "docs_researcher", "browser_debugger"],
            discovery["roles"],
        )
        flattened = [
            role
            for stage in plan["agent_plan"]["stages"]
            for role in stage["roles"]
            if role != "main"
        ]
        self.assertEqual(list(dict.fromkeys(flattened)), plan["recommended_agents"])

    def test_requested_verify_mode_is_rejected(self) -> None:
        repo, cfg = self.make_repo("src/widget.py")
        with self.assertRaises(APError):
            self.plan(repo, cfg, requested_mode="verify")

    def test_configured_high_risk_profile_cannot_be_downgraded_by_cli(self) -> None:
        cfg = base_config()
        cfg["workflow"] = {"mode": "dev", "profile": "high-risk", "completion": "push"}
        repo, cfg = self.make_repo("src/widget.py", cfg)
        plan = self.plan(repo, cfg, requested_profile="micro", requested_mode="dev")
        self.assertEqual("high-risk", plan["profile"])
        self.assertEqual("changed", plan["selected_scope"])
        self.assertEqual("dev", plan["effective_mode"])

    def test_doctor_rejects_configured_verify_mode(self) -> None:
        cfg = base_config()
        cfg["workflow"] = {"mode": "verify", "profile": "auto", "completion": "push"}
        repo, _ = self.make_repo("src/widget.py", cfg)
        with self.assertRaises(APError) as context:
            ap.cmd_doctor(argparse.Namespace(repo=str(repo)))
        self.assertIn("workflow.mode", str(context.exception))

    def test_configured_micro_profile_applies_to_ordinary_code(self) -> None:
        cfg = base_config()
        cfg["workflow"] = {"mode": "dev", "profile": "micro", "completion": "push"}
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

    def test_full_scope_rule_does_not_expand_local_gate(self) -> None:
        cfg = base_config()
        cfg["gate"]["rules"] = [{"name": "sensitive", "paths": ["src/sensitive/**"], "scope": "full"}]
        repo, cfg = self.make_repo("src/sensitive/value.py", cfg)
        plan = self.plan(repo, cfg, requested_scope="changed", requested_profile="micro", requested_mode="dev")
        self.assertEqual("micro", plan["profile"])
        self.assertEqual("changed", plan["selected_scope"])
        self.assertEqual("dev", plan["effective_mode"])

    def test_legacy_rule_commands_never_run_in_automatic_gate(self) -> None:
        cfg = base_config()
        repo, cfg = self.make_repo("src/sensitive/value.py", cfg)
        quick_marker = repo / "quick-ran"
        full_marker = repo / "full-ran"
        build_marker = repo / "build-ran"
        cfg["commands"] = {
            "gate_changed": f"touch {quick_marker}",
            "gate_full": f"touch {full_marker}",
            "build": f"touch {build_marker}",
        }
        cfg["gate"]["rules"] = [
            {
                "name": "legacy-heavy-rule",
                "paths": ["src/sensitive/**"],
                "scope": "full",
                "commands": ["gate_full", "build"],
            }
        ]
        self.write_config(repo, cfg)

        ap.cmd_light_gate(
            argparse.Namespace(
                repo=str(repo),
                scope="changed",
                profile="",
                mode="dev",
                base="",
                explain=False,
            )
        )

        self.assertTrue(quick_marker.exists())
        self.assertFalse(full_marker.exists())
        self.assertFalse(build_marker.exists())

    def test_classify_never_recommends_a_second_gate_or_structure_scan(self) -> None:
        repo, _ = self.make_repo("src/widget.py")
        with mock.patch.object(ap, "_record_evidence"):
            with mock.patch("builtins.print") as printed:
                ap.cmd_classify(
                    argparse.Namespace(
                        repo=str(repo),
                        scope="auto",
                        profile="",
                        mode="dev",
                        base="",
                        json=False,
                    )
                )
        rendered = "\n".join(" ".join(map(str, call.args)) for call in printed.call_args_list)
        self.assertNotIn("light-gate", rendered)
        self.assertNotIn("structure-check", rendered)

    def test_custom_full_on_path_does_not_expand_local_gate(self) -> None:
        cfg = base_config()
        cfg["gate"]["full_on"] = {"paths": ["src/sensitive/**"]}
        repo, cfg = self.make_repo("src/sensitive/value.py", cfg)
        plan = self.plan(repo, cfg, requested_scope="changed", requested_profile="micro", requested_mode="dev")
        self.assertEqual("micro", plan["profile"])
        self.assertEqual("changed", plan["selected_scope"])
        self.assertEqual("dev", plan["effective_mode"])

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

    def test_doctor_rejects_legacy_isolation(self) -> None:
        cfg = base_config()
        cfg["concurrency"]["isolation"] = "legacy"
        repo, _ = self.make_repo(config=cfg)
        with self.assertRaises(APError) as context:
            ap.cmd_doctor(argparse.Namespace(repo=str(repo)))
        self.assertIn("must be worktree", str(context.exception))

    def test_doctor_requires_one_fast_gate_for_every_profile(self) -> None:
        for profile in ["micro", "standard", "high-risk", "auto"]:
            with self.subTest(profile=profile):
                cfg = base_config()
                cfg["workflow"]["profile"] = profile
                cfg["commands"] = {"gate_standard": "true", "gate_full": "true"}
                repo, _ = self.make_repo(config=cfg)
                with self.assertRaises(APError) as context:
                    ap.cmd_doctor(argparse.Namespace(repo=str(repo)))
                self.assertIn("fast gate command", str(context.exception))

    def test_doctor_requires_direct_access_password_even_with_env_reference(self) -> None:
        cfg = base_config()
        cfg["access"]["gitlab"]["password"] = ""
        cfg["access"]["gitlab"]["password_env"] = "GITLAB_PASSWORD"
        repo, _ = self.make_repo(config=cfg)
        with self.assertRaises(APError) as context:
            ap.cmd_doctor(argparse.Namespace(repo=str(repo)))
        self.assertIn("access.gitlab.password", str(context.exception))

    def test_doctor_rejects_quoted_nullish_access_placeholders(self) -> None:
        for placeholder in ["NULL", "~"]:
            with self.subTest(placeholder=placeholder):
                cfg = base_config()
                cfg["access"]["gitlab"]["password"] = placeholder
                repo, _ = self.make_repo(config=cfg)
                with self.assertRaises(APError) as context:
                    ap.cmd_doctor(argparse.Namespace(repo=str(repo)))
                self.assertIn("access.gitlab.password", str(context.exception))

    def test_doctor_rejects_non_string_access_values(self) -> None:
        for value in [False, 0]:
            with self.subTest(value=value):
                cfg = base_config()
                cfg["access"]["gitlab"]["password"] = value
                repo, _ = self.make_repo(config=cfg)
                with self.assertRaises(APError) as context:
                    ap.cmd_doctor(argparse.Namespace(repo=str(repo)))
                self.assertIn("access.gitlab.password", str(context.exception))

    def test_doctor_validates_access_url_shape_without_network(self) -> None:
        cfg = base_config()
        cfg["access"]["nexus"]["frontend"]["url"] = "nexus.local"
        repo, _ = self.make_repo(config=cfg)
        with self.assertRaises(APError) as context:
            ap.cmd_doctor(argparse.Namespace(repo=str(repo)))
        self.assertIn("valid http/https URL", str(context.exception))

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

    def test_dev_closure_rejects_owner_acceptance_pass(self) -> None:
        with self.assertRaises(APError):
            ap._validate_closure_result("dev", "PASS")

    def test_manual_closure_infers_one_of_the_three_effective_profiles(self) -> None:
        repo, _ = self.make_repo("src/widget.py")
        closure_path = self.record_closure(repo, self.closure_args(repo, result="DEV-CLOSED"))
        closure = closure_path.read_text(encoding="utf-8")
        self.assertIn("- Effective Profile: standard", closure)
        self.assertNotIn("(not recorded)", closure)

    def test_manual_closure_uses_dev_closed_for_high_risk_work(self) -> None:
        repo, _ = self.make_repo("migrations/001.sql")
        closure_path = self.record_closure(repo, self.closure_args(repo, result="DEV-CLOSED"))
        closure = closure_path.read_text(encoding="utf-8")
        self.assertIn("- Effective Profile: high-risk", closure)

    def test_manual_pass_is_outside_automatic_coding_closure(self) -> None:
        repo, _ = self.make_repo("src/widget.py")
        with self.assertRaises(APError) as context:
            self.record_closure(
                repo,
                self.closure_args(repo, result="PASS", profile="high-risk", verification=[])
            )
        self.assertIn("owner acceptance", str(context.exception))

    def test_manual_closure_uses_commit_diff_after_high_risk_change_is_committed(self) -> None:
        repo, _ = self.make_repo("migrations/001.sql")
        run(repo, "git", "add", "-A")
        run(repo, "git", "commit", "-qm", "database migration")

        closure_path = self.record_closure(
            repo,
            self.closure_args(
                repo,
                result="DEV-CLOSED",
                verification=["fast changed gate passed"],
            )
        )
        closure = closure_path.read_text(encoding="utf-8")
        self.assertIn("- Effective Profile: high-risk", closure)


if __name__ == "__main__":
    unittest.main()
