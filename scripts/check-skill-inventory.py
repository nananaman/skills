#!/usr/bin/env python3
"""Deterministic inventory checks for this Agent Skills repository."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
import re
import sys


FRONTMATTER_BOUNDARY = "---"
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
MARKDOWN_HEADING = re.compile(r"^\s{0,3}#{1,6}(?:[ \t]+|$)(.*)$")
MARKDOWN_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
IGNORED_ROOTS = {".agents", ".claude", ".git", "apm_modules", "node_modules"}
EXCLUDED_PROMPT_MARKDOWN = {"README.md", "NOTICE.md"}
ENGLISH_CONTROL_HEADINGS = {
    "workflow",
    "completion",
    "safety",
    "output",
    "contract",
    "lifecycle",
    "context discovery",
    "branch router",
    "change rules",
    "failure handling",
    "when to use",
    "when not to use",
    "prerequisites",
    "progress",
    "authority boundary",
}


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    message: str


def parse_frontmatter(path: Path) -> tuple[dict[str, str], list[Finding]]:
    findings: list[Finding] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    relative = path.as_posix()
    if not lines or lines[0].strip() != FRONTMATTER_BOUNDARY:
        return {}, [Finding("frontmatter-missing", relative, "先頭に YAML frontmatter がありません")]

    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == FRONTMATTER_BOUNDARY)
    except StopIteration:
        return {}, [Finding("frontmatter-unclosed", relative, "YAML frontmatter が閉じられていません")]

    metadata: dict[str, str] = {}
    for line_number, line in enumerate(lines[1:end], start=2):
        if not line.strip() or line.startswith((" ", "\t")):
            continue
        if ":" not in line:
            findings.append(Finding("frontmatter-invalid-line", relative, f"{line_number} 行目を解釈できません"))
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip("\"'")

    for required in ("name", "description"):
        if not metadata.get(required):
            findings.append(Finding("frontmatter-required", relative, f"frontmatter に {required}: が必要です"))
    return metadata, findings


def skill_paths(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("SKILL.md")
        if not any(part in IGNORED_ROOTS for part in path.relative_to(root).parts)
    )


def validate_name(root: Path, path: Path, name: str) -> Finding | None:
    relative = path.relative_to(root)
    leaf = path.parent.name
    category = relative.parts[0]
    allowed = {leaf, f"{category}-{leaf}"}
    if name not in allowed:
        return Finding(
            "name-directory-mismatch",
            relative.as_posix(),
            f"name: {name!r} は directory 名に対応しません（許可値: {sorted(allowed)}）",
        )
    return None


def validate_readme_coverage(root: Path, path: Path) -> list[Finding]:
    relative = path.relative_to(root)
    category = relative.parts[0]
    skill_directory = path.parent.name
    checks = (
        (root / "README.md", f"./{relative.as_posix()}"),
        (root / category / "README.md", f"./{skill_directory}/SKILL.md"),
    )
    findings: list[Finding] = []
    for readme, expected in checks:
        if not readme.is_file():
            findings.append(Finding("readme-missing", readme.relative_to(root).as_posix(), "README.md がありません"))
            continue
        if expected not in readme.read_text(encoding="utf-8"):
            findings.append(
                Finding(
                    "readme-skill-missing",
                    readme.relative_to(root).as_posix(),
                    f"{expected} への skill 導線がありません",
                )
            )
    return findings


def validate_links(root: Path, path: Path) -> list[Finding]:
    findings: list[Finding] = []
    text = path.read_text(encoding="utf-8")
    for target in MARKDOWN_LINK.findall(text):
        target = target.strip().split("#", 1)[0]
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            findings.append(Finding("link-outside-repository", path.relative_to(root).as_posix(), target))
            continue
        if not resolved.exists():
            findings.append(Finding("link-missing", path.relative_to(root).as_posix(), target))
    return findings


def prompt_markdown_paths(skill_files: list[Path]) -> list[Path]:
    return sorted(
        {
            markdown
            for skill in skill_files
            for markdown in skill.parent.rglob("*.md")
            if markdown.name not in EXCLUDED_PROMPT_MARKDOWN
            and not any(part in IGNORED_ROOTS for part in markdown.relative_to(skill.parent).parts)
        }
    )


def validate_japanese_control_headings(root: Path, path: Path) -> list[Finding]:
    findings: list[Finding] = []
    active_fence: tuple[str, int] | None = None
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        fence = MARKDOWN_FENCE.match(line)
        if active_fence is not None:
            if (
                fence
                and fence.group(1)[0] == active_fence[0]
                and len(fence.group(1)) >= active_fence[1]
                and not line[fence.end() :].strip()
            ):
                active_fence = None
            continue
        if fence and not (fence.group(1)[0] == "`" and "`" in line[fence.end() :]):
            active_fence = (fence.group(1)[0], len(fence.group(1)))
            continue
        heading = MARKDOWN_HEADING.match(line)
        heading_text = re.sub(r"[ \t]+#+[ \t]*$", "", heading.group(1)).strip() if heading else ""
        if heading and heading_text.casefold() in ENGLISH_CONTROL_HEADINGS:
            findings.append(
                Finding(
                    "english-control-heading",
                    path.relative_to(root).as_posix(),
                    f"{line_number} 行目の制御見出しを日本語で書いてください: {heading_text}",
                )
            )
    return findings


def check(root: Path) -> tuple[list[Path], list[Finding]]:
    root = root.resolve()
    skills = skill_paths(root)
    findings: list[Finding] = []
    names: dict[str, Path] = {}

    for path in skills:
        metadata, metadata_findings = parse_frontmatter(path)
        findings.extend(
            Finding(item.code, path.relative_to(root).as_posix(), item.message)
            for item in metadata_findings
        )
        name = metadata.get("name")
        if name:
            mismatch = validate_name(root, path, name)
            if mismatch:
                findings.append(mismatch)
            if name in names:
                findings.append(
                    Finding(
                        "name-duplicate",
                        path.relative_to(root).as_posix(),
                        f"name: {name!r} は {names[name].relative_to(root).as_posix()} と重複しています",
                    )
                )
            else:
                names[name] = path
        findings.extend(validate_readme_coverage(root, path))

    markdown_files = [root / "README.md"]
    markdown_files.extend(root.glob("*/README.md"))
    markdown_files.extend(skills)
    for path in sorted(set(markdown_files)):
        if path.is_file():
            findings.extend(validate_links(root, path))

    for path in prompt_markdown_paths(skills):
        findings.extend(validate_japanese_control_headings(root, path))

    return skills, sorted(findings, key=lambda item: (item.path, item.code, item.message))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--json", action="store_true", help="結果を JSON で出力する")
    args = parser.parse_args()

    skills, findings = check(args.root)
    if args.json:
        print(json.dumps({"skills": len(skills), "findings": [asdict(item) for item in findings]}, ensure_ascii=False, indent=2))
    else:
        print(f"skills: {len(skills)}")
        if findings:
            for item in findings:
                print(f"{item.path}: [{item.code}] {item.message}")
        else:
            print("findings: 0")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
