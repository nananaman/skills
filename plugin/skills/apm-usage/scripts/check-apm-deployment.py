#!/usr/bin/env python3
"""APM manifest / lock / commit / Codex・Claude 展開を読み取り専用で照合する。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys

import yaml


REPOSITORY = 'nananaman/skills'
TARGETS = {'agent-skills': '.agents/skills', 'claude': '.claude/skills'}


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(['git', '--no-lazy-fetch', '--no-optional-locks', '-C', str(repo), *args], stderr=subprocess.DEVNULL)


def digest(content: bytes) -> str:
    return 'sha256:' + hashlib.sha256(content).hexdigest()


def file_hashes(content: bytes) -> tuple[str, str]:
    # APM 0.29 の per-file hash: UTF-8 text の CRLF のみ LF にする。
    canonical = content
    if b'\x00' not in content:
        try:
            content.decode('utf-8')
            canonical = content.replace(b'\r\n', b'\n')
        except UnicodeDecodeError:
            pass
    return digest(content), digest(canonical)


def scan_error(error: OSError) -> None:
    raise error


def snapshot(path: Path, *, cache: bool = False) -> dict[str, tuple[str, str]]:
    if path.is_symlink():
        raise ValueError('skill directory symlink is not inspected')
    if not path.is_dir():
        raise ValueError('skill directory missing')
    result = {}
    for directory, subdirs, files in os.walk(path, onerror=scan_error, followlinks=False):
        subdirs[:] = sorted(d for d in subdirs if d != '__pycache__')
        for name in sorted(subdirs + files):
            item = Path(directory) / name
            if item.is_symlink():
                raise ValueError('symlink inside skill is not inspected')
            relative = item.relative_to(path).as_posix()
            if item.suffix == '.pyc' or (cache and relative == '.apm-pin'):
                continue
            if item.is_file():
                result[relative] = file_hashes(item.read_bytes())
            elif not item.is_dir():
                raise ValueError('non-regular entry is not inspected')
    if 'SKILL.md' not in result:
        raise ValueError('SKILL.md missing')
    return result


def commit_snapshot(repo: Path, commit: str, relative: str) -> dict[str, tuple[str, str]]:
    result = {}
    for record in git(repo, 'ls-tree', '-rz', commit, '--', relative).split(b'\0'):
        if not record:
            continue
        metadata, name = record.split(b'\t', 1)
        mode, kind, oid = metadata.split()
        if kind != b'blob' or mode == b'120000':
            raise ValueError('non-regular Git entry is not inspected')
        result[name.decode()[len(relative) + 1:]] = file_hashes(git(repo, 'cat-file', 'blob', oid.decode()))
    if 'SKILL.md' not in result:
        raise ValueError('skill missing at target commit')
    return result


def differences(expected: dict, actual: dict) -> list[str]:
    return sorted(k for k in expected.keys() | actual.keys() if expected.get(k) != actual.get(k))


def load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('YAML mapping required')
    return value


def expand_path(value: str, base: Path, home: Path) -> Path:
    if value.startswith('~/'):
        path = home / value[2:]
    else:
        path = Path(value)
    return path if path.is_absolute() else base / path


def inspected(path: Path, findings: list, code: str, *, cache: bool = False) -> dict | None:
    try:
        return snapshot(path, cache=cache)
    except (OSError, ValueError) as error:
        findings.append({'code': code, 'reason': type(error).__name__})
        return None


def local_relative(source: Path, repo: Path, common: bytes) -> str | None:
    try:
        return source.relative_to(repo).as_posix()
    except ValueError:
        try:
            if git(source, 'rev-parse', '--path-format=absolute', '--git-common-dir').strip() != common:
                return None
            checkout = Path(git(source, 'rev-parse', '--show-toplevel').decode().strip())
            return source.relative_to(checkout).as_posix()
        except (OSError, subprocess.CalledProcessError, ValueError):
            return None


def audit(args: argparse.Namespace) -> dict:
    repo = args.source_repo.resolve()
    home = args.home.resolve()
    scope_root = home if args.scope == 'global' else args.root.resolve()
    state_root = home / '.apm' if args.scope == 'global' else scope_root
    manifest_path = state_root / 'apm.yml'
    manifest = load_yaml(manifest_path)
    lock = load_yaml(state_root / 'apm.lock.yaml')
    if str(lock.get('lockfile_version')) != '1':
        raise ValueError('unsupported lockfile version')
    manifest_dependencies = manifest.get('dependencies', {})
    if not isinstance(manifest_dependencies, dict):
        raise ValueError('manifest dependencies mapping required')
    dependencies = manifest_dependencies.get('apm', [])
    locked_dependencies = lock.get('dependencies', [])
    if not isinstance(dependencies, list) or not isinstance(locked_dependencies, list):
        raise ValueError('dependency list required')
    if not all(isinstance(d, dict) for d in locked_dependencies):
        raise ValueError('lock dependency mapping required')
    commit = git(repo, 'rev-parse', '--verify', '--end-of-options', args.commit + '^{commit}').decode().strip()
    targets = manifest.get('targets', manifest.get('target', []))
    if isinstance(targets, str):
        targets = [s.strip() for s in targets.split(',')]
    if not isinstance(targets, list):
        raise ValueError('target list required')
    report = {'scope': args.scope, 'scope_root': str(scope_root), 'manifest': str(manifest_path),
              'manifest_realpath': str(manifest_path.resolve()), 'lock': str(state_root / 'apm.lock.yaml'),
              'source_repo': str(repo),
              'target_commit': commit, 'findings': [], 'skills': []}
    if args.expected_manifest and args.expected_manifest.resolve() != manifest_path.resolve():
        report['findings'].append({'code': 'manifest-location-mismatch',
                                   'expected': str(args.expected_manifest.resolve())})
    common = git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir').strip()
    matched_entries = set()
    names = set()
    for dependency in dependencies:
        pin = None
        if isinstance(dependency, dict) and isinstance(dependency.get('path'), str):
            source_path = expand_path(dependency['path'], state_root, home)
            source = source_path.resolve()
            relative = local_relative(source, repo, common)
            if relative is None:
                continue
            matches = [i for i, d in enumerate(locked_dependencies)
                       if isinstance(d.get('local_path'), str)
                       and expand_path(d['local_path'], state_root, home).resolve() == source]
        elif isinstance(dependency, str) and dependency.startswith(REPOSITORY + '/'):
            reference, separator, pin = dependency.partition('#')
            relative = reference[len(REPOSITORY) + 1:]
            if not separator or not re.fullmatch(r'[0-9a-f]{40}', pin):
                report['findings'].append({'code': 'unsupported-managed-reference'})
                continue
            source = state_root / 'apm_modules' / REPOSITORY / relative
            source_path = source
            matches = [i for i, d in enumerate(locked_dependencies)
                       if d.get('repo_url') == REPOSITORY and d.get('virtual_path') == relative]
        else:
            continue
        if not re.fullmatch(r'plugin/skills/[a-z0-9-]+', relative):
            report['findings'].append({'code': 'unsupported-managed-path'})
            continue
        name = Path(relative).name
        row = {'name': name, 'source': str(source_path), 'manifest_commit': pin,
               'lock_commit': None, 'findings': [], 'targets': {}}
        report['skills'].append(row)
        if name in names:
            row['findings'].append({'code': 'duplicate-skill-name'})
        names.add(name)
        if not pin and source != repo / relative:
            row['findings'].append({'code': 'source-checkout-mismatch'})
        if pin and pin != commit:
            row['findings'].append({'code': 'manifest-commit-mismatch'})
        if len(matches) != 1:
            row['findings'].append({'code': 'lock-entry-missing-or-duplicate'})
        matched_entries.update(matches)
        entry = locked_dependencies[matches[0]] if len(matches) == 1 else {}
        row['lock_commit'] = entry.get('resolved_commit')
        if pin and row['lock_commit'] != pin:
            row['findings'].append({'code': 'lock-commit-mismatch'})
        try:
            expected = commit_snapshot(repo, commit, relative)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            row['findings'].append({'code': 'target-commit-unverified', 'reason': type(error).__name__})
            row['status'] = 'unverified'
            continue
        source_content = inspected(source_path, row['findings'], 'source-unverified', cache=bool(pin))
        if source_content is not None and (changes := differences(expected, source_content)):
            row['findings'].append({'code': 'source-content-mismatch', 'files': changes})
        deployed = entry.get('deployed_files', [])
        lock_hashes = entry.get('deployed_file_hashes', {})
        if (not isinstance(deployed, list) or not all(isinstance(p, str) for p in deployed)
                or not isinstance(lock_hashes, dict)
                or not all(isinstance(p, str) and isinstance(h, str) for p, h in lock_hashes.items())):
            raise ValueError('invalid deployment records')
        for target, prefix in TARGETS.items():
            if target not in targets:
                row['findings'].append({'code': 'target-not-configured', 'target': target})
            skill_prefix = prefix + '/' + name
            if skill_prefix not in deployed:
                row['findings'].append({'code': 'lock-target-missing', 'target': target})
            target_findings = []
            destination = scope_root / skill_prefix
            actual = inspected(destination, target_findings, 'deployment-unverified')
            for finding in target_findings:
                row['findings'].append({**finding, 'target': target})
            changes = differences(expected, actual) if actual is not None else []
            row['targets'][target] = {'path': str(destination),
                                      'status': 'unverified' if actual is None else 'mismatch' if changes else 'match',
                                      'files': changes}
            if changes:
                row['findings'].append({'code': 'deployment-content-mismatch', 'target': target})
            locked = {p[len(skill_prefix) + 1:]: h for p, h in lock_hashes.items()
                      if p.startswith(skill_prefix + '/')}
            directories = {parent.as_posix() for f in expected for parent in Path(f).parents if str(parent) != '.'}
            recorded = {p[len(skill_prefix) + 1:] for p in deployed if p.startswith(skill_prefix + '/')} - directories
            if changes := sorted(recorded ^ expected.keys()):
                row['findings'].append({'code': 'lock-files-mismatch', 'target': target, 'files': changes})
            if not locked:
                row['findings'].append({'code': 'lock-content-unverified', 'target': target})
            elif changes := differences({p: h[1] for p, h in expected.items()}, locked):
                row['findings'].append({'code': 'lock-content-mismatch', 'target': target, 'files': changes})
        row['status'] = 'mismatch' if row['findings'] else 'match'
    for i, entry in enumerate(locked_dependencies):
        local = entry.get('local_path')
        relative = local_relative(expand_path(local, state_root, home).resolve(), repo, common) if isinstance(local, str) else None
        managed_local = relative is not None and re.fullmatch(r'plugin/skills/[a-z0-9-]+', relative)
        if i not in matched_entries and (entry.get('repo_url') == REPOSITORY or managed_local):
            report['findings'].append({'code': 'orphan-lock-entry', 'name': entry.get('name', entry.get('repo_url'))})
    if not report['skills']:
        report['findings'].append({'code': 'no-managed-skills'})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=['global', 'project'], required=True)
    parser.add_argument('--root', type=Path, default=Path.cwd(), help='project scope root')
    parser.add_argument('--home', type=Path, default=Path.home(), help='global user home')
    parser.add_argument('--source-repo', type=Path, required=True)
    parser.add_argument('--expected-manifest', type=Path, help='実際に読まれるべき manifest の実体')
    parser.add_argument('--commit', default='HEAD', help='照合する正本 commit（既定 HEAD）')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        report = audit(args)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError, yaml.YAMLError) as error:
        print(json.dumps({'error': type(error).__name__, 'status': 'unverified',
                          'reason': str(error) if type(error) is ValueError else
                          'manifest / lock / source repo / local commit を読み取れません'}, ensure_ascii=False))
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"scope: {report['scope']}  manifest: {report['manifest_realpath']}")
        print(f"target commit: {report['target_commit']}")
        for row in report['skills']:
            print(f"{row['name']}: {row['status']}")
            for finding in row['findings']:
                print('  ' + json.dumps(finding, ensure_ascii=False))
        for finding in report['findings']:
            print(json.dumps(finding, ensure_ascii=False))
    return int(bool(report['findings'] or any(s['findings'] for s in report['skills'])))


if __name__ == '__main__':
    sys.exit(main())
