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
    fields(document, 'version source_id requested_tasks reports window enumeration_complete')
    require(type(document['version']) is int and document['version'] == 1, 'unsupported retrospective version')
    safe_strings(document)
    text_id(document['source_id'])
    fields(document['window'], 'since cutoff')
    since, cutoff = (instant(document['window'][key]) for key in ('since', 'cutoff'))
    require(since < cutoff, 'empty or reversed retrospective window')
    require(type(document['enumeration_complete']) is bool, 'invalid enumeration completeness')
    tasks, reports = document['requested_tasks'], document['reports']
    require(isinstance(tasks, list) and isinstance(reports, list), 'retrospective lists required')
    require(len(tasks) <= max_reports and len(reports) <= max_reports, 'retrospective request/report budget exceeded')
    requested = {}
    for task in tasks:
        fields(task, 'task_id status')
        task_id = text_id(task['task_id'])
        require(task_id not in requested, 'duplicate requested task')
        require(isinstance(task['status'], str) and task['status'] in OUTCOMES, 'invalid requested status')
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
        require(completed is None or since <= completed <= cutoff, 'completion outside retrospective window')
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


def intake(args):
    require(type(args.max_reports) is int and 1 <= args.max_reports <= 2, 'max-reports must be 1 or 2')
    paths(args)
    target = read(args.target)
    identity = profile(target)
    document = read_envelope(args.input)
    since, cutoff, counts = validate(document, args.max_reports)
    source = document['source_id']
    explicit = {text_id(root) for root in args.exclude_root}
    current = os.environ.get('CODEX_THREAD_ID')
    with locked(args.state):
        # A case-only alias of the previously absent lock is detectable now.
        paths(args)
        state = load_state(args.state, identity)
        ledger = state.setdefault('retrospective_units', {})
        current_sources = {origin for origin, roots in state.get('maintenance_roots', {}).items()
                           if current and current in roots}
        require(len(current_sources) <= 1, 'current maintenance source registration is ambiguous')
        current_source = next(iter(current_sources), None)
        if current and current_source is None:
            require(not any(report['task_id'] == current for report in document['reports']) and
                    not any(unit['facts']['root_id'] == current for unit in ledger.values()),
                    'current maintenance source is not registered')
        exclusions = state.setdefault('retrospective_excluded_roots', {})
        excluded = set(exclusions.get(source, [])) | explicit
        excluded.update(report['task_id'] for report in document['reports'] if report['kind'] != 'work')
        registered = set(state.get('maintenance_roots', {}).get(source, []))
        pending_requests = state.setdefault('retrospective_pending_requests', {}).setdefault(source, {})
        for task in document['requested_tasks']:
            if task['status'] == 'received':
                pending_requests.pop(task['task_id'], None)
            else:
                saved = pending_requests.setdefault(task['task_id'], {'window': document['window']})
                saved['status'] = task['status']
        for root in excluded | registered:
            pending_requests.pop(root, None)
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
            units.sort(key=lambda unit: (unit['facts']['updated_at'] or '', unit['key']))
            groups.append(dict(id=digest([origin, root, sorted(unit['key'] for unit in units)]),
                               source_id=origin, root_id=root,
                               units=[dict(key=unit['key'], status=unit['status'],
                                           candidate_id=unit['candidate_id'], **unit['facts']) for unit in units],
                               needs_reconciliation=any(unit['status'] == 'applying' for unit in units)))
        groups.sort(key=lambda group: (group['units'][0]['updated_at'] or '',
                                       group['source_id'], group['root_id'], group['id']))
        reconciliation = [group for group in groups if group['needs_reconciliation']]
        held = [group for group in groups if args.new_evidence_only and
                all(unit['status'] in {'deferred', 'failed'} for unit in group['units'])]
        held_ids = {group['id'] for group in held}
        pending = [group for group in groups if not group['needs_reconciliation'] and group['id'] not in held_ids]
        selected = reconciliation + pending[:max(0, target['budget']['max_cases'] - len(reconciliation))]
        receipt_complete = counts['received'] == len(document['requested_tasks']) and not pending_requests
        coverage = (document['enumeration_complete'] and receipt_complete and
                    all(report['completed_at'] is not None for report in document['reports']))
        batch = dict(version=1, id=uuid.uuid4().hex, target=identity,
                     window=dict(since=stamp(since), cutoff=stamp(cutoff)), budget=target['budget'],
                     evidence_basis='self-report', history_coverage_complete=False, checkpoint_written=False,
                     requested_tasks=document['requested_tasks'],
                     pending_requests=[dict(task_id=task, **saved) for task, saved in sorted(pending_requests.items())],
                     unresolved_request_count=len(pending_requests),
                     requested_outcome_counts={status: counts[status] for status in sorted(OUTCOMES)},
                     report_receipt_complete=receipt_complete, window_coverage_complete=coverage,
                     status='ready' if selected else 'budget-exhausted' if pending else
                     'awaiting-evidence' if held else 'awaiting-input' if not receipt_complete or not coverage else 'no-new-input',
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
