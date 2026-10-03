import copy
import importlib.util
import json
import os
from pathlib import Path, PureWindowsPath
import sys
import subprocess
import tempfile
import io
import queue
import threading
import time
import unittest
from unittest.mock import patch, Mock
from argparse import Namespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'meta/skill-maintenance/scripts'
sys.path.insert(0, str(SCRIPT))
import codex_export as exporter
import maintenance


class ProxyTest(unittest.TestCase):
    def bare(self):
        proxy = exporter.Proxy.__new__(exporter.Proxy)
        proxy.sequence = 0
        proxy.messages = queue.Queue()
        proxy.send_lock = threading.Lock()
        proxy.close_lock = threading.Lock()
        proxy.process = None
        proxy.server_version = exporter.PROTOCOL
        return proxy

    def metadata_fixture(self):
        return json.loads((SCRIPT.parent/'examples/codex-0160-metadata.json').read_text())

    def test_official_0160_metadata_contract_and_normal_not_loaded_status(self):
        data = self.metadata_fixture()
        self.assertEqual('0.160.0', exporter.verify_server_version(data['initialize']['userAgent']))
        exporter.validate_initialize_0160(data['initialize'])
        proxy = self.bare(); proxy.server_version = '0.160.0'; proxy._send = Mock()
        proxy.messages.put({'id':1,'result':data['result']})
        self.assertEqual(data['result'], proxy.call('thread/read', data['params']))

    def test_server_build_version_uses_first_originator_pair_not_later_client_versions(self):
        observed_shape='synthetic-synthetic/0.160.0 (synthetic synthetic 1.0.0; synthetic) synthetic/9.8.7 (synthetic-synthetic; synthetic)'
        self.assertEqual('0.160.0',exporter.verify_server_version(observed_shape))
        for value in (observed_shape.replace('/0.160.0 ', '/0.160.1 '),
                      observed_shape.replace('/0.160.0 ', '/0.160.0-dev '),
                      'unknown/9.8.7 (synthetic synthetic 1.0.0; synthetic) codex_cli_rs/0.160.0'):
            with self.subTest(value=value),self.assertRaises(ValueError):exporter.verify_server_version(value)

    def test_formal_originator_with_spaces_is_supported_without_weakening_version_gate(self):
        value='Codex Desktop/0.160.0 (SyntheticOS 1.0.0; synthetic-arch) synthetic/9.8.7'
        self.assertEqual('0.160.0',exporter.verify_server_version(value))
        for invalid in (value.replace('/0.160.0 ', '/0.160.1 '),value.replace('/0.160.0 ', '/0.160.0-dev '),
                        value.replace('Codex Desktop','Codex\nDesktop')):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):exporter.verify_server_version(invalid)

    def test_0160_unverified_history_and_full_read_are_rejected_before_send(self):
        proxy = self.bare(); proxy.server_version = '0.160.0'; proxy._send = Mock()
        for method, params in [('thread/list',{}),('thread/turns/list',{}),('thread/items/list',{}),
                               ('thread/read',{'threadId':'synthetic-task','includeTurns':True})]:
            with self.subTest(method=method), patch.object(exporter,'RPC_TIMEOUT',.01), self.assertRaises(ValueError):proxy.call(method,params)
        proxy._send.assert_not_called()

    def test_0160_required_metadata_mismatch_and_unexpected_turn_content_are_blocked(self):
        data = self.metadata_fixture()
        for field,value in [('id','other-task'),('createdAt',True),('cwd','relative'),
                            ('ephemeral','false'),('status',{'type':'unknown'}),('turns',[{'id':'unexpected'}])]:
            result=copy.deepcopy(data['result']);result['thread'][field]=value
            proxy=self.bare();proxy.server_version='0.160.0';proxy._send=Mock()
            proxy.messages.put({'id':1,'result':result})
            with self.subTest(field=field),self.assertRaises(ValueError):proxy.call('thread/read',data['params'])

    def test_0160_initialize_requires_official_fields(self):
        for field in ('codexHome','platformFamily','platformOs','userAgent'):
            data=self.metadata_fixture()['initialize'];data.pop(field)
            with self.subTest(field=field),self.assertRaises(ValueError):exporter.validate_initialize_0160(data)

    def test_backpressured_send_times_out_and_reaps_only_owned_proxy(self):
        proxy = self.bare()
        # A local synthetic child never drains stdin; no Codex process or data.
        proxy.process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
        start = time.monotonic()
        try:
            with self.assertRaisesRegex(ValueError, 'send deadline'):
                proxy._write(b'x' * (1024 * 1024), start + .05)
            self.assertIsNotNone(proxy.process.poll())
            self.assertLess(time.monotonic() - start, 4)
        finally:
            proxy.close()

    def test_partial_pipe_writes_preserve_all_request_bytes(self):
        proxy = self.bare()
        received = bytearray()
        def partial(data):
            received.extend(data[:3])
            return min(3, len(data))
        proxy.process = Mock(stdin=Mock(write=partial))
        proxy._write(b'abcdefghij', time.monotonic()+1)
        self.assertEqual(b'abcdefghij', received)

    def test_malformed_initialize_envelopes_reap_owned_proxy(self):
        for message in ([], {'id':1,'result':[]}, {'id':1,'error':[]}):
            with self.subTest(message=message):
                process = Mock(stdin=io.BytesIO(), stdout=io.BytesIO())
                process.poll.return_value = None
                def synthetic_read(proxy):
                    proxy.messages.put({'transport_ready':True})
                    proxy.messages.put(message)
                with patch.object(exporter.subprocess, 'run', return_value=Mock(stdout='codex-cli '+exporter.PROTOCOL)), \
                     patch.object(exporter.subprocess, 'Popen', return_value=process), \
                     patch.object(exporter.Proxy, '_read', synthetic_read), \
                     self.assertRaises(ValueError):
                    exporter.Proxy({})
                process.terminate.assert_called_once()
                self.assertTrue(process.stdin.closed)

    def test_proxy_checks_server_home_before_reads_for_both_versions(self):
        for version in ('0.159.3', '0.160.0'):
            for server_home in ('/fixture/expected', '/fixture/other', None):
                with self.subTest(version=version, home=server_home):
                    process = Mock(stdin=io.BytesIO(), stdout=io.BytesIO())
                    process.poll.return_value = None
                    result = self.metadata_fixture()['initialize']
                    result['userAgent'] = result['userAgent'].replace('0.160.0', version)
                    result['codexHome'] = server_home
                    def synthetic_read(proxy):
                        proxy.messages.put({'transport_ready':True})
                        proxy.messages.put({'id':1,'result':result})
                    with patch.object(exporter.subprocess, 'run', return_value=Mock(stdout='codex-cli '+exporter.PROTOCOL)), \
                         patch.object(exporter.subprocess, 'Popen', return_value=process), \
                         patch.object(exporter.Proxy, '_read', synthetic_read):
                        if server_home == '/fixture/expected':
                            proxy = exporter.Proxy({'codex_home':'/fixture/expected'})
                            self.assertEqual(1, proxy.sequence)  # initialize only
                            proxy.close()
                        else:
                            with self.assertRaises(ValueError): exporter.Proxy({'codex_home':'/fixture/expected'})
                        process.terminate.assert_called_once()

    def test_notifications_do_not_consume_response_count_budget(self):
        proxy = self.bare()
        proxy._send = Mock()
        for _ in range(100): proxy.messages.put({'method':'thread/status/changed','params':{}})
        proxy.messages.put({'id':1,'result':{'data':[]}})
        self.assertEqual({'data':[]}, proxy.call('thread/list', {}))

    def test_notification_flood_still_obeys_deadline(self):
        proxy = self.bare()
        proxy._send = Mock()
        proxy.messages = Mock()
        proxy.messages.get.return_value = {'method':'thread/status/changed','params':{}}
        with patch.object(exporter, 'RPC_TIMEOUT', .01, create=True), self.assertRaises(ValueError):
            proxy.call('thread/list', {})

    def test_server_initiated_request_is_rejected_without_execution(self):
        proxy = self.bare()
        proxy._send = Mock()
        proxy.messages.put({'id':'server-request', 'method':'command/exec', 'params':{}})
        with self.assertRaisesRegex(ValueError,'server-initiated'):
            proxy.call('thread/list', {})


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((SCRIPT.parent / 'examples/codex-source.json').read_text())
        self.data = json.loads((SCRIPT.parent / 'examples/codex-protocol.json').read_text())
        self.target = json.loads((SCRIPT.parent / 'examples/target.json').read_text())

    def run_export(self):
        return exporter.export(exporter.Fixture(self.data), self.config, self.target,
                               '2026-01-02T00:00:00Z', '2026-01-03T00:00:00Z', [])

    def test_completed_only_and_pending_identifiers(self):
        output = self.run_export()
        units = output['sessions'][0]['units']
        self.assertEqual(['completed', 'in-progress'], [u['status'] for u in units])
        self.assertNotIn('content', units[1])
        self.assertTrue(output['coverage']['complete'])

    def test_legacy_output_labels_self_report_and_limited_coverage(self):
        output = self.run_export()
        self.assertTrue(output['sessions'][0]['units'][0]['content']['observed'].startswith(
            'Agent final report (not independently verified):\n'))
        self.assertEqual('app-server-index', output['coverage_notes']['scope'])
        self.assertEqual('synthetic-fixture', output['coverage_notes']['input_kind'])
        self.assertFalse(output['coverage_notes']['snapshot_guaranteed'])
        self.config['thread_ids'] = ['task']
        self.assertEqual('explicit-thread-ids', self.run_export()['coverage_notes']['scope'])

    def test_proxy_selection_binds_effective_home_and_executable(self):
        self.config['transport'] = 'proxy'
        with patch.dict(os.environ, {'CODEX_HOME':'/fixture/home-a'}), patch.object(exporter.shutil, 'which', return_value='/fixture/bin/codex-a'):
            first = exporter.selection(self.config)
        with patch.dict(os.environ, {'CODEX_HOME':'/fixture/home-b'}), patch.object(exporter.shutil, 'which', return_value='/fixture/bin/codex-a'):
            self.assertNotEqual(first, exporter.selection(self.config))
        with patch.dict(os.environ, {'CODEX_HOME':'/fixture/home-a'}), patch.object(exporter.shutil, 'which', return_value='/fixture/bin/codex-b'):
            self.assertNotEqual(first, exporter.selection(self.config))
        self.config['codex_home'] = '/fixture/explicit'
        with patch.dict(os.environ, {'CODEX_HOME':'/fixture/ignored'}):
            self.assertEqual('/fixture/explicit', exporter.selection(self.config)['input']['codex_home'])

    def test_fixture_selection_binds_config_directory(self):
        self.assertNotEqual(exporter.selection(self.config, Path('/fixture/a')),
                            exporter.selection(self.config, Path('/fixture/b')))

    def test_symlink_fixture_stops_before_transport(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'actual.json').write_text(json.dumps(self.data))
            (root/'codex-protocol.json').symlink_to(root/'actual.json')
            with self.assertRaisesRegex(ValueError,'symlink input'):
                exporter.selection(self.config, root)

    def test_completed_copy_supersedes_pending_or_cancelled_copy_in_either_order(self):
        for status in ('inProgress', 'interrupted'):
            for reversed_order in (False, True):
                with self.subTest(status=status, reversed_order=reversed_order):
                    data = copy.deepcopy(self.data)
                    child = copy.deepcopy(data['threads'][0]['data'][0])
                    child.update(id='child',parentThreadId='task')
                    data['threads'][0]['data'].append(child)
                    data['turns']['child'] = copy.deepcopy(data['turns']['task'])
                    data['turns']['child'][0]['data'][0].update(status=status,completedAt=None)
                    if reversed_order: data['threads'][0]['data'].reverse()
                    output = exporter.export(exporter.Fixture(data),self.config,self.target,
                                             '2026-01-02T00:00:00Z','2026-01-03T00:00:00Z',[])
                    copies = [u for s in output['sessions'] for u in s['units'] if u['id']=='turn-1']
                    self.assertEqual(['completed'],[u['status'] for u in copies])

    def test_changed_legacy_input_is_blocked_before_transport_or_state_write(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp); repo=home/'repo'; repo.mkdir()
            source=home/'source.json'; source.write_text(json.dumps(self.config))
            target=home/'target.json'; target.write_text(json.dumps(self.target))
            (home/'codex-protocol.json').write_text(json.dumps(self.data))
            args=Namespace(source=source,target=target,repo=repo,state=home/'private/state.json',
                           output=home/'private/batches',current_root='maintenance',cutoff='2026-01-03T00:00:00Z',
                           since=None,hours=24,exclude_root=[])
            result=maintenance.prepare(args)
            batch=json.loads(Path(result['batch']).read_text())
            self.assertEqual(batch['coverage_notes'], result['coverage_notes'])
            before=args.state.read_bytes()
            self.config['fixture']='other.json'; source.write_text(json.dumps(self.config))
            with patch.object(exporter, 'Fixture', side_effect=AssertionError('must not read')):
                with self.assertRaisesRegex(ValueError,'selection'): maintenance.prepare(args)
            self.assertEqual(before, args.state.read_bytes())

    def test_unknown_protocol_stops(self):
        self.data['protocol_version'] = '0.160.0'
        with self.assertRaises(ValueError): self.run_export()

    def test_unverified_running_server_version_stops_before_read(self):
        exporter.verify_server_version('codex_cli_rs/0.159.3 (SyntheticOS 1.0.0; synthetic-arch) synthetic/9.8.7')
        for agent in ('codex_cli_rs/0.160.1 (macOS 1.0.0)','unknown/0.159.3',None,
                      'codex-cli 0.159.3-dev','codex-cli 0.159.3.1','codex-cli 0.159.3+build'):
            with self.subTest(agent=agent),self.assertRaises(ValueError):exporter.verify_server_version(agent)

    def test_incomplete_pagination_stops(self):
        self.data['threads'][0]['nextCursor'] = 'missing'
        with self.assertRaises(ValueError): self.run_export()

    def test_budget_does_not_become_partial_success(self):
        self.config['max_turns'] = 1
        with self.assertRaises(ValueError): self.run_export()

    def test_unknown_status_stops(self):
        self.data['turns']['task'][0]['data'][0]['status'] = 'newState'
        with self.assertRaises(ValueError): self.run_export()

    def test_missing_completion_timestamp_stops(self):
        self.data['turns']['task'][0]['data'][0]['completedAt'] = None
        with self.assertRaises(ValueError): self.run_export()

    def test_secret_pattern_blocks_without_echoing_content(self):
        self.data['items']['turn-1'][0]['data'][0]['item']['content'][0]['text'] = 'api_key=private-example'
        with self.assertRaisesRegex(ValueError, '^sensitive turn blocked$'): self.run_export()

    def test_excluded_root_never_fetches_items(self):
        self.config['exclude_roots'] = ['task']
        self.data['items'] = {}
        self.assertEqual([], self.run_export()['sessions'][0]['units'])

    def test_parent_scope_mismatch_stops(self):
        self.data['threads'][0]['data'][0]['parentThreadId'] = 'outside'
        with self.assertRaisesRegex(ValueError, 'ancestor'): self.run_export()

    def test_non_final_output_is_not_observed(self):
        self.data['items']['turn-1'][0]['data'][-1]['item']['phase'] = 'commentary'
        with self.assertRaises(ValueError): self.run_export()

    def test_windows_cwd_comparison_is_native_path_aware(self):
        self.config['path_flavour'] = 'windows'
        self.config['repos'][0]['cwd'] = r'C:\Work\App'
        self.data['threads'][0]['data'][0]['cwd'] = 'c:/work/app'
        self.assertEqual(1, len(self.run_export()['sessions']))

    def test_other_scope_is_rejected_before_transport(self):
        self.config['repos'][0]['information_scope'] = 'organization:other'
        with self.assertRaises(ValueError): self.run_export()

    def test_incomplete_items_stops(self):
        self.data['items']['turn-1'][0]['nextCursor'] = 'missing'
        with self.assertRaises(ValueError): self.run_export()

    def test_duplicate_page_rejects(self):
        self.data['threads'][0]['data'] *= 2
        with self.assertRaises(ValueError): self.run_export()

    def test_prepare_replay_and_failed_read_preserve_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            repo = home / 'repo'; repo.mkdir()
            private = home / 'private'
            source = home / 'source.json'
            target = home / 'target.json'
            fixture = home / 'codex-protocol.json'
            source.write_text(json.dumps(self.config))
            target.write_text(json.dumps(self.target))
            fixture.write_text(json.dumps(self.data))
            command = [sys.executable, str(SCRIPT / 'maintenance.py'), 'prepare',
                       '--source', str(source), '--target', str(target), '--repo', str(repo),
                       '--state', str(private / 'state.json'), '--output', str(private / 'batches'),
                       '--current-root', 'maintenance-root', '--cutoff', '2026-01-03T00:00:00Z']
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            original = (private / 'state.json').read_bytes()
            batch = json.loads(Path(json.loads(first.stdout)['batch']).read_text())
            repeated = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, repeated.returncode, repeated.stderr)
            again = json.loads(Path(json.loads(repeated.stdout)['batch']).read_text())
            self.assertEqual(batch['cases'], again['cases'])
            self.assertEqual(1, again['unfinished_units'])
            after = json.loads((private / 'state.json').read_text())
            before = json.loads(original)
            after.pop('batches'); before.pop('batches')
            after.pop('latest_batch'); before.pop('latest_batch')
            self.assertEqual(before, after)
            original = (private / 'state.json').read_bytes()
            self.assertEqual(['maintenance-root'], json.loads(original)['sources'][self.config['source_id']]['excluded_roots'])
            self.data['threads'][0]['nextCursor'] = 'missing'
            fixture.write_text(json.dumps(self.data))
            failed = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(2, failed.returncode)
            self.assertEqual('', failed.stdout)
            self.assertEqual(original, (private / 'state.json').read_bytes())
            self.assertEqual([], list(repo.iterdir()))

    def test_second_page_is_collected(self):
        page = self.data['turns']['task'][0]
        page['nextCursor'] = '1'
        following = {'data': [page['data'].pop()], 'nextCursor': None}
        self.data['turns']['task'].append(following)
        self.assertEqual(2, len(self.run_export()['sessions'][0]['units']))

    def test_old_pending_is_included_even_on_first_run(self):
        self.data['turns']['task'][0]['data'][1]['startedAt'] = 1
        self.assertEqual('in-progress', self.run_export()['sessions'][0]['units'][1]['status'])

    def test_excluded_child_subtree_leaves_root(self):
        child = copy.deepcopy(self.data['threads'][0]['data'][0])
        child.update(id='child', parentThreadId='task')
        self.data['threads'][0]['data'].append(child)
        self.config['exclude_roots'] = ['child']
        result=self.run_export()['sessions']
        self.assertEqual(['task','child'], [s['id'] for s in result])
        self.assertEqual([],result[1]['units'])

    def test_deferred_turn_id_in_other_root_does_not_fetch_old_content(self):
        other=copy.deepcopy(self.data['threads'][0]['data'][0]);other['id']='other-root'
        self.data['threads'][0]['data'].append(other)
        self.data['turns']['other-root']=copy.deepcopy(self.data['turns']['task'])
        old=self.data['turns']['other-root'][0]['data'][0]
        old['completedAt']=1
        adapter=exporter.Fixture(self.data);call=adapter.call
        def checked(method,params):
            if method=='thread/items/list':self.assertNotEqual('other-root',params['threadId'])
            return call(method,params)
        adapter.call=checked
        result=exporter.export(adapter,self.config,self.target,'2026-01-02T00:00:00Z','2026-01-03T00:00:00Z',
                               [{'root_id':'task','unit_id':'turn-1'}])
        self.assertEqual(['in-progress'],[u['status'] for u in result['sessions'][1]['units']])

    def test_source_race_stops(self):
        adapter = exporter.Fixture(self.data)
        call = adapter.call
        count = 0
        def changed(method, params):
            nonlocal count
            if method == 'thread/list':
                count += 1
                if count == 3: self.data['threads'][0]['data'][0]['updatedAt'] += 1
            return call(method, params)
        adapter.call = changed
        with self.assertRaisesRegex(ValueError, 'changed during read'):
            exporter.export(adapter, self.config, self.target, '2026-01-02T00:00:00Z', '2026-01-03T00:00:00Z', [])

    def test_source_cwd_race_between_allowlisted_repos_stops(self):
        self.config['repos'].append({**self.config['repos'][0], 'cwd':'/fixture/another-app'})
        adapter = exporter.Fixture(self.data); call = adapter.call; count = 0
        def changed(method,params):
            nonlocal count
            if method=='thread/list':
                count+=1
                if count==3:self.data['threads'][0]['data'][0]['cwd']='/fixture/another-app'
            return call(method,params)
        adapter.call=changed
        with self.assertRaisesRegex(ValueError,'changed during read'):
            exporter.export(adapter,self.config,self.target,'2026-01-02T00:00:00Z','2026-01-03T00:00:00Z',[])

    def test_unknown_source_kind_is_requested(self):
        adapter = exporter.Fixture(self.data)
        call = adapter.call
        def checked(method, params):
            if method == 'thread/list': self.assertIn('unknown', params['sourceKinds'])
            return call(method, params)
        adapter.call = checked
        exporter.export(adapter, self.config, self.target, '2026-01-02T00:00:00Z', '2026-01-03T00:00:00Z', [])

    def test_prepare_holds_lock_before_adapter_read_and_writes_exact_checked_size(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp); repo = home/'repo'; repo.mkdir()
            source = home/'source.json'; source.write_text(json.dumps(self.config))
            target = home/'target.json'; target.write_text(json.dumps(self.target))
            (home/'codex-protocol.json').write_text(json.dumps(self.data))
            args = Namespace(source=source,target=target,repo=repo,state=home/'private/state.json',
                             output=home/'private/batches',current_root='maintenance',cutoff='2026-01-03T00:00:00Z',
                             since=None,hours=24,exclude_root=[])
            fixture = exporter.Fixture
            def checked(data):
                self.assertTrue(args.state.with_name('state.json.lock').is_dir())
                return fixture(data)
            with patch.object(exporter, 'Fixture', side_effect=checked):
                result = maintenance.prepare(args)
            export_path = Path(result['export'])
            data = json.loads(export_path.read_text())
            self.assertEqual(len(json.dumps(data, ensure_ascii=False, allow_nan=False).encode()), export_path.stat().st_size)
            self.assertFalse(args.state.with_name('state.json.lock').exists())

    def test_explicit_id_scope_never_calls_thread_list_or_other_ids(self):
        self.config['thread_ids'] = ['task']
        adapter = exporter.Fixture(self.data)
        call = adapter.call
        def checked(method, params):
            self.assertNotEqual('thread/list', method)
            self.assertEqual('task', params['threadId'])
            return call(method, params)
        adapter.call = checked
        result = exporter.export(adapter, self.config, self.target, '2026-01-02T00:00:00Z', '2026-01-03T00:00:00Z', [])
        self.assertEqual(['task'], [s['id'] for s in result['sessions']])

    def test_id_scope_rejects_different_returned_id(self):
        self.config['thread_ids'] = ['task']
        self.data['thread_reads'] = {'task': {'thread': {**self.data['threads'][0]['data'][0], 'id':'other'}}}
        with self.assertRaisesRegex(ValueError, 'ID mismatch'): self.run_export()

    def test_empty_or_duplicate_id_scope_fails_before_rpc(self):
        for ids in [[], ['task','task'], [None]]:
            self.config['thread_ids'] = ids
            with self.subTest(ids=ids), patch.object(exporter.Fixture, 'call', side_effect=AssertionError('must not read')):
                with self.assertRaises(ValueError): self.run_export()

    def test_unknown_explicit_id_does_not_fall_back_to_listing(self):
        self.config['thread_ids'] = ['missing']
        adapter = exporter.Fixture(self.data)
        methods = []
        call = adapter.call
        def checked(method, params):
            methods.append(method); return call(method, params)
        adapter.call = checked
        with self.assertRaises((KeyError, ValueError)):
            exporter.export(adapter, self.config, self.target, '2026-01-02T00:00:00Z', '2026-01-03T00:00:00Z', [])
        self.assertEqual(['thread/read'], methods)

    def test_id_scoped_prepare_failure_preserves_state_and_rejects_other_roots(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp); repo=home/'repo'; repo.mkdir()
            self.config['thread_ids']=['task']
            source=home/'source.json';source.write_text(json.dumps(self.config))
            target=home/'target.json';target.write_text(json.dumps(self.target))
            fixture=home/'codex-protocol.json';fixture.write_text(json.dumps(self.data))
            args=Namespace(source=source,target=target,repo=repo,state=home/'private/state.json',
                           output=home/'private/batches',current_root='maintenance',cutoff='2026-01-03T00:00:00Z',
                           since=None,hours=24,exclude_root=[])
            result=maintenance.prepare(args)
            batch=json.loads(Path(result['batch']).read_text())
            self.assertEqual(['task'],[c['root_id'] for c in batch['cases']])
            before=args.state.read_bytes()
            self.data['thread_reads']={};fixture.write_text(json.dumps(self.data))
            with self.assertRaises(KeyError):maintenance.prepare(args)
            self.assertEqual(before,args.state.read_bytes())
            state=json.loads(before)
            next(iter(state['units'].values()))['facts']['root_id']='another-authorized-task'
            args.state.write_text(json.dumps(state))
            with self.assertRaisesRegex(ValueError,'dedicated ID-scoped state'):maintenance.prepare(args)

    def test_not_loaded_items_may_be_omitted_but_cannot_contain_content(self):
        for turn in self.data['turns']['task'][0]['data']: turn.pop('items')
        self.assertTrue(self.run_export()['coverage']['complete'])
        self.data['turns']['task'][0]['data'][0]['items']=[{'private':'content'}]
        with self.assertRaisesRegex(ValueError,'unexpected turn content'):self.run_export()

    def test_prepared_scope_cannot_change_mode_ids_or_source_without_reading(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);repo=home/'repo';repo.mkdir()
            self.config['thread_ids']=['task']
            source=home/'source.json';source.write_text(json.dumps(self.config))
            target=home/'target.json';target.write_text(json.dumps(self.target))
            (home/'codex-protocol.json').write_text(json.dumps(self.data))
            args=Namespace(source=source,target=target,repo=repo,state=home/'private/state.json',
                           output=home/'private/batches',current_root='maintenance',cutoff='2026-01-03T00:00:00Z',
                           since=None,hours=24,exclude_root=[])
            maintenance.prepare(args)
            before=args.state.read_bytes()
            for change in ('index','ids','source'):
                config=copy.deepcopy(self.config)
                if change=='index':config.pop('thread_ids')
                elif change=='ids':config['thread_ids'].append('child')
                else:config['source_id']='different-source'
                source.write_text(json.dumps(config))
                with self.subTest(change=change),patch.object(exporter.Fixture,'call',side_effect=AssertionError('must not read')):
                    with self.assertRaisesRegex(ValueError,'selection|ID-scoped'):
                        maintenance.prepare(args)
                self.assertEqual(before,args.state.read_bytes())


if __name__ == '__main__': unittest.main()
