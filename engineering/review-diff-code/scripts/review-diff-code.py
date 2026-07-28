#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
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
RUN_MARKER = ".review-diff-code-run"
MANIFEST_NAME = "manifest.json"


class ReviewError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare and validate artifacts for a subagent-based diff review."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Create the Context Builder input.")
    prepare.add_argument("--mode", choices=("auto", "branch", "local", "commit"), default="auto")
    prepare.add_argument("--base", help="Base ref for branch mode")
    prepare.add_argument("--commit", default="HEAD", help="Commit ref for commit mode")
    prepare.add_argument(
        "--run-root",
        type=Path,
        help="Directory under which a private run directory is created.",
    )

    for command in ("reset-context", "validate-context", "route", "collect", "cleanup"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--run-dir", type=Path, required=True)

    return parser.parse_args()


def command_output(args: list[str], cwd: Path, *, check: bool = True) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"command failed: {' '.join(args)}")
    return result.stdout


def repository_root() -> Path:
    return Path(command_output(["git", "rev-parse", "--show-toplevel"], Path.cwd()).strip())


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


def create_raw_bundle(
    repo: Path,
    mode: str,
    base: str | None,
    commit: str,
) -> tuple[str, str, list[str], str | None]:
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
            ["git", "diff", "--find-renames", "--name-only", "-z", f"{resolved}...HEAD"],
            repo,
        )
        parts.extend(
            [
                "# Target",
                "mode: branch",
                f"base: {resolved}",
                "head: HEAD",
                "",
                "# Diff stat",
                command_output(
                    ["git", "diff", "--find-renames", "--stat", f"{resolved}...HEAD"],
                    repo,
                ).rstrip(),
                "",
                "# Changed files",
                command_output(
                    ["git", "diff", "--find-renames", "--name-status", f"{resolved}...HEAD"],
                    repo,
                ).rstrip(),
                "",
                "# Diff",
                command_output(
                    ["git", "diff", "--find-renames", f"{resolved}...HEAD"],
                    repo,
                ).rstrip(),
            ]
        )
    elif mode == "local":
        changed_files = sorted(
            set(
                null_separated_paths(["git", "diff", "--name-only", "-z"], repo)
                + null_separated_paths(["git", "diff", "--cached", "--name-only", "-z"], repo)
                + untracked_files(repo)
            )
        )
        resolved = None
        parts.extend(
            [
                "# Target",
                "mode: local",
                "",
                "# Diff stat (unstaged)",
                command_output(["git", "diff", "--stat"], repo).rstrip(),
                "",
                "# Diff stat (staged)",
                command_output(["git", "diff", "--cached", "--stat"], repo).rstrip(),
                "",
                "# Untracked files",
                command_output(
                    ["git", "ls-files", "--others", "--exclude-standard"],
                    repo,
                ).rstrip(),
                "",
                "# Diff (unstaged)",
                command_output(["git", "diff", "--find-renames"], repo).rstrip(),
                "",
                "# Diff (staged)",
                command_output(["git", "diff", "--cached", "--find-renames"], repo).rstrip(),
                "",
                "# Untracked file contents",
                untracked_contents(repo).rstrip(),
            ]
        )
    else:
        changed_files = null_separated_paths(
            ["git", "show", "--format=", "--find-renames", "--name-only", "-z", commit],
            repo,
        )
        resolved = None
        parts.extend(
            [
                "# Target",
                "mode: commit",
                f"commit: {commit}",
                "",
                "# Commit",
                command_output(
                    [
                        "git",
                        "show",
                        "--find-renames",
                        "--stat",
                        "--oneline",
                        "--decorate",
                        "--no-ext-diff",
                        commit,
                    ],
                    repo,
                ).rstrip(),
                "",
                "# Diff",
                command_output(
                    [
                        "git",
                        "show",
                        "--find-renames",
                        "--format=fuller",
                        "--no-ext-diff",
                        commit,
                    ],
                    repo,
                ).rstrip(),
            ]
        )
    return mode, "\n".join(parts).rstrip() + "\n", changed_files, resolved


def bundle_digest(bundle: str) -> str:
    return hashlib.sha256(bundle.encode()).hexdigest()


def repository_state_digest(repo: Path) -> str:
    digest = hashlib.sha256()
    for args in (
        ["git", "rev-parse", "HEAD"],
        ["git", "diff", "--binary", "--no-ext-diff"],
        ["git", "diff", "--cached", "--binary", "--no-ext-diff"],
    ):
        digest.update(command_output(args, repo).encode())
        digest.update(b"\0")
    for relative in sorted(untracked_files(repo)):
        path = repo / relative
        digest.update(relative.encode())
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(b"symlink\0")
            digest.update(os.readlink(path).encode())
        elif path.is_file():
            digest.update(b"file\0")
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(65_536), b""):
                    digest.update(chunk)
        else:
            digest.update(b"other\0")
        digest.update(b"\0")
    return digest.hexdigest()


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
        diff = (
            command_output(
                [
                    "git",
                    "--literal-pathspecs",
                    "diff",
                    "--find-renames",
                    f"{resolved_base}...HEAD",
                    *paths,
                ],
                repo,
            ).rstrip()
            if implementation_files
            else ""
        )
        parts.extend(
            [
                f"base: {resolved_base}",
                "head: HEAD",
                "",
                "# Changed implementation files",
                "\n".join(implementation_files),
                "",
                "# Implementation diff",
                diff,
            ]
        )
    elif mode == "local":
        allowed = set(implementation_files)
        unstaged = (
            command_output(
                ["git", "--literal-pathspecs", "diff", "--find-renames", *paths],
                repo,
            ).rstrip()
            if implementation_files
            else ""
        )
        staged = (
            command_output(
                ["git", "--literal-pathspecs", "diff", "--cached", "--find-renames", *paths],
                repo,
            ).rstrip()
            if implementation_files
            else ""
        )
        parts.extend(
            [
                "",
                "# Changed implementation files",
                "\n".join(implementation_files),
                "",
                "# Diff (unstaged)",
                unstaged,
                "",
                "# Diff (staged)",
                staged,
                "",
                "# Untracked implementation file contents",
                untracked_contents(repo, allowed).rstrip(),
            ]
        )
    else:
        diff = (
            command_output(
                [
                    "git",
                    "--literal-pathspecs",
                    "show",
                    "--find-renames",
                    "--format=",
                    "--no-ext-diff",
                    commit,
                    *paths,
                ],
                repo,
            ).rstrip()
            if implementation_files
            else ""
        )
        parts.extend(
            [
                f"commit: {commit}",
                "",
                "# Changed implementation files",
                "\n".join(implementation_files),
                "",
                "# Implementation diff",
                diff,
            ]
        )
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
            [
                "git",
                "--literal-pathspecs",
                "diff",
                "--find-renames",
                f"{resolved_base}...HEAD",
                *paths,
            ],
            repo,
        ).rstrip()
    if mode == "local":
        parts = [
            command_output(
                ["git", "--literal-pathspecs", "diff", "--find-renames", *paths],
                repo,
            ).rstrip(),
            command_output(
                ["git", "--literal-pathspecs", "diff", "--cached", "--find-renames", *paths],
                repo,
            ).rstrip(),
            untracked_contents(repo, set(context_files)).rstrip(),
        ]
        return "\n".join(part for part in parts if part)
    return command_output(
        [
            "git",
            "--literal-pathspecs",
            "show",
            "--find-renames",
            "--format=",
            "--no-ext-diff",
            commit,
            *paths,
        ],
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


def related_file_evidence(
    repo: Path,
    item: dict[str, object],
) -> tuple[Path, int, int, list[str]]:
    if set(item) != {"path", "lines"}:
        raise RuntimeError("context builder related_files item has invalid fields")
    if not all(isinstance(item[key], str) and item[key] for key in ("path", "lines")):
        raise RuntimeError("context builder related_files fields must be non-empty strings")
    lines = item["lines"]
    if not re.fullmatch(r"[1-9]\d*(?:-[1-9]\d*)?", lines):
        raise RuntimeError("context builder related_files lines must be a line or line range")
    path = repository_evidence_file(repo, item["path"], "related_files.path")
    start_text, separator, end_text = lines.partition("-")
    start = int(start_text)
    end = int(end_text) if separator else start
    try:
        source_lines = read_regular_utf8(path, 2_000_000).splitlines()
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise RuntimeError(
            "context builder related_files path must be bounded UTF-8 text"
        ) from error
    if end < start or end > len(source_lines):
        raise RuntimeError("context builder related_files lines are outside its source file")
    return path, start, end, source_lines


def parse_context_builder_output(
    stdout: str,
    changed_files: list[str],
    repo: Path,
) -> dict[str, object]:
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
    validated_related = []
    for item in related:
        _, start, end, source_lines = related_file_evidence(repo, item)
        if item["path"] in changed_files:
            raise RuntimeError("context builder related_files must not include changed files")
        validated_related.append(
            {
                "path": item["path"],
                "lines": item["lines"],
                "content": "\n".join(source_lines[start - 1 : end]),
            }
        )
    result["related_files"] = validated_related
    return result


def render_review_context(
    repo: Path,
    context: dict[str, object],
    context_diff: str,
) -> str:
    rendered = "# Review context"
    if context_diff:
        rendered += "\n\n# Context file diff\n\n```text\n" + context_diff.rstrip() + "\n```"
    related_files = []
    for item in context["related_files"]:
        related_files.append(item)
    if related_files:
        rendered += "\n\n# Related files\n\n" + json.dumps(
            related_files,
            ensure_ascii=False,
            indent=2,
        )
    return rendered


def build_reviewer_prompt(reviewer_id: str, bundle: str, impact_context: str) -> str:
    prompt_template = Template((PROMPT_DIR / f"{reviewer_id}.md").read_text())
    return prompt_template.substitute(
        impact_context_section="" if reviewer_id == "adversarial" else impact_context.rstrip(),
        change_bundle=bundle.rstrip(),
    ).rstrip() + "\n"


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


def read_regular_utf8(path: Path, maximum_size: int) -> str:
    descriptor = -1
    try:
        flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum_size:
            raise ValueError("artifact is not a bounded regular file")
        chunks: list[bytes] = []
        remaining = maximum_size + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        output = b"".join(chunks)
        if len(output) > maximum_size:
            raise ValueError("artifact exceeds its size limit")
        return output.decode("utf-8")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def read_reviewer_result(path: Path) -> tuple[str, str]:
    try:
        output = read_regular_utf8(path, 200_000)
        return validate_output(output), output
    except (OSError, UnicodeDecodeError, ValueError):
        return "protocol_failure(invalid_result_file)", ""


def create_run_directory(run_root: Path | None) -> Path:
    root = run_root or Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="review-diff-code-", dir=root)).resolve()
    run_dir.chmod(0o700)
    (run_dir / RUN_MARKER).write_text("review-diff-code\n")
    return run_dir


def write_manifest(run_dir: Path, manifest: dict[str, object]) -> None:
    manifest_path = run_dir / MANIFEST_NAME
    pending = run_dir / f"{MANIFEST_NAME}.pending"
    payload = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(pending, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as destination:
            destination.write(payload)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(pending, manifest_path)
    except Exception:
        if pending.exists() and stat.S_ISREG(pending.lstat().st_mode):
            pending.unlink()
        raise
    finally:
        os.close(descriptor)


def load_run(run_dir_argument: Path) -> tuple[Path, dict[str, object]]:
    if run_dir_argument.is_symlink():
        raise RuntimeError("run directory must not be a symbolic link")
    run_dir = run_dir_argument.resolve(strict=True)
    marker = run_dir / RUN_MARKER
    manifest_path = run_dir / MANIFEST_NAME
    try:
        marker_text = read_regular_utf8(marker, 100)
        manifest_text = read_regular_utf8(manifest_path, 100_000)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise RuntimeError("run metadata is missing or invalid") from error
    if marker_text != "review-diff-code\n":
        raise RuntimeError("run directory is not owned by review-diff-code")
    try:
        manifest = json.loads(manifest_text)
    except json.JSONDecodeError as error:
        raise RuntimeError("run manifest is missing or invalid") from error
    if manifest.get("run_dir") != str(run_dir):
        raise RuntimeError("run manifest does not match its directory")
    return run_dir, manifest


def prepare_review(args: argparse.Namespace) -> int:
    repo = repository_root().resolve()
    mode, raw_bundle, changed_files, resolved_base = create_raw_bundle(
        repo,
        args.mode,
        args.base,
        args.commit,
    )
    run_dir = create_run_directory(args.run_root)
    context_dir = run_dir / "context-builder"
    context_dir.mkdir()
    prompt_file = context_dir / "prompt.md"
    result_file = context_dir / "result.json"
    prompt_file.write_text(build_context_builder_prompt(changed_files, raw_bundle))
    manifest = {
        "version": 1,
        "run_dir": str(run_dir),
        "repo": str(repo),
        "mode": mode,
        "resolved_base": resolved_base,
        "commit": args.commit,
        "changed_files": changed_files,
        "bundle_digest": bundle_digest(raw_bundle),
        "repository_state_digest": repository_state_digest(repo),
        "state": "prepared",
    }
    write_manifest(run_dir, manifest)
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "context_prompt_file": str(prompt_file),
                "context_result_file": str(result_file),
            },
            ensure_ascii=False,
        )
    )
    return 0


def validate_repository_state(manifest: dict[str, object], repo: Path) -> None:
    repo = Path(manifest["repo"]).resolve(strict=True)
    current_mode, current_bundle, current_files, current_base = create_raw_bundle(
        repo,
        manifest["mode"],
        manifest["resolved_base"],
        manifest["commit"],
    )
    if (
        current_mode != manifest["mode"]
        or current_base != manifest["resolved_base"]
        or current_files != manifest["changed_files"]
        or bundle_digest(current_bundle) != manifest["bundle_digest"]
        or repository_state_digest(repo) != manifest["repository_state_digest"]
    ):
        raise ReviewError(
            "repository_drift",
            "repository changed after prepare; discard this run and prepare again",
        )


def validated_context(
    run_dir: Path,
    manifest: dict[str, object],
    repo: Path,
) -> dict[str, object]:
    context_file = run_dir / "context-builder" / "result.json"
    try:
        context_raw = read_regular_utf8(context_file, 200_000)
        return parse_context_builder_output(
            context_raw,
            manifest["changed_files"],
            repo,
        )
    except (OSError, UnicodeDecodeError, ValueError, RuntimeError) as error:
        raise ReviewError("context_result_invalid", str(error)) from error


def validate_context_review(args: argparse.Namespace) -> int:
    run_dir, manifest = load_run(args.run_dir)
    repo = Path(manifest["repo"]).resolve(strict=True)
    validate_repository_state(manifest, repo)
    validated_context(run_dir, manifest, repo)
    print(json.dumps({"run_dir": str(run_dir), "status": "valid"}))
    return 0


def reset_context_review(args: argparse.Namespace) -> int:
    run_dir, manifest = load_run(args.run_dir)
    if manifest.get("state") != "prepared":
        raise ReviewError(
            "run_protocol_invalid",
            "context result can only be reset before reviewer routing",
        )
    result_file = run_dir / "context-builder" / "result.json"
    if result_file.exists() or result_file.is_symlink():
        if not stat.S_ISREG(result_file.lstat().st_mode):
            raise ReviewError(
                "run_protocol_invalid",
                "context result is not a regular file",
            )
        result_file.unlink()
    print(json.dumps({"run_dir": str(run_dir), "status": "reset"}))
    return 0


def route_review(args: argparse.Namespace) -> int:
    run_dir, manifest = load_run(args.run_dir)
    repo = Path(manifest["repo"]).resolve(strict=True)
    reviewers_root = run_dir / "reviewers"
    if manifest.get("state") == "routed":
        validate_routed_artifacts(run_dir)
        return print_routed_review(run_dir)
    if manifest.get("state") != "prepared":
        raise ReviewError("run_protocol_invalid", "review run is not ready for routing")
    if reviewers_root.exists() or reviewers_root.is_symlink():
        validate_routed_artifacts(run_dir)
        manifest["state"] = "routed"
        write_manifest(run_dir, manifest)
        return print_routed_review(run_dir)
    validate_repository_state(manifest, repo)
    context = validated_context(run_dir, manifest, repo)
    implementation_bundle = create_implementation_bundle(
        repo,
        manifest["mode"],
        manifest["resolved_base"],
        manifest["commit"],
        context["implementation_files"],
    )
    context_diff = create_context_diff(
        repo,
        manifest["mode"],
        manifest["resolved_base"],
        manifest["commit"],
        context["context_files"],
    )
    impact_context = render_review_context(repo, context, context_diff)
    prompts = {
        reviewer_id: build_reviewer_prompt(
            reviewer_id,
            implementation_bundle,
            impact_context,
        )
        for reviewer_id, _ in REVIEWERS
    }
    staging = Path(tempfile.mkdtemp(prefix=".reviewers-", dir=run_dir))
    try:
        prompt_digests: dict[str, str] = {}
        for reviewer_id, _ in REVIEWERS:
            reviewer_dir = staging / reviewer_id
            reviewer_dir.mkdir()
            (reviewer_dir / "prompt.md").write_text(prompts[reviewer_id])
            prompt_digests[reviewer_id] = bundle_digest(prompts[reviewer_id])
        (staging / "integrity.json").write_text(
            json.dumps(
                {"version": 1, "prompt_digests": prompt_digests},
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        validate_repository_state(manifest, repo)
        staging.replace(reviewers_root)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    manifest["state"] = "routed"
    write_manifest(run_dir, manifest)
    return print_routed_review(run_dir)


def print_routed_review(run_dir: Path) -> int:
    reviewers = {
        reviewer_id: {
            "prompt_file": str(run_dir / "reviewers" / reviewer_id / "prompt.md"),
            "result_file": str(run_dir / "reviewers" / reviewer_id / "result.md"),
        }
        for reviewer_id, _ in REVIEWERS
    }
    print(json.dumps({"run_dir": str(run_dir), "reviewers": reviewers}, ensure_ascii=False))
    return 0


def validate_routed_artifacts(run_dir: Path) -> None:
    reviewers_root = run_dir / "reviewers"
    if not reviewers_root.exists() or not stat.S_ISDIR(reviewers_root.lstat().st_mode):
        raise ReviewError("run_protocol_invalid", "reviewer artifact root is invalid")
    expected_root_entries = {"integrity.json", *(reviewer_id for reviewer_id, _ in REVIEWERS)}
    if {path.name for path in reviewers_root.iterdir()} != expected_root_entries:
        raise ReviewError("run_protocol_invalid", "reviewer artifact root has invalid members")
    try:
        integrity = json.loads(read_regular_utf8(reviewers_root / "integrity.json", 20_000))
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise ReviewError("run_protocol_invalid", "reviewer integrity record is invalid") from error
    expected_ids = {reviewer_id for reviewer_id, _ in REVIEWERS}
    if (
        not isinstance(integrity, dict)
        or set(integrity) != {"version", "prompt_digests"}
        or integrity["version"] != 1
        or not isinstance(integrity["prompt_digests"], dict)
        or set(integrity["prompt_digests"]) != expected_ids
    ):
        raise ReviewError("run_protocol_invalid", "reviewer integrity schema is invalid")
    for reviewer_id, _ in REVIEWERS:
        reviewer_dir = reviewers_root / reviewer_id
        prompt_file = reviewer_dir / "prompt.md"
        if (
            not reviewer_dir.exists()
            or not stat.S_ISDIR(reviewer_dir.lstat().st_mode)
            or not prompt_file.exists()
            or not stat.S_ISREG(prompt_file.lstat().st_mode)
        ):
            raise ReviewError(
                "run_protocol_invalid",
                f"reviewer artifact is incomplete: {reviewer_id}",
            )
        members = {path.name for path in reviewer_dir.iterdir()}
        if not {"prompt.md"} <= members <= {"prompt.md", "result.md"}:
            raise ReviewError(
                "run_protocol_invalid",
                f"reviewer artifact has invalid members: {reviewer_id}",
            )
        try:
            prompt = read_regular_utf8(prompt_file, 1_000_000)
        except (OSError, UnicodeDecodeError, ValueError) as error:
            raise ReviewError(
                "run_protocol_invalid",
                f"reviewer prompt is invalid: {reviewer_id}",
            ) from error
        if bundle_digest(prompt) != integrity["prompt_digests"][reviewer_id]:
            raise ReviewError(
                "run_protocol_invalid",
                f"reviewer prompt digest mismatch: {reviewer_id}",
            )


def collect_review(args: argparse.Namespace) -> int:
    run_dir, manifest = load_run(args.run_dir)
    if manifest.get("state") != "routed":
        raise RuntimeError("review run has not been routed")
    repo = Path(manifest["repo"]).resolve(strict=True)
    validate_repository_state(manifest, repo)
    validate_routed_artifacts(run_dir)
    results: list[tuple[str, str, str, str]] = []
    for reviewer_id, title in REVIEWERS:
        result_file = run_dir / "reviewers" / reviewer_id / "result.md"
        status, output = read_reviewer_result(result_file)
        results.append((reviewer_id, title, status, output))
    validate_repository_state(manifest, repo)
    successes = sum(status == "success" for _, _, status, _ in results)
    overall = "failed" if successes == 0 else "partial_failure" if successes < len(results) else "success"
    print("# Review Summary\n")
    print(f"overall_status: {overall}")
    print(f"mode: {manifest['mode']}")
    print("orchestrator: codex_subagents")
    print("reviewer_isolation: context_level\n")
    print("| Reviewer | Status |")
    print("| --- | --- |")
    for _, title, status, _ in results:
        print(f"| {title} | {status} |")
    print("\n# Findings by Reviewer")
    for _, title, status, output in results:
        print(f"\n## {title}\n\nstatus: {status}\n")
        print(output.rstrip() if output.strip() else "No output.")
    return 1 if successes == 0 else 0


def cleanup_review(args: argparse.Namespace) -> int:
    run_dir, _ = load_run(args.run_dir)
    known_files = {
        RUN_MARKER,
        MANIFEST_NAME,
        f"{MANIFEST_NAME}.pending",
        "context-builder/prompt.md",
        "context-builder/result.json",
        "reviewers/integrity.json",
    }
    known_directories = {"context-builder", "reviewers"}
    for reviewer_id, _ in REVIEWERS:
        known_files.update(
            {
                f"reviewers/{reviewer_id}/prompt.md",
                f"reviewers/{reviewer_id}/result.md",
            }
        )
        known_directories.add(f"reviewers/{reviewer_id}")
    for relative in known_directories:
        path = run_dir / relative
        if path.exists() or path.is_symlink():
            if not stat.S_ISDIR(path.lstat().st_mode):
                raise ReviewError(
                    "cleanup_refused",
                    f"protocol directory is not a real directory: {relative}",
                )
    actual = {
        str(path.relative_to(run_dir))
        for path in run_dir.rglob("*")
    }
    unknown = actual - known_files - known_directories
    if unknown:
        raise ReviewError(
            "cleanup_refused",
            "run directory contains unknown content: " + ", ".join(sorted(unknown))
        )
    for relative in sorted(known_files, reverse=True):
        path = run_dir / relative
        if path.exists() or path.is_symlink():
            path.unlink()
    for relative in sorted(known_directories, reverse=True):
        path = run_dir / relative
        if path.exists():
            path.rmdir()
    run_dir.rmdir()
    return 0


def main() -> int:
    args = parse_args()
    try:
        if args.command == "prepare":
            return prepare_review(args)
        if args.command == "reset-context":
            return reset_context_review(args)
        if args.command == "validate-context":
            return validate_context_review(args)
        if args.command == "route":
            return route_review(args)
        if args.command == "collect":
            return collect_review(args)
        return cleanup_review(args)
    except ReviewError as error:
        print(
            json.dumps(
                {"error": {"code": error.code, "message": str(error)}},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    except Exception as error:
        print(
            json.dumps(
                {"error": {"code": "internal_error", "message": str(error)}},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
