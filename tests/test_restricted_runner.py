"""モデルの既存認証と評価ツールの環境・権限を分離する契約。"""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import os
import sys
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'plugin/skills/skill-workbench/scripts/restricted_runner.py'
SPEC = importlib.util.spec_from_file_location('restricted_runner', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RestrictedRunnerTest(unittest.TestCase):
    def fake_home(self, root):
        home = root / 'user'; (home / '.codex').mkdir(parents=True)
        (home / '.codex/auth.json').write_text('{"auth_mode":"chatgpt"}')
        return {'HOME': str(home)}

    def test_client_and_tool_environments_do_not_inherit_production_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            inherited = {'HOME': str(root / 'user'), 'PATH': '/usr/bin:/bin',
                         'AWS_SECRET_ACCESS_KEY': 'synthetic-secret', 'OPENAI_API_KEY': 'synthetic-api-key',
                         'CODEX_PERMISSION_PROFILE': 'preserve-managed-boundary', 'SHELL': '/opt/homebrew/bin/zsh'}
            client, tool = MODULE.environments(root / 'work', root / 'private', inherited)
            self.assertNotIn('AWS_SECRET_ACCESS_KEY', client)
            self.assertNotIn('OPENAI_API_KEY', client)
            self.assertNotIn('CODEX_HOME', tool)
            self.assertEqual(str(root / 'user/.codex'), client['CODEX_HOME'])
            self.assertEqual(str(root / 'work'), tool['HOME'])
            self.assertEqual('preserve-managed-boundary', client['CODEX_PERMISSION_PROFILE'])
            self.assertEqual('/bin/zsh', client['SHELL'])
            self.assertEqual('/bin/zsh', tool['SHELL'])
            self.assertFalse(Path(client['TMPDIR']).is_relative_to(root / 'private'))
            self.assertTrue(Path(client['TMPDIR']).is_relative_to((root / 'work').parent))

    @unittest.skipUnless(sys.platform == 'darwin', 'validated macOS sandbox adapter')
    def test_probe_failure_cannot_return_a_model_execution_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); work = root / 'work'; private = root / 'private'
            work.mkdir(); private.mkdir()
            inherited = self.fake_home(root)
            executable = root / 'fake-codex'
            executable.write_text('#!/bin/sh\nexit 71\n'); executable.chmod(0o755)
            with self.assertRaisesRegex(ValueError, 'preflight'):
                MODULE.prepare(str(executable), work, private, inherited, 10)
            self.assertFalse((private / 'model-started').exists())

    @unittest.skipUnless(sys.platform == 'darwin', 'validated macOS sandbox adapter')
    def test_incomplete_probe_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); work = root / 'work'; private = root / 'private'
            work.mkdir(); private.mkdir()
            executable = root / 'fake-codex'
            executable.write_text('#!/bin/sh\nprintf \'{"workspace_read_write":true}\\n\'\n')
            executable.chmod(0o755)
            with self.assertRaisesRegex(ValueError, 'preflight'):
                MODULE.prepare(str(executable), work, private, self.fake_home(root), 10)

    @unittest.skipUnless(sys.platform == 'darwin', 'validated macOS sandbox adapter')
    def test_workbench_never_starts_model_when_preflight_fails(self):
        import json
        import sys
        spec = importlib.util.spec_from_file_location('restricted_workbench', SCRIPT.parent / 'workbench.py')
        wb = importlib.util.module_from_spec(spec); spec.loader.exec_module(wb)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / 'source'; source.mkdir(); (source / 'SKILL.md').write_text('synthetic skill')
            fixture = root / 'fixture'; fixture.mkdir()
            archive = root / 'archive'
            candidate = wb.snapshot(archive, source, {'parents': [], 'hypothesis': 'runner boundary', 'strategy': 'baseline'})
            executable = root / 'fake-codex'; marker = root / 'model-started'; version_env = root / 'version-env.json'
            executable.write_text('#!' + sys.executable + '\nimport sys,pathlib\n'
                'if "--version" in sys.argv:\n'
                ' import json,os; pathlib.Path(' + repr(str(version_env)) + ').write_text(json.dumps({"has_secret":"AWS_SECRET_ACCESS_KEY" in os.environ,"shell":os.environ.get("SHELL")})); print("codex-cli 0.159.3"); sys.exit(0)\n'
                'if "sandbox" in sys.argv: sys.exit(71)\n'
                'pathlib.Path(' + repr(str(marker)) + ').touch()\n')
            executable.chmod(0o755)
            suite = {'version': 2, 'mode': 'execution', 'entrypoint': 'SKILL.md', 'cases': [
                {'id': 'case', 'split': 'train', 'prompt': 'synthetic task',
                 'checks': [{'id': 'outcome', 'criterion': 'correct', 'required': True}]}]}
            case = suite['cases'][0]
            case['contract'] = {'source_prompt': case['prompt'], 'requirements': [
                {'text': case['prompt'], 'checks': [c['id']], 'surfaces': ['artifact']} for c in case['checks']],
                'reviewed_by': 'case-owner', 'review_note': 'Synthetic boundary test.'}
            inherited = self.fake_home(root); inherited['CODEX_HOME'] = str(root / 'user/.codex'); inherited['AWS_SECRET_ACCESS_KEY'] = 'synthetic-secret'
            with patch.dict(os.environ, inherited):
                run = wb.execute(archive, candidate, suite, 'case', fixture,
                    {'model': 'existing-model', 'reasoning': 'low', 'context': 'synthetic',
                     'restricted': {'executable': str(executable)}}, timeout=10)
            self.assertFalse(marker.exists())
            self.assertEqual({'has_secret': False, 'shell': '/bin/zsh'}, json.loads(version_env.read_text()))
            self.assertEqual('error', wb.load_run(run)['status'])
            self.assertFalse(json.loads((run / 'preflight.json').read_text())['passed'])

    @unittest.skipUnless(sys.platform == 'darwin', 'validated macOS sandbox adapter')
    def test_ancestor_project_configuration_is_rejected_before_any_subprocess(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); work = root / 'project/child/work'; private = root / 'private'
            work.mkdir(parents=True); private.mkdir()
            inherited = self.fake_home(root)
            for name in ('.codex', '.mcp.json'):
                marker = root / 'project' / name
                marker.touch()
                with patch.object(MODULE.subprocess, 'Popen') as launch:
                    with self.assertRaisesRegex(ValueError, 'project client configuration'):
                        MODULE.prepare('/usr/bin/true', work, private, inherited, 10)
                    launch.assert_not_called()
                marker.unlink()

    @unittest.skipUnless(sys.platform == 'darwin', 'validated macOS sandbox adapter')
    def test_non_object_auth_metadata_is_a_recordable_validation_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); work = root / 'work'; private = root / 'private'
            work.mkdir(); private.mkdir()
            inherited = self.fake_home(root)
            for value in ('null', '[]', '"synthetic"'):
                (root / 'user/.codex/auth.json').write_text(value)
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'ChatGPT sign-in'):
                    MODULE.prepare('/usr/bin/true', work, private, inherited, 10)

    def test_explicit_null_restricted_config_cannot_fall_back_to_default_runner(self):
        spec = importlib.util.spec_from_file_location('restricted_workbench', SCRIPT.parent / 'workbench.py')
        wb = importlib.util.module_from_spec(spec); spec.loader.exec_module(wb)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'source'; source.mkdir()
            (source / 'SKILL.md').write_text('synthetic skill')
            archive = root / 'archive'; fixture = root / 'fixture'; fixture.mkdir()
            candidate = wb.snapshot(archive, source, {'parents': [], 'hypothesis': 'boundary', 'strategy': 'baseline'})
            suite = {'version': 2, 'mode': 'execution', 'entrypoint': 'SKILL.md', 'cases': [
                {'id': 'case', 'split': 'train', 'prompt': 'synthetic task',
                 'checks': [{'id': 'outcome', 'criterion': 'correct', 'required': True}]}]}
            case = suite['cases'][0]
            case['contract'] = {'source_prompt': case['prompt'], 'requirements': [
                {'text': case['prompt'], 'checks': [c['id']], 'surfaces': ['artifact']} for c in case['checks']],
                'reviewed_by': 'case-owner', 'review_note': 'Synthetic boundary test.'}
            with patch.object(wb.subprocess, 'run') as launch:
                with self.assertRaisesRegex(ValueError, 'restricted requires'):
                    wb.execute(archive, candidate, suite, 'case', fixture,
                        {'model': 'existing-model', 'reasoning': 'low', 'context': 'synthetic', 'restricted': None})
                launch.assert_not_called()
