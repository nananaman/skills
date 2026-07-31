from __future__ import annotations

import json
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
from contextlib import redirect_stdout


SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL = SKILL_DIR / "SKILL.md"
PROTOCOL = SKILL_DIR / "references" / "review-protocol.md"
CREATE_PR_SKILL = SKILL_DIR.parent / "create-pr" / "SKILL.md"
HELPER = SKILL_DIR / "scripts" / "review-diff-code.py"
PROMPT_DIR = SKILL_DIR / "assets" / "reviewer-prompts"
REVIEWER_IDS = ("contract-compatibility", "adversarial")


def load_helper_module():
    spec = importlib.util.spec_from_file_location("review_diff_code_helper", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReviewDiffCodeProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.runs = self.root / "runs"
        self._make_repo()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            text=True,
            capture_output=True,
            check=True,
        )

    def _make_repo(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self._git("config", "user.name", "Review Test")
        self._git("config", "user.email", "review-test@example.com")
        (self.repo / "example.txt").write_text("first\n")
        (self.repo / "related.txt").write_text("RELATED_FILE_MARKER\n")
        self._git("add", "example.txt", "related.txt")
        self._git("commit", "-qm", "first")
        (self.repo / "example.txt").write_text("first\nsecond\n")
        self._git("add", "example.txt")
        self._git("commit", "-qm", "second")

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(HELPER), *args],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=False,
        )

    def _prepare(self, *args: str) -> dict[str, str]:
        result = self._run(
            "prepare",
            "--run-root",
            str(self.runs),
            *args,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def _error_code(self, result: subprocess.CompletedProcess[str]) -> str:
        return json.loads(result.stderr)["error"]["code"]

    def _write_roster(
        self,
        reviewers: list[dict[str, str]] | None = None,
        excluded_context_paths: list[str] | None = None,
    ) -> Path:
        roster_file = self.root / "reviewers.json"
        roster_file.write_text(
            json.dumps(
                {
                    "reviewers": reviewers
                    or [
                        {
                            "id": "contract-compatibility",
                            "name": "Contract Compatibility",
                            "expertise": "API、型、CLI、設定とconsumerの境界",
                            "mission": "後方互換性と入出力contractの不整合を発見する",
                            "focus": "公開CLIの引数contract",
                            "reason": "公開APIの変更を含むため",
                        },
                    ],
                    "adversarial": {
                        "excluded_context_paths": (
                            ["plans/"]
                            if excluded_context_paths is None
                            else excluded_context_paths
                        )
                    },
                }
            )
            + "\n"
        )
        return roster_file

    def _route(self, prepared: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return self._run(
            "route",
            "--run-dir",
            prepared["run_dir"],
            "--roster-file",
            str(self._write_roster()),
        )

    def test_prepare_branch_resolves_full_ids_without_context_artifacts(self) -> None:
        # Arrange & Act: prepare a branch review from symbolic refs through the public CLI.
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")

        # Assert: the target is immutable and no diff-bearing context artifact is created.
        run_dir = Path(prepared["run_dir"])
        self.assertTrue(run_dir.is_dir())
        self.assertEqual(run_dir.stat().st_mode & 0o777, 0o700)
        self.assertRegex(prepared["target"]["base"], r"^[0-9a-f]{40}$")
        self.assertRegex(prepared["target"]["head"], r"^[0-9a-f]{40}$")
        self.assertEqual(prepared["changed_files"], ["example.txt"])
        self.assertFalse((run_dir / "context-builder").exists())
        self.assertNotIn("engine", prepared)
        self.assertNotIn("model", prepared)

    def test_prepare_commit_resolves_full_id_and_changed_paths(self) -> None:
        # Arrange & Act: prepare a commit review from a symbolic commit name.
        prepared = self._prepare("--mode", "commit", "--commit", "HEAD")

        # Assert: later ref movement cannot change the commit under review.
        self.assertRegex(prepared["target"]["commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(prepared["changed_files"], ["example.txt"])

    def test_prepare_and_load_accept_sha256_full_object_ids(self) -> None:
        sha_repo = self.root / "sha256-repo"
        initialized = subprocess.run(
            ["git", "init", "-q", "--object-format=sha256", str(sha_repo)],
            text=True,
            capture_output=True,
            check=False,
        )
        if initialized.returncode != 0:
            self.skipTest("installed Git does not support SHA-256 repositories")
        subprocess.run(["git", "-C", str(sha_repo), "config", "user.name", "Review Test"], check=True)
        subprocess.run(
            ["git", "-C", str(sha_repo), "config", "user.email", "review-test@example.com"],
            check=True,
        )
        (sha_repo / "example.txt").write_text("sha256\n")
        subprocess.run(["git", "-C", str(sha_repo), "add", "example.txt"], check=True)
        subprocess.run(["git", "-C", str(sha_repo), "commit", "-qm", "sha256"], check=True)

        # Act
        result = subprocess.run(
            [
                str(HELPER),
                "prepare",
                "--mode",
                "commit",
                "--commit",
                "HEAD",
                "--run-root",
                str(self.runs),
            ],
            cwd=sha_repo,
            text=True,
            capture_output=True,
            check=False,
        )

        # Assert: prepare and load_run both accept the repository's native full ID.
        self.assertEqual(result.returncode, 0, result.stderr)
        prepared = json.loads(result.stdout)
        self.assertRegex(prepared["target"]["commit"], r"^[0-9a-f]{64}$")
        helper = load_helper_module()
        _, manifest = helper.load_run(Path(prepared["run_dir"]))
        self.assertEqual(manifest["target"]["commit"], prepared["target"]["commit"])

    def test_route_creates_small_direct_investigation_prompts(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")

        # Act: render reviewer inputs from a fixed Git target.
        result = self._route(prepared)

        # Assert: prompts point reviewers at Git without embedding the diff body.
        self.assertEqual(result.returncode, 0, result.stderr)
        routed = json.loads(result.stdout)
        self.assertEqual(set(routed["reviewers"]), set(REVIEWER_IDS))
        reviewer_root = Path(prepared["run_dir"]) / "reviewers"
        self.assertEqual(
            {
                Path(reviewer["prompt_file"]).parent.parent
                for reviewer in routed["reviewers"].values()
            },
            {reviewer_root},
        )
        contract_prompt = Path(
            routed["reviewers"]["contract-compatibility"]["prompt_file"]
        ).read_text()
        self.assertIn("API、型、CLI、設定とconsumerの境界", contract_prompt)
        self.assertIn("後方互換性と入出力contractの不整合を発見する", contract_prompt)
        self.assertIn("公開CLIの引数contract", contract_prompt)
        self.assertIn("今回の重点は優先事項であり、探索範囲を限定しない", contract_prompt)
        target = prepared["target"]
        self.assertIn(f"diff --find-renames {target['base']}...{target['head']}", contract_prompt)
        manifest = json.loads((Path(prepared["run_dir"]) / "manifest.json").read_text())
        self.assertIn(f"git -C {manifest['repo']}", contract_prompt)
        self.assertIn("example.txt", contract_prompt)
        self.assertIn("read-only", contract_prompt)
        self.assertNotIn("+second", contract_prompt)

    def test_route_keeps_adversarial_blind_to_selection_and_context_paths(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        roster = self._write_roster(
            excluded_context_paths=["plans/", "docs/design/"],
        )

        # Act
        result = self._run(
            "route",
            "--run-dir",
            prepared["run_dir"],
            "--roster-file",
            str(roster),
        )

        # Assert: Adversarial receives only fixed-target and context-exclusion guidance.
        self.assertEqual(result.returncode, 0, result.stderr)
        routed = json.loads(result.stdout)
        adversarial = Path(routed["reviewers"]["adversarial"]["prompt_file"]).read_text()
        self.assertIn("plans/", adversarial)
        self.assertIn("docs/design/", adversarial)
        self.assertIn("Do not inspect", adversarial)
        self.assertIn(":(top,literal,exclude)plans", adversarial)
        self.assertNotIn('"plans/', adversarial.split("変更path:", 1)[1].split("```", 2)[1])
        self.assertNotIn("公開CLIの引数contract", adversarial)
        self.assertNotIn("公開APIの変更を含むため", adversarial)

    def test_adversarial_command_literally_excludes_file_directory_and_glob_paths(self) -> None:
        # Arrange: commit context-only names whose metacharacters must remain literal.
        (self.repo / "plans").mkdir()
        (self.repo / "plans" / "secret.md").write_text("DIRECTORY_SECRET\n")
        (self.repo / "literal[1].md").write_text("GLOB_SECRET\n")
        control_path = self.repo / "line\nbreak.md"
        control_path.write_text("CONTROL_SECRET\n")
        (self.repo / "visible.md").write_text("VISIBLE\n")
        self._git("add", ".")
        self._git("commit", "-qm", "context paths")
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        roster = self._write_roster(
            excluded_context_paths=["plans", "literal[1].md", "line\nbreak.md"],
        )
        routed_result = self._run(
            "route",
            "--run-dir",
            prepared["run_dir"],
            "--roster-file",
            str(roster),
        )
        self.assertEqual(routed_result.returncode, 0, routed_result.stderr)
        routed = json.loads(routed_result.stdout)
        prompt = Path(routed["reviewers"]["adversarial"]["prompt_file"]).read_text()
        command = prompt.split("```sh\n", 1)[1].split("\n```", 1)[0]

        # Act
        command_result = subprocess.run(
            command,
            shell=True,
            text=True,
            capture_output=True,
            check=True,
        )

        # Assert: only reviewable implementation content reaches command output.
        self.assertIn("VISIBLE", command_result.stdout)
        self.assertNotIn("DIRECTORY_SECRET", command_result.stdout)
        self.assertNotIn("GLOB_SECRET", command_result.stdout)
        self.assertNotIn("CONTROL_SECRET", command_result.stdout)
        inventory = prompt.split("変更path:\n```json\n", 1)[1].split("\n```", 1)[0]
        self.assertNotIn("plans", inventory)
        self.assertNotIn("literal[1].md", inventory)
        self.assertNotIn(r"line\nbreak.md", inventory)

    def test_route_rejects_the_legacy_array_roster(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        roster = self.root / "legacy-roster.json"
        roster.write_text("[]\n")

        # Act
        result = self._run(
            "route",
            "--run-dir",
            prepared["run_dir"],
            "--roster-file",
            str(roster),
        )

        # Assert
        self.assertEqual(self._error_code(result), "reviewer_roster_invalid")
        self.assertFalse((Path(prepared["run_dir"]) / "reviewers").exists())

    def test_route_rejects_unsafe_excluded_context_paths(self) -> None:
        for unsafe in ("/tmp/plans", "../plans", "docs/../plans"):
            with self.subTest(unsafe=unsafe):
                prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
                roster = self._write_roster(excluded_context_paths=[unsafe])

                # Act
                result = self._run(
                    "route",
                    "--run-dir",
                    prepared["run_dir"],
                    "--roster-file",
                    str(roster),
                )

                # Assert
                self.assertEqual(self._error_code(result), "reviewer_roster_invalid")
                self.assertFalse((Path(prepared["run_dir"]) / "reviewers").exists())

    def test_route_rejects_an_oversized_prompt_before_publication(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        helper = load_helper_module()

        # Act: force the public prompt contract below the smallest valid prompt.
        with mock.patch.object(helper, "MAX_REVIEWER_PROMPT_BYTES", 10):
            with self.assertRaises(helper.ReviewError) as raised:
                helper.route_review(
                    SimpleNamespace(
                        run_dir=Path(prepared["run_dir"]),
                        roster_file=self._write_roster(),
                    )
                )

        # Assert: an invalid prompt never reaches the published artifact location.
        self.assertEqual(raised.exception.code, "run_protocol_invalid")
        self.assertFalse((Path(prepared["run_dir"]) / "reviewers").exists())

    def test_route_rejects_a_prompt_equal_to_the_size_limit(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        helper = load_helper_module()

        # Act
        with (
            mock.patch.object(helper, "MAX_REVIEWER_PROMPT_BYTES", 10),
            mock.patch.object(helper, "build_reviewer_prompt", return_value="1234567890"),
        ):
            with self.assertRaises(helper.ReviewError):
                helper.route_review(
                    SimpleNamespace(
                        run_dir=Path(prepared["run_dir"]),
                        roster_file=self._write_roster(),
                    )
                )

        # Assert
        self.assertFalse((Path(prepared["run_dir"]) / "reviewers").exists())

    def test_local_prompt_uses_fixed_head_and_safe_untracked_contract(self) -> None:
        (self.repo / "new.txt").write_text("new\n")
        prepared = self._prepare("--mode", "local")

        # Act
        result = self._route(prepared)

        # Assert
        self.assertEqual(result.returncode, 0, result.stderr)
        routed = json.loads(result.stdout)
        prompt = Path(routed["reviewers"]["adversarial"]["prompt_file"]).read_text()
        self.assertIn(f"diff --find-renames {prepared['target']['head']}", prompt)
        self.assertIn(f"diff --cached --find-renames {prepared['target']['head']}", prompt)
        self.assertIn("untracked symbolic link", prompt)
        self.assertIn("lstat", prompt)
        self.assertIn("readlink", prompt)
        self.assertIn("dereference", prompt)
        dynamic = Path(
            routed["reviewers"]["contract-compatibility"]["prompt_file"]
        ).read_text()
        self.assertIn("untracked symbolic link", dynamic)
        self.assertIn("lstat", dynamic)
        self.assertIn("readlink", dynamic)
        self.assertIn("dereference", dynamic)

    def test_manifest_target_rejects_shell_injection_before_prompt_render(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        manifest_file = Path(prepared["run_dir"]) / "manifest.json"
        manifest = json.loads(manifest_file.read_text())
        manifest["target"]["head"] = "$(touch /tmp/review-diff-code-injected)"
        manifest_file.write_text(json.dumps(manifest) + "\n")

        # Act
        result = self._route(prepared)

        # Assert
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(Path("/tmp/review-diff-code-injected").exists())

    def test_prompt_inventory_escapes_control_characters_in_changed_paths(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        manifest_file = Path(prepared["run_dir"]) / "manifest.json"
        manifest = json.loads(manifest_file.read_text())
        manifest["changed_files"] = ["line\nbreak.txt"]
        helper = load_helper_module()

        # Act
        prompt = helper.build_reviewer_prompt(
            {
                "id": "contract-compatibility",
                "name": "Contract",
                "expertise": "contracts",
                "mission": "find breaks",
                "focus": "CLI",
                "reason": "CLI changed",
            },
            manifest,
            Path(prepared["run_dir"]) / "result.md",
            [],
        )

        # Assert
        self.assertIn(r"line\nbreak.txt", prompt)
        self.assertNotIn("line\nbreak.txt", prompt)

    def test_repository_digest_changes_when_untracked_mode_changes(self) -> None:
        path = self.repo / "script.sh"
        path.write_text("#!/bin/sh\n")
        helper = load_helper_module()
        before = helper.repository_state_digest(self.repo)

        # Act
        path.chmod(0o755)

        # Assert
        self.assertNotEqual(helper.repository_state_digest(self.repo), before)

    def test_route_rejects_more_than_two_dynamic_reviewers(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        roster = self._write_roster(
            [
                {
                    "id": "contract-compatibility",
                    "name": "Contract Compatibility",
                    "expertise": "APIとconsumerの境界",
                    "mission": "互換性違反を発見する",
                    "focus": "公開API",
                    "reason": "公開APIの変更を含むため",
                },
                {
                    "id": "security",
                    "name": "Security",
                    "expertise": "認証と認可の境界",
                    "mission": "権限逸脱を発見する",
                    "focus": "認証処理",
                    "reason": "認証処理を含むため",
                },
                {
                    "id": "data-integrity",
                    "name": "Data Integrity",
                    "expertise": "永続化とtransaction",
                    "mission": "部分更新とデータ欠落を発見する",
                    "focus": "保存処理",
                    "reason": "永続状態を変更するため",
                },
            ]
        )

        # Act: route more dynamic specialists than the concurrency contract permits.
        result = self._run(
            "route",
            "--run-dir",
            prepared["run_dir"],
            "--roster-file",
            str(roster),
        )

        # Assert: invalid orchestration cannot publish reviewer artifacts.
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self._error_code(result), "reviewer_roster_invalid")
        self.assertFalse((Path(prepared["run_dir"]) / "reviewers").exists())

    def test_route_rejects_the_removed_question_field(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        roster_object = json.loads(self._write_roster().read_text())
        reviewers = roster_object["reviewers"]
        reviewers[0]["question"] = "公開contractを壊す変更があるか"
        roster = self._write_roster(reviewers)

        # Act: route a roster using the former question-based contract.
        result = self._run(
            "route",
            "--run-dir",
            prepared["run_dir"],
            "--roster-file",
            str(roster),
        )

        # Assert: a concrete question cannot replace specialist expertise and ownership.
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self._error_code(result), "reviewer_roster_invalid")
        self.assertFalse((Path(prepared["run_dir"]) / "reviewers").exists())

    def test_worktree_drift_after_prepare_blocks_reviewer_routing(self) -> None:
        (self.repo / "example.txt").write_text("dirty before prepare\n")
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        (self.repo / "example.txt").write_text("changed after prepare\n")

        # Act
        result = self._route(prepared)

        # Assert: reviewers never receive a target that differs from prepare state.
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self._error_code(result), "repository_drift")
        self.assertFalse((Path(prepared["run_dir"]) / "reviewers").exists())

    def test_collect_validates_reviewer_results_and_reports_partial_failure(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        routed_result = self._route(prepared)
        self.assertEqual(routed_result.returncode, 0, routed_result.stderr)
        routed = json.loads(routed_result.stdout)
        Path(routed["reviewers"]["contract-compatibility"]["result_file"]).write_text(
            "No actionable findings.\n"
        )
        Path(routed["reviewers"]["adversarial"]["result_file"]).write_text("")

        # Act
        result = self._run("collect", "--run-dir", prepared["run_dir"])

        # Assert: valid results remain usable but an invalid reviewer forbids a clean result.
        self.assertEqual(result.returncode, 0)
        self.assertIn("overall_status: partial_failure", result.stdout)
        self.assertIn("| Adversarial | protocol_failure(empty_output) |", result.stdout)

    def test_collect_returns_nonzero_when_all_reviewer_results_are_invalid(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        routed_result = self._route(prepared)
        self.assertEqual(routed_result.returncode, 0, routed_result.stderr)
        routed = json.loads(routed_result.stdout)
        for reviewer in routed["reviewers"].values():
            Path(reviewer["result_file"]).write_text("")

        result = self._run("collect", "--run-dir", prepared["run_dir"])

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("overall_status: failed", result.stdout)

    def test_collect_rejects_repository_drift_after_reviewer_routing(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        routed_result = self._route(prepared)
        self.assertEqual(routed_result.returncode, 0, routed_result.stderr)
        routed = json.loads(routed_result.stdout)
        for reviewer in routed["reviewers"].values():
            Path(reviewer["result_file"]).write_text("No actionable findings.\n")
        (self.repo / "example.txt").write_text("changed during review\n")

        result = self._run("collect", "--run-dir", prepared["run_dir"])

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self._error_code(result), "repository_drift")
        self.assertNotIn("overall_status: success", result.stdout)

    def test_collect_rejects_repository_drift_during_result_collection(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        routed_result = self._route(prepared)
        self.assertEqual(routed_result.returncode, 0, routed_result.stderr)
        routed = json.loads(routed_result.stdout)
        for reviewer in routed["reviewers"].values():
            Path(reviewer["result_file"]).write_text("No actionable findings.\n")
        helper = load_helper_module()
        original_reader = helper.read_reviewer_result
        changed = False

        def read_and_mutate(path: Path):
            nonlocal changed
            result = original_reader(path)
            if not changed:
                (self.repo / "example.txt").write_text("changed during collect\n")
                changed = True
            return result

        with mock.patch.object(helper, "read_reviewer_result", side_effect=read_and_mutate):
            with redirect_stdout(io.StringIO()):
                with self.assertRaises(helper.ReviewError) as raised:
                    helper.collect_review(
                        SimpleNamespace(run_dir=Path(prepared["run_dir"]))
                    )

        self.assertEqual(raised.exception.code, "repository_drift")

    def test_route_refuses_a_preexisting_reviewer_artifact_root(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        (Path(prepared["run_dir"]) / "reviewers").mkdir()

        result = self._route(prepared)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self._error_code(result), "run_protocol_invalid")

    def test_repeat_route_rejects_a_modified_published_prompt(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        routed_result = self._route(prepared)
        self.assertEqual(routed_result.returncode, 0, routed_result.stderr)
        routed = json.loads(routed_result.stdout)
        Path(routed["reviewers"]["adversarial"]["prompt_file"]).write_text("tampered\n")

        result = self._route(prepared)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self._error_code(result), "run_protocol_invalid")

    def test_collect_rejects_an_unexpected_reviewer_artifact(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        routed_result = self._route(prepared)
        self.assertEqual(routed_result.returncode, 0, routed_result.stderr)
        routed = json.loads(routed_result.stdout)
        for reviewer in routed["reviewers"].values():
            Path(reviewer["result_file"]).write_text("No actionable findings.\n")
        (Path(prepared["run_dir"]) / "reviewers" / "unexpected.txt").write_text("extra\n")

        result = self._run("collect", "--run-dir", prepared["run_dir"])

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self._error_code(result), "run_protocol_invalid")

    def test_route_recovers_a_complete_publication_before_manifest_update(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        routed_result = self._route(prepared)
        self.assertEqual(routed_result.returncode, 0, routed_result.stderr)
        manifest_file = Path(prepared["run_dir"]) / "manifest.json"
        manifest = json.loads(manifest_file.read_text())
        manifest["state"] = "prepared"
        manifest_file.write_text(json.dumps(manifest) + "\n")

        result = self._route(prepared)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(manifest_file.read_text())["state"], "routed")

    def test_route_recovery_rejects_repository_drift(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        routed_result = self._route(prepared)
        self.assertEqual(routed_result.returncode, 0, routed_result.stderr)
        manifest_file = Path(prepared["run_dir"]) / "manifest.json"
        manifest = json.loads(manifest_file.read_text())
        manifest["state"] = "prepared"
        manifest_file.write_text(json.dumps(manifest) + "\n")
        (self.repo / "example.txt").write_text("drift\n")

        # Act
        result = self._route(prepared)

        # Assert
        self.assertEqual(self._error_code(result), "repository_drift")

    def test_cleanup_rejects_an_invalid_manifest_reviewer_id(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        routed_result = self._route(prepared)
        self.assertEqual(routed_result.returncode, 0, routed_result.stderr)
        manifest_file = Path(prepared["run_dir"]) / "manifest.json"
        manifest = json.loads(manifest_file.read_text())
        manifest["reviewers"][0]["id"] = "../outside"
        manifest_file.write_text(json.dumps(manifest) + "\n")

        # Act
        result = self._run("cleanup", "--run-dir", prepared["run_dir"])

        # Assert
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(Path(prepared["run_dir"]).exists())

    def test_prepare_local_inventories_staged_unstaged_and_untracked_paths(self) -> None:
        # Arrange: create one path with staged and unstaged edits plus one untracked path.
        (self.repo / "example.txt").write_text("first\nsecond\nstaged\n")
        self._git("add", "example.txt")
        (self.repo / "example.txt").write_text("first\nsecond\nstaged\nunstaged\n")
        (self.repo / "new-file.txt").write_text("untracked marker\n")

        # Act
        prepared = self._prepare("--mode", "local")

        # Assert: local inventory covers every worktree state without embedding contents.
        self.assertRegex(prepared["target"]["head"], r"^[0-9a-f]{40}$")
        self.assertEqual(prepared["changed_files"], ["example.txt", "new-file.txt"])
        self.assertNotIn("context_prompt_file", prepared)

    def test_local_mode_does_not_follow_untracked_symbolic_links(self) -> None:
        secret = self.root / "secret.txt"
        secret.write_text("OUTSIDE_SECRET_MARKER\n")
        (self.repo / "outside-link").symlink_to(secret)

        prepared = self._prepare("--mode", "local")

        # Assert: inventory includes the path but prepare never exposes target contents.
        self.assertIn("outside-link", prepared["changed_files"])
        self.assertNotIn("OUTSIDE_SECRET_MARKER", json.dumps(prepared))

    def test_cleanup_removes_only_a_helper_owned_run_directory(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        unrelated = self.root / "unrelated"
        unrelated.mkdir()

        result = self._run("cleanup", "--run-dir", prepared["run_dir"])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(Path(prepared["run_dir"]).exists())
        self.assertTrue(unrelated.exists())

    def test_cleanup_refuses_a_run_directory_with_unknown_content(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        unknown = Path(prepared["run_dir"]) / "unknown.txt"
        unknown.write_text("must survive\n")

        # Act
        result = self._run("cleanup", "--run-dir", prepared["run_dir"])

        # Assert: cleanup never recursively deletes files outside its protocol.
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(unknown.exists())
        self.assertTrue(Path(prepared["run_dir"]).exists())

    def test_cleanup_refuses_a_symlinked_protocol_directory(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        routed = self._route(prepared)
        self.assertEqual(routed.returncode, 0, routed.stderr)
        run_dir = Path(prepared["run_dir"])
        reviewers_dir = run_dir / "reviewers"
        external = self.root / "external-reviewers"
        external.mkdir()
        external_prompt = external / "prompt.md"
        external_prompt.write_text("must survive\n")
        for path in reviewers_dir.rglob("*"):
            if path.is_file():
                path.unlink()
        for path in sorted(reviewers_dir.iterdir(), reverse=True):
            path.rmdir()
        reviewers_dir.rmdir()
        reviewers_dir.symlink_to(external, target_is_directory=True)

        # Act
        result = self._run("cleanup", "--run-dir", prepared["run_dir"])

        # Assert: cleanup does not traverse a protocol directory symlink.
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(external_prompt.exists())
        self.assertTrue(reviewers_dir.is_symlink())

    def test_manifest_update_failure_preserves_the_previous_manifest(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        run_dir = Path(prepared["run_dir"])
        manifest_file = run_dir / "manifest.json"
        previous = manifest_file.read_text()
        helper = load_helper_module()

        with mock.patch.object(helper.os, "replace", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                helper.write_manifest(run_dir, {"state": "routed"})

        self.assertEqual(manifest_file.read_text(), previous)

    def test_cleanup_rejects_symlinked_run_metadata(self) -> None:
        for metadata_name in (".review-diff-code-run", "manifest.json"):
            with self.subTest(metadata_name=metadata_name):
                prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
                metadata = Path(prepared["run_dir"]) / metadata_name
                external = self.root / f"external-{metadata_name.lstrip('.')}"
                external.write_text(metadata.read_text())
                metadata.unlink()
                metadata.symlink_to(external)

                result = self._run("cleanup", "--run-dir", prepared["run_dir"])

                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(external.exists())

    def test_collect_rejects_a_symlinked_result_without_printing_its_target(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        routed_result = self._route(prepared)
        self.assertEqual(routed_result.returncode, 0, routed_result.stderr)
        routed = json.loads(routed_result.stdout)
        secret = self.root / "secret.txt"
        secret.write_text("OUTSIDE_SECRET_MARKER\n")
        for reviewer_id, reviewer in routed["reviewers"].items():
            result_file = Path(reviewer["result_file"])
            if reviewer_id == "adversarial":
                result_file.symlink_to(secret)
            else:
                result_file.write_text("No actionable findings.\n")

        # Act
        result = self._run("collect", "--run-dir", prepared["run_dir"])

        # Assert: invalid output is reported without echoing untrusted file contents.
        self.assertEqual(result.returncode, 0)
        self.assertIn("| Adversarial | protocol_failure(invalid_result_file) |", result.stdout)
        self.assertNotIn("OUTSIDE_SECRET_MARKER", result.stdout)

    def test_create_pr_delegates_review_gate_to_the_skill_contract(self) -> None:
        create_pr = CREATE_PR_SKILL.read_text()

        self.assertIn("`review-diff-code`", create_pr)
        self.assertNotIn("review-diff-code.py --mode", create_pr)

    def test_skill_delegates_reviewers_to_fresh_subagents(self) -> None:
        # Arrange & Act: read the model-facing orchestration contract.
        skill = SKILL.read_text() + PROTOCOL.read_text()

        # Assert: Codex owns concurrency and each reviewer gets a fresh conversation context.
        self.assertIn("spawn_agent", skill)
        self.assertIn('fork_turns="none"', skill)
        self.assertIn("context-level isolation", skill)
        self.assertNotIn("fresh sandbox", skill)
        self.assertNotIn("bundle-only", skill)

    def test_skill_uses_a_cost_effective_reviewer_model_with_high_reasoning(self) -> None:
        # Arrange & Act: read the model-facing orchestration contract.
        skill = SKILL.read_text() + PROTOCOL.read_text()

        # Assert: reviewer quality and cost are selected by capability, not a fixed model ID.
        self.assertIn("安価側model", skill)
        self.assertIn("reasoning / thinkingは`high`", skill)
        self.assertIn("model名は固定しない", skill)
        self.assertIn("既定model", skill)

    def test_engine_process_options_are_not_part_of_the_public_interface(self) -> None:
        result = self._run("--help")

        self.assertEqual(result.returncode, 0)
        for removed_option in ("--engine", "--model", "--thinking", "--timeout-sec"):
            self.assertNotIn(removed_option, result.stdout)
        self.assertNotIn("reset-context", result.stdout)
        self.assertNotIn("validate-context", result.stdout)

    def test_reviewer_prompts_remain_standalone_templates(self) -> None:
        self.assertEqual(
            {path.stem for path in PROMPT_DIR.glob("*.md")},
            {"reviewer", "adversarial"},
        )
        for path in PROMPT_DIR.glob("*.md"):
            template = path.read_text()
            self.assertIn("$investigation_command", template)
            self.assertIn("$changed_files_json", template)
            self.assertIn("$result_file", template)
            self.assertRegex(template, r"[ぁ-んァ-ヶ一-龠]")


if __name__ == "__main__":
    unittest.main()
