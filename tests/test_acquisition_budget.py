"""Byte/time budgets and full pagination; synthetic data, no daemon or sessions."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'meta/skill-maintenance/scripts'))
import codex_proxy as PROXY
import codex_wire as WIRE
import codex_reader as READER
import codex_index as INDEX
import codex_minimize as MINIMIZE
from common import validate_evidence
from tests import test_reader_regressions as fixture_tests
from tests import test_codex_reader as reader_tests


class AcquisitionTest(unittest.TestCase):
    def test_more_than_twenty_pages_are_read_and_cursor_loops_still_stop(self):
        class Pages:
            def call(self,method,params):
                offset=int(params.get('cursor','0'))
                return dict(data=[offset],nextCursor=str(offset+1) if offset<40 else None)
        pages=list(PROXY.iter_pages(Pages(),'thread/list',{'limit':1}))
        self.assertEqual(41,len(pages))
        class Loop:
            def call(self,method,params): return dict(data=[],nextCursor='same')
        with self.assertRaisesRegex(ValueError,'cursor loop'):
            list(PROXY.iter_pages(Loop(),'thread/list',{'limit':1}))

    def test_more_than_one_hundred_threads_and_turns_are_selected(self):
        fixture=fixture_tests.ReaderRegressions()
        window=fixture.selection()['window'];start=int(READER.instant(window['since']).timestamp())
        class IndexPages:
            def call(self,method,params):
                offset=int(params.get('cursor','0'))
                return dict(data=[] if params['archived'] else [fixture.metadata(str(i),start+10) for i in range(offset,min(offset+50,150))],
                            nextCursor=str(offset+50) if not params['archived'] and offset+50<150 else None)
        with patch.object(INDEX.sys,'platform','darwin'):
            selection,_=INDEX.index(IndexPages(),fixture.source(),dict(sources={}),**window,codex_home=str(Path.home()/'.codex'))
        self.assertEqual(150,len(selection['threads']))
        class TurnPages:
            def call(self,method,params):
                offset=int(params.get('cursor','0'))
                return dict(data=[fixture.turn(str(i),start+2000-i) for i in range(offset,min(offset+20,1100))],
                            nextCursor=str(offset+20) if offset+20<1100 else None)
        selected,counts=READER.select_turns(TurnPages(),fixture.selection())
        self.assertEqual(1100,len(selected['threads'][0]['turns']))
        self.assertEqual(55,counts['turn_pages'])

    def test_more_than_twenty_item_pages_and_256_events_are_retained(self):
        fixture=fixture_tests.ReaderRegressions();window=fixture.selection()['window']
        start=int(READER.instant(window['since']).timestamp());turn=fixture.turn('turn',start+2,started=start)
        items=[dict(id='user',type='userMessage',content=[dict(type='text',text='Check the synthetic fixture.')]),
               dict(id='agent',type='agentMessage',text='Synthetic checks recorded.')]
        items += [dict(id='command-'+str(i),type='commandExecution',status='completed',exitCode=0,
                       command='synthetic check',aggregatedOutput='checks passed') for i in range(420)]
        class ItemPages:
            def call(self,method,params):
                offset=int(params.get('cursor','0'))
                return dict(data=[dict(turnId='turn',item=i) for i in items[offset:offset+20]],
                            nextCursor=str(offset+20) if offset+20<len(items) else None)
        review=MINIMIZE.read_turn(ItemPages(),'root',turn,start,start+86400)
        self.assertTrue(review['trace_complete'])
        self.assertEqual(22,review['pages'])
        self.assertEqual(840,len(review['events']))
        validate_evidence(dict(version=1,complete=True,truncated=False,events=review['events']))

    def test_byte_budget_and_deadline_exhaustion_are_incomplete(self):
        with patch.object(PROXY.time,'monotonic',return_value=100):
            budget=PROXY.AcquisitionBudget(max_bytes=10,max_seconds=5)
            budget.consume(10)
            budget.check()  # Exact size is allowed if this completes the stage.
            with self.assertRaises(PROXY.AcquisitionIncomplete): budget.check_request()
            late=PROXY.AcquisitionBudget(max_bytes=100,max_seconds=5)
        with patch.object(PROXY.time,'monotonic',return_value=105):
            with self.assertRaises(PROXY.AcquisitionIncomplete): budget.check()
            with self.assertRaises(PROXY.AcquisitionIncomplete): late.consume(3)
            self.assertEqual(3,late.received_bytes)
        with patch.object(PROXY.time,'monotonic',return_value=100):
            budget=PROXY.AcquisitionBudget(max_bytes=10,max_seconds=5)
            with self.assertRaises(PROXY.AcquisitionIncomplete): budget.consume(11)

    def test_frame_over_remaining_budget_is_stopped_before_body_read(self):
        stream=io.BytesIO(bytes([0x81,126])+(1000).to_bytes(2,'big')+b'x'*1000)
        with self.assertRaisesRegex(ValueError,'acquisition byte budget exhausted'):
            WIRE.receive(stream,remaining_budget=999)
        self.assertEqual(4,stream.tell())
        stream=io.BytesIO(bytes([0x81,3])+b'abc')
        self.assertEqual(b'abc',WIRE.receive(stream,remaining_budget=3)[2])

    def test_index_receives_the_requested_budget_and_original_codex_home(self):
        fixture=fixture_tests.ReaderRegressions()
        class Fake:
            server_version='0.160.0'
            def __init__(self,config):
                assert config['codex_home']==str(Path.home()/'.codex')
                assert config['codex_executable']=='synthetic-cli'
                self.budget=config['acquisition_budget']
                assert self.budget.max_bytes==1000
            def close(self): pass
            def call(self,method,params):
                self.budget.consume(2000)
        with tempfile.TemporaryDirectory() as tmp:
            private=Path(tmp);source=private/'source.json';state=private/'state.json';output=private/'index.json'
            source.write_text(json.dumps(fixture.source()))
            argv=['reader','index','--source',str(source),'--state',str(state),'--output',str(output),
                '--since','2026-10-03T00:00:00Z','--cutoff','2026-10-04T00:00:00Z',
                '--codex-home',str(Path.home()/'.codex'),'--codex-executable','synthetic-cli','--max-bytes','1000']
            with patch.object(READER,'Proxy',Fake),patch.object(READER.sys,'platform','darwin'),patch.object(sys,'argv',argv):
                self.assertEqual(2,READER.main())
            result=json.loads(output.with_suffix('.result.json').read_text())
            self.assertEqual('incomplete',result['status'])
            self.assertFalse(state.exists())
            self.assertFalse(output.exists())
            self.assertEqual(1000,result['acquisition_budget']['max_bytes'])

    def test_transport_reports_oversized_frame_as_budget_exhaustion_without_reading_body(self):
        import queue
        from types import SimpleNamespace
        proxy=PROXY.Proxy.__new__(PROXY.Proxy)
        proxy.budget=PROXY.AcquisitionBudget(max_bytes=999,max_seconds=30)
        stream=io.BytesIO(bytes([0x81,126])+(1000).to_bytes(2,'big')+b'x'*1000)
        proxy.process=SimpleNamespace(stdout=stream)
        proxy.messages=queue.Queue(maxsize=16)
        proxy.handshake_key='synthetic'
        with patch.object(WIRE,'accept',return_value=None): proxy._read()
        self.assertTrue(proxy.messages.get_nowait()['transport_ready'])
        self.assertTrue(proxy.messages.get_nowait()['budget_exhausted'])
        self.assertEqual(4,stream.tell())
        self.assertEqual(0,proxy.budget.received_bytes)

    def test_incomplete_stage_never_writes_export_or_checkpoint_and_retries_same_window(self):
        selection=reader_tests.ReaderTest().selection()
        selection['turn_selection_complete']=True
        start=int(READER.instant(selection['window']['since']).timestamp())
        selection['threads'][0]['turns']=[fixture_tests.ReaderRegressions().turn('turn',start+10)]
        class Fake:
            server_version='0.160.0'
            charge=2000
            def __init__(self,config): self.budget=config['acquisition_budget']
            def close(self): pass
            def call(self,method,params):
                self.budget.consume(self.charge)
                if method=='thread/read':
                    return dict(thread=reader_tests.ReaderTest().metadata(sessionId='root',gitInfo={'originUrl':'https://github.com/example/project.git'},status={'type':'idle'}))
                items=[dict(id='u',type='userMessage',content=[dict(type='text',text='Check fixture.')]),
                       dict(id='a',type='agentMessage',text='Fixture recorded.')]
                return dict(data=[dict(turnId='turn',item=i) for i in items],nextCursor=None)
        with tempfile.TemporaryDirectory() as tmp:
            private=Path(tmp);state=private/'state.json';chosen=private/'selection.json';output=private/'export.json'
            state.write_text(json.dumps(dict(sources={},units={})));original=state.read_bytes()
            chosen.write_text(json.dumps(selection))
            argv=['reader','read','--read-completed','--selection',str(chosen),'--state',str(state),
                  '--codex-home',str(Path.home()/'.codex'),'--output',str(output),'--max-bytes','1000','--max-seconds','30']
            with patch.object(READER,'Proxy',Fake),patch.object(READER.sys,'platform','darwin'),patch.object(sys,'argv',argv):
                self.assertEqual(2,READER.main())
            result=json.loads(output.with_suffix('.result.json').read_text())
            self.assertEqual('incomplete',result['status'])
            self.assertFalse(result['output_written'])
            self.assertFalse(result['checkpoint_written'])
            self.assertEqual(selection['window'],result['resume']['window'])
            self.assertFalse(output.exists())
            self.assertEqual(original,state.read_bytes())
            Fake.charge=100
            with patch.object(READER,'Proxy',Fake),patch.object(READER.sys,'platform','darwin'),patch.object(sys,'argv',argv):
                self.assertEqual(0,READER.main())
            export=json.loads(output.read_text())
            self.assertTrue(export['coverage']['complete'])
            self.assertEqual(1,len(export['sessions'][0]['units']))
            self.assertEqual(original,state.read_bytes())


if __name__=='__main__': unittest.main()
