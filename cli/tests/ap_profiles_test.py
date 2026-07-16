#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "src" / "auto-coding-skill" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import ap  # noqa: E402
from core import APError  # noqa: E402


def run(repo: Path, *args: str) -> None:
    subprocess.run(list(args), cwd=repo, check=True, text=True, capture_output=True)


def base_config() -> dict:
    return {
        "workflow": {"mode": "dev", "profile": "auto", "completion": "push"},
        "concurrency": {"isolation": "adaptive"},
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
            "fallback_scope": "changed",
            "full_on_unknown": False,
            "no_change_scope": "changed",
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
    @staticmethod
    def workflow_policy(*, fragments: list[dict] | None = None) -> dict:
        return {
            "schema_version": 1,
            "managed_versions": {"agents": "3.0.2", "engineering": "3.0.2"},
            "known_official_engineering_body_sha256": [],
            "known_official_fragments": fragments or [],
            "conflict_rules": [
                {
                    "id": "mandatory-full",
                    "paths": ["AGENTS.md", "docs/ENGINEERING.md"],
                    "pattern": r"^.*must run the full gate.*$",
                    "flags": "im",
                    "message": "full gate is not automatic",
                }
            ],
            "dependency_recovery": {
                "allowed_gate": "gate_changed",
                "requires_locked_dependency": True,
                "retry_same_gate_only": True,
                "forbid_full_gate_recovery": True,
            },
        }

    @staticmethod
    def reviewer_assignment(**overrides: object) -> dict:
        assignment = {
            "contract_version": 1,
            "node_id": "reviewer-1",
            "task_id": "T001",
            "role": "reviewer",
            "base_sha": "HEAD",
            "scope": "review owned diff",
            "depends_on": ["fixer-1"],
            "acceptance": ["review current fingerprint"],
            "diff_base": "HEAD~1",
            "diff_head": "HEAD",
            "diff_fingerprint": "a" * 64,
            "owning_fixer": "fixer-1",
        }
        assignment.update(overrides)
        return assignment

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
        self.assertEqual(1, plan["contract_version"])
        self.assertEqual("data/contracts/orchestration-v1.schema.json", plan["contract_schema"])
        for field in [
            "contract_version",
            "contract_schema",
            "policies",
            "assignment_contract",
            "result_contract",
            "stages",
            "constraints",
            "optional_roles",
        ]:
            self.assertIn(field, plan["agent_plan"])

    def test_planned_files_and_intent_drive_classification_without_polluting_changed_files(self) -> None:
        repo, cfg = self.make_repo()
        plan = self.plan(
            repo,
            cfg,
            planned_paths=["src/frontend/LoginPage.tsx"],
            intent="新增登录鉴权页面并发布",
        )
        self.assertEqual([], plan["changed_files"])
        self.assertEqual(["src/frontend/LoginPage.tsx"], plan["planned_files"])
        self.assertEqual(["src/frontend/LoginPage.tsx"], plan["classification_files"])
        self.assertTrue(plan["intent_provided"])
        self.assertEqual(["auth", "release_or_tooling", "ui"], plan["intent_categories"])
        self.assertEqual(["auth", "release_or_tooling"], plan["intent_risk_candidates"])
        self.assertTrue(plan["needs_browser"])
        self.assertEqual("standard", plan["profile"])
        self.assertFalse(plan["review_required"])
        self.assertEqual([], plan["recommended_agents"])
        self.assertEqual([], plan["optional_agents"])
        self.assertNotIn("browser_debugger", plan["recommended_agents"])
        self.assertNotIn("docs_researcher", plan["recommended_agents"])
        self.assertNotIn("新增登录鉴权页面并发布", str(plan))

    def test_ordinary_code_resolves_standard(self) -> None:
        repo, cfg = self.make_repo()
        plan = self.plan(repo, cfg, planned_paths=["src/widget.py"])
        self.assertEqual("standard", plan["profile"])
        self.assertEqual("change", plan["task_kind"])
        self.assertEqual("changed", plan["selected_scope"])
        self.assertEqual("dev", plan["effective_mode"])
        self.assertEqual([], plan["recommended_agents"])
        agent_plan = plan["agent_plan"]
        self.assertEqual("main-only", agent_plan["strategy"])
        self.assertEqual(["delivery"], [stage["id"] for stage in agent_plan["stages"]])
        self.assertTrue(agent_plan["policies"]["one_writer_per_worktree"])
        self.assertEqual("explicit-only-for-isolated-or-delegated-work", agent_plan["policies"]["path_ownership"])
        self.assertEqual(
            "integrate-before-dependent-start",
            agent_plan["policies"]["dependency_policy"],
        )
        self.assertEqual("main", agent_plan["policies"]["review_feedback_owner"])
        self.assertEqual("diff-fingerprint-when-required", agent_plan["policies"]["review_binding"])
        self.assertEqual("main", agent_plan["policies"]["lifecycle_owner"])
        self.assertIn("owned_paths", agent_plan["assignment_contract"]["writer"])
        self.assertIn("diff_fingerprint", agent_plan["assignment_contract"]["reviewer"])
        self.assertIn("diff_fingerprint", agent_plan["result_contract"])
        delivery = next(stage for stage in agent_plan["stages"] if stage["id"] == "delivery")
        self.assertEqual("serial", delivery["mode"])
        self.assertFalse(plan["review_required"])
        self.assertEqual(
            ["analysis", "final_changed_scope_gate", "commit_push"],
            plan["mechanism_plan"]["required"],
        )
        self.assertFalse(plan["mechanism_plan"]["lifecycle_required"])
        self.assertIn("read_only_subagents", plan["mechanism_plan"]["optional_when_beneficial"])
        self.assertNotIn("parallel_fixers", plan["mechanism_plan"]["optional_when_beneficial"])
        self.assertIn("task_lifecycle", plan["mechanism_plan"]["forbidden"])
        self.assertIn("parallel_fixers", plan["mechanism_plan"]["forbidden"])

    def test_intent_only_classifies_read_only_change_and_terminal_work(self) -> None:
        repo, cfg = self.make_repo()
        read_only = self.plan(repo, cfg, intent="Explain how authentication currently works")
        self.assertEqual("read_only", read_only["task_kind"])
        self.assertEqual("none", read_only["execution_mode"])
        self.assertEqual(["analysis"], read_only["mechanism_plan"]["required"])
        self.assertIn(
            "read_only_subagents",
            read_only["mechanism_plan"]["optional_when_beneficial"],
        )
        self.assertIn("commit_push", read_only["mechanism_plan"]["forbidden"])

        change = self.plan(repo, cfg, intent="Fix the login redirect bug")
        self.assertEqual("change", change["task_kind"])
        self.assertEqual("direct", change["execution_mode"])
        self.assertIn("commit_push", change["mechanism_plan"]["required"])

        chinese_change = self.plan(repo, cfg, intent="请解决并优化登录跳转问题")
        self.assertEqual("change", chinese_change["task_kind"])

        forced_read_only = self.plan(
            repo,
            cfg,
            intent="Fix wording in the explanation",
            requested_task_kind="read_only",
        )
        self.assertEqual("read_only", forced_read_only["task_kind"])

        terminal = self.plan(
            repo,
            cfg,
            intent="reconcile the completed task ledger",
        )
        self.assertEqual("terminal_maintenance", terminal["task_kind"])
        self.assertEqual(
            ["analysis", "targeted_consistency_check", "commit_push"],
            terminal["mechanism_plan"]["required"],
        )
        self.assertIn("task_lifecycle", terminal["mechanism_plan"]["forbidden"])

        with self.assertRaises(APError):
            self.plan(
                repo,
                cfg,
                planned_paths=["src/payment/service.py"],
                requested_task_kind="terminal_maintenance",
            )
        with self.assertRaises(APError):
            self.plan(
                repo,
                cfg,
                planned_paths=["src/widget.py"],
                requested_task_kind="none",
            )

    def test_execution_mode_is_none_direct_isolated_or_parallel(self) -> None:
        repo, cfg = self.make_repo()
        self.assertEqual("none", self.plan(repo, cfg)["execution_mode"])
        direct = self.plan(repo, cfg, planned_paths=["src/widget.py"])
        self.assertEqual("direct", direct["execution_mode"])
        dirty = repo / "existing.txt"
        dirty.write_text("user change\n", encoding="utf-8")
        isolated = self.plan(repo, cfg, planned_paths=["src/widget.py"])
        self.assertEqual("isolated", isolated["execution_mode"])
        self.assertTrue(isolated["mechanism_plan"]["lifecycle_required"])
        self.assertIn("worktree", isolated["mechanism_plan"]["required"])
        dirty.unlink()
        parallel = self.plan(
            repo,
            cfg,
            planned_paths=["src/widget.py"],
            parallel_writers=2,
        )
        self.assertEqual("isolated", parallel["execution_mode"])
        self.assertTrue(parallel["review_required"])
        self.assertIn("fixer", parallel["recommended_agents"])
        self.assertIn("parallel_fixers", parallel["mechanism_plan"]["required"])
        self.assertEqual("orchestrated-subagents", parallel["agent_plan"]["strategy"])

    def test_working_tree_snapshot_covers_clean_unstaged_staged_and_untracked_paths(self) -> None:
        repo, _ = self.make_repo()
        unstaged = repo / "tracked unstaged.txt"
        staged = repo / "tracked-staged.txt"
        unstaged.write_text("baseline\n", encoding="utf-8")
        staged.write_text("baseline\n", encoding="utf-8")
        run(repo, "git", "add", "tracked unstaged.txt", "tracked-staged.txt")
        run(repo, "git", "commit", "-qm", "add status fixtures")

        self.assertEqual([], ap._working_tree_paths(repo))

        unstaged.write_text("unstaged change\n", encoding="utf-8")
        staged.write_text("staged change\n", encoding="utf-8")
        run(repo, "git", "add", "tracked-staged.txt")
        (repo / "untracked path.txt").write_text("untracked\n", encoding="utf-8")
        (repo / "untracked\nline.txt").write_text("untracked newline\n", encoding="utf-8")

        self.assertEqual(
            [
                "tracked unstaged.txt",
                "tracked-staged.txt",
                "untracked\nline.txt",
                "untracked path.txt",
            ],
            ap._working_tree_paths(repo),
        )

    def test_working_tree_snapshot_includes_both_staged_rename_endpoints(self) -> None:
        repo, _ = self.make_repo()
        source = repo / "old name.txt"
        source.write_text("stable\n", encoding="utf-8")
        run(repo, "git", "add", "old name.txt")
        run(repo, "git", "commit", "-qm", "add rename fixture")

        run(repo, "git", "mv", "old name.txt", "new name.txt")

        self.assertEqual(
            ["new name.txt", "old name.txt"],
            ap._working_tree_paths(repo),
        )

    def test_working_tree_snapshot_fails_closed_on_git_error_or_malformed_output(self) -> None:
        repo, _ = self.make_repo()
        failed = subprocess.CompletedProcess(
            args=["git", "status"],
            returncode=128,
            stdout="",
            stderr="fatal: status unavailable",
        )
        with mock.patch.object(ap, "run", return_value=failed):
            with self.assertRaises(APError) as context:
                ap._working_tree_paths(repo)
        self.assertIn("refusing a direct execution plan", str(context.exception))
        self.assertIn("status unavailable", str(context.exception))

        malformed = subprocess.CompletedProcess(
            args=["git", "status"],
            returncode=0,
            stdout="1 malformed\0",
            stderr="",
        )
        with mock.patch.object(ap, "run", return_value=malformed):
            with self.assertRaises(APError) as context:
                ap._working_tree_paths(repo)
        self.assertIn("Cannot parse Git working tree status", str(context.exception))

    def test_writer_registries_fail_closed_when_json_is_corrupt(self) -> None:
        repo, cfg = self.make_repo()
        task_registry = ap._task_state_root(repo) / "tasks" / "T001.json"
        task_registry.parent.mkdir(parents=True, exist_ok=True)
        task_registry.write_text("{broken", encoding="utf-8")
        with self.assertRaises(APError) as context:
            self.plan(repo, cfg, planned_paths=["src/widget.py"])
        self.assertIn("Task registry is unreadable", str(context.exception))

        task_registry.unlink()
        claim_registry = (
            ap._task_state_root(repo) / "direct-claims" / ("a" * 32 + ".json")
        )
        claim_registry.parent.mkdir(parents=True, exist_ok=True)
        claim_registry.write_text("{broken", encoding="utf-8")
        with self.assertRaises(APError) as context:
            self.plan(repo, cfg, planned_paths=["src/widget.py"])
        self.assertIn("Direct claim registry is unreadable", str(context.exception))

    def test_same_owner_direct_claim_is_rejected_and_not_implicitly_exempted(self) -> None:
        repo, cfg = self.make_repo()
        claim = ap._create_direct_claim(repo, cfg, ["src/widget.py"], "same-owner")
        claim_path = ap._direct_claim_path(repo, claim["claim_id"])

        plan = self.plan(repo, cfg, planned_paths=["src/widget.py"])
        self.assertTrue(plan["active_writer"])
        self.assertEqual("isolated", plan["execution_mode"])
        self.assertTrue(claim_path.exists())
        self.assertEqual(claim["claim_id"], json.loads(claim_path.read_text())["claim_id"])

        with self.assertRaises(APError) as context:
            ap._create_direct_claim(repo, cfg, ["src/widget.py"], "same-owner")
        self.assertIn(claim["claim_id"], str(context.exception))
        self.assertTrue(claim_path.exists())

    def test_continue_direct_accepts_only_declared_current_task_dirt(self) -> None:
        repo, cfg = self.make_repo()
        claim = ap._create_direct_claim(
            repo,
            cfg,
            ["src/widget.py"],
            os.environ.get("CODEX_THREAD_ID") or "profile-test-owner",
        )
        target = repo / "src" / "widget.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("task change\n", encoding="utf-8")

        default = self.plan(repo, cfg, planned_paths=["src/widget.py"])
        self.assertEqual("isolated", default["execution_mode"])
        continued = self.plan(
            repo,
            cfg,
            planned_paths=["src/widget.py"],
            continue_direct=True,
            direct_claim_id=claim["claim_id"],
        )
        self.assertEqual("direct", continued["execution_mode"])
        self.assertTrue(continued["continued_direct"])
        self.assertEqual([], continued["dirty_outside_plan"])

        (repo / "unrelated.txt").write_text("other writer\n", encoding="utf-8")
        with self.assertRaises(APError) as context:
            self.plan(
                repo,
                cfg,
                planned_paths=["src/widget.py"],
                continue_direct=True,
                direct_claim_id=claim["claim_id"],
            )
        self.assertIn("outside the clean direct claim", str(context.exception))

    def test_continue_direct_requires_a_clean_pre_write_claim(self) -> None:
        repo, cfg = self.make_repo()
        (repo / "unknown.txt").write_text("pre-existing user change\n", encoding="utf-8")
        with self.assertRaises(APError) as context:
            ap._create_direct_claim(repo, cfg, ["."], "profile-test-owner")
        self.assertIn("before the first write", str(context.exception))
        with self.assertRaises(APError) as context:
            self.plan(repo, cfg, planned_paths=["."], continue_direct=True)
        self.assertIn("requires --direct-claim", str(context.exception))

    def test_risk_intent_is_candidate_while_paths_and_rules_control_escalation(self) -> None:
        repo, cfg = self.make_repo()
        ui = self.plan(
            repo,
            cfg,
            planned_paths=["frontend/src/LoginPage.tsx"],
            intent="修复登录跳转问题",
        )
        self.assertEqual("standard", ui["profile"])
        self.assertFalse(ui["review_required"])
        self.assertEqual(["auth"], ui["intent_risk_candidates"])
        self.assertEqual(["browser_debugger"], ui["optional_agents"])

        backend = self.plan(repo, cfg, planned_paths=["backend/auth/service.py"])
        self.assertEqual("high-risk", backend["profile"])
        self.assertTrue(backend["review_required"])
        self.assertEqual(["explorer"], backend["optional_agents"])

        cfg["risk"] = {
            "rules": [
                {
                    "name": "sensitive-login-ui",
                    "paths": ["frontend/src/LoginPage.tsx"],
                    "profile": "high-risk",
                }
            ]
        }
        configured = self.plan(repo, cfg, planned_paths=["frontend/src/LoginPage.tsx"])
        self.assertEqual("high-risk", configured["profile"])

        order = self.plan(repo, cfg, planned_paths=["backend/orders/sort_order.py"])
        self.assertNotIn("payment", order["categories"])

    def test_high_confidence_intent_and_backend_login_escalate_without_ui_false_positive(self) -> None:
        repo, cfg = self.make_repo()
        for intent, category in [
            ("修改数据库迁移", "db"),
            ("修改后端鉴权权限", "auth"),
            ("修改支付结算逻辑", "payment"),
            ("修改生产网关配置", "gateway"),
        ]:
            with self.subTest(intent=intent):
                plan = self.plan(repo, cfg, intent=intent)
                self.assertEqual("high-risk", plan["profile"])
                self.assertTrue(plan["review_required"])
                self.assertIn(category, plan["high_confidence_intent_categories"])

        backend_login = self.plan(
            repo,
            cfg,
            planned_paths=["backend/login_handler.go"],
            intent="修复登录处理",
        )
        self.assertEqual("high-risk", backend_login["profile"])
        self.assertTrue(backend_login["review_required"])

        login_ui = self.plan(
            repo,
            cfg,
            planned_paths=["frontend/LoginPage.tsx"],
            intent="修复登录页面跳转",
        )
        self.assertEqual("standard", login_ui["profile"])
        self.assertFalse(login_ui["review_required"])

    def test_generated_agent_strategies_match_contract_schema(self) -> None:
        schema = json.loads(
            (REPO_ROOT / "src" / "auto-coding-skill" / "data" / "contracts" / "orchestration-v1.schema.json")
            .read_text(encoding="utf-8")
        )
        allowed = set(schema["$defs"]["agentPlan"]["properties"]["strategy"]["enum"])
        repo, cfg = self.make_repo()
        for kwargs in [
            {"planned_paths": ["src/widget.py"]},
            {"planned_paths": ["backend/auth/service.py"]},
            {"planned_paths": ["src/widget.py"], "parallel_writers": 2},
        ]:
            with self.subTest(kwargs=kwargs):
                plan = self.plan(repo, cfg, **kwargs)
                self.assertIn(plan["agent_plan"]["strategy"], allowed)
                ap._validate_orchestration_contract("classify", plan)

    def test_agent_assignment_and_result_contracts_are_machine_enforced(self) -> None:
        fingerprint = "a" * 64
        assignment = {
            "contract_version": 1,
            "node_id": "reviewer-1",
            "task_id": "T001",
            "role": "reviewer",
            "base_sha": "HEAD",
            "scope": "review owned diff",
            "depends_on": [],
            "acceptance": ["review current fingerprint"],
            "diff_base": "HEAD~1",
            "diff_head": "HEAD",
            "diff_fingerprint": fingerprint,
            "owning_fixer": "fixer-1",
        }
        ap._validate_orchestration_contract("assignment", assignment)
        self_review = dict(assignment, node_id="fixer-1")
        with self.assertRaises(APError):
            ap._validate_orchestration_contract("assignment", self_review)

        result = {
            "contract_version": 1,
            "node_id": "reviewer-1",
            "role": "reviewer",
            "task_id": "T001",
            "base_sha": "HEAD~1",
            "status": "completed",
            "summary": "reviewed",
            "depends_on": [],
            "owned_paths": [],
            "changed_paths": [],
            "diff_fingerprint": fingerprint,
            "evidence": ["diff reviewed"],
            "findings": [],
            "verdict": "approved",
            "risks": [],
            "next_owner": "main",
        }
        ap._validate_orchestration_contract("result", result)
        with self.assertRaises(APError):
            ap._validate_orchestration_contract("result", dict(result, diff_fingerprint=""))

    def test_reviewer_result_template_has_complete_contract_and_verdict_mappings(self) -> None:
        assignment = self.reviewer_assignment()
        required_fields = {
            "contract_version",
            "node_id",
            "role",
            "task_id",
            "base_sha",
            "status",
            "summary",
            "depends_on",
            "owned_paths",
            "changed_paths",
            "diff_fingerprint",
            "evidence",
            "findings",
            "verdict",
            "risks",
            "next_owner",
        }
        for verdict, status, next_owner in [
            ("approved", "completed", "main"),
            ("changes-requested", "completed", "fixer-1"),
            ("blocked", "blocked", "main"),
        ]:
            with self.subTest(verdict=verdict):
                result = ap._reviewer_result_template(assignment, verdict)
                self.assertEqual(required_fields, set(result))
                self.assertEqual("reviewer", result["role"])
                self.assertEqual("reviewer-1", result["node_id"])
                self.assertEqual("T001", result["task_id"])
                self.assertEqual("HEAD", result["base_sha"])
                self.assertEqual(["fixer-1"], result["depends_on"])
                self.assertEqual([], result["owned_paths"])
                self.assertEqual([], result["changed_paths"])
                self.assertEqual("a" * 64, result["diff_fingerprint"])
                self.assertEqual(verdict, result["verdict"])
                self.assertEqual(status, result["status"])
                self.assertEqual(next_owner, result["next_owner"])
                ap._validate_orchestration_contract("result", result)

    def test_reviewer_runtime_normalizes_presentation_fields_but_binds_identity(self) -> None:
        assignment = self.reviewer_assignment()
        result = ap._normalize_reviewer_runtime_result(
            assignment,
            {
                "verdict": "approved",
                "summary": "focused review complete",
                "evidence": ["diff inspected"],
            },
        )
        self.assertEqual("reviewer-1", result["node_id"])
        self.assertEqual("a" * 64, result["diff_fingerprint"])
        self.assertEqual(["fixer-1"], result["depends_on"])
        self.assertEqual("focused review complete", result["summary"])

        with self.assertRaisesRegex(APError, "does not match its assignment"):
            ap._normalize_reviewer_runtime_result(
                assignment,
                {
                    "verdict": "approved",
                    "diff_fingerprint": "b" * 64,
                },
            )

    def test_codex_reviewer_command_is_ephemeral_read_only_and_uses_managed_instructions(self) -> None:
        repo, _ = self.make_repo()
        assignment_path = repo / "assignment.json"
        result_path = repo / "result.json"
        with mock.patch.object(ap.shutil, "which", return_value="/usr/local/bin/codex"):
            command = ap._codex_reviewer_command(repo, assignment_path, result_path)

        self.assertEqual("/usr/local/bin/codex", command[0])
        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("read-only", command)
        self.assertIn('model_reasoning_effort="xhigh"', command)
        developer_override = next(
            item for item in command if item.startswith("developer_instructions=")
        )
        tomllib.loads(developer_override)
        self.assertEqual(str(result_path), command[command.index("-o") + 1])

    def test_reviewer_process_timeout_terminates_its_process_group(self) -> None:
        repo, _ = self.make_repo()
        process = mock.MagicMock()
        process.pid = 4321
        process.poll.return_value = None
        process.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd=["fake-reviewer"], timeout=0.01),
            ("partial", "stopped"),
        ]
        with (
            mock.patch.object(ap.subprocess, "Popen", return_value=process) as popen,
            mock.patch.object(ap.os, "killpg") as killpg,
        ):
            with self.assertRaises(ap._ReviewerRuntimeTimeout):
                ap._run_supervised_reviewer_process(
                    ["fake-reviewer", "; touch must-not-run"],
                    cwd=repo,
                    env={"PATH": os.environ.get("PATH", "")},
                    timeout_seconds=0.01,
                )

        self.assertEqual(["fake-reviewer", "; touch must-not-run"], popen.call_args.args[0])
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertEqual(mock.call(4321, ap.signal.SIGTERM), killpg.call_args)

    def test_reviewer_assignment_timing_contract_and_fixed_budgets(self) -> None:
        issued_at = "2026-07-16T00:00:00+00:00"
        assignment = self.reviewer_assignment(
            review_depth="focused",
            timeout_seconds=90,
            issued_at=issued_at,
            deadline_at="2026-07-16T00:01:30+00:00",
            scope_revision=1,
        )
        self.assertEqual(
            assignment,
            ap._validate_orchestration_contract("assignment", assignment),
        )
        self.assertEqual(("focused", 90), ap._normalized_task_review_policy(True))
        self.assertEqual(
            ("deep", 300),
            ap._normalized_task_review_policy(True, "focused", "deep"),
        )
        self.assertEqual(("none", 0), ap._normalized_task_review_policy(False, "deep"))

        invalid_contracts = [
            self.reviewer_assignment(
                review_depth="focused",
                timeout_seconds=0,
                issued_at=issued_at,
                deadline_at="2026-07-16T00:01:30+00:00",
            ),
            self.reviewer_assignment(
                review_depth="focused",
                timeout_seconds=90,
                issued_at="2026-07-16T00:00:00",
                deadline_at="2026-07-16T00:01:30",
            ),
            self.reviewer_assignment(
                review_depth="focused",
                timeout_seconds=90,
                issued_at=issued_at,
                deadline_at="2026-07-16T00:01:00+00:00",
            ),
        ]
        for payload in invalid_contracts:
            with self.subTest(payload=payload):
                with self.assertRaises(APError):
                    ap._validate_orchestration_contract("assignment", payload)

    def test_reviewer_result_template_rejects_wrong_role_self_review_and_empty_fingerprint(self) -> None:
        invalid_assignments = [
            self.reviewer_assignment(role="explorer"),
            self.reviewer_assignment(node_id="fixer-1"),
            self.reviewer_assignment(diff_fingerprint=""),
        ]
        for assignment in invalid_assignments:
            with self.subTest(assignment=assignment):
                with self.assertRaises(APError):
                    ap._reviewer_result_template(assignment, "approved")

    def test_agent_result_template_command_reads_assignment_and_prints_json(self) -> None:
        repo, _ = self.make_repo()
        assignment_path = repo / "reviewer-assignment.json"
        assignment_path.write_text(
            json.dumps(self.reviewer_assignment()),
            encoding="utf-8",
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            ap.cmd_agent_result_template(
                argparse.Namespace(
                    repo=str(repo),
                    file=str(assignment_path),
                    payload="",
                    verdict="changes-requested",
                )
            )

        result = json.loads(output.getvalue())
        self.assertEqual("reviewer", result["role"])
        self.assertEqual("changes-requested", result["verdict"])
        self.assertEqual("completed", result["status"])
        self.assertEqual("fixer-1", result["next_owner"])
        self.assertEqual(16, len(result))

    def test_contract_validation_collects_missing_unexpected_type_pattern_and_conditionals(self) -> None:
        result = ap._reviewer_result_template(self.reviewer_assignment(), "approved")
        result.pop("next_owner")
        result.update(
            {
                "node_id": [],
                "changed_paths": ["src/unauthorized.py"],
                "diff_fingerprint": "not-a-fingerprint",
                "verdict": "ready-for-review",
                "unexpected_field": True,
            }
        )

        with self.assertRaises(APError) as context:
            ap._validate_orchestration_contract("result", result)

        message = str(context.exception)
        self.assertIn("missing next_owner", message)
        self.assertIn("unexpected unexpected_field", message)
        self.assertIn("$.node_id: expected type", message)
        self.assertIn("$.diff_fingerprint: string does not match", message)
        self.assertIn("$.changed_paths: too many array items", message)
        self.assertIn("$.verdict: value is outside the allowed enum", message)

    def test_contract_if_branches_do_not_apply_other_role_requirements(self) -> None:
        fixer_assignment = {
            "contract_version": 1,
            "node_id": "fixer-1",
            "task_id": "T001",
            "role": "fixer",
            "base_sha": "HEAD",
            "scope": "implement one change",
            "depends_on": [],
            "acceptance": ["tests pass"],
            "execution_mode": "isolated",
            "owned_paths": ["src/**"],
        }
        with self.assertRaises(APError) as context:
            ap._validate_orchestration_contract("assignment", fixer_assignment)

        message = str(context.exception)
        self.assertIn("task_branch", message)
        self.assertIn("worktree_path", message)
        self.assertNotIn("diff_base", message)
        self.assertNotIn("diff_head", message)
        self.assertNotIn("diff_fingerprint", message)
        self.assertNotIn("owning_fixer", message)

    def test_validation_routes_collect_all_commands_and_reject_unmapped_code(self) -> None:
        repo, cfg = self.make_repo()
        cfg["commands"] = {"one": "true", "two": "true"}
        cfg["validation"] = {
            "on_unmapped": "error",
            "routes": [
                {"name": "all-src", "paths": ["src/**"], "commands": ["one", "two"]},
                {"name": "python", "paths": ["**/*.py"], "commands": ["two"]},
            ],
        }
        plan = ap._validation_plan(cfg, ["src/widget.py"])
        self.assertEqual(["one", "two"], plan["commands"])
        self.assertEqual(["all-src", "python"], plan["matched_routes"])
        ap._validate_validation_plan(cfg, plan)
        with self.assertRaises(APError) as context:
            ap._validate_validation_plan(cfg, ap._validation_plan(cfg, ["contracts/api.yaml"]))
        self.assertIn("no validation route", str(context.exception))

    def test_final_gate_budget_is_configurable_and_times_out(self) -> None:
        cfg = base_config()
        cfg["validation"] = {
            "on_unmapped": "error",
            "max_command_seconds": 0.05,
            "max_total_seconds": 0.1,
            "routes": [{"name": "slow", "paths": ["src/**"], "commands": ["slow"]}],
        }
        cfg["commands"]["slow"] = f'{sys.executable} -c "import time; time.sleep(1)"'
        repo, cfg = self.make_repo("src/widget.py", cfg)
        with self.assertRaises(APError) as context:
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
        self.assertIn("timed out", str(context.exception))

        cfg["validation"]["max_command_seconds"] = 240
        cfg["validation"]["max_total_seconds"] = 300
        self.assertEqual(
            {"command_seconds": 240.0, "total_seconds": 300.0},
            ap._final_gate_budget(cfg),
        )

        cfg["validation"]["max_total_seconds"] = 200
        with self.assertRaises(APError) as context:
            ap._final_gate_budget(cfg)
        self.assertIn("cannot exceed validation.max_total_seconds", str(context.exception))

    def test_final_changed_scope_gate_runs_blocking_structure_check(self) -> None:
        cfg = base_config()
        cfg["structure"] = {
            "enabled": True,
            "enforcement": "blocking",
            "max_file_lines_warn": 0,
            "max_file_lines_block": 1,
            "max_function_lines_warn": 0,
            "layer_rules": {"enabled": False},
        }
        cfg["optimization"] = {"require_baseline_for_global_review": False}
        repo, _ = self.make_repo("src/too-large.py", cfg)
        (repo / "src" / "too-large.py").write_text("one\ntwo\n", encoding="utf-8")

        with self.assertRaisesRegex(APError, "structure-check failed"):
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

    def test_route_timeout_uses_smallest_matching_budget(self) -> None:
        cfg = base_config()
        cfg["commands"] = {"one": "true", "two": "true"}
        cfg["validation"] = {
            "on_unmapped": "error",
            "max_command_seconds": 120,
            "max_total_seconds": 180,
            "routes": [
                {
                    "name": "all-src",
                    "paths": ["src/**"],
                    "commands": ["one", "two"],
                    "timeout_seconds": 90,
                },
                {
                    "name": "python",
                    "paths": ["**/*.py"],
                    "commands": ["two"],
                    "timeout_seconds": 30,
                },
            ],
        }
        plan = ap._validation_plan(cfg, ["src/widget.py"])
        self.assertEqual({"one": 90.0, "two": 30.0}, plan["command_timeouts"])

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
        self.assertFalse(plan["needs_dd"])
        self.assertTrue(plan["review_required"])
        self.assertIn("reviewer", plan["recommended_agents"])
        self.assertFalse(plan["needs_jenkins"])
        self.assertFalse(plan["needs_target"])

    def test_focused_and_deep_review_policies_share_reviewer_with_bounded_attempt(self) -> None:
        cfg = base_config()
        cfg["risk"] = {
            "rules": [
                {
                    "name": "focused-sensitive-change",
                    "paths": ["src/sensitive/**"],
                    "profile": "high-risk",
                }
            ]
        }
        repo, cfg = self.make_repo(config=cfg)
        focused = self.plan(repo, cfg, planned_paths=["src/sensitive/value.py"])
        deep = self.plan(repo, cfg, planned_paths=["backend/auth/service.py"])

        for plan, depth, timeout in [
            (focused, "focused", 90),
            (deep, "deep", 300),
        ]:
            with self.subTest(depth=depth):
                self.assertTrue(plan["review_required"])
                self.assertEqual(depth, plan["review_depth"])
                self.assertEqual("reviewer", plan["review_agent"])
                self.assertEqual(timeout, plan["review_timeout_seconds"])
                self.assertEqual(1, plan["review_analysis_attempt_limit"])
                self.assertEqual("reviewer", plan["agent_plan"]["policies"]["review_agent"])
                self.assertEqual(
                    timeout,
                    plan["agent_plan"]["policies"]["review_timeout_seconds"],
                )
                self.assertEqual(
                    1,
                    plan["agent_plan"]["policies"]["review_analysis_attempt_limit"],
                )
                constraints = " ".join(plan["agent_plan"]["constraints"]).lower()
                self.assertIn("timeout is blocked", constraints)
                self.assertIn("reuse the same analysis", constraints)

    def test_ui_api_reports_capabilities_without_auto_dispatch(self) -> None:
        repo, cfg = self.make_repo("src/api/settings-page.tsx")
        plan = self.plan(repo, cfg)
        self.assertTrue(plan["needs_browser"])
        self.assertEqual([], plan["recommended_agents"])
        self.assertEqual("main-only", plan["agent_plan"]["strategy"])
        self.assertEqual(["main"], plan["agent_plan"]["stages"][0]["roles"])

    def test_ui_classification_uses_segments_and_extensions_not_substrings(self) -> None:
        for path in [
            ".env.components",
            "docker-compose.components.yml",
            "config/component-overrides.yml",
            "backend/component_service.go",
        ]:
            with self.subTest(path=path):
                self.assertNotIn("ui", ap._classify_paths([path])["categories"])

        for path in [
            "frontend/src/app.ts",
            "src/components/Button.ts",
            "src/views/Home.js",
            "src/Button.tsx",
            "miniapp/pages/home/index.ts",
        ]:
            with self.subTest(path=path):
                self.assertIn("ui", ap._classify_paths([path])["categories"])

        repo, cfg = self.make_repo()
        plan = self.plan(repo, cfg, planned_paths=[".env.components"])
        self.assertFalse(plan["needs_browser"])

    def test_exact_cross_module_high_risk_rename_is_mechanical_but_reviewed(self) -> None:
        repo, cfg = self.make_repo()
        source = repo / "backend" / "auth" / "policy.py"
        source.parent.mkdir(parents=True)
        source.write_text("POLICY = 'stable'\n", encoding="utf-8")
        run(repo, "git", "add", str(source.relative_to(repo)))
        run(repo, "git", "commit", "-qm", "add auth policy")
        destination = repo / "account" / "auth" / "policy.py"
        destination.parent.mkdir(parents=True)
        run(repo, "git", "mv", str(source.relative_to(repo)), str(destination.relative_to(repo)))

        plan = self.plan(repo, cfg)

        self.assertEqual(
            ["account/auth/policy.py", "backend/auth/policy.py"],
            plan["changed_files"],
        )
        self.assertTrue(plan["cross_module"])
        self.assertEqual("high-risk", plan["profile"])
        self.assertEqual("mechanical", plan["change_nature"])
        self.assertTrue(plan["review_required"])
        self.assertFalse(plan["design_required"])

        extra = repo / "account" / "auth" / "new_policy.py"
        extra.write_text("POLICY = 'new'\n", encoding="utf-8")
        mixed = self.plan(repo, cfg)
        self.assertEqual("unknown", mixed["change_nature"])
        self.assertTrue(mixed["design_required"])

    def test_semantic_or_unknown_cross_module_high_risk_change_keeps_design(self) -> None:
        repo, cfg = self.make_repo()
        source = repo / "backend" / "auth" / "policy.py"
        source.parent.mkdir(parents=True)
        source.write_text("POLICY = 'stable'\n", encoding="utf-8")
        run(repo, "git", "add", str(source.relative_to(repo)))
        run(repo, "git", "commit", "-qm", "add auth policy")
        destination = repo / "account" / "auth" / "policy.py"
        destination.parent.mkdir(parents=True)
        run(repo, "git", "mv", str(source.relative_to(repo)), str(destination.relative_to(repo)))
        destination.write_text("POLICY = 'changed'\n", encoding="utf-8")

        semantic = self.plan(repo, cfg, intent="改变鉴权策略行为和模块职责")
        self.assertEqual("semantic", semantic["change_nature"])
        self.assertTrue(semantic["review_required"])
        self.assertTrue(semantic["design_required"])

        clean_repo, clean_cfg = self.make_repo()
        unknown = self.plan(
            clean_repo,
            clean_cfg,
            planned_paths=["backend/auth/policy.py", "account/auth/policy.py"],
        )
        self.assertEqual("unknown", unknown["change_nature"])
        self.assertTrue(unknown["review_required"])
        self.assertTrue(unknown["design_required"])

    def test_failed_git_rename_probe_stays_conservative(self) -> None:
        repo, _ = self.make_repo()
        failed = subprocess.CompletedProcess(
            args=["git", "diff"],
            returncode=128,
            stdout="",
            stderr="fatal: diff unavailable",
        )
        with (
            mock.patch.object(ap, "_effective_change_base", return_value=""),
            mock.patch.object(ap, "run", return_value=failed),
        ):
            self.assertFalse(
                ap._pure_exact_git_rename(
                    repo,
                    "",
                    ["backend/auth/policy.py", "account/auth/policy.py"],
                )
            )

    def test_explicit_design_rule_wins_over_mechanical_change(self) -> None:
        cfg = base_config()
        cfg["risk"] = {
            "rules": [
                {
                    "name": "auth-design",
                    "paths": ["**/auth/**"],
                    "profile": "high-risk",
                    "design": "required",
                }
            ]
        }
        repo, cfg = self.make_repo(config=cfg)
        plan = self.plan(
            repo,
            cfg,
            planned_paths=["backend/auth/policy.py", "account/auth/policy.py"],
            intent="机械同步，不改变行为",
        )
        self.assertEqual("mechanical", plan["change_nature"])
        self.assertTrue(plan["review_required"])
        self.assertTrue(plan["design_required"])

    def test_semantic_or_negated_intent_overrides_mechanical_words(self) -> None:
        repo, cfg = self.make_repo()
        paths = ["backend/auth/policy.py", "account/auth/policy.py"]
        for intent in [
            "mechanical sync that changes behavior",
            "rename only while changing the API contract",
            "机械同步但修改鉴权契约",
        ]:
            with self.subTest(intent=intent):
                plan = self.plan(repo, cfg, planned_paths=paths, intent=intent)
                self.assertEqual("semantic", plan["change_nature"])
                self.assertTrue(plan["design_required"])

        for intent in ["not mechanical", "不是机械变更"]:
            with self.subTest(intent=intent):
                plan = self.plan(repo, cfg, planned_paths=paths, intent=intent)
                self.assertEqual("unknown", plan["change_nature"])
                self.assertTrue(plan["design_required"])

    def test_terminal_ledger_maintenance_creates_no_lifecycle_plan(self) -> None:
        repo, cfg = self.make_repo()
        plan = self.plan(repo, cfg, planned_paths=["docs/tasks/closure-log.md"])
        self.assertTrue(plan["terminal_maintenance"])
        self.assertEqual("none", plan["execution_mode"])
        self.assertFalse(plan["review_required"])
        self.assertFalse(plan["design_required"])
        self.assertEqual([], plan["recommended_agents"])

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
        quick_marker = repo.parent / "quick-ran"
        full_marker = repo.parent / "full-ran"
        build_marker = repo.parent / "build-ran"
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

    def test_classify_text_output_exposes_workspace_and_writer_snapshot(self) -> None:
        repo, _ = self.make_repo("path with spaces.txt")
        output = io.StringIO()
        args = argparse.Namespace(
            repo=str(repo),
            scope="auto",
            profile="",
            mode="dev",
            base="",
            planned_path=[],
            intent="",
            intent_file="",
            task_kind="auto",
            claim_direct=False,
            claim_owner="",
            continue_direct=False,
            direct_claim="",
            writers=1,
            json=False,
        )
        with mock.patch.object(ap, "_record_evidence"):
            with contextlib.redirect_stdout(output):
                ap.cmd_classify(args)

        rendered = output.getvalue()
        self.assertIn(f"[classify] repo={repo.resolve()}", rendered)
        self.assertIn("[classify] workspace_dirty=true", rendered)
        self.assertIn('[classify] dirty_paths=["path with spaces.txt"]', rendered)
        self.assertIn("[classify] active_writer=false", rendered)
        self.assertIn("[classify] review_analysis_attempt_limit=0", rendered)

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

    def test_structure_scan_excludes_non_authoritative_agent_history_and_metadata(self) -> None:
        repo, _ = self.make_repo()
        files = {
            ".agents/archive/old.py": "old = True\n",
            ".agents/agents/custom.toml": "model = 'test'\n",
            ".agents/managed-install.json": "{}\n",
            ".agents/custom/check.py": "active = True\n",
            "src/app.py": "active = True\n",
        }
        for relative, content in files.items():
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        run(repo, "git", "add", "-A")
        run(repo, "git", "commit", "-qm", "add structure fixtures")

        candidates = ap._structure_paths_for_scope(repo, "full", "", {})

        self.assertIn(".agents/custom/check.py", candidates)
        self.assertIn("src/app.py", candidates)
        self.assertNotIn(".agents/archive/old.py", candidates)
        self.assertNotIn(".agents/agents/custom.toml", candidates)
        self.assertNotIn(".agents/managed-install.json", candidates)

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

    def test_upgrade_migrates_legacy_yaml_and_known_policy_fragments(self) -> None:
        cfg = base_config()
        cfg["gate"]["full_on"] = {"paths": ["src/**"]}
        cfg["gate"]["rules"] = [
            {
                "name": "legacy",
                "paths": ["src/**"],
                "profile": "high-risk",
                "scope": "full",
                "commands": ["gate_full"],
            }
        ]
        repo, _ = self.make_repo(config=cfg)
        engineering = repo / "docs" / "ENGINEERING.md"
        engineering.write_text(
            engineering.read_text(encoding="utf-8") + "High-risk work must run the full gate.\n",
            encoding="utf-8",
        )
        policy = self.workflow_policy(
            fragments=[
                {
                    "id": "official-high-risk-full",
                    "paths": ["docs/ENGINEERING.md"],
                    "match": "exact-line",
                    "text": "High-risk work must run the full gate.",
                }
            ]
        )
        args = argparse.Namespace(repo=str(repo), write=True, dry_run=False, json=False)
        with mock.patch.object(ap, "_load_workflow_migration_policy", return_value=policy):
            ap.cmd_upgrade(args)

        migrated, body = ap._read_frontmatter_markdown(engineering)
        self.assertNotIn("full_on", migrated["gate"])
        self.assertEqual([], migrated["gate"]["rules"])
        self.assertEqual("high-risk", migrated["risk"]["rules"][0]["profile"])
        self.assertEqual(["gate_full"], migrated["validation"]["routes"][-1]["commands"])
        self.assertEqual("true", migrated["commands"]["gate_full"])
        self.assertNotIn("must run the full gate", body)

    def test_upgrade_unknown_policy_conflict_fails_before_any_write(self) -> None:
        repo, _ = self.make_repo()
        engineering = repo / "docs" / "ENGINEERING.md"
        engineering.write_text(
            engineering.read_text(encoding="utf-8")
            + "High-risk work must run the full gate.\n",
            encoding="utf-8",
        )
        before = engineering.read_text(encoding="utf-8")
        args = argparse.Namespace(repo=str(repo), write=True, dry_run=False, json=False)
        with mock.patch.object(
            ap,
            "_load_workflow_migration_policy",
            return_value=self.workflow_policy(),
        ):
            with self.assertRaises(APError) as context:
                ap.cmd_upgrade(args)
        self.assertIn("docs/ENGINEERING.md", str(context.exception))
        self.assertEqual(before, engineering.read_text(encoding="utf-8"))
        self.assertFalse((repo / ".agents").exists())

    def test_doctor_ignores_managed_blocks_but_rejects_unknown_external_rule(self) -> None:
        repo, _ = self.make_repo()
        agents = repo / "AGENTS.md"
        agents.write_text(
            "<!-- auto-coding-skill:managed-agents:start version=3.0.2 -->\n"
            "High-risk work must run the full gate.\n"
            "<!-- auto-coding-skill:managed-agents:end -->\n",
            encoding="utf-8",
        )
        policy = self.workflow_policy()
        with mock.patch.object(ap, "_load_workflow_migration_policy", return_value=policy):
            ap.cmd_doctor(argparse.Namespace(repo=str(repo)))
        agents.write_text(agents.read_text(encoding="utf-8") + "High-risk work must run the full gate.\n", encoding="utf-8")
        with mock.patch.object(ap, "_load_workflow_migration_policy", return_value=policy):
            with self.assertRaises(APError) as context:
                ap.cmd_doctor(argparse.Namespace(repo=str(repo)))
        self.assertIn("AGENTS.md:4", str(context.exception))

    def test_doctor_rejects_legacy_isolation(self) -> None:
        cfg = base_config()
        cfg["concurrency"]["isolation"] = "legacy"
        repo, _ = self.make_repo(config=cfg)
        with self.assertRaises(APError) as context:
            ap.cmd_doctor(argparse.Namespace(repo=str(repo)))
        self.assertIn("must be adaptive or worktree", str(context.exception))

    def test_doctor_requires_one_fast_gate_for_every_profile(self) -> None:
        for profile in ["micro", "standard", "high-risk", "auto"]:
            with self.subTest(profile=profile):
                cfg = base_config()
                cfg["workflow"]["profile"] = profile
                cfg["commands"] = {"gate_standard": "true", "gate_full": "true"}
                repo, _ = self.make_repo(config=cfg)
                with self.assertRaises(APError) as context:
                    ap.cmd_doctor(argparse.Namespace(repo=str(repo)))
                self.assertIn("validation.routes", str(context.exception))

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

    def test_root_and_nested_package_json_are_high_risk_and_require_review(self) -> None:
        repo, cfg = self.make_repo()
        for path in ["package.json", "frontend/admin/package.json"]:
            with self.subTest(path=path):
                plan = self.plan(
                    repo,
                    cfg,
                    planned_paths=[path],
                    requested_task_kind="change",
                )
                self.assertEqual("high-risk", plan["profile"])
                self.assertTrue(plan["review_required"])
                self.assertIn("release_or_tooling", plan["categories"])

    def test_explicit_full_structure_scope_inspects_clean_tracked_files(self) -> None:
        cfg = base_config()
        cfg["structure"] = {
            "enabled": True,
            "enforcement": "advisory",
            "max_file_lines_warn": 0,
            "max_file_lines_block": 0,
            "max_function_lines_warn": 0,
            "layer_rules": {"enabled": False},
        }
        cfg["optimization"] = {"require_baseline_for_global_review": False}
        repo, _ = self.make_repo("src/app.py", cfg)
        run(repo, "git", "add", "-A")
        run(repo, "git", "commit", "-qm", "add tracked structure fixture")

        output = io.StringIO()
        with mock.patch.object(ap, "_record_evidence"), contextlib.redirect_stdout(output):
            ap.cmd_structure_check(
                argparse.Namespace(repo=str(repo), scope="full", base="", json=True)
            )

        result = json.loads(output.getvalue())
        self.assertEqual("full", result["scope"])
        self.assertGreaterEqual(result["inspected_files"], 1)

    def test_verify_jenkins_accepts_access_schema_and_uses_selected_identity(self) -> None:
        repo, cfg = self.make_repo()
        (repo / "Jenkinsfile").write_text("pipeline {}\n", encoding="utf-8")

        with mock.patch.object(ap, "_record_evidence"):
            ap.cmd_verify_jenkins(argparse.Namespace(repo=str(repo), component="all"))

        header = ap._jenkins_basic_auth_headers(cfg, component="backend")["Authorization"]
        decoded = base64.b64decode(header.removeprefix("Basic ")).decode("utf-8")
        self.assertEqual("back:back-pass", decoded)

    def test_jenkins_component_is_ambiguous_with_two_access_endpoints(self) -> None:
        cfg = base_config()
        with self.assertRaisesRegex(APError, "Multiple access.jenkins endpoints"):
            ap._resolve_jenkins_component(cfg)

        cfg["access"]["jenkins"]["backend"] = dict(cfg["access"]["jenkins"]["frontend"])
        self.assertEqual("frontend", ap._resolve_jenkins_component(cfg))

    def test_verify_jenkins_build_uses_one_selected_access_component(self) -> None:
        repo, _ = self.make_repo()
        args = argparse.Namespace(
            repo=str(repo),
            component="backend",
            git_ref="HEAD",
            job_name=None,
            job_url=None,
            multibranch_root_job=None,
            branch_name=None,
            build_number=7,
            max_builds=20,
            timeout_sec=1,
            poll_sec=1,
            allow_no_deploy=True,
        )
        payload = {
            "number": 7,
            "result": "SUCCESS",
            "building": False,
            "description": "deployed",
            "url": "https://jenkins-back.test/7/",
        }
        with (
            mock.patch.object(ap, "_jenkins_api_get_json", return_value=payload) as api_get,
            mock.patch.object(ap, "_record_evidence"),
        ):
            ap.cmd_verify_jenkins_build(args)

        self.assertEqual("backend", api_get.call_args.kwargs["component"])
        self.assertIn("https://jenkins-back.test/7/api/json", api_get.call_args.args[0])

    def test_verify_jenkins_preserves_legacy_configuration(self) -> None:
        cfg = base_config()
        cfg["access"]["jenkins"] = {}
        cfg["jenkins"] = {
            "base_url": "https://legacy-jenkins.test",
            "job_url": "https://legacy-jenkins.test/job/backend",
            "trigger_branch": "dev",
            "image_repository": "registry.test/project/backend",
            "image_tag_strategy": "commit",
            "deploy_env": "production",
            "api_user": "legacy-user",
            "api_password": "legacy-pass",
        }
        cfg["target_env"] = {
            "health_base_url": "https://legacy-target.test",
            "health_path": "/healthz",
        }
        repo, _ = self.make_repo(config=cfg)
        (repo / "Jenkinsfile").write_text("pipeline {}\n", encoding="utf-8")

        with mock.patch.object(ap, "_record_evidence"):
            ap.cmd_verify_jenkins(argparse.Namespace(repo=str(repo), component="all"))

        self.assertEqual("", ap._resolve_jenkins_component(cfg))
        header = ap._jenkins_basic_auth_headers(cfg)["Authorization"]
        decoded = base64.b64decode(header.removeprefix("Basic ")).decode("utf-8")
        self.assertEqual("legacy-user:legacy-pass", decoded)

    def test_jenkins_crumb_cache_is_scoped_by_identity(self) -> None:
        cfg = base_config()
        cfg["access"]["jenkins"]["frontend"].update(
            {"url": "https://jenkins.test/job/frontend", "username": "front-user"}
        )
        cfg["access"]["jenkins"]["backend"].update(
            {"url": "https://jenkins.test/job/backend", "username": "back-user"}
        )

        def response(crumb: str) -> mock.MagicMock:
            value = mock.MagicMock()
            value.__enter__.return_value.read.return_value = json.dumps(
                {"crumbRequestField": "Jenkins-Crumb", "crumb": crumb}
            ).encode("utf-8")
            return value

        ap._JENKINS_CRUMB_CACHE.clear()
        self.addCleanup(ap._JENKINS_CRUMB_CACHE.clear)
        with mock.patch.object(
            ap.urllib.request,
            "urlopen",
            side_effect=[response("crumb-front"), response("crumb-back")],
        ) as urlopen:
            frontend = ap._jenkins_crumb_headers(cfg, component="frontend")
            backend = ap._jenkins_crumb_headers(cfg, component="backend")

        self.assertEqual({"Jenkins-Crumb": "crumb-front"}, frontend)
        self.assertEqual({"Jenkins-Crumb": "crumb-back"}, backend)
        self.assertEqual(2, urlopen.call_count)
        self.assertEqual(2, len(ap._JENKINS_CRUMB_CACHE))

    def test_verify_target_uses_access_project_urls_without_legacy_wait(self) -> None:
        repo, _ = self.make_repo()
        args = argparse.Namespace(
            repo=str(repo),
            backend_path=["/healthz"],
            frontend_path=["/"],
            backend_basic_auth=False,
            frontend_basic_auth=False,
        )
        with (
            mock.patch.object(ap, "_http_get", return_value=(200, "ok")) as http_get,
            mock.patch.object(ap, "_wait_for_health_url") as wait_health,
            mock.patch.object(ap, "_record_evidence"),
        ):
            ap.cmd_verify_target(args)

        self.assertEqual(
            ["https://project-back.test/healthz", "https://project-front.test/"],
            [call.args[0] for call in http_get.call_args_list],
        )
        wait_health.assert_not_called()

    def test_verify_target_missing_access_url_fails_before_network(self) -> None:
        cfg = base_config()
        cfg["access"]["project"]["backend"]["url"] = ""
        repo, _ = self.make_repo(config=cfg)
        args = argparse.Namespace(
            repo=str(repo),
            backend_path=["/healthz"],
            frontend_path=None,
            backend_basic_auth=False,
            frontend_basic_auth=False,
        )
        with (
            mock.patch.object(ap, "_http_get") as http_get,
            mock.patch.object(ap, "http_get_status") as get_status,
            mock.patch.object(ap.time, "sleep") as sleep,
        ):
            with self.assertRaisesRegex(APError, "access.project.backend.url"):
                ap.cmd_verify_target(args)

        http_get.assert_not_called()
        get_status.assert_not_called()
        sleep.assert_not_called()

    def test_verify_target_preserves_legacy_endpoint_and_health_preflight(self) -> None:
        cfg = base_config()
        cfg["access"]["project"] = {}
        cfg["jenkins"] = {"deploy_timeout_sec": 7}
        cfg["target_env"] = {
            "backend_base_url": "https://legacy-target.test/api",
            "backend_username": "legacy-user",
            "backend_password": "legacy-pass",
            "health_base_url": "https://legacy-target.test",
            "health_path": "/healthz",
        }
        repo, _ = self.make_repo(config=cfg)
        args = argparse.Namespace(
            repo=str(repo),
            backend_path=["/ready"],
            frontend_path=None,
            backend_basic_auth=False,
            frontend_basic_auth=False,
        )
        with (
            mock.patch.object(ap, "_wait_for_health_url") as wait_health,
            mock.patch.object(ap, "_http_get", return_value=(200, "ok")) as http_get,
            mock.patch.object(ap, "_record_evidence"),
        ):
            ap.cmd_verify_target(args)

        wait_health.assert_called_once_with(
            "target", "https://legacy-target.test/healthz", 7
        )
        self.assertEqual("https://legacy-target.test/api/ready", http_get.call_args.args[0])

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
