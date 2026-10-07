"""Owned stdio transport with synthetic pipes; no actual CLI, sessions or server."""
import contextlib
import io
import json
import queue
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugin/skills/skill-maintenance/scripts'))
import codex_proxy as P
import codex_reader as R
from codex_compat import ReadContract, METHODS
from tests.test_reader_compatibility import schemas


def contract():
    request, _ = schemas()
    responses = {method: {'type': 'object', 'required': ['data', 'nextCursor'],
        'properties': {'data': {'type': 'array', 'items': True}, 'nextCursor': {'type': ['string', 'null']}}}
        for method in METHODS}
    responses['initialize'] = {'type': 'object', 'required': ['userAgent', 'codexHome', 'platformFamily', 'platformOs'],
        'properties': {key: {'type': 'string'} for key in ('userAgent', 'codexHome', 'platformFamily', 'platformOs')}}
    responses['thread/read'] = {'type': 'object', 'required': ['thread'], 'properties': {'thread': True}}
    return ReadContract(request, responses)


class SyntheticServer:
    def __init__(self, command, **kwargs):
        self.command, self.requests, self.terminated = command, [], False
        self.responses = queue.Queue()
        self.pending = b''
        self.stdout = self
        self.stdin = self.Input(self)
        self.home = kwargs['env']['CODEX_HOME']
        self.wrong_home = False
        self.bad_response = False
        self.active = False
        self.start = int(R.instant('2026-10-03T00:00:00Z').timestamp())

    class Input:
        def __init__(self, owner): self.owner = owner
        def write(self, data):
            request = json.loads(bytes(data))
            if 'id' in request:
                self.owner.requests.append(request)
                result = self.owner.respond(request['method'], request['params'])
                self.owner.responses.put((json.dumps({'id': request['id'], 'result': result}) + '\n').encode())
            return len(data)
        def close(self): pass

    def respond(self, method, params):
        if method == 'initialize':
            return {'userAgent': 'codex_cli_rs/0.159.2 (Mac OS; arm64)',
                'codexHome': '/another/home' if self.wrong_home else self.home,
                'platformFamily': 'unix', 'platformOs': 'macos'}
        metadata = {'id': 'root', 'sessionId': 'root', 'createdAt': self.start,
            'updatedAt': self.start+10, 'source': 'cli', 'cwd': str(Path.home()/'fixture'),
            'path': str(Path(self.home)/'synthetic.jsonl'), 'turns': [], 'ephemeral': False,
            'status': {'type': 'active', 'activeFlags': []} if self.active else {'type': 'idle'},
            'gitInfo': {'originUrl': 'https://github.com/example/project.git'},
            'cliVersion': '0.159.2', 'modelProvider': 'synthetic', 'preview': 'password: never-save-preview', 'projectId': None}
        if method == 'thread/read': return {'thread': metadata}
        if method == 'thread/list':
            result = {'data': [] if params['archived'] else [metadata], 'nextCursor': None}
            if self.bad_response: result['unknown'] = True
            return result
        if method == 'thread/turns/list':
            return {'data': [{'id': 'turn', 'status': 'completed', 'startedAt': self.start,
                'completedAt': self.start+1, 'items': [], 'itemsView': 'notLoaded'}], 'nextCursor': None}
        if method == 'thread/items/list':
            return {'data': [{'turnId': 'turn', 'item': item} for item in [
                {'id': 'u', 'type': 'userMessage', 'content': [{'type': 'text', 'text': 'Check the synthetic fixture.'}]},
                {'id': 'a', 'type': 'agentMessage', 'text': 'Synthetic checks recorded.'}]], 'nextCursor': None}
        raise AssertionError('unsupported synthetic RPC')

    def readline(self, limit):
        if not self.pending:
            self.pending = self.responses.get(timeout=2)
        result, self.pending = self.pending[:limit], self.pending[limit:]
        return result
    def poll(self): return 0 if self.terminated else None
    def terminate(self):
        self.terminated = True
        self.responses.put(b'')
    def wait(self, timeout=None): return 0
    def close(self): self.terminate()


class StdioTest(unittest.TestCase):
    def config(self):
        return {'codex_home': str(Path.home()/'.codex'), 'codex_executable': 'synthetic-codex',
                'transport': 'local-stdio', 'start_local_server': True,
                'acquisition_budget': P.AcquisitionBudget(100000, 10)}

    def test_explicit_opt_in_required_before_cli_or_spawn(self):
        for changes in ({'start_local_server': False}, {'transport': 'unknown'}, {'transport': 'proxy'}):
            with patch.object(P, 'inspect_cli') as inspect, patch.object(P.subprocess, 'Popen') as spawn:
                with self.assertRaises(ValueError): P.Proxy({**self.config(), **changes})
                inspect.assert_not_called(); spawn.assert_not_called()

    def test_missing_daemon_never_automatically_starts_stdio(self):
        config = self.config(); config.pop('transport'); config.pop('start_local_server')
        with patch.object(P, 'inspect_cli', return_value=(contract(), 'codex-cli 0.159.2')), \
             patch.object(P.subprocess, 'Popen', side_effect=OSError('synthetic absent socket')) as spawn:
            with self.assertRaises(ValueError): P.Proxy(config)
        self.assertEqual(1, spawn.call_count)
        self.assertEqual(['app-server', 'proxy'], spawn.call_args.args[0][-2:])

    def test_owned_stdio_handshake_read_contract_and_cleanup(self):
        children = []
        def spawn(*args, **kwargs):
            child = SyntheticServer(*args, **kwargs); children.append(child); return child
        with patch.object(P, 'inspect_cli', return_value=(contract(), 'codex-cli 0.159.2')), \
             patch.object(P.subprocess, 'Popen', side_effect=spawn):
            reader = P.Proxy(self.config())
            try:
                result = reader.call('thread/list', {'archived': True, 'sortKey': 'updated_at', 'sortDirection': 'desc',
                    'sourceKinds': ['cli', 'vscode', 'exec', 'appServer'], 'useStateDbOnly': True,
                    'cwd': [str(Path.home()/'fixture')], 'limit': 50})
                self.assertEqual([], result['data'])
                for method in ('thread/read', 'thread/turns/list', 'thread/items/list'):
                    with self.assertRaisesRegex(ValueError, 'cross-process live status is unverified'):
                        reader.call(method, {})
                self.assertEqual('0.159.2', reader.server_version)
                with self.assertRaises(ValueError): reader.call('turn/start', {})
            finally: reader.close()
        self.assertEqual(['app-server', '--listen', 'stdio://'], children[0].command[-3:])
        self.assertTrue(children[0].terminated)

    def test_wrong_home_blocks_before_history_calls(self):
        children = []
        def spawn(*args, **kwargs):
            child = SyntheticServer(*args, **kwargs); child.wrong_home = True; children.append(child); return child
        with patch.object(P, 'inspect_cli', return_value=(contract(), 'codex-cli 0.159.2')), \
             patch.object(P.subprocess, 'Popen', side_effect=spawn):
            with self.assertRaisesRegex(ValueError, 'CODEX_HOME mismatch'): P.Proxy(self.config())
        self.assertEqual(['initialize'], [r['method'] for r in children[0].requests])
        self.assertTrue(children[0].terminated)

    def test_unknown_response_fields_stop(self):
        def spawn(*args, **kwargs):
            child = SyntheticServer(*args, **kwargs); child.bad_response = True; return child
        with patch.object(P, 'inspect_cli', return_value=(contract(), 'codex-cli 0.159.2')), \
             patch.object(P.subprocess, 'Popen', side_effect=spawn):
            reader = P.Proxy(self.config())
            try:
                with self.assertRaisesRegex(ValueError, 'unknown read response schema'):
                    reader.call('thread/list', {'archived': False, 'sortKey': 'updated_at', 'sortDirection': 'desc',
                        'sourceKinds': ['cli', 'vscode', 'exec', 'appServer'], 'useStateDbOnly': True,
                        'cwd': [str(Path.home()/'fixture')], 'limit': 50})
            finally: reader.close()

    def test_stdio_reads_no_bytes_beyond_budget(self):
        proxy = P.Proxy.__new__(P.Proxy)
        proxy.transport = 'local-stdio'; proxy.messages = queue.Queue()
        proxy.budget = P.AcquisitionBudget(8, 10)
        source = io.BytesIO(b'{"id":12345}\n')
        proxy.process = type('Owned', (), {'stdout': source})()
        proxy._read()
        self.assertEqual({'transport_ready': True}, proxy.messages.get_nowait())
        self.assertTrue(proxy.messages.get_nowait()['budget_exhausted'])
        self.assertEqual(8, source.tell())
        self.assertEqual(8, proxy.budget.received_bytes)

    def test_index_preserves_minimization_binding_and_turn_body_stages_block(self):
        children = []
        def spawn(*args, **kwargs):
            child = SyntheticServer(*args, **kwargs); children.append(child); return child
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); state = root/'state.json'; source = root/'source.json'
            source.write_text(json.dumps({'version': 1, 'source_id': 'synthetic', 'device_id': 'fixture',
                'host_id': 'local', 'path_flavour': 'posix', 'exclude_roots': [], 'repos': [{
                    'id': 'example/project', 'cwd': str(Path.home()/'fixture'), 'information_scope': 'personal:example'}]}))
            common = ['--repo', str(ROOT), '--transport', 'local-stdio', '--start-local-server', '--codex-home',
                str(Path.home()/'.codex'), '--codex-executable', 'synthetic-codex', '--state', str(state)]
            with patch.object(P, 'inspect_cli', return_value=(contract(), 'codex-cli 0.159.2')), \
                 patch.object(P.subprocess, 'Popen', side_effect=spawn), patch.object(R.sys, 'platform', 'darwin'):
                args = ['reader', 'index', *common, '--source', str(source), '--since', '2026-10-03T00:00:00Z',
                    '--cutoff', '2026-10-04T00:00:00Z', '--output', str(root/'index.json')]
                with patch.object(sys, 'argv', args), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(0, R.main())
                self.assertFalse(state.exists())
                self.assertNotIn('never-save-preview', (root/'index.progress.json').read_text())
                self.assertEqual('authorized-owned-local-stdio-v1', json.loads((root/'index.progress.json').read_text())['binding']['transport'])
                for action in ('turns', 'read'):
                    args = ['reader', action, *common, '--selection', str(root/'index.json'), '--read-completed',
                        '--output', str(root/(action+'.json'))]
                    before = len(children)
                    with patch.object(sys, 'argv', args), contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(2, R.main())
                    self.assertEqual(before, len(children))
                    result = json.loads((root/(action+'.result.json')).read_text())
                    self.assertFalse(result['checkpoint_written'])
                    self.assertFalse(result['output_written'])
                    self.assertFalse((root/(action+'.json')).exists())
                    self.assertFalse((root/(action+'.progress.json')).exists())
            self.assertTrue(all(child.terminated for child in children))
            self.assertTrue(all(request['method'] in {'initialize','thread/list'}
                for child in children for request in child.requests))

    def test_final_index_response_followed_by_byte_exhaustion_is_incomplete(self):
        # 最後の応答より後に受信した未完通知も、取得の失敗として確定前に検出する。
        stopped = threading.Event()
        children = []
        original_read, original_index = P.Proxy._read, R.index

        class TrailingNotificationServer(SyntheticServer):
            class Input(SyntheticServer.Input):
                def write(self, data):
                    count = super().write(data)
                    request = json.loads(bytes(data))
                    if request.get('method') == 'thread/list' and request['params']['archived']:
                        self.owner.responses.put(b'{' + b' ' * 4096)
                    return count

        def spawn(*args, **kwargs):
            child = TrailingNotificationServer(*args, **kwargs)
            children.append(child)
            return child

        def receive(proxy):
            try:
                original_read(proxy)
            finally:
                stopped.set()

        def index(*args, **kwargs):
            result = original_index(*args, **kwargs)
            self.assertTrue(stopped.wait(1), 'synthetic trailing input was not consumed')
            return result

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/'source.json'
            source.write_text(json.dumps({'version': 1, 'source_id': 'synthetic', 'device_id': 'fixture',
                'host_id': 'local', 'path_flavour': 'posix', 'exclude_roots': [], 'repos': [{
                    'id': 'example/project', 'cwd': str(Path.home()/'fixture'),
                    'information_scope': 'personal:example'}]}))
            args = ['reader', 'index', '--repo', str(ROOT), '--transport', 'local-stdio',
                '--start-local-server', '--codex-home', str(root/'synthetic-home'),
                '--source', str(source), '--state', str(root/'state.json'), '--max-bytes', '4096',
                '--since', '2026-10-03T00:00:00Z', '--cutoff', '2026-10-04T00:00:00Z',
                '--output', str(root/'index.json')]
            with patch.object(P, 'inspect_cli', return_value=(contract(), 'codex-cli 0.159.2')), \
                 patch.object(P.subprocess, 'Popen', side_effect=spawn), \
                 patch.object(P.Proxy, '_read', receive), patch.object(R, 'index', index), \
                 patch.object(R.sys, 'platform', 'darwin'), patch.object(sys, 'argv', args), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(2, R.main())
            result = json.loads((root/'index.result.json').read_text())
            self.assertEqual('incomplete', result['status'])
            self.assertFalse(result['output_written'])
            self.assertFalse(result['checkpoint_written'])
            self.assertFalse((root/'index.json').exists())
            self.assertFalse((root/'state.json').exists())
            self.assertTrue(children[0].terminated)

    def test_complete_final_response_at_exact_byte_limit_commits_index(self):
        # 完全な最終応答で上限ちょうどに達しても、追加取得が不要なら成功できる。
        budget = P.AcquisitionBudget(4096, 10)
        stopped = threading.Event()
        original_read, original_index = P.Proxy._read, R.index

        class ExactBudgetServer(SyntheticServer):
            def respond(self, method, params):
                result = super().respond(method, params)
                if method == 'thread/list' and params['archived']:
                    final = (json.dumps({'id': self.requests[-1]['id'], 'result': result}) + '\n').encode()
                    budget.max_bytes = budget.received_bytes + len(final)
                return result

        def receive(proxy):
            try:
                original_read(proxy)
            finally:
                stopped.set()

        def index(*args, **kwargs):
            result = original_index(*args, **kwargs)
            self.assertTrue(stopped.wait(1), 'synthetic receiver did not reach exact limit')
            return result

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/'source.json'
            source.write_text(json.dumps({'version': 1, 'source_id': 'synthetic', 'device_id': 'fixture',
                'host_id': 'local', 'path_flavour': 'posix', 'exclude_roots': [], 'repos': [{
                    'id': 'example/project', 'cwd': str(Path.home()/'fixture'),
                    'information_scope': 'personal:example'}]}))
            args = ['reader', 'index', '--repo', str(ROOT), '--transport', 'local-stdio',
                '--start-local-server', '--codex-home', str(root/'synthetic-home'),
                '--source', str(source), '--state', str(root/'state.json'),
                '--since', '2026-10-03T00:00:00Z', '--cutoff', '2026-10-04T00:00:00Z',
                '--output', str(root/'index.json')]
            with patch.object(P, 'inspect_cli', return_value=(contract(), 'codex-cli 0.159.2')), \
                 patch.object(P.subprocess, 'Popen', side_effect=ExactBudgetServer), \
                 patch.object(P.Proxy, '_read', receive), patch.object(R, 'index', index), \
                 patch.object(R, 'AcquisitionBudget', return_value=budget), \
                 patch.object(R.sys, 'platform', 'darwin'), patch.object(sys, 'argv', args), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, R.main())
            result = json.loads((root/'index.result.json').read_text())
            self.assertEqual('index-selection-verified', result['status'])
            self.assertTrue(result['output_written'])
            self.assertFalse(result['checkpoint_written'])
            self.assertEqual(budget.max_bytes, budget.received_bytes)
            self.assertTrue((root/'index.json').exists())


if __name__ == '__main__': unittest.main()
