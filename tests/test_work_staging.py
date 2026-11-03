"""Response staging preserves synthetic input without changing the intake ledger."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'plugin/skills/skill-maintenance/scripts/maintenance.py'


class WorkStagingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.repo = self.home / 'repo'
        self.repo.mkdir()
        self.input = self.home / 'response.json'
        self.output = self.home / 'responses'
        self.document = json.loads((ROOT / 'plugin/skills/skill-maintenance/examples/work-retrospectives.json').read_text())
        self.document.pop('window')
        self.document.update(version=2, selection_basis='completed-turn-delta')
        for task in self.document['requested_tasks']:
            task.update(completed_turn_id='work-' + task['task_id'], receipt_turn_id='reply-' + task['task_id']
                        if task['status'] == 'received' else None)

    def stage(self, raw=None, response_id='response-1'):
        self.input.write_bytes(raw if raw is not None else json.dumps(self.document).encode())
        return subprocess.run([sys.executable, str(SCRIPT), 'stage-retrospectives', '--input', str(self.input),
                               '--repo', str(self.repo), '--output', str(self.output), '--response-id', response_id],
                              capture_output=True, text=True, timeout=3)

    def receipt(self, result):
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(Path(json.loads(result.stdout)['receipt']).read_text())

    def test_mixed_invalid_identity_keeps_valid_report_and_original_bytes(self):
        invalid = copy.deepcopy(self.document['reports'][0])
        invalid.update(task_id='unknown-task', report_id=None, revision=None)
        self.document['reports'].append(invalid)
        self.document['requested_tasks'].append(dict(task_id='unknown-task', status='received',
                                                     completed_turn_id='work-unknown', receipt_turn_id='reply-unknown'))
        receipt = self.receipt(self.stage())
        self.assertEqual(1, len(receipt['envelopes']))
        self.assertEqual(1, len(receipt['held']))
        self.assertEqual(self.input.read_bytes(), Path(receipt['raw_path']).read_bytes())
        prepared = json.loads(Path(receipt['envelopes'][0]).read_text())
        self.assertEqual(self.document['reports'][:1], prepared['reports'])
        self.assertFalse(prepared['enumeration_complete'])
        self.assertFalse(receipt['state_written'])

    def test_special_characters_are_data_and_replay_reuses_the_same_receipt(self):
        self.document['reports'][0]['claims'][0]['summary'] = '`touch SHOULD_NOT_EXIST` $(touch SHOULD_NOT_EXIST) " \\ 日本語'
        first = self.receipt(self.stage())
        second = self.receipt(self.stage())
        self.assertEqual(first, second)
        self.assertEqual(1, len(list(self.output.iterdir())))
        self.assertFalse((ROOT / 'SHOULD_NOT_EXIST').exists())
        self.assertEqual(hashlib.sha256(self.input.read_bytes()).hexdigest(), first['sha256'])

    def test_duplicate_task_is_held_without_choosing_an_arbitrary_report(self):
        self.document['reports'].append(copy.deepcopy(self.document['reports'][0]))
        receipt = self.receipt(self.stage())
        self.assertEqual([], receipt['envelopes'])
        self.assertTrue(receipt['held'])

    def test_out_of_range_timestamp_does_not_block_an_independent_valid_report(self):
        invalid = copy.deepcopy(self.document['reports'][0])
        invalid.update(task_id='invalid-time', report_id='report-time', completed_at='0001-01-01T00:00:00+23:59')
        self.document['reports'].append(invalid)
        self.document['requested_tasks'].append(dict(task_id='invalid-time', status='received',
                                                     completed_turn_id='work-time', receipt_turn_id='reply-time'))
        receipt = self.receipt(self.stage())
        self.assertEqual(1, len(receipt['envelopes']))
        self.assertEqual(1, len(receipt['held']))

    def test_truncated_response_is_retained_and_later_response_can_resume(self):
        broken = self.receipt(self.stage(b'{"reports": ['))
        self.assertEqual([], broken['envelopes'])
        good = self.receipt(self.stage(response_id='response-2'))
        self.assertEqual(1, len(good['envelopes']))
        self.assertEqual(b'{"reports": [', Path(broken['raw_path']).read_bytes())

    def test_same_response_id_with_changed_content_is_rejected_without_overwrite(self):
        first = self.receipt(self.stage())
        old = Path(first['raw_path']).read_bytes()
        result = self.stage(b'{}')
        self.assertEqual(2, result.returncode)
        self.assertEqual(old, Path(first['raw_path']).read_bytes())

    def test_saved_response_can_resume_before_receipt_and_pass_normal_intake(self):
        receipt = self.receipt(self.stage())
        event = Path(receipt['raw_path']).parent
        # 原本保存後、事前検査結果の保存前に終了した状態を再構成する。
        for path in event.iterdir():
            if path.name != 'response.json':
                path.unlink()
        resumed = self.receipt(self.stage())
        target = self.home / 'target.json'
        target.write_bytes((ROOT / 'plugin/skills/skill-maintenance/examples/target.json').read_bytes())
        state = self.home / 'state.json'
        result = subprocess.run([sys.executable, str(SCRIPT), 'intake-retrospectives',
                                 '--input', resumed['envelopes'][0], '--target', str(target),
                                 '--repo', str(self.repo), '--state', str(state), '--output', str(self.home / 'batches')],
                                capture_output=True, text=True, timeout=3)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(1, len(json.loads(state.read_text())['retrospective_units']))


if __name__ == '__main__':
    unittest.main()
