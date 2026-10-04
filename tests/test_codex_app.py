import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'meta/skill-maintenance/scripts'))
import codex_app
import maintenance


START = '2026-01-02T00:00:00Z'
END = '2026-01-03T00:00:00Z'
T0 = 1767312000
T1 = 1767398400


def fixture():
    source = {'version': 1, 'source_id': 'fixture-app-index', 'device_id': 'fixture-device',
              'host_id': 'local', 'path_flavour': 'posix', 'exclude_roots': [],
              'repos': [{'id': 'example/app', 'cwd': '/fixture/app', 'information_scope': 'personal:example'}],
              'max_threads': 10, 'max_turns': 40}
    row = {'id': 'work', 'host_id': 'local', 'cwd': '/fixture/app', 'status': 'notLoaded', 'updated_at': T1-1}
    snapshot = {'version': 1, 'device_id': 'fixture-device', 'host_id': 'local',
                'source_identity': {'source_id': source['source_id'], 'selection': codex_app.selection(source)},
                'window': {'start': START, 'end': END},
                'capabilities': {'list_threads': True, 'read_thread': True, 'list_archived_threads': True},
                'unavailable_hosts': [], 'unavailable_sources': [],
                'recent': {'limit': 50, 'before': [row], 'after': [copy.deepcopy(row)]},
                'pinned': {'before': [], 'after': []},
                'archive': {'complete': True, 'before': [], 'after': []},
                'threads': [{'thread': copy.deepcopy(row), 'pages': [{'cursor': None,
                    'page': {'order': 'newest_first', 'limit': 10, 'hasMore': False, 'nextCursor': None},
                    'turns': [{'id': 'turn', 'status': 'completed', 'startedAt': T0+1, 'completedAt': T1-1,
                               'content': {'request': 'Fix a link.', 'expected': 'Fix a link.',
                                           'observed': 'Agent reported the link was fixed.'}}]}]}]}
    return source, snapshot


class AppCaptureTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.repo = self.home / 'repo'; self.repo.mkdir()
        self.source, self.snapshot = fixture()
        self.target = json.loads((ROOT / 'meta/skill-maintenance/examples/target.json').read_text())
        self.target['budget']['max_cases'] = 10
        self.args = argparse.Namespace(repo=self.repo, source=self.home/'source.json', target=self.home/'target.json',
            state=self.home/'private/state.json', output=self.home/'private/batches', snapshot=self.home/'private/capture.json',
            since=START, cutoff=END, current_root='maintenance', exclude_root=[])
        self.args.snapshot.parent.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def run_capture(self):
        for path, data in ((self.args.source, self.source), (self.args.target, self.target),
                           (self.args.snapshot, self.snapshot)):
            path.write_text(json.dumps(data))
        result = maintenance.import_app(self.args)
        self.batch_path = Path(result['batch'])
        return json.loads(self.batch_path.read_text())

    def record(self, batch, status):
        decision = self.home/'decision.json'
        decision.write_text(json.dumps({'case_id': batch['cases'][0]['id'], 'status': status, 'reason': 'Synthetic evidence.'}))
        return maintenance.record(argparse.Namespace(repo=self.repo, state=self.args.state,
                                                     batch=self.batch_path, result=decision))

    def row(self):
        return self.snapshot['recent']['before'][0]

    def turn(self):
        return self.snapshot['threads'][0]['pages'][0]['turns'][0]

    def synchronize_row(self):
        self.snapshot['recent']['after'][0] = copy.deepcopy(self.row())
        self.snapshot['threads'][0]['thread'] = copy.deepcopy(self.row())

    def test_replay_deduplicates_and_record_is_idempotent(self):
        first = self.run_capture()
        self.assertFalse(first['coverage_notes']['outcomes_independently_verified'])
        again = self.run_capture()
        self.assertEqual(first['cases'][0]['id'], again['cases'][0]['id'])
        self.assertEqual(1, len(json.loads(self.args.state.read_text())['units']))
        self.assertEqual('no-change', self.record(again, 'no-change')['status'])
        self.assertEqual('already-recorded', self.record(again, 'no-change')['status'])
        self.assertEqual('no-new-input', self.run_capture()['status'])
        self.assertEqual([], list(self.repo.iterdir()))

    def test_failed_analysis_remains_pending(self):
        first = self.run_capture()
        self.record(first, 'failed')
        self.assertEqual('failed', self.run_capture()['cases'][0]['units'][0]['status'])

    def test_no_body_required_does_not_probe_an_unrelated_thread(self):
        self.snapshot['recent'].update(before=[], after=[])
        self.snapshot['threads'] = []
        self.snapshot['capabilities']['read_thread'] = 'not-needed'
        self.assertEqual('no-new-input', self.run_capture()['status'])

    def test_unconfirmed_read_cannot_import_existing_threads(self):
        self.snapshot['capabilities']['read_thread'] = 'not-needed'
        with self.assertRaisesRegex(ValueError, 'unconfirmed'):
            self.run_capture()

    def test_nullable_cwd_outside_allowlist_is_ignored(self):
        row = {**self.row(), 'id': 'projectless', 'cwd': None}
        self.snapshot['recent']['before'].append(row)
        self.snapshot['recent']['after'].append(copy.deepcopy(row))
        self.assertEqual(1, len(self.run_capture()['cases']))

    def test_snapshot_in_repository_is_blocked(self):
        self.args.snapshot = self.repo/'capture.json'
        with self.assertRaisesRegex(ValueError, 'outside target repository'):
            self.run_capture()

    def test_missing_capability_does_not_advance_existing_state(self):
        self.run_capture(); original = self.args.state.read_bytes()
        self.snapshot['capabilities']['read_thread'] = False
        with self.assertRaisesRegex(ValueError, 'capabilities'):
            self.run_capture()
        self.assertEqual(original, self.args.state.read_bytes())

    def test_device_identity_cannot_change_at_same_source_id(self):
        self.run_capture()
        self.source['device_id'] = self.snapshot['device_id'] = 'another-device'
        with self.assertRaisesRegex(ValueError, 'selection changed'):
            self.run_capture()

    def test_scope_change_cannot_reuse_state(self):
        self.run_capture()
        self.source['repos'].append({'id': 'example/app', 'cwd': '/fixture/new', 'information_scope': 'personal:example'})
        with self.assertRaisesRegex(ValueError, 'selection changed'):
            self.run_capture()

    def test_other_organization_is_blocked(self):
        self.source['repos'][0]['information_scope'] = 'organization:other'
        with self.assertRaisesRegex(ValueError, 'scope mismatch'):
            self.run_capture()
        self.assertFalse(self.args.state.exists())

    def test_incomplete_archive_is_blocked(self):
        self.snapshot['archive']['complete'] = False
        with self.assertRaisesRegex(ValueError, 'archive pagination'):
            self.run_capture()

    def test_recent_limit_inside_window_is_blocked(self):
        rows = [{**self.row(), 'id': str(i)} for i in range(50)]
        self.snapshot['recent'].update(before=rows, after=copy.deepcopy(rows))
        with self.assertRaisesRegex(ValueError, 'limit cuts'):
            self.run_capture()

    def test_changed_index_is_blocked(self):
        self.snapshot['recent']['after'][0]['updated_at'] += 1
        with self.assertRaisesRegex(ValueError, 'index changed'):
            self.run_capture()

    def test_unavailable_source_is_blocked(self):
        self.snapshot['unavailable_hosts'] = ['unavailable-device']
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            self.run_capture()

    def test_missing_thread_and_extra_host_capture_are_blocked(self):
        self.snapshot['threads'] = []
        with self.assertRaisesRegex(ValueError, 'captures missing'):
            self.run_capture()

    def test_active_thread_is_not_read_and_is_carried_until_finished(self):
        self.row()['status'] = 'active'; self.synchronize_row()
        saved = self.snapshot['threads']; self.snapshot['threads'] = []
        batch = self.run_capture()
        self.assertEqual('awaiting-input', batch['status'])
        self.assertEqual(1, batch['unfinished_units'])
        self.row()['status'] = 'notLoaded'; self.snapshot['threads'] = saved; self.synchronize_row()
        batch = self.run_capture()
        self.assertEqual(0, batch['unfinished_units'])
        self.assertEqual(1, len(batch['cases']))

    def test_missing_known_unfinished_thread_is_blocked(self):
        self.row()['status'] = 'active'; self.synchronize_row(); self.snapshot['threads'] = []
        self.run_capture()
        self.snapshot['recent'].update(before=[], after=[])
        with self.assertRaisesRegex(ValueError, 'omitted a known unfinished thread'):
            self.run_capture()

    def test_explicit_exclusion_resolves_previously_unfinished_root(self):
        self.row()['status'] = 'active'; self.synchronize_row(); self.snapshot['threads'] = []
        self.run_capture()
        self.args.exclude_root = ['work']
        result = self.run_capture()
        self.assertEqual('no-new-input', result['status'])
        self.assertEqual(0, result['unfinished_units'])

    def test_completing_copied_unfinished_turn_resolves_without_duplicate(self):
        row = {**self.row(), 'id': 'work-copy'}
        self.snapshot['recent']['before'].append(row)
        self.snapshot['recent']['after'].append(copy.deepcopy(row))
        clone = copy.deepcopy(self.snapshot['threads'][0]); clone['thread'] = copy.deepcopy(row)
        original = copy.deepcopy(clone['pages'][0]['turns'][0])
        clone['pages'][0]['turns'][0].update(status='inProgress', completedAt=None)
        clone['pages'][0]['turns'][0].pop('content')
        self.snapshot['threads'].append(clone)
        self.assertEqual(1, self.run_capture()['unfinished_units'])
        clone['pages'][0]['turns'][0] = original
        self.assertEqual(0, self.run_capture()['unfinished_units'])
        self.assertEqual(1, len(json.loads(self.args.state.read_text())['units']))
        self.assertEqual(0, self.run_capture()['unfinished_units'])

    def test_unfinished_turn_is_carried_without_content(self):
        turn = self.turn(); saved = copy.deepcopy(turn)
        turn.update(status='inProgress', completedAt=None); del turn['content']
        self.assertEqual('awaiting-input', self.run_capture()['status'])
        self.snapshot['threads'][0]['pages'][0]['turns'][0] = saved
        self.assertEqual(0, self.run_capture()['unfinished_units'])

    def test_missing_known_unfinished_turn_is_blocked(self):
        self.turn().update(status='inProgress', completedAt=None); self.turn().pop('content')
        self.run_capture()
        self.snapshot['threads'][0]['pages'][0]['turns'] = []
        with self.assertRaisesRegex(ValueError, 'omitted a known unfinished turn'):
            self.run_capture()

    def test_period_boundary_includes_end_and_start_and_skips_older(self):
        turns = self.snapshot['threads'][0]['pages'][0]['turns']
        turns[0].update(startedAt=T1, completedAt=T1)
        at_start = copy.deepcopy(turns[0]); at_start.update(id='start', startedAt=T0, completedAt=T0)
        old = {'id': 'old', 'status': 'completed', 'startedAt': T0-2, 'completedAt': T0-1}
        turns.extend([at_start, old])
        self.assertEqual(2, len(self.run_capture()['cases'][0]['units']))

    def test_old_content_is_rejected_instead_of_saved(self):
        self.turn().update(startedAt=T0-2, completedAt=T0-1)
        with self.assertRaisesRegex(ValueError, 'out-of-window'):
            self.run_capture()

    def test_missing_final_is_not_success(self):
        self.turn()['content']['observed'] = ''
        with self.assertRaisesRegex(ValueError, 'do not invent success'):
            self.run_capture()

    def test_pagination_must_reach_boundary_or_end(self):
        self.snapshot['threads'][0]['pages'][0]['page'].update(hasMore=True, nextCursor='next')
        with self.assertRaisesRegex(ValueError, 'pages stop inside window'):
            self.run_capture()

    def test_cursor_chain_is_checked(self):
        page = self.snapshot['threads'][0]['pages'][0]
        page['cursor'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'cursor chain'):
            self.run_capture()

    def test_old_boundary_allows_stopping_but_reports_unseen_unfinished(self):
        page = self.snapshot['threads'][0]['pages'][0]
        page['page'].update(hasMore=True, nextCursor='next')
        page['turns'].append({'id': 'older', 'status': 'completed', 'startedAt': T0-2, 'completedAt': T0-1})
        self.assertEqual('ready', self.run_capture()['status'])

    def test_self_exclusion_never_needs_body(self):
        self.args.current_root = 'work'; self.snapshot['threads'] = []
        result = self.run_capture()
        self.assertEqual('no-new-input', result['status'])
        self.assertEqual(1, result['excluded_sessions'])

    def test_archived_and_pinned_threads_are_included(self):
        row = self.row()
        self.snapshot['recent'].update(before=[], after=[])
        self.snapshot['pinned'].update(before=[row], after=[copy.deepcopy(row)])
        self.assertEqual(1, len(self.run_capture()['cases']))

    def test_copied_turn_deduplicates_within_capture_and_across_runs(self):
        row = {**self.row(), 'id': 'work-copy'}
        self.snapshot['recent']['before'].append(row)
        self.snapshot['recent']['after'].append(copy.deepcopy(row))
        clone = copy.deepcopy(self.snapshot['threads'][0]); clone['thread'] = copy.deepcopy(row)
        self.snapshot['threads'].append(clone)
        self.assertEqual(1, sum(len(c['units']) for c in self.run_capture()['cases']))
        self.snapshot['recent'].update(before=[row], after=[copy.deepcopy(row)])
        self.snapshot['threads'] = [clone]
        self.assertEqual(1, len(json.loads(self.args.state.read_text())['units']))
        self.assertEqual(1, sum(len(c['units']) for c in self.run_capture()['cases']))

    def test_conflicting_copied_turn_is_blocked(self):
        self.run_capture()
        self.row()['id'] = 'copy'; self.synchronize_row()
        self.turn()['content']['observed'] = 'Different report.'
        with self.assertRaisesRegex(ValueError, 'conflicting facts'):
            self.run_capture()

    def test_checkpoint_gap_requires_wider_capture_and_never_silently_expands(self):
        self.run_capture(); original = self.args.state.read_bytes()
        self.args.since = '2026-01-04T00:00:00Z'; self.args.cutoff = '2026-01-05T00:00:00Z'
        self.snapshot['window'] = {'start': self.args.since, 'end': self.args.cutoff}
        with self.assertRaisesRegex(ValueError, 'checkpoint gap'):
            self.run_capture()
        self.assertEqual(original, self.args.state.read_bytes())

    def test_thread_budget_is_not_partial_success(self):
        self.source['max_turns'] = 0
        with self.assertRaisesRegex(ValueError, 'budget'):
            self.run_capture()

    def test_native_minimizer_discards_commands_and_old_messages(self):
        row = self.row()
        native_row = {'id': row['id'], 'hostId': row['host_id'], 'cwd': row['cwd'],
                      'updatedAt': row['updated_at'], 'status': row['status'], 'title': 'PRIVATE-TITLE'}
        index = {'threads': [native_row], 'pinnedThreads': [], 'unavailableHosts': [], 'unavailableSources': []}
        index['threads'].append({'id': 'other-chat', 'kind': 'chatgpt', 'status': 'idle', 'updatedAt': T0})
        turn = copy.deepcopy(self.turn()); turn.pop('content')
        turn['items'] = [{'type': 'userMessage', 'content': [{'type': 'text', 'text': 'Fix a link.'}]},
                         {'type': 'agentMessage', 'phase': 'final_answer', 'text': 'Fixed.'},
                         {'type': 'commandExecution', 'command': 'PRIVATE-COMMAND-DO-NOT-SAVE'}]
        old = copy.deepcopy(turn); old.update(id='old', startedAt=T0-2, completedAt=T0-1)
        old['items'][0]['content'][0]['text'] = 'PRIVATE-OLD-MESSAGE'
        bundle = {'capabilities': self.snapshot['capabilities'], 'index_before': index, 'index_after': index,
                  'source_identity': self.snapshot['source_identity'], 'index_limit': 50,
                  'archive_before': [{'cursor': None, 'result': {'threads': [], 'nextCursor': None}}],
                  'archive_after': [{'cursor': None, 'result': {'threads': [], 'nextCursor': None}}],
                  'reads': [{'pages': [{'cursor': None, 'params': {'hostId':'local', 'threadId':'work',
                            'includeOutputs':False, 'turnLimit':10, 'maxOutputCharsPerItem':4000}, 'result': {'thread': native_row,
                            'page': self.snapshot['threads'][0]['pages'][0]['page'], 'turns': [turn, old]}}]}]}
        minimized = codex_app.minimize_native(bundle, self.source, START, END)
        encoded = json.dumps(minimized)
        self.assertNotIn('PRIVATE-', encoded)
        self.assertIn('not independently verified', encoded)
        self.snapshot = minimized
        self.assertEqual('ready', self.run_capture()['status'])

    def test_capture_cannot_be_relabelled_to_another_scope_or_source(self):
        self.source['source_id'] = 'another-source'
        with self.assertRaisesRegex(ValueError, 'capture source/scope mismatch'):
            self.run_capture()

    def test_capture_cannot_be_relabelled_in_a_fresh_organization_state(self):
        self.source['repos'][0]['information_scope'] = 'organization:example'
        self.target.update(manager='organization', information_scope='organization:example')
        with self.assertRaisesRegex(ValueError, 'capture source/scope mismatch'):
            self.run_capture()

    def test_smaller_effective_recent_limit_cannot_hide_missing_threads(self):
        self.snapshot['recent']['limit'] = 1
        with self.assertRaisesRegex(ValueError, 'limit cuts'):
            self.run_capture()

    def test_known_secret_in_minimized_capture_is_blocked(self):
        self.turn()['content']['request'] = 'api_key=synthetic-not-a-real-secret'
        with self.assertRaisesRegex(ValueError, 'sensitive app turn'):
            self.run_capture()


class NativeCompletenessTest(unittest.TestCase):
    def setUp(self):
        self.source, snapshot = fixture()
        row = snapshot['recent']['before'][0]
        native = {'id':'work','hostId':'local','cwd':row['cwd'],'updatedAt':row['updated_at'],'status':'notLoaded'}
        index = {'threads':[native],'pinnedThreads':[],'unavailableHosts':[],'unavailableSources':[]}
        self.turn = {'id':'turn','status':'completed','startedAt':T0+1,'completedAt':T1-1,
                     'items':[{'type':'userMessage','content':[{'type':'text','text':'Synthetic request'}]},
                              {'type':'agentMessage','phase':'final_answer','text':'Synthetic final.'}]}
        self.bundle = {'source_identity':snapshot['source_identity'],'index_limit':50,
            'capabilities':snapshot['capabilities'],'index_before':index,'index_after':index,
            'archive_before':[{'cursor':None,'result':{'threads':[],'nextCursor':None}}],
            'archive_after':[{'cursor':None,'result':{'threads':[],'nextCursor':None}}],
            'reads':[{'pages':[{'cursor':None,'params':{'hostId':'local','threadId':'work','includeOutputs':False,
                         'turnLimit':10,'maxOutputCharsPerItem':4000},'result':{'thread':native,
                         'page':snapshot['threads'][0]['pages'][0]['page'],'turns':[self.turn]}}]}]}

    def test_native_trace_evidence_is_rejected_instead_of_silently_discarded(self):
        self.bundle['reads'][0]['pages'][0]['result']['turns'][0]['evidence'] = {
            'version': 1, 'complete': True, 'truncated': False, 'events': []}
        with self.assertRaisesRegex(ValueError, 'report-only'):
            codex_app.minimize_native(self.bundle, self.source, START, END)

    def test_native_blank_final_is_rejected(self):
        self.turn['items'][1]['text'] = '  '
        with self.assertRaisesRegex(ValueError, 'empty request/final'):
            codex_app.minimize_native(self.bundle,self.source,START,END)

    def test_native_non_text_request_is_rejected(self):
        self.turn['items'][0]['content'].append({'type':'image','url':'synthetic'})
        with self.assertRaisesRegex(ValueError, 'non-text request'):
            codex_app.minimize_native(self.bundle,self.source,START,END)

    def test_native_limit_sized_final_is_rejected(self):
        self.turn['items'][1]['text'] = 'x'*4000
        with self.assertRaisesRegex(ValueError, 'limit-sized'):
            codex_app.minimize_native(self.bundle,self.source,START,END)

    def test_native_truncation_metadata_is_rejected(self):
        self.turn['items'][1]['truncated'] = True
        with self.assertRaisesRegex(ValueError, 'truncated'):
            codex_app.minimize_native(self.bundle,self.source,START,END)

    def test_native_secret_is_rejected_before_capture(self):
        self.turn['items'][1]['text'] = 'api_key=synthetic-not-a-real-secret'
        with self.assertRaisesRegex(ValueError, 'sensitive app turn'):
            codex_app.minimize_native(self.bundle,self.source,START,END)

    def test_native_missing_request_parameters_is_rejected(self):
        self.bundle['reads'][0]['pages'][0]['params']['threadId'] = 'other'
        with self.assertRaisesRegex(ValueError, 'provenance mismatch'):
            codex_app.minimize_native(self.bundle,self.source,START,END)

    def test_native_preserves_actual_index_limit(self):
        self.bundle['index_limit'] = 10
        result = codex_app.minimize_native(self.bundle,self.source,START,END)
        self.assertEqual(10,result['recent']['limit'])

    def test_native_discards_foreign_index_rows_but_retains_saturation_boundary(self):
        foreign = {'id':'unrelated-private-id','hostId':'other-host','cwd':'/private/foreign',
                   'updatedAt':T1-2,'status':'notLoaded'}
        for index in ('index_before','index_after'):
            self.bundle[index] = copy.deepcopy(self.bundle[index])
            self.bundle[index]['threads'].append(foreign)
            self.bundle[index]['pinnedThreads'].append(foreign)
        for archive in ('archive_before','archive_after'):
            self.bundle[archive][0]['result']['threads'].append(foreign)
        self.bundle['index_limit'] = 2
        result = codex_app.minimize_native(self.bundle,self.source,START,END)
        self.assertNotIn('unrelated-private-id',json.dumps(result))
        self.assertNotIn('/private/foreign',json.dumps(result))
        self.assertEqual({'count':2,'oldest_updated_at':T1-2},result['recent']['scan']['before'])
        target=json.loads((ROOT/'meta/skill-maintenance/examples/target.json').read_text())
        with self.assertRaisesRegex(ValueError,'limit cuts through window'):
            codex_app.export(result,self.source,target,START,END,{},{})

    def test_native_outside_scope_read_stops_before_retaining_content(self):
        self.bundle['reads'][0]['pages'][0]['result']['thread']['cwd'] = '/foreign/repo'
        with self.assertRaisesRegex(ValueError,'outside source scope'):
            codex_app.minimize_native(self.bundle,self.source,START,END)


if __name__ == '__main__':
    unittest.main()
