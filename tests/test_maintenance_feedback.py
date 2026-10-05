"""Self feedback is native failure/user input, never model self assessment."""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from tests import test_codex_reader as reader_tests
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'meta/skill-maintenance/scripts'))
import codex_index as INDEX
import codex_reader as READER
import maintenance as COLLECT
from common import validate_feedback
from tests import test_reader_regressions as fixture_tests


class FeedbackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.private = Path(self.tmp.name)
        self.fixture = fixture_tests.ReaderRegressions()
        self.window = self.fixture.selection()['window']
        self.start = int(READER.instant(self.window['since']).timestamp())
        self.target = json.loads((ROOT/'meta/skill-maintenance/examples/target.json').read_text())
        self.target['source_repos'] = ['example/project']
        self.target_path = self.private/'target.json'
        self.target_path.write_text(json.dumps(self.target))
        self.state_path = self.private/'state.json'
        self.register_args = argparse.Namespace(repo=ROOT, state=self.state_path, target=self.target_path,
                                               source_id='synthetic', root_id='root')
        with patch.dict(os.environ, {}, clear=True):
            COLLECT.register_run(self.register_args)
        self.ledger = json.loads(self.state_path.read_text())
        self.source = self.fixture.source()
        self.turns = [self.fixture.turn('initial', self.start+1), self.fixture.turn('later', self.start+2)]
        self.items = {
            'initial': [dict(type='userMessage'), dict(type='agentMessage'),
                        dict(id='fail', type='commandExecution', status='completed', exitCode=1,
                             command='private argument', aggregatedOutput='error: invalid option')],
            'later': [dict(id='user', type='userMessage', content=[dict(type='text', text='The reported check did not run.')]),
                      dict(type='agentMessage'), dict(type='reasoning'),
                      dict(type='collabAgentToolCall'), dict(type='webSearch'),
                      dict(id='pass', type='commandExecution', status='completed', exitCode=0,
                           command='test', aggregatedOutput='All checks passed')]
        }
        owner = self
        class Proxy:
            calls = []
            def call(self, method, params):
                self.calls.append((method, params.copy()))
                if method == 'thread/list':
                    return dict(data=[] if params['archived'] else [owner.fixture.metadata('root', owner.start+10)], nextCursor=None)
                if method == 'thread/turns/list':
                    return dict(data=[owner.turns[0]] if params['sortDirection']=='asc' else list(reversed(owner.turns)), nextCursor=None)
                if method == 'thread/read':
                    return dict(thread=reader_tests.ReaderTest().metadata(sessionId='root', gitInfo={'originUrl':'https://github.com/example/project.git'}, status={'type':'idle'}))
                return dict(data=[dict(turnId=params['turnId'], item=i) for i in owner.items[params['turnId']]], nextCursor=None)
        self.proxy = Proxy()

    def export(self):
        with patch.dict(os.environ, {'CODEX_THREAD_ID':'current'}, clear=True), patch.object(INDEX.sys, 'platform', 'darwin'):
            selection, _ = INDEX.index(self.proxy, self.source, self.ledger, **self.window,
                codex_home=str(Path.home()/'.codex'))
            self.assertTrue(selection['coverage_complete'])
            selection, _ = READER.select_turns(self.proxy, selection)
            return READER.read_completed(self.proxy, selection, self.ledger)[0]

    def collect(self, export):
        path = self.private/'export.json'
        path.write_text(json.dumps(export))
        result = COLLECT.collect(argparse.Namespace(repo=ROOT, state=self.state_path, target=self.target_path,
            input=path, output=self.private/'batches', since=self.window['since'], cutoff=self.window['cutoff'],
            hours=24, exclude_root=[], new_evidence_only=True))
        self.ledger = json.loads(self.state_path.read_text())
        return json.loads(Path(result['batch']).read_text())

    def test_registration_is_idempotent_and_survives_acquisition_failure_without_checkpoint(self):
        before = self.state_path.read_bytes()
        with patch.dict(os.environ, {}, clear=True):
            COLLECT.register_run(self.register_args)
        self.assertEqual(before, self.state_path.read_bytes())
        self.assertEqual({}, self.ledger['sources'])
        self.assertEqual({}, self.ledger['units'])
        with patch.dict(os.environ, {'CODEX_THREAD_ID':'wrong'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'this maintenance run'):
                COLLECT.register_run(self.register_args)
        self.assertEqual(before, self.state_path.read_bytes())

    def test_official_reader_collect_replay_keeps_failures_and_later_user_input_only(self):
        export = self.export()
        units = export['sessions'][0]['units']
        self.assertEqual('maintenance-feedback', export['sessions'][0]['kind'])
        self.assertEqual(['user-input'], [e['kind'] for e in units[0]['evidence']['events']])
        self.assertEqual(['tool-call','tool-result'], [e['kind'] for e in units[1]['evidence']['events']])
        self.assertEqual('error', units[1]['evidence']['events'][1]['status'])
        self.assertNotIn('All checks passed', str(export))
        self.assertNotIn('private argument', str(export))
        first = self.collect(export)
        keys = set(self.ledger['units'])
        self.assertEqual(1, len(first['cases']))
        self.assertEqual(2, first['evidence_quality']['maintenance_feedback_units'])
        self.assertTrue(all(u['facts']['maintenance_feedback'] for u in self.ledger['units'].values()))
        second = self.collect(export)
        self.assertEqual(keys, set(self.ledger['units']))
        self.assertEqual(first['cases'], second['cases'])
        # Reuse stable facts rather than reread tool/user bodies.
        calls = len([c for c in self.proxy.calls if c[0]=='thread/items/list'])
        self.export()
        self.assertEqual(calls, len([c for c in self.proxy.calls if c[0]=='thread/items/list']))

    def test_native_success_with_http_text_does_not_become_failure_feedback(self):
        for output in ('PASS: unauthorized fixture returned expected HTTP 403', 'HTTP/1.1 403 Forbidden'):
            self.items['initial'].append(dict(id='http', type='commandExecution', status='completed', exitCode=0,
                command='synthetic regression', aggregatedOutput=output))
            events = self.export()['sessions'][0]['units'][1]['evidence']['events']
            self.assertEqual(['fail','fail:result'],[e['id'] for e in events])
            self.assertEqual('error',events[1]['status'])
            self.items['initial'].pop()

    def test_resumed_current_root_holds_saved_feedback_then_resumes_next_run(self):
        self.collect(self.export())
        snapshot = copy.deepcopy(self.ledger['units'])
        with patch.dict(os.environ, {'CODEX_THREAD_ID':'root'},clear=True),patch.object(INDEX.sys,'platform','darwin'):
            selection,_ = INDEX.index(self.proxy,self.source,self.ledger,**self.window,
                codex_home=str(Path.home()/'.codex'))
            self.assertEqual([],selection['threads'])
            selection['turn_selection_complete'] = True
            export,_ = READER.read_completed(self.proxy,selection,self.ledger)
            batch = self.collect(export)
        self.assertEqual([],batch['cases'])
        self.assertEqual('awaiting-input',batch['status'])
        self.assertEqual(2,batch['current_root_held_units'])
        self.assertEqual(snapshot,self.ledger['units'])
        self.assertNotIn('root',self.ledger['sources']['synthetic']['feedback_excluded_roots'])
        self.assertEqual(1,len(self.collect(self.export())['cases']))

    def test_collecting_other_source_keeps_current_registered_feedback_held(self):
        # Arrange: Aの保存feedbackがある現在runで、Bの取得結果を処理する。
        export = self.export()
        self.collect(export)
        before = copy.deepcopy(self.ledger['units'])
        other = copy.deepcopy(export)
        other['source_id'] = 'other-source'
        other['sessions'] = []
        # Act
        with patch.dict(os.environ, {'CODEX_THREAD_ID': 'root'}, clear=True):
            batch = self.collect(other)
        # Assert: 取得中source Bを現在runのsource Aと取り違えない。
        self.assertEqual([], batch['cases'])
        self.assertEqual(2, batch['current_root_held_units'])
        self.assertEqual(before, self.ledger['units'])
        self.assertEqual(1, len(self.collect(export)['cases']))

    def test_current_root_preserves_unfinished_feedback_during_empty_export(self):
        self.turns = [dict(id='initial',status='inProgress',startedAt=self.start,completedAt=None,items=[],itemsView='notLoaded')]
        self.collect(self.export())
        pending = copy.deepcopy(self.ledger['sources']['synthetic']['deferred'])
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'root'},clear=True),patch.object(INDEX.sys,'platform','darwin'):
            selection,_ = INDEX.index(self.proxy,self.source,self.ledger,**self.window,
                codex_home=str(Path.home()/'.codex'))
            selection['turn_selection_complete'] = True
            export,_ = READER.read_completed(self.proxy,selection,self.ledger)
            self.collect(export)
        self.assertEqual(pending,self.ledger['sources']['synthetic']['deferred'])

    def test_initial_prompt_and_self_success_produce_no_case(self):
        self.turns = self.turns[:1]
        self.items['initial'] = [dict(type='userMessage'), dict(type='agentMessage'),
                                dict(type='reasoning'), dict(type='collabAgentToolCall')]
        batch = self.collect(self.export())
        self.assertEqual([], batch['cases'])
        self.assertEqual({}, self.ledger['units'])
        self.assertEqual('no-new-input', batch['status'])

    def test_current_and_explicitly_excluded_registered_roots_are_never_read(self):
        for current, explicit in [('root', []), ('current', ['root'])]:
            self.source['exclude_roots'] = explicit
            with patch.dict(os.environ, {'CODEX_THREAD_ID':current}, clear=True), patch.object(INDEX.sys, 'platform', 'darwin'):
                selected, _ = INDEX.index(self.proxy,self.source,self.ledger,**self.window,
                    codex_home=str(Path.home()/'.codex'))
            self.assertEqual([], selected['threads'])
        self.assertFalse(any(m=='thread/items/list' for m,_ in self.proxy.calls))

    def test_explicit_exclusion_holds_saved_feedback_candidates_and_persists(self):
        self.collect(self.export())
        self.source['exclude_roots'] = ['root']
        batch = self.collect(self.export())
        self.assertEqual([], batch['cases'])
        self.assertEqual(['root'], self.ledger['sources']['synthetic']['feedback_excluded_roots'])
        self.source['exclude_roots'] = []
        self.assertEqual([], self.collect(self.export())['cases'])

    def test_evaluation_and_unclassified_exclusions_are_not_opted_into_feedback(self):
        self.ledger['maintenance_roots'] = {}
        self.source['exclude_roots'] = ['root']
        with patch.dict(os.environ, {}, clear=True), patch.object(INDEX.sys, 'platform', 'darwin'):
            selected, _ = INDEX.index(self.proxy,self.source,self.ledger,**self.window,
                codex_home=str(Path.home()/'.codex'))
        self.assertEqual([], selected['threads'])

    def test_out_of_scope_source_is_held_before_body_acquisition(self):
        self.source['repos'][0]['id'] = 'other/project'
        with patch.dict(os.environ, {'CODEX_THREAD_ID':'current'}, clear=True), patch.object(INDEX.sys,'platform','darwin'):
            selected, counts = INDEX.index(self.proxy,self.source,self.ledger,**self.window,
                codex_home=str(Path.home()/'.codex'))
        self.assertFalse(selected['coverage_complete'])
        self.assertEqual([], selected['threads'])
        self.assertIn('repository_information_scope_unregistered', counts['held_reasons'])
        self.assertFalse(any(m=='thread/items/list' for m,_ in self.proxy.calls))

    def test_collector_rejects_unregistered_feedback_without_advancing_state(self):
        export = self.export()
        self.ledger['maintenance_roots'] = {}
        self.state_path.write_text(json.dumps(self.ledger))
        before = self.state_path.read_bytes()
        with self.assertRaisesRegex(ValueError,'unregistered maintenance feedback'):
            self.collect(export)
        self.assertEqual(before, self.state_path.read_bytes())

    def test_feedback_rejects_success_and_self_correction_as_support(self):
        export = self.export()
        evidence = export['sessions'][0]['units'][1]['evidence']
        evidence['events'][1]['status'] = 'success'
        with self.assertRaisesRegex(ValueError,'success is not'):
            validate_feedback(evidence)
        evidence['events'] = [dict(id='self',kind='correction',summary='This proposal improved scores.')]
        with self.assertRaisesRegex(ValueError,'self-generated'):
            validate_feedback(evidence)

    def test_child_work_under_feedback_root_cannot_reenter_as_independent_support(self):
        export = self.export()
        child = copy.deepcopy(export['sessions'][0])
        child.update(id='child', parent_id='root',kind='work')
        export['sessions'].append(child)
        batch = self.collect(export)
        self.assertEqual(1,batch['excluded_sessions'])
        self.assertEqual(2,len(self.ledger['units']))

    def test_missing_diagnostic_and_sensitive_user_input_block_checkpoint(self):
        before = self.state_path.read_bytes()
        self.items['initial'][2]['aggregatedOutput'] = ''
        with self.assertRaisesRegex(ValueError,'incomplete item evidence'):
            self.export()
        self.assertEqual(before,self.state_path.read_bytes())
        self.items['initial'][2]['aggregatedOutput'] = 'error: invalid option'
        self.items['later'][0]['content'][0]['text'] = 'password: synthetic-secret'
        with self.assertRaisesRegex(ValueError,'user input cannot'):
            self.export()
        self.assertEqual(before,self.state_path.read_bytes())

    def test_pending_feedback_finishing_without_failures_resolves_without_a_case(self):
        self.turns = [dict(id='initial',status='inProgress',startedAt=self.start,completedAt=None,items=[],itemsView='notLoaded')]
        self.collect(self.export())
        self.assertEqual(1,len(self.ledger['sources']['synthetic']['deferred']))
        self.turns = [self.fixture.turn('initial', self.start+10)]
        self.items['initial'] = [dict(type='agentMessage')]
        batch = self.collect(self.export())
        self.assertEqual({},self.ledger['sources']['synthetic']['deferred'])
        self.assertEqual([],batch['cases'])

    def test_feedback_failed_and_interrupted_native_status_needs_no_model_report(self):
        for status in ('failed', 'interrupted'):
            self.turns = [self.fixture.turn('initial',self.start+10,status)]
            self.items['initial'] = [dict(type='agentMessage')]
            events = self.export()['sessions'][0]['units'][0]['evidence']['events']
            self.assertEqual(['error'],[e['kind'] for e in events])
            self.assertIn(status,events[0]['summary'])

    def test_active_thread_and_missing_known_feedback_turn_are_held(self):
        export = self.export()
        # A resumed active thread is stopped before any item body read.
        original_call = self.proxy.call
        def active(method, params):
            if method == 'thread/read':
                return dict(thread=reader_tests.ReaderTest().metadata(sessionId='root',gitInfo={'originUrl':'https://github.com/example/project.git'},status={'type':'active'}))
            return original_call(method,params)
        self.proxy.call = active
        calls = len([c for c in self.proxy.calls if c[0]=='thread/items/list'])
        with self.assertRaisesRegex(ValueError,'active thread body held'):
            self.export()
        self.assertEqual(calls,len([c for c in self.proxy.calls if c[0]=='thread/items/list']))
        self.proxy.call = original_call
        self.ledger['sources']['synthetic'] = dict(through=self.window['since'],adapter_selection=INDEX.source_boundary(self.source),
            deferred={'pending':dict(root_id='root',unit_id='missing',revision=1)},excluded_roots=['root'])
        with self.assertRaisesRegex(ValueError,'omitted a known unfinished'):
            self.export()

    def test_parent_cycle_still_blocks(self):
        export = self.export()
        export['sessions'][0]['parent_id'] = 'root'
        with self.assertRaisesRegex(ValueError,'invalid root'):
            self.collect(export)

    def test_recorded_normal_observation_cannot_be_reused_as_feedback(self):
        self.collect(self.export())
        for unit in self.ledger['units'].values():
            unit['facts'].pop('maintenance_feedback')
        with self.assertRaisesRegex(ValueError,'route changed'):
            self.export()


if __name__ == '__main__':
    unittest.main()
