"""User-facing daily report CLI uses sanitized, synthetic summaries only."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'meta/skill-maintenance/scripts/maintenance.py'


class DailyReportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.repo = self.home / 'repo'
        self.repo.mkdir()
        self.input = self.home / 'summary.json'
        self.output = self.home / 'report.md'
        self.config = self.home / 'report-config.json'
        self.settings = dict(version=1, report_timezone='Asia/Tokyo', information_scope='personal:example',
                             report_destination=dict(kind='host-space', reference='caller-private-parent',
                                                     information_scope='personal:example'))
        self.document = json.loads((ROOT / 'meta/skill-maintenance/examples/daily-report.json').read_text())

    def run_report(self, output=None):
        self.input.write_text(json.dumps(self.document))
        self.config.write_text(json.dumps(self.settings))
        return subprocess.run([sys.executable, str(SCRIPT), 'daily-report', '--input', str(self.input),
                               '--config', str(self.config), '--repo', str(self.repo), '--output', str(output or self.output)],
                              capture_output=True, text=True, timeout=3)

    def test_report_is_portable_and_separates_self_report_failure_and_candidate_hold(self):
        self.document['candidates'][0]['pr_urls'] = ['https://github.com/example/skills/pull/7']

        result = self.run_report()

        self.assertEqual(0, result.returncode, result.stderr)
        content = self.output.read_text()
        self.assertIn('注文処理の失敗ログ確認', content)
        self.assertIn('自己申告', content)
        self.assertIn('取得失敗', content)
        self.assertIn('保留', content)
        self.assertIn('https://github.com/example/skills/pull/7', content)
        self.assertEqual('host-handoff-pending', json.loads(result.stdout)['delivery_status'])
        self.assertEqual(0, self.output.stat().st_mode & 0o077)
        handoff = json.loads(Path(json.loads(result.stdout)['handoff']).read_text())
        self.assertEqual('personal:example', handoff['information_scope'])
        self.assertEqual('caller-private-parent', handoff['destination']['reference'])
        self.assertEqual(hashlib.sha256(self.output.read_bytes()).hexdigest(), handoff['parts'][0]['sha256'])
        self.assertNotIn('caller-private-parent', content)

    def test_expanded_markdown_is_partitioned_without_losing_entries(self):
        sample = self.document['sessions'][0]
        self.document['sessions'] = [dict(sample, label='synthetic-session-' + str(n), work='&' * 15900)
                                     for n in range(110)]

        result = self.run_report()

        self.assertEqual(0, result.returncode, result.stderr)
        handoff = json.loads(Path(json.loads(result.stdout)['handoff']).read_text())
        self.assertGreater(len(handoff['parts']), 1)
        pieces = [Path(part['path']).read_bytes() for part in handoff['parts']]
        self.assertTrue(all(len(piece) <= 8 * 1024 * 1024 for piece in pieces))
        content = b''.join(pieces).decode('utf-8')
        for n in range(110):
            self.assertIn('synthetic\\-session\\-' + str(n) + '\n', content)
        self.assertEqual(0, handoff['remaining_parts'])
        self.assertEqual('host-handoff-pending', handoff['delivery_status'])

    def test_destination_scope_mismatch_blocks_all_report_outputs(self):
        self.settings['report_destination']['information_scope'] = 'organization:other'

        result = self.run_report()

        self.assertEqual(2, result.returncode)
        self.assertFalse(self.output.exists())
        self.assertEqual([], list(self.home.glob('*.handoff.json')))

    def test_input_scope_mismatch_blocks_cross_scope_handoff(self):
        self.document['information_scope'] = 'organization:other'

        result = self.run_report()

        self.assertEqual(2, result.returncode)
        self.assertIn('report input scope differs', result.stderr)
        self.assertFalse(self.output.exists())

    def test_report_rejects_private_material_and_unknown_fields_before_writing(self):
        original = copy.deepcopy(self.document)
        for value in ('/Users/example/private/file', 'C:\\private\\file',
                      'api' + '_key=synthetic-secret', '12345678-1234-1234-1234-123456789abc',
                      'https://private.example/raw-log'):
            with self.subTest(value=value):
                self.document = copy.deepcopy(original)
                self.document['sessions'][0]['work'] = value
                result = self.run_report()
                self.assertEqual(2, result.returncode)
                self.assertNotIn(value, result.stderr)
                self.assertFalse(self.output.exists())
        self.document = {**original, 'raw_trace': 'should not pass'}
        self.assertEqual(2, self.run_report().returncode)
        self.assertFalse(self.output.exists())

    def test_existing_report_and_repo_files_are_not_overwritten(self):
        self.output.write_text('existing report')

        result = self.run_report()

        self.assertEqual(2, result.returncode)
        self.assertEqual('existing report', self.output.read_text())
        self.assertEqual(2, self.run_report(self.repo / 'private.md').returncode)
        self.assertFalse((self.repo / 'private.md').exists())

    def test_case_alias_of_repo_is_rejected_before_private_report_is_created(self):
        alias = self.repo.parent / self.repo.name.upper()
        if not alias.exists() or not alias.samefile(self.repo):
            self.skipTest('case-insensitive filesystem required')

        result = self.run_report(alias / 'private.md')

        self.assertEqual(2, result.returncode)
        self.assertFalse((self.repo / 'private.md').exists())

    def test_report_neutralizes_markdown_in_sanitized_labels(self):
        self.document['sessions'][0]['label'] = '[作業](任意リンク) <script> *注記*'

        result = self.run_report()

        self.assertEqual(0, result.returncode, result.stderr)
        content = self.output.read_text()
        self.assertNotIn('<script>', content)
        self.assertNotIn('[作業](任意リンク)', content)
