"""Bounded reader contracts with synthetic pages; no CLI or model execution."""
from pathlib import Path
import argparse
import json
import tempfile
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'meta/skill-maintenance/scripts'))
import codex_reader as READER
import maintenance as COLLECT
from common import validate_evidence


class ReaderTest(unittest.TestCase):
    def selection(self):
        return dict(source_id='synthetic', host_id='local', coverage_complete=True,
            adapter_selection={'mode': 'repo-index'},
            window={'since': '2026-10-03T00:00:00Z', 'cutoff': '2026-10-04T00:00:00Z'},
            threads=[dict(id='root', session_id='root', repository='example/project',
                information_scope='personal:example', Mac_local_proof=True, ephemeral=False)])

    def test_turn_selection_never_loads_items_and_applies_completion_cutoff(self):
        start = int(READER.instant('2026-10-03T00:00:00Z').timestamp())
        class Fake:
            def call(self, method, params):
                self.method, self.params = method, params
                return dict(data=[dict(id='inside', status='completed', startedAt=start,
                    completedAt=start+1, items=[], itemsView='notLoaded'),
                    dict(id='later', status='completed', startedAt=start,
                    completedAt=start+86401, items=[], itemsView='notLoaded')], nextCursor=None)
        fake = Fake()
        result, counts = READER.select_turns(fake, self.selection())
        self.assertEqual('thread/turns/list', fake.method)
        self.assertEqual('notLoaded', fake.params['itemsView'])
        self.assertEqual(['inside'], [t['id'] for t in result['threads'][0]['turns']])
        self.assertEqual(1, counts['selected_completed_turns'])

    def test_shared_item_reader_minimizes_and_exports_api_failure_with_exit_zero(self):
        selection = self.selection()
        start = int(READER.instant(selection['window']['since']).timestamp())
        selection['turn_selection_complete'] = True
        selection['threads'][0]['turns'] = [dict(id='turn', status='completed', startedAt=start, completedAt=start+10)]
        ledger = dict(units={}, sources={'synthetic': dict(adapter_selection=selection['adapter_selection'], deferred={})})
        class Fake:
            def call(self, method, params):
                if method == 'thread/read':
                    return dict(thread=dict(sessionId='root', gitInfo={'originUrl': 'https://github.com/example/project.git'}, status={'type': 'idle'}))
                self.method = method
                items = [dict(type='userMessage', id='u', content=[{'type': 'text', 'text': 'Check the endpoint.'}]),
                    dict(type='agentMessage', id='a', text='The endpoint returned HTTP 402.', phase='final_answer'),
                    dict(type='commandExecution', id='c', command='curl endpoint private-argument', status='completed', exitCode=0,
                         aggregatedOutput='HTTP 402\nInsufficient balance'),
                    dict(type='mcpToolCall', id='m', tool='check', status='completed', error=None,
                         result={'isError': True, 'content': [{'type': 'text', 'text': 'HTTP 403 denied'}]}),
                    dict(type='reasoning', id='r', text='private reasoning must be discarded')]
                return dict(data=[dict(turnId='turn', item=i) for i in items], nextCursor=None)
        fake = Fake()
        export, counts = READER.read_completed(fake, selection, ledger)
        evidence = export['sessions'][0]['units'][0]['evidence']
        validate_evidence(evidence)
        self.assertEqual('thread/items/list', fake.method)
        self.assertEqual(1, counts['body_turns_read'])
        self.assertIn('402', evidence['events'][1]['summary'])
        self.assertNotIn('private reasoning', str(export))
        self.assertNotIn('private-argument', str(export))
        self.assertEqual('error', evidence['events'][3]['status'])
        self.assertIn('403', evidence['events'][3]['summary'])


class ReaderEntryTest(unittest.TestCase):
    def test_first_cli_entry_needs_no_existing_state_and_continuation_keeps_scope(self):
        start='2026-10-03T00:00:00Z'; cutoff='2026-10-04T00:00:00Z'
        ts=int(READER.instant(start).timestamp())
        source=dict(version=1,source_id='synthetic',device_id='fixture',host_id='local',path_flavour='posix',
            repos=[dict(id='example/app',cwd='/fixture/app',information_scope='personal:example')],exclude_roots=[])
        class FakeProxy:
            server_version='0.160.0'
            def __init__(self,config): pass
            def close(self): pass
            def call(self,method,params):
                if method == 'thread/list':
                    row=dict(id='root',sessionId='root',updatedAt=ts+10,turns=[],source='cli',
                        cwd=str(Path.home()/'fixture'),path=str(Path.home()/'.codex/fixture'),
                        gitInfo={'originUrl':'https://github.com/example/app.git'},ephemeral=False,status={'type':'idle'})
                    return dict(data=[] if params['archived'] else [row],nextCursor=None)
                if method == 'thread/turns/list':
                    return dict(data=[dict(id='turn',status='completed',startedAt=ts,completedAt=ts+1,
                        items=[],itemsView='notLoaded')],nextCursor=None)
                if method == 'thread/read':
                    return dict(thread=dict(sessionId='root',gitInfo={'originUrl':'https://github.com/example/app.git'},status={'type':'idle'}))
                items=[dict(id='u',type='userMessage',content=[dict(type='text',text='Check fixture.')]),
                       dict(id='a',type='agentMessage',text='Fixture checked.')]
                return dict(data=[dict(turnId='turn',item=i) for i in items],nextCursor=None)
        with tempfile.TemporaryDirectory() as tmp:
            private=Path(tmp);state=private/'state.json';config=private/'source.json'
            config.write_text(json.dumps(source))
            with patch.object(READER,'Proxy',FakeProxy),patch.object(READER.sys,'platform','darwin'):
                for action,extra in [('index',['--source',str(config),'--state',str(state),'--since',start,'--cutoff',cutoff]),
                        ('turns',['--selection',str(private/'index.json')]),
                        ('read',['--selection',str(private/'turns.json'),'--state',str(state),'--read-completed'])]:
                    with patch.object(sys,'argv',['reader',action,*extra,'--codex-home',str(Path.home()/'.codex'),'--output',str(private/(action+'.json'))]):
                        self.assertEqual(0,READER.main())
                    self.assertFalse(state.exists())
                target=private/'target.json'
                target.write_bytes((ROOT/'meta/skill-maintenance/examples/target.json').read_bytes())
                COLLECT.collect(argparse.Namespace(repo=ROOT,state=state,input=private/'read.json',target=target,
                    output=private/'batches',since=start,cutoff=cutoff,hours=24,exclude_root=[],new_evidence_only=True))
                original=state.read_bytes()
                source['repos'][0]['cwd']='/fixture/changed';config.write_text(json.dumps(source))
                with patch.object(sys,'argv',['reader','index','--source',str(config),'--state',str(state),
                        '--since',start,'--cutoff',cutoff,'--codex-home',str(Path.home()/'.codex'),'--output',str(private/'changed.json')]):
                    self.assertEqual(2,READER.main())
                self.assertFalse((private/'changed.json').exists())
                self.assertEqual(original,state.read_bytes())


if __name__ == '__main__':
    unittest.main()
