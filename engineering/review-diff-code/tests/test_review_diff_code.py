from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL = SKILL_DIR / "SKILL.md"
HELPER = SKILL_DIR / "scripts" / "review-diff-code.py"
LEGACY_HELPER = SKILL_DIR / "scripts" / "review-diff-code"
PROMPT_DIR = SKILL_DIR / "assets" / "reviewer-prompts"
CONTEXT_BUILDER_PROMPT = SKILL_DIR / "assets" / "context-builder.md"
REVIEWER_IDS = {"behavioral-safety", "design-quality", "adversarial"}


FAKE_ENGINE = r"""#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys
import time

prompt = sys.stdin.read()
first_line = prompt.splitlines()[0]
title = next(
    title for marker, title in (
        ("Context Builder", "Context Builder"),
        ("Behavioral Safety", "Behavioral Safety"),
        ("Design Quality", "Design Quality"),
        ("adversarial", "Adversarial"),
    ) if marker in first_line
)
stem = Path(os.environ["FAKE_CAPTURE_DIR"]) / f"{title.replace(' ', '_').replace('/', '_')}.{os.getpid()}"
Path(str(stem) + ".prompt").write_text(prompt)
Path(str(stem) + ".cwd").write_text(str(Path.cwd()) + "\n")
Path(str(stem) + ".args").write_text("\n".join(sys.argv[1:]) + "\n")
print("FAKE_ENGINE_STDERR_MARKER", file=sys.stderr)
if title == "Context Builder":
    if os.getenv("FAKE_MALFORMED_CONTEXT_BUILDER"):
        print("not json")
        raise SystemExit(0)
    changed_line = next(line for line in prompt.splitlines() if line.startswith("changed_files_json: "))
    changed_files = json.loads(changed_line.removeprefix("changed_files_json: "))
    context_files = [path for path in changed_files if "issue" in path.lower()]
    implementation_files = [path for path in changed_files if path not in context_files]
    if os.getenv("FAKE_INCOMPLETE_CLASSIFICATION_CONTEXT_BUILDER"):
        implementation_files = implementation_files[1:]
    output = {
        "implementation_files": implementation_files,
        "context_files": context_files,
        "related_files": [{"path": "related.txt", "lines": "1"}],
    }
    if os.getenv("FAKE_INVALID_RELATED_FILE_CONTEXT_BUILDER"):
        output["related_files"] = [{"path": "related.txt", "lines": 1}]
    if os.getenv("FAKE_INVALID_RELATED_LINES_CONTEXT_BUILDER"):
        output["related_files"][0]["lines"] = "999"
    print(json.dumps(output))
    raise SystemExit(0)
if os.getenv("FAKE_FAIL_REVIEWER") in (title, "all"):
    print("Error: simulated reviewer failure", file=sys.stderr)
    raise SystemExit(7)
if os.getenv("FAKE_SLEEP_REVIEWER") == title:
    time.sleep(10)
if os.getenv("FAKE_EMPTY_REVIEWER") == title:
    raise SystemExit(0)
if os.getenv("FAKE_PREFIXED_SENTINEL_REVIEWER") == title:
    print("unrequested preface")
    print("No actionable findings.")
    raise SystemExit(0)
if os.getenv("FAKE_NO_PERIOD_REVIEWER") == title:
    print("No actionable findings")
    raise SystemExit(0)
if os.getenv("FAKE_HEADING_ONLY_REVIEWER") == title:
    print("### [medium] Incomplete finding")
    raise SystemExit(0)
if os.getenv("FAKE_DIRECT_FINDING_REVIEWER") == title:
    print("### [medium] Direct finding without section heading")
    print("- Target: example.txt:1")
    print("- Problem: example problem")
    print("- Evidence: example evidence")
    print("- Suggested fix: example fix")
    raise SystemExit(0)
print("No actionable findings.")
"""


FAKE_BWRAP = r"""#!/usr/bin/env python3
import os
from pathlib import Path
import sys

prompt = sys.stdin.read()
capture = Path(os.environ["FAKE_CAPTURE_DIR"])
(capture / "bwrap.args").write_text("\n".join(sys.argv[1:]) + "\n")
first_line = prompt.splitlines()[0]
title = next(
    title for marker, title in (
        ("Behavioral Safety", "Behavioral Safety"),
        ("Design Quality", "Design Quality"),
        ("adversarial", "Adversarial"),
    ) if marker in first_line
)
(capture / f"{title.replace(' ', '_')}.{os.getpid()}.prompt").write_text(prompt)
print("No actionable findings.")
"""


class ReviewDiffCodeCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.bin = self.root / "bin"
        self.capture = self.root / "capture"
        self.bin.mkdir()
        self.capture.mkdir()
        self._make_repo()
        self._write_executable("pi", FAKE_ENGINE)

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

    def _write_executable(self, name: str, content: str) -> Path:
        path = self.bin / name
        path.write_text(textwrap.dedent(content))
        path.chmod(0o755)
        return path

    def _run(self, *args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("HERDR_ENV", None)
        env.update(
            {
                "PATH": f"{self.bin}:{env['PATH']}",
                "FAKE_CAPTURE_DIR": str(self.capture),
            }
        )
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [str(HELPER), *args],
            cwd=self.repo,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def _prepare_herdr_review(self) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        result = self._run(
            "--engine", "pi", "--mode", "branch", "--base", "HEAD~1",
            extra_env={"HERDR_ENV": "1", "TMPDIR": str(self.root)},
        )
        manifest = json.loads(result.stdout) if result.returncode == 0 else {}
        return result, manifest

    def _captured_prompt(self, title: str) -> Path:
        matches = list(self.capture.glob(f"{title.replace(' ', '_')}.*.prompt"))
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_python_entrypoint_is_the_only_review_runner(self) -> None:
        self.assertTrue(HELPER.is_file())
        self.assertTrue(os.access(HELPER, os.X_OK))
        self.assertFalse(LEGACY_HELPER.exists())

    def test_skill_routes_semantic_closeout_changes_without_excluding_normal_fixes(self) -> None:
        # Arrange & Act: metadata is the public discovery contract for model invocation.
        description = next(
            line.removeprefix("description: ")
            for line in SKILL.read_text().splitlines()
            if line.startswith("description: ")
        )

        # Assert: semantic implementation surfaces route to review, with only non-semantic diffs skippable.
        for trigger in ("コード", "設定", "テスト", "schema", "依存関係", "agent指示", "closeout review"):
            self.assertIn(trigger, description)
        for skippable in ("コメント", "誤字", "空白", "formatter"):
            self.assertIn(skippable, description)
        self.assertNotIn("通常実装、修正だけの依頼では使わない", description)

    def test_skill_routes_every_herdr_session_to_visible_reviewer_panes(self) -> None:
        # Arrange & Act: the body is the orchestration contract followed by the main agent.
        skill = SKILL.read_text()

        # Assert: Herdr is unconditional, non-focusing, and collected through the helper protocol.
        self.assertIn("`HERDR_ENV=1`なら、無条件にHerdr branchへ進む", skill)
        self.assertIn("--no-focus", skill)
        self.assertIn("--collect <run_dir>", skill)
        self.assertIn("preflight失敗時は他engineへfallbackせず停止", skill)

    def test_skill_uses_and_closes_a_dedicated_review_tab(self) -> None:
        # Arrange & Act: the skill body is the public Herdr layout and cleanup contract.
        skill = SKILL.read_text()

        # Assert: review panes never shrink the main tab and only the run-owned tab is closed.
        self.assertIn("herdr tab create", skill)
        self.assertIn("review専用tab", skill)
        self.assertIn("herdr tab close <review-tab-id>", skill)
        self.assertIn("既存tabをcloseしない", skill)
        self.assertIn("review専用tab作成後の全失敗", skill)
        self.assertIn("作成成功して保存済みのpane IDだけ", skill)
        self.assertIn("現在のpane ID集合と保存済みpane ID集合が完全一致", skill)

    def test_skill_collects_missing_herdr_results_before_cleanup(self) -> None:
        # Arrange & Act: the skill body defines how incomplete reviewer output is finalized.
        skill = SKILL.read_text()

        # Assert: missing files become reviewer statuses instead of bypassing collection.
        self.assertIn("result.md`の有無にかかわらず", skill)
        self.assertIn("failed(missing_result)", skill)
        self.assertIn("status化してからcleanup", skill)

    def test_panel_option_is_not_part_of_the_public_interface(self) -> None:
        result = self._run("--panel", "legacy")
        help_result = self._run("--help")

        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments: --panel legacy", result.stderr)
        self.assertNotIn("--panel", help_result.stdout)

    def test_context_builder_runs_first_and_reviewers_are_bundle_only(self) -> None:
        result = self._run("--engine", "pi", "--mode", "branch", "--base", "HEAD~1")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("| Behavioral Safety | success |", result.stdout)
        self.assertIn("| Design Quality | success |", result.stdout)
        self.assertIn("| Adversarial | success |", result.stdout)
        self.assertEqual(len(list(self.capture.glob("*.prompt"))), 4)
        builder = self._captured_prompt("Context Builder")
        builder_stem = str(builder).removesuffix(".prompt")
        self.assertEqual(
            Path(Path(builder_stem + ".cwd").read_text().strip()).resolve(),
            self.repo.resolve(),
        )
        self.assertIn("read,grep,find,ls", Path(builder_stem + ".args").read_text())
        for title in ("Behavioral Safety", "Design Quality", "Adversarial"):
            reviewer = self._captured_prompt(title)
            stem = str(reviewer).removesuffix(".prompt")
            self.assertNotEqual(Path(stem + ".cwd").read_text().strip(), str(self.repo))
            self.assertNotIn("read,grep,find,ls", Path(stem + ".args").read_text())
        reviewer_cwds = {
            self._captured_prompt(title).with_suffix(".cwd").read_text().strip()
            for title in ("Behavioral Safety", "Design Quality", "Adversarial")
        }
        self.assertEqual(len(reviewer_cwds), 3)
        self.assertIn("RELATED_FILE_MARKER", self._captured_prompt("Behavioral Safety").read_text())
        self.assertIn("RELATED_FILE_MARKER", self._captured_prompt("Design Quality").read_text())
        self.assertNotIn("RELATED_FILE_MARKER", self._captured_prompt("Adversarial").read_text())

    def test_herdr_environment_prepares_visible_review_without_starting_reviewers(self) -> None:
        # Arrange & Act: Herdr routing is selected only from the public environment contract.
        result, manifest = self._prepare_herdr_review()

        # Assert: the helper hands reviewer startup to the main agent and materializes isolated workspaces.
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(manifest["status"], "prepared")
        self.assertEqual(manifest["orchestrator"], "herdr")
        self.assertEqual(len(list(self.capture.glob("*.prompt"))), 1)
        reviewers = manifest["reviewers"]
        self.assertEqual({reviewer["id"] for reviewer in reviewers}, REVIEWER_IDS)
        for reviewer in reviewers:
            workspace = Path(reviewer["cwd"])
            self.assertTrue((workspace / "prompt.md").is_file())
            self.assertTrue((workspace / "task.md").is_file())
            self.assertEqual(Path(reviewer["result"]), workspace / "result.md")

    def test_collect_validates_results_written_by_herdr_reviewers(self) -> None:
        # Arrange: prepare a run and emulate the three visible reviewer panes completing successfully.
        prepare_result, manifest = self._prepare_herdr_review()
        self.assertEqual(prepare_result.returncode, 0, prepare_result.stderr)
        for reviewer in manifest["reviewers"]:
            Path(reviewer["result"]).write_text("No actionable findings.\n")

        # Act: collect is a separate deterministic phase after pane orchestration.
        result = self._run("--collect", manifest["run_dir"])

        # Assert: collection preserves the existing reviewer protocol and summary contract.
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("overall_status: success", result.stdout)
        self.assertIn("orchestrator: herdr", result.stdout)

    def test_collect_does_not_report_clean_when_a_herdr_reviewer_is_incomplete(self) -> None:
        # Arrange: only two of three panes have produced protocol-valid results.
        prepare_result, manifest = self._prepare_herdr_review()
        self.assertEqual(prepare_result.returncode, 0, prepare_result.stderr)
        for reviewer in manifest["reviewers"][:2]:
            Path(reviewer["result"]).write_text("No actionable findings.\n")

        # Act
        result = self._run("--collect", manifest["run_dir"])

        # Assert: an incomplete visible review cannot become a clean gate.
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("overall_status: partial_failure", result.stdout)
        self.assertIn("failed(missing_result)", result.stdout)

    def test_collect_rejects_reused_workspace_for_multiple_herdr_reviewers(self) -> None:
        # Arrange: point a second reviewer at the first reviewer's workspace and result.
        prepare_result, manifest = self._prepare_herdr_review()
        self.assertEqual(prepare_result.returncode, 0, prepare_result.stderr)
        first, second = manifest["reviewers"][:2]
        second["cwd"] = first["cwd"]
        second["task"] = first["task"]
        second["result"] = first["result"]
        (Path(manifest["run_dir"]) / "manifest.json").write_text(json.dumps(manifest))
        Path(first["result"]).write_text("No actionable findings.\n")

        # Act
        result = self._run("--collect", manifest["run_dir"])

        # Assert: one output cannot satisfy multiple independent reviewer slots.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid Herdr reviewer workspace", result.stderr)

    def test_issue_documents_are_routed_only_to_impact_reviewers(self) -> None:
        issue = self.repo / "docs" / "issues" / "001.md"
        issue.parent.mkdir(parents=True)
        issue.write_text("ISSUE_FILE_CONTENT_MARKER\n")

        result = self._run("--engine", "pi", "--mode", "local")

        self.assertEqual(result.returncode, 0, result.stderr)
        for title in ("Behavioral Safety", "Design Quality"):
            prompt = self._captured_prompt(title).read_text()
            self.assertIn("ISSUE_FILE_CONTENT_MARKER", prompt)
            self.assertIn("# Context file diff", prompt)
        adversarial = self._captured_prompt("Adversarial").read_text()
        self.assertNotIn("ISSUE_FILE_CONTENT_MARKER", adversarial)
        self.assertNotIn("docs/issues/001.md", adversarial)

    def test_issue_only_commit_does_not_leak_its_diff_to_adversarial(self) -> None:
        issue = self.repo / "docs" / "issues" / "001.md"
        issue.parent.mkdir(parents=True)
        issue.write_text("ISSUE_FILE_CONTENT_MARKER\n")
        self._git("add", "docs/issues/001.md")
        self._git("commit", "-qm", "add issue")

        result = self._run("--engine", "pi", "--mode", "commit", "--commit", "HEAD")

        self.assertEqual(result.returncode, 0, result.stderr)
        adversarial = self._captured_prompt("Adversarial").read_text()
        self.assertNotIn("ISSUE_FILE_CONTENT_MARKER", adversarial)
        self.assertNotIn("docs/issues/001.md", adversarial)

    def test_git_pathspec_magic_cannot_expand_implementation_selection(self) -> None:
        magic = self.repo / ":(glob)**"
        magic.write_text("implementation marker\n")
        issue = self.repo / "docs" / "issues" / "001.md"
        issue.parent.mkdir(parents=True)
        issue.write_text("ISSUE_FILE_CONTENT_MARKER\n")
        self._git("add", ":(glob)**", "docs/issues/001.md")

        cases = (
            ("local", ("--mode", "local")),
            ("branch", ("--mode", "branch", "--base", "HEAD~1")),
            ("commit", ("--mode", "commit", "--commit", "HEAD")),
        )
        for name, arguments in cases:
            if name == "branch":
                self._git("commit", "-qm", "add implementation and issue")
            with self.subTest(mode=name):
                result = self._run("--engine", "pi", *arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                adversarial = self._captured_prompt("Adversarial").read_text()
                self.assertIn("implementation marker", adversarial)
                self.assertNotIn("ISSUE_FILE_CONTENT_MARKER", adversarial)
                self.assertNotIn("docs/issues/001.md", adversarial)
                for path in self.capture.iterdir():
                    path.unlink()

    def test_invalid_context_builder_output_blocks_reviewers(self) -> None:
        for environment in (
            {"FAKE_MALFORMED_CONTEXT_BUILDER": "1"},
            {"FAKE_INCOMPLETE_CLASSIFICATION_CONTEXT_BUILDER": "1"},
            {"FAKE_INVALID_RELATED_FILE_CONTEXT_BUILDER": "1"},
            {"FAKE_INVALID_RELATED_LINES_CONTEXT_BUILDER": "1"},
        ):
            with self.subTest(environment=environment):
                result = self._run(
                    "--engine", "pi", "--mode", "branch", "--base", "HEAD~1",
                    extra_env=environment,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("context builder", result.stderr.lower())
                self.assertEqual(len(list(self.capture.glob("*.prompt"))), 1)
                for path in self.capture.iterdir():
                    path.unlink()

    def test_local_mode_includes_staged_unstaged_and_untracked_content(self) -> None:
        (self.repo / "example.txt").write_text("first\nsecond\nstaged\n")
        self._git("add", "example.txt")
        (self.repo / "example.txt").write_text("first\nsecond\nstaged\nunstaged\n")
        (self.repo / "new-file.txt").write_text("untracked marker\n")

        result = self._run("--engine", "pi", "--mode", "local")

        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = self._captured_prompt("Behavioral Safety").read_text()
        self.assertIn("+staged", prompt)
        self.assertIn("+unstaged", prompt)
        self.assertIn("untracked marker", prompt)

    def test_local_mode_does_not_follow_untracked_symbolic_links(self) -> None:
        secret = self.root / "secret.txt"
        secret.write_text("OUTSIDE_SECRET_MARKER\n")
        (self.repo / "outside-link").symlink_to(secret)

        result = self._run("--engine", "pi", "--mode", "local")

        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = self._captured_prompt("Behavioral Safety").read_text()
        self.assertIn("skipped: symbolic link", prompt)
        self.assertNotIn("OUTSIDE_SECRET_MARKER", prompt)

    def test_local_mode_skips_non_null_binary_files(self) -> None:
        (self.repo / "binary-data").write_bytes(b"\x01\x02\x03\x04BINARY_MARKER")

        result = self._run("--engine", "pi", "--mode", "local")

        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = self._captured_prompt("Behavioral Safety").read_text()
        self.assertIn("skipped: binary file", prompt)
        self.assertNotIn("BINARY_MARKER", prompt)

    def test_commit_mode_includes_selected_commit(self) -> None:
        result = self._run("--engine", "pi", "--mode", "commit", "--commit", "HEAD")

        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = self._captured_prompt("Behavioral Safety").read_text()
        self.assertIn("commit: HEAD", prompt)
        self.assertIn("+second", prompt)

    def test_one_reviewer_failure_returns_partial_failure(self) -> None:
        result = self._run(
            "--engine", "pi", "--mode", "branch", "--base", "HEAD~1",
            extra_env={"FAKE_FAIL_REVIEWER": "Adversarial"},
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("overall_status: partial_failure", result.stdout)
        self.assertIn("| Adversarial | failed(7) |", result.stdout)
        self.assertNotIn("Error: simulated reviewer failure", result.stdout)

    def test_all_reviewer_failures_return_non_zero(self) -> None:
        result = self._run(
            "--engine", "pi", "--mode", "branch", "--base", "HEAD~1",
            extra_env={"FAKE_FAIL_REVIEWER": "all"},
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("overall_status: failed", result.stdout)

    def test_reviewer_timeout_returns_partial_failure(self) -> None:
        result = self._run(
            "--engine", "pi", "--mode", "branch", "--base", "HEAD~1", "--timeout-sec", "1",
            extra_env={"FAKE_SLEEP_REVIEWER": "Adversarial"},
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("| Adversarial | timeout |", result.stdout)

    def test_invalid_reviewer_outputs_are_protocol_failures(self) -> None:
        for environment in (
            {"FAKE_EMPTY_REVIEWER": "Adversarial"},
            {"FAKE_PREFIXED_SENTINEL_REVIEWER": "Adversarial"},
        ):
            with self.subTest(environment=environment):
                result = self._run(
                    "--engine", "pi", "--mode", "branch", "--base", "HEAD~1",
                    extra_env=environment,
                )
                self.assertIn("overall_status: partial_failure", result.stdout)
                self.assertIn("protocol_failure", result.stdout)
                for path in self.capture.iterdir():
                    path.unlink()

    def test_direct_finding_heading_is_valid(self) -> None:
        result = self._run(
            "--engine", "pi", "--mode", "branch", "--base", "HEAD~1",
            extra_env={"FAKE_DIRECT_FINDING_REVIEWER": "Adversarial"},
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("overall_status: success", result.stdout)

    def test_heading_without_required_finding_fields_is_a_protocol_failure(self) -> None:
        result = self._run(
            "--engine", "pi", "--mode", "branch", "--base", "HEAD~1",
            extra_env={"FAKE_HEADING_ONLY_REVIEWER": "Adversarial"},
        )

        self.assertIn("overall_status: partial_failure", result.stdout)
        self.assertIn("| Adversarial | protocol_failure(invalid_format) |", result.stdout)

    def test_no_finding_sentinel_accepts_an_omitted_final_period(self) -> None:
        result = self._run(
            "--engine", "pi", "--mode", "branch", "--base", "HEAD~1",
            extra_env={"FAKE_NO_PERIOD_REVIEWER": "Adversarial"},
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("overall_status: success", result.stdout)

    def test_invalid_timeout_environment_is_reported_without_a_traceback(self) -> None:
        result = self._run(
            "--engine", "pi", "--mode", "branch", "--base", "HEAD~1",
            extra_env={"REVIEW_DIFF_CODE_TIMEOUT_SEC": "invalid"},
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid REVIEW_DIFF_CODE_TIMEOUT_SEC", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_help_ignores_an_invalid_timeout_environment(self) -> None:
        result = self._run("--help", extra_env={"REVIEW_DIFF_CODE_TIMEOUT_SEC": "invalid"})

        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout)

    def test_explicit_timeout_overrides_an_invalid_timeout_environment(self) -> None:
        result = self._run(
            "--engine", "pi", "--mode", "branch", "--base", "HEAD~1", "--timeout-sec", "2",
            extra_env={"REVIEW_DIFF_CODE_TIMEOUT_SEC": "invalid"},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("timeout_sec: 2", result.stdout)

    def test_failure_stderr_requires_explicit_opt_in(self) -> None:
        result = self._run(
            "--show-failure-stderr", "--engine", "pi", "--mode", "branch", "--base", "HEAD~1",
            extra_env={"FAKE_FAIL_REVIEWER": "Adversarial"},
        )

        self.assertIn("Error: simulated reviewer failure", result.stdout)

    def test_codex_reviewers_use_bundle_only_sandbox(self) -> None:
        self._write_executable("codex", FAKE_ENGINE)
        self._write_executable("bwrap", FAKE_BWRAP)
        self._write_executable(
            "file",
            """#!/usr/bin/env python3
import sys
print(f"{sys.argv[1]}: ELF 64-bit LSB pie executable, static-pie linked")
""",
        )
        codex_home = self.root / "codex-home"
        codex_home.mkdir()
        (codex_home / "auth.json").write_text("{}\n")

        result = self._run(
            "--engine", "codex", "--mode", "branch", "--base", "HEAD~1",
            extra_env={"CODEX_HOME": str(codex_home)},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        bwrap_args = (self.capture / "bwrap.args").read_text()
        self.assertIn("--unshare-all", bwrap_args)
        self.assertIn(str(codex_home / "auth.json"), bwrap_args)
        self.assertNotIn(str(self.repo), bwrap_args)
        self.assertIn("gpt-5.6-luna", bwrap_args)
        self.assertIn('model_reasoning_effort="medium"', bwrap_args)

        builder = self._captured_prompt("Context Builder")
        builder_args = Path(str(builder).removesuffix(".prompt") + ".args").read_text()
        self.assertNotIn("--ask-for-approval", builder_args)

    def test_nono_wrapped_codex_uses_fresh_bundle_only_sandbox_without_bwrap(self) -> None:
        raw_bin = self.root / "raw-bin"
        raw_bin.mkdir()
        package_root = self.root / "codex-package"
        launcher = package_root / "bin" / "codex.js"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("#!/bin/sh\nexit 98\n")
        launcher.chmod(0o755)
        raw_codex = raw_bin / "codex"
        raw_codex.symlink_to(launcher)
        native_codex = package_root / "node_modules" / "@openai" / "codex-test" / "vendor" / "test-target" / "bin" / "codex"
        native_codex.parent.mkdir(parents=True)
        native_codex.write_text(textwrap.dedent(FAKE_ENGINE))
        native_codex.chmod(0o755)
        codex_home = self.root / "codex-home"
        codex_home.mkdir()
        (codex_home / "auth.json").write_text("{}\n")
        self._write_executable(
            "codex",
            """#!/bin/sh
exec nono run --silent --profile test-codex --allow-cwd -- codex "$@"
""",
        )
        self._write_executable(
            "nono",
            """#!/usr/bin/env python3
import os
from pathlib import Path
import subprocess
import sys

capture = Path(os.environ["FAKE_CAPTURE_DIR"])
(capture / "nono.args").write_text("\\n".join(sys.argv[1:]) + "\\n")
separator = sys.argv.index("--")
command = sys.argv[separator + 1:]
command[0] = str(Path(os.environ["FAKE_RAW_CODEX"]))
raise SystemExit(subprocess.run(command).returncode)
""",
        )

        result = self._run(
            "--engine", "codex", "--mode", "branch", "--base", "HEAD~1",
            extra_env={
                "FAKE_RAW_CODEX": str(native_codex),
                "PATH": f"{self.bin}:{raw_bin}:{os.environ['PATH']}",
                "CODEX_HOME": str(codex_home),
                "NONO_CAP_FILE": "",
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        nono_args = (self.capture / "nono.args").read_text()
        self.assertNotIn("--profile", nono_args)
        self.assertIn(f"--allow-cwd\n--read-file\n{codex_home / 'auth.json'}\n--", nono_args)
        self.assertIn(str(native_codex), nono_args)
        self.assertNotIn(str(self.repo), nono_args)

    def test_nested_nono_codex_review_fails_closed(self) -> None:
        self._write_executable("codex", FAKE_ENGINE + "\n# nono run --profile test-codex --allow-cwd -- codex\n")
        self._write_executable("nono", "#!/bin/sh\nexit 99\n")

        result = self._run(
            "--show-failure-stderr", "--engine", "codex", "--mode", "branch", "--base", "HEAD~1",
            extra_env={"NONO_CAP_FILE": "/tmp/existing-capability.json"},
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot create bundle-only Codex isolation inside an existing nono sandbox", result.stdout)

    def test_auto_engine_falls_back_when_context_builder_cannot_start(self) -> None:
        self._write_executable(
            "pi",
            """#!/bin/sh
echo 'pi authentication required' >&2
exit 1
""",
        )
        self._write_executable("codex", FAKE_ENGINE)
        self._write_executable("bwrap", FAKE_BWRAP)
        self._write_executable(
            "file",
            """#!/usr/bin/env python3
import sys
print(f"{sys.argv[1]}: ELF 64-bit LSB pie executable, static-pie linked")
""",
        )
        codex_home = self.root / "codex-home"
        codex_home.mkdir()
        (codex_home / "auth.json").write_text("{}\n")

        result = self._run(
            "--engine", "auto", "--mode", "branch", "--base", "HEAD~1",
            extra_env={"CODEX_HOME": str(codex_home)},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("engine: codex", result.stdout)

    def test_claude_context_builder_gets_read_tools_and_reviewers_get_none(self) -> None:
        self._write_executable("claude", FAKE_ENGINE)

        result = self._run("--engine", "claude", "--mode", "branch", "--base", "HEAD~1")

        self.assertEqual(result.returncode, 0, result.stderr)
        builder = self._captured_prompt("Context Builder")
        builder_args = Path(str(builder).removesuffix(".prompt") + ".args").read_text()
        self.assertIn("--tools\nRead,Grep,Glob", builder_args)
        for title in ("Behavioral Safety", "Design Quality", "Adversarial"):
            reviewer = self._captured_prompt(title)
            reviewer_args = Path(str(reviewer).removesuffix(".prompt") + ".args").read_text()
            self.assertIn("--tools\n\n", reviewer_args)

    def test_reviewer_prompts_are_standalone_japanese_templates(self) -> None:
        self.assertEqual(
            {path.name for path in PROMPT_DIR.glob("*.md")},
            {"behavioral-safety.md", "design-quality.md", "adversarial.md"},
        )
        for path in PROMPT_DIR.glob("*.md"):
            template = path.read_text()
            self.assertRegex(template, r"[ぁ-んァ-ヶ一-龠]")
            self.assertIn("$change_bundle", template)
            self.assertNotIn("fresh context", template)
            self.assertNotIn("$reviewer_title", template)
            self.assertNotIn("$engine", template)
            self.assertNotIn("$model", template)
            self.assertNotIn("$thinking_line", template)

        runner = HELPER.read_text()
        self.assertNotIn("Assume the supplied diff is wrong.", runner)
        self.assertNotIn("You are an independent", runner)

    def test_reviewer_prompt_template_renders_bundle_without_runner_metadata(self) -> None:
        result = self._run("--engine", "pi", "--mode", "branch", "--base", "HEAD~1")

        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = self._captured_prompt("Behavioral Safety").read_text()
        self.assertIn("# 変更bundle", prompt)
        self.assertIn("+second", prompt)
        self.assertNotIn("# レビュー情報", prompt)
        self.assertNotIn("engine: pi", prompt)
        self.assertNotIn("thinking: low", prompt)
        self.assertNotRegex(prompt, r"\$[A-Za-z_{]")

    def test_context_builder_policy_is_a_prompt_asset(self) -> None:
        template = CONTEXT_BUILDER_PROMPT.read_text()

        self.assertIn("$changed_files_json", template)
        self.assertIn("$raw_change_bundle", template)
        self.assertIn("untrusted", template)
        self.assertIn('"related_files"', template)
        for removed_field in (
            "unclassified_files",
            "issue_context",
            "related_implementation",
            "impact_coverage",
            "unresolved_impact",
        ):
            self.assertNotIn(removed_field, template)
        self.assertNotIn("--prompt-file", HELPER.read_text())


if __name__ == "__main__":
    unittest.main()
