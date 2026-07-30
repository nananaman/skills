#!/usr/bin/env python3
"""ローカル差分を収集・検証し、意図ごとに解説するレポートを生成する。"""

from __future__ import annotations

import argparse
import base64
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


SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "assets" / "report-template.html"
MERMAID_BUNDLE = SKILL_DIR / "node_modules" / "mermaid" / "dist" / "mermaid.min.js"
PRISM_BUNDLES = (
    SKILL_DIR / "node_modules" / "prismjs" / "prism.js",
    *(
        SKILL_DIR / "node_modules" / "prismjs" / "components" / f"prism-{language}.min.js"
        for language in (
            "bash",
            "c",
            "cpp",
            "go",
            "java",
            "json",
            "kotlin",
            "markdown",
            "python",
            "ruby",
            "rust",
            "sql",
            "typescript",
            "jsx",
            "tsx",
            "yaml",
        )
    ),
)
def run_git(repo: Path, *args: str, check: bool = True) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def repository_root() -> Path:
    output = run_git(Path.cwd(), "rev-parse", "--show-toplevel")
    return Path(output.decode().strip()).resolve()


def serialize_json(value: object, *, indent: int | None = None) -> str:
    return json.dumps(value, ensure_ascii=True, indent=indent)


def nul_paths(repo: Path, *args: str) -> list[str]:
    output = run_git(repo, *args)
    return [item.decode("utf-8", errors="surrogateescape") for item in output.split(b"\0") if item]


def changed_pathspecs(repo: Path, source: str) -> list[tuple[str, list[str]]]:
    cached = ["--cached"] if source == "staged" else []
    fields = nul_paths(repo, "diff", *cached, "--find-renames", "--name-status", "-z")
    changes: list[tuple[str, list[str]]] = []
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        if status.startswith(("R", "C")):
            old_path, new_path = fields[index:index + 2]
            changes.append((new_path, [old_path, new_path]))
            index += 2
        else:
            path = fields[index]
            changes.append((path, [path]))
            index += 1
    return changes


def stable_id(source: str, path: str, raw: str, ordinal: int) -> str:
    digest = hashlib.sha256(
        f"{source}\0{path}\0{ordinal}\0{raw}".encode("utf-8", errors="surrogateescape")
    ).hexdigest()
    return f"h{digest[:12]}"


def parse_hunks(source: str, path: str, raw_diff: str) -> list[dict[str, object]]:
    lines = raw_diff.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.startswith("@@ ")]
    if not starts:
        return [
            {
                "id": stable_id(source, path, raw_diff, 0),
                "header": "Binary or metadata-only change",
                "raw": raw_diff,
            }
        ]

    hunks: list[dict[str, object]] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        raw = "".join(lines[start:end])
        hunks.append(
            {
                "id": stable_id(source, path, raw, position),
                "header": lines[start].rstrip("\n"),
                "raw": raw,
            }
        )
    return hunks


def tracked_entry(
    repo: Path,
    source: str,
    path: str,
    pathspecs: list[str] | None = None,
) -> dict[str, object]:
    cached = ["--cached"] if source == "staged" else []
    raw = run_git(
        repo,
        "diff",
        *cached,
        "--find-renames",
        "--binary",
        "--no-ext-diff",
        "--unified=3",
        "--",
        *(pathspecs or [path]),
    )
    raw_diff = raw.decode("utf-8", errors="replace")
    binary = (
        b"\0" in raw
        or b"GIT binary patch" in raw
        or (b"Binary files " in raw and b" differ" in raw)
    )
    return {
        "source": source,
        "path": path,
        "file_type": "tracked",
        "binary": binary,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_diff": raw_diff,
        "hunks": parse_hunks(source, path, raw_diff),
    }


def untracked_entry(repo: Path, path: str) -> dict[str, object]:
    absolute = repo / path
    mode = absolute.lstat().st_mode
    if stat.S_ISLNK(mode):
        target = os.readlink(absolute)
        identity = target.encode("utf-8", errors="surrogateescape")
        target_display = json.dumps(target, ensure_ascii=True)
        raw_diff = (
            f"diff --git a/{path} b/{path}\n"
            "new file mode 120000\n"
            "--- /dev/null\n"
            f"+++ b/{path}\n"
            "@@ -0,0 +1 @@\n"
            f"+{target_display}\n"
        )
        binary = False
        file_type = "symlink"
    elif not stat.S_ISREG(mode):
        identity = f"{path}\0{mode}".encode("utf-8", errors="surrogateescape")
        raw_diff = f"Special untracked file {path} (mode {stat.S_IFMT(mode):o})\n"
        binary = True
        file_type = "special"
    else:
        content = absolute.read_bytes()
        identity = content
        file_type = "regular"
        binary = False
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            raw_diff = f"Undisplayable non-UTF-8 file /dev/null and b/{path} differ\n"
            binary = True
        else:
            if b"\0" in content:
                raw_diff = f"Binary file /dev/null and b/{path} differ\n"
                binary = True
                text = ""
        if not binary:
            body = "".join(f"+{line}" for line in text.splitlines(keepends=True))
            if text and not text.endswith(("\n", "\r")):
                body += "\n\\ No newline at end of file\n"
            line_count = len(text.splitlines())
            raw_diff = (
                f"diff --git a/{path} b/{path}\n"
                "new file mode 100644\n"
                "--- /dev/null\n"
                f"+++ b/{path}\n"
                f"@@ -0,0 +1,{line_count} @@\n"
                f"{body}"
            )
            binary = False
    return {
        "source": "untracked",
        "path": path,
        "file_type": file_type,
        "binary": binary,
        "raw_sha256": hashlib.sha256(identity).hexdigest(),
        "raw_diff": raw_diff,
        "hunks": parse_hunks("untracked", path, raw_diff),
    }


def collect_snapshot(repo: Path) -> dict[str, object]:
    staged = changed_pathspecs(repo, "staged")
    unstaged = changed_pathspecs(repo, "unstaged")
    untracked = nul_paths(repo, "ls-files", "--others", "--exclude-standard", "-z")
    entries = [tracked_entry(repo, "staged", path, pathspecs) for path, pathspecs in staged]
    entries.extend(
        tracked_entry(repo, "unstaged", path, pathspecs)
        for path, pathspecs in unstaged
    )
    entries.extend(untracked_entry(repo, path) for path in untracked)
    if not entries:
        raise ValueError("no local changes")
    hunks = [
        {
            **hunk,
            "source": entry["source"],
            "path": entry["path"],
            "binary": entry["binary"],
        }
        for entry in entries
        for hunk in entry["hunks"]
    ]
    additions = 0
    deletions = 0
    for entry in entries:
        for hunk in entry["hunks"]:
            if not str(hunk["header"]).startswith("@@ "):
                continue
            for line in str(hunk["raw"]).splitlines()[1:]:
                if line.startswith("+"):
                    additions += 1
                elif line.startswith("-"):
                    deletions += 1
    branch_result = subprocess.run(
        ["git", "-C", str(repo), "symbolic-ref", "--short", "-q", "HEAD"],
        capture_output=True,
        check=False,
    )
    branch = branch_result.stdout.decode().strip()
    if not branch:
        branch = run_git(repo, "rev-parse", "--short", "HEAD").decode().strip()
    canonical = json.dumps(
        {
            "repository": str(repo),
            "branch": branch,
            "entries": entries,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "version": 1,
        "repository": str(repo),
        "branch": branch,
        "entries": entries,
        "hunks": hunks,
        "stats": {
            "files": len({str(entry["path"]) for entry in entries}),
            "hunks": len(hunks),
            "additions": additions,
            "deletions": deletions,
        },
        "fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def snapshot_command(args: argparse.Namespace) -> int:
    repo = repository_root()
    snapshot = collect_snapshot(repo)
    default_output = not args.output
    if args.output:
        output = Path(args.output).resolve()
    else:
        git_path = run_git(
            repo,
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            "explain-diff",
        ).decode().strip()
        output = Path(git_path) / str(snapshot["fingerprint"]) / "snapshot.json"
    payload = serialize_json(snapshot, indent=2) + "\n"
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    except PermissionError:
        if not default_output:
            raise
        repository_key = hashlib.sha256(str(repo).encode("utf-8")).hexdigest()[:12]
        output = (
            Path(tempfile.gettempdir())
            / "explain-diff"
            / repository_key
            / str(snapshot["fingerprint"])
            / "snapshot.json"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
        print(f"warning: Git path is not writable; using {output.parent}", file=sys.stderr)
    print(output)
    return 0


def require_text(group: dict[str, object], field: str) -> str:
    value = group.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"group {group.get('id', '<unknown>')}: {field} must be non-empty text")
    return value


def validate_manifest(snapshot: dict[str, object], manifest: dict[str, object]) -> list[dict[str, object]]:
    if manifest.get("version") != 2:
        raise ValueError("manifest version must be 2")
    for field in ("title", "context", "outcome"):
        value = manifest.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"manifest {field} must be non-empty text")
    groups = manifest.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("manifest groups must be a non-empty list")

    expected = {hunk["id"] for hunk in snapshot.get("hunks", [])}
    assigned: list[str] = []
    validated: list[dict[str, object]] = []
    seen_group_ids: set[str] = set()
    for raw_group in groups:
        if not isinstance(raw_group, dict):
            raise ValueError("each group must be an object")
        group = dict(raw_group)
        group_id = require_text(group, "id")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", group_id):
            raise ValueError(f"group id must be dash-case: {group_id}")
        if group_id in seen_group_ids:
            raise ValueError(f"duplicate group id: {group_id}")
        seen_group_ids.add(group_id)
        for field in ("title", "before", "after", "why", "review_focus"):
            require_text(group, field)
        hunk_ids = group.get("hunk_ids")
        if not isinstance(hunk_ids, list) or not hunk_ids:
            raise ValueError(f"group {group_id}: hunk_ids must be a non-empty list")
        elif not all(isinstance(item, str) for item in hunk_ids):
            raise ValueError(f"group {group_id}: hunk_ids must contain text ids")
        else:
            assigned.extend(hunk_ids)
        validated.append(group)

    unknown = sorted(set(assigned) - expected)
    if unknown:
        raise ValueError(f"unknown hunk ids: {', '.join(unknown)}")
    duplicates = sorted({item for item in assigned if assigned.count(item) > 1})
    if duplicates:
        raise ValueError(f"duplicate hunk assignments: {', '.join(duplicates)}")
    unassigned = sorted(expected - set(assigned))
    if unassigned:
        raise ValueError(f"unassigned hunks: {', '.join(unassigned)}")
    return validated


def validate_glossary(manifest: dict[str, object]) -> list[dict[str, object]]:
    raw_glossary = manifest.get("glossary", [])
    if not isinstance(raw_glossary, list):
        raise ValueError("manifest glossary must be a list")
    seen_ids: set[str] = set()
    validated: list[dict[str, object]] = []
    for raw_entry in raw_glossary:
        if not isinstance(raw_entry, dict):
            raise ValueError("each glossary entry must be an object")
        entry = dict(raw_entry)
        entry_id = require_text(entry, "id")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", entry_id):
            raise ValueError(f"glossary id must be dash-case: {entry_id}")
        if entry_id in seen_ids:
            raise ValueError(f"duplicate glossary id: {entry_id}")
        seen_ids.add(entry_id)
        require_text(entry, "term")
        require_text(entry, "definition")
        validated.append(entry)
    return validated


def validate_diagrams(
    snapshot: dict[str, object],
    manifest: dict[str, object],
    groups: list[dict[str, object]],
    glossary: list[dict[str, object]],
) -> list[dict[str, object]]:
    raw_diagrams = manifest.get("diagrams", [])
    if not isinstance(raw_diagrams, list):
        raise ValueError("manifest diagrams must be a list")
    group_hunks = {
        str(group["id"]): set(group["hunk_ids"])
        for group in groups
    }
    hunk_paths = {
        str(hunk["id"]): str(hunk["path"])
        for hunk in snapshot.get("hunks", [])
    }
    glossary_ids = {str(entry["id"]) for entry in glossary}
    diagram_ids: set[str] = set()
    validated: list[dict[str, object]] = []
    for raw_diagram in raw_diagrams:
        if not isinstance(raw_diagram, dict):
            raise ValueError("each diagram must be an object")
        diagram = dict(raw_diagram)
        diagram_id = require_text(diagram, "id")
        if diagram_id in diagram_ids:
            raise ValueError(f"duplicate diagram id: {diagram_id}")
        diagram_ids.add(diagram_id)
        for field in ("title", "description"):
            require_text(diagram, field)
        if diagram.get("format") != "mermaid":
            raise ValueError(f"diagram {diagram_id}: format must be mermaid")
        if diagram.get("format") == "mermaid":
            source = require_text(diagram, "source")
            diagram_kind = diagram.get("diagram_kind")
            prefixes = {
                "flowchart": ("flowchart ", "graph "),
                "stateDiagram-v2": ("stateDiagram-v2",),
                "sequenceDiagram": ("sequenceDiagram",),
            }
            if diagram_kind not in prefixes:
                raise ValueError(f"diagram {diagram_id}: unsupported mermaid diagram_kind")
            if not source.lstrip().startswith(prefixes[str(diagram_kind)]):
                raise ValueError(f"diagram {diagram_id}: source does not match diagram_kind")
            node_links = diagram.get("node_links", [])
            if not isinstance(node_links, list):
                raise ValueError(f"diagram {diagram_id}: node_links must be a list")
            if node_links and diagram_kind != "flowchart":
                raise ValueError(
                    f"diagram {diagram_id}: node_links are supported only for flowchart"
                )
            for link in node_links:
                if not isinstance(link, dict):
                    raise ValueError(f"diagram {diagram_id}: node link must be an object")
                require_text(link, "node_id")
                group_ids = link.get("group_ids", [])
                hunk_ids = link.get("hunk_ids", [])
                term_ids = link.get("term_ids", [])
                if not all(isinstance(value, str) for values in (group_ids, hunk_ids, term_ids) for value in values):
                    raise ValueError(f"diagram {diagram_id}: node link ids must be text")
                if set(group_ids) - set(group_hunks):
                    raise ValueError(f"diagram {diagram_id}: node link has unknown group id")
                if set(hunk_ids) - set(hunk_paths):
                    raise ValueError(f"diagram {diagram_id}: node link has unknown hunk id")
                linked_group_hunks = set().union(
                    *(group_hunks[group_id] for group_id in group_ids)
                ) if group_ids else set()
                if group_ids and set(hunk_ids) - linked_group_hunks:
                    raise ValueError(
                        f"diagram {diagram_id}: node link hunk does not belong to linked group"
                    )
                if set(term_ids) - glossary_ids:
                    raise ValueError(f"diagram {diagram_id}: node link has unknown glossary term")
            validated.append(diagram)
            continue
    return validated


def render_command(args: argparse.Namespace) -> int:
    snapshot_path = Path(args.snapshot).resolve()
    manifest_path = Path(args.manifest).resolve()
    output = Path(args.output).resolve()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    repository = snapshot.get("repository")
    fingerprint = snapshot.get("fingerprint")
    if not isinstance(repository, str) or not isinstance(fingerprint, str):
        raise ValueError("snapshot repository or fingerprint is missing")
    repository_path = Path(repository).resolve()
    git_dir = Path(
        run_git(
            repository_path,
            "rev-parse",
            "--path-format=absolute",
            "--git-dir",
        ).decode().strip()
    ).resolve()
    if output.is_relative_to(repository_path) and not output.is_relative_to(git_dir):
        relative_output = output.relative_to(repository_path)
        ignored = subprocess.run(
            ["git", "-C", str(repository_path), "check-ignore", "--quiet", "--", str(relative_output)],
            check=False,
        )
        if ignored.returncode != 0:
            raise ValueError("output inside repository must be ignored")
    try:
        current_fingerprint = collect_snapshot(repository_path)["fingerprint"]
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError(f"stale snapshot: cannot reproduce current local diff ({error})") from error
    if current_fingerprint != fingerprint:
        raise ValueError(f"stale snapshot: expected {fingerprint}, current {current_fingerprint}")
    groups = validate_manifest(snapshot, manifest)
    glossary = validate_glossary(manifest)
    diagrams = validate_diagrams(snapshot, manifest, groups, glossary)
    report_data = {
        "snapshot": snapshot,
        "manifest": {**manifest, "groups": groups, "diagrams": diagrams, "glossary": glossary},
    }
    encoded = base64.b64encode(
        json.dumps(report_data, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    html = TEMPLATE.read_text(encoding="utf-8")
    missing_frontend_dependencies = [
        path for path in (MERMAID_BUNDLE, *PRISM_BUNDLES) if not path.is_file()
    ]
    if missing_frontend_dependencies:
        raise RuntimeError(
            "Frontend dependencies are missing; run "
            f"`npm ci --ignore-scripts --prefix {SKILL_DIR}`"
        )
    mermaid_source = MERMAID_BUNDLE.read_text(encoding="utf-8").replace("</script", "<\\/script")
    prism_source = "\n".join(
        path.read_text(encoding="utf-8") for path in PRISM_BUNDLES
    ).replace("</script", "<\\/script")
    html = html.replace("__MERMAID_JS__", mermaid_source)
    html = html.replace("__PRISM_JS__", prism_source)
    html = html.replace("__REPORT_FINGERPRINT__", fingerprint)
    html = html.replace("__REPORT_DATA_BASE64__", encoded)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(output)
    if not args.no_open:
        opener = shutil.which("open") or shutil.which("xdg-open")
        if opener:
            subprocess.Popen(
                [opener, str(output)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        else:
            print(f"warning: browser opener not found; open {output}", file=sys.stderr)
    return 0


def verify_command(args: argparse.Namespace) -> int:
    repo = repository_root()
    current = collect_snapshot(repo)["fingerprint"]
    if current != args.fingerprint:
        raise ValueError(f"stale fingerprint: expected {args.fingerprint}, current {current}")
    print(current)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot = subparsers.add_parser("snapshot", help="local差分のsnapshotを作成する")
    snapshot.add_argument("--output")
    snapshot.set_defaults(handler=snapshot_command)
    render = subparsers.add_parser("render", help="manifestを検証してHTMLを生成する")
    render.add_argument("--snapshot", required=True)
    render.add_argument("--manifest", required=True)
    render.add_argument("--output", required=True)
    render.add_argument("--no-open", action="store_true")
    render.set_defaults(handler=render_command)
    verify = subparsers.add_parser("verify", help="現在のlocal差分とfingerprintを照合する")
    verify.add_argument("--fingerprint", required=True)
    verify.set_defaults(handler=verify_command)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.handler(args)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
