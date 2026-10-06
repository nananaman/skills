#!/usr/bin/env python3
"""Build a skills-only plugin from tracked canonical skills, without installing it."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile


SPEC = importlib.util.spec_from_file_location('inventory', Path(__file__).with_name('check-skill-inventory.py'))
assert SPEC and SPEC.loader
INVENTORY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = INVENTORY
SPEC.loader.exec_module(INVENTORY)
LINK = re.compile(r'(\[[^\]]*\]\()([^)]+)(\))')


def tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'], check=True, capture_output=True)
    return sorted(root / os.fsdecode(path) for path in result.stdout.split(b'\0') if path)


def regular_file(root: Path, path: Path) -> None:
    for part in [path, *path.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise ValueError(f'symlink is not packageable: {path.relative_to(root)}')
    if not path.is_file():
        raise ValueError(f'tracked file missing: {path.relative_to(root)}')


def package(root: Path, output: Path) -> dict:
    root, output = root.resolve(), output.resolve()
    if output.exists():
        raise ValueError('output already exists; choose a fresh directory')
    if output == root or root.is_relative_to(output):
        raise ValueError('output must not contain the source repository')
    if output.is_relative_to(root) and not output.is_relative_to(root / '_build'):
        raise ValueError('output inside the repository must be under _build/')

    tracked = tracked_files(root)
    sources = [path for path in tracked if path.name == 'SKILL.md'
               and not any(part in INVENTORY.IGNORED_ROOTS for part in path.relative_to(root).parts)]
    untracked = set(INVENTORY.skill_paths(root)) - set(sources)
    if untracked:
        raise ValueError('untracked SKILL.md: ' + ', '.join(str(p.relative_to(root)) for p in sorted(untracked)))
    if not sources:
        raise ValueError('no tracked skills')

    mapping: dict[Path, Path] = {}
    skills = []
    names = set()
    for source in sources:
        files = [path for path in tracked if path.is_relative_to(source.parent)]
        for path in files:
            regular_file(root, path)
        metadata, findings = INVENTORY.parse_frontmatter(source)
        if findings:
            raise ValueError(f'invalid skill metadata: {source.relative_to(root)}')
        name = metadata['name']
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name) or name in names:
            raise ValueError(f'invalid or duplicate skill name: {name}')
        names.add(name)
        destination = Path('skills') / name
        skills.append({'name': name, 'source': source.relative_to(root).as_posix(),
                       'package': (destination / 'SKILL.md').as_posix()})
        for path in files:
            mapping[path] = destination / path.relative_to(source.parent)

    for filename in ('plugin.json', 'README.md'):
        source = root / 'plugin' / filename
        if source not in tracked:
            raise ValueError(f'package metadata must be tracked: plugin/{filename}')
        regular_file(root, source)
        mapping[source] = Path(filename)
    manifest = json.loads((root / 'plugin/plugin.json').read_text(encoding='utf-8'))
    name, version = manifest['name'], manifest['version']
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('invalid package name or version')

    def rewrite_links(source: Path, destination: Path, content: str) -> str:
        def replace(match):
            target, separator, fragment = match[2].partition('#')
            if not target or re.match(r'[a-zA-Z][a-zA-Z0-9+.-]*:', target):
                return match[0]
            resolved = (source.parent / target).resolve()
            if resolved in mapping:
                mapped = mapping[resolved]
            else:
                children = [p for p in mapping if p.is_relative_to(resolved)]
                if not children or not resolved.is_dir():
                    raise ValueError(f'unbundled link in {source.relative_to(root)}: {target}')
                child = children[0]
                mapped = mapping[child]
                for _ in child.relative_to(resolved).parts:
                    mapped = mapped.parent
            relative = Path(os.path.relpath(mapped, destination.parent)).as_posix()
            if target.endswith('/'):
                relative += '/'
            return match[1] + relative + separator + fragment + match[3]
        return LINK.sub(replace, content)

    # Validate and prepare everything before creating any output.
    contents = {}
    for source, destination in mapping.items():
        data = source.read_bytes()
        if source.suffix == '.md':
            data = rewrite_links(source, destination, data.decode('utf-8')).encode('utf-8')
        contents[destination] = (data, source.stat().st_mode & 0o777)
    record = {'skills': skills, 'files': {p.as_posix(): hashlib.sha256(data).hexdigest()
                                       for p, (data, _) in sorted(contents.items())}}
    contents[Path('inventory.json')] = ((json.dumps(record, ensure_ascii=False, indent=2) + '\n').encode(), 0o644)
    plugin = output / name
    plugin.mkdir(parents=True)
    for destination, (data, mode) in contents.items():
        target = plugin / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(mode)

    marketplace = output / '.agents/plugins/marketplace.json'
    marketplace.parent.mkdir(parents=True)
    marketplace.write_text(json.dumps({
        'name': 'nananaman-skills-local',
        'interface': {'displayName': 'nananaman skills (local build)'},
        'plugins': [{'name': name, 'source': {'source': 'local', 'path': './' + name},
                     'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'},
                     'category': 'Productivity'}],
    }, indent=2) + '\n', encoding='utf-8')
    archive = output / f'{name}-{version}.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
        for path, (data, mode) in sorted(contents.items()):
            entry = zipfile.ZipInfo((Path(name) / path).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (0o100000 | mode) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            zipped.writestr(entry, data)
    return {'plugin': str(plugin), 'zip': str(archive), 'skills': len(skills),
            'files': len(contents), 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--output', type=Path, help='fresh directory; default: <root>/_build/plugins')
    args = parser.parse_args()
    try:
        result = package(args.root, args.output or args.root / '_build/plugins')
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print(f'build-plugin: {error}', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
