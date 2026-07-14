#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from string import Template


REVIEWERS = (
    ("behavioral-safety", "Behavioral Safety"),
    ("design-quality", "Design Quality"),
    ("adversarial", "Adversarial"),
)
NO_FINDINGS = {"No actionable findings", "No actionable findings."}
FINDING_HEADING = re.compile(r"^### \[(critical|high|medium|low)\] .+")
REQUIRED_FINDING_FIELDS = ("- Target:", "- Problem:", "- Evidence:", "- Suggested fix:")
SKILL_DIR = Path(__file__).resolve().parent.parent
PROMPT_DIR = SKILL_DIR / "assets" / "reviewer-prompts"
CONTEXT_BUILDER_TEMPLATE = SKILL_DIR / "assets" / "context-builder.md"


@dataclass(frozen=True)
class ReviewerResult:
    reviewer_id: str
    title: str
    status: str
    stdout: str
    stderr: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Strict, diff-focused code review with three independent reviewers."
    )
    timeout_environment = os.getenv("REVIEW_DIFF_CODE_TIMEOUT_SEC", "600")
    parser.add_argument("--mode", choices=("auto", "branch", "local", "commit"), default="auto")
    parser.add_argument("--base", help="Base ref for branch mode")
    parser.add_argument("--commit", default="HEAD", help="Commit ref for commit mode")
    parser.add_argument("--engine", choices=("auto", "pi", "codex", "claude"), default=os.getenv("REVIEW_DIFF_CODE_ENGINE", "auto"))
    parser.add_argument("--model", default="", help="Override model for the selected engine")
    parser.add_argument("--thinking", default="", help="Override thinking level when supported")
    parser.add_argument("--timeout-sec", type=positive_int, default=600)
    parser.add_argument("--show-failure-stderr", action="store_true", help="Show raw failed-reviewer stderr; it may repeat bundle data")
    help_requested = any(argument in ("-h", "--help") for argument in sys.argv[1:])
    timeout_overridden = any(
        argument == "--timeout-sec" or argument.startswith("--timeout-sec=")
        for argument in sys.argv[1:]
    )
    should_read_timeout_environment = not help_requested and not timeout_overridden
    if should_read_timeout_environment:
        try:
            parser.set_defaults(timeout_sec=positive_int(timeout_environment))
        except (ValueError, argparse.ArgumentTypeError):
            parser.error(f"invalid REVIEW_DIFF_CODE_TIMEOUT_SEC: {timeout_environment}")
    args = parser.parse_args()
    return args


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def command_output(args: list[str], cwd: Path, *, check: bool = True) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"command failed: {' '.join(args)}")
    return result.stdout


def repository_root() -> Path:
    return Path(command_output(["git", "rev-parse", "--show-toplevel"], Path.cwd()).strip())


def select_engine(requested: str) -> str:
    if requested != "auto":
        if not shutil.which(requested):
            raise RuntimeError(f"{requested} not found")
        return requested
    for candidate in ("pi", "codex", "claude"):
        if shutil.which(candidate):
            return candidate
    raise RuntimeError("no supported review engine found: install pi, codex, or claude")


def engine_settings(engine: str, model: str, thinking: str) -> tuple[str, str]:
    if engine == "pi":
        return model or os.getenv("REVIEW_DIFF_CODE_PI_MODEL", ""), thinking or os.getenv("REVIEW_DIFF_CODE_PI_THINKING", "low")
    if engine == "codex":
        return model or os.getenv("REVIEW_DIFF_CODE_CODEX_MODEL", "gpt-5.6-luna"), thinking or os.getenv("REVIEW_DIFF_CODE_CODEX_THINKING", "medium")
    return model or os.getenv("REVIEW_DIFF_CODE_CLAUDE_MODEL", "sonnet"), thinking


def resolve_base(repo: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    if shutil.which("gh"):
        result = subprocess.run(
            ["gh", "pr", "view", "--json", "baseRefName", "--jq", ".baseRefName"],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return f"origin/{result.stdout.strip()}"
    return "origin/main"


def has_dirty_work(repo: Path) -> bool:
    return bool(command_output(["git", "status", "--porcelain"], repo).strip())


def untracked_files(repo: Path) -> list[str]:
    raw = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=repo,
        capture_output=True,
        check=True,
    ).stdout
    return [os.fsdecode(encoded) for encoded in raw.split(b"\0") if encoded]


def untracked_contents(repo: Path, allowed: set[str] | None = None) -> str:
    sections: list[str] = []
    for relative in untracked_files(repo):
        if allowed is not None and relative not in allowed:
            continue
        path = repo / relative
        if path.is_symlink():
            sections.append(f"\n## Untracked file: {relative}\nskipped: symbolic link\n")
            continue
        if not path.is_file():
            continue
        size = path.stat().st_size
        header = f"\n## Untracked file: {relative}\nsize: {size} bytes\n"
        if size > 200_000:
            sections.append(header + "skipped: file is larger than 200000 bytes\n")
            continue
        data = path.read_bytes()
        if b"\0" in data:
            sections.append(header + "skipped: binary file\n")
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            sections.append(header + "skipped: binary file\n")
            continue
        if any(ord(character) < 32 and character not in "\t\n\r\f" for character in text):
            sections.append(header + "skipped: binary file\n")
            continue
        sections.append(header + "```\n" + text + "\n```\n")
    return "".join(sections)


def null_separated_paths(args: list[str], repo: Path) -> list[str]:
    raw = subprocess.run(args, cwd=repo, capture_output=True, check=True).stdout
    return [os.fsdecode(path) for path in raw.split(b"\0") if path]


def create_raw_bundle(repo: Path, mode: str, base: str | None, commit: str) -> tuple[str, str, list[str], str | None]:
    if mode == "auto":
        mode = "local" if has_dirty_work(repo) else "branch"
    parts = [
        "# Repository",
        repo.name,
        "",
        "# Git status",
        command_output(["git", "status", "--short", "--branch"], repo).rstrip(),
        "",
    ]
    if mode == "branch":
        resolved = resolve_base(repo, base)
        changed_files = null_separated_paths(
            ["git", "diff", "--find-renames", "--name-only", "-z", f"{resolved}...HEAD"], repo
        )
        parts.extend(
            [
                "# Target", f"mode: branch", f"base: {resolved}", "head: HEAD", "",
                "# Diff stat", command_output(["git", "diff", "--find-renames", "--stat", f"{resolved}...HEAD"], repo).rstrip(), "",
                "# Changed files", command_output(["git", "diff", "--find-renames", "--name-status", f"{resolved}...HEAD"], repo).rstrip(), "",
                "# Diff", command_output(["git", "diff", "--find-renames", f"{resolved}...HEAD"], repo).rstrip(),
            ]
        )
    elif mode == "local":
        changed_files = sorted(set(
            null_separated_paths(["git", "diff", "--name-only", "-z"], repo)
            + null_separated_paths(["git", "diff", "--cached", "--name-only", "-z"], repo)
            + untracked_files(repo)
        ))
        resolved = None
        parts.extend(
            [
                "# Target", "mode: local", "",
                "# Diff stat (unstaged)", command_output(["git", "diff", "--stat"], repo).rstrip(), "",
                "# Diff stat (staged)", command_output(["git", "diff", "--cached", "--stat"], repo).rstrip(), "",
                "# Untracked files", command_output(["git", "ls-files", "--others", "--exclude-standard"], repo).rstrip(), "",
                "# Diff (unstaged)", command_output(["git", "diff", "--find-renames"], repo).rstrip(), "",
                "# Diff (staged)", command_output(["git", "diff", "--cached", "--find-renames"], repo).rstrip(), "",
                "# Untracked file contents", untracked_contents(repo).rstrip(),
            ]
        )
    else:
        changed_files = null_separated_paths(
            ["git", "show", "--format=", "--find-renames", "--name-only", "-z", commit], repo
        )
        resolved = None
        parts.extend(
            [
                "# Target", "mode: commit", f"commit: {commit}", "",
                "# Commit", command_output(["git", "show", "--find-renames", "--stat", "--oneline", "--decorate", "--no-ext-diff", commit], repo).rstrip(), "",
                "# Diff", command_output(["git", "show", "--find-renames", "--format=fuller", "--no-ext-diff", commit], repo).rstrip(),
            ]
        )
    return mode, "\n".join(parts).rstrip() + "\n", changed_files, resolved


def create_implementation_bundle(
    repo: Path,
    mode: str,
    resolved_base: str | None,
    commit: str,
    implementation_files: list[str],
) -> str:
    paths = ["--", *implementation_files]
    parts = ["# Repository", repo.name, "", "# Target", f"mode: {mode}"]
    if mode == "branch":
        branch_diff = (
            command_output(["git", "--literal-pathspecs", "diff", "--find-renames", f"{resolved_base}...HEAD", *paths], repo).rstrip()
            if implementation_files else ""
        )
        parts.extend([
            f"base: {resolved_base}", "head: HEAD", "", "# Changed implementation files",
            "\n".join(implementation_files), "", "# Implementation diff",
            branch_diff,
        ])
    elif mode == "local":
        allowed = set(implementation_files)
        unstaged_diff = (
            command_output(["git", "--literal-pathspecs", "diff", "--find-renames", *paths], repo).rstrip()
            if implementation_files else ""
        )
        staged_diff = (
            command_output(["git", "--literal-pathspecs", "diff", "--cached", "--find-renames", *paths], repo).rstrip()
            if implementation_files else ""
        )
        parts.extend([
            "", "# Changed implementation files", "\n".join(implementation_files),
            "", "# Diff (unstaged)", unstaged_diff,
            "", "# Diff (staged)", staged_diff,
            "", "# Untracked implementation file contents", untracked_contents(repo, allowed).rstrip(),
        ])
    else:
        commit_diff = (
            command_output(["git", "--literal-pathspecs", "show", "--find-renames", "--format=", "--no-ext-diff", commit, *paths], repo).rstrip()
            if implementation_files else ""
        )
        parts.extend([
            f"commit: {commit}", "", "# Changed implementation files", "\n".join(implementation_files),
            "", "# Implementation diff",
            commit_diff,
        ])
    return "\n".join(parts).rstrip() + "\n"


def create_context_diff(
    repo: Path,
    mode: str,
    resolved_base: str | None,
    commit: str,
    context_files: list[str],
) -> str:
    if not context_files:
        return ""
    paths = ["--", *context_files]
    if mode == "branch":
        return command_output(
            ["git", "--literal-pathspecs", "diff", "--find-renames", f"{resolved_base}...HEAD", *paths],
            repo,
        ).rstrip()
    if mode == "local":
        parts = [
            command_output(["git", "--literal-pathspecs", "diff", "--find-renames", *paths], repo).rstrip(),
            command_output(
                ["git", "--literal-pathspecs", "diff", "--cached", "--find-renames", *paths], repo
            ).rstrip(),
            untracked_contents(repo, set(context_files)).rstrip(),
        ]
        return "\n".join(part for part in parts if part)
    return command_output(
        ["git", "--literal-pathspecs", "show", "--find-renames", "--format=", "--no-ext-diff", commit, *paths],
        repo,
    ).rstrip()


def build_context_builder_prompt(changed_files: list[str], raw_bundle: str) -> str:
    return Template(CONTEXT_BUILDER_TEMPLATE.read_text()).substitute(
        changed_files_json=json.dumps(changed_files, ensure_ascii=False),
        raw_change_bundle=raw_bundle.rstrip(),
    ).rstrip() + "\n"


def repository_evidence_file(repo: Path, relative: str, field: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise RuntimeError(f"context builder {field} must be a repository-relative path")
    path = repo / relative
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as error:
        raise RuntimeError(f"context builder {field} does not exist: {relative}") from error
    if path.is_symlink() or not resolved.is_relative_to(repo.resolve()) or not resolved.is_file():
        raise RuntimeError(f"context builder {field} is not a regular repository file: {relative}")
    return resolved


def related_file_range(repo: Path, item: dict[str, object]) -> tuple[Path, int, int]:
    if set(item) != {"path", "lines"}:
        raise RuntimeError("context builder related_files item has invalid fields")
    if not all(isinstance(item[key], str) and item[key] for key in ("path", "lines")):
        raise RuntimeError("context builder related_files fields must be non-empty strings")
    lines = item["lines"]
    if not re.fullmatch(r"[1-9]\d*(?:-[1-9]\d*)?", lines):
        raise RuntimeError("context builder related_files lines must be a line or line range")
    path = repository_evidence_file(repo, item["path"], "related_files.path")
    try:
        source = path.read_text()
    except UnicodeDecodeError as error:
        raise RuntimeError("context builder related_files path must be UTF-8 text") from error
    start_text, separator, end_text = lines.partition("-")
    start = int(start_text)
    end = int(end_text) if separator else start
    if end < start or end > len(source.splitlines()):
        raise RuntimeError("context builder related_files lines are outside its source file")
    return path, start, end


def parse_context_builder_output(stdout: str, changed_files: list[str], repo: Path) -> dict[str, object]:
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"context builder returned invalid JSON: {error}") from error
    if not isinstance(result, dict):
        raise RuntimeError("context builder output must be a JSON object")
    if set(result) != {"implementation_files", "context_files", "related_files"}:
        raise RuntimeError("context builder output has invalid fields")
    classifications: dict[str, list[str]] = {}
    for key in ("implementation_files", "context_files"):
        value = result.get(key)
        if not isinstance(value, list) or not all(isinstance(path, str) for path in value):
            raise RuntimeError(f"context builder field {key} must be a string array")
        classifications[key] = value
    flattened = [path for values in classifications.values() for path in values]
    if len(flattened) != len(set(flattened)):
        raise RuntimeError("context builder classifications overlap or contain duplicates")
    if set(flattened) != set(changed_files):
        raise RuntimeError("context builder classifications do not cover exactly the changed files")
    related = result.get("related_files")
    if not isinstance(related, list) or not all(isinstance(item, dict) for item in related):
        raise RuntimeError("context builder field related_files must be an object array")
    for item in related:
        related_file_range(repo, item)
        if item["path"] in changed_files:
            raise RuntimeError("context builder related_files must not include changed files")
    return result


def render_review_context(repo: Path, context: dict[str, object], context_diff: str) -> str:
    rendered = "# Review context"
    if context_diff:
        rendered += "\n\n# Context file diff\n\n```text\n" + context_diff.rstrip() + "\n```"
    related_files = []
    for item in context["related_files"]:
        path, start, end = related_file_range(repo, item)
        content = "\n".join(path.read_text().splitlines()[start - 1 : end])
        related_files.append({"path": item["path"], "lines": item["lines"], "content": content})
    if related_files:
        rendered += "\n\n# Related files\n\n" + json.dumps(related_files, ensure_ascii=False, indent=2)
    return rendered


def build_prompt(
    reviewer_id: str,
    bundle: str,
    impact_context: str,
) -> str:
    prompt_template = Template((PROMPT_DIR / f"{reviewer_id}.md").read_text())
    return prompt_template.substitute(
        impact_context_section="" if reviewer_id == "adversarial" else impact_context.rstrip(),
        change_bundle=bundle.rstrip(),
    ).rstrip() + "\n"


def static_codex_command(model: str, thinking: str) -> list[str]:
    bwrap = shutil.which("bwrap")
    codex = shutil.which("codex")
    if not bwrap or not codex:
        raise RuntimeError("bwrap and codex are required for bundle-only Codex review")
    codex_path = Path(codex).resolve()
    file_output = command_output(["file", str(codex_path)], Path.cwd())
    if "static-pie linked" not in file_output and "statically linked" not in file_output:
        raise RuntimeError(f"bundle-only Codex review requires a static Codex executable: {codex_path}")
    codex_home = Path(os.getenv("CODEX_HOME", Path.home() / ".codex"))
    auth = codex_home / "auth.json"
    if not auth.is_file():
        raise RuntimeError(f"Codex auth file not found: {auth}")
    codex_args = ["/bin/codex", "--ask-for-approval", "never", "--model", model]
    if thinking:
        codex_args.extend(["-c", f'model_reasoning_effort="{thinking}"'])
    return [
        bwrap, "--unshare-all", "--share-net", "--die-with-parent", "--new-session", "--clearenv",
        "--dir", "/bin", "--ro-bind", str(codex_path), "/bin/codex",
        "--dir", "/codex-home", "--ro-bind", str(auth), "/codex-home/auth.json",
        "--dir", "/home", "--dir", "/home/codex",
        "--dir", "/etc", "--dir", "/etc/ssl", "--ro-bind", "/etc/ssl/certs", "/etc/ssl/certs",
        "--ro-bind", "/etc/hosts", "/etc/hosts", "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--dir", "/workspace", "--chdir", "/workspace",
        "--setenv", "HOME", "/home/codex", "--setenv", "CODEX_HOME", "/codex-home", "--setenv", "PATH", "/bin",
        "--setenv", "SSL_CERT_FILE", "/etc/ssl/certs/ca-certificates.crt",
        *codex_args, "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check", "-C", "/workspace", "-s", "read-only", "-",
    ]


def engine_command(engine: str, role: str, repo: Path, isolation_root: Path, model: str, thinking: str) -> tuple[list[str], Path]:
    context_builder = role == "context-builder"
    if engine == "pi":
        args = ["pi", "--no-session", "--tools", "read,grep,find,ls" if context_builder else ""]
        if model:
            args.extend(["--model", model])
        if thinking:
            args.extend(["--thinking", thinking])
        args.append("-p")
        return args, repo if context_builder else isolation_root
    if engine == "codex":
        if not context_builder:
            return static_codex_command(model, thinking), isolation_root
        args = ["codex", "--ask-for-approval", "never", "--model", model]
        if thinking:
            args.extend(["-c", f'model_reasoning_effort="{thinking}"'])
        args.extend(["exec", "--ephemeral", "-C", str(repo), "-s", "read-only", "-"])
        return args, repo
    args = ["claude", "--print", "--no-session-persistence", "--tools"]
    args.append("Read,Grep,Glob" if context_builder else "")
    args.extend(["--model", model])
    return args, repo if context_builder else isolation_root


def execute(command: list[str], cwd: Path, prompt: str, timeout: int) -> tuple[int, str, str, bool]:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(prompt, timeout=timeout)
        return process.returncode, stdout, stderr, False
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return 124, stdout, stderr, True


def validate_output(stdout: str) -> str:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        return "protocol_failure(empty_output)"

    if "\n".join(lines) in NO_FINDINGS:
        return "success"

    if lines[0] == "## Findings":
        lines = lines[1:]
    if not lines or not FINDING_HEADING.fullmatch(lines[0]):
        return "protocol_failure(invalid_format)"

    heading_indexes = [index for index, line in enumerate(lines) if FINDING_HEADING.fullmatch(line)]
    for position, start in enumerate(heading_indexes):
        end = heading_indexes[position + 1] if position + 1 < len(heading_indexes) else len(lines)
        block = lines[start + 1 : end]
        if not all(any(line.startswith(field) for line in block) for field in REQUIRED_FINDING_FIELDS):
            return "protocol_failure(invalid_format)"
    return "success"


def run_reviewer(
    reviewer_id: str,
    title: str,
    repo: Path,
    isolation_root: Path,
    prompt: str,
    engine: str,
    model: str,
    thinking: str,
    timeout: int,
) -> ReviewerResult:
    try:
        command, cwd = engine_command(engine, reviewer_id, repo, isolation_root, model, thinking)
        returncode, stdout, stderr, timed_out = execute(command, cwd, prompt, timeout)
    except Exception as error:
        return ReviewerResult(reviewer_id, title, "failed(126)", "", str(error) + "\n")
    if timed_out:
        status = "timeout"
    elif returncode != 0:
        status = f"failed({returncode})"
    else:
        status = validate_output(stdout)
    return ReviewerResult(reviewer_id, title, status, stdout, stderr)


def render_summary(args: argparse.Namespace, mode: str, engine: str, model: str, thinking: str, results: list[ReviewerResult]) -> int:
    successes = sum(result.status == "success" for result in results)
    overall = "failed" if successes == 0 else "partial_failure" if successes < len(results) else "success"
    print("# Review Summary\n")
    print(f"overall_status: {overall}")
    print(f"engine: {engine}")
    print(f"model: {model or 'default'}")
    print(f"thinking: {thinking or 'none'}")
    print(f"timeout_sec: {args.timeout_sec}")
    print(f"mode: {mode}")
    print("context_builder: success")
    print("reviewer_isolation: bundle_only")
    print(f"failure_stderr: {'shown' if args.show_failure_stderr else 'suppressed'}\n")
    print("| Reviewer | Status |")
    print("| --- | --- |")
    for result in results:
        print(f"| {result.title} | {result.status} |")
    print("\n# Findings by Reviewer")
    for result in results:
        print(f"\n## {result.title}\n\nstatus: {result.status}\n")
        print(result.stdout.rstrip() if result.stdout.strip() else "No output.")
    failures = [result for result in results if result.status != "success" and result.stderr]
    if failures:
        print("\n# Diagnostics")
        for result in failures:
            print(f"\n## {result.title} stderr\n")
            if args.show_failure_stderr:
                print("```\n" + result.stderr.rstrip() + "\n```")
            else:
                size = len(result.stderr.encode())
                print(f"suppressed: {size} bytes (rerun with --show-failure-stderr only if exposing bundle data is acceptable)")
    print(f"review-diff-code target: {mode}", file=sys.stderr)
    print(f"engine: {engine}", file=sys.stderr)
    print(f"model: {model or 'default'}", file=sys.stderr)
    if thinking:
        print(f"thinking: {thinking}", file=sys.stderr)
    print(f"overall_status: {overall}", file=sys.stderr)
    return 1 if successes == 0 else 0


def main() -> int:
    args = parse_args()
    try:
        repo = repository_root()
        engine = select_engine(args.engine)
        model, thinking = engine_settings(engine, args.model, args.thinking)
        mode, raw_bundle, changed_files, resolved_base = create_raw_bundle(repo, args.mode, args.base, args.commit)
        with tempfile.TemporaryDirectory(prefix="review-diff-code-") as directory:
            isolation_root = Path(directory) / "reviewer-root"
            isolation_root.mkdir()
            builder_prompt = build_context_builder_prompt(changed_files, raw_bundle)
            builder_command, builder_cwd = engine_command(
                engine, "context-builder", repo, isolation_root, model, thinking
            )
            returncode, stdout, stderr, timed_out = execute(
                builder_command, builder_cwd, builder_prompt, args.timeout_sec
            )
            if timed_out:
                raise RuntimeError("context builder timed out")
            if returncode != 0:
                detail = stderr.strip() if args.show_failure_stderr else f"exit {returncode}"
                raise RuntimeError(f"context builder failed: {detail}")
            context = parse_context_builder_output(stdout, changed_files, repo)
            implementation_bundle = create_implementation_bundle(
                repo,
                mode,
                resolved_base,
                args.commit,
                context["implementation_files"],
            )
            context_diff = create_context_diff(
                repo,
                mode,
                resolved_base,
                args.commit,
                context["context_files"],
            )
            impact_context = render_review_context(repo, context, context_diff)
            prompts = {
                reviewer_id: build_prompt(reviewer_id, implementation_bundle, impact_context)
                for reviewer_id, title in REVIEWERS
            }
            with ThreadPoolExecutor(max_workers=len(REVIEWERS)) as executor:
                futures = [
                    executor.submit(
                        run_reviewer,
                        reviewer_id,
                        title,
                        repo,
                        isolation_root,
                        prompts[reviewer_id],
                        engine,
                        model,
                        thinking,
                        args.timeout_sec,
                    )
                    for reviewer_id, title in REVIEWERS
                ]
                results = [future.result() for future in futures]
        return render_summary(args, mode, engine, model, thinking, results)
    except Exception as error:
        print(f"review-diff-code: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
