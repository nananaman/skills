"""Synthetic adversarial regressions. No CLI, real sessions or model calls."""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'meta/skill-maintenance/scripts'))
import codex_app as APP
import codex_index as INDEX
import codex_reader as READER
import codex_minimize as MINIMIZE
import maintenance as COLLECT
from tests import test_codex_app as app_tests
from tests.test_codex_app import START, END, T0, T1
from tests import test_codex_reader as reader_tests


class AppRegressions(unittest.TestCase):
    setUp = app_tests.AppCaptureTest.setUp
    tearDown = app_tests.AppCaptureTest.tearDown
    run_capture = app_tests.AppCaptureTest.run_capture
    row = app_tests.AppCaptureTest.row
    turn = app_tests.AppCaptureTest.turn
    synchronize_row = app_tests.AppCaptureTest.synchronize_row

    def test_post_cutoff_update_keeps_finished_turn_or_blocks_without_capture(self):
        self.row()['updated_at'] = T1+1
        self.synchronize_row()
        self.assertEqual(1, len(self.run_capture()['cases']))
        original = self.args.state.read_bytes()
        self.snapshot['threads'] = []
        with self.assertRaisesRegex(ValueError, 'captures missing'):
            self.run_capture()
        self.assertEqual(original, self.args.state.read_bytes())

    def test_finished_failures_keep_evidence_and_missing_body_never_advances_checkpoint(self):
        for status in ('failed', 'interrupted'):
            with self.subTest(status=status):
                self.turn()['status'] = status
                self.turn()['evidence'] = dict(version=1, complete=True, truncated=False,
                    events=[dict(id='failure', kind='error', summary='HTTP 403 permission denied')])
                export = APP.export(self.snapshot, self.source, self.target, START, END, {}, {})
                unit = export['sessions'][0]['units'][0]
                self.assertEqual('completed', unit['status'])
                self.assertIn(status, unit['content']['observed'])
                self.assertIn('403', unit['evidence']['events'][0]['summary'])
        self.turn()['status'] = 'completed'
        self.run_capture()
        original = self.args.state.read_bytes()
        self.turn().update(id='new-failed', status='failed')
        self.turn().pop('content')
        with self.assertRaisesRegex(ValueError, 'content missing'):
            self.run_capture()
        self.assertEqual(original, self.args.state.read_bytes())


class ReaderRegressions(unittest.TestCase):
    def selection(self):
        return reader_tests.ReaderTest().selection()

    def turn(self, ident, done, status='completed', started=None):
        return dict(id=ident, status=status, startedAt=done-1 if started is None else started,
                    completedAt=done, items=[], itemsView='notLoaded')

    def test_old_history_and_failure_do_not_consume_today_budget(self):
        start = int(READER.instant(self.selection()['window']['since']).timestamp())
        for old_status in ('completed', 'failed', 'interrupted'):
            turns = [self.turn('today', start+1)] + [self.turn(str(i), start-500000-i, old_status) for i in range(100)]
            class Pages:
                calls = 0
                def call(self, method, params):
                    self.calls += 1
                    offset = int(params.get('cursor', '0'))
                    return dict(data=turns[offset:offset+20], nextCursor=str(offset+20))
            proxy = Pages()
            selected, counts = READER.select_turns(proxy, self.selection(), 1, 1)
            self.assertEqual(['today'], [t['id'] for t in selected['threads'][0]['turns']])
            self.assertEqual(1, counts['selected_turns'])
            self.assertEqual(1, proxy.calls)

    def test_known_unfinished_requires_more_pages_and_selected_budget_still_blocks(self):
        start = int(READER.instant(self.selection()['window']['since']).timestamp())
        selection = self.selection()
        selection['unfinished_by_root'] = {'root': ['known']}
        class Pages:
            def call(self, method, params):
                if 'cursor' not in params:
                    return dict(data=[ReaderRegressions().turn('today',start+1),
                        ReaderRegressions().turn('old',start-10)],nextCursor='more')
                return dict(data=[dict(id='known',status='inProgress',startedAt=start-100,
                    completedAt=None,items=[],itemsView='notLoaded')],nextCursor=None)
        result,_ = READER.select_turns(Pages(), selection, 2, 2)
        self.assertEqual(['today','known'], [t['id'] for t in result['threads'][0]['turns']])
        with self.assertRaisesRegex(ValueError,'page budget'):
            READER.select_turns(Pages(), selection, 1, 2)
        with self.assertRaisesRegex(ValueError,'selected turn budget'):
            READER.select_turns(Pages(), selection, 2, 1)

    def body(self, turn, dynamic=None, item_started=None):
        class Body:
            def call(self, method, params):
                items=[dict(id='u',type='userMessage',content=[dict(type='text',text='Check fixture.')]),
                       dict(id='a',type='agentMessage',text='Fixture result recorded.')]
                if dynamic is not None:
                    items.append(dynamic)
                return dict(data=[dict(turnId=turn['id'],item=i,startedAtMs=item_started) for i in items],nextCursor=None)
        return Body()

    def test_cross_midnight_turn_uses_turn_bounds_and_rejects_unrelated_item(self):
        start = int(READER.instant(self.selection()['window']['since']).timestamp())
        turn = self.turn('cross-day',start+10,started=start-10)
        result = MINIMIZE.read_turn(self.body(turn,item_started=(start-10)*1000),'root',turn,start,start+86400)
        self.assertTrue(result['trace_complete'])
        result = MINIMIZE.read_turn(self.body(turn,item_started=turn['completedAt']*1000+600),'root',turn,start,start+86400)
        self.assertTrue(result['trace_complete'])
        with self.assertRaisesRegex(ValueError,'outside selected turn'):
            MINIMIZE.read_turn(self.body(turn,item_started=(start-11)*1000),'root',turn,start,start+86400)
        with self.assertRaisesRegex(ValueError,'outside selected turn'):
            MINIMIZE.read_turn(self.body(turn,item_started=(turn['completedAt']+1)*1000),'root',turn,start,start+86400)

    def test_dynamic_failure_preserves_safe_diagnostic_and_missing_detail_is_not_complete(self):
        start = int(READER.instant(self.selection()['window']['since']).timestamp())
        turn = self.turn('failed-tool',start+10,started=start)
        item=dict(id='dynamic',type='dynamicToolCall',tool='check',status='completed',success=False,
                  contentItems=[dict(type='inputText',text='HTTP 403 permission denied')])
        result=MINIMIZE.read_turn(self.body(turn,item),'root',turn,start,start+86400)
        self.assertIn('403',result['events'][1]['summary'])
        self.assertTrue(result['trace_complete'])
        item['contentItems']=[]
        result=MINIMIZE.read_turn(self.body(turn,item),'root',turn,start,start+86400)
        self.assertFalse(result['trace_complete'])
        self.assertIn('diagnostic_not_available',result['events'][1]['summary'])
        item['contentItems']=[dict(type='inputText',text='X'*80)]
        result=MINIMIZE.read_turn(self.body(turn,item),'root',turn,start,start+86400)
        self.assertFalse(result['trace_complete'])
        self.assertTrue(json.loads(result['events'][1]['summary'])['diagnostic_has_omission'])
        for missing in [dict(id='mcp',type='mcpToolCall',tool='check',status='completed',error=None,
                             result={'isError':True,'content':[]}),
                        dict(id='command',type='commandExecution',status='failed',exitCode=1,
                             command='check fixture',aggregatedOutput='')]:
            result=MINIMIZE.read_turn(self.body(turn,missing),'root',turn,start,start+86400)
            self.assertFalse(result['trace_complete'])
            self.assertTrue(json.loads(result['events'][1]['summary'])['diagnostic_not_available'])

    def test_current_root_exclusion_survives_export_collect_and_next_day(self):
        window=self.selection()['window'];start=int(READER.instant(window['since']).timestamp())
        repo=dict(id='example/app',cwd='/fixture/app',information_scope='personal:example')
        binding=dict(mode='repo-index',device_id='fixture',host_id='local',path_flavour='posix',repos=[repo])
        source=dict(version=1,source_id='synthetic',device_id='fixture',host_id='local',path_flavour='posix',repos=[repo],exclude_roots=[])
        target=json.loads((ROOT/'meta/skill-maintenance/examples/target.json').read_text())
        ledger=dict(version=1,target=COLLECT.profile(target),sources={'synthetic':dict(through=window['since'],adapter_selection=binding,deferred={},excluded_roots=[])},units={},decisions={},claims={})
        row=dict(id='maintenance-one',sessionId='maintenance-one',updatedAt=start+86401,turns=[],source='cli',
            cwd=str(Path.home()/'fixture'),path=str(Path.home()/'.codex/fixture'),
            gitInfo={'originUrl':'https://github.com/example/app.git'},ephemeral=False,status={'type':'idle'})
        class Index:
            def call(self,method,params):
                return dict(data=[] if params['archived'] else [row],nextCursor=None)
        with patch.dict(os.environ,{'CODEX_THREAD_ID':row['id']}), patch.object(INDEX.sys,'platform','darwin'):
            selection,_=INDEX.index(Index(),source,ledger,**window,codex_home=str(Path.home()/'.codex'),max_pages=1,max_threads=10)
        selection['turn_selection_complete']=True
        export,_=READER.read_completed(None,selection,ledger)
        with tempfile.TemporaryDirectory() as tmp:
            private=Path(tmp)
            for name,data in [('state',ledger),('export',export),('target',target)]:
                (private/(name+'.json')).write_text(json.dumps(data))
            args=argparse.Namespace(repo=ROOT,state=private/'state.json',input=private/'export.json',target=private/'target.json',output=private/'batches',since=window['since'],cutoff=window['cutoff'],hours=24,exclude_root=[],new_evidence_only=True)
            COLLECT.collect(args)
            saved=json.loads(args.state.read_text())
            self.assertIn(row['id'],saved['sources']['synthetic']['excluded_roots'])
            with patch.dict(os.environ,{'CODEX_THREAD_ID':'maintenance-two'}), patch.object(INDEX.sys,'platform','darwin'):
                next_day,_=INDEX.index(Index(),source,saved,window['cutoff'],'2026-10-05T00:00:00Z',str(Path.home()/'.codex'),1,10)
            self.assertEqual([],next_day['threads'])


if __name__ == '__main__':
    unittest.main()
