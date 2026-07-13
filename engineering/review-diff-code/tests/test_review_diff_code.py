from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


SKILL_DIR = Path(__file__).resolve().parent.parent
HELPER = SKILL_DIR / "scripts" / "review-diff-code"
PROMPT_DIR = SKILL_DIR / "assets" / "reviewer-prompts"


FAKE_ENGINE = r"""#!/usr/bin/env python3
import os
from pathlib import Path
import re
import sys
import time

prompt = sys.stdin.read()
match = re.search(r"^reviewer: (.+)$", prompt, re.MULTILINE)
title = match.group(1) if match else "unknown"
stem = Path(os.environ["FAKE_CAPTURE_DIR"]) / f"{title.replace(' ', '_').replace('/', '_')}.{os.getpid()}"
Path(str(stem) + ".prompt").write_text(prompt)
Path(str(stem) + ".cwd").write_text(str(Path.cwd()) + "\n")
Path(str(stem) + ".args").write_text("\n".join(sys.argv[1:]) + "\n")
print("FAKE_ENGINE_STDERR_MARKER", file=sys.stderr)
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
import re
import sys

prompt = sys.stdin.read()
capture = Path(os.environ["FAKE_CAPTURE_DIR"])
(capture / "bwrap.args").write_text("\n".join(sys.argv[1:]) + "\n")
match = re.search(r"^reviewer: (.+)$", prompt, re.MULTILINE)
title = match.group(1) if match else "unknown"
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
        self._git("add", "example.txt")
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

    def _captured_prompt(self, title: str) -> Path:
        matches = list(self.capture.glob(f"{title.replace(' ', '_')}.*.prompt"))
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_panel_option_is_not_part_of_the_public_interface(self) -> None:
        result = self._run("--panel", "legacy")
        help_result = self._run("--help")

        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments: --panel legacy", result.stderr)
        self.assertNotIn("--panel", help_result.stdout)

    def test_default_workflow_runs_three_reviewers_and_isolates_adversarial_context(self) -> None:
        context = self.root / "context.md"
        context.write_text("IMPLEMENTER_REASONING_MARKER\n")

        result = self._run(
            "--engine", "pi", "--mode", "branch", "--base", "HEAD~1", "--prompt-file", str(context)
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("| Behavioral Safety | success |", result.stdout)
        self.assertIn("| Design Quality | success |", result.stdout)
        self.assertIn("| Adversarial | success |", result.stdout)
        self.assertEqual(len(list(self.capture.glob("*.prompt"))), 3)
        self.assertIn("IMPLEMENTER_REASONING_MARKER", self._captured_prompt("Behavioral Safety").read_text())
        self.assertIn("IMPLEMENTER_REASONING_MARKER", self._captured_prompt("Design Quality").read_text())
        adversarial = self._captured_prompt("Adversarial")
        self.assertNotIn("IMPLEMENTER_REASONING_MARKER", adversarial.read_text())
        stem = str(adversarial).removesuffix(".prompt")
        self.assertNotEqual(Path(stem + ".cwd").read_text().strip(), str(self.repo))
        self.assertNotIn("read,grep,find,ls", Path(stem + ".args").read_text())

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

    def test_codex_adversarial_uses_read_root_sandbox(self) -> None:
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

    def test_claude_non_adversarial_reviewers_receive_only_read_tools(self) -> None:
        self._write_executable("claude", FAKE_ENGINE)

        result = self._run("--engine", "claude", "--mode", "branch", "--base", "HEAD~1")

        self.assertEqual(result.returncode, 0, result.stderr)
        behavioral = self._captured_prompt("Behavioral Safety")
        behavioral_args = Path(str(behavioral).removesuffix(".prompt") + ".args").read_text()
        self.assertIn("--tools\nRead,Grep,Glob", behavioral_args)
        adversarial = self._captured_prompt("Adversarial")
        adversarial_args = Path(str(adversarial).removesuffix(".prompt") + ".args").read_text()
        self.assertIn("--tools\n\n", adversarial_args)

    def test_reviewer_prompts_are_standalone_files(self) -> None:
        self.assertEqual(
            {path.name for path in PROMPT_DIR.glob("*.md")},
            {"behavioral-safety.md", "design-quality.md", "adversarial.md"},
        )
        runner = HELPER.read_text()
        self.assertNotIn("Assume the supplied diff is wrong.", runner)
        self.assertNotIn("You are an independent", runner)


if __name__ == "__main__":
    unittest.main()
