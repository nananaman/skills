"""Read-only Codex adapter: 0.159.3 export, 0.160.0 metadata-only read.

No SQLite/rollout fallback, daemon startup, index repair or model execution.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import queue
import re
import shutil
import subprocess
import threading
import time
import codex_wire

from maintenance import require, instant, stamp, text_id

PROTOCOL = '0.159.3'
RPC_TIMEOUT = 30
READ_METHODS = {'thread/read', 'thread/list', 'thread/turns/list', 'thread/items/list'}
SERVER_METHODS = {PROTOCOL: READ_METHODS, '0.160.0': {'thread/read'}}
SENSITIVE = re.compile(r'(?i)(api[_-]?key\s*[:=]|password\s*[:=]|secret\s*[:=]|bearer\s+|-----BEGIN.*PRIVATE KEY|sk-[a-z0-9]{12}|gh[pousr]_[a-z0-9]{12})')


def verify_server_version(agent):
    require(isinstance(agent,str),'unknown app-server userAgent')
    require(all(' '<=char<='~' for char in agent),'unknown app-server userAgent')
    # get_codex_user_agent() prefixes the server build with its originator,
    # which may be a desktop client name rather than "codex_cli_rs".
    match=re.fullmatch(r'([^/]+)/([^\s()]+) \([^()\r\n]+; [^()\r\n]+\)(?: [^\r\n]*)?',agent)
    require(match is not None and match.group(1).strip() and match.group(2) in SERVER_METHODS,
            'unsupported or unverified app-server version; no thread read attempted')
    return match.group(2)


def absolute_metadata_path(value):
    require(isinstance(value,str) and
            any(path.is_absolute() and '..' not in path.parts
                for path in (PurePosixPath(value),PureWindowsPath(value))),
            'unknown absolute metadata path')


def validate_initialize_0160(result):
    # Public rust-v0.160.0 v1/InitializeResponse; no settings are inferred.
    require(isinstance(result,dict) and all(isinstance(result.get(k),str) and result[k]
            for k in ('userAgent','codexHome','platformFamily','platformOs')),
            'unknown 0.160.0 initialize response')
    absolute_metadata_path(result['codexHome'])


def validate_metadata_0160(params,result):
    # Only the explicitly verified includeTurns:false contract is supported.
    thread=result.get('thread')
    required={'cliVersion','createdAt','cwd','ephemeral','id','modelProvider','preview',
              'projectId','sessionId','source','status','turns','updatedAt'}
    require(isinstance(thread,dict) and required<=thread.keys(), 'unknown 0.160.0 thread metadata')
    require(thread['id']==params['threadId'], 'thread read ID mismatch')
    require(all(isinstance(thread[k],str) for k in ('cliVersion','id','modelProvider','preview','sessionId'))
            and all(type(thread[k]) is int for k in ('createdAt','updatedAt'))
            and type(thread['ephemeral']) is bool
            and (thread['projectId'] is None or isinstance(thread['projectId'],str))
            and isinstance(thread['source'],(str,dict)), 'unknown 0.160.0 metadata field type')
    absolute_metadata_path(thread['cwd'])
    require(thread['turns']==[], 'metadata-only read unexpectedly included turns')
    status=thread['status']
    require(isinstance(status,dict) and status.get('type') in {'notLoaded','idle','systemError','active'},
            'unknown 0.160.0 thread status')
    if status['type']=='active':
        require(isinstance(status.get('activeFlags'),list) and
                all(flag in {'waitingOnApproval','waitingOnUserInput'} for flag in status['activeFlags']),
                'unknown 0.160.0 active thread flags')


class Fixture:
    """Synthetic app-server pages. Never read live sessions through this transport."""
    def __init__(self, data):
        require(data['protocol_version'] == PROTOCOL, 'unsupported Codex protocol version')
        self.data = data

    def call(self, method, params):
        if method == 'thread/read':
            return self.data['thread_reads'][params['threadId']]
        elif method == 'thread/list':
            pages = self.data['archived_threads'] if params['archived'] else self.data['threads']
        elif method == 'thread/turns/list':
            pages = self.data['turns'][params['threadId']]
        elif method == 'thread/items/list':
            pages = self.data['items'][params['turnId']]
        else:
            raise ValueError('unsupported read method')
        cursor = params.get('cursor')
        index = 0 if cursor is None else int(cursor)
        require(index < len(pages), 'incomplete fixture pages')
        return pages[index]

    def close(self): pass


class Proxy:
    """Use only an existing daemon. Rejections/timeouts stop this source."""
    def __init__(self, config):
        self.process = None
        self.server_version = None
        self.close_lock = threading.Lock()
        env = dict(os.environ)
        inputs = proxy_input(config)
        env['CODEX_HOME'] = inputs['codex_home']
        executable = inputs['codex_executable']
        try:
            result = subprocess.run([executable, '--version'], env=env, capture_output=True,
                                    text=True, timeout=15, check=True)
            require(result.stdout.strip() == 'codex-cli ' + PROTOCOL, 'unsupported Codex CLI version')
            self.process = subprocess.Popen([executable, 'app-server', 'proxy'], env=env,
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.DEVNULL, bufsize=0)
            self.messages = queue.Queue(maxsize=16)
            self.send_lock = threading.Lock()
            key, request = codex_wire.request()
            self.handshake_key = key
            self.reader = threading.Thread(target=self._read, daemon=True)
            self.reader.start()
            deadline=time.monotonic()+RPC_TIMEOUT
            self._write(request,deadline)
            ready=self.messages.get(timeout=max(0,deadline-time.monotonic()))
            require(isinstance(ready,dict) and ready.get('transport_ready'),
                    ready.get('transport_error','WebSocket handshake unavailable') if isinstance(ready,dict)
                    else 'WebSocket handshake unavailable')
            self.sequence = 0
            initialized=self.call('initialize', {'clientInfo': {'name': 'skill-maintenance', 'version': '1'},
                                                 'capabilities': {'experimentalApi': True}})
            self.server_version=verify_server_version(initialized.get('userAgent'))
            if self.server_version=='0.160.0':validate_initialize_0160(initialized)
            require(isinstance(initialized.get('codexHome'), str) and
                    Path(initialized['codexHome']).is_absolute() and
                    str(Path(initialized['codexHome']).resolve()) == inputs['codex_home'],
                    'app-server CODEX_HOME mismatch; no thread read attempted')
            self._send(json.dumps({'method': 'initialized','params':{}}).encode())
        except ValueError as error:
            self.close()
            raise ValueError('Codex read-only proxy initialization failed: ' + str(error)) from None
        except (OSError, subprocess.SubprocessError, queue.Empty):
            self.close()
            raise ValueError('Codex read-only proxy unavailable; no fallback attempted') from None

    def _read(self):
        try:
            codex_wire.accept(self.process.stdout,self.handshake_key)
            self.messages.put({'transport_ready':True},timeout=1)
            fragmented=None
            while True:
                final,opcode,payload=codex_wire.receive(self.process.stdout)
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
            try:self.messages.put({'transport_error':str(error)},timeout=1)
            except queue.Full:pass
        finally:
            try: self.messages.put(None, timeout=1)
            except queue.Full: pass

    def _write(self,data,deadline):
        # A portable bounded pipe writer. Only this owned proxy child is reaped
        # on timeout; the existing daemon is never terminated or restarted.
        if not self.send_lock.acquire(timeout=max(0,deadline-time.monotonic())):
            self.close()
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
            raise ValueError('Codex proxy send deadline exceeded')
        if errors:
            self.close()
            raise ValueError('Codex proxy send failed') from None

    def _send(self,payload,opcode=1,deadline=None):
        self._write(codex_wire.frame(payload,opcode),
                    deadline if deadline is not None else time.monotonic()+RPC_TIMEOUT)

    def call(self, method, params):
        require(method in {'initialize', *READ_METHODS},
                'unsupported read method')
        if method!='initialize':
            require(method in SERVER_METHODS.get(self.server_version,set()),
                    'method not validated for this app-server version')
            if self.server_version=='0.160.0':
                require(isinstance(params,dict) and set(params)=={'threadId','includeTurns'}
                        and isinstance(params['threadId'],str) and params['threadId'].strip()
                        and params['includeTurns'] is False, '0.160.0 supports explicit metadata-only read')
        self.sequence += 1
        ident = self.sequence
        try:
            deadline = time.monotonic() + RPC_TIMEOUT
            self._send(json.dumps({'id': ident, 'method': method, 'params': params}).encode('utf-8'),deadline=deadline)
            while True:
                remaining=deadline-time.monotonic()
                require(remaining>0,'Codex RPC response deadline exceeded')
                message = self.messages.get(timeout=remaining)
                require(isinstance(message,dict), 'Codex proxy disconnected or unknown RPC message schema')
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
                    if self.server_version=='0.160.0' and method=='thread/read':
                        validate_metadata_0160(params,message['result'])
                    return message['result']
        except (OSError, queue.Empty):
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


def pages(transport, method, params, budget):
    values, cursors = [], set()
    cursor = None
    while True:
        response = transport.call(method, {**params, 'cursor': cursor, 'limit': min(budget, 100)})
        require(isinstance(response.get('data'), list), 'unknown page schema')
        values.extend(response['data'])
        require(len(values) <= budget, 'source budget exhausted; coverage incomplete')
        following = response.get('nextCursor')
        if following is None: return values
        require(isinstance(following, str) and following not in cursors, 'invalid pagination cursor')
        cursors.add(following); cursor = following


def path_key(value, flavour):
    cls = PureWindowsPath if flavour == 'windows' else PurePosixPath
    path = cls(value)
    require(path.is_absolute() and '..' not in path.parts, 'source cwd must be absolute and normalized')
    return str(path).casefold() if flavour == 'windows' else str(path)


def epoch(value):
    require(type(value) is int, 'unknown turn timestamp')
    return datetime.fromtimestamp(value, timezone.utc)


def proxy_input(config):
    home = config.get('codex_home') or os.environ.get('CODEX_HOME') or str(Path.home() / '.codex')
    require(Path(home).is_absolute(), 'CODEX_HOME must be absolute')
    executable = config.get('codex_executable', 'codex')
    resolved = shutil.which(executable)
    # An unavailable command fails at spawn; it never acquires input.
    if resolved or Path(executable).is_absolute() or '/' in executable or '\\' in executable:
        executable = str(Path(resolved or executable).resolve())
    return {'codex_home': str(Path(home).resolve()), 'codex_executable': executable}


def selection(config, source_dir=None):
    """Stable input boundary; changing it requires a separate private state."""
    require(config['version'] == 1 and config['protocol_version'] == PROTOCOL, 'unsupported source version')
    flavour = config['path_flavour']
    require(flavour in {'posix', 'windows'}, 'unknown path flavour')
    ids = config.get('thread_ids')
    if 'thread_ids' in config:
        require(isinstance(ids, list) and ids and all(isinstance(x, str) and x.strip() for x in ids),
                'invalid thread ID allowlist')
        require(len(ids) == len(set(ids)), 'duplicate thread ID allowlist')
    repositories = [{'id': r['id'], 'cwd': path_key(r['cwd'], flavour),
                     'information_scope': r['information_scope']} for r in config['repos']]
    if config['transport'] == 'fixture':
        fixture = (source_dir or Path.cwd()) / config['fixture']
        require(not fixture.is_symlink(), 'symlink input is not supported')
        inputs = {'fixture': os.path.abspath(fixture)}
    else:
        inputs = proxy_input(config)
    return {'adapter': 'codex', 'protocol_version': PROTOCOL, 'transport': config['transport'],
            'input': inputs,
            'mode': 'thread-ids' if ids is not None else 'repo-index',
            'thread_ids': sorted(ids) if ids is not None else None, 'path_flavour': flavour,
            'repos': sorted(repositories, key=lambda r: (r['cwd'], r['id']))}


def content(items):
    requests, finals = [], []
    for entry in items:
        item = entry['item']
        if item['type'] == 'userMessage':
            for part in item['content']:
                require(part['type'] == 'text', 'non-text request requires separate adapter')
                requests.append(part['text'])
        elif item['type'] == 'agentMessage' and item.get('phase') == 'final_answer':
            finals.append(item['text'])
    request, observed = '\n'.join(requests), '\n'.join(finals)
    require(request.strip() and observed.strip(), 'turn lacks explicit request or final answer')
    require(not SENSITIVE.search(request + '\n' + observed), 'sensitive turn blocked')
    # No inferred success/expected outcome: evaluation must derive criteria from the request.
    return {'request': request, 'expected': 'Original request requirements; outcome not independently verified.',
            'observed': 'Agent final report (not independently verified):\n' + observed}


def export(transport, config, target, since, cutoff, deferred):
    require(config['version'] == 1 and config['protocol_version'] == PROTOCOL, 'unsupported source version')
    source = text_id(config['source_id'])
    flavour = config['path_flavour']
    require(flavour in {'posix', 'windows'}, 'unknown path flavour')
    repositories = {}
    for repo in config['repos']:
        require(repo['id'] in target['source_repos'] and
                repo['information_scope'] == target['information_scope'], 'source repo/scope mismatch')
        key = path_key(repo['cwd'], flavour)
        require(key not in repositories, 'duplicate source cwd')
        repositories[key] = repo
    require(repositories, 'source repo allowlist required')
    for key in ['max_threads', 'max_turns', 'max_content_turns', 'max_items']:
        require(type(config[key]) is int and config[key] > 0, 'invalid source budget')
    start, end = instant(since), instant(cutoff)
    require(start < end, 'invalid source window')
    thread_ids = config.get('thread_ids')
    if 'thread_ids' in config:
        require(isinstance(thread_ids, list) and thread_ids and
                all(isinstance(x, str) and x.strip() for x in thread_ids), 'invalid thread ID allowlist')
        require(len(thread_ids) == len(set(thread_ids)) and len(thread_ids) <= config['max_threads'],
                'duplicate or excessive thread ID allowlist')
    params = {'cwd': [r['cwd'] for r in config['repos']], 'useStateDbOnly': True,
              'sortKey': 'updated_at', 'sortDirection': 'asc',
              'sourceKinds': ['cli', 'vscode', 'exec', 'appServer', 'subAgent',
                              'subAgentReview', 'subAgentCompact', 'subAgentThreadSpawn', 'subAgentOther', 'unknown']}
    def inventory():
        rows = []
        if thread_ids is not None:
            for ident in thread_ids:
                response = transport.call('thread/read', {'threadId': ident, 'includeTurns': False})
                thread = response['thread']
                require(thread['id'] == ident, 'thread ID mismatch')
                require(not thread.get('turns'), 'unexpected metadata turn content')
                rows.append(thread)
        else:
            for archived in [False, True]:
                rows.extend(pages(transport, 'thread/list', {**params, 'archived': archived}, config['max_threads']))
        require(len(rows) <= config['max_threads'], 'source thread budget exhausted')
        by_id = {text_id(t['id']): t for t in rows}
        require(len(by_id) == len(rows), 'duplicate thread page')
        for t in rows:
            require(path_key(t['cwd'], flavour) in repositories, 'server returned out-of-scope thread')
            require(type(t['updatedAt']) is int and type(t['createdAt']) is int, 'unknown thread schema')
            require(not t.get('ephemeral') and not t.get('forkedFromId'), 'ephemeral/fork history unsupported')
        return by_id
    threads = inventory()
    markers = lambda rows: {k: (v['updatedAt'], v['createdAt'], v.get('parentThreadId'),
                               path_key(v['cwd'], flavour)) for k,v in rows.items()}
    initial_markers = markers(threads)
    def root_of(ident):
        seen = set()
        while threads[ident].get('parentThreadId'):
            require(ident not in seen, 'ancestor cycle')
            seen.add(ident)
            parent = threads[ident]['parentThreadId']
            require(parent in threads, 'missing or out-of-scope ancestor')
            require(path_key(threads[parent]['cwd'], flavour) == path_key(threads[ident]['cwd'], flavour),
                    'ancestor source mismatch')
            ident = parent
        return ident
    roots = {ident: root_of(ident) for ident in threads}
    excluded = set(config['exclude_roots'])
    require(all(isinstance(x, str) for x in excluded), 'invalid exclusions')
    sessions, fetched, turns_seen, canonical = [], 0, 0, {}
    deferred_ids = {(d['root_id'],d['unit_id']) for d in deferred}
    for ident, thread in threads.items():
        root = roots[ident]
        ancestors = {ident, root}
        node = ident
        while threads[node].get('parentThreadId'):
            node = threads[node]['parentThreadId']; ancestors.add(node)
        repo = repositories[path_key(thread['cwd'], flavour)]
        units = []
        # Retain metadata headers for every selected ID, including explicit
        # exclusions, so the collector can prove ID coverage without body reads.
        sessions.append({'id': ident, 'root_id': root, 'parent_id': thread.get('parentThreadId'),
                         'source_repo': repo['id'], 'information_scope': repo['information_scope'],
                         'kind': 'work', 'units': units})
        if ancestors & excluded: continue
        turns = pages(transport, 'thread/turns/list', {'threadId': ident, 'itemsView': 'notLoaded',
                                                    'sortDirection': 'asc'}, config['max_turns'])
        turns_seen += len(turns)
        require(turns_seen <= config['max_turns'], 'source turn budget exhausted')
        require(len({t['id'] for t in turns}) == len(turns), 'duplicate turn page')
        for turn in turns:
            uid = text_id(turn['id']); status = turn['status']
            require(turn.get('itemsView') == 'notLoaded' and turn.get('items', []) == [], 'unexpected turn content')
            require(status in {'completed', 'inProgress', 'failed', 'interrupted'}, 'unknown turn status')
            updated = epoch(turn['completedAt'] if status == 'completed' else turn['startedAt'])
            if updated > end: continue
            unit = {'id': uid, 'revision': 1, 'updated_at': stamp(updated),
                    'status': 'completed' if status == 'completed' else
                              'in-progress' if status == 'inProgress' else 'cancelled'}
            if status == 'completed':
                if updated < start and (root,uid) not in deferred_ids: continue
                key = (root, uid)
                fetched += 1
                require(fetched <= config['max_content_turns'], 'content budget exhausted; coverage incomplete')
                items = pages(transport, 'thread/items/list', {'threadId': ident, 'turnId': uid,
                                                              'sortDirection': 'asc'}, config['max_items'])
                require(all(e.get('turnId') == uid for e in items), 'unexpected item turn')
                require(len({e['item']['id'] for e in items}) == len(items), 'duplicate item page')
                unit['content'] = content(items)
                if key in canonical:
                    require(canonical[key] == unit, 'inconsistent copied turn')
                canonical[key] = unit
            units.append(unit)
    # A completed canonical copy supersedes stale pending/cancelled copies of
    # the same root/unit. Keep completed copies for the collector's fact check.
    for session in sessions:
        session['units'][:] = [u for u in session['units']
                               if u['status'] == 'completed' or (session['root_id'], u['id']) not in canonical]
    # Detect changes during read; no resume/server write is used to obtain a snapshot.
    final = inventory()
    require(markers(final) == initial_markers, 'source changed during read; retry later')
    return {'version': 1, 'source_id': source, 'coverage': {'start': since, 'end': cutoff, 'complete': True},
            'coverage_notes': {
                'scope': 'explicit-thread-ids' if 'thread_ids' in config else 'app-server-index',
                'input_kind': 'synthetic-fixture' if config['transport'] == 'fixture' else 'existing-app-server',
                'snapshot_guaranteed': False, 'outcomes_independently_verified': False,
                'limitations': ['No coverage of records outside the selected index or ID allowlist.',
                                'Undetected concurrent updates are possible.',
                                'Repository tests use synthetic fixtures; live deployment compatibility requires separate verification.']},
            'sessions': sessions}
