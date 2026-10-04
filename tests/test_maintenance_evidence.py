"""Synthetic tool evidence and compatibility; no reader, socket, or private history."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from tests import test_skill_maintenance as baseline
from tests import test_codex_app as app_tests


ROOT = Path(__file__).resolve().parents[1]
TRACE = json.loads((ROOT / 'meta/skill-maintenance/examples/trace-export.json').read_text())


class EvidenceTest(unittest.TestCase):
    # Reuse only the transactional CLI harness.
    tearDown = baseline.MaintenanceTest.tearDown
    collect = baseline.MaintenanceTest.collect
    batch = baseline.MaintenanceTest.batch
    record = baseline.MaintenanceTest.record

    def setUp(self):
        baseline.MaintenanceTest.setUp(self)
        self.document = copy.deepcopy(TRACE)

    def evidence(self):
        return self.document['sessions'][0]['units'][0]['evidence']

    def test_tool_failure_correction_and_recheck_survive_collect_record_replay(self):
        first = self.batch(self.collect())
        self.assertEqual(self.evidence(), first['cases'][0]['units'][0]['evidence'])
        self.assertEqual({'with_trace': 1, 'report_only': 0, 'outcomes_independently_verified': False},
                         first['evidence_quality'])
        self.assertEqual(0, self.record(first, 'no-change').returncode)
        again = self.batch(self.collect())
        self.assertEqual([], again['cases'])
        self.assertEqual(1, len(json.loads(self.state.read_text())['units']))

    def test_incomplete_and_truncated_evidence_leave_checkpoint_unchanged(self):
        self.batch(self.collect())
        original = self.state.read_bytes()
        for field, value in [('complete', False), ('truncated', True)]:
            with self.subTest(field=field):
                self.evidence()[field] = value
                result = self.collect()
                self.assertEqual(2, result.returncode)
                self.assertEqual(original, self.state.read_bytes())
                self.evidence()[field] = not value

    def test_missing_results_bad_order_duplicate_ids_and_unknown_fields_block(self):
        events = copy.deepcopy(self.evidence()['events'])
        invalid = [events[:-1], list(reversed(events)), events + [events[-1]],
                   [{**events[0], 'arguments': 'raw command'}, *events[1:]],
                   [*events[:2], {**events[2], 'references': ['unseen']}, *events[3:]],
                   [{**events[0], 'summary': 'x' * 4097}, *events[1:]]]
        for rows in invalid:
            with self.subTest(rows=[r['id'] for r in rows]):
                self.evidence()['events'] = rows
                self.assertEqual(2, self.collect().returncode)
                self.assertFalse(self.state.exists())

    def test_sensitive_summary_or_content_is_not_saved_or_echoed(self):
        sensitive = 'api' + '_key=' + 'synthetic-value'
        for location in ['summary', 'multiline-summary', 'tool', 'request', 'timestamp']:
            with self.subTest(location=location):
                self.document = copy.deepcopy(TRACE)
                if location == 'summary':
                    self.evidence()['events'][1]['summary'] = sensitive
                elif location == 'multiline-summary':
                    self.evidence()['events'][1]['summary'] = sensitive.replace('=', '\n=')
                elif location == 'tool':
                    self.evidence()['events'][0]['tool'] = sensitive.replace('=', '\n=')
                elif location == 'timestamp':
                    self.document['sessions'][0]['units'][0]['updated_at'] = sensitive
                else:
                    self.document['sessions'][0]['units'][0]['content']['request'] = sensitive
                result = self.collect()
                self.assertEqual(2, result.returncode)
                self.assertNotIn(sensitive, result.stderr)
                self.assertFalse(self.state.exists())
                self.assertFalse(self.output.exists())

    def test_trace_change_with_same_revision_is_rejected(self):
        self.batch(self.collect())
        original = self.state.read_bytes()
        self.evidence()['events'][1]['summary'] = 'A different result.'
        self.assertEqual(2, self.collect().returncode)
        self.assertEqual(original, self.state.read_bytes())

    def test_legacy_input_keeps_keys_and_closed_decisions_without_implicit_enrichment(self):
        del self.document['sessions'][0]['units'][0]['evidence']
        first = self.batch(self.collect())
        self.assertEqual(1, first['evidence_quality']['report_only'])
        facts = json.loads(self.state.read_text())['units']
        self.assertTrue(all('evidence' not in u['facts'] for u in facts.values()))
        self.assertEqual(0, self.record(first, 'no-change').returncode)
        again = self.batch(self.collect())
        self.assertEqual([], again['cases'])
        original = self.state.read_bytes()
        self.document['sessions'][0]['units'][0]['evidence'] = copy.deepcopy(TRACE['sessions'][0]['units'][0]['evidence'])
        self.assertEqual(2, self.collect().returncode)
        self.assertEqual(original, self.state.read_bytes())

    def test_truncated_coverage_and_selection_change_do_not_reset_state(self):
        self.batch(self.collect())
        original = self.state.read_bytes()
        self.document['coverage']['truncated'] = True
        self.assertEqual(2, self.collect().returncode)
        self.document['coverage']['truncated'] = False
        self.document['adapter_selection'] = {'mode': 'app-index'}
        self.assertEqual(2, self.collect().returncode)
        self.assertEqual(original, self.state.read_bytes())

    def test_same_root_copy_with_conflicting_tool_evidence_is_rejected(self):
        child = copy.deepcopy(self.document['sessions'][0])
        child.update(id='child', parent_id='task')
        child['units'][0]['evidence']['events'][1]['summary'] = 'Different observed result.'
        self.document['sessions'].append(child)
        self.assertEqual(2, self.collect().returncode)
        self.assertFalse(self.state.exists())


class AppEvidenceTest(unittest.TestCase):
    setUp = app_tests.AppCaptureTest.setUp
    tearDown = app_tests.AppCaptureTest.tearDown
    run_capture = app_tests.AppCaptureTest.run_capture
    turn = app_tests.AppCaptureTest.turn

    def test_optional_trace_is_preserved_by_offline_capture_import(self):
        self.turn()['evidence'] = copy.deepcopy(TRACE['sessions'][0]['units'][0]['evidence'])
        first = self.run_capture()
        self.assertEqual(self.turn()['evidence'], first['cases'][0]['units'][0]['evidence'])
        self.assertEqual(1, first['evidence_quality']['with_trace'])
        self.assertEqual(first['cases'][0]['id'], self.run_capture()['cases'][0]['id'])


class DependencyTest(unittest.TestCase):
    def test_shared_contract_import_does_not_load_collector_or_transport(self):
        scripts = ROOT / 'meta/skill-maintenance/scripts'
        code = "import common,codex_app,sys; assert 'maintenance' not in sys.modules; assert 'codex_export' not in sys.modules; assert 'codex_wire' not in sys.modules"
        result = subprocess.run([sys.executable, '-c', code], cwd=scripts, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == '__main__':
    unittest.main()
