"""Anonymous host metadata and real CLI lifecycle contracts for completed-turn deltas."""
import copy
import json
import os
import unittest

from tests import test_work_retrospectives as fixtures


class TurnDeltaTest(unittest.TestCase):
    setUp = fixtures.RetrospectiveTest.setUp
    cli = fixtures.RetrospectiveTest.cli
    intake = fixtures.RetrospectiveTest.intake
    batch = fixtures.RetrospectiveTest.batch
    record = fixtures.RetrospectiveTest.record

    def delta(self, task='task-a', turn='work-a', reply='reply-a', revision=1):
        report = fixtures.report(task, revision)
        report['completed_at'] = report['received_at'] = None
        return dict(version=2, source_id='work-host-example',
                    selection_basis='completed-turn-delta', enumeration_complete=False,
                    requested_tasks=[dict(task_id=task, completed_turn_id=turn,
                                          receipt_turn_id=reply, status='received')], reports=[report])

    def observed(self, task='task-a', turn='work-a', status='completed', kind='work'):
        return dict(task_id=task, latest_turn_id=turn, latest_turn_status=status,
                    source_repo='example/app', information_scope='public', kind=kind)

    def select(self, tasks, *extra):
        metadata = self.home / 'metadata.json'
        metadata.write_text(json.dumps(dict(version=1, source_id='work-host-example',
                                           enumeration_complete=False, tasks=tasks)))
        result = self.cli('select-retrospectives', '--input', metadata, '--target', self.target_file,
                          '--repo', self.repo, '--state', self.state, *extra)
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def test_legacy_received_reports_are_not_requested_again_without_new_completed_turn(self):
        # Arrange: v1で受信済みの報告と、hostが照合したそのreply turn。
        self.document['reports'][0]['completed_at'] = None
        self.document['reports'][0]['received_at'] = None
        old = self.batch(self.intake())
        before = self.state.read_bytes()
        report = self.document['reports'][0]
        # Act
        selected = self.select([self.observed(turn=report['report_id'])])
        # Assert: queryは変更せず、報告replyを実務再開と誤認しない。
        self.assertEqual([], selected['requested_tasks'])
        self.assertEqual(['task-a'], selected['legacy_unbound_reports'])
        self.assertFalse(selected['history_coverage_complete'])
        self.document = self.delta(turn=report['report_id'], reply=report['report_id'])
        self.document['reports'] = [report]
        self.batch(self.intake('--new-evidence-only'))
        self.assertEqual(1, len(json.loads(self.state.read_text())['retrospective_units']))
        self.assertEqual([], self.select([self.observed(turn=report['report_id'])])['requested_tasks'])

    def test_selection_requires_completed_work_and_respects_repo_scope_and_exclusions(self):
        # Arrange
        tasks = [self.observed('task-c', 'work-c'), self.observed('task-a', 'work-a'),
                 self.observed('task-b', 'work-b'), self.observed('active', 'active-a', 'inProgress'),
                 self.observed('evaluation', 'eval-a', kind='evaluation'),
                 dict(self.observed('outside', 'outside-a'), source_repo='other/app')]
        # Act
        selected = self.select(tasks, '--exclude-root', 'task-b')
        # Assert
        self.assertEqual(['task-a', 'task-c'], [r['task_id'] for r in selected['requested_tasks']])
        self.assertEqual(2, selected['eligible_completed_turns'])
        state = json.loads(self.state.read_text())
        self.assertEqual({}, state['sources'])
        self.assertEqual({}, state.get('retrospective_units', {}))
        self.assertFalse(selected['history_coverage_complete'])

    def test_selection_returns_all_authorized_tasks_without_fixed_count_cutoff(self):
        tasks = [self.observed('task-' + str(n), 'work-' + str(n)) for n in range(43)]

        selected = self.select(tasks)

        self.assertEqual(43, len(selected['requested_tasks']))
        self.assertEqual(43, selected['eligible_completed_turns'])
        self.assertEqual(0, selected['queued_completed_turns'])
        # 選定だけでは送信・受信済みにはならず、全turnを失敗に備えて保持する。
        queue = json.loads(self.state.read_text())['retrospective_pending_turns']['work-host-example']
        self.assertEqual(43, sum(len(turns) for turns in queue.values()))

    def test_transport_pages_keep_unprocessed_turns_and_resume_without_recollecting_receipts(self):
        self.select([self.observed('task-a', 'work-a'), self.observed('task-b', 'work-b'),
                     self.observed('task-c', 'work-c')])
        self.document = self.delta()
        first = self.batch(self.intake())
        self.assertFalse(first['visible_delta_receipt_complete'])

        selected = self.select([self.observed('task-a', 'reply-a')])

        self.assertEqual([], selected['requested_tasks'])
        self.assertEqual(2, selected['queued_completed_turns'])
        selected = self.select([self.observed('task-b', 'work-b'), self.observed('task-c', 'work-c')])
        self.assertEqual(['task-b', 'task-c'], [r['task_id'] for r in selected['requested_tasks']])


    def test_intake_consumes_work_and_reply_turn_and_reopened_task_selects_only_new_turn(self):
        # Arrange
        self.document = self.delta()
        first = self.batch(self.intake())
        self.assertEqual(0, self.record(first, 'deferred').returncode)
        state = json.loads(self.state.read_text())
        # Act / Assert
        self.assertEqual([], self.select([self.observed(turn='work-a')])['requested_tasks'])
        self.assertEqual([], self.select([self.observed(turn='reply-a')])['requested_tasks'])
        next_request = self.select([self.observed(turn='work-b')])['requested_tasks']
        self.assertEqual('work-b', next_request[0]['completed_turn_id'])
        self.document = self.delta(turn='work-b', reply='reply-b', revision=2)
        resumed = self.batch(self.intake('--new-evidence-only'))
        self.assertEqual(1, len(resumed['cases']))
        self.assertEqual(2, len(resumed['cases'][0]['units']))
        self.assertFalse(resumed['window_coverage_complete'])
        self.assertFalse(resumed['history_coverage_complete'])
        self.assertFalse(resumed['checkpoint_written'])
        after = json.loads(self.state.read_text())
        for key in ('sources', 'units', 'claims', 'decisions'):
            self.assertEqual(state[key], after[key])

    def test_unreceived_retry_retains_original_turn_when_latest_turn_advances(self):
        # Arrange: 元turnの取得失敗後にtaskが別turnで再開。
        self.document = self.delta()
        self.document['requested_tasks'][0].update(status='failed', receipt_turn_id=None)
        self.document['reports'] = []
        self.batch(self.intake())
        self.document['requested_tasks'] = []
        self.batch(self.intake())
        # Act
        selected = self.select([self.observed(turn='work-b')])
        # Assert: 元の未受信turnをretryしてから新turnを選ぶ。
        self.assertEqual('work-a', selected['requested_tasks'][0]['completed_turn_id'])
        self.assertTrue(selected['requested_tasks'][0]['retry'])
        self.assertEqual(1, selected['queued_completed_turns'])
        self.document = self.delta()
        self.batch(self.intake())
        selected = self.select([self.observed(turn='reply-a')])
        self.assertEqual('work-b', selected['requested_tasks'][0]['completed_turn_id'])
        self.assertFalse(selected['requested_tasks'][0]['retry'])

    def test_empty_next_delta_does_not_resolve_missing_request_or_invent_time(self):
        self.document = self.delta()
        self.document['requested_tasks'][0].update(status='held', receipt_turn_id=None)
        self.document['reports'] = []
        self.batch(self.intake())
        self.document['requested_tasks'] = []
        again = self.batch(self.intake())
        self.assertEqual(1, again['unresolved_request_count'])
        self.assertFalse(again['report_receipt_complete'])
        self.assertEqual('work-a', again['pending_requests'][0]['completed_turn_id'])

    def test_same_revision_cannot_be_bound_to_another_work_turn(self):
        self.document = self.delta()
        self.batch(self.intake())
        before = self.state.read_bytes()
        self.document['requested_tasks'][0]['completed_turn_id'] = 'different-work'
        result = self.intake()
        self.assertEqual(2, result.returncode)
        self.assertEqual(before, self.state.read_bytes())

    def test_delta_has_no_timestamp_window_but_known_receipt_order_remains_validated(self):
        self.document = self.delta()
        self.document['reports'][0]['completed_at'] = '2020-01-02T12:00:00Z'
        self.document['reports'][0]['received_at'] = '2026-01-02T13:00:00Z'
        batch = self.batch(self.intake())
        self.assertIsNone(batch['window'])
        self.assertEqual('completed-turn-delta', batch['selection_basis'])
        self.assertTrue(batch['report_receipt_complete'])
        self.assertFalse(batch['window_coverage_complete'])

    def test_registered_exclusion_survives_next_selection_and_intake(self):
        self.document = self.delta()
        self.batch(self.intake('--exclude-root', 'task-a'))
        self.assertEqual([], self.select([self.observed()])['requested_tasks'])
        again = self.batch(self.intake())
        self.assertEqual([], again['cases'])
        self.assertEqual({}, json.loads(self.state.read_text())['retrospective_units'])

    def test_selector_current_source_binding_does_not_hide_same_id_in_another_source(self):
        self.document = self.delta()
        self.batch(self.intake())
        state = json.loads(self.state.read_text())
        state['maintenance_roots'] = {'native-other': ['task-a']}
        self.state.write_text(json.dumps(state))
        previous = os.environ.get('CODEX_THREAD_ID')
        os.environ['CODEX_THREAD_ID'] = 'task-a'
        try:
            selected = self.select([self.observed(turn='new-work')])
            self.assertEqual(1, len(selected['requested_tasks']))
        finally:
            if previous is None:
                os.environ.pop('CODEX_THREAD_ID', None)
            else:
                os.environ['CODEX_THREAD_ID'] = previous

    def test_invalid_delta_receipts_and_duplicate_task_metadata_are_rejected(self):
        valid = self.delta()
        changes = [dict(selection_basis='time-window'), dict(window={}),
                   dict(requested_tasks=[dict(valid['requested_tasks'][0], receipt_turn_id=None)]),
                   dict(requested_tasks=[dict(valid['requested_tasks'][0], completed_turn_id='')])]
        for change in changes:
            with self.subTest(change=change):
                self.document = dict(copy.deepcopy(valid), **change)
                self.assertEqual(2, self.intake().returncode)
                self.assertFalse(self.state.exists())
        metadata = self.home / 'metadata.json'
        metadata.write_text(json.dumps(dict(version=1, source_id='work-host-example',
                                           enumeration_complete=True, tasks=[self.observed(), self.observed()])))
        result = self.cli('select-retrospectives', '--input', metadata, '--target', self.target_file,
                          '--repo', self.repo, '--state', self.state)
        self.assertEqual(2, result.returncode)

    def test_selector_state_cannot_overwrite_target_or_input(self):
        metadata = self.home / 'metadata.json'
        metadata.write_text(json.dumps(dict(version=1, source_id='work-host-example',
                                           enumeration_complete=False, tasks=[self.observed()])))
        for protected in (self.target_file, metadata):
            before = protected.read_bytes()
            result = self.cli('select-retrospectives', '--input', metadata, '--target', self.target_file,
                              '--repo', self.repo, '--state', protected)
            self.assertEqual(2, result.returncode)
            self.assertEqual(before, protected.read_bytes())

    def test_legacy_missing_request_is_not_silently_resolved_by_a_different_delta(self):
        self.document['requested_tasks'][0]['status'] = 'held'
        self.document['reports'] = []
        self.batch(self.intake())
        before = self.state.read_bytes()
        selected = self.select([self.observed()])
        self.assertEqual(['task-a'], selected['legacy_unbound_requests'])
        self.assertEqual([], selected['requested_tasks'])
        queued = json.loads(self.state.read_text())
        self.assertEqual(['work-a'], queued['retrospective_pending_turns']['work-host-example']['task-a'])
        before = self.state.read_bytes()
        self.document = self.delta()
        self.assertEqual(2, self.intake().returncode)
        self.assertEqual(before, self.state.read_bytes())
        self.document = json.loads((fixtures.ROOT / 'plugin/skills/skill-maintenance/examples/work-retrospectives.json').read_text())
        self.batch(self.intake())
        legacy_report = copy.deepcopy(self.document['reports'][0])
        self.document = self.delta(turn='old-reply', reply='old-reply')
        self.document['reports'] = [legacy_report]
        self.batch(self.intake())
        self.assertEqual('work-a', self.select([self.observed(turn='old-reply')])['requested_tasks'][0]['completed_turn_id'])

    def test_complete_metadata_with_queued_turns_is_not_complete_receipt_coverage(self):
        self.select([self.observed('task-a', 'work-a'), self.observed('task-b', 'work-b'),
                     self.observed('task-c', 'work-c')])
        self.document = self.delta()
        self.document['enumeration_complete'] = True
        batch = self.batch(self.intake())
        self.assertFalse(batch['visible_delta_receipt_complete'])
        self.assertFalse(batch['history_coverage_complete'])

    def test_legacy_report_id_collision_needs_explicit_receipt_binding_and_preserves_new_turn(self):
        self.document['reports'][0]['report_id'] = 'work-b'
        self.document['reports'][0]['completed_at'] = None
        self.document['reports'][0]['received_at'] = None
        legacy_report = copy.deepcopy(self.document['reports'][0])
        self.batch(self.intake())
        selected = self.select([self.observed(turn='work-b')])
        self.assertEqual(['task-a'], selected['legacy_unbound_reports'])
        self.assertEqual([], selected['requested_tasks'])
        self.document = self.delta(turn='old-reply', reply='old-reply')
        self.document['reports'] = [legacy_report]
        self.batch(self.intake())
        selected = self.select([self.observed(turn='old-reply')])
        self.assertEqual('work-b', selected['requested_tasks'][0]['completed_turn_id'])

    def test_same_revision_receipt_cannot_be_changed_to_hide_another_work_turn(self):
        self.document = self.delta()
        self.batch(self.intake())
        before = self.state.read_bytes()
        self.document['requested_tasks'][0]['receipt_turn_id'] = 'work-b'
        self.assertEqual(2, self.intake().returncode)
        self.assertEqual(before, self.state.read_bytes())
        self.assertEqual('work-b', self.select([self.observed(turn='work-b')])['requested_tasks'][0]['completed_turn_id'])

    def test_terminal_failed_or_interrupted_latest_does_not_block_original_completed_retry(self):
        for status in ('failed', 'interrupted'):
            with self.subTest(status=status):
                self.document = self.delta()
                self.document['requested_tasks'][0].update(status='failed', receipt_turn_id=None)
                self.document['reports'] = []
                self.batch(self.intake())
                selected = self.select([self.observed(turn='later-turn', status=status)])
                self.assertEqual('work-a', selected['requested_tasks'][0]['completed_turn_id'])
        active = self.select([self.observed(turn='active', status='inProgress')])
        self.assertEqual([], active['requested_tasks'])
        self.assertEqual(['task-a'], active['held_retry_tasks'])

    def test_delta_case_budget_order_does_not_depend_on_original_or_receipt_time(self):
        self.document = self.delta()
        second = self.delta('task-b', 'work-b', 'reply-b')
        self.document['requested_tasks'] += second['requested_tasks']
        self.document['reports'] += second['reports']
        for report, year in zip(self.document['reports'], (2030, 2020)):
            report['completed_at'] = report['received_at'] = f'{year}-01-02T12:00:00Z'
        batch = self.batch(self.intake())
        self.assertEqual('task-a', batch['cases'][0]['root_id'])

    def test_selector_explicit_exclusion_persists_and_clears_old_retry_queue(self):
        self.document = self.delta()
        self.document['requested_tasks'][0].update(status='failed', receipt_turn_id=None)
        self.document['reports'] = []
        self.batch(self.intake())
        self.select([self.observed(turn='work-b')])
        self.assertEqual([], self.select([self.observed(turn='work-b')], '--exclude-root', 'task-a')['requested_tasks'])
        self.assertEqual([], self.select([self.observed(turn='work-b')])['requested_tasks'])
        state = json.loads(self.state.read_text())
        self.assertIn('task-a', state['retrospective_excluded_roots']['work-host-example'])
        self.assertNotIn('task-a', state['retrospective_pending_requests']['work-host-example'])
        self.assertNotIn('task-a', state['retrospective_pending_turns']['work-host-example'])

    def test_unregistered_current_cannot_enter_failed_request_or_saved_queue(self):
        self.document = self.delta()
        self.document['requested_tasks'][0].update(status='failed', receipt_turn_id=None)
        self.document['reports'] = []
        env = dict(os.environ, CODEX_THREAD_ID='task-a')
        self.assertEqual(2, self.intake(env=env).returncode)
        self.assertFalse(self.state.exists())
        self.batch(self.intake())
        before = self.state.read_bytes()
        self.document['requested_tasks'] = []
        self.assertEqual(2, self.intake(env=env).returncode)
        self.assertEqual(before, self.state.read_bytes())

    def test_v1_cannot_resolve_or_overwrite_turn_bound_v2_missing_request(self):
        self.document = self.delta()
        self.document['requested_tasks'][0].update(status='failed', receipt_turn_id=None)
        self.document['reports'] = []
        self.batch(self.intake())
        before = self.state.read_bytes()
        v1 = json.loads((fixtures.ROOT / 'plugin/skills/skill-maintenance/examples/work-retrospectives.json').read_text())
        for status in ('received', 'held'):
            with self.subTest(status=status):
                self.document = copy.deepcopy(v1)
                self.document['requested_tasks'][0]['status'] = status
                if status != 'received':
                    self.document['reports'] = []
                self.assertEqual(2, self.intake().returncode)
                self.assertEqual(before, self.state.read_bytes())


if __name__ == '__main__':
    unittest.main()
