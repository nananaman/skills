"""Daily metadata selection, preserving the successful Mac probe's checks."""
from collections import Counter
import os
from pathlib import Path, PurePosixPath
import re
import sys
from common import instant, require, text_id
from codex_proxy import iter_pages


def github_repo(origin):
    if not isinstance(origin, str):
        return None
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?', origin)
    return '/'.join(match.groups()) if match else None


def within(path, prefix):
    return isinstance(path, str) and path.startswith(prefix + '/') and '..' not in PurePosixPath(path).parts


def source_boundary(config):
    """The current Mac CLI reader's immutable repository selection."""
    require(isinstance(config, dict) and set(config) == {'version', 'source_id', 'device_id', 'host_id', 'path_flavour', 'repos', 'exclude_roots'}, 'unknown source fields')
    require(config['version'] == 1 and config['host_id'] == 'local' and
            config['path_flavour'] == 'posix', 'unknown Mac source contract')
    text_id(config['source_id'])
    text_id(config['device_id'])
    repos = config['repos']
    require(isinstance(repos, list) and repos, 'source repos required')
    for repo in repos:
        require(isinstance(repo, dict) and set(repo) == {'id', 'cwd', 'information_scope'}, 'invalid source repo')
        text_id(repo['id'])
        scope = text_id(repo['information_scope'])
        require(scope.startswith('personal:') and scope.removeprefix('personal:').strip(),
                'this verified Mac entry supports registered personal sources only')
        path = PurePosixPath(repo['cwd'])
        require(path.is_absolute() and '..' not in path.parts and str(path) == repo['cwd'],
                'source cwd must be absolute and normalized')
    require(len({(r['id'], r['cwd']) for r in repos}) == len(repos), 'duplicate source repo')
    require(isinstance(config['exclude_roots'], list) and
            all(isinstance(v, str) and v.strip() for v in config['exclude_roots']), 'invalid source exclusions')
    return dict(mode='repo-index', device_id=config['device_id'], host_id='local', path_flavour='posix',
                repos=sorted(repos, key=lambda r: (r['cwd'], r['id'])))


def index(proxy, config, ledger, since, cutoff, codex_home, max_pages, max_threads):
    require(sys.platform == 'darwin' and config['host_id'] == 'local', 'Mac local source required')
    start, end = int(instant(since).timestamp()), int(instant(cutoff).timestamp())
    require(start < end, 'invalid window')
    boundary = source_boundary(config)
    previous_source = ledger['sources'].get(config['source_id'], {})
    if previous_source:
        require(int(instant(previous_source['through']).timestamp()) >= start,
                'checkpoint gap precedes authorized start; use an explicitly authorized wider window')
        require(previous_source['adapter_selection'] == boundary,
                'source boundary changed; reconcile before reading')
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
        host_id='local', adapter_selection=boundary, window=dict(since=since, cutoff=cutoff),
        coverage_complete=not held, threads=eligible,
        excluded_roots=sorted(excluded),
        unfinished_by_root={root: sorted(v['unit_id'] for v in previous_source.get('deferred', {}).values() if v['root_id'] == root)
                            for root in {v['root_id'] for v in previous_source.get('deferred', {}).values()} - excluded})
    stats.update(eligible_sessions=len(eligible), held_sessions=sum(held.values()))
    return selection, {**dict(stats), 'repositories': dict(repositories), 'held_reasons': dict(held)}
