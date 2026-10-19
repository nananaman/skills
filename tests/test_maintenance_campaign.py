"""評価予算と再開境界の公開契約。モデルや実サービスは呼ばない。"""
import importlib.util
from pathlib import Path
import tempfile
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'plugin/skills/skill-maintenance/scripts/campaign.py'


SPEC = importlib.util.spec_from_file_location('campaign', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CampaignTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'campaign'

    def recorded_run(self, attempt, verdict='pass', environment='frozen', seconds=1):
        wb = MODULE.wb
        plan = self.plan()
        folder = self.root / ('run' + attempt['id'])
        folder.mkdir()
        wb.write_new(folder / 'suite.json', plan['suite'])
        record = {'id': folder.name, 'candidate': attempt['candidate'], 'case': attempt['case'],
                  'repeat': attempt['repeat'], 'suite': wb.digest(plan['suite']), 'environment': environment,
                  'status': 'completed', 'metrics': {'duration_seconds': seconds, 'tokens': None, 'cost_usd': None},
                  'checks': {}, 'artifacts': wb.artifact_digests(folder)}
        wb.write_new(folder / 'run.json', record)
        wb.write_new(folder / 'run-digest.json', wb.digest(record))
        wb.grade(folder, {'grader': 'independent', 'checks': {
            key: {'verdict': verdict, 'evidence': 'fixture observation'} for key in ('outcome','honesty')}})
        return folder

    def pair(self, case, before='pass', after='pass'):
        for candidate, verdict in [('old', before), ('new', after)]:
            a = MODULE.claim(self.folder, candidate, case, 1, 10)
            MODULE.finish(self.folder, a['id'], self.recorded_run(a, verdict))

    def test_finished_attempt_still_consumes_run_and_time_reservations(self):
        for budget, message in [({'max_runs': 1}, 'run budget'), ({'max_seconds': 10}, 'time budget')]:
            with self.subTest(budget=budget):
                folder = self.root / ('limited' + message[0])
                plan = self.plan(); plan['budget'] = budget
                MODULE.create(folder, plan)
                a = MODULE.claim(folder, 'old', 'broken', 1, 10)
                MODULE.finish(folder, a['id'], self.recorded_run(a))
                with self.assertRaisesRegex(ValueError, message):
                    MODULE.claim(folder, 'new', 'broken', 1, 1)

    def test_concurrent_cli_claims_dispatch_exactly_once(self):
        MODULE.create(self.folder, self.plan())
        command = [sys.executable, str(SCRIPT), 'claim', '--campaign', str(self.folder),
                   '--candidate', 'old', '--case', 'broken', '--repeat', '1', '--timeout', '10']
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: subprocess.run(command, capture_output=True), range(4)))
        self.assertEqual(1, sum(r.returncode == 0 for r in results))
        self.assertEqual(1, len(MODULE.status(self.folder)['attempts']))

    def test_error_recovery_keeps_charge_and_requires_new_repeat(self):
        MODULE.create(self.folder, self.plan())
        a = MODULE.claim(self.folder, 'old', 'broken', 1, 30)
        MODULE.interrupt(self.folder, a['id'], 'host confirmed process stopped; no external effects')
        state = MODULE.status(self.folder)
        self.assertEqual('interrupted', state['attempts'][0]['status'])
        self.assertEqual(30, state['attempts'][0]['charged_seconds'])
        with self.assertRaisesRegex(ValueError, 'already claimed'):
            MODULE.claim(self.folder, 'old', 'broken', 1, 30)
        MODULE.claim(self.folder, 'old', 'broken', 2, 30)
        with self.assertRaises(ValueError):
            MODULE.claim(self.folder, 'new', 'broken', 1, 1)

    def test_record_must_match_claim_and_frozen_environment(self):
        plan = self.plan(); plan['budget'] = {}
        MODULE.create(self.folder, plan)
        a = MODULE.claim(self.folder, 'old', 'broken', 1, 10)
        run = self.recorded_run(a)
        MODULE.finish(self.folder, a['id'], run)
        b = MODULE.claim(self.folder, 'new', 'broken', 1, 10)
        with self.assertRaisesRegex(ValueError, 'environment'):
            MODULE.finish(self.folder, b['id'], self.recorded_run(b, environment='different'))
        self.assertEqual('running', MODULE.status(self.folder)['attempts'][1]['status'])

    def test_holdout_requires_independent_selection_and_clean_final_gate(self):
        plan = self.plan(); plan['budget'] = {}
        MODULE.create(self.folder, plan)
        with self.assertRaisesRegex(ValueError, 'select before test'):
            MODULE.claim(self.folder, 'new', 'fresh', 1, 10)
        self.pair('broken', before='fail')
        self.pair('ordinary')
        summary = MODULE.summarize(self.folder)
        self.assertEqual(1, summary['splits']['train']['candidate']['successes'])
        self.assertIsNone(summary['splits']['train']['candidate']['cost_usd'])
        self.assertIsNone(summary['comparisons']['train']['metrics']['cost_usd_delta'])
        with self.assertRaisesRegex(ValueError, 'independent'):
            MODULE.select(self.folder, 'editor', 'approve', summary['evidence_digest'], 'observed benefit')
        MODULE.select(self.folder, 'reviewer', 'approve', summary['evidence_digest'], 'observed benefit')
        with self.assertRaisesRegex(ValueError, 'selection frozen'):
            MODULE.claim(self.folder, 'new', 'broken', 2, 10)
        self.pair('fresh')
        final = MODULE.summarize(self.folder)
        self.assertEqual('eligible_for_draft', MODULE.gate(self.folder, 'reviewer2', final['evidence_digest'], 'fresh review')['status'])
        with self.assertRaisesRegex(ValueError, 'campaign frozen'):
            MODULE.claim(self.folder, 'new', 'fresh', 2, 10)

    def test_required_failure_tie_and_false_success_block_adoption(self):
        plan = self.plan(); plan['budget'] = {}
        MODULE.create(self.folder, plan)
        self.pair('broken', before='fail')
        self.pair('ordinary', before='fail', after='fail')
        summary = MODULE.summarize(self.folder)
        self.assertEqual(1, summary['splits']['validation']['candidate']['false_successes'])
        with self.assertRaisesRegex(ValueError, 'candidate required checks'):
            MODULE.select(self.folder, 'reviewer', 'approve', summary['evidence_digest'], 'high score')

    def test_interrupted_attempt_blocks_adoption_and_remains_in_success_denominator(self):
        plan = self.plan(); plan['budget'] = {}
        MODULE.create(self.folder, plan)
        a = MODULE.claim(self.folder, 'old', 'broken', 2, 10)
        MODULE.interrupt(self.folder, a['id'], 'host confirmed stopped')
        self.pair('broken', before='fail'); self.pair('ordinary')
        summary = MODULE.summarize(self.folder)
        self.assertEqual(1, summary['unresolved_attempts'])
        self.assertEqual(2, summary['splits']['train']['baseline']['attempts'])
        with self.assertRaisesRegex(ValueError, 'unresolved attempts'):
            MODULE.select(self.folder, 'reviewer', 'approve', summary['evidence_digest'], 'later pairs passed')

    def test_stale_review_cannot_select_after_new_evidence(self):
        plan = self.plan(); plan['budget'] = {}
        MODULE.create(self.folder, plan)
        old = MODULE.summarize(self.folder)['evidence_digest']
        self.pair('broken', before='fail'); self.pair('ordinary')
        with self.assertRaisesRegex(ValueError, 'stale review evidence'):
            MODULE.select(self.folder, 'reviewer', 'approve', old, 'old judgment')
        self.assertIsNone(MODULE.status(self.folder)['selection'])

    def test_rejected_selection_never_unlocks_test(self):
        plan = self.plan(); plan['budget'] = {}
        MODULE.create(self.folder, plan)
        summary = MODULE.summarize(self.folder)
        MODULE.select(self.folder, 'reviewer', 'reject', summary['evidence_digest'], 'no useful candidate')
        with self.assertRaisesRegex(ValueError, 'select before test'):
            MODULE.claim(self.folder, 'new', 'fresh', 1, 10)

    def test_near_duplicate_family_cannot_cross_holdout_boundary(self):
        plan = self.plan()
        plan['cases']['fresh']['family'] = 'broken'
        with self.assertRaisesRegex(ValueError, 'family crosses'):
            MODULE.create(self.folder, plan)
        self.assertFalse(self.folder.exists())

    def test_unsupported_money_budget_fails_without_silently_dropping_it(self):
        plan = self.plan(); plan['budget']['max_cost_usd'] = 1
        with self.assertRaisesRegex(ValueError, 'host hard limiter'):
            MODULE.create(self.folder, plan)
        self.assertFalse(self.folder.exists())

    def test_claim_is_durable_and_duplicate_is_not_dispatched(self):
        spec = importlib.util.spec_from_file_location('campaign', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module.create(root / 'campaign', self.plan())
            first = module.claim(root / 'campaign', 'old', 'broken', 1, 30)
            self.assertEqual('running', first['status'])
            with self.assertRaisesRegex(ValueError, 'already claimed'):
                module.claim(root / 'campaign', 'old', 'broken', 1, 30)
            self.assertEqual(1, len(module.status(root / 'campaign')['attempts']))

    @staticmethod
    def plan():
        return {'version': 1, 'baseline': 'old', 'candidate': 'new',
                'proposer': 'editor', 'environment': 'frozen', 'budget': {'max_runs': 2, 'max_seconds': 60},
                'suite': {'version': 1, 'mode': 'execution', 'entrypoint': 'SKILL.md',
                          'cases': [{'id': name, 'prompt': 'Verify the output', 'split': split,
                                     'checks': [{'id': 'outcome', 'criterion': 'Correct output', 'required': True},
                                                {'id': 'honesty', 'criterion': 'No false success', 'required': True}]
                                     } for name, split in [('broken','train'),('ordinary','validation'),('fresh','test')]]},
                'cases': {name: {'family': name, 'origin': 'synthetic', 'normal': name == 'ordinary',
                                 'false_success_check': 'honesty', 'evidence': 'sanitized example'}
                          for name in ('broken','ordinary','fresh')}}
