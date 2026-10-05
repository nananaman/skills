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
import codex_index as INDEX
import codex_reader as READER
import codex_minimize as MINIMIZE
import maintenance as COLLECT
from tests import test_codex_reader as reader_tests


class ReaderRegressions(unittest.TestCase):
    def selection(self):
        return reader_tests.ReaderTest().selection()

    def turn(self, ident, done, status='completed', started=None):
        return dict(id=ident, status=status, startedAt=done-1 if started is None else started,
                    completedAt=done, items=[], itemsView='notLoaded')

    def metadata(self, ident, updated):
        return dict(id=ident, sessionId=ident, updatedAt=updated, turns=[], source='cli',
            cwd=str(Path.home()/'fixture'), path=str(Path.home()/'.codex/fixture'),
            gitInfo={'originUrl':'https://github.com/example/project.git'},
            ephemeral=False, status={'type':'idle'})

    def source(self):
        return dict(version=1, source_id='synthetic', device_id='fixture', host_id='local',
            path_flavour='posix', repos=[dict(id='example/project', cwd=str(Path.home()/'fixture'),
                information_scope='personal:example')], exclude_roots=[])

    def test_post_cutoff_thread_update_preserves_in_window_completed_turn(self):
        window=self.selection()['window']; start=int(READER.instant(window['since']).timestamp())
        row=self.metadata('root',start+86401)
        class Pages:
            def call(self,method,params):
                if method == 'thread/list':
                    return dict(data=[] if params['archived'] else [row],nextCursor=None)
                return dict(data=[ReaderRegressions().turn('inside',start+1)],nextCursor=None)
        with patch.object(INDEX.sys,'platform','darwin'):
            selected,_=INDEX.index(Pages(),self.source(),dict(sources={}),**window,
                codex_home=str(Path.home()/'.codex'))
        selected,_=READER.select_turns(Pages(),selected)
        self.assertEqual(['inside'],[t['id'] for t in selected['threads'][0]['turns']])

    def test_finished_failures_keep_evidence_and_missing_body_never_advances_checkpoint(self):
        selection=self.selection();start=int(READER.instant(selection['window']['since']).timestamp())
        selection['turn_selection_complete']=True
        class Body:
            missing=False
            def call(self,method,params):
                if method == 'thread/read':
                    return dict(thread=reader_tests.ReaderTest().metadata(sessionId='root',gitInfo={'originUrl':'https://github.com/example/project.git'},status={'type':'idle'}))
                items=[] if self.missing else [dict(id='u',type='userMessage',content=[dict(type='text',text='Check fixture.')]),
                    dict(id='a',type='agentMessage',text='The request failed.'),
                    dict(id='e',type='dynamicToolCall',tool='check',status='completed',success=False,
                         contentItems=[dict(type='inputText',text='HTTP 403 permission denied')])]
                return dict(data=[dict(turnId=params['turnId'],item=i) for i in items],nextCursor=None)
        body=Body()
        ledger=dict(sources={},units={})
        with tempfile.TemporaryDirectory() as tmp:
            private=Path(tmp)
            target=json.loads((ROOT/'meta/skill-maintenance/examples/target.json').read_text())
            target['source_repos']=['example/project']
            (private/'target.json').write_text(json.dumps(target))
            args=argparse.Namespace(repo=ROOT,state=private/'state.json',input=private/'export.json',target=private/'target.json',output=private/'batches',since=selection['window']['since'],cutoff=selection['window']['cutoff'],hours=24,exclude_root=[],new_evidence_only=True)
            for status in ('failed','interrupted'):
                selection['threads'][0]['turns']=[self.turn(status,start+10,status,started=start)]
                export,_=READER.read_completed(body,selection,ledger)
                unit=export['sessions'][0]['units'][0]
                self.assertEqual('completed',unit['status'])
                self.assertIn(status,unit['content']['observed'])
                self.assertIn('403',unit['evidence']['events'][1]['summary'])
                args.input.write_text(json.dumps(export));COLLECT.collect(args)
                ledger=json.loads(args.state.read_text())
            original=args.state.read_bytes()
            selection['threads'][0]['turns']=[self.turn('missing',start+11,'failed',started=start)]
            body.missing=True
            with self.assertRaisesRegex(ValueError,'request/response missing'):
                READER.read_completed(body,selection,ledger)
            self.assertEqual(original,args.state.read_bytes())

    def test_failed_or_interrupted_before_assistant_response_exports_native_failure(self):
        # Arrange: 応答前に終了したturnも、取得済みの要求とnative終了状態を残す。
        selection=self.selection();start=int(READER.instant(selection['window']['since']).timestamp())
        selection['turn_selection_complete']=True
        class Body:
            with_tool=False
            def call(self,method,params):
                if method == 'thread/read':
                    return dict(thread=reader_tests.ReaderTest().metadata(sessionId='root',gitInfo={'originUrl':'https://github.com/example/project.git'},status={'type':'idle'}))
                items=[dict(id='u',type='userMessage',content=[dict(type='text',text='Check fixture.')])]
                if self.with_tool:
                    items.append(dict(id='e',type='dynamicToolCall',tool='check',status='completed',success=False,
                        contentItems=[dict(type='inputText',text='HTTP 403 permission denied')]))
                return dict(data=[dict(turnId=params['turnId'],item=i) for i in items],nextCursor=None)
        body=Body()
        for status in ('failed','interrupted'):
            for with_tool in (False,True):
                with self.subTest(status=status,with_tool=with_tool):
                    body.with_tool=with_tool
                    selection['threads'][0]['turns']=[self.turn(status,start+10,status,started=start)]
                    # Act
                    export,_=READER.read_completed(body,selection,dict(sources={},units={}))
                    # Assert: 作業成功や未記録のassistant応答を補わない。
                    unit=export['sessions'][0]['units'][0]
                    self.assertEqual('completed',unit['status'])
                    self.assertEqual('Check fixture.',unit['content']['request'])
                    self.assertIn('Recorded turn status: '+status,unit['content']['observed'])
                    self.assertTrue(unit['evidence']['complete'])
                    if with_tool:
                        self.assertEqual('error',unit['evidence']['events'][1]['status'])
                        self.assertIn('403',unit['evidence']['events'][1]['summary'])
                    else:
                        self.assertEqual([],unit['evidence']['events'])
        # 正常完了の応答欠落は、失敗turnの例外で許容しない。
        selection['threads'][0]['turns']=[self.turn('missing-response',start+10,started=start)]
        with self.assertRaisesRegex(ValueError,'request/response missing'):
            READER.read_completed(body,selection,dict(sources={},units={}))

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
            selected, counts = READER.select_turns(proxy, self.selection())
            self.assertEqual(['today'], [t['id'] for t in selected['threads'][0]['turns']])
            self.assertEqual(1, counts['selected_turns'])
            self.assertEqual(1, proxy.calls)

    def test_known_unfinished_requires_all_needed_pages_and_missing_turn_still_blocks(self):
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
        result,_ = READER.select_turns(Pages(), selection)
        self.assertEqual(['today','known'], [t['id'] for t in result['threads'][0]['turns']])
        class Missing:
            def call(self, method, params):
                return dict(data=[ReaderRegressions().turn('today',start+1)],nextCursor=None)
        with self.assertRaisesRegex(ValueError,'omitted a known unfinished'):
            READER.select_turns(Missing(), selection)

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

    def test_truncated_command_failure_diagnostic_blocks_verified_export(self):
        # Arrange: 先頭12行は安全な容量内でも、13行目以降の診断を失う。
        selection=self.selection();start=int(READER.instant(selection['window']['since']).timestamp())
        selection['turn_selection_complete']=True
        turn=self.turn('long-failure',start+10,started=start)
        selection['threads'][0]['turns']=[turn]
        output='\n'.join('error '+('detail '*25)+str(i) for i in range(20))
        item=dict(id='c',type='commandExecution',command='check fixture',status='failed',exitCode=1,
            aggregatedOutput=output)
        body=self.body(turn,item)
        class Body:
            def call(self,method,params):
                if method == 'thread/read':
                    return dict(thread=reader_tests.ReaderTest().metadata(sessionId='root',gitInfo={'originUrl':'https://github.com/example/project.git'},status={'type':'idle'}))
                return body.call(method,params)
        # Act / Assert: 要約の保存成功を完全な失敗証拠としない。
        result=MINIMIZE.read_turn(body,'root',turn,start,start+86400)
        self.assertFalse(result['trace_complete'])
        self.assertTrue(json.loads(result['events'][1]['summary'])['diagnostic_truncated'])
        with self.assertRaisesRegex(ValueError,'incomplete item evidence'):
            READER.read_completed(Body(),selection,dict(sources={},units={}))

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
            selection,_=INDEX.index(Index(),source,ledger,**window,codex_home=str(Path.home()/'.codex'))
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
                next_day,_=INDEX.index(Index(),source,saved,window['cutoff'],'2026-10-05T00:00:00Z',str(Path.home()/'.codex'))
            self.assertEqual([],next_day['threads'])


if __name__ == '__main__':
    unittest.main()
