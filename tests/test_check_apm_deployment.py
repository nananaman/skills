from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import unittest

import yaml


SCRIPT = Path(__file__).resolve().parent.parent / 'plugin/skills/apm-usage/scripts/check-apm-deployment.py'


class ApmDeploymentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / 'source'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'core.autocrlf', 'false')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'core.hooksPath', '/dev/null')
        self.skill = self.repo / 'plugin/skills/example'
        self.skill.mkdir(parents=True)
        (self.skill / 'SKILL.md').write_text('---\nname: example\ndescription: test\n---\nCurrent\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')
        self.commit = self.git('rev-parse', 'HEAD').strip()
        self.home = self.root / 'home'
        self.apm = self.home / '.apm'
        self.apm.mkdir(parents=True)
        self.manifest = {'target': 'claude,agent-skills', 'dependencies': {'apm': [{'path': str(self.skill)}]}}
        self.lock = {'lockfile_version': '1', 'dependencies': [{
            'repo_url': '_local/example', 'source': 'local', 'local_path': str(self.skill),
            'package_type': 'claude_skill', 'deployed_files': [f'{target}/skills/example{suffix}' for target in ('.agents', '.claude')
                               for suffix in ('', '/SKILL.md')],
        }]}
        self.lock['dependencies'][0]['deployed_file_hashes'] = {
            f'{target}/skills/example/SKILL.md': 'sha256:' + hashlib.sha256((self.skill / 'SKILL.md').read_bytes()).hexdigest()
            for target in ('.agents', '.claude')}
        for target in ('.agents', '.claude'):
            shutil.copytree(self.skill, self.home / target / 'skills/example')

    def git(self, *args: str) -> str:
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True)

    def audit(self, *args: str, script: Path = SCRIPT) -> tuple[int, dict]:
        for path, value in ((self.apm / 'apm.yml', self.manifest), (self.apm / 'apm.lock.yaml', self.lock)):
            content = yaml.safe_dump(value)
            if not path.exists() or path.read_text() != content:
                path.write_text(content)
        result = subprocess.run(
            [sys.executable, str(script), '--scope', 'global', '--home', str(self.home),
             '--source-repo', str(self.repo), '--json', *args], capture_output=True, text=True,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
        )
        return result.returncode, json.loads(result.stdout)

    def test_unchanged_deployments_match_without_writing_inputs(self) -> None:
        # lock のハッシュがある場合は target commit・lock・実体がすべて一致する。
        self.audit()
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}

        code, report = self.audit()

        self.assertEqual(0, code, report)
        self.assertEqual('match', report['skills'][0]['status'])
        self.assertEqual(self.commit, report['target_commit'])
        after = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def codes(self, report: dict) -> set[str]:
        return {f['code'] for f in report['findings']} | {
            f['code'] for row in report['skills'] for f in row['findings']}

    def test_old_deployments_report_both_targets_and_stale_lock(self) -> None:
        (self.skill / 'SKILL.md').write_text('New version\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'new version')

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertIn('lock-content-mismatch', self.codes(report))
        self.assertEqual({'agent-skills', 'claude'}, {
            f['target'] for f in report['skills'][0]['findings'] if f['code'] == 'deployment-content-mismatch'})

    def test_update_of_only_one_target_reports_the_stale_side(self) -> None:
        (self.home / '.claude/skills/example/SKILL.md').write_text('Stale\n')

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertEqual('match', report['skills'][0]['targets']['agent-skills']['status'])
        self.assertEqual('mismatch', report['skills'][0]['targets']['claude']['status'])

    def test_a_different_worktree_is_reported_even_with_identical_contents(self) -> None:
        other = self.root / 'other-worktree'
        self.git('worktree', 'add', '--detach', '-q', str(other), 'HEAD')
        self.manifest['dependencies']['apm'][0]['path'] = str(other / 'plugin/skills/example')
        self.lock['dependencies'][0]['local_path'] = str(other / 'plugin/skills/example')

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertIn('source-checkout-mismatch', self.codes(report))
        self.assertEqual('match', report['skills'][0]['targets']['claude']['status'])

    def test_missing_one_target_does_not_hide_the_other_target_result(self) -> None:
        shutil.rmtree(self.home / '.claude/skills/example')

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertEqual('unverified', report['skills'][0]['targets']['claude']['status'])
        self.assertEqual('match', report['skills'][0]['targets']['agent-skills']['status'])

    def use_pin(self, commit: str | None = None) -> None:
        pin = commit or self.commit
        self.manifest['dependencies']['apm'] = [f'nananaman/skills/plugin/skills/example#{pin}']
        entry = self.lock['dependencies'][0]
        entry.pop('source')
        entry.pop('local_path')
        entry.update(repo_url='nananaman/skills', virtual_path='plugin/skills/example', resolved_commit=pin)
        cache = self.apm / 'apm_modules/nananaman/skills/plugin/skills/example'
        shutil.copytree(self.skill, cache)
        (cache / '.apm-pin').write_text(pin)

    def test_full_sha_pin_is_checked_against_lock_cache_and_target_commit(self) -> None:
        self.use_pin()

        code, report = self.audit()

        self.assertEqual(0, code, report)
        self.assertEqual(self.commit, report['skills'][0]['manifest_commit'])
        self.assertEqual(self.commit, report['skills'][0]['lock_commit'])

    def test_stale_sha_in_lock_is_not_hidden_by_matching_deployed_bytes(self) -> None:
        self.use_pin()
        self.lock['dependencies'][0]['resolved_commit'] = '0' * 40

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertIn('lock-commit-mismatch', self.codes(report))
        self.assertEqual('match', report['skills'][0]['targets']['claude']['status'])

    def test_old_manifest_pin_is_reported_against_the_requested_target(self) -> None:
        self.use_pin()
        (self.skill / 'SKILL.md').write_text('New version\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'new version')

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertIn('manifest-commit-mismatch', self.codes(report))

    def test_project_scope_reads_the_project_not_the_global_deployments(self) -> None:
        project = self.root / 'project'
        project.mkdir()
        self.manifest['dependencies']['apm'][0]['path'] = '../source/plugin/skills/example'
        self.lock['dependencies'][0]['local_path'] = '../source/plugin/skills/example'
        (project / 'apm.yml').write_text(yaml.safe_dump(self.manifest))
        (project / 'apm.lock.yaml').write_text(yaml.safe_dump(self.lock))
        for target in ('.agents', '.claude'):
            shutil.copytree(self.skill, project / target / 'skills/example')
        (self.home / '.claude/skills/example/SKILL.md').write_text('Different global copy\n')

        code, report = self.audit('--scope', 'project', '--root', str(project))

        self.assertEqual(0, code, report)
        self.assertEqual(str(project.resolve()), report['scope_root'])

    def test_expected_manifest_in_another_worktree_is_reported(self) -> None:
        expected = self.root / 'proposed-apm.yml'
        expected.write_text(yaml.safe_dump(self.manifest))

        code, report = self.audit('--expected-manifest', str(expected))

        self.assertEqual(1, code)
        self.assertIn('manifest-location-mismatch', self.codes(report))

    def test_lock_must_record_the_deployment_in_the_selected_scope(self) -> None:
        self.lock['dependencies'][0]['deployed_files'] = ['.claude/skills/example']

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertIn('lock-target-missing', self.codes(report))

    def test_extra_deployed_file_is_reported_without_printing_its_contents(self) -> None:
        (self.home / '.agents/skills/example/unexpected.txt').write_text('private fixture sentinel')

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertNotIn('private fixture sentinel', json.dumps(report))
        self.assertIn('unexpected.txt', report['skills'][0]['targets']['agent-skills']['files'])

    def test_short_pin_is_unverified_instead_of_using_the_network(self) -> None:
        self.manifest['dependencies']['apm'] = ['nananaman/skills/plugin/skills/example#main']

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertIn('unsupported-managed-reference', self.codes(report))

    def test_lock_without_file_hashes_is_explicitly_unverified(self) -> None:
        self.lock['dependencies'][0].pop('deployed_file_hashes')

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertIn('lock-content-unverified', self.codes(report))
        self.assertEqual('match', report['skills'][0]['targets']['claude']['status'])

    def test_a_missing_lock_entry_is_reported_even_when_both_targets_match(self) -> None:
        self.lock['dependencies'] = []

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertIn('lock-entry-missing-or-duplicate', self.codes(report))

    def test_undeclared_managed_lock_entry_is_reported(self) -> None:
        self.lock['dependencies'].append({'repo_url': 'nananaman/skills',
                                          'virtual_path': 'plugin/skills/removed', 'name': 'removed'})

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertIn('orphan-lock-entry', self.codes(report))

    def test_local_source_edits_are_distinguished_from_deployment_drift(self) -> None:
        (self.skill / 'SKILL.md').write_text('Uncommitted edit\n')

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertIn('source-content-mismatch', self.codes(report))
        self.assertEqual('match', report['skills'][0]['targets']['agent-skills']['status'])

    def test_symlink_inside_a_skill_is_not_followed(self) -> None:
        outside = self.root / 'outside.txt'
        outside.write_text('private symlink sentinel')
        (self.home / '.agents/skills/example/link').symlink_to(outside)

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertIn('deployment-unverified', self.codes(report))
        self.assertNotIn('private symlink sentinel', json.dumps(report))

    def test_invalid_lock_schema_returns_an_input_error(self) -> None:
        self.lock['dependencies'] = ['invalid entry']

        code, report = self.audit()

        self.assertEqual(2, code)
        self.assertEqual('unverified', report['status'])

    def test_target_commit_not_available_locally_returns_an_input_error(self) -> None:
        code, report = self.audit('--commit', 'f' * 40)

        self.assertEqual(2, code)
        self.assertEqual('unverified', report['status'])

    def test_invalid_manifest_dependency_schema_returns_an_input_error(self) -> None:
        self.manifest['dependencies'] = []

        code, report = self.audit()

        self.assertEqual(2, code)
        self.assertEqual('unverified', report['status'])

    def test_project_does_not_accept_an_unconfigured_target_as_fully_matching(self) -> None:
        self.manifest['target'] = 'claude'

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertIn('target-not-configured', self.codes(report))

    def test_skill_directory_symlink_is_not_followed(self) -> None:
        deployed = self.home / '.agents/skills/example'
        shutil.rmtree(deployed)
        deployed.symlink_to(self.skill, target_is_directory=True)

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertEqual('unverified', report['skills'][0]['targets']['agent-skills']['status'])

    def test_local_source_symlink_is_unverified_before_its_contents_are_read(self) -> None:
        alias = self.root / 'alias'
        alias.symlink_to(self.skill, target_is_directory=True)
        self.manifest['dependencies']['apm'][0]['path'] = str(alias)
        self.lock['dependencies'][0]['local_path'] = str(alias)

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertIn('source-unverified', self.codes(report))

    def test_orphan_lock_entry_in_another_worktree_is_reported(self) -> None:
        other = self.root / 'other-worktree'
        self.git('worktree', 'add', '--detach', '-q', str(other), 'HEAD')
        self.lock['dependencies'].append({'repo_url': '_local/example',
            'local_path': str(other / 'plugin/skills/example'), 'source': 'local'})

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertIn('orphan-lock-entry', self.codes(report))

    def test_missing_deployed_file_record_is_not_hidden_by_a_correct_hash(self) -> None:
        self.lock['dependencies'][0]['deployed_files'].remove('.agents/skills/example/SKILL.md')

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertIn('lock-files-mismatch', self.codes(report))

    def test_lock_hash_normalizes_utf8_crlf_while_content_comparison_remains_exact(self) -> None:
        content = b'---\r\nname: example\r\ndescription: test\r\n---\r\n'
        (self.skill / 'SKILL.md').write_bytes(content)
        self.git('add', '.')
        self.git('commit', '-qm', 'CRLF fixture')
        entry = self.lock['dependencies'][0]
        for target in ('.agents', '.claude'):
            (self.home / target / 'skills/example/SKILL.md').write_bytes(content)
            entry['deployed_file_hashes'][f'{target}/skills/example/SKILL.md'] = (
                'sha256:' + hashlib.sha256(content.replace(b'\r\n', b'\n')).hexdigest())

        code, report = self.audit()

        self.assertEqual(0, code, report)

    def test_binary_lock_hash_keeps_crlf_and_bare_cr_bytes(self) -> None:
        # NUL・不正UTF-8を含むbinaryと、単独CRのtextは正規化しない。
        values = {'nul.bin': b'zero\x00\r\n', 'invalid.bin': b'\xff\r\n', 'bare.txt': b'bare\rreturn'}
        for name, content in values.items():
            (self.skill / name).write_bytes(content)
            for target in ('.agents', '.claude'):
                (self.home / target / 'skills/example' / name).write_bytes(content)
                entry = self.lock['dependencies'][0]
                entry['deployed_files'].append(f'{target}/skills/example/{name}')
                entry['deployed_file_hashes'][f'{target}/skills/example/{name}'] = (
                    'sha256:' + hashlib.sha256(content).hexdigest())
        self.git('add', '.')
        self.git('commit', '-qm', 'binary fixture')

        code, report = self.audit()

        self.assertEqual(0, code, report)

    def test_missing_partial_clone_blob_does_not_invoke_a_remote_helper(self) -> None:
        marker = self.root / 'fetch-invoked'
        helper = self.root / 'bin/git-remote-auditprobe'
        helper.parent.mkdir()
        helper.write_text('#!/bin/sh\nprintf invoked > ' + shlex.quote(str(marker)) + '\nexit 1\n')
        helper.chmod(0o755)
        self.git('config', 'remote.origin.url', 'auditprobe::fixture')
        self.git('config', 'remote.origin.promisor', 'true')
        self.git('config', 'extensions.partialClone', 'origin')
        oid = self.git('hash-object', 'plugin/skills/example/SKILL.md').strip()
        (self.repo / '.git/objects' / oid[:2] / oid[2:]).unlink()
        # remote helper は local sentinel だけを書く。実ネットワークは使わない。
        from unittest.mock import patch
        with patch.dict(os.environ, {'PATH': str(helper.parent) + os.pathsep + os.environ['PATH']}):
            code, report = self.audit()

        self.assertEqual(1, code)
        self.assertIn('target-commit-unverified', self.codes(report))
        self.assertFalse(marker.exists(), 'audit attempted a lazy fetch')

    @unittest.skipIf(os.geteuid() == 0, 'root bypasses directory read permissions')
    def test_unreadable_extra_directory_is_unverified_instead_of_silently_skipped(self) -> None:
        blocked = self.home / '.agents/skills/example/blocked'
        blocked.mkdir()
        (blocked / 'extra.txt').write_text('unreadable fixture')
        blocked.chmod(0)
        self.addCleanup(blocked.chmod, 0o700)

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertEqual('unverified', report['skills'][0]['targets']['agent-skills']['status'])

    def test_deployment_newline_change_is_byte_drift_even_when_the_lock_hash_matches(self) -> None:
        deployed = self.home / '.claude/skills/example/SKILL.md'
        deployed.write_bytes(deployed.read_bytes().replace(b'\n', b'\r\n'))

        code, report = self.audit()

        self.assertEqual(1, code)
        self.assertIn('deployment-content-mismatch', self.codes(report))
        self.assertNotIn('lock-content-mismatch', self.codes(report))

    def test_copied_skill_runs_without_repository_level_scripts_or_docs(self) -> None:
        deployed_skill = self.root / 'standalone-skill'
        shutil.copytree(SCRIPT.parent.parent, deployed_skill)

        code, report = self.audit(script=deployed_skill / 'scripts/check-apm-deployment.py')

        self.assertEqual(0, code, report)
        self.assertEqual('match', report['skills'][0]['status'])
