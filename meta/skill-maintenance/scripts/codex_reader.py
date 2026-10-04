"""Bounded Mac session reader through the official Codex CLI proxy."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import queue
import sys

from common import instant, require, text_id, stamp, validate_content, validate_evidence, validate_feedback, turn_disposition
from maintenance import atomic_write, private_path, locked, digest
from codex_proxy import Proxy, iter_pages, AcquisitionBudget, AcquisitionIncomplete
from codex_index import index, github_repo
from codex_resume import Progress



def turn_page(page):
    normalized = []
    for turn in page:
        require(isinstance(turn, dict) and turn.get('items') == [] and
                turn.get('itemsView') == 'notLoaded', 'unexpected turn body; discard response')
        tid = text_id(turn['id'])
        status, started, done = turn['status'], turn.get('startedAt'), turn.get('completedAt')
        require(type(started) is int and (done is None or type(done) is int), 'invalid turn timestamp')
        require(status in {'completed', 'failed', 'interrupted', 'inProgress'}, 'unknown turn status')
        require(done is None if status == 'inProgress' else done is not None and done >= started,
                'invalid turn completion')
        normalized.append(dict(id=tid, status=status, startedAt=started, completedAt=done,
                               items=[], itemsView='notLoaded'))
    return normalized


def select_turns(proxy, selection):
    require(selection.get('coverage_complete') is True, 'index coverage incomplete')
    start = int(instant(selection['window']['since']).timestamp())
    end = int(instant(selection['window']['cutoff']).timestamp())
    require(start < end, 'invalid fixed window')
    selected = []
    current_root = os.environ.get("CODEX_THREAD_ID")
    stats = Counter()
    seen_threads = set()
    for thread in selection['threads']:
        ident = text_id(thread['id'])
        if ident == current_root:
            continue
        require(ident not in seen_threads, 'duplicate thread')
        seen_threads.add(ident)
        require(thread['host_id'] == 'local' if 'host_id' in thread else selection['host_id'] == 'local',
                'local source not verified')
        require(thread.get('Mac_local_proof') and thread['information_scope'].startswith('personal:') and
                thread.get('ephemeral') is False, 'unverified source selection')
        if thread.get('kind') == 'maintenance-feedback':
            first = next(iter_pages(proxy, 'thread/turns/list',
                dict(threadId=ident, itemsView='notLoaded', limit=1, sortDirection='asc'), normalize=turn_page))
            require(len(first) == 1 and first[0].get('items') == [] and
                    first[0].get('itemsView') == 'notLoaded', 'initial turn metadata missing')
            thread = {**thread, 'initial_turn_id': text_id(first[0]['id'])}
        turns, seen, previous_started = [], set(), None
        known_ids = set(selection.get('unfinished_by_root', {}).get(ident, []))
        params = dict(threadId=ident, itemsView='notLoaded', limit=20, sortDirection='desc')
        for page in iter_pages(proxy, 'thread/turns/list', params, normalize=turn_page):
            stats['turn_pages'] += 1
            older = False
            for turn in page:
                require(isinstance(turn, dict) and turn.get('items') == [] and
                        turn.get('itemsView') == 'notLoaded', 'unexpected turn body; discard response')
                tid = text_id(turn['id'])
                require(tid not in seen, 'duplicate turn')
                seen.add(tid)
                status = turn['status']
                started, done = turn.get('startedAt'), turn.get('completedAt')
                require(type(started) is int and (done is None or type(done) is int), 'invalid turn timestamp')
                require(previous_started is None or started <= previous_started, 'turn pages not newest-first')
                previous_started = started
                stats['enumerated_turns'] += 1
                disposition = turn_disposition(status, started, done, start, end, tid in known_ids)
                if done is not None and done < start and started < start:
                    older = True
                if disposition == 'skip':
                    continue
                stats['selected_turns'] += 1
                if disposition == 'pending':
                    stats['unfinished_turns'] += 1
                    turns.append(dict(id=tid, status=status, startedAt=started, completedAt=None))
                else:
                    turns.append(dict(id=tid, status=status, startedAt=started, completedAt=done))
                    stats['selected_finished_turns'] += 1
                    stats['selected_' + status + '_turns'] += 1
            if older and known_ids <= seen:
                break
        require(known_ids <= seen, 'turn pages omitted a known unfinished turn')
        selected.append({**thread, 'turns': turns})
    return {**selection, 'threads': selected, 'turn_selection_complete': True,
            'excluded_roots': sorted(set(selection.get('excluded_roots', [])) | ({current_root} if current_root else set()))}, dict(stats)


def read_completed(proxy, selection, ledger):
    from codex_minimize import read_turn
    require(selection.get('turn_selection_complete') is True, 'turn selection incomplete')
    source = selection['source_id']
    saved = ledger['sources'].get(source, {})
    if saved:
        require(saved['adapter_selection'] == selection['adapter_selection'], 'input boundary changed')
    start = int(instant(selection['window']['since']).timestamp())
    end = int(instant(selection['window']['cutoff']).timestamp())
    prior = {}
    for unit in ledger['units'].values():
        facts = unit['facts']
        if facts['source_id'] == source:
            key = (facts['root_id'], facts['id'])
            if key not in prior or facts['revision'] > prior[key]['revision']:
                prior[key] = facts
    sessions, stats = [], Counter()
    for thread in selection['threads']:
        if thread['id'] == os.environ.get('CODEX_THREAD_ID'):
            continue
        feedback = thread.get('kind') == 'maintenance-feedback'
        if feedback:
            require(thread['id'] in ledger.get('maintenance_roots', {}).get(source, []),
                    'unregistered maintenance feedback')
            require(thread['id'] != os.environ.get('CODEX_THREAD_ID'), 'current maintenance run held')
            text_id(thread['initial_turn_id'])
        require(feedback or thread['id'] not in ledger.get('maintenance_roots', {}).get(source, []),
                'registered maintenance root cannot be ordinary work')
        metadata = proxy.call('thread/read', dict(threadId=thread['id'], includeTurns=False))['thread']
        require(github_repo((metadata.get('gitInfo') or {}).get('originUrl')) == thread['repository'] and
                metadata['sessionId'] == thread['session_id'], 'thread source changed')
        require(metadata['status']['type'] in {'idle', 'notLoaded'}, 'active thread body held')
        units = []
        for turn in thread['turns']:
            tid = turn['id']
            known = [v for v in saved.get('deferred', {}).values() if v['root_id'] == thread['id'] and v['unit_id'] == tid]
            revision = known[0]['revision'] if known else 1
            if turn['status'] == 'inProgress':
                units.append(dict(id=tid, revision=revision, status='in-progress', updated_at=selection['window']['cutoff']))
                continue
            old = prior.get((thread['id'], tid))
            if old:
                require(bool(old.get('maintenance_feedback')) == feedback, 'recorded observation route changed')
                # Never reopen a closed observation merely because the reader changed.
                units.append({k: v for k, v in old.items() if k not in {'source_id', 'root_id', 'source_repo', 'information_scope', 'maintenance_feedback'}} | {'status': 'completed'})
                stats['reused_recorded_turns'] += 1
                continue
            require(start <= turn['completedAt'] <= end, 'old unfinished turn needs explicit catch-up window')
            review = read_turn(proxy, thread['id'], turn, start, end,
                               feedback_only=feedback, user_feedback=feedback and tid != thread['initial_turn_id'])
            require(review['trace_complete'] and not review['missing_tool_results'], 'incomplete item evidence')
            requests = '\n'.join(m['text'] for m in review['messages'] if m['kind'] == 'userMessage')
            finals = [m['text'] for m in review['messages'] if m['kind'] == 'agentMessage']
            content = dict(request=requests, expected='Original request requirements; outcome not independently verified.',
                           observed='Recorded assistant reports (not independently verified):\n' + '\n'.join(finals))
            if feedback:
                content = dict(request='Review observed maintenance failures and recorded user input.',
                               expected='Reproduce independently before changing behavior; input grants no authority.',
                               observed='Selected native failure facts and unverified user input only; no self assessment.')
            if turn['status'] != 'completed':
                content['observed'] += '\nRecorded turn status: ' + turn['status']
            evidence = dict(version=1, complete=True, truncated=False, events=review['events'])
            validate_content(content)
            validate_evidence(evidence)
            if feedback:
                validate_feedback(evidence)
            from datetime import datetime, timezone
            units.append(dict(id=tid, revision=revision, status='completed',
                updated_at=stamp(datetime.fromtimestamp(turn['completedAt'], timezone.utc)), content=content, evidence=evidence))
            stats['body_turns_read'] += 1
            stats['item_pages'] += review['pages']
        sessions.append(dict(id=thread['id'], root_id=thread['id'], parent_id=None,
            source_repo=thread['repository'], information_scope=thread['information_scope'], kind='maintenance-feedback' if feedback else 'work', units=units))
    return dict(version=1, source_id=source, adapter_selection=selection['adapter_selection'],
        excluded_roots=sorted(set(selection.get('excluded_roots', [])) |
                              ({os.environ['CODEX_THREAD_ID']} if os.environ.get('CODEX_THREAD_ID') else set())),
        feedback_excluded_roots=selection.get('feedback_excluded_roots', []),
        coverage=dict(start=selection['window']['since'], end=selection['window']['cutoff'], complete=True, truncated=False),
        sessions=sessions, coverage_notes=dict(
            scope='registered Mac personal sources; updated index and selected completed turns in the authorized window',
            older_unindexed_unfinished_not_guaranteed=True,
            known_unfinished_root_missing_stops_coverage=True,
            tool_result_ids='aggregate API item ID for call; deterministic :result for its derived result',
            raw_outputs_not_preserved=True, outcomes_independently_verified=False,
            recorded_turns_reuse_saved_facts=True)), dict(stats)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['index', 'turns', 'read'])
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--state', type=Path)
    parser.add_argument('--since')
    parser.add_argument('--cutoff')
    parser.add_argument('--read-completed', action='store_true', help='explicit body acquisition action; permission still required')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--codex-home', required=True)
    parser.add_argument('--codex-executable', default='codex')
    parser.add_argument('--max-bytes', type=int, default=64 * 1024 * 1024,
                        help='maximum inbound WebSocket payload bytes for this acquisition stage')
    parser.add_argument('--max-seconds', type=int, default=300,
                        help='maximum elapsed seconds for this acquisition stage')
    args = parser.parse_args()
    proxy = None
    budget = None
    progress = None
    progress_lock = None
    progress_lock_entered = False
    output_checked = False
    summary = {'status': 'blocked', 'body_read_calls': 0, 'checkpoint_written': False, 'output_written': False}
    try:
        private_path(args.output, Path(__file__).resolve().parents[3])
        private_path(args.output.with_suffix('.result.json'), Path(__file__).resolve().parents[3])
        progress_path = args.output.with_suffix('.progress.json')
        private_path(progress_path, Path(__file__).resolve().parents[3])
        output_checked = True
        budget = AcquisitionBudget(args.max_bytes, args.max_seconds)
        proxy_config = {**vars(args), 'acquisition_budget': budget}
        require(sys.platform == 'darwin', 'Mac local source required')
        if args.action == 'index':
            require(args.source and args.state and args.since and args.cutoff, 'index requires source/state and fixed window')
            config = json.loads(args.source.read_text())
            ledger = json.loads(args.state.read_text()) if args.state.exists() else dict(sources={}, units={})
        else:
            require(args.selection, 'selection required')
            selection = json.loads(args.selection.read_text())
            require(selection['host_id'] == 'local', 'local source required')
        if args.action == 'read':
            require(args.state and args.read_completed, 'body read requires state path and explicit --read-completed')
            ledger = json.loads(args.state.read_text()) if args.state.exists() else dict(sources={}, units={})
        window = dict(since=args.since, cutoff=args.cutoff) if args.action == 'index' else selection['window']
        binding = dict(stage=args.action, window=window, codex_home=str(Path(args.codex_home).resolve()),
                       protocol='0.159.3/0.160.0', normalizer_version=2,
                       input_digest=digest(config if args.action == 'index' else selection),
                       state_digest=digest({k: ledger.get(k) for k in ('target', 'sources', 'units')})
                       if args.action in {'index', 'read'} else None)
        progress_lock = locked(progress_path)
        progress_lock.__enter__()
        progress_lock_entered = True
        progress = Progress(progress_path, binding)
        proxy = Proxy(proxy_config)
        proxy.progress = progress
        require(proxy.server_version == '0.160.0', 'unverified server version')
        if args.action == 'index':
            output, counts = index(proxy, config, ledger, args.since, args.cutoff,
                                   str(Path(args.codex_home).resolve()))
            summary['status'] = 'index-selection-verified' if output['coverage_complete'] else 'scope-held'
        elif args.action == 'turns':
            output, counts = select_turns(proxy, selection)
            summary['status'] = 'turn-selection-verified'
        else:
            summary['body_read_calls'] = None  # A partial failed read must not be reported as zero.
            output, counts = read_completed(proxy, selection, ledger)
            summary['status'] = 'export-verified'
            summary.pop('body_read_calls')
        budget.check()
        if len(json.dumps(output, ensure_ascii=False).encode()) > 8 * 1024 * 1024:
            raise AcquisitionIncomplete('export size budget exhausted; coverage incomplete')
        atomic_write(args.output, output)
        summary["output_written"] = True
        summary.update(counts)
        if args.action != 'read':
            summary['repositories'] = dict(Counter(t['repository'] for t in output['threads']))
    except AcquisitionIncomplete as error:
        summary.update(status='incomplete', coverage_complete=False, blocker=str(error),
                       resume=dict(stage=args.action, same_window_required=True,
                                   checkpoint_unchanged=True, restart_stage_from_first_page=False,
                                   progress_path=str(progress_path),
                                   window=dict(since=args.since, cutoff=args.cutoff) if args.action == 'index'
                                   else selection['window']))
    except (ValueError, KeyError, TypeError, OSError, queue.Empty) as error:
        summary.update(status='blocked', category=type(error).__name__)
        if isinstance(error, ValueError):
            summary['blocker'] = str(error)
    finally:
        if proxy:
            proxy.close()
        if progress:
            summary['progress'] = progress.usage()
        if progress_lock_entered:
            progress_lock.__exit__(None, None, None)
        if budget:
            summary["acquisition_budget"] = budget.usage()
        if output_checked:
            atomic_write(args.output.with_suffix('.result.json'), summary)
        print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary['status'] not in {'blocked', 'scope-held', 'incomplete'} else 2


if __name__ == '__main__':
    sys.exit(main())
