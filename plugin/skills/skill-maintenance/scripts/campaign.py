#!/usr/bin/env python3
"""Private evaluation ledger. Dispatch and adoption remain separate host decisions (Python 3.11+)."""
import argparse
from contextlib import contextmanager
import fcntl
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
import time
import uuid

_SPEC = importlib.util.spec_from_file_location('maintenance_workbench',
    Path(__file__).resolve().parents[2] / 'skill-workbench/scripts/workbench.py')
wb = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(wb)
require = wb.require


def number(value, name):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0, f'invalid {name}')


def sync_directory(folder):
    descriptor = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def save(folder, state):
    # Replace only this campaign's state; acquisition / retrospective state is never opened.
    with tempfile.NamedTemporaryFile('w', dir=folder, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(state, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        temporary.replace(folder / 'state.json')
        sync_directory(folder)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def locked(folder):
    with (folder / 'lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        state = wb.read(folder / 'state.json')
        require(state['plan_digest'] == wb.digest(wb.read(folder / 'plan.json')), 'plan changed')
        yield state
        save(folder, state)


def create(folder, plan):
    wb.validate_suite(plan['suite'])
    require(plan['version'] == 1 and plan['baseline'] != plan['candidate'], 'invalid candidates/version')
    for key in ('baseline', 'candidate', 'proposer'):
        wb.identifier(plan[key])
    require(set(plan['budget']) <= {'max_runs', 'max_seconds'},
            'unsupported budget: token/cost caps need a host hard limiter, never silently discard them')
    for key, value in plan['budget'].items():
        number(value, key)
        require(value > 0 and (key != 'max_runs' or type(value) is int), 'invalid budget')
    require(isinstance(plan['environment'], str) and plan['environment'].strip(), 'frozen environment required')
    cases = plan['suite']['cases']
    require(set(plan['cases']) == {c['id'] for c in cases}, 'case metadata mismatch')
    families = {}
    for case in cases:
        meta = plan['cases'][case['id']]
        require(meta['origin'] in {'practice', 'guide', 'synthetic'}, 'invalid origin')
        require(type(meta['normal']) is bool, 'normal must be boolean')
        require(isinstance(meta['evidence'], str) and meta['evidence'].strip(), 'evidence required')
        wb.identifier(meta['family'])
        require(families.setdefault(meta['family'], case['split']) == case['split'], 'family crosses splits')
        require(any(c['id'] == meta['false_success_check'] and c['required'] for c in case['checks']),
                'false success needs a required check')
    require({c['split'] for c in cases} == {'train', 'validation', 'test'}, 'three splits required')
    require(any(m['normal'] for m in plan['cases'].values()), 'normal cases required')
    folder.mkdir(parents=True, exist_ok=False)
    os.chmod(folder, 0o700)
    wb.write_new(folder / 'plan.json', plan)
    with (folder / 'plan.json').open('rb') as stream:
        os.fsync(stream.fileno())
    sync_directory(folder.parent)
    save(folder, {'version': 1, 'plan_digest': wb.digest(plan), 'attempts': [], 'selection': None})


def status(folder):
    with locked(folder) as state:
        return state


def claim(folder, candidate, case_id, repeat, timeout):
    number(timeout, 'timeout')
    require(timeout > 0 and type(repeat) is int and repeat > 0, 'positive timeout/repeat required')
    with locked(folder) as state:
        require('gate' not in state, 'campaign frozen after gate')
        plan = wb.read(folder / 'plan.json')
        require(candidate in (plan['baseline'], plan['candidate']), 'unknown candidate')
        case = next((c for c in plan['suite']['cases'] if c['id'] == case_id), None)
        require(case is not None, 'unknown case')
        require(not any(a['candidate'] == candidate and a['case'] == case_id and a['repeat'] == repeat
                        for a in state['attempts']), 'already claimed; retain uncertain attempts, use new repeat after recovery')
        require(case['split'] != 'test' or (state['selection'] is not None and
                state['selection']['decision'] == 'approve'), 'select before test')
        require(case['split'] == 'test' or state['selection'] is None, 'selection frozen')
        require(not any(a['status'] == 'running' for a in state['attempts']), 'another attempt is running')
        budget = plan['budget']
        require(len(state['attempts']) < budget.get('max_runs', math.inf), 'run budget exhausted')
        used = sum(a.get('charged_seconds', a['timeout']) for a in state['attempts'])
        require(used + timeout <= budget.get('max_seconds', math.inf), 'time budget exhausted')
        attempt = {'id': uuid.uuid4().hex, 'candidate': candidate, 'case': case_id, 'repeat': repeat,
                   'timeout': timeout, 'status': 'running', 'claimed_at': time.time()}
        state['attempts'].append(attempt)
        return attempt


def find_attempt(state, ident):
    require('gate' not in state, 'campaign frozen after gate')
    attempt = next((a for a in state['attempts'] if a['id'] == ident), None)
    require(attempt is not None, 'unknown attempt')
    require(attempt['status'] == 'running', 'attempt already finalized')
    return attempt


def finish(folder, ident, run_folder):
    """Import only integrity-checked workbench evidence; no raw trace leaves its private archive."""
    run_folder = run_folder.resolve()
    run = wb.load_run(run_folder)
    with locked(folder) as state:
        a = find_attempt(state, ident)
        plan = wb.read(folder / 'plan.json')
        require(run['suite'] == wb.digest(plan['suite']), 'suite mismatch')
        require(all(run[k] == a[k] for k in ('candidate', 'case', 'repeat')), 'claim mismatch')
        require(run['status'] in {'completed', 'timeout', 'error'}, 'invalid run status')
        require(run['environment'] == plan['environment'], 'environment mismatch')
        require(not any(x.get('run') == str(run_folder) for x in state['attempts']), 'run already imported')
        duration = run['metrics']['duration_seconds']
        number(duration, 'duration')
        state['environment'] = run['environment']
        a.update(status=run['status'], run=str(run_folder), run_digest=wb.digest(run),
                 charged_seconds=max(a['timeout'], duration),
                 exceeded_timeout=duration > a['timeout'])
        # Reserve the entire authorized slot, including setup/host overhead; no implicit refund.
        return a


def interrupt(folder, ident, evidence):
    require(isinstance(evidence, str) and evidence.strip(), 'stopped-process evidence required')
    with locked(folder) as state:
        a = find_attempt(state, ident)
        a.update(status='interrupted', charged_seconds=a['timeout'], recovery_evidence=evidence)
        return a


def loaded(plan, state):
    records = []
    for a in state['attempts']:
        if 'run' not in a:
            continue
        run = wb.load_run(Path(a['run']))
        require(wb.digest(run) == a['run_digest'], 'imported evidence changed; create a new campaign')
        records.append(run)
    return records


def summarize_state(plan, state):
    records = loaded(plan, state)
    comparisons, splits = {}, {}
    for split in ('train', 'validation', 'test'):
        selected = [c for c in plan['suite']['cases'] if c['split'] == split]
        comparison = wb.compare(plan['suite'], records, plan['baseline'], plan['candidate'], split)
        comparisons[split] = comparison
        per_candidate = {}
        for label in ('baseline', 'candidate'):
            aa = [a for a in state['attempts'] if a['candidate'] == plan[label] and
                  a['case'] in {c['id'] for c in selected}]
            rr = [r for r in records if r['candidate'] == plan[label] and r['case'] in {c['id'] for c in selected}]
            successes = false_successes = 0
            for r in rr:
                case = next(c for c in selected if c['id'] == r['case'])
                if r['status'] == 'completed':
                    successes += all(r['checks'].get(c['id'], {}).get('verdict') == 'pass'
                                     for c in case['checks'] if c['required'])
                    check = plan['cases'][r['case']]['false_success_check']
                    false_successes += r['checks'].get(check, {}).get('verdict') == 'fail'
            metrics = {}
            for key in ('duration_seconds', 'tokens', 'cost_usd'):
                values = [r['metrics'].get(key) for r in rr]
                metrics[key] = sum(values) if values and len(values) == len(aa) and None not in values else None
            per_candidate[label] = {'attempts': len(aa), 'runs': len(rr), 'successes': successes,
                'success_rate': successes / len(aa) if aa else None, 'false_successes': false_successes,
                'unresolved_runs': sum(r['status'] != 'completed' or not r['checks'] or
                                      any(c.get('verdict') == 'unknown' for c in r['checks'].values()) for r in rr),
                **metrics}
        per_candidate['normal_regressions'] = sum(row['outcome'] == 'regressed' and plan['cases'][row['case']]['normal']
                                                  for row in comparison['rows'])
        splits[split] = per_candidate
    evidence = wb.digest({'plan': wb.digest(plan), 'attempts': state['attempts'], 'comparisons': comparisons})
    return {'evidence_digest': evidence, 'comparisons': comparisons, 'splits': splits,
            'attempts': len(state['attempts']),
            'unresolved_attempts': sum(a['status'] != 'completed' for a in state['attempts']),
            'running': sum(a['status'] == 'running' for a in state['attempts']),
            'charged_seconds': sum(a.get('charged_seconds', a['timeout']) for a in state['attempts'])}


def summarize(folder):
    with locked(folder) as state:
        return summarize_state(wb.read(folder / 'plan.json'), state)


def clean_split(plan, summary, split):
    comparison = summary['comparisons'][split]
    require(comparison['assessment'] not in {'regressed', 'tradeoff', 'inconclusive'}, f'{split} has regression/missing evidence')
    cases = {c['id']: c for c in plan['suite']['cases'] if c['split'] == split}
    require(all(row['after'] == 'pass' for row in comparison['rows']
                if next(c for c in cases[row['case']]['checks'] if c['id'] == row['check'])['required']),
            'candidate required checks must pass, including failure ties')


def review_input(plan, state, reviewer, evidence_digest, reason):
    wb.identifier(reviewer)
    require(reviewer != plan['proposer'], 'independent reviewer required')
    require(isinstance(reason, str) and reason.strip(), 'review reason required')
    summary = summarize_state(plan, state)
    require(summary['evidence_digest'] == evidence_digest, 'stale review evidence')
    require(not summary['running'], 'running/uncertain attempts remain')
    require(not summary['unresolved_attempts'], 'unresolved attempts: adoption held; retry in a new campaign')
    require(not any(a.get('exceeded_timeout') for a in state['attempts']), 'host timeout enforcement failed')
    return summary


def select(folder, reviewer, decision, evidence_digest, reason):
    with locked(folder) as state:
        plan = wb.read(folder / 'plan.json')
        require(state['selection'] is None, 'selection is immutable; create new campaign')
        require(not any(a['case'] in {c['id'] for c in plan['suite']['cases'] if c['split'] == 'test'}
                        for a in state['attempts']), 'holdout already used')
        summary = review_input(plan, state, reviewer, evidence_digest, reason)
        require(decision in {'approve', 'hold', 'reject'}, 'invalid selection decision')
        if decision == 'approve':
            for split in ('train', 'validation'):
                clean_split(plan, summary, split)
        state['selection'] = {'reviewer': reviewer, 'decision': decision, 'reason': reason,
                              'evidence_digest': evidence_digest}
        return state['selection']


def gate(folder, reviewer, evidence_digest, reason):
    with locked(folder) as state:
        plan = wb.read(folder / 'plan.json')
        summary = review_input(plan, state, reviewer, evidence_digest, reason)
        require(state['selection'] is not None and state['selection']['decision'] == 'approve', 'not selected')
        for split in ('train', 'validation', 'test'):
            clean_split(plan, summary, split)
        require(any(summary['comparisons'][s]['assessment'] == 'improved' for s in ('train', 'validation')),
                'no demonstrated quality advantage; burden-only decisions need separate paired analysis')
        result = {'status': 'eligible_for_draft', 'reviewer': reviewer, 'reason': reason,
                  'evidence_digest': evidence_digest, 'candidate': plan['candidate'],
                  'efficacy_scope': sorted({m['origin'] for m in plan['cases'].values()}),
                  'deployment_changed': False}
        require('gate' not in state, 'gate already recorded')
        state['gate'] = result
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('create', 'status', 'claim', 'finish', 'interrupt', 'summary', 'select', 'gate'):
        command = commands.add_parser(name)
        command.add_argument('--campaign', type=Path, required=True)
        if name == 'create':
            command.add_argument('--plan', type=Path, required=True)
        if name == 'claim':
            command.add_argument('--candidate', required=True)
            command.add_argument('--case', required=True)
            command.add_argument('--repeat', type=int, required=True)
            command.add_argument('--timeout', type=float, required=True)
        if name in ('finish', 'interrupt'):
            command.add_argument('--attempt', required=True)
        if name == 'finish':
            command.add_argument('--run', type=Path, required=True)
        if name == 'interrupt':
            command.add_argument('--evidence', required=True)
        if name in ('select', 'gate'):
            command.add_argument('--reviewer', required=True)
            command.add_argument('--evidence-digest', required=True)
            command.add_argument('--reason', required=True)
        if name == 'select':
            command.add_argument('--decision', choices=('approve', 'hold', 'reject'), required=True)
    args = parser.parse_args()
    try:
        folder = args.campaign
        if args.command == 'create':
            create(folder, wb.read(args.plan)); result = {'created': True}
        elif args.command == 'status': result = status(folder)
        elif args.command == 'summary': result = summarize(folder)
        elif args.command == 'claim': result = claim(folder, args.candidate, args.case, args.repeat, args.timeout)
        elif args.command == 'finish': result = finish(folder, args.attempt, args.run)
        elif args.command == 'interrupt': result = interrupt(folder, args.attempt, args.evidence)
        elif args.command == 'select':
            result = select(folder, args.reviewer, args.decision, args.evidence_digest, args.reason)
        else: result = gate(folder, args.reviewer, args.evidence_digest, args.reason)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, json.dumps({'error': str(error)}, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
