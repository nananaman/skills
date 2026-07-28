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
CREATE_PR_SKILL = SKILL_DIR.parent / "create-pr" / "SKILL.md"
HELPER = SKILL_DIR / "scripts" / "review-diff-code.py"
PROMPT_DIR = SKILL_DIR / "assets" / "reviewer-prompts"
REVIEWER_IDS = ("behavioral-safety", "design-quality", "adversarial")


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

    def _write_context_result(
        self,
        prepared: dict[str, str],
        *,
        implementation_files: list[str] | None = None,
        context_files: list[str] | None = None,
        related_files: list[dict[str, str]] | None = None,
    ) -> None:
        Path(prepared["context_result_file"]).write_text(
            json.dumps(
                {
                    "implementation_files": (
                        ["example.txt"] if implementation_files is None else implementation_files
                    ),
                    "context_files": [] if context_files is None else context_files,
                    "related_files": (
                        [{"path": "related.txt", "lines": "1"}]
                        if related_files is None
                        else related_files
                    ),
                }
            )
        )

    def test_prepare_creates_context_builder_artifacts_without_starting_an_engine(self) -> None:
        # Arrange & Act: prepare a branch review from the public CLI.
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")

        # Assert: the main agent receives a self-contained prompt/result protocol.
        run_dir = Path(prepared["run_dir"])
        self.assertTrue(run_dir.is_dir())
        self.assertEqual(run_dir.stat().st_mode & 0o777, 0o700)
        prompt = Path(prepared["context_prompt_file"]).read_text()
        self.assertIn('changed_files_json: ["example.txt"]', prompt)
        self.assertIn("+second", prompt)
        self.assertEqual(
            Path(prepared["context_result_file"]),
            run_dir / "context-builder" / "result.json",
        )
        self.assertNotIn("engine", prepared)
        self.assertNotIn("model", prepared)

    def test_route_creates_three_role_specific_prompts_from_valid_context(self) -> None:
        issue = self.repo / "docs" / "issue.md"
        issue.parent.mkdir()
        issue.write_text("ISSUE_CONTEXT_MARKER\n")
        self._git("add", "docs/issue.md")
        prepared = self._prepare("--mode", "local")
        self._write_context_result(
            prepared,
            implementation_files=[],
            context_files=["docs/issue.md"],
        )

        # Act: validate the Context Builder result and render reviewer inputs.
        result = self._run("route", "--run-dir", prepared["run_dir"])

        # Assert: impact reviewers receive context while Adversarial receives implementation only.
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
        for reviewer_id in ("behavioral-safety", "design-quality"):
            prompt = Path(routed["reviewers"][reviewer_id]["prompt_file"]).read_text()
            self.assertIn("ISSUE_CONTEXT_MARKER", prompt)
            self.assertIn("RELATED_FILE_MARKER", prompt)
        adversarial = Path(routed["reviewers"]["adversarial"]["prompt_file"]).read_text()
        self.assertNotIn("ISSUE_CONTEXT_MARKER", adversarial)
        self.assertNotIn("RELATED_FILE_MARKER", adversarial)

    def test_invalid_context_result_blocks_reviewer_routing(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        Path(prepared["context_result_file"]).write_text(
            json.dumps(
                {
                    "implementation_files": [],
                    "context_files": [],
                    "related_files": [{"path": "related.txt", "lines": "999"}],
                }
            )
        )

        # Act
        result = self._run("route", "--run-dir", prepared["run_dir"])

        # Assert: invalid classification never produces reviewer prompts.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("context builder", result.stderr.lower())
        self.assertFalse((Path(prepared["run_dir"]) / "reviewers").exists())

    def test_worktree_drift_after_prepare_blocks_reviewer_routing(self) -> None:
        (self.repo / "example.txt").write_text("dirty before prepare\n")
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        self._write_context_result(prepared)
        (self.repo / "example.txt").write_text("changed after prepare\n")

        # Act
        result = self._run("route", "--run-dir", prepared["run_dir"])

        # Assert: reviewers never receive a bundle that differs from Context Builder input.
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self._error_code(result), "repository_drift")
        self.assertFalse((Path(prepared["run_dir"]) / "reviewers").exists())

    def test_validate_context_accepts_a_complete_context_builder_result(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        self._write_context_result(prepared)

        result = self._run("validate-context", "--run-dir", prepared["run_dir"])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "valid")

    def test_validate_context_rejects_an_invalid_result_before_routing(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        Path(prepared["context_result_file"]).write_text("{}\n")

        result = self._run("validate-context", "--run-dir", prepared["run_dir"])

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self._error_code(result), "context_result_invalid")
        self.assertFalse((Path(prepared["run_dir"]) / "reviewers").exists())

    def test_validate_context_rejects_a_symlinked_result_without_reading_its_target(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        secret = self.root / "secret-context.json"
        secret.write_text(
            json.dumps(
                {
                    "implementation_files": ["example.txt"],
                    "context_files": [],
                    "related_files": [{"path": "related.txt", "lines": "1"}],
                }
            )
            + "\n"
        )
        Path(prepared["context_result_file"]).symlink_to(secret)

        result = self._run("validate-context", "--run-dir", prepared["run_dir"])

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self._error_code(result), "context_result_invalid")

    def test_validate_context_rejects_oversized_related_file_evidence(self) -> None:
        oversized = self.repo / "oversized-related.txt"
        oversized.write_text("x" * 2_000_001)
        self._git("add", "oversized-related.txt")
        self._git("commit", "-qm", "add oversized related file")
        (self.repo / "example.txt").write_text("review target\n")
        self._git("add", "example.txt")
        self._git("commit", "-qm", "add review target")
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        self._write_context_result(
            prepared,
            related_files=[{"path": "oversized-related.txt", "lines": "1"}],
        )

        result = self._run("validate-context", "--run-dir", prepared["run_dir"])

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self._error_code(result), "context_result_invalid")

    def test_reset_context_removes_a_previous_attempt_result(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        result_file = Path(prepared["context_result_file"])
        result_file.write_text('{"stale": true}\n')

        # Act
        result = self._run("reset-context", "--run-dir", prepared["run_dir"])

        # Assert: a fresh Context Builder cannot accidentally reuse the previous attempt.
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(result_file.exists())

    def test_collect_validates_reviewer_results_and_reports_partial_failure(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        self._write_context_result(prepared)
        routed_result = self._run("route", "--run-dir", prepared["run_dir"])
        self.assertEqual(routed_result.returncode, 0, routed_result.stderr)
        routed = json.loads(routed_result.stdout)
        Path(routed["reviewers"]["behavioral-safety"]["result_file"]).write_text(
            "No actionable findings.\n"
        )
        Path(routed["reviewers"]["design-quality"]["result_file"]).write_text(
            "No actionable findings\n"
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
        self._write_context_result(prepared)
        routed_result = self._run("route", "--run-dir", prepared["run_dir"])
        self.assertEqual(routed_result.returncode, 0, routed_result.stderr)
        routed = json.loads(routed_result.stdout)
        for reviewer in routed["reviewers"].values():
            Path(reviewer["result_file"]).write_text("")

        result = self._run("collect", "--run-dir", prepared["run_dir"])

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("overall_status: failed", result.stdout)

    def test_collect_rejects_repository_drift_after_reviewer_routing(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        self._write_context_result(prepared)
        routed_result = self._run("route", "--run-dir", prepared["run_dir"])
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
        self._write_context_result(prepared)
        routed_result = self._run("route", "--run-dir", prepared["run_dir"])
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
        self._write_context_result(prepared)
        (Path(prepared["run_dir"]) / "reviewers").mkdir()

        result = self._run("route", "--run-dir", prepared["run_dir"])

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self._error_code(result), "run_protocol_invalid")

    def test_repeat_route_rejects_a_modified_published_prompt(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        self._write_context_result(prepared)
        routed_result = self._run("route", "--run-dir", prepared["run_dir"])
        self.assertEqual(routed_result.returncode, 0, routed_result.stderr)
        routed = json.loads(routed_result.stdout)
        Path(routed["reviewers"]["adversarial"]["prompt_file"]).write_text("tampered\n")

        result = self._run("route", "--run-dir", prepared["run_dir"])

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self._error_code(result), "run_protocol_invalid")

    def test_collect_rejects_an_unexpected_reviewer_artifact(self) -> None:
        prepared = self._prepare("--mode", "branch", "--base", "HEAD~1")
        self._write_context_result(prepared)
        routed_result = self._run("route", "--run-dir", prepared["run_dir"])
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
        self._write_context_result(prepared)
        routed_result = self._run("route", "--run-dir", prepared["run_dir"])
        self.assertEqual(routed_result.returncode, 0, routed_result.stderr)
        manifest_file = Path(prepared["run_dir"]) / "manifest.json"
        manifest = json.loads(manifest_file.read_text())
        manifest["state"] = "prepared"
        manifest_file.write_text(json.dumps(manifest) + "\n")

        result = self._run("route", "--run-dir", prepared["run_dir"])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(manifest_file.read_text())["state"], "routed")

    def test_local_mode_includes_staged_unstaged_and_untracked_content(self) -> None:
        (self.repo / "example.txt").write_text("first\nsecond\nstaged\n")
        self._git("add", "example.txt")
        (self.repo / "example.txt").write_text("first\nsecond\nstaged\nunstaged\n")
        (self.repo / "new-file.txt").write_text("untracked marker\n")

        prepared = self._prepare("--mode", "local")

        prompt = Path(prepared["context_prompt_file"]).read_text()
        self.assertIn("+staged", prompt)
        self.assertIn("+unstaged", prompt)
        self.assertIn("untracked marker", prompt)

    def test_local_mode_does_not_follow_untracked_symbolic_links(self) -> None:
        secret = self.root / "secret.txt"
        secret.write_text("OUTSIDE_SECRET_MARKER\n")
        (self.repo / "outside-link").symlink_to(secret)

        prepared = self._prepare("--mode", "local")

        prompt = Path(prepared["context_prompt_file"]).read_text()
        self.assertIn("skipped: symbolic link", prompt)
        self.assertNotIn("OUTSIDE_SECRET_MARKER", prompt)

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
        run_dir = Path(prepared["run_dir"])
        context_dir = run_dir / "context-builder"
        external = self.root / "external-context"
        external.mkdir()
        external_prompt = external / "prompt.md"
        external_prompt.write_text("must survive\n")
        (context_dir / "prompt.md").unlink()
        context_dir.rmdir()
        context_dir.symlink_to(external, target_is_directory=True)

        # Act
        result = self._run("cleanup", "--run-dir", prepared["run_dir"])

        # Assert: cleanup does not traverse a protocol directory symlink.
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(external_prompt.exists())
        self.assertTrue(context_dir.is_symlink())

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
        self._write_context_result(prepared)
        routed_result = self._run("route", "--run-dir", prepared["run_dir"])
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
        skill = SKILL.read_text()

        # Assert: Codex owns concurrency and each reviewer gets a fresh conversation context.
        self.assertIn("spawn_agent", skill)
        self.assertIn('fork_turns="none"', skill)
        self.assertIn("context-level isolation", skill)
        self.assertNotIn("fresh sandbox", skill)
        self.assertNotIn("bundle-only", skill)

    def test_engine_process_options_are_not_part_of_the_public_interface(self) -> None:
        result = self._run("--help")

        self.assertEqual(result.returncode, 0)
        for removed_option in ("--engine", "--model", "--thinking", "--timeout-sec"):
            self.assertNotIn(removed_option, result.stdout)

    def test_reviewer_prompts_remain_standalone_templates(self) -> None:
        self.assertEqual(
            {path.stem for path in PROMPT_DIR.glob("*.md")},
            set(REVIEWER_IDS),
        )
        for path in PROMPT_DIR.glob("*.md"):
            template = path.read_text()
            self.assertIn("$change_bundle", template)
            self.assertRegex(template, r"[ぁ-んァ-ヶ一-龠]")


if __name__ == "__main__":
    unittest.main()
