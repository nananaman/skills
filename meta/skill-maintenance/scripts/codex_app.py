"""Validate minimized Codex app-tool captures; never opens a live transport."""

from datetime import datetime, timezone
import math

from common import instant, require, stamp, text_id, path_key, SENSITIVE, validate_evidence, turn_disposition


LIMIT = 50
PENDING = "app-active-thread:"


def allowed_row(row, config):
    return (row['host_id'] == config['host_id'] and isinstance(row.get('cwd'), str) and
            path_key(row['cwd'], config['path_flavour']) in
            {path_key(r['cwd'], config['path_flavour']) for r in config['repos']})


def minimize_indexes(snapshot, config):
    """Retain only scoped index rows and anonymous saturation evidence."""
    recent = snapshot['recent']
    if 'scan' not in recent:
        recent['scan'] = {}
        for side in ('before', 'after'):
            times = [epoch(r['updated_at']) for r in recent[side]]
            require(times == sorted(times, reverse=True), 'app index is not in recency order')
            recent['scan'][side] = {'count': len(times),
                                    'oldest_updated_at': recent[side][-1]['updated_at'] if times else None}
    for section in ('recent', 'pinned', 'archive'):
        for side in ('before', 'after'):
            snapshot[section][side] = [r for r in snapshot[section][side] if allowed_row(r, config)]
    require(all(allowed_row(c['thread'], config) for c in snapshot['threads']),
            'app read outside source scope')
    return snapshot


def native_row(row):
    """Discard titles, previews and unrelated native metadata."""
    raw_status = row['status']
    host = 'non-codex:chatgpt' if row.get('kind') == 'chatgpt' else row['hostId']
    return {'id': row['id'], 'host_id': host, 'cwd': row.get('cwd'),
            'updated_at': row['updatedAt'],
            'status': raw_status['type'] if isinstance(raw_status, dict) else raw_status}


def minimize_native(bundle, config, since, cutoff):
    """Normalize parsed successful native tool results, without retaining commands."""
    start, end = instant(since), instant(cutoff)
    identity = {'source_id': config['source_id'], 'selection': selection(config)}
    require(bundle['source_identity'] == identity, 'native bundle source/scope mismatch')
    actual_limit = bundle['index_limit']
    require(type(actual_limit) is int and 0 < actual_limit <= LIMIT, 'native effective index limit missing')
    def archive(pages):
        rows, cursor = [], None
        require(pages, 'native archive probe missing')
        for i, result in enumerate(pages):
            require(result['cursor'] == cursor, 'native archive cursor chain missing')
            data = result['result']
            rows.extend(native_row(r) for r in data['threads'])
            cursor = data['nextCursor']
            require(cursor is not None or i == len(pages)-1, 'native archive pages after end')
        require(cursor is None, 'native archive pagination incomplete')
        return rows
    captures = []
    for entry in bundle['reads']:
        pages, thread = [], None
        for page in entry['pages']:
            data = page['result']
            row = native_row(data['thread'])
            params = page['params']
            require(params['hostId'] == config['host_id'] and params['threadId'] == row['id'] and
                    params['includeOutputs'] is False and params.get('cursor') == page['cursor'] and
                    params['turnLimit'] == data['page']['limit'], 'native read request provenance mismatch')
            chars = params['maxOutputCharsPerItem']
            require(type(chars) is int and chars > 0, 'native message limit missing')
            def message(value, metadata):
                require(isinstance(value, str) and value.strip(), 'native empty request/final; acquisition incomplete')
                require(len(value) < chars and not metadata.get('truncated') and not metadata.get('isTruncated') and
                        not any(m in value.lower() for m in ('[truncated]', '[output truncated]')),
                        'native truncated or limit-sized message; acquisition incomplete')
                require(not SENSITIVE.search(value), 'sensitive app turn blocked')
                return value
            require(thread is None or thread == row, 'native thread changed between pages')
            thread = row
            require(allowed_row(row, config), 'native read outside source scope')
            turns = []
            for turn in data['turns']:
                require('evidence' not in turn,
                        'native report-only capture cannot import trace evidence; use a normalized export')
                unit = {k: turn[k] for k in ('id', 'status', 'startedAt', 'completedAt')}
                done = epoch(unit['completedAt']) if unit['completedAt'] is not None else None
                known = unit['id'] in entry.get('known_unfinished_ids', [])
                if turn_disposition(unit['status'], epoch(unit['startedAt']), done, start, end, known) == 'selected':
                    requests = []
                    finals = []
                    for item in turn['items']:
                        if item['type'] == 'userMessage':
                            require(item['content'] and all(c['type'] == 'text' for c in item['content']),
                                    'native non-text request; acquisition incomplete')
                            require(not item.get('truncated') and not item.get('isTruncated'), 'native truncated request')
                            requests.extend(message(c['text'], c) for c in item['content'])
                        elif item['type'] == 'agentMessage' and item.get('phase') == 'final_answer':
                            finals.append(message(item['text'], item))
                    request = '\n'.join(requests)
                    require(request.strip() and finals, 'native turn lacks request/final; acquisition incomplete')
                    unit['content'] = {'request': request, 'expected': request,
                                       'observed': 'Agent final report (not independently verified):\n' + '\n'.join(finals)}
                turns.append(unit)
            pages.append({'cursor': page['cursor'], 'page': data['page'], 'turns': turns})
        captures.append({'thread': thread, 'pages': pages})
    before, after = bundle['index_before'], bundle['index_after']
    require(before['unavailableHosts'] == after['unavailableHosts'] and
            before['unavailableSources'] == after['unavailableSources'], 'native source availability changed')
    return minimize_indexes({'version': 1, 'device_id': config['device_id'], 'host_id': config['host_id'],
            'source_identity': identity,
            'capabilities': bundle['capabilities'], 'window': {'start': stamp(start), 'end': stamp(end)},
            'unavailable_hosts': before['unavailableHosts'], 'unavailable_sources': before['unavailableSources'],
            'recent': {'limit': actual_limit, 'before': [native_row(r) for r in before['threads']],
                       'after': [native_row(r) for r in after['threads']]},
            'pinned': {'before': [native_row(r) for r in before['pinnedThreads']],
                       'after': [native_row(r) for r in after['pinnedThreads']]},
            'archive': {'complete': True, 'before': archive(bundle['archive_before']),
                        'after': archive(bundle['archive_after'])}, 'threads': captures}, config)


def selection(config):
    require(config['version'] == 1, 'unsupported app source version')
    text_id(config['source_id'])
    text_id(config['device_id'])
    require(config['host_id'] == 'local', 'app source must use this executor local host')
    require(config['path_flavour'] in {'posix', 'windows'}, 'unknown path flavour')
    repos = config['repos']
    require(isinstance(repos, list) and repos, 'app repo allowlist required')
    paths = [path_key(r['cwd'], config['path_flavour']) for r in repos]
    require(len(paths) == len(set(paths)), 'ambiguous app cwd allowlist')
    for r in repos:
        text_id(r['id']); text_id(r['information_scope'])
    for name in ('max_threads', 'max_turns'):
        require(type(config[name]) is int and config[name] > 0, 'invalid app budget')
    require(isinstance(config['exclude_roots'], list) and
            all(isinstance(i, str) and i for i in config['exclude_roots']), 'invalid app exclusions')
    return {'mode': 'app-index', 'device_id': config['device_id'], 'host_id': config['host_id'],
            'path_flavour': config['path_flavour'],
            'coverage_scope': 'visible-updated-threads-and-known-unfinished',
            'repos': sorted([{k: r[k] for k in ('id', 'cwd', 'information_scope')} for r in repos],
                            key=lambda r: r['cwd'])}


def epoch(value):
    require(type(value) in {int, float} and math.isfinite(value) and 0 <= value <= 253402300799,
            'invalid app timestamp')
    return datetime.fromtimestamp(value, timezone.utc)


def status(value):
    require(value in {'idle', 'active', 'notLoaded', 'waiting', 'error'}, 'unknown app thread status')
    return value


def indexed(rows):
    require(isinstance(rows, list), 'app index entries required')
    result = {}
    for row in rows:
        key = (text_id(row['host_id']), text_id(row['id']))
        require(key not in result, 'duplicate app index identity')
        epoch(row['updated_at']); status(row['status'])
        result[key] = row
    return result


def export(snapshot, config, target, since, cutoff, previous, state_units):
    boundary = selection(config)
    start, end = instant(since), instant(cutoff)
    require(start < end, 'empty or reversed app window')
    require(snapshot['version'] == 1 and snapshot['host_id'] == config['host_id'] and
            snapshot['device_id'] == config['device_id'], 'app capture device/host mismatch')
    require(snapshot['source_identity'] == {'source_id': config['source_id'], 'selection': boundary},
            'app capture source/scope mismatch')
    capabilities = snapshot['capabilities']
    require(set(capabilities) == {'list_threads', 'read_thread', 'list_archived_threads'} and
            capabilities['list_threads'] is True and capabilities['list_archived_threads'] is True and
            (capabilities['read_thread'] is True or capabilities['read_thread'] == 'not-needed'),
            'app read capabilities not successfully probed; acquisition incomplete')
    require(instant(snapshot['window']['start']) == start and
            instant(snapshot['window']['end']) == end, 'app capture window does not cover required checkpoint gap')
    require(not snapshot['unavailable_hosts'] and not snapshot['unavailable_sources'],
            'app index has unavailable sources; acquisition incomplete')
    recent = snapshot['recent']
    limit = recent['limit']
    require(type(limit) is int and 0 < limit <= LIMIT, 'unsupported app recent index limit')
    before, after = indexed(recent['before']), indexed(recent['after'])
    for side in ('before', 'after'):
        rows = recent[side]
        times = [epoch(r['updated_at']) for r in rows]
        require(times == sorted(times, reverse=True), 'app index is not in recency order')
        scan = recent.get('scan', {}).get(side, {'count': len(rows),
                    'oldest_updated_at': rows[-1]['updated_at'] if rows else None})
        count, oldest = scan['count'], scan['oldest_updated_at']
        require(type(count) is int and len(rows) <= count <= limit, 'app index exceeds advertised limit')
        require((count == 0 and oldest is None) or
                (count > 0 and oldest is not None and (not times or epoch(oldest) <= times[-1])),
                'invalid anonymous app index boundary')
        require(count < limit or epoch(oldest) < start,
                'app recent index limit cuts through window; acquisition incomplete')
    archived = snapshot['archive']
    require(archived['complete'] is True, 'app archive pagination incomplete')
    archive_before, archive_after = indexed(archived['before']), indexed(archived['after'])
    # Pinned threads are not part of the 50-entry recents limit.
    pinned_before, pinned_after = indexed(snapshot['pinned']['before']), indexed(snapshot['pinned']['after'])
    def combine(*parts):
        merged = {}
        for part in parts:
            for key, row in part.items():
                require(key not in merged or merged[key] == row, 'conflicting app index metadata')
                merged[key] = row
        return merged
    first = combine(before, archive_before, pinned_before)
    last = combine(after, archive_after, pinned_after)
    repos = {path_key(r['cwd'], config['path_flavour']): r for r in config['repos']}
    require(all(r['id'] in target['source_repos'] and
                r['information_scope'] in {'public', target['information_scope']} for r in repos.values()),
            'app repo target/information scope mismatch')
    excluded = set(config['exclude_roots']) | set(previous.get('excluded_roots', []))
    deferred = list(previous.get('deferred', {}).values())
    pending_threads = {d['session_id'] for d in deferred}
    def allowed(row):
        return (row['host_id'] == config['host_id'] and isinstance(row.get('cwd'), str) and
                path_key(row['cwd'], config['path_flavour']) in repos)
    def wanted(index):
        return {key: row for key, row in index.items() if allowed(row) and
                (start <= epoch(row['updated_at']) or row['id'] in pending_threads or
                 row['status'] in {'active', 'waiting'})}
    wanted_first, wanted_last = wanted(first), wanted(last)
    require(wanted_first == wanted_last, 'app index changed during capture; retry within authorization')
    require(len(wanted_first) <= config['max_threads'], 'app thread budget exhausted; acquisition incomplete')
    require(pending_threads <= {row['id'] for row in wanted_first.values()} | excluded,
            'app index omitted a known unfinished thread')
    captures = {text_id(c['thread']['id']): c for c in snapshot['threads']}
    require(len(captures) == len(snapshot['threads']), 'duplicate app thread capture')
    expected_reads = {row['id'] for row in wanted_first.values()
                      if row['id'] not in excluded and row['status'] not in {'active', 'waiting'}}
    require(not expected_reads or capabilities['read_thread'] is True,
            'app read capability unconfirmed for required threads')
    require(set(captures) == expected_reads, 'app thread captures missing or outside selected scope')
    sessions, canonical, turn_count, copies = [], {}, 0, 0
    for saved in state_units.values():
        facts = saved['facts']
        if facts['source_id'] == config['source_id']:
            canonical[(facts['id'], facts['revision'])] = facts
    for row in sorted(wanted_first.values(), key=lambda r: r['id']):
        repo = repos[path_key(row['cwd'], config['path_flavour'])]
        session = {'id': row['id'], 'root_id': row['id'], 'parent_id': None,
                   'source_repo': repo['id'], 'information_scope': repo['information_scope'],
                   'kind': 'skill-maintenance' if row['id'] in excluded else 'work', 'units': []}
        sessions.append(session)
        if row['id'] in excluded:
            continue
        marker = PENDING + row['id']
        if row['status'] in {'active', 'waiting'}:
            # Do not read active bodies. Preserve known actual unfinished turns too.
            ids = {d['unit_id'] for d in deferred if d['session_id'] == row['id']} | {marker}
            session['units'] = [{'id': i, 'revision': 1, 'updated_at': stamp(start),
                                 'status': 'in-progress'} for i in sorted(ids)]
            continue
        capture = captures[row['id']]
        require(capture['thread'] == row, 'app thread metadata differs from stable index')
        pages, seen, cursors, prior_cursor, oldest = capture['pages'], set(), set(), None, None
        require(isinstance(pages, list) and pages, 'app turn pages missing')
        for number, page in enumerate(pages):
            require(page['cursor'] == prior_cursor, 'app turn cursor chain incomplete')
            info = page['page']
            require(info['order'] == 'newest_first' and type(info['hasMore']) is bool,
                    'unknown app turn page schema')
            require((info['hasMore'] and isinstance(info['nextCursor'], str) and info['nextCursor']) or
                    (not info['hasMore'] and info['nextCursor'] is None), 'invalid app next cursor')
            for turn in page['turns']:
                ident = text_id(turn['id'])
                require(ident not in seen, 'duplicate app turn page entry')
                seen.add(ident)
                require(turn['status'] in {'completed', 'inProgress', 'interrupted', 'failed'},
                        'unknown app turn status')
                started = epoch(turn['startedAt'])
                require(oldest is None or started <= oldest, 'app turns not in newest-first order')
                oldest = started
                completed = epoch(turn['completedAt']) if turn['completedAt'] is not None else None
                require(completed is None or completed >= started, 'app turn timestamps reversed')
                known = any(d['session_id'] == row['id'] and d['unit_id'] == ident for d in deferred)
                disposition = turn_disposition(turn['status'], started, completed, start, end, known)
                if disposition == 'skip':
                    require('content' not in turn, 'out-of-window app content must not be persisted')
                    continue
                turn_count += 1
                require(turn_count <= config['max_turns'], 'app selected turn budget exhausted; acquisition incomplete')
                if disposition == 'pending':
                    session['units'].append({'id': ident, 'revision': 1, 'updated_at': stamp(started),
                                             'status': 'in-progress'})
                    continue
                require('content' in turn, 'finished app turn content missing; failure evidence must not be discarded')
                content = dict(turn['content'])
                require(set(content) == {'request', 'expected', 'observed'} and
                        all(isinstance(v, str) and v.strip() for v in content.values()),
                        'app completed content missing; do not invent success')
                require(not any(SENSITIVE.search(v) for v in content.values()), 'sensitive app turn blocked')
                if turn['status'] != 'completed':
                    content['observed'] += '\nRecorded turn status: ' + turn['status']
                facts = {'source_id': config['source_id'], 'root_id': row['id'], 'id': ident,
                         'source_repo': repo['id'], 'information_scope': repo['information_scope'],
                         'revision': 1, 'updated_at': stamp(completed), 'content': content}
                evidence = {}
                if 'evidence' in turn:
                    validate_evidence(turn['evidence'])
                    evidence['evidence'] = turn['evidence']
                    facts.update(evidence)
                saved = canonical.get((ident, 1))
                if saved and saved['root_id'] != row['id']:
                    require({k: v for k, v in saved.items() if k != 'root_id'} ==
                            {k: v for k, v in facts.items() if k != 'root_id'},
                            'copied app turn has conflicting facts or scope')
                    copies += 1
                    if known:
                        session['units'].append({'id': ident, 'revision': 1, 'updated_at': stamp(completed),
                                                 'status': 'cancelled', 'deduplicated_into': saved['root_id']})
                    continue
                canonical[(ident, 1)] = facts
                session['units'].append({'id': ident, 'revision': 1, 'updated_at': stamp(completed),
                                         'status': 'completed', 'content': content, **evidence})
            prior_cursor = info['nextCursor']
            require(prior_cursor is None or prior_cursor not in cursors, 'repeated app pagination cursor')
            cursors.add(prior_cursor)
            require(info['hasMore'] or number == len(pages)-1, 'app pages continue after end')
        last_page = pages[-1]['page']
        remaining = {d['unit_id'] for d in deferred if d['session_id'] == row['id'] and d['unit_id'] != marker} - seen
        require(not remaining, 'app pages omitted a known unfinished turn')
        require(not last_page['hasMore'] or (oldest is not None and oldest < start),
                'app pages stop inside window; acquisition incomplete')
        if any(d['session_id'] == row['id'] and d['unit_id'] == marker for d in deferred):
            session['units'].append({'id': marker, 'revision': 1, 'updated_at': stamp(start), 'status': 'cancelled'})
    return {'version': 1, 'source_id': config['source_id'], 'adapter_selection': boundary,
            'coverage': {'start': stamp(start), 'end': stamp(end), 'complete': True},
            'coverage_notes': {'scope': boundary['coverage_scope'], 'copied_turns_deduplicated': copies,
                               'outcomes_independently_verified': False,
                               'unseen_older_unfinished': 'not_enumerated', 'ancestry': 'not_exposed'},
            'excluded_roots': sorted(excluded), 'sessions': sessions}
