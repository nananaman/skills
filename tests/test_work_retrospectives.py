"""Portable self-report CLI contracts using anonymous local files only."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'meta/skill-maintenance/scripts/maintenance.py'


def report(task='task-a', revision=1):
    return dict(task_id=task, report_id='report-' + task, revision=revision,
                source_repo='example/app', information_scope='public', kind='work',
                completed_at='2026-01-02T12:00:00Z', received_at='2026-01-02T13:00:00Z',
                claims=[dict(summary='A synthetic check passed.',
                             evidence_refs=['opaque:check-1'], unknowns=['Independent outcome unverified.'])])


class RetrospectiveTest(unittest.TestCase):
    def test_all_received_tasks_are_available_for_retrospective_even_without_candidate_budget(self):
        # 評価候補予算は全実務の回収・診断を件数で切り捨てる予算ではない。
        self.target['budget'] = dict(max_cases=0, max_runs=0)
        self.target_file.write_text(json.dumps(self.target))
        self.document['reports'] = [report('task-' + str(n)) for n in range(43)]
        self.document['requested_tasks'] = [dict(task_id=r['task_id'], status='received')
                                            for r in self.document['reports']]

        batch = self.batch(self.intake())

        self.assertEqual(43, len(batch['cases']))
        self.assertEqual(43, batch['queued_cases'])
        self.assertEqual(0, batch['budget']['max_runs'])
        self.assertEqual('ready', batch['status'])
        self.assertFalse(batch['history_coverage_complete'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.repo = self.home / 'repo'
        self.repo.mkdir()
        self.state = self.home / 'private/state.json'
        self.output = self.home / 'private/batches'
        self.input = self.home / 'reports.json'
        self.target_file = self.home / 'target.json'
        self.target = json.loads((ROOT / 'meta/skill-maintenance/examples/target.json').read_text())
        self.target_file.write_text(json.dumps(self.target))
        self.document = json.loads((ROOT / 'meta/skill-maintenance/examples/work-retrospectives.json').read_text())

    def cli(self, command, *args, env=None):
        return subprocess.run([sys.executable, str(SCRIPT), command, *map(str, args)],
                              cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=3)

    def intake(self, *extra, output=None, env=None):
        self.input.write_text(json.dumps(self.document))
        return self.cli('intake-retrospectives', '--input', self.input, '--target', self.target_file,
                        '--repo', self.repo, '--state', self.state, '--output', output or self.output,
                        *extra, env=env)

    def batch(self, result):
        self.assertEqual(0, result.returncode, result.stderr)
        self.batch_path = Path(json.loads(result.stdout)['batch'])
        return json.loads(self.batch_path.read_text())

    def record(self, batch, status, **extra):
        decision = self.home / 'decision.json'
        decision.write_text(json.dumps(dict(case_id=batch['cases'][0]['id'], status=status,
                                           reason='Synthetic decision.', **extra)))
        return self.cli('record', '--batch', self.batch_path, '--result', decision,
                        '--state', self.state, '--repo', self.repo)

    def test_intake_deduplicates_and_registers_self_report_batch_without_native_state(self):
        # Arrange: 閉じた実務taskの自己申告だけを渡す。
        # Act
        first = self.batch(self.intake())
        again = self.batch(self.intake())
        state = json.loads(self.state.read_text())
        # Assert: 同revisionは一つ、native履歴の完全性とcheckpointは主張しない。
        self.assertEqual(1, len(state['retrospective_units']))
        self.assertEqual({}, state['units'])
        self.assertEqual({}, state['sources'])
        self.assertEqual(first['cases'], again['cases'])
        self.assertEqual('self-report', first['evidence_basis'])
        self.assertFalse(first['history_coverage_complete'])
        self.assertFalse(first['checkpoint_written'])
        self.assertTrue(first['report_receipt_complete'])
        self.assertTrue(first['window_coverage_complete'])
        self.assertEqual(again['id'], state['latest_batch'])
        self.assertIn(again['id'], state['batches'])

    def test_record_decision_and_revision_resume_group_original_task(self):
        # Arrange: 保留済みのrevisionに新証拠revisionを追加する。
        first = self.batch(self.intake())
        # Act
        result = self.record(first, 'deferred')
        # Assert
        self.assertEqual(0, result.returncode, result.stderr)
        held = self.batch(self.intake('--new-evidence-only'))
        self.assertEqual([], held['cases'])
        self.assertEqual(1, held['held_cases'])
        self.document['reports'][0]['revision'] = 2
        resumed = self.batch(self.intake('--new-evidence-only'))
        self.assertEqual(1, len(resumed['cases']))
        self.assertEqual(2, len(resumed['cases'][0]['units']))
        self.assertEqual({1, 2}, {u['revision'] for u in resumed['cases'][0]['units']})
        self.assertEqual(0, self.record(resumed, 'no-change').returncode)
        self.assertEqual([], self.batch(self.intake())['cases'])

    def test_evaluation_application_and_reconciliation_use_existing_lifecycle(self):
        # Arrange: 実際の操作を行わず、同じjournalの状態遷移を検査する。
        first = self.batch(self.intake())
        candidate = 'a' * 64
        # Act
        evaluated = self.record(first, 'evaluated', candidate_id=candidate, evidence=['opaque:evaluation'])
        # Assert
        self.assertEqual(0, evaluated.returncode, evaluated.stderr)
        fresh = self.batch(self.intake())
        applying = self.record(fresh, 'applying', candidate_id=candidate, evidence=['opaque:intent'], operations=['edit'])
        self.assertEqual(0, applying.returncode, applying.stderr)
        self.target['budget']['max_cases'] = 0
        self.target_file.write_text(json.dumps(self.target))
        reconciling = self.batch(self.intake('--new-evidence-only'))
        self.assertTrue(reconciling['cases'][0]['needs_reconciliation'])
        self.assertEqual(0, self.record(reconciling, 'applied', candidate_id=candidate,
                                       evidence=['opaque:verified-diff']).returncode)
        self.assertEqual([], self.batch(self.intake())['cases'])
        state = json.loads(self.state.read_text())
        self.assertEqual('applied', state['claims'][candidate]['status'])
        self.assertEqual({}, state['units'])

    def test_native_report_rejects_registered_self_report_batch(self):
        # Arrange: 自己申告batchは登録済みでもnative取得の証明ではない。
        self.batch(self.intake())
        before = self.state.read_bytes()
        manifest = self.home / 'acquisitions.json'
        manifest.write_text(json.dumps(dict(version=1, sources=[dict(source_id=self.document['source_id'],
                            kind='work', status='collected', batch=str(self.batch_path))])))
        output = self.home / 'private/native-report.json'
        # Act
        result = self.cli('report', '--acquisitions', manifest, '--target', self.target_file,
                          '--repo', self.repo, '--state', self.state, '--output', output,
                          '--since', self.document['window']['since'], '--cutoff', self.document['window']['cutoff'],
                          '--expected-source-id', self.document['source_id'])
        # Assert
        self.assertEqual(2, result.returncode)
        self.assertIn('self-report is not native collection', result.stderr)
        self.assertEqual(before, self.state.read_bytes())
        self.assertFalse(output.exists())

    def assert_rejected_without_mutation(self, *extra, **kwargs):
        before = self.state.read_bytes() if self.state.exists() else None
        batches = sorted(self.output.glob('*.json'))
        result = self.intake(*extra, **kwargs)
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertEqual(before, self.state.read_bytes() if self.state.exists() else None)
        self.assertEqual(batches, sorted(self.output.glob('*.json')))
        return result

    def test_missing_received_report_and_changed_same_revision_fail_atomically(self):
        # Arrange: 既存revisionと、その直後に検査される追加task。
        self.batch(self.intake())
        original = copy.deepcopy(self.document)
        # Act / Assert: 欠落を成功した空入力へ変換しない。
        self.document['reports'] = []
        self.assert_rejected_without_mutation()
        self.document = original
        self.document['requested_tasks'].insert(0, dict(task_id='task-b', status='received'))
        self.document['reports'].insert(0, report('task-b'))
        self.document['reports'][1]['claims'][0]['summary'] = 'Changed claim.'
        self.assert_rejected_without_mutation()

    def test_strict_envelope_reports_reject_before_persistence(self):
        # Arrange: v1の境界・異常系を独立した入力として検査する。
        original = copy.deepcopy(self.document)
        invalid = [dict(version=True), dict(enumeration_complete=1), dict(extra='unknown'),
                   dict(window=dict(since='bad', cutoff='2026-01-03T00:00:00Z')),
                   dict(requested_tasks=[dict(task_id='task-a', status='unknown')]),
                   dict(requested_tasks=[dict(task_id='task-a', status='failed')]),
                   dict(requested_tasks=[dict(task_id='task-a', status='received')] * 2),
                   dict(reports=[report(), report()])]
        bad_reports = [dict(revision=True), dict(revision=0), dict(raw_trace='blocked'), dict(raw_reasoning=[]),
                       dict(extra='unknown'), dict(kind='other'), dict(received_at='bad'),
                       dict(completed_at='2026-01-02T12:00:00'), dict(completed_at='2026-01-04T00:00:00Z'),
                       dict(received_at='2026-01-01T00:00:00Z'), dict(claims=[]),
                       dict(claims=[dict(summary='claim', evidence_refs=[], unknowns=[])]),
                       dict(claims=[dict(summary='claim', evidence_refs=['x'], unknowns=[1])]),
                       dict(claims=[dict(summary='claim', evidence_refs=['x'], unknowns=[], raw_reasoning='blocked')])]
        invalid += [dict(reports=[{**report(), **changes}]) for changes in bad_reports]
        for changes in invalid:
            with self.subTest(changes=changes):
                self.document = {**copy.deepcopy(original), **changes}
                # Act / Assert
                self.assert_rejected_without_mutation()
                self.assertFalse(self.output.exists())
        self.document = original
        for budget in ('0', '-1', 'infinity'):
            with self.subTest(budget=budget):
                self.assert_rejected_without_mutation('--max-reports', budget)

    def test_sensitive_strings_are_rejected_without_echoing_or_saving(self):
        # Arrange: 内容、参照、未確認事項、識別子も検査対象。
        original = copy.deepcopy(self.document)
        secret = 'api' + '_key=synthetic-value'
        for location in ('summary', 'evidence_refs', 'unknowns', 'source_id', 'report_id'):
            with self.subTest(location=location):
                self.document = copy.deepcopy(original)
                if location == 'source_id':
                    self.document[location] = secret
                elif location == 'report_id':
                    self.document['reports'][0][location] = secret
                else:
                    self.document['reports'][0]['claims'][0][location] = secret if location == 'summary' else [secret]
                # Act
                result = self.assert_rejected_without_mutation()
                # Assert
                self.assertNotIn(secret, result.stderr + result.stdout)

    def test_scope_repo_and_maintenance_root_exclusions_filter_cases(self):
        # Arrange: 許可外repo/scopeと保守・評価は通常の事例にしない。
        original = copy.deepcopy(self.document)
        for changes in (dict(source_repo='other/app'), dict(information_scope='organization:other'),
                        dict(kind='skill-maintenance'), dict(kind='evaluation')):
            with self.subTest(changes=changes):
                self.document = {**copy.deepcopy(original), 'reports': [{**report(), **changes}]}
                # Act
                batch = self.batch(self.intake())
                # Assert
                self.assertEqual([], batch['cases'])
                self.assertEqual(1, batch['excluded_reports'])
                self.assertEqual({}, json.loads(self.state.read_text())['retrospective_units'])
        # 恒久kind除外は別taskの正当なscope確認を妨げない。
        self.document = copy.deepcopy(original)
        self.document['reports'] = [report('task-b')]
        self.document['requested_tasks'] = [dict(task_id='task-b', status='received')]
        self.document['reports'][0]['information_scope'] = self.target['information_scope']
        self.assertEqual(1, len(self.batch(self.intake())['cases']))

    def test_registered_explicit_and_current_roots_exclude_saved_pending_cases(self):
        # Arrange: 一度取り込んだ事例にも後からのroot除外を適用する。
        for mode in ('registered', 'explicit', 'current'):
            with self.subTest(mode=mode):
                task = 'task-' + mode
                self.document['reports'] = [report(task)]
                self.document['requested_tasks'] = [dict(task_id=task, status='received')]
                self.batch(self.intake())
                extra, env = (), None
                if mode == 'registered':
                    result = self.cli('register-run', '--target', self.target_file, '--repo', self.repo,
                                      '--state', self.state, '--source-id', self.document['source_id'], '--root-id', task,
                                      env={**os.environ, 'CODEX_THREAD_ID': task})
                    self.assertEqual(0, result.returncode, result.stderr)
                elif mode == 'explicit':
                    extra = ('--exclude-root', task)
                else:
                    env = {**os.environ, 'CODEX_THREAD_ID': task}
                # Act / Assert: 未登録currentを別sourceと推測して除外しない。
                if mode == 'current':
                    result = self.assert_rejected_without_mutation(*extra, env=env)
                    self.assertIn('current maintenance source is not registered', result.stderr)
                    continue
                batch = self.batch(self.intake(*extra, env=env))
                self.assertNotIn(task, [case['root_id'] for case in batch['cases']])
                self.assertNotIn(task, [c['root_id'] for c in self.batch(self.intake())['cases']])

    def test_missing_timestamps_and_partial_receipt_keep_missingness_and_reports_only_coverage(self):
        # Arrange: 完了時刻と受信時刻が不明でも自己申告は分析候補にできる。
        self.document['reports'][0].update(completed_at=None, received_at=None)
        self.document['requested_tasks'].append(dict(task_id='task-b', status='unsupported'))
        # Act
        batch = self.batch(self.intake())
        # Assert: 欠落は成功した空履歴ではない。
        unit = batch['cases'][0]['units'][0]
        self.assertTrue(unit['completion_timestamp_missing'])
        self.assertTrue(unit['receipt_timestamp_missing'])
        self.assertIsNone(unit['updated_at'])
        self.assertFalse(batch['report_receipt_complete'])
        self.assertFalse(batch['window_coverage_complete'])
        self.assertEqual(dict(received=1, unsupported=1, failed=0, held=0), batch['requested_outcome_counts'])
        self.assertFalse(batch['history_coverage_complete'])

    def test_unknown_completion_and_incomplete_enumeration_prevent_window_coverage(self):
        # Arrange: 全report受信と期間内reportの完全性は別の条件。
        self.document['reports'][0]['completed_at'] = None
        # Act / Assert
        batch = self.batch(self.intake())
        self.assertTrue(batch['report_receipt_complete'])
        self.assertFalse(batch['window_coverage_complete'])
        self.document['reports'][0] = report(revision=2)
        self.document['enumeration_complete'] = False
        self.assertFalse(self.batch(self.intake())['window_coverage_complete'])

    def test_unavailable_requested_tasks_remain_awaiting_input(self):
        # Arrange: 受信できなかったtaskだけの入力も欠落を明示する。
        self.document['reports'] = []
        for status in ('held', 'failed', 'unsupported'):
            with self.subTest(status=status):
                self.document['requested_tasks'][0]['status'] = status
                # Act
                first = self.batch(self.intake('--new-evidence-only'))
                again = self.batch(self.intake('--new-evidence-only'))
                # Assert
                self.assertEqual('awaiting-input', again['status'])
                self.assertEqual(first['requested_outcome_counts'], again['requested_outcome_counts'])
                self.assertFalse(again['report_receipt_complete'])
                self.assertFalse(again['window_coverage_complete'])

    def test_failed_repeat_preserves_ledger_and_opaque_references_are_never_opened(self):
        # Arrange: 存在しないpathや命令風参照も単なる文字列。
        self.document['reports'][0]['claims'][0]['evidence_refs'] = [str(self.home / 'absent'),
                                                                  'https://invalid.example/evidence', '$(touch forbidden)']
        batch = self.batch(self.intake())
        self.assertEqual(0, self.record(batch, 'failed').returncode)
        before = copy.deepcopy(json.loads(self.state.read_text())['retrospective_units'])
        # Act
        again = self.batch(self.intake('--new-evidence-only'))
        # Assert
        self.assertEqual('awaiting-evidence', again['status'])
        self.assertEqual(before, json.loads(self.state.read_text())['retrospective_units'])
        self.assertFalse((ROOT / 'forbidden').exists())

    def test_native_journal_checkpoints_and_unfinished_units_are_preserved(self):
        # Arrange: native collectで作ったcheckpointを含む同じ台帳。
        export = self.home / 'native-export.json'
        export.write_text((ROOT / 'meta/skill-maintenance/examples/export.json').read_text())
        native = self.cli('collect', '--input', export, '--target', self.target_file, '--repo', self.repo,
                          '--state', self.state, '--output', self.home / 'private/native-batches',
                          '--cutoff', '2026-01-03T00:00:00Z')
        self.assertEqual(0, native.returncode, native.stderr)
        before = json.loads(self.state.read_text())
        # Act
        batch = self.batch(self.intake())
        self.assertEqual(0, self.record(batch, 'deferred').returncode)
        after = json.loads(self.state.read_text())
        # Assert
        for key in ('units', 'sources', 'claims'):
            self.assertEqual(before[key], after[key])
        for key, value in before['batches'].items():
            self.assertEqual(value, after['batches'][key])

    def test_candidate_budget_does_not_limit_received_task_diagnosis(self):
        # 改善候補の評価予算と、受信実務の診断を分離する。
        self.document['requested_tasks'].append(dict(task_id='task-b', status='received'))
        self.document['reports'].append(report('task-b'))
        # Act
        batch = self.batch(self.intake())
        # Assert
        self.assertEqual(2, len(batch['cases']))
        self.assertEqual(2, batch['queued_cases'])
        self.target['budget']['max_cases'] = 0
        self.target_file.write_text(json.dumps(self.target))
        again = self.batch(self.intake())
        self.assertEqual('ready', again['status'])
        self.assertEqual(2, len(again['cases']))
        self.assertEqual(2, again['queued_cases'])

    def test_output_collisions_symlinks_and_state_lock_are_protected(self):
        # Arrange: 正常batchの後、保護pathとの衝突を試す。
        self.batch(self.intake())
        lock = self.state.with_name(self.state.name + '.lock')
        file_output = self.home / 'existing.json'
        file_output.write_text('protected')
        symlink = self.home / 'linked'
        symlink.symlink_to(self.output, target_is_directory=True)
        for path in (self.input, self.target_file, self.state, lock, lock / 'batches',
                     self.state.parent, self.repo / 'private', file_output, symlink):
            with self.subTest(path=path):
                # Act / Assert
                self.assert_rejected_without_mutation(output=path)
        self.assertEqual('protected', file_output.read_text())
        lock.mkdir()
        try:
            result = self.assert_rejected_without_mutation()
            self.assertIn('state is locked', result.stderr)
            self.assertTrue(lock.exists())
        finally:
            lock.rmdir()

    def test_target_profile_changes_and_oversize_input_are_rejected(self):
        # Arrange: 許可scopeと入力容量は有限契約。
        self.batch(self.intake())
        self.target['source_repos'] = ['other/app']
        self.target_file.write_text(json.dumps(self.target))
        # Act / Assert
        self.assert_rejected_without_mutation()
        self.target['source_repos'] = ['example/app']
        self.target_file.write_text(json.dumps(self.target))
        self.document['reports'][0]['claims'][0]['summary'] = 'x' * (8 * 1024 * 1024)
        self.assert_rejected_without_mutation()

    def test_duplicate_json_fields_are_rejected_before_mutation(self):
        # Arrange: JSON parserによる重複fieldの上書きで内容を隠せない。
        self.batch(self.intake())
        before = self.state.read_bytes()
        raw = json.dumps(self.document)
        self.input.write_text(raw.replace('"revision": 1', '"revision": 2, "revision": 1'))
        # Act
        result = self.cli('intake-retrospectives', '--input', self.input, '--target', self.target_file,
                          '--repo', self.repo, '--state', self.state, '--output', self.output)
        # Assert
        self.assertEqual(2, result.returncode)
        self.assertEqual(before, self.state.read_bytes())

    def test_repository_case_alias_cannot_make_output_public(self):
        # Arrange: 大小文字だけ違うrepo名が同じdirectoryを指すfilesystem。
        alias = self.repo.with_name(self.repo.name.swapcase())
        if not alias.exists():
            self.skipTest('case-sensitive filesystem')
        self.assertTrue(alias.samefile(self.repo))
        # Act / Assert
        self.assert_rejected_without_mutation(output=alias / 'batches')

    def test_case_alias_of_new_lock_is_rejected_without_leaving_lock_contents(self):
        # Arrange: lock作成前は存在しない大小文字aliasも、作成後は同じdirectory。
        case_probe = self.home / 'probe'
        case_probe.mkdir()
        if not case_probe.with_name('PROBE').exists():
            self.skipTest('case-sensitive filesystem')
        self.batch(self.intake())
        lock = self.state.with_name(self.state.name + '.lock')
        alias = lock.with_name(lock.name.swapcase())
        # Act / Assert
        self.assert_rejected_without_mutation(output=alias)
        self.assertFalse(lock.exists())

    def test_self_report_decisions_reject_invalid_intents_stale_and_modified_batches(self):
        # Arrange: nativeと同じrecord検証がself-report ledgerにも適用される。
        first = self.batch(self.intake())
        candidate = 'b' * 64
        before = self.state.read_bytes()
        # Act / Assert: evaluated前のapplyingは不可。
        invalid = self.record(first, 'applying', candidate_id=candidate, evidence=['opaque:intent'], operations=['edit'])
        self.assertEqual(2, invalid.returncode)
        self.assertEqual(before, self.state.read_bytes())
        saved_batch = self.batch_path
        fresh = self.batch(self.intake())
        before = self.state.read_bytes()
        current_batch = self.batch_path
        self.batch_path = saved_batch
        self.assertEqual(2, self.record(first, 'no-change').returncode)
        self.assertEqual(before, self.state.read_bytes())
        self.batch_path = current_batch
        modified = copy.deepcopy(fresh)
        modified['cases'][0]['units'][0]['claims'][0]['summary'] = 'Tampered claim.'
        current_batch.write_text(json.dumps(modified))
        self.assertEqual(2, self.record(modified, 'no-change').returncode)
        self.assertEqual(before, self.state.read_bytes())
        current_batch.write_text(json.dumps(fresh))
        self.assertEqual(0, self.record(fresh, 'evaluated', candidate_id=candidate, evidence=['opaque:evaluation']).returncode)
        intent = self.batch(self.intake())
        self.assertEqual(0, self.record(intent, 'applying', candidate_id=candidate,
                                       evidence=['opaque:intent'], operations=['edit']).returncode)
        reconciling = self.batch(self.intake())
        before = self.state.read_bytes()
        self.assertEqual(2, self.record(reconciling, 'failed', evidence=['opaque:unverified']).returncode)
        self.assertEqual(before, self.state.read_bytes())
        self.assertEqual(0, self.record(reconciling, 'failed', reconciled=True,
                                       evidence=['opaque:confirmed-not-applied']).returncode)
        self.assertNotIn(candidate, json.loads(self.state.read_text())['claims'])

    def test_private_report_input_inside_target_repo_is_rejected(self):
        # Arrange: 受信内容を公開checkout内から渡そうとする。
        self.input = self.repo / 'reports.json'
        # Act / Assert
        self.assert_rejected_without_mutation()

    def test_fifo_report_input_is_rejected_without_waiting_for_writer(self):
        # Arrange: サイズ0でも通常ファイルではない。
        os.mkfifo(self.input)
        # Act
        result = self.cli('intake-retrospectives', '--input', self.input, '--target', self.target_file,
                          '--repo', self.repo, '--state', self.state, '--output', self.output)
        # Assert: cli helperの短いtimeoutで待機を検出する。
        self.assertEqual(2, result.returncode)
        self.assertFalse(self.state.exists())
        self.assertFalse(self.output.exists())

    def test_unregistered_older_revision_does_not_reopen_closed_task(self):
        # Arrange: revision2を先に受信して終了したtask。
        self.document['reports'][0]['revision'] = 2
        batch = self.batch(self.intake())
        self.assertEqual(0, self.record(batch, 'no-change').returncode)
        self.document['reports'][0]['revision'] = 1
        # Act / Assert
        self.assert_rejected_without_mutation()

    def test_new_revision_cannot_replace_stable_report_identity(self):
        # Arrange
        self.batch(self.intake())
        self.document['reports'][0].update(revision=2, report_id='replacement-id')
        # Act / Assert
        self.assert_rejected_without_mutation()

    def test_missing_request_survives_empty_next_envelope_and_later_receipt(self):
        # Arrange: 元window内のtaskを取得できなかった。
        original = copy.deepcopy(self.document)
        self.document['reports'] = []
        self.document['requested_tasks'][0]['status'] = 'failed'
        self.batch(self.intake())
        self.document['requested_tasks'] = []
        # Act
        missing = self.batch(self.intake())
        # Assert: 空列挙で既知の欠落を消さない。
        self.assertEqual('awaiting-input', missing['status'])
        self.assertFalse(missing['report_receipt_complete'])
        self.assertFalse(missing['window_coverage_complete'])
        self.assertEqual(1, missing['unresolved_request_count'])
        self.assertEqual('task-a', missing['pending_requests'][0]['task_id'])
        self.document = original
        resolved = self.batch(self.intake())
        self.assertEqual(0, resolved['unresolved_request_count'])
        self.assertTrue(resolved['report_receipt_complete'])
        self.assertFalse(resolved['history_coverage_complete'])

    def test_current_source_binding_does_not_hide_other_source_same_root(self):
        # Arrange: source Bの正当なtaskと同名のsource A保守root。
        self.target['budget']['max_cases'] = 2
        self.target_file.write_text(json.dumps(self.target))
        self.document['source_id'] = 'source-b'
        self.document['reports'] = [report('shared-root')]
        self.document['requested_tasks'] = [dict(task_id='shared-root', status='received')]
        self.batch(self.intake())
        env = {**os.environ, 'CODEX_THREAD_ID': 'shared-root'}
        registered = self.cli('register-run', '--target', self.target_file, '--repo', self.repo,
                              '--state', self.state, '--source-id', 'source-a', '--root-id', 'shared-root', env=env)
        self.assertEqual(0, registered.returncode, registered.stderr)
        self.document['source_id'] = 'source-a'
        self.document['reports'] = [report('ordinary-root')]
        self.document['requested_tasks'] = [dict(task_id='ordinary-root', status='received')]
        # Act
        batch = self.batch(self.intake(env=env))
        # Assert
        self.assertIn(('source-b', 'shared-root'), [(case['source_id'], case['root_id']) for case in batch['cases']])

    def test_obsolete_count_limit_is_rejected_instead_of_silently_cutting_off_tasks(self):
        # Arrange / Act / Assert
        self.assert_rejected_without_mutation('--max-reports', '2')

    def test_case_budget_selects_oldest_instant_across_timezone_offsets(self):
        # Arrange: 表記上は03:30が02:00より後だが、実時間は先。
        self.document['reports'][0]['completed_at'] = '2026-01-02T03:30:00+02:00'
        later = report('task-b')
        later['completed_at'] = '2026-01-02T02:00:00Z'
        self.document['reports'].append(later)
        self.document['requested_tasks'].append(dict(task_id='task-b', status='received'))
        # Act
        batch = self.batch(self.intake())
        # Assert
        self.assertEqual('task-a', batch['cases'][0]['root_id'])
        self.assertEqual('2026-01-02T01:30:00Z', batch['cases'][0]['units'][0]['updated_at'])

    def test_known_older_snapshot_replays_without_reopening_closed_units(self):
        # Arrange: 保存済みの旧snapshotは新しいrevision追加後も再利用する。
        original = copy.deepcopy(self.document)
        first = self.batch(self.intake())
        self.assertEqual(0, self.record(first, 'deferred').returncode)
        self.document['reports'][0]['revision'] = 2
        second = self.batch(self.intake())
        self.assertEqual(0, self.record(second, 'no-change').returncode)
        self.document = original
        # Act
        replay = self.batch(self.intake())
        # Assert: 未登録の後着旧revisionとは区別する。
        self.assertEqual([], replay['cases'])
        self.assertEqual(2, len(json.loads(self.state.read_text())['retrospective_units']))
