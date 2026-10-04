"""Daily metadata selection, preserving the successful Mac probe's checks."""
from collections import Counter
import os
from pathlib import Path, PurePosixPath
import re
import sys
from common import instant, require
from codex_proxy import iter_pages


def github_repo(origin):
    if not isinstance(origin, str):
        return None
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?', origin)
    return '/'.join(match.groups()) if match else None


def within(path, prefix):
    return isinstance(path, str) and path.startswith(prefix + '/') and '..' not in PurePosixPath(path).parts


def index(proxy, config, ledger, since, cutoff, codex_home, max_pages, max_threads):
    require(sys.platform == 'darwin' and config['host_id'] == 'local', 'Mac local source required')
    require(config['version'] == 1 and config['path_flavour'] == 'posix', 'unknown source contract')
    start, end = int(instant(since).timestamp()), int(instant(cutoff).timestamp())
    require(start < end, 'invalid window')
    # Retain the existing logical input boundary. No new source/state identity.
    saved = ledger['sources'][config['source_id']]['adapter_selection']
    previous_source = ledger['sources'][config['source_id']]
    require(int(instant(previous_source['through']).timestamp()) >= start,
            'checkpoint gap precedes authorized start; use an explicitly authorized wider window')
    require(saved['mode'] in {'app-index', 'repo-index'} and saved['device_id'] == config['device_id'] and
            saved['host_id'] == config['host_id'] and saved['path_flavour'] == config['path_flavour'] and
            sorted(saved['repos'], key=lambda r: (r['cwd'], r['id'])) ==
            sorted(config['repos'], key=lambda r: (r['cwd'], r['id'])), 'source boundary changed; reconcile before reading')
    require(all(r['information_scope'].startswith('personal:') for r in config['repos']),
            'this verified Mac entry supports registered personal sources only')
    home = str(Path.home())
    excluded = set(config['exclude_roots']) | set(previous_source.get('excluded_roots', []))
    if os.environ.get('CODEX_THREAD_ID'):
        excluded.add(os.environ['CODEX_THREAD_ID'])
    eligible, seen = [], set()
    held, repositories = Counter(), Counter()
    stats = Counter()
    for archived in (False, True):
        previous = None
        params = dict(archived=archived, sortKey='updated_at', sortDirection='desc',
                      sourceKinds=['cli', 'vscode', 'exec', 'appServer'], useStateDbOnly=True, limit=50)
        for page in iter_pages(proxy, 'thread/list', params, max_pages):
            stats['index_pages'] += 1
            older = False
            for t in page:
                require(isinstance(t, dict) and t.get('turns') == [], 'unexpected index body; discard response')
                ts = t.get('updatedAt')
                require(type(ts) is int and (previous is None or ts <= previous), 'unstable index ordering')
                previous = ts
                if ts < start:
                    older = True
                    continue
                ident = t['id']
                if ident in seen:
                    continue
                seen.add(ident)
                require(len(seen) <= max_threads, 'thread budget exhausted')
                if ident in excluded or t['sessionId'] in excluded:
                    stats['excluded_maintenance'] += 1
                    continue
                if t.get('parentThreadId') is not None:
                    stats['excluded_nonroot'] += 1
                    continue
                repo = github_repo((t.get('gitInfo') or {}).get('originUrl'))
                scope = {r['information_scope'] for r in config['repos'] if r['id'] == repo}
                extra, envs = t.get('extra') or {}, t.get('environments')
                reason = None
                if t.get('source') not in {'cli', 'vscode', 'exec', 'appServer'}:
                    reason = 'unknown_source_kind'
                elif not within(t.get('cwd'), home) or not within(t.get('path'), codex_home):
                    reason = 'Mac_local_origin_not_confirmed'
                elif any(k in extra and extra[k] not in (None, 'local') for k in ('hostId', 'host_id', 'remoteHost', 'remote_host', 'remoteEnvironmentId')):
                    reason = 'remote_or_unknown_host'
                elif envs and any(e.get('environmentId') != 'local' for e in envs):
                    reason = 'environment_host_not_confirmed'
                elif not repo or len(scope) != 1:
                    reason = 'repository_information_scope_unregistered'
                elif t.get('ephemeral') is not False:
                    reason = 'ephemeral_origin_unconfirmed'
                if reason:
                    held[reason] += 1
                    continue
                repositories[repo] += 1
                eligible.append(dict(id=ident, session_id=t['sessionId'], repository=repo,
                    information_scope=next(iter(scope)), updated_at=ts, archived=archived,
                    source_kind=t['source'], ephemeral=False, Mac_local_proof=True,
                    runtime_status=(t.get('status') or {}).get('type', 'unknown')))
            if older:
                break
    unfinished = previous_source.get('deferred', {}).values()
    missing = {v['root_id'] for v in unfinished} - {t['id'] for t in eligible} - excluded
    if missing:
        held['known_unfinished_root_outside_index'] += len(missing)
    selection = dict(version=1, source_id=config['source_id'], device_id=config['device_id'],
        host_id='local', adapter_selection=saved, window=dict(since=since, cutoff=cutoff),
        coverage_complete=not held, threads=eligible,
        excluded_roots=sorted(excluded),
        unfinished_by_root={root: sorted(v['unit_id'] for v in previous_source.get('deferred', {}).values() if v['root_id'] == root)
                            for root in {v['root_id'] for v in previous_source.get('deferred', {}).values()} - excluded})
    stats.update(eligible_sessions=len(eligible), held_sessions=sum(held.values()))
    return selection, {**dict(stats), 'repositories': dict(repositories), 'held_reasons': dict(held)}
