#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from string import Template


NO_FINDINGS = {
    "対応が必要な指摘はありません。",
    "No actionable findings",
    "No actionable findings.",
}
FINDING_HEADING = re.compile(r"^### \[(critical|high|medium|low)\] .+")
REVIEWER_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_DIGEST = re.compile(r"^[0-9a-f]{64}$")
ADVERSARIAL_REVIEWER = {
    "id": "adversarial",
    "name": "Adversarial",
}
MAX_REVIEWER_PROMPT_BYTES = 1_000_000
JAPANESE_FINDING_FIELDS = ("- 対象:", "- 問題:", "- 根拠:", "- 修正案:")
LEGACY_ENGLISH_FINDING_FIELDS = ("- Target:", "- Problem:", "- Evidence:", "- Suggested fix:")
SKILL_DIR = Path(__file__).resolve().parent.parent
PROMPT_DIR = SKILL_DIR / "assets" / "reviewer-prompts"
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

    prepare = subparsers.add_parser("prepare", help="Fix the Git review target.")
    prepare.add_argument("--mode", choices=("auto", "branch", "local", "commit"), default="auto")
    prepare.add_argument("--base", help="Base ref for branch mode")
    prepare.add_argument("--commit", default="HEAD", help="Commit ref for commit mode")
    prepare.add_argument(
        "--run-root",
        type=Path,
        help="Directory under which a private run directory is created.",
    )

    for command in ("collect", "cleanup"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--run-dir", type=Path, required=True)
    route = subparsers.add_parser("route")
    route.add_argument("--run-dir", type=Path, required=True)
    route.add_argument("--roster-file", type=Path, required=True)

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


def resolve_commit_id(repo: Path, revision: str) -> str:
    return command_output(["git", "rev-parse", "--verify", f"{revision}^{{commit}}"], repo).strip()


def prepare_target(
    repo: Path,
    mode: str,
    base: str | None,
    commit: str,
) -> tuple[str, dict[str, str]]:
    if mode == "auto":
        mode = "local" if has_dirty_work(repo) else "branch"
    if mode == "branch":
        return mode, {
            "base": resolve_commit_id(repo, resolve_base(repo, base)),
            "head": resolve_commit_id(repo, "HEAD"),
        }
    if mode == "commit":
        return mode, {"commit": resolve_commit_id(repo, commit)}
    return mode, {"head": resolve_commit_id(repo, "HEAD")}


def changed_files_for_target(
    repo: Path,
    mode: str,
    target: dict[str, str],
) -> list[str]:
    if mode == "branch":
        return null_separated_paths(
            [
                "git",
                "diff",
                "--find-renames",
                "--name-only",
                "-z",
                f"{target['base']}...{target['head']}",
            ],
            repo,
        )
    if mode == "commit":
        return null_separated_paths(
            [
                "git",
                "show",
                "--format=",
                "--find-renames",
                "--name-only",
                "-z",
                target["commit"],
            ],
            repo,
        )
    return sorted(
        set(
            null_separated_paths(["git", "diff", "--name-only", "-z"], repo)
            + null_separated_paths(["git", "diff", "--cached", "--name-only", "-z"], repo)
            + untracked_files(repo)
        )
    )


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


def null_separated_paths(args: list[str], repo: Path) -> list[str]:
    raw = subprocess.run(args, cwd=repo, capture_output=True, check=True).stdout
    return [os.fsdecode(path) for path in raw.split(b"\0") if path]


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


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
        metadata = path.lstat()
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(str(stat.S_IFMT(metadata.st_mode)).encode())
        digest.update(b"\0")
        digest.update(str(stat.S_IMODE(metadata.st_mode)).encode())
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


def read_reviewer_roster(path: Path) -> dict[str, object]:
    try:
        raw = read_regular_utf8(path.resolve(strict=True), 100_000)
        roster_config = json.loads(raw)
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise ReviewError("reviewer_roster_invalid", "reviewer roster is not valid JSON") from error
    if (
        not isinstance(roster_config, dict)
        or set(roster_config) != {"reviewers", "adversarial"}
        or not isinstance(roster_config["reviewers"], list)
        or not 1 <= len(roster_config["reviewers"]) <= 2
        or not isinstance(roster_config["adversarial"], dict)
        or set(roster_config["adversarial"]) != {"excluded_context_paths"}
    ):
        raise ReviewError(
            "reviewer_roster_invalid",
            "reviewer roster must use the object schema with one or two dynamic reviewers",
        )
    roster = roster_config["reviewers"]
    expected_fields = {
        "id",
        "name",
        "expertise",
        "mission",
        "focus",
        "reason",
    }
    validated: list[dict[str, str]] = []
    for reviewer in roster:
        if (
            not isinstance(reviewer, dict)
            or set(reviewer) != expected_fields
            or not all(isinstance(value, str) and value.strip() for value in reviewer.values())
            or not REVIEWER_ID.fullmatch(reviewer["id"])
            or reviewer["id"] == "adversarial"
        ):
            raise ReviewError("reviewer_roster_invalid", "reviewer roster entry is invalid")
        validated.append({key: reviewer[key].strip() for key in expected_fields})
    reviewer_ids = [reviewer["id"] for reviewer in validated]
    if len(reviewer_ids) != len(set(reviewer_ids)):
        raise ReviewError("reviewer_roster_invalid", "reviewer ids must be unique")
    excluded_paths = roster_config["adversarial"]["excluded_context_paths"]
    if not isinstance(excluded_paths, list):
        raise ReviewError(
            "reviewer_roster_invalid",
            "excluded context paths must be an array",
        )
    validated_paths: list[str] = []
    for value in excluded_paths:
        if (
            not isinstance(value, str)
            or not value.strip()
            or Path(value).is_absolute()
            or ".." in Path(value).parts
        ):
            raise ReviewError(
                "reviewer_roster_invalid",
                "excluded context paths must be repository-relative paths without '..'",
            )
        validated_paths.append(value.strip())
    return {
        "reviewers": [*validated, ADVERSARIAL_REVIEWER.copy()],
        "excluded_context_paths": validated_paths,
    }


def build_reviewer_prompt(
    reviewer: dict[str, str],
    manifest: dict[str, object],
    result_file: Path,
    excluded_context_paths: list[str],
) -> str:
    template_name = "adversarial.md" if reviewer["id"] == "adversarial" else "reviewer.md"
    prompt_template = Template((PROMPT_DIR / template_name).read_text())
    target = manifest["target"]
    repo = shlex.quote(manifest["repo"])
    exclusions = [
        shlex.quote(f":(top,literal,exclude){path.rstrip('/')}")
        for path in excluded_context_paths
    ]
    pathspec = " -- ." + (" " + " ".join(exclusions) if exclusions else "")
    if manifest["mode"] == "branch":
        investigation_command = (
            f"git -C {repo} diff --find-renames "
            f"{target['base']}...{target['head']}{pathspec}"
        )
    elif manifest["mode"] == "commit":
        investigation_command = (
            f"git -C {repo} show --find-renames {target['commit']}{pathspec}"
        )
    else:
        investigation_command = (
            f"git -C {repo} diff --find-renames {target['head']}{pathspec}; "
            f"git -C {repo} diff --cached --find-renames {target['head']}{pathspec}; "
            f"git -C {repo} ls-files --others --exclude-standard{pathspec}"
        )
    changed_files = [
        path
        for path in manifest["changed_files"]
        if not any(
            path == excluded.rstrip("/") or path.startswith(excluded.rstrip("/") + "/")
            for excluded in excluded_context_paths
        )
    ]
    return prompt_template.substitute(
        reviewer_name=reviewer["name"],
        reviewer_expertise=reviewer.get("expertise", ""),
        reviewer_mission=reviewer.get("mission", ""),
        review_focus=reviewer.get("focus", ""),
        selection_reason=reviewer.get("reason", ""),
        investigation_command=investigation_command,
        changed_files_json=json.dumps(changed_files, ensure_ascii=True, indent=2),
        result_file=str(result_file),
        excluded_context_paths_json=json.dumps(
            excluded_context_paths,
            ensure_ascii=True,
            indent=2,
        ),
    ).rstrip() + "\n"


def validate_output(stdout: str) -> str:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        return "protocol_failure(empty_output)"
    if "\n".join(lines) in NO_FINDINGS:
        return "success"
    required_fields = JAPANESE_FINDING_FIELDS
    has_explicit_format = False
    if lines[0] == "## 指摘":
        has_explicit_format = True
        lines = lines[1:]
    elif lines[0] == "## Findings":
        has_explicit_format = True
        required_fields = LEGACY_ENGLISH_FINDING_FIELDS
        lines = lines[1:]
    if not lines or not FINDING_HEADING.fullmatch(lines[0]):
        return "protocol_failure(invalid_format)"
    heading_indexes = [index for index, line in enumerate(lines) if FINDING_HEADING.fullmatch(line)]
    if not has_explicit_format:
        first_end = heading_indexes[1] if len(heading_indexes) > 1 else len(lines)
        first_block = lines[heading_indexes[0] + 1 : first_end]
        if any(line.startswith(LEGACY_ENGLISH_FINDING_FIELDS[0]) for line in first_block):
            required_fields = LEGACY_ENGLISH_FINDING_FIELDS
    for position, start in enumerate(heading_indexes):
        end = heading_indexes[position + 1] if position + 1 < len(heading_indexes) else len(lines)
        block = lines[start + 1 : end]
        if not all(any(line.startswith(field) for line in block) for field in required_fields):
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


def validate_manifest_schema(manifest: object, run_dir: Path) -> dict[str, object]:
    common_fields = {
        "version",
        "run_dir",
        "repo",
        "mode",
        "target",
        "changed_files",
        "repository_state_digest",
        "state",
    }
    if not isinstance(manifest, dict) or not common_fields <= set(manifest):
        raise RuntimeError("run manifest schema is invalid")
    if (
        manifest["version"] != 1
        or manifest["run_dir"] != str(run_dir)
        or not isinstance(manifest["repo"], str)
        or not Path(manifest["repo"]).is_absolute()
        or manifest["mode"] not in {"branch", "commit", "local"}
        or not isinstance(manifest["changed_files"], list)
        or not all(isinstance(path, str) and path for path in manifest["changed_files"])
        or len(set(manifest["changed_files"])) != len(manifest["changed_files"])
        or not isinstance(manifest["repository_state_digest"], str)
        or not SHA256_DIGEST.fullmatch(manifest["repository_state_digest"])
        or manifest["state"] not in {"prepared", "routed"}
    ):
        raise RuntimeError("run manifest schema is invalid")
    expected_target_fields = {
        "branch": {"base", "head"},
        "commit": {"commit"},
        "local": {"head"},
    }[manifest["mode"]]
    target = manifest["target"]
    try:
        object_format = command_output(
            ["git", "rev-parse", "--show-object-format"],
            Path(manifest["repo"]),
        ).strip()
    except (OSError, RuntimeError) as error:
        raise RuntimeError("run manifest repository object format is invalid") from error
    object_id_length = {"sha1": 40, "sha256": 64}.get(object_format)
    if (
        object_id_length is None
        or not isinstance(target, dict)
        or set(target) != expected_target_fields
        or not all(
            isinstance(value, str)
            and len(value) == object_id_length
            and re.fullmatch(r"[0-9a-f]+", value)
            for value in target.values()
        )
    ):
        raise RuntimeError("run manifest target is invalid")
    extra_fields = set(manifest) - common_fields
    if extra_fields:
        if extra_fields != {"route_config", "reviewers"}:
            raise RuntimeError("run manifest schema is invalid")
        route_config = manifest["route_config"]
        if (
            not isinstance(route_config, dict)
            or set(route_config) != {"reviewers", "excluded_context_paths"}
            or route_config["reviewers"] != manifest["reviewers"]
            or not isinstance(route_config["excluded_context_paths"], list)
            or not all(
                isinstance(path, str)
                and path
                and not Path(path).is_absolute()
                and ".." not in Path(path).parts
                for path in route_config["excluded_context_paths"]
            )
        ):
            raise RuntimeError("run manifest route config is invalid")
    elif manifest["state"] == "routed":
        raise RuntimeError("routed manifest is missing route config")
    return manifest


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
    manifest = validate_manifest_schema(manifest, run_dir)
    reviewers = manifest.get("reviewers")
    if reviewers is not None:
        dynamic_fields = {"id", "name", "expertise", "mission", "focus", "reason"}
        if (
            not isinstance(reviewers, list)
            or not reviewers
            or any(
                not isinstance(reviewer, dict)
                or (
                    set(reviewer) != {"id", "name"}
                    if reviewer.get("id") == "adversarial"
                    else set(reviewer) != dynamic_fields
                )
                or not all(isinstance(value, str) and value for value in reviewer.values())
                or not REVIEWER_ID.fullmatch(reviewer["id"])
                for reviewer in reviewers
            )
            or len({reviewer["id"] for reviewer in reviewers}) != len(reviewers)
            or sum(reviewer["id"] == "adversarial" for reviewer in reviewers) != 1
        ):
            raise RuntimeError("run manifest reviewer roster is invalid")
    return run_dir, manifest


def prepare_review(args: argparse.Namespace) -> int:
    repo = repository_root().resolve()
    mode, target = prepare_target(
        repo,
        args.mode,
        args.base,
        args.commit,
    )
    changed_files = changed_files_for_target(repo, mode, target)
    run_dir = create_run_directory(args.run_root)
    manifest = {
        "version": 1,
        "run_dir": str(run_dir),
        "repo": str(repo),
        "mode": mode,
        "target": target,
        "changed_files": changed_files,
        "repository_state_digest": repository_state_digest(repo),
        "state": "prepared",
    }
    write_manifest(run_dir, manifest)
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "target": target,
                "changed_files": changed_files,
            },
            ensure_ascii=False,
        )
    )
    return 0


def validate_repository_state(manifest: dict[str, object], repo: Path) -> None:
    repo = Path(manifest["repo"]).resolve(strict=True)
    if (
        changed_files_for_target(repo, manifest["mode"], manifest["target"])
        != manifest["changed_files"]
        or repository_state_digest(repo) != manifest["repository_state_digest"]
    ):
        raise ReviewError(
            "repository_drift",
            "repository changed after prepare; discard this run and prepare again",
        )


def route_review(args: argparse.Namespace) -> int:
    run_dir, manifest = load_run(args.run_dir)
    repo = Path(manifest["repo"]).resolve(strict=True)
    roster_config = read_reviewer_roster(args.roster_file)
    roster = roster_config["reviewers"]
    excluded_context_paths = roster_config["excluded_context_paths"]
    route_config = {
        "reviewers": roster,
        "excluded_context_paths": excluded_context_paths,
    }
    reviewers_root = run_dir / "reviewers"
    if manifest.get("state") == "routed":
        if manifest.get("route_config") != route_config:
            raise ReviewError("run_protocol_invalid", "reviewer roster changed after routing")
        validate_repository_state(manifest, repo)
        validate_routed_artifacts(run_dir)
        return print_routed_review(run_dir)
    if manifest.get("state") != "prepared":
        raise ReviewError("run_protocol_invalid", "review run is not ready for routing")
    if manifest.get("route_config") not in (None, route_config):
        raise ReviewError("run_protocol_invalid", "reviewer roster changed during routing")
    if manifest.get("route_config") is None:
        manifest["route_config"] = route_config
        manifest["reviewers"] = roster
        write_manifest(run_dir, manifest)
    if reviewers_root.exists() or reviewers_root.is_symlink():
        validate_repository_state(manifest, repo)
        validate_routed_artifacts(run_dir)
        manifest["state"] = "routed"
        write_manifest(run_dir, manifest)
        return print_routed_review(run_dir)
    validate_repository_state(manifest, repo)
    staging = Path(tempfile.mkdtemp(prefix=".reviewers-", dir=run_dir))
    try:
        prompt_digests: dict[str, str] = {}
        for reviewer in roster:
            reviewer_id = reviewer["id"]
            reviewer_dir = staging / reviewer_id
            reviewer_dir.mkdir()
            result_file = reviewers_root / reviewer_id / "result.md"
            prompt = build_reviewer_prompt(
                reviewer,
                manifest,
                result_file,
                excluded_context_paths if reviewer_id == "adversarial" else [],
            )
            prompt_file = reviewer_dir / "prompt.md"
            prompt_file.write_text(prompt)
            try:
                validated_prompt = read_regular_utf8(
                    prompt_file,
                    MAX_REVIEWER_PROMPT_BYTES,
                )
                if len(validated_prompt.encode()) >= MAX_REVIEWER_PROMPT_BYTES:
                    raise ValueError("reviewer prompt must be smaller than its size limit")
            except (OSError, UnicodeDecodeError, ValueError) as error:
                raise ReviewError(
                    "run_protocol_invalid",
                    f"reviewer prompt is invalid: {reviewer_id}",
                ) from error
            prompt_digests[reviewer_id] = text_digest(validated_prompt)
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
    _, manifest = load_run(run_dir)
    reviewers = {}
    for reviewer in manifest["reviewers"]:
        reviewer_id = reviewer["id"]
        reviewers[reviewer_id] = {
            "prompt_file": str(run_dir / "reviewers" / reviewer_id / "prompt.md"),
            "result_file": str(run_dir / "reviewers" / reviewer_id / "result.md"),
        }
    print(json.dumps({"run_dir": str(run_dir), "reviewers": reviewers}, ensure_ascii=False))
    return 0


def validate_routed_artifacts(run_dir: Path) -> None:
    _, manifest = load_run(run_dir)
    reviewers = manifest.get("reviewers")
    if not isinstance(reviewers, list):
        raise ReviewError("run_protocol_invalid", "reviewer roster is missing")
    reviewer_ids = [reviewer["id"] for reviewer in reviewers]
    reviewers_root = run_dir / "reviewers"
    if not reviewers_root.exists() or not stat.S_ISDIR(reviewers_root.lstat().st_mode):
        raise ReviewError("run_protocol_invalid", "reviewer artifact root is invalid")
    expected_root_entries = {"integrity.json", *reviewer_ids}
    if {path.name for path in reviewers_root.iterdir()} != expected_root_entries:
        raise ReviewError("run_protocol_invalid", "reviewer artifact root has invalid members")
    try:
        integrity = json.loads(read_regular_utf8(reviewers_root / "integrity.json", 20_000))
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise ReviewError("run_protocol_invalid", "reviewer integrity record is invalid") from error
    expected_ids = set(reviewer_ids)
    if (
        not isinstance(integrity, dict)
        or set(integrity) != {"version", "prompt_digests"}
        or integrity["version"] != 1
        or not isinstance(integrity["prompt_digests"], dict)
        or set(integrity["prompt_digests"]) != expected_ids
    ):
        raise ReviewError("run_protocol_invalid", "reviewer integrity schema is invalid")
    for reviewer_id in reviewer_ids:
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
            prompt = read_regular_utf8(prompt_file, MAX_REVIEWER_PROMPT_BYTES)
            if len(prompt.encode()) >= MAX_REVIEWER_PROMPT_BYTES:
                raise ValueError("reviewer prompt must be smaller than its size limit")
        except (OSError, UnicodeDecodeError, ValueError) as error:
            raise ReviewError(
                "run_protocol_invalid",
                f"reviewer prompt is invalid: {reviewer_id}",
            ) from error
        if text_digest(prompt) != integrity["prompt_digests"][reviewer_id]:
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
    for reviewer in manifest["reviewers"]:
        reviewer_id = reviewer["id"]
        title = reviewer["name"]
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
    print("\n# レビュー担当別の指摘")
    for _, title, status, output in results:
        print(f"\n## {title}\n\nstatus: {status}\n")
        print(output.rstrip() if output.strip() else "No output.")
    return 1 if successes == 0 else 0


def cleanup_review(args: argparse.Namespace) -> int:
    run_dir, manifest = load_run(args.run_dir)
    known_files = {
        RUN_MARKER,
        MANIFEST_NAME,
        f"{MANIFEST_NAME}.pending",
        "reviewers/integrity.json",
    }
    known_directories = {"reviewers"}
    for reviewer in manifest.get("reviewers", []):
        reviewer_id = reviewer["id"]
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
