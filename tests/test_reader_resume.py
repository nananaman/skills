"""Persistent normalized pagination with fixed scope, no actual sessions or daemon."""
import contextlib
import io
import json
import os
import queue
import threading
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'meta/skill-maintenance/scripts'))
import codex_proxy as P
import codex_reader as R
import codex_minimize as M
from tests import test_reader_regressions as fixture_tests


class ResumeTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.private=Path(self.tmp.name);self.fixture=fixture_tests.ReaderRegressions()
        self.window=self.fixture.selection()['window'];self.start=int(R.instant(self.window['since']).timestamp())
        self.state=self.private/'state.json';self.state.write_text(json.dumps(dict(sources={},units={})))
        self.original=self.state.read_bytes()
        self.source=self.private/'source.json';self.source.write_text(json.dumps(self.fixture.source()))
        self.output=self.private/'index.json'

    def argv(self,action,byte_limit):
        common=['reader',action,'--state',str(self.state),'--output',str(self.output),
                '--codex-home',str(Path.home()/'.codex'),'--max-bytes',str(byte_limit)]
        if action=='index': return common+['--source',str(self.source),'--since',self.window['since'],'--cutoff',self.window['cutoff']]
        if action=='read': common+=['--read-completed']
        return common+['--selection',str(self.private/'selection.json')]

    def run_reader(self,fake,argv):
        with patch.object(R,'Proxy',fake),patch.object(R.sys,'platform','darwin'),patch.object(sys,'argv',argv),contextlib.redirect_stdout(io.StringIO()):
            code=R.main()
        return code,json.loads(self.output.with_suffix('.result.json').read_text())

    def index_proxy(self):
        owner=self
        class Fake:
            server_version='0.160.0'
            attempts=[];stale=False;expired=False
            def __init__(self,config):
                self.budget=config['acquisition_budget'];self.calls=[];self.attempts.append(self.calls)
            def close(self): pass
            def call(self,method,params):
                self.calls.append((params['archived'],params.get('cursor')))
                n=int(params.get('cursor','0'))
                if self.expired and n:
                    raise ValueError('Codex read RPC -32602: read rejected')
                row=owner.fixture.metadata('moved-root' if self.stale and n==0 else str(n),owner.start+80000)
                row.update(preview='password: synthetic-secret-preview',title='PRIVATE TITLE')
                response=dict(data=[row],nextCursor=str(n+1) if n<2 else None)
                self.budget.consume(len(json.dumps(response).encode()))
                return response
        return Fake

    def index_limit(self):
        row=self.fixture.metadata('0',self.start+80000)
        row.update(preview='password: synthetic-secret-preview',title='PRIVATE TITLE')
        return 2*len(json.dumps(dict(data=[row],nextCursor='1')).encode())+1

    def test_index_advances_across_small_fixed_budgets_then_completes(self):
        fake=self.index_proxy();args=self.argv('index',self.index_limit())
        code,result=self.run_reader(fake,args)
        self.assertEqual(2,code);self.assertEqual('incomplete',result['status'])
        self.assertEqual(2,result['progress']['saved_pages'])
        self.assertFalse(self.output.exists())
        for _ in range(12):
            code,result=self.run_reader(fake,args)
            self.assertEqual(self.original,self.state.read_bytes())
            if code==0: break
            self.assertEqual('incomplete',result['status'])
            self.assertFalse(result['output_written'])
        self.assertEqual(0,code)
        self.assertEqual('2',fake.attempts[1][0][1])
        selected=json.loads(self.output.read_text())
        self.assertTrue(selected['coverage_complete'])
        self.assertEqual({'0','1','2'},{t['id'] for t in selected['threads']})
        saved=self.output.with_suffix('.progress.json').read_text()
        self.assertNotIn('synthetic-secret-preview',saved)
        self.assertNotIn('PRIVATE TITLE',saved)
        self.assertNotIn(str(Path.home()/'fixture'),saved)
        self.assertFalse(result['checkpoint_written'])

    def test_fixed_window_and_scope_mismatch_block_before_rpc(self):
        for alteration in ('window','scope','normalizer'):
            with self.subTest(alteration=alteration):
                self.output=self.private/(alteration+'.json')
                fake=self.index_proxy();args=self.argv('index',self.index_limit())
                self.assertEqual(2,self.run_reader(fake,args)[0])
                attempts=len(fake.attempts)
                if alteration=='window': args[args.index('--cutoff')+1]='2026-10-05T00:00:00Z'
                elif alteration=='normalizer':
                    progress=self.output.with_suffix('.progress.json')
                    document=json.loads(progress.read_text())
                    document['binding']['normalizer_version']-=1
                    document['digest']=R.digest({k:v for k,v in document.items() if k!='digest'})
                    progress.write_text(json.dumps(document))
                else:
                    config=json.loads(self.source.read_text());config['repos'][0]['id']='other/project'
                    self.source.write_text(json.dumps(config))
                code,result=self.run_reader(fake,args)
                self.assertEqual(2,code);self.assertEqual('blocked',result['status'])
                self.assertIn('binding changed',result['blocker'])
                self.assertEqual(attempts,len(fake.attempts))
                self.assertEqual(self.original,self.state.read_bytes())

    def test_corrupted_progress_and_old_cursor_never_reset_or_claim_coverage(self):
        fake=self.index_proxy();args=self.argv('index',self.index_limit())
        self.run_reader(fake,args);progress=self.output.with_suffix('.progress.json');saved=progress.read_bytes()
        fake.expired=True
        code,result=self.run_reader(fake,args)
        self.assertEqual(2,code);self.assertEqual('blocked',result['status'])
        self.assertEqual(saved,progress.read_bytes())
        self.assertFalse(self.output.exists())
        self.assertEqual('2',fake.attempts[-1][0][1])
        document=json.loads(saved);document['pages']={};progress.write_text(json.dumps(document))
        attempts=len(fake.attempts)
        code,result=self.run_reader(fake,args)
        self.assertEqual('blocked',result['status']);self.assertIn('integrity mismatch',result['blocker'])
        self.assertEqual(attempts,len(fake.attempts))
        self.assertEqual(self.original,self.state.read_bytes())

    def test_moved_index_head_blocks_resumed_coverage(self):
        fake=self.index_proxy();args=self.argv('index',self.index_limit())
        self.run_reader(fake,args);fake.stale=True
        for _ in range(12):
            code,result=self.run_reader(fake,args)
            if result['status']=='blocked': break
        self.assertEqual('blocked',result['status'])
        self.assertIn('head changed',result['blocker'])
        self.assertFalse(self.output.exists())
        self.assertEqual(self.original,self.state.read_bytes())

    def test_head_confirmation_is_live_again_after_confirmation_timeout(self):
        fake=self.index_proxy()
        self.assertEqual(0,self.run_reader(fake,self.argv('index',10000))[0])
        args=self.argv('index',self.index_limit()//2+128)
        code,result=self.run_reader(fake,args)
        self.assertEqual('incomplete',result['status'])
        self.assertEqual([(False,None),(True,None)],fake.attempts[-1])
        fake.stale=True
        code,result=self.run_reader(fake,args)
        self.assertEqual('blocked',result['status'])
        self.assertIn('head changed',result['blocker'])
        self.assertEqual([(False,None)],fake.attempts[-1])
        self.assertFalse(result['output_written'])
        self.assertEqual(self.original,self.state.read_bytes())

    def test_new_current_root_is_excluded_before_cached_items_or_native_read(self):
        self.output=self.private/'export.json'
        selection=self.fixture.selection();selection['turn_selection_complete']=True
        selection['threads'][0]['turns']=[self.fixture.turn('turn',self.start+10)]
        (self.private/'selection.json').write_text(json.dumps(selection))
        class Fake:
            server_version='0.160.0';attempts=[]
            def __init__(self,config): self.budget=config['acquisition_budget'];self.calls=[];self.attempts.append(self.calls)
            def close(self): pass
            def call(self,method,params):
                self.calls.append(method)
                if method=='thread/read':
                    self.budget.consume(10)
                    return dict(thread=dict(sessionId='root',gitInfo={'originUrl':'https://github.com/example/project.git'},status={'type':'idle'}))
                self.budget.consume(100)
                n=int(params.get('cursor','0'))
                item=dict(id='u',type='userMessage',content=[dict(type='text',text='Synthetic request.')])
                return dict(data=[dict(turnId='turn',item=item)],nextCursor='1' if n==0 else None)
        args=self.argv('read',110)
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'other-root'}):
            self.assertEqual(2,self.run_reader(Fake,args)[0])
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'root'}):
            code,result=self.run_reader(Fake,args)
        self.assertEqual(0,code);self.assertEqual([],Fake.attempts[-1])
        export=json.loads(self.output.read_text())
        self.assertEqual([],export['sessions']);self.assertIn('root',export['excluded_roots'])
        self.assertEqual(self.original,self.state.read_bytes())

    def test_turn_metadata_resumes_from_saved_cursor_without_loading_bodies(self):
        self.output=self.private/'turns.json'
        (self.private/'selection.json').write_text(json.dumps(self.fixture.selection()))
        owner=self
        class Fake:
            server_version='0.160.0';attempts=[]
            def __init__(self,config): self.budget=config['acquisition_budget'];self.calls=[];self.attempts.append(self.calls)
            def close(self): pass
            def call(self,method,params):
                assert params['itemsView']=='notLoaded'
                self.calls.append(params.get('cursor'))
                n=int(params.get('cursor','0'))
                response=dict(data=[owner.fixture.turn(str(n),owner.start+10-n)],nextCursor=str(n+1) if n<4 else None)
                self.budget.consume(len(json.dumps(response).encode()))
                return response
        sample=dict(data=[self.fixture.turn('0',self.start+10)],nextCursor='1')
        args=self.argv('turns',2*len(json.dumps(sample).encode())+1)
        self.assertEqual(2,self.run_reader(Fake,args)[0])
        self.assertEqual(2,self.run_reader(Fake,args)[0])
        code,result=self.run_reader(Fake,args)
        self.assertEqual(0,code)
        self.assertEqual('2',Fake.attempts[1][0])
        self.assertEqual('4',Fake.attempts[2][0])
        self.assertEqual(5,len(json.loads(self.output.read_text())['threads'][0]['turns']))
        self.assertEqual(self.original,self.state.read_bytes())

    def test_item_pages_resume_without_raw_reasoning_secrets_or_command_arguments(self):
        self.output=self.private/'export.json'
        selection=self.fixture.selection();selection['turn_selection_complete']=True
        selection['threads'][0]['turns']=[self.fixture.turn('turn',self.start+10)]
        (self.private/'selection.json').write_text(json.dumps(selection))
        items=[dict(id='u',type='userMessage',content=[dict(type='text',text='Check fixture.')]),
               dict(id='r',type='reasoning',text='PRIVATE REASONING password: raw-secret'),
               dict(id='c',type='commandExecution',status='completed',exitCode=0,
                    command='private-argument',aggregatedOutput='checks passed\npassword: synthetic-secret'),
               dict(id='a',type='agentMessage',text='Fixture recorded.')]
        class Fake:
            server_version='0.160.0';attempts=[]
            def __init__(self,config): self.budget=config['acquisition_budget'];self.calls=[];self.attempts.append(self.calls)
            def close(self): pass
            def call(self,method,params):
                if method=='thread/read':
                    self.budget.consume(10)
                    return dict(thread=dict(sessionId='root',gitInfo={'originUrl':'https://github.com/example/project.git'},status={'type':'idle'}))
                self.calls.append(params.get('cursor'));n=int(params.get('cursor','0'))
                self.budget.consume(100)
                return dict(data=[dict(turnId='turn',item=items[n])],nextCursor=str(n+1) if n<3 else None)
        args=self.argv('read',210)
        self.assertEqual(2,self.run_reader(Fake,args)[0])
        code,result=self.run_reader(Fake,args)
        self.assertEqual(0,code);self.assertEqual(['2','3'],Fake.attempts[1])
        export=json.loads(self.output.read_text())
        self.assertTrue(export['coverage']['complete'])
        self.assertEqual(2,len(export['sessions'][0]['units'][0]['evidence']['events']))
        saved=self.output.with_suffix('.progress.json').read_text()
        for private in ('PRIVATE REASONING','raw-secret','synthetic-secret','private-argument'):
            self.assertNotIn(private,saved)
        self.assertEqual(self.original,self.state.read_bytes())

    def test_checkpoint_change_blocks_partial_cache_reuse_before_rpc(self):
        fake=self.index_proxy();args=self.argv('index',self.index_limit())
        self.run_reader(fake,args);attempts=len(fake.attempts)
        current=json.loads(self.state.read_text());current['sources']['synthetic']=dict(through=self.window['cutoff'])
        self.state.write_text(json.dumps(current))
        code,result=self.run_reader(fake,args)
        self.assertEqual('blocked',result['status'])
        self.assertIn('binding changed',result['blocker'])
        self.assertEqual(attempts,len(fake.attempts))

    def test_structured_mcp_error_secret_is_removed_before_progress_save(self):
        turn=self.fixture.turn('turn',self.start+10)
        item=dict(id='mcp',type='mcpToolCall',status='failed',tool='synthetic',
                  error=dict(message='request failed',password='synthetic-json-secret'))
        normalized=M.item_page([dict(turnId='turn',item=item)],turn,False,False)
        from codex_resume import Progress
        progress=Progress(self.private/'mcp.progress.json',dict(window=self.window))
        progress.save('thread/items/list',dict(turnId='turn'),None,normalized,None)
        saved=progress.path.read_text()
        self.assertNotIn('synthetic-json-secret',saved)
        self.assertTrue(normalized['missing'])
        self.assertIn('sensitive line omitted',saved)

    def test_progress_lock_conflict_never_starts_proxy_or_breaks_existing_lock(self):
        fake=self.index_proxy();args=self.argv('index',self.index_limit())
        lock=self.output.with_suffix('.progress.json').with_name('index.progress.json.lock')
        lock.mkdir()
        code,result=self.run_reader(fake,args)
        self.assertEqual('blocked',result['status'])
        self.assertIn('locked',result['blocker'])
        self.assertEqual([],fake.attempts)
        self.assertTrue(lock.exists())
        self.assertEqual(self.original,self.state.read_bytes())

    def test_send_deadline_exhaustion_is_incomplete_with_resume(self):
        self.output=self.private/'export.json'
        selection=self.fixture.selection();selection['turn_selection_complete']=True
        (self.private/'selection.json').write_text(json.dumps(selection))
        class Fake(P.Proxy):
            def __init__(self,config):
                self.server_version='0.160.0';self.budget=config['acquisition_budget'];self.sequence=0
                self.close_lock=threading.Lock();self.send_lock=threading.Lock();self.messages=queue.Queue()
                class Jammed:
                    gate=threading.Event()
                    def write(self,data): self.gate.wait(2);return len(data)
                    def close(self): self.gate.set()
                self.process=SimpleNamespace(stdin=Jammed(),stdout=io.BytesIO(),poll=lambda:0)
        args=self.argv('read',10000)+['--max-seconds','1']
        code,result=self.run_reader(Fake,args)
        self.assertEqual(2,code);self.assertEqual('incomplete',result['status'])
        self.assertIn('resume',result)
        self.assertIn('time budget',result['blocker'])
        self.assertFalse(self.output.exists());self.assertEqual(self.original,self.state.read_bytes())


if __name__=='__main__': unittest.main()
