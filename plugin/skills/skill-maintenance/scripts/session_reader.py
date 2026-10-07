"""Read explicitly authorized local Codex JSONL; keep visible context in order.

No RPC, diagnosis, evaluation budget, checkpoint update, or external writes.
The caller chooses authorized paths and interprets each transcript separately.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

SOURCE_GAP = re.compile(r'output (?:was )?truncated|(?:tokens|characters) truncated|omitted \d+ lines', re.I)


def instant(value):
    moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if moment.tzinfo is None:
        raise ValueError('timestamp needs timezone')
    return moment


def open_source(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    return os.fdopen(fd, 'rb')


def read_session(path, lower=None, upper=None, index_only=False, sink=None, end_bytes=None):
    items, errors, metadata, gaps, lifecycle = [], [], {}, [], []
    activity, timestamp_seen, visible = False, False, 0
    before = path.stat()
    end_bytes = before.st_size if end_bytes is None else end_bytes
    position = 0
    with open_source(path) as stream:
        number = 0
        while position < end_bytes:
            line = stream.readline(end_bytes - position)
            if not line:
                break
            number += 1
            position += len(line)
            try:
                record = json.loads(line)
                payload = record.get('payload', {})
                stamp = record.get('timestamp')
                if stamp:
                    moment = instant(stamp)
                    timestamp_seen = True
                    activity |= (not lower or moment >= lower) and (not upper or moment < upper)
                    if upper and moment >= upper:
                        continue
                if record.get('type') == 'session_meta':
                    metadata = {key: payload.get(key) for key in ('id', 'cwd', 'source', 'parent_thread_id')}
                if record.get('type') == 'event_msg' and payload.get('type') in {'task_started', 'task_complete', 'turn_aborted'}:
                    lifecycle.append({'line': number, 'timestamp': stamp, 'event': payload['type']})
                if index_only or record.get('type') != 'response_item':
                    continue
                if payload.get('type') == 'reasoning' or payload.get('phase') == 'analysis':
                    continue
                if upper and not stamp:
                    errors.append({'line': number, 'error': 'missing item timestamp; withheld at cutoff'})
                    continue
                payload = {key: value for key, value in payload.items() if key != 'encrypted_content'}
                item = {'line': number, 'timestamp': stamp, 'payload': payload}
                if sink is None:
                    items.append(item)
                else:
                    sink.write(json.dumps(item, ensure_ascii=False) + '\n')
                visible += 1
                if payload.get('type', '').endswith('_output') and SOURCE_GAP.search(json.dumps(payload, ensure_ascii=False)):
                    gaps.append(number)
            except (ValueError, TypeError, AttributeError) as error:
                errors.append({'line': number, 'error': type(error).__name__})
                lifecycle.append({'line': number, 'timestamp': None, 'event': 'unknown'})
    after = path.stat()
    changed = (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
    return {'metadata': metadata, 'items': items, 'visible_items': visible, 'errors': errors,
            'activity_in_period': activity, 'timestamp_seen': timestamp_seen,
            'source_version': (before.st_size, before.st_mtime_ns),
            'source_gaps': gaps, 'changed_during_read': changed, 'lifecycle': lifecycle}


def private_directory(path, repo):
    resolved = path.resolve()
    if resolved == repo.resolve() or repo.resolve() in resolved.parents:
        raise ValueError('private output must be outside improvement repository')
    if any(parent.name == '.git' for parent in (resolved, *resolved.parents)):
        raise ValueError('private output must be outside Git metadata')
    if any((parent / '.git').exists() for parent in (resolved, *resolved.parents)):
        raise ValueError('private output must be outside every Git checkout')
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(path, 0o700)


def write_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def scope_reason(path, source):
    with open_source(path) as stream:
        record = json.loads(next(stream))
    if record.get('type') != 'session_meta':
        raise ValueError('session metadata missing')
    metadata = record['payload']
    if metadata.get('id') in source.get('exclude_roots', []):
        return 'caller-excluded root'
    if metadata.get('parent_thread_id') or isinstance(metadata.get('source'), dict):
        return 'child session; correlate with parent, not independent evidence'
    git = metadata.get('git')
    remote = git.get('repository_url') if isinstance(git, dict) else ''
    remote = remote if isinstance(remote, str) else ''
    slug = remote.removeprefix('git@github.com:').removesuffix('.git') if remote.startswith('git@github.com:') else ''
    if remote.startswith('https://github.com/'):
        url = urlsplit(remote)
        if not url.query and not url.fragment:
            slug = url.path.strip('/').removesuffix('.git')
    cwd = metadata.get('cwd')
    for repository in source.get('repos', []):
        if slug and slug == repository['id']:
            return repository
        if cwd and repository.get('cwd') and Path(cwd).resolve() == Path(repository['cwd']).resolve():
            return repository
    return 'outside configured source repositories or unresolved ownership'


def collect(sessions, output, repo, since=None, until=None, source=None):
    start = time.monotonic()
    lower, upper = instant(since) if since else None, instant(until) if until else None
    if lower and upper and lower >= upper:
        raise ValueError('since must precede until')
    sessions = sessions.absolute()
    if any(part.is_symlink() for part in (sessions, *sessions.parents)):
        raise ValueError('authorized source path must have no symlink components; use its canonical path')
    if not sessions.exists():
        raise ValueError('authorized session source is missing')
    paths = sorted(sessions.rglob('*.jsonl')) if sessions.is_dir() else [sessions]
    private_directory(output, repo)
    result = {'counts': dict(discovered=len(paths), selected=0, read=0, partial=0, failed=0, outside_period=0, excluded=0, held=0),
              'period': {'since': since, 'until': until}, 'sessions': []}
    for number, path in enumerate(paths, 1):
        entry = {'source': str(path), 'status': 'failed'}
        item_start = time.monotonic()
        transcript = output / f'session-{number:05d}.jsonl'
        selected = False
        try:
            if path.is_symlink() or not path.is_file() or (sessions.is_dir() and sessions.resolve() not in path.resolve().parents):
                raise ValueError('candidate is not a regular file within authorized directory')
            if source is not None:
                scope = scope_reason(path, source)
                if isinstance(scope, str):
                    entry.update(status='excluded', reason=scope)
                    continue
                entry['repository'] = scope['id']
                entry['information_scope'] = scope.get('information_scope')
            index = read_session(path, lower, upper, index_only=True)
            entry['metadata'] = index['metadata']
            if (lower or upper) and index['timestamp_seen'] and not index['activity_in_period']:
                entry.update(status='outside_period', reason='no activity in requested period')
                continue
            selected = True
            index_stat = path.stat()
            if index['source_version'] != (index_stat.st_size, index_stat.st_mtime_ns):
                entry.update(status='held', reason='session changed after index; visible body not exported')
                continue
            if not index['metadata'].get('id'):
                entry['reason'] = 'metadata missing'
                continue
            if not index['lifecycle'] or index['lifecycle'][-1]['event'] == 'unknown':
                entry.update(status='held', reason='termination unknown; visible body not exported')
                continue
            if index['changed_during_read'] or (index['lifecycle'] and index['lifecycle'][-1]['event'] == 'task_started'):
                entry.update(status='held', reason='active or changing session; visible body not exported')
                continue
            fd = os.open(transcript, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                data = read_session(path, lower, upper, sink=stream, end_bytes=index['source_version'][0])
            entry.update({key: value for key, value in data.items() if key not in {'items', 'activity_in_period', 'timestamp_seen', 'source_version'}})
            after = path.stat()
            changed = data['changed_during_read'] or (index_stat.st_size, index_stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
            if changed or (data['lifecycle'] and data['lifecycle'][-1]['event'] == 'task_started'):
                entry.update(status='held', reason='session changed or became active before export')
            elif not data['metadata'].get('id') or not data['visible_items']:
                entry['reason'] = 'metadata or visible context missing'
            else:
                entry['status'] = 'partial' if data['errors'] or data['source_gaps'] or ((lower or upper) and not data['timestamp_seen']) else 'read'
                entry['transcript'] = str(transcript)
        except (OSError, UnicodeError, ValueError, TypeError, AttributeError, KeyError, StopIteration) as error:
            selected = True
            entry['reason'] = type(error).__name__
        finally:
            if transcript.exists() and not entry.get('transcript'):
                transcript.unlink()
            result['counts']['selected'] += int(selected)
            result['counts'][entry['status']] += 1
            entry['elapsed_seconds'] = time.monotonic() - item_start
            result['sessions'].append(entry)
    result['elapsed_seconds'] = time.monotonic() - start
    write_json(output / 'manifest.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sessions', type=Path, required=True, help='explicitly authorized file or directory')
    parser.add_argument('--output', type=Path, required=True, help='new private directory outside Git')
    parser.add_argument('--repo', type=Path, required=True, help='improvement repository, never a history scope grant')
    parser.add_argument('--source', type=Path, help='caller source.json: allowed repo IDs/cwds and excluded roots')
    parser.add_argument('--since', help='inclusive activity timestamp with timezone')
    parser.add_argument('--until', help='exclusive activity timestamp with timezone')
    args = parser.parse_args()
    source = json.loads(args.source.read_text()) if args.source else None
    result = collect(args.sessions, args.output, args.repo, args.since, args.until, source)
    print(json.dumps({'counts': result['counts'], 'elapsed_seconds': result['elapsed_seconds'],
                      'manifest': str(args.output / 'manifest.json')}, ensure_ascii=False))
    return 1 if result['counts']['failed'] or result['counts']['partial'] or result['counts']['held'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
