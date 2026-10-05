"""Fresh daily checkpoint with registered maintenance and evaluation exclusions."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'meta/skill-maintenance/scripts'))
import maintenance as M
import codex_index as I
import codex_reader as R
from tests import test_reader_regressions as fixture_tests


class InitializationTest(unittest.TestCase):
    def test_initial_daily_collection_preserves_registered_exclusions(self):
        fixture=fixture_tests.ReaderRegressions();window=fixture.selection()['window']
        start=int(R.instant(window['since']).timestamp())
        source=fixture.source();source['exclude_roots']=['known-maintenance','known-evaluation']
        target=json.loads((ROOT/'meta/skill-maintenance/examples/target.json').read_text())
        target['source_repos']=['example/project']
        class Pages:
            calls=[]
            def call(self,method,params):
                self.calls.append((method,params.copy()))
                if method=='thread/list':
                    return dict(data=[] if params['archived'] else [fixture.metadata(ident,start+10)
                        for ident in ('new-work','known-maintenance','known-evaluation')],nextCursor=None)
                if method=='thread/turns/list':
                    return dict(data=[fixture.turn('new-turn',start+1)],nextCursor=None)
                if method=='thread/read':
                    return dict(thread=dict(sessionId='new-work',gitInfo={'originUrl':'https://github.com/example/project.git'},status={'type':'idle'}))
                items=[dict(id='u',type='userMessage',content=[dict(type='text',text='Check a new fixture.')]),
                       dict(id='a',type='agentMessage',text='New fixture recorded; outcome unverified.')]
                return dict(data=[dict(turnId='new-turn',item=i) for i in items],nextCursor=None)
        with tempfile.TemporaryDirectory() as tmp:
            private=Path(tmp);daily=private/'daily-state.json';target_path=private/'target.json'
            target_path.write_text(json.dumps(target))
            with patch.dict(os.environ,{'CODEX_THREAD_ID':'new-maintenance'},clear=True):
                M.register_run(argparse.Namespace(target=target_path,repo=ROOT,state=daily,
                               source_id='synthetic',root_id='new-maintenance'))
                registered=json.loads(daily.read_text())
                self.assertEqual({},registered['sources'])
                self.assertEqual({},registered['units'])
                pages=Pages()
                with patch.object(I.sys,'platform','darwin'):
                    selection,_=I.index(pages,source,registered,**window,codex_home=str(Path.home()/'.codex'))
                self.assertTrue(selection['coverage_complete'])
                self.assertEqual(['new-work'],[t['id'] for t in selection['threads']])
                turns,_=R.select_turns(pages,selection)
                export,_=R.read_completed(pages,turns,registered)
                export_path=private/'export.json';export_path.write_text(json.dumps(export))
                result=M.collect(argparse.Namespace(repo=ROOT,state=daily,target=target_path,input=export_path,
                    output=private/'batches',since=window['since'],cutoff=window['cutoff'],hours=24,exclude_root=[],new_evidence_only=True))
            current=json.loads(daily.read_text());batch=json.loads(Path(result['batch']).read_text())
            self.assertEqual(window['cutoff'],current['sources']['synthetic']['through'])
            self.assertEqual('repo-index',current['sources']['synthetic']['adapter_selection']['mode'])
            self.assertTrue(set(source['exclude_roots']) <= set(current['sources']['synthetic']['excluded_roots']))
            self.assertEqual(1,len(current['units']))
            self.assertEqual(1,len(batch['cases']))
            self.assertEqual('synthetic',batch['cases'][0]['source_id'])
            self.assertEqual('new-work',batch['cases'][0]['root_id'])
            self.assertFalse(any(method=='thread/read' and params['threadId']!='new-work' for method,params in pages.calls))


if __name__=='__main__': unittest.main()
