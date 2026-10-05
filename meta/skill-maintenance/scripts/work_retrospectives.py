"""Bounded, offline intake of untrusted Work self-reports; never a native reader."""
from collections import Counter
import json
import os
import stat
import uuid

from common import SENSITIVE, instant, require, stamp, text_id
from maintenance import (TERMINAL, atomic_write, digest, load_state, locked,
                         private_path, profile, read, same_path)

OUTCOMES = {'received', 'unsupported', 'failed', 'held'}


def fields(value, expected):
    require(isinstance(value, dict) and set(value) == set(expected.split()),
            'unknown or missing retrospective fields')


def safe_strings(value):
    if isinstance(value, str):
        require(not SENSITIVE.search(value), 'sensitive retrospective content blocked')
    elif isinstance(value, list):
        for item in value:
            safe_strings(item)
    elif isinstance(value, dict):
        require(not {'raw_trace', 'raw_reasoning'} & value.keys(), 'raw retrospective material blocked')
        for key, item in value.items():
            safe_strings(key)
            safe_strings(item)


def read_envelope(path):
    require(not path.is_symlink(), 'symlink input is not supported')
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
    try:
        metadata = os.fstat(fd)
        require(stat.S_ISREG(metadata.st_mode), 'retrospective input must be a regular file')
        limit = 8 * 1024 * 1024
        require(metadata.st_size <= limit, 'retrospective input exceeds 8 MiB')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        require(len(raw) <= limit, 'retrospective input exceeds 8 MiB')
    finally:
        os.close(fd)

    def unique_fields(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate retrospective JSON field')
            result[key] = value
        return result

    def invalid_constant(_value):
        raise ValueError('invalid retrospective JSON constant')

    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique_fields,
                      parse_constant=invalid_constant)


def validate(document, max_reports):
    require(isinstance(document, dict) and type(document.get('version')) is int and
            document['version'] in {1, 2}, 'unsupported retrospective version')
    delta = document['version'] == 2
    fields(document, 'version source_id requested_tasks reports enumeration_complete ' +
           ('selection_basis' if delta else 'window'))
    safe_strings(document)
    text_id(document['source_id'])
    since = cutoff = None
    if delta:
        require(document['selection_basis'] == 'completed-turn-delta', 'invalid retrospective selection basis')
    else:
        fields(document['window'], 'since cutoff')
        since, cutoff = (instant(document['window'][key]) for key in ('since', 'cutoff'))
        require(since < cutoff, 'empty or reversed retrospective window')
    require(type(document['enumeration_complete']) is bool, 'invalid enumeration completeness')
    tasks, reports = document['requested_tasks'], document['reports']
    require(isinstance(tasks, list) and isinstance(reports, list), 'retrospective lists required')
    require(len(tasks) <= max_reports and len(reports) <= max_reports, 'retrospective request/report budget exceeded')
    requested = {}
    for task in tasks:
        fields(task, 'task_id status' + (' completed_turn_id receipt_turn_id' if delta else ''))
        task_id = text_id(task['task_id'])
        require(task_id not in requested, 'duplicate requested task')
        require(isinstance(task['status'], str) and task['status'] in OUTCOMES, 'invalid requested status')
        if delta:
            text_id(task['completed_turn_id'])
            if task['status'] == 'received':
                text_id(task['receipt_turn_id'])
            else:
                require(task['receipt_turn_id'] is None, 'unreceived request cannot have a receipt turn')
        requested[task_id] = task['status']
    seen = set()
    for report in reports:
        fields(report, 'task_id report_id revision source_repo information_scope kind completed_at received_at claims')
        task_id = text_id(report['task_id'])
        require(task_id not in seen, 'multiple reports for one task')
        seen.add(task_id)
        for key in ('report_id', 'source_repo', 'information_scope'):
            text_id(report[key])
        require(type(report['revision']) is int and report['revision'] > 0, 'invalid report revision')
        require(isinstance(report['kind'], str) and report['kind'] in {'work', 'skill-maintenance', 'evaluation'},
                'invalid report kind')
        completed = instant(report['completed_at']) if report['completed_at'] is not None else None
        received = instant(report['received_at']) if report['received_at'] is not None else None
        require(delta or completed is None or since <= completed <= cutoff, 'completion outside retrospective window')
        require(completed is None or received is None or received >= completed, 'receipt precedes completion')
        require(isinstance(report['claims'], list) and report['claims'], 'nonempty report claims required')
        for claim in report['claims']:
            fields(claim, 'summary evidence_refs unknowns')
            require(isinstance(claim['summary'], str) and claim['summary'].strip(), 'empty claim summary')
            refs = claim['evidence_refs']
            require(isinstance(refs, list) and refs and all(isinstance(ref, str) and ref.strip() for ref in refs),
                    'nonempty opaque evidence references required')
            require(isinstance(claim['unknowns'], list) and all(isinstance(item, str) for item in claim['unknowns']),
                    'invalid claim unknowns')
    require(seen == {task for task, status in requested.items() if status == 'received'},
            'received statuses must match reports exactly')
    return since, cutoff, Counter(requested.values())


def paths(args):
    require(args.repo.is_dir(), 'target repository directory is missing')
    for path in (args.input, args.state, args.output):
        private_path(path, args.repo)
        require(not any(same_path(parent, args.repo) for parent in (path, *path.parents)),
                'state/output must be outside target repository')
    require(not args.output.exists() or args.output.is_dir(), 'retrospective output must be a directory')
    lock = args.state.with_name(args.state.name + '.lock')
    for protected in (args.target, args.state, args.input, lock):
        # A dedicated directory cannot contain a protected file, or live inside it.
        require(not any(same_path(parent, protected) for parent in (args.output, *args.output.parents)) and
                not any(same_path(args.output, parent) for parent in protected.parents),
                'retrospective output overlaps protected input/state/lock')
    require(not same_path(args.state, args.target) and not same_path(args.state, args.input),
            'retrospective state must not overwrite inputs')


def facts(source, report):
    return {**report, 'source_id': source, 'root_id': report['task_id'], 'id': report['report_id'],
            'updated_at': stamp(instant(report['completed_at'] or report['received_at']))
            if report['completed_at'] or report['received_at'] else None,
            'completion_timestamp_missing': report['completed_at'] is None,
            'receipt_timestamp_missing': report['received_at'] is None, 'evidence_basis': 'self-report'}


def current_binding(state, current, incoming_roots):
    sources = {source for source, roots in state.get('maintenance_roots', {}).items()
               if current and current in roots}
    require(len(sources) <= 1, 'current maintenance source registration is ambiguous')
    if current and not sources:
        saved = {unit['facts']['root_id'] for unit in state.get('retrospective_units', {}).values()}
        for name in ('retrospective_pending_requests', 'retrospective_pending_turns'):
            saved.update(root for tasks in state.get(name, {}).values() for root in tasks)
        require(current not in set(incoming_roots) | saved, 'current maintenance source is not registered')
    return next(iter(sources), None)


def select(args):
    """Queue completed IDs from permitted host metadata; never receipt or transport."""
    require(type(args.max_reports) is int and 1 <= args.max_reports <= 2, 'max-reports must be 1 or 2')
    require(args.repo.is_dir(), 'target repository directory is missing')
    for path in (args.input, args.state):
        private_path(path, args.repo)
        require(not any(same_path(parent, args.repo) for parent in (path, *path.parents)),
                'selection input/state must be outside target repository')
    require(not same_path(args.state, args.target) and not same_path(args.state, args.input) and
            not same_path(args.input, args.state.with_name(args.state.name + '.lock')),
            'selection state/lock must not overwrite inputs')
    identity = profile(read(args.target))
    document = read_envelope(args.input)
    fields(document, 'version source_id enumeration_complete tasks')
    require(type(document['version']) is int and document['version'] == 1, 'unsupported selection version')
    safe_strings(document)
    source = text_id(document['source_id'])
    require(type(document['enumeration_complete']) is bool and isinstance(document['tasks'], list),
            'invalid host metadata')
    tasks = {}
    for task in document['tasks']:
        fields(task, 'task_id latest_turn_id latest_turn_status source_repo information_scope kind')
        root = text_id(task['task_id'])
        require(root not in tasks, 'duplicate host task')
        for key in ('latest_turn_id', 'source_repo', 'information_scope'):
            text_id(task[key])
        require(task['latest_turn_status'] in {'completed', 'inProgress', 'failed', 'interrupted'},
                'unsupported host turn status')
        require(task['kind'] in {'work', 'skill-maintenance', 'evaluation'}, 'invalid host task kind')
        tasks[root] = task
    explicit = {text_id(root) for root in args.exclude_root}
    current = os.environ.get('CODEX_THREAD_ID')
    with locked(args.state):
        state = load_state(args.state, identity)
        original_digest = digest(state)
        current_source = current_binding(state, current, tasks)
        old_excluded = set(state.get('retrospective_excluded_roots', {}).get(source, []))
        new_excluded = old_excluded | explicit | {root for root, task in tasks.items() if task['kind'] != 'work'}
        if new_excluded != old_excluded:
            state.setdefault('retrospective_excluded_roots', {})[source] = sorted(new_excluded)
        excluded = (set(state.get('maintenance_roots', {}).get(source, [])) |
                    new_excluded)
        if source == current_source:
            excluded.add(current)
        pending = state.get('retrospective_pending_requests', {}).get(source, {})
        seen = state.get('retrospective_seen_turns', {}).get(source, {})
        latest_reports = {}
        for key, unit in state.get('retrospective_units', {}).items():
            fact = unit['facts']
            if fact['source_id'] == source:
                previous = latest_reports.get(fact['task_id'])
                if previous is None or fact['revision'] > previous[1]:
                    latest_reports[fact['task_id']] = (key, fact['revision'])
        unbound_reports = {root for root, (key, _revision) in latest_reports.items()
                           if key not in state.get('retrospective_unit_turns', {})}
        requests = []
        unbound = []
        unbound_receipts = []
        held_retry = []
        eligible_turns = 0
        old_turns = state.get('retrospective_pending_turns', {}).get(source, {})
        pending_turns = {root: list(turns) for root, turns in old_turns.items()}
        for root in excluded:
            pending.pop(root, None)
            pending_turns.pop(root, None)
        for root, task in sorted(tasks.items()):
            if (root in excluded or task['kind'] != 'work' or
                    task['source_repo'] not in identity['source_repos'] or
                    task['information_scope'] not in {'public', identity['information_scope']}):
                continue
            retry = pending.get(root)
            if task['latest_turn_status'] == 'inProgress':
                if retry:
                    held_retry.append(root)
                continue
            consumed = set(seen.get(root, []))
            turns = pending_turns.get(root, [])
            latest = task['latest_turn_id']
            if task['latest_turn_status'] == 'completed' and latest not in consumed and latest not in turns:
                pending_turns[root] = turns = turns + [latest]
            if retry and not retry.get('completed_turn_id'):
                unbound.append(root)
                continue
            if root in unbound_reports:
                unbound_receipts.append(root)
                continue
            turn = retry['completed_turn_id'] if retry else next((turn for turn in turns if turn not in consumed), None)
            if turn is None:
                continue
            eligible_turns += len((set(turns) | {turn}) - consumed)
            previous = [unit['facts'] for unit in state.get('retrospective_units', {}).values()
                        if unit['facts']['source_id'] == source and unit['facts']['task_id'] == root]
            requests.append(dict(task_id=root, completed_turn_id=turn, retry=bool(retry),
                                 report_id=previous[0]['report_id'] if previous else None,
                                 revision=max((fact['revision'] for fact in previous), default=0) + 1))
        requests.sort(key=lambda request: (not request['retry'], request['task_id']))
        if pending_turns != old_turns:
            state.setdefault('retrospective_pending_turns', {})[source] = pending_turns
        if digest(state) != original_digest:
            atomic_write(args.state, state)
        return dict(source_id=source, selection_basis='completed-turn-delta',
                    requested_tasks=requests[:args.max_reports], eligible_completed_turns=eligible_turns,
                    queued_completed_turns=max(0, eligible_turns - min(len(requests), args.max_reports)),
                    enumeration_complete=document['enumeration_complete'],
                    legacy_unbound_requests=unbound, legacy_unbound_reports=unbound_receipts,
                    held_retry_tasks=held_retry, unresolved_request_count=len(pending),
                    source_coverage='unknown', history_coverage_complete=False, checkpoint_written=False)


def intake(args):
    require(type(args.max_reports) is int and 1 <= args.max_reports <= 2, 'max-reports must be 1 or 2')
    paths(args)
    target = read(args.target)
    identity = profile(target)
    document = read_envelope(args.input)
    since, cutoff, counts = validate(document, args.max_reports)
    delta = document['version'] == 2
    source = document['source_id']
    explicit = {text_id(root) for root in args.exclude_root}
    current = os.environ.get('CODEX_THREAD_ID')
    with locked(args.state):
        # A case-only alias of the previously absent lock is detectable now.
        paths(args)
        state = load_state(args.state, identity)
        ledger = state.setdefault('retrospective_units', {})
        current_source = current_binding(state, current, (task['task_id'] for task in document['requested_tasks']))
        exclusions = state.setdefault('retrospective_excluded_roots', {})
        excluded = set(exclusions.get(source, [])) | explicit
        excluded.update(report['task_id'] for report in document['reports'] if report['kind'] != 'work')
        registered = set(state.get('maintenance_roots', {}).get(source, []))
        pending_requests = state.setdefault('retrospective_pending_requests', {}).setdefault(source, {})
        for task in document['requested_tasks']:
            existing_request = pending_requests.get(task['task_id'])
            require(delta or not existing_request or not existing_request.get('completed_turn_id'),
                    'turn-bound missing request requires v2 input')
            if task['status'] == 'received':
                previous_request = pending_requests.get(task['task_id'])
                require(not delta or not previous_request or
                        previous_request['completed_turn_id'] == task['completed_turn_id'],
                        'retry must preserve unreceived completed turn')
                pending_requests.pop(task['task_id'], None)
            else:
                context = ({'selection_basis': 'completed-turn-delta', 'completed_turn_id': task['completed_turn_id']}
                           if delta else {'window': document['window']})
                saved = pending_requests.setdefault(task['task_id'], context)
                require(not delta or
                        saved['completed_turn_id'] == task['completed_turn_id'],
                        'retry must preserve unreceived completed turn')
                saved['status'] = task['status']
        for root in excluded | registered:
            pending_requests.pop(root, None)
            state.get('retrospective_pending_turns', {}).get(source, {}).pop(root, None)
        excluded_count = 0
        for report in document['reports']:
            key = digest(['work-retrospective', source, report['task_id'], report['revision']])
            snapshot = facts(source, report)
            previous = [unit['facts'] for unit in ledger.values()
                        if unit['facts']['source_id'] == source and unit['facts']['root_id'] == report['task_id']]
            require(all(fact['report_id'] == report['report_id'] for fact in previous),
                    'stable retrospective report ID changed')
            require(key in ledger or not previous or report['revision'] > max(fact['revision'] for fact in previous),
                    'unregistered older retrospective revision')
            require(key not in ledger or ledger[key]['facts'] == snapshot,
                    'report changed at same revision; submit a new revision')
            if (report['task_id'] in excluded | registered or source == current_source and report['task_id'] == current or
                    report['source_repo'] not in identity['source_repos'] or
                    report['information_scope'] not in {'public', identity['information_scope']}):
                excluded_count += 1
                continue
            ledger.setdefault(key, dict(facts=snapshot, status='pending', candidate_id=None))
            if delta:
                request = next(task for task in document['requested_tasks'] if task['task_id'] == report['task_id'])
                bindings = state.setdefault('retrospective_unit_turns', {})
                binding = {name: request[name] for name in ('completed_turn_id', 'receipt_turn_id')}
                require(key not in bindings or bindings[key] == binding,
                        'same revision cannot refer to different work/receipt turns')
                bindings[key] = binding
                seen = state.setdefault('retrospective_seen_turns', {}).setdefault(source, {})
                seen[report['task_id']] = sorted(set(seen.get(report['task_id'], [])) |
                                                 {request['completed_turn_id'], request['receipt_turn_id']})
                queue = state.get('retrospective_pending_turns', {}).get(source, {})
                if report['task_id'] in queue:
                    remaining = [turn for turn in queue[report['task_id']] if turn not in seen[report['task_id']]]
                    if remaining:
                        queue[report['task_id']] = remaining
                    else:
                        queue.pop(report['task_id'])
        grouped = {}
        for key, unit in ledger.items():
            fact = unit['facts']
            origin, root = fact['source_id'], fact['root_id']
            roots = excluded if origin == source else set(exclusions.get(origin, []))
            roots = roots | set(state.get('maintenance_roots', {}).get(origin, []))
            if unit['status'] in TERMINAL or root in roots or origin == current_source and root == current:
                continue
            phase = (unit['status'], unit['candidate_id']) if unit['status'] in {'evaluated', 'applying'} else ('pending', None)
            grouped.setdefault((origin, root, phase), []).append({'key': key, **unit})
        groups = []
        for (origin, root, _), units in grouped.items():
            units.sort(key=(lambda unit: (unit['facts']['revision'], unit['key'])) if delta else
                       (lambda unit: (unit['facts']['updated_at'] or '', unit['key'])))
            groups.append(dict(id=digest([origin, root, sorted(unit['key'] for unit in units)]),
                               source_id=origin, root_id=root,
                               units=[dict(key=unit['key'], status=unit['status'],
                                           candidate_id=unit['candidate_id'], **unit['facts']) for unit in units],
                               needs_reconciliation=any(unit['status'] == 'applying' for unit in units)))
        groups.sort(key=(lambda group: (group['source_id'], group['root_id'], group['id'])) if delta else
                    (lambda group: (group['units'][0]['updated_at'] or '',
                                    group['source_id'], group['root_id'], group['id'])))
        reconciliation = [group for group in groups if group['needs_reconciliation']]
        held = [group for group in groups if args.new_evidence_only and
                all(unit['status'] in {'deferred', 'failed'} for unit in group['units'])]
        held_ids = {group['id'] for group in held}
        pending = [group for group in groups if not group['needs_reconciliation'] and group['id'] not in held_ids]
        selected = reconciliation + pending[:max(0, target['budget']['max_cases'] - len(reconciliation))]
        receipt_complete = counts['received'] == len(document['requested_tasks']) and not pending_requests
        coverage = (not delta and document['enumeration_complete'] and receipt_complete and
                    all(report['completed_at'] is not None for report in document['reports']))
        batch = dict(version=1, id=uuid.uuid4().hex, target=identity,
                     window=None if delta else dict(since=stamp(since), cutoff=stamp(cutoff)), budget=target['budget'],
                     selection_basis='completed-turn-delta' if delta else 'time-window',
                     source_coverage='unknown',
                     visible_delta_receipt_complete=(document['enumeration_complete'] and receipt_complete and
                                                     not state.get('retrospective_pending_turns', {}).get(source)) if delta else None,
                     evidence_basis='self-report', history_coverage_complete=False, checkpoint_written=False,
                     requested_tasks=document['requested_tasks'],
                     pending_requests=[dict(task_id=task, **saved) for task, saved in sorted(pending_requests.items())],
                     unresolved_request_count=len(pending_requests),
                     requested_outcome_counts={status: counts[status] for status in sorted(OUTCOMES)},
                     report_receipt_complete=receipt_complete, window_coverage_complete=coverage,
                     status='ready' if selected else 'budget-exhausted' if pending else
                     'awaiting-evidence' if held else 'awaiting-input' if not receipt_complete or
                     not (document['enumeration_complete'] if delta else coverage) else 'no-new-input',
                     cases=selected, queued_cases=len(groups), unfinished_units=0, excluded_reports=excluded_count,
                     source_id=source, held_cases=len(held), held_case_ids=sorted(held_ids),
                     evidence_quality=dict(with_trace=0, outcomes_independently_verified=False))
        batch_path = args.output / (batch['id'] + '.json')
        require(not batch_path.exists() and not batch_path.is_symlink(), 'immutable retrospective batch already exists')
        atomic_write(batch_path, batch)
        exclusions[source] = sorted(excluded)
        state.setdefault('batches', {})[batch['id']] = digest(batch)
        state['latest_batch'] = batch['id']
        atomic_write(args.state, state)
        return dict(batch=str(batch_path), status=batch['status'])
