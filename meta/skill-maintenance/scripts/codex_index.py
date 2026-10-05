"""Select registered Mac session metadata within an authorized window."""
from collections import Counter
import os
from pathlib import Path, PurePosixPath
import re
import sys
from common import instant, require, text_id
from codex_proxy import iter_pages


def permitted_scope(scope):
    if not isinstance(scope, str):
        return False
    kind, separator, owner = scope.partition(':')
    return kind in {'personal', 'organization'} and bool(separator and owner) and owner == owner.strip()


def github_repo(origin):
    if not isinstance(origin, str):
        return None
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?', origin)
    return '/'.join(match.groups()) if match else None


def within(path, prefix):
    return isinstance(path, str) and path.startswith(prefix + '/') and '..' not in PurePosixPath(path).parts


def repository_scope(repos):
    """Validate the caller's repository allowlist and return its single scope."""
    require(isinstance(repos, list) and repos, 'source repos required')
    for repo in repos:
        require(isinstance(repo, dict) and set(repo) == {'id', 'cwd', 'information_scope'}, 'invalid source repo')
        text_id(repo['id'])
        scope = text_id(repo['information_scope'])
        require(permitted_scope(scope), 'unregistered information scope')
        kind, _, owner = scope.partition(':')
        require(kind != 'organization' or repo['id'].startswith(owner + '/'),
                'organization repo owner mismatch')
        path = PurePosixPath(repo['cwd'])
        require(path.is_absolute() and '..' not in path.parts and str(path) == repo['cwd'],
                'source cwd must be absolute and normalized')
    require(len({r['information_scope'] for r in repos}) == 1,
            'mixed information scopes require separate source and state')
    require(len({(r['id'], r['cwd']) for r in repos}) == len(repos), 'duplicate source repo')
    return repos[0]['information_scope']


def source_boundary(config):
    """The current Mac CLI reader's immutable repository selection."""
    require(isinstance(config, dict) and set(config) == {'version', 'source_id', 'device_id', 'host_id', 'path_flavour', 'repos', 'exclude_roots'}, 'unknown source fields')
    require(config['version'] == 1 and config['host_id'] == 'local' and
            config['path_flavour'] == 'posix', 'unknown Mac source contract')
    text_id(config['source_id'])
    text_id(config['device_id'])
    repos = config['repos']
    repository_scope(repos)
    require(isinstance(config['exclude_roots'], list) and
            all(isinstance(v, str) and v.strip() for v in config['exclude_roots']), 'invalid source exclusions')
    return dict(mode='repo-index', device_id=config['device_id'], host_id='local', path_flavour='posix',
                repos=sorted(repos, key=lambda r: (r['cwd'], r['id'])))



def index_page(page, config, codex_home):
    """Persist IDs and source assessments, never preview, paths or external metadata."""
    normalized = []
    for t in page:
        require(isinstance(t, dict) and t.get('turns') == [], 'unexpected index body; discard response')
        ident, session = text_id(t['id']), text_id(t['sessionId'])
        ts, created = t.get('updatedAt'), t.get('createdAt')
        require(type(ts) is int and (created is None or type(created) is int and created <= ts), 'invalid index timestamp')
        repo = github_repo((t.get('gitInfo') or {}).get('originUrl'))
        scope = {r['information_scope'] for r in config['repos'] if r['id'] == repo and r['cwd'] == t.get('cwd')}
        extra, envs = t.get('extra') or {}, t.get('environments')
        reason = None
        if not isinstance(t.get('source'), str) or t['source'] not in {'cli', 'vscode', 'exec', 'appServer'}:
            reason = 'unknown_source_kind'
        elif not within(t.get('cwd'), str(Path.home())) or not within(t.get('path'), codex_home):
            reason = 'Mac_local_origin_not_confirmed'
        elif not isinstance(extra, dict) or any(k in extra and extra[k] not in (None, 'local')
                for k in ('hostId', 'host_id', 'remoteHost', 'remote_host', 'remoteEnvironmentId')):
            reason = 'remote_or_unknown_host'
        elif envs and (not isinstance(envs, list) or any(not isinstance(e, dict) or e.get('environmentId') != 'local' for e in envs)):
            reason = 'environment_host_not_confirmed'
        elif not repo or len(scope) != 1:
            reason = 'repository_information_scope_unregistered'
        elif t.get('ephemeral') is not False:
            reason = 'ephemeral_origin_unconfirmed'
        thread = None
        if reason is None:
            status = (t.get('status') or {}).get('type', 'unknown')
            thread = dict(id=ident, session_id=session, repository=repo,
                information_scope=next(iter(scope)), updated_at=ts, source_kind=t['source'],
                ephemeral=False, Mac_local_proof=True,
                runtime_status=status if status in {'idle', 'notLoaded', 'active', 'systemError'} else 'unknown')
        normalized.append(dict(id=ident, session_id=session, updated_at=ts, created_at=created,
                               is_root=t.get('parentThreadId') is None, reason=reason, thread=thread))
    return normalized


def index(proxy, config, ledger, since, cutoff, codex_home):
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
    feedback_roots = set(ledger.get('maintenance_roots', {}).get(config['source_id'], []))
    excluded = set(config['exclude_roots']) | set(previous_source.get('excluded_roots', [])) | feedback_roots
    feedback_excluded = set(config['exclude_roots']) | set(previous_source.get('feedback_excluded_roots', []))
    hard_excluded = set(feedback_excluded)
    if os.environ.get('CODEX_THREAD_ID'):
        hard_excluded.add(os.environ['CODEX_THREAD_ID'])
    if os.environ.get('CODEX_THREAD_ID'):
        excluded.add(os.environ['CODEX_THREAD_ID'])
    eligible, seen = [], set()
    held, repositories = Counter(), Counter()
    stats = Counter()
    anchors = {False: [], True: []}
    def relevant(t):
        feedback = t['id'] in feedback_roots and not ({t['id'], t['session_id']} & hard_excluded)
        return (t['updated_at'] >= start and (t.get('created_at') is None or t['created_at'] <= end) and
                t['is_root'] and (feedback or not ({t['id'], t['session_id']} & excluded)))
    for archived in (False, True):
        previous = None
        phase_seen = set()
        phase_first_page = stats['index_pages'] + 1
        params = dict(archived=archived, sortKey='updated_at', sortDirection='desc',
                      sourceKinds=['cli', 'vscode', 'exec', 'appServer'], useStateDbOnly=True, cwd=sorted({r['cwd'] for r in config['repos']}), limit=50)
        for page in iter_pages(proxy, 'thread/list', params,
                               normalize=lambda page: index_page(page, config, codex_home)):
            stats['index_pages'] += 1
            older = False
            for t in page:
                ts = t.get('updated_at')
                require(type(ts) is int and (previous is None or ts <= previous), 'unstable index ordering')
                previous = ts
                if ts < start:
                    older = True
                    continue
                if t.get('created_at') is not None and t['created_at'] > end:
                    continue
                ident = t['id']
                require(ident not in phase_seen, 'duplicate index row; source changed during pagination')
                phase_seen.add(ident)
                if relevant(t) and stats['index_pages'] == phase_first_page:
                    anchors[archived].append(t)
                if ident in seen:
                    continue
                seen.add(ident)
                feedback = ident in feedback_roots and not ({ident, t['session_id']} & hard_excluded)
                if not feedback and (ident in excluded or t['session_id'] in excluded):
                    stats['excluded_maintenance'] += 1
                    continue
                if not t['is_root']:
                    stats['excluded_nonroot'] += 1
                    continue
                reason = t['reason']
                if reason:
                    held[reason] += 1
                    continue
                thread = t['thread']
                repositories[thread['repository']] += 1
                eligible.append({**thread, 'archived': archived,
                                 'kind': 'maintenance-feedback' if feedback else 'work'})
            if older:
                break
    progress = getattr(proxy, 'progress', None)
    if progress and progress.hits:
        # Confirm each native first page live; cached confirmations cannot prove
        # the source stayed stable. Two finite page reads leave cached acquisition
        # progress intact if confirmation itself exhausts this attempt's budget.
        for archived in (False, True):
            params = dict(archived=archived, sortKey='updated_at', sortDirection='desc',
                          sourceKinds=['cli', 'vscode', 'exec', 'appServer'], useStateDbOnly=True, cwd=sorted({r['cwd'] for r in config['repos']}), limit=50)
            response = proxy.call('thread/list', params)
            require(isinstance(response.get('data'), list) and len(response['data']) <= 50,
                    'invalid live head page')
            fresh = [t for t in index_page(response['data'], config, codex_home) if relevant(t)]
            require(fresh == anchors[archived],
                    'index head changed during resume; preserve progress and restart explicitly')
        stats['resume_head_verified'] = 1
    unfinished = previous_source.get('deferred', {}).values()
    missing = {v['root_id'] for v in unfinished} - {t['id'] for t in eligible} - (excluded - (feedback_roots - hard_excluded))
    if missing:
        held['known_unfinished_root_outside_index'] += len(missing)
    selection = dict(version=1, source_id=config['source_id'], device_id=config['device_id'],
        host_id='local', codex_home=codex_home, adapter_selection=boundary, window=dict(since=since, cutoff=cutoff),
        coverage_complete=not held, threads=eligible,
        excluded_roots=sorted(excluded), feedback_excluded_roots=sorted(feedback_excluded),
        unfinished_by_root={root: sorted(v['unit_id'] for v in previous_source.get('deferred', {}).values() if v['root_id'] == root)
                            for root in {v['root_id'] for v in previous_source.get('deferred', {}).values()} - (excluded - (feedback_roots - hard_excluded))})
    stats.update(eligible_sessions=len(eligible), held_sessions=sum(held.values()))
    return selection, {**dict(stats), 'repositories': dict(repositories), 'held_reasons': dict(held)}
