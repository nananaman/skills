"""Bounded official CLI connection to an existing Codex daemon.
"""
import json, os, queue, re, shutil, subprocess, threading, time
from pathlib import Path, PurePosixPath, PureWindowsPath
import codex_wire
from codex_compat import inspect_cli
from common import require, SENSITIVE
RPC_TIMEOUT = 30
READ_METHODS = {'thread/read', 'thread/list', 'thread/turns/list', 'thread/items/list'}


def validate_read_params(method, params):
    require(isinstance(params, dict), 'invalid read parameters')
    if method == 'thread/read':
        require(set(params) == {'threadId', 'includeTurns'} and
                isinstance(params['threadId'], str) and params['threadId'].strip() and
                params['includeTurns'] is False, 'metadata-only read required')
        return
    fields = {'cursor', 'limit', 'sortDirection'}
    if method == 'thread/list':
        fields |= {'archived', 'sortKey', 'sourceKinds', 'useStateDbOnly', 'cwd'}
        require(params.get('useStateDbOnly') is True and params.get('sortKey') == 'updated_at' and
                params.get('sortDirection') == 'desc' and type(params.get('archived')) is bool and
                params.get('sourceKinds') == ['cli', 'vscode', 'exec', 'appServer'] and
                isinstance(params.get('cwd'), list) and params['cwd'] and
                all(isinstance(path, str) and PurePosixPath(path).is_absolute() and
                    '..' not in PurePosixPath(path).parts for path in params['cwd']),
                'metadata-only index parameters required')
    else:
        fields.add('threadId')
        require(isinstance(params.get('threadId'), str) and params['threadId'].strip(), 'thread ID required')
        if method == 'thread/turns/list':
            fields.add('itemsView')
            require(params.get('itemsView') == 'notLoaded', 'turn bodies must not be loaded')
        else:
            fields.add('turnId')
            require(isinstance(params.get('turnId'), str) and params['turnId'].strip(), 'turn ID required')
    require(set(params) <= fields and type(params.get('limit')) is int and 1 <= params['limit'] <= 50 and
            params.get('sortDirection') in {'asc', 'desc'} and
            ('cursor' not in params or isinstance(params['cursor'], str) and params['cursor']),
            'invalid bounded page parameters')


class AcquisitionIncomplete(ValueError):
    """Resource exhaustion is incomplete acquisition, never successful coverage."""


class AcquisitionBudget:
    def __init__(self, max_bytes=64 * 1024 * 1024, max_seconds=300):
        require(type(max_bytes) is int and max_bytes > 0 and
                type(max_seconds) is int and max_seconds > 0, 'invalid acquisition budget')
        self.max_bytes, self.max_seconds = max_bytes, max_seconds
        self.started = time.monotonic()
        self.deadline = self.started + max_seconds
        self.received_bytes = 0

    def check(self):
        if time.monotonic() >= self.deadline:
            raise AcquisitionIncomplete('acquisition time budget exhausted; coverage incomplete')

    def check_request(self):
        self.check()
        if self.received_bytes >= self.max_bytes:
            raise AcquisitionIncomplete('acquisition byte budget exhausted; coverage incomplete')

    def consume(self, size):
        require(type(size) is int and size >= 0, 'invalid received byte count')
        self.received_bytes += size
        if self.received_bytes > self.max_bytes:
            raise AcquisitionIncomplete('acquisition byte budget exhausted; coverage incomplete')
        self.check()

    def usage(self):
        return dict(max_bytes=self.max_bytes, received_bytes=self.received_bytes,
                    max_seconds=self.max_seconds, elapsed_seconds=round(time.monotonic() - self.started, 3))


def iter_pages(proxy, method, params, *, normalize=None, context=None):
    """Replay normalized saved pages, then acquire and persist the next cursor page."""
    cursor = None
    seen = set()
    progress = getattr(proxy, 'progress', None)
    require(progress is None or normalize is not None, 'raw pages must not be persisted')
    while True:
        request = {**params, **({'cursor': cursor} if cursor else {})}
        cached = progress.get(method, request, context) if progress else None
        if cached is None:
            response = proxy.call(method, request)
            require(isinstance(response.get('data'), list) and len(response['data']) <= params['limit'],
                    'invalid page size')
            next_cursor = response.get('nextCursor')
            require(next_cursor is None or isinstance(next_cursor, str) and next_cursor, 'invalid cursor')
            require(next_cursor is None or next_cursor not in seen, 'cursor loop')
            data = normalize(response['data']) if normalize else response['data']
            if progress:
                progress.save(method, request, context, data, next_cursor)
        else:
            data, next_cursor = cached['data'], cached['nextCursor']
            require(next_cursor is None or isinstance(next_cursor, str) and next_cursor, 'invalid cached cursor')
            require(next_cursor is None or next_cursor not in seen, 'cached cursor loop')
        yield data
        if next_cursor is None:
            return
        seen.add(next_cursor)
        cursor = next_cursor


def verify_server_version(agent):
    require(isinstance(agent,str),'unknown app-server userAgent')
    require(all(' '<=char<='~' for char in agent),'unknown app-server userAgent')
    # get_codex_user_agent() prefixes the server build with its originator,
    # which may be a desktop client name rather than "codex_cli_rs".
    match=re.fullmatch(r'([^/]+)/([^\s()]+) \([^()\r\n]+; [^()\r\n]+\)(?: [^\r\n]*)?',agent)
    require(match is not None and match.group(1).strip() and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?', match.group(2)),
            'unknown app-server identity; no thread read attempted')
    return match.group(2)

def absolute_metadata_path(value):
    require(isinstance(value,str) and
            any(path.is_absolute() and '..' not in path.parts
                for path in (PurePosixPath(value),PureWindowsPath(value))),
            'unknown absolute metadata path')

def validate_initialize(result):
    # Required read-handshake fields; no settings are inferred.
    require(isinstance(result,dict) and all(isinstance(result.get(k),str) and result[k]
            for k in ('userAgent','codexHome','platformFamily','platformOs')),
            'unknown read-contract initialize response')
    absolute_metadata_path(result['codexHome'])

def validate_metadata(params,result):
    # Only metadata reads with includeTurns:false are supported.
    thread=result.get('thread')
    required={'cliVersion','createdAt','cwd','ephemeral','id','modelProvider','preview',
              'projectId','sessionId','source','status','turns','updatedAt'}
    require(isinstance(thread,dict) and required<=thread.keys(), 'unknown read-contract thread metadata')
    require(thread['id']==params['threadId'], 'thread read ID mismatch')
    require(all(isinstance(thread[k],str) for k in ('cliVersion','id','modelProvider','preview','sessionId'))
            and all(type(thread[k]) is int for k in ('createdAt','updatedAt'))
            and type(thread['ephemeral']) is bool
            and (thread['projectId'] is None or isinstance(thread['projectId'],str))
            and isinstance(thread['source'],(str,dict)), 'unknown read-contract metadata field type')
    absolute_metadata_path(thread['cwd'])
    require(thread['turns']==[], 'metadata-only read unexpectedly included turns')
    status=thread['status']
    require(isinstance(status,dict) and status.get('type') in {'notLoaded','idle','systemError','active'},
            'unknown read-contract thread status')
    if status['type']=='active':
        require(isinstance(status.get('activeFlags'),list) and
                all(flag in {'waitingOnApproval','waitingOnUserInput'} for flag in status['activeFlags']),
                'unknown read-contract active thread flags')

class Proxy:
    """Use only an existing daemon. Rejections/timeouts stop this source."""
    def __init__(self, config):
        self.process = None
        self.server_version = None
        self.budget = config.get('acquisition_budget') or AcquisitionBudget()
        self.close_lock = threading.Lock()
        env = dict(os.environ)
        inputs = proxy_input(config)
        env['CODEX_HOME'] = inputs['codex_home']
        executable = inputs['codex_executable']
        try:
            self.contract, self.cli_version = inspect_cli(executable, env, self.budget)
            self.process = subprocess.Popen([executable, 'app-server', 'proxy'], env=env,
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.DEVNULL, bufsize=0)
            self.messages = queue.Queue(maxsize=16)
            self.send_lock = threading.Lock()
            key, request = codex_wire.request()
            self.handshake_key = key
            self.reader = threading.Thread(target=self._read, daemon=True)
            self.reader.start()
            deadline=min(time.monotonic()+RPC_TIMEOUT, self.budget.deadline)
            self._write(request,deadline)
            ready=self.messages.get(timeout=max(0,deadline-time.monotonic()))
            require(isinstance(ready,dict) and ready.get('transport_ready'),
                    ready.get('transport_error','WebSocket handshake unavailable') if isinstance(ready,dict)
                    else 'WebSocket handshake unavailable')
            self.sequence = 0
            initialized=self.call('initialize', {'clientInfo': {'name': 'skill-maintenance', 'version': '1'},
                                                 'capabilities': {'experimentalApi': True}})
            self.server_version=verify_server_version(initialized.get('userAgent'))
            validate_initialize(initialized)
            require(isinstance(initialized.get('codexHome'), str) and
                    Path(initialized['codexHome']).is_absolute() and
                    str(Path(initialized['codexHome']).resolve()) == inputs['codex_home'],
                    'app-server CODEX_HOME mismatch; no thread read attempted')
            self._send(json.dumps({'method': 'initialized','params':{}}).encode())
        except AcquisitionIncomplete:
            self.close()
            raise
        except ValueError as error:
            self.close()
            self.budget.check()
            raise ValueError('Codex read-only proxy initialization failed: ' + str(error)) from None
        except (OSError, subprocess.SubprocessError, queue.Empty):
            self.close()
            self.budget.check()
            raise ValueError('Codex read-only proxy unavailable; no fallback attempted') from None

    def _read(self):
        try:
            codex_wire.accept(self.process.stdout,self.handshake_key)
            self.messages.put({'transport_ready':True},timeout=1)
            fragmented=None
            while True:
                self.budget.check()
                final,opcode,payload=codex_wire.receive(self.process.stdout,
                    remaining_budget=self.budget.max_bytes - self.budget.received_bytes)
                self.budget.consume(len(payload))
                if opcode==8:break
                if opcode==9:self._send(payload,10);continue
                if opcode==10:continue
                if opcode==1:
                    require(fragmented is None,'unexpected WebSocket message fragment')
                    fragmented=bytearray(payload)
                else:
                    require(fragmented is not None,'unexpected WebSocket continuation')
                    fragmented.extend(payload)
                require(len(fragmented)<=codex_wire.LIMIT,'RPC response too large')
                if final:
                    message=json.loads(fragmented.decode('utf-8'))
                    require(isinstance(message,dict),'unknown RPC message schema')
                    self.messages.put(message, timeout=RPC_TIMEOUT)
                    fragmented=None
        except (OSError, ValueError, queue.Full) as error:
            try:self.messages.put({'transport_error':str(error), 'budget_exhausted':
                isinstance(error, AcquisitionIncomplete) or str(error).startswith('acquisition byte budget exhausted')},timeout=1)
            except queue.Full:pass
        finally:
            try: self.messages.put(None, timeout=1)
            except queue.Full: pass

    def _write(self,data,deadline):
        # A portable bounded pipe writer. Only this owned proxy child is reaped
        # on timeout; the existing daemon is never terminated or restarted.
        if not self.send_lock.acquire(timeout=max(0,deadline-time.monotonic())):
            self.close()
            self.budget.check()
            raise ValueError('Codex proxy send deadline exceeded')
        errors=[]
        def write():
            try:
                remaining=memoryview(data)
                while remaining:
                    count=self.process.stdin.write(remaining)
                    require(type(count) is int and count>0,'Codex proxy pipe closed')
                    remaining=remaining[count:]
            except (OSError, ValueError) as error:errors.append(error)
            finally:self.send_lock.release()
        writer=threading.Thread(target=write,daemon=True)
        writer.start()
        writer.join(timeout=max(0,deadline-time.monotonic()))
        if writer.is_alive():
            self.close()
            writer.join(timeout=1)
            self.budget.check()
            raise ValueError('Codex proxy send deadline exceeded')
        if errors:
            self.close()
            self.budget.check()
            raise ValueError('Codex proxy send failed') from None

    def _send(self,payload,opcode=1,deadline=None):
        self._write(codex_wire.frame(payload,opcode),
                    min(deadline if deadline is not None else time.monotonic()+RPC_TIMEOUT, self.budget.deadline))

    def call(self, method, params):
        self.budget.check_request()
        require(method in {'initialize', *READ_METHODS},
                'unsupported read method')
        if method!='initialize':
            validate_read_params(method, params)
        self.contract.validate_request(method, params)
        self.sequence += 1
        ident = self.sequence
        try:
            deadline = min(time.monotonic() + RPC_TIMEOUT, self.budget.deadline)
            self._send(json.dumps({'id': ident, 'method': method, 'params': params}).encode('utf-8'),deadline=deadline)
            while True:
                self.budget.check()
                remaining=deadline-time.monotonic()
                require(remaining>0,'Codex RPC response deadline exceeded')
                message = self.messages.get(timeout=remaining)
                require(isinstance(message,dict), 'Codex proxy disconnected or unknown RPC message schema')
                if message.get('budget_exhausted'):
                    raise AcquisitionIncomplete('acquisition resource budget exhausted; coverage incomplete')
                require('transport_error' not in message,'Codex WebSocket transport failed')
                require(not ('method' in message and 'id' in message),'unsupported server-initiated request')
                if message.get('id') == ident:
                    if 'error' in message:
                        error=message['error']
                        require(isinstance(error,dict),'unknown RPC error schema')
                        code=error.get('code');detail=error.get('message','')
                        require(type(code) is int and isinstance(detail,str),'unknown RPC error schema')
                        safe=detail[:256] if detail.startswith(('thread not loaded:','thread not found:')) and not SENSITIVE.search(detail) else 'read rejected'
                        raise ValueError('Codex read RPC '+str(code)+': '+safe)
                    require(isinstance(message.get('result'),dict),'unknown Codex RPC response')
                    self.contract.validate_response(method, message['result'])
                    if method=='thread/read':
                        validate_metadata(params,message['result'])
                    return message['result']
        except (OSError, queue.Empty):
            self.budget.check()
            raise ValueError('Codex read RPC unavailable; no fallback attempted') from None

    def close(self):
        with self.close_lock:
            if self.process:
                if self.process.poll() is None:
                    self.process.terminate()
                    try: self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.process.kill(); self.process.wait(timeout=3)
                for stream in (self.process.stdin, self.process.stdout):
                    if stream: stream.close()

def proxy_input(config):
    home = config.get('codex_home') or os.environ.get('CODEX_HOME') or str(Path.home() / '.codex')
    require(Path(home).is_absolute(), 'CODEX_HOME must be absolute')
    executable = config.get('codex_executable', 'codex')
    resolved = shutil.which(executable)
    # An unavailable command fails at spawn; it never acquires input.
    if resolved or Path(executable).is_absolute() or '/' in executable or '\\' in executable:
        executable = str(Path(resolved or executable).resolve())
    return {'codex_home': str(Path(home).resolve()), 'codex_executable': executable}
