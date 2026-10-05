#!/usr/bin/env python3
"""Collect normalized, private exports and journal maintenance decisions. Python 3.11+."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from common import require, instant, stamp, text_id, validate_content, validate_evidence, validate_feedback
import hashlib
import json
import os
import re
from pathlib import Path
import sys
import tempfile
import uuid


TERMINAL = {"no-change", "applied"}
EXCLUDED_KINDS = {"skill-maintenance", "evaluation"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def read(path, limit=None):
    require(not path.is_symlink(), "symlink input is not supported")
    if limit is not None:
        require(path.stat().st_size <= limit, "input exceeds 8 MiB; export a smaller scope")
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path, value, indent=2):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=indent, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def locked(state):
    state.parent.mkdir(parents=True, exist_ok=True)
    lock = state.with_name(state.name + ".lock")
    try:
        lock.mkdir()
    except FileExistsError:
        raise ValueError("state is locked; check for a live process before manual recovery")
    try:
        yield
    finally:
        lock.rmdir()


def private_path(path, repo):
    require(not path.is_symlink(), "symlink output/state is not supported")
    require(not path.resolve().is_relative_to(repo.resolve()), "state/output must be outside target repository")


def same_path(first, second):
    return (first.resolve() == second.resolve() or
            first.exists() and second.exists() and first.samefile(second))


def profile(target):
    require(target["version"] == 1, "unsupported target version")
    require(target["manager"] in {"user", "organization"}, "excluded target: third-party or unknown manager")
    owner = text_id(target["owner"])
    require(target["management_verified"] is True, "unverified target management")
    scope = ("personal:" if target["manager"] == "user" else "organization:") + owner
    require(target["information_scope"] == scope, "target owner/scope mismatch")
    text_id(target["id"])
    require(isinstance(target["source_repos"], list) and target["source_repos"], "source repo allowlist is required")
    for source_repo in target["source_repos"]:
        text_id(source_repo)
    for key in ("max_cases", "max_runs"):
        require(type(target["budget"][key]) is int and target["budget"][key] >= 0, "invalid budget")
    return {**{key: target[key] for key in ("id", "owner", "manager", "information_scope")},
            'source_repos': sorted(set(target['source_repos']))}


def load_state(path, identity):
    if not path.exists():
        return {"version": 1, "target": identity, "sources": {}, "units": {}, "decisions": {}, "claims": {}}
    state = read(path)
    require(state["version"] == 1 and state["target"] == identity, "state target/scope mismatch")
    return state


def register_run(args):
    require(args.repo.is_dir(), "target repository directory is missing")
    private_path(args.state, args.repo)
    identity = profile(read(args.target))
    source, root = text_id(args.source_id), text_id(args.root_id)
    require(not os.environ.get('CODEX_THREAD_ID') or os.environ['CODEX_THREAD_ID'] == root,
            'registration must identify this maintenance run')
    with locked(args.state):
        state = load_state(args.state, identity)
        roots = state.setdefault('maintenance_roots', {}).setdefault(source, [])
        if root not in roots:
            roots.append(root)
            roots.sort()
        atomic_write(args.state, state)
    return dict(status='maintenance-run-registered', checkpoint_written=False)


def completed_facts(source, session, unit, updated):
    content = unit["content"]
    validate_content(content)
    validate_evidence(unit["evidence"])
    feedback = session['kind'] == 'maintenance-feedback'
    if feedback:
        validate_feedback(unit['evidence'])
    return {**({'maintenance_feedback': True} if feedback else {}),
            "source_id": source, "root_id": session["root_id"], "id": unit["id"],
            "source_repo": session["source_repo"], "information_scope": session["information_scope"],
            "revision": unit["revision"], "updated_at": stamp(updated), "content": content,
            "evidence": unit["evidence"]}


def check_selection(state, source, selection):
    require(selection is None or isinstance(selection, dict) and
            selection.get('mode') == 'repo-index', 'invalid adapter selection')
    previous = state['sources'].get(source)
    if previous:
        require(previous['adapter_selection'] == selection,
                'input selection changed; use a dedicated state')


def collect(args):
    require(args.repo.is_dir(), "target repository directory is missing")
    private_path(args.state, args.repo)
    private_path(args.output, args.repo)
    target = read(args.target)
    identity = profile(target)
    document = read(args.input, limit=8 * 1024 * 1024)
    require(document["version"] == 1, "unsupported export version")
    source = text_id(document["source_id"])
    cutoff = instant(args.cutoff) if args.cutoff else datetime.now(timezone.utc)
    require(args.hours > 0, "hours must be positive")
    since = instant(args.since) if args.since else cutoff - timedelta(hours=args.hours)
    require(since < cutoff, "empty or reversed window")
    with locked(args.state):
        state = load_state(args.state, identity)
        previous = state["sources"].get(source, {})
        feedback_roots = set(state.get('maintenance_roots', {}).get(source, []))
        selection = document.get('adapter_selection')
        check_selection(state, source, selection)
        if previous:
            through = instant(previous["through"])
            require(through <= cutoff, "cutoff precedes checkpoint")
            require(args.since is None or through >= since, 'checkpoint gap precedes authorized start; authorize a wider --since')
            since = min(since, through)
        coverage = document["coverage"]
        require(coverage["complete"] is True and instant(coverage["start"]) <= since
                and instant(coverage["end"]) >= cutoff, "incomplete export coverage; not no-change")
        require(coverage.get("truncated", False) is False, "truncated export coverage; not no-change")
        sessions = document["sessions"]
        require(isinstance(sessions, list), "sessions must be a list")
        indexed = {text_id(s["id"]): s for s in sessions}
        require(len(indexed) == len(sessions), "duplicate session ID")
        current_root = os.environ.get('CODEX_THREAD_ID')
        current_sources = {origin for origin, roots in state.get('maintenance_roots', {}).items()
                           if current_root and current_root in roots}
        require(len(current_sources) <= 1, 'current maintenance source registration is ambiguous')
        current_source = next(iter(current_sources), None)
        if current_root and current_source is None:
            require(not any(session['root_id'] == current_root for session in sessions) and
                    not any(unit['facts']['root_id'] == current_root for unit in state['units'].values()),
                    'current maintenance source is not registered')
        collecting_current_source = source == current_source
        for session in sessions:
            root = indexed.get(session["root_id"])
            require(root is not None and root["root_id"] == root["id"] and root["parent_id"] is None,
                    "missing or invalid root session")
            seen = set()
            node = session
            while node["parent_id"] is not None:
                require(node["id"] not in seen, "parent cycle")
                seen.add(node["id"])
                node = indexed.get(node["parent_id"])
                require(node is not None and node["root_id"] == root["id"], "invalid parent/root relationship")
            require(node["id"] == root["id"], "inconsistent root")
            require(session["source_repo"] == root["source_repo"] and
                    session["information_scope"] == root["information_scope"], "parent/child scope mismatch")
            require(session["kind"] in {"work", "maintenance-feedback", *EXCLUDED_KINDS}, "unknown session kind")
            if session['kind'] == 'maintenance-feedback':
                require(session['id'] == session['root_id'] and session['parent_id'] is None and
                        session['root_id'] in feedback_roots, 'unregistered maintenance feedback')
                require(not collecting_current_source or session['root_id'] != current_root,
                        'current maintenance run held')
        excluded_roots = {s["id"] for s in sessions if s["id"] == s["root_id"] and s["kind"] in EXCLUDED_KINDS}
        for exclusions in (document.get('excluded_roots', []), previous.get('excluded_roots', []), args.exclude_root):
            require(isinstance(exclusions, list) and all(isinstance(x, str) and x for x in exclusions),
                    'invalid persistent exclusions')
            excluded_roots.update(exclusions)
        excluded_roots.update(feedback_roots)
        hard_excluded = set(args.exclude_root) | {s['root_id'] for s in sessions if s['kind'] in EXCLUDED_KINDS}
        for exclusions in (document.get('feedback_excluded_roots', []), previous.get('feedback_excluded_roots', [])):
            require(isinstance(exclusions, list) and all(isinstance(x, str) and x for x in exclusions),
                    'invalid feedback exclusions')
            hard_excluded.update(exclusions)
        allowed_feedback = {s['root_id'] for s in sessions if s['kind'] == 'maintenance-feedback'} - hard_excluded
        observed = set()
        deferred = {}
        excluded = 0
        for session in sessions:
            root_excluded = session['root_id'] in excluded_roots
            feedback_allowed = session['kind'] == 'maintenance-feedback' and session['root_id'] in allowed_feedback
            if (collecting_current_source and session["root_id"] == current_root or root_excluded and not feedback_allowed or session["kind"] in EXCLUDED_KINDS
                    or session["source_repo"] not in target["source_repos"]
                    or session["information_scope"] not in {"public", identity["information_scope"]}):
                excluded += 1
                continue
            for unit in session["units"]:
                text_id(unit["id"])
                require(type(unit["revision"]) is int and unit["revision"] > 0, "invalid unit revision")
                key = digest([source, session["root_id"], unit["id"], unit["revision"]])
                observed.add(key)
                updated = instant(unit["updated_at"])
                require(unit["status"] in {"completed", "in-progress"}, "invalid unit status")
                if key in state["units"]:
                    require(unit["status"] == "completed", "completed unit changed; export a new revision")
                    require(state["units"][key]["facts"] == completed_facts(source, session, unit, updated),
                            "completed unit changed; export a new revision")
                    continue
                if updated > cutoff:
                    if key in previous.get("deferred", {}):
                        deferred[key] = previous["deferred"][key]
                    continue
                if unit["status"] == "in-progress":
                    deferred[key] = {"session_id": session["id"], "root_id": session["root_id"],
                                     "unit_id": unit["id"], "revision": unit["revision"]}
                    continue
                if updated < since and key not in previous.get("deferred", {}):
                    continue
                facts = completed_facts(source, session, unit, updated)
                if facts.get('maintenance_feedback') and not facts['evidence']['events']:
                    continue  # A finished run without feedback also resolves its pending observation.
                state["units"][key] = {"facts": facts,
                                       "status": "pending", "candidate_id": None}
        # A resumed current root is a temporary hold; do not consume its pending observations.
        deferred.update({k: value for k, value in previous.get('deferred', {}).items()
                         if collecting_current_source and value['root_id'] == current_root and value['root_id'] not in hard_excluded})
        required_deferred = {k for k, value in previous.get('deferred', {}).items()
                             if (not collecting_current_source or value['root_id'] != current_root) and
                             (value['root_id'] not in excluded_roots or value['root_id'] in allowed_feedback)}
        require(required_deferred <= observed, "export omitted an unfinished unit")
        grouped = {}
        current_held = 0
        for key, unit in state["units"].items():
            facts = unit["facts"]
            if facts['source_id'] == current_source and facts['root_id'] == current_root:
                current_held += unit['status'] not in TERMINAL
                continue
            origin = facts['source_id']
            if origin == source:
                origin_excluded, origin_hard = excluded_roots, hard_excluded
            else:
                saved_source = state['sources'].get(origin, {})
                origin_excluded = (set(saved_source.get('excluded_roots', [])) |
                                   set(state.get('maintenance_roots', {}).get(origin, [])))
                origin_hard = set(saved_source.get('feedback_excluded_roots', []))
            if (unit["status"] not in TERMINAL and facts["source_repo"] in target["source_repos"]
                    and facts["information_scope"] in {"public", identity["information_scope"]}
                    and (facts["root_id"] not in origin_excluded or
                         facts.get('maintenance_feedback') and facts['root_id'] not in origin_hard)):
                phase = (unit["status"], unit["candidate_id"]) if unit["status"] in {"evaluated", "applying"} else ("pending", None)
                grouped.setdefault((facts["source_id"], facts["root_id"], phase), []).append({"key": key, **unit})
        groups = []
        for (origin, root, _phase), units in grouped.items():
            units.sort(key=lambda u: (u["facts"]["updated_at"], u["key"]))
            groups.append({"id": digest([origin, root, sorted(u["key"] for u in units)]),
                           "source_id": origin, "root_id": root,
                           "units": [{"key": u["key"], "status": u["status"],
                                      "candidate_id": u["candidate_id"], **u["facts"]} for u in units],
                           "needs_reconciliation": any(u["status"] == "applying" for u in units)})
        groups.sort(key=lambda g: (g["units"][0]["updated_at"], g["id"]))
        reconciliation = [g for g in groups if g['needs_reconciliation']]
        held = [g for g in groups if getattr(args, 'new_evidence_only', False)
                and all(u['status'] in {'deferred', 'failed'} for u in g['units'])]
        held_ids = {g['id'] for g in held}
        pending = [g for g in groups if not g['needs_reconciliation'] and g['id'] not in held_ids]
        selected = reconciliation + pending[:max(0, target['budget']['max_cases'] - len(reconciliation))]
        unfinished = len(deferred) + sum(len(saved["deferred"]) for ident, saved in state["sources"].items() if ident != source)
        batch = {"version": 1, "id": uuid.uuid4().hex, "target": identity,
                 "window": {"since": stamp(since), "cutoff": stamp(cutoff)}, "budget": target["budget"],
                 "status": "ready" if selected else "budget-exhausted" if pending else
                           "awaiting-evidence" if held else
                           "awaiting-input" if unfinished or current_held else "no-new-input",
                 "cases": selected, "queued_cases": len(groups), "unfinished_units": unfinished,
                 "excluded_sessions": excluded}
        batch['source_collection'] = {
            'source_id': source,
            'status': 'acquired' if sessions or deferred else 'empty',
            'exported_sessions': len(sessions), 'unfinished_units': len(deferred),
            'coverage': {'start': stamp(since), 'end': stamp(cutoff), 'complete': True}}
        if current_held:
            batch['current_root_held_units'] = current_held
        if getattr(args, 'new_evidence_only', False):
            batch['held_cases'] = len(held)
            batch['held_case_ids'] = sorted(held_ids)
        selected_units = [u for case in selected for u in case["units"]]
        batch["evidence_quality"] = {"with_trace": len(selected_units),
                                     "outcomes_independently_verified": False}
        feedback_count = sum(bool(u.get("maintenance_feedback")) for u in selected_units)
        if feedback_count:
            batch["evidence_quality"]["maintenance_feedback_units"] = feedback_count
        batch_path = args.output / (batch["id"] + ".json")
        if 'coverage_notes' in document:
            batch['coverage_notes'] = document['coverage_notes']
        atomic_write(batch_path, batch)
        state.setdefault('batches', {})[batch['id']] = digest(batch)
        state['latest_batch'] = batch['id']
        state["sources"][source] = {"through": stamp(cutoff), "deferred": deferred,
                                   "excluded_roots": sorted(excluded_roots), 'adapter_selection': selection,
                                   'feedback_excluded_roots': sorted(hard_excluded)}
        atomic_write(args.state, state)
        return {"batch": str(batch_path), "status": batch["status"]}



def report(args):
    """Summarize independent acquisitions without collecting or changing their state."""
    require(args.repo.is_dir(), 'target repository directory is missing')
    private_path(args.state, args.repo)
    private_path(args.output, args.repo)
    protected = (args.state, args.target, args.acquisitions)
    output = args.output.resolve()
    require(not any(same_path(args.output, path) for path in protected) and
            not output.is_relative_to(args.state.with_name(args.state.name + '.lock').resolve()),
            'report output must not overwrite inputs or the state lock')
    expected = [text_id(source) for source in args.expected_source_id]
    require(len(expected) == len(set(expected)), 'duplicate expected source')
    identity = profile(read(args.target))
    manifest = read(args.acquisitions, limit=8 * 1024 * 1024)
    require(isinstance(manifest, dict) and set(manifest) == {'version', 'sources'}
            and manifest['version'] == 1 and isinstance(manifest['sources'], list)
            and manifest['sources'], 'invalid acquisition manifest')
    since, cutoff = instant(args.since), instant(args.cutoff)
    require(since < cutoff, 'empty or reversed window')
    sources, analyses, seen = [], [], set()
    with locked(args.state):
        state = load_state(args.state, identity)
        for entry in manifest['sources']:
            require(isinstance(entry, dict), 'invalid source outcome')
            source = text_id(entry['source_id'])
            require(source not in seen, 'duplicate source outcome')
            seen.add(source)
            kind = entry['kind']
            require(isinstance(kind, str) and re.fullmatch(r'[a-z][a-z0-9-]{0,39}', kind),
                    'invalid source kind')
            status = entry['status']
            row = {'source_id': source, 'kind': kind, 'coverage_complete': False}
            if status == 'collected':
                require(set(entry) == {'source_id', 'kind', 'status', 'batch'}, 'invalid collected outcome')
                batch_path = Path(entry['batch'])
                require(not same_path(args.output, batch_path), 'report output must not overwrite its batch')
                batch = read(batch_path)
                require(batch['target'] == identity and
                        state.get('batches', {}).get(batch['id']) == digest(batch),
                        'unverified collection batch')
                require(batch.get('evidence_basis') != 'self-report', 'self-report is not native collection')
                collection = batch.get('source_collection')
                require(isinstance(collection, dict) and collection.get('source_id') == source
                        and collection.get('status') in {'acquired', 'empty'},
                        'batch lacks this source acquisition result')
                coverage = collection['coverage']
                require(coverage['complete'] is True and instant(coverage['start']) <= since
                        and instant(coverage['end']) == cutoff
                        and instant(state['sources'][source]['through']) >= cutoff,
                        'source collection does not cover report window')
                require(collection['status'] != 'empty' or
                        collection['exported_sessions'] == collection['unfinished_units'] == 0,
                        'empty acquisition contains input or unfinished units')
                row.update(status=collection['status'], coverage_complete=True,
                           exported_sessions=collection['exported_sessions'],
                           unfinished_units=collection['unfinished_units'])
                analyses.append({'batch_id': batch['id'], 'status': batch['status'],
                                 'cases': len(batch['cases']),
                                 'case_sources': sorted({case['source_id'] for case in batch['cases']})})
            else:
                require(status in {'unsupported', 'failed'} and
                        {'source_id', 'kind', 'status', 'reason_code'} <= set(entry) <=
                        {'source_id', 'kind', 'status', 'reason_code', 'limitations'},
                        'invalid unavailable source outcome')
                codes = [entry['reason_code'], *entry.get('limitations', [])]
                require(isinstance(entry.get('limitations', []), list) and
                        all(isinstance(code, str) and re.fullmatch(r'[a-z][a-z0-9-]{0,63}', code)
                            for code in codes), 'invalid source limitation code')
                row.update(status=status, reason_code=entry['reason_code'])
                if 'limitations' in entry:
                    row['limitations'] = entry['limitations']
            sources.append(row)
        require(seen == set(expected), 'source outcomes do not match requested sources')
        complete = all(row['coverage_complete'] for row in sources)
        result = {'version': 1, 'target': identity,
                  'window': {'since': stamp(since), 'cutoff': stamp(cutoff)},
                  'status': 'complete' if complete else 'partial' if analyses else 'unavailable',
                  'coverage_complete': complete, 'sources': sources,
                  'analysis_batches': analyses, 'checkpoint_written': False}
        atomic_write(args.output, result)
    return {'report': str(args.output), 'status': result['status'],
            'coverage_complete': complete, 'checkpoint_written': False}


def record(args):
    private_path(args.state, args.repo)
    require(args.state.is_file(), "state does not exist")
    batch, result = read(args.batch), read(args.result)
    require(batch["version"] == 1, "unsupported batch version")
    selected = [case for case in batch["cases"] if case["id"] == result["case_id"]]
    require(len(selected) == 1, "case is not in batch")
    case = selected[0]
    status = result["status"]
    require(status in {"no-change", "deferred", "failed", "evaluated", "applying", "applied"}, "invalid decision status")
    require(isinstance(result["reason"], str) and result["reason"].strip(), "decision reason required")
    evidence = result.get("evidence", [])
    require(isinstance(evidence, list) and all(isinstance(e, str) and e.strip() for e in evidence), "invalid evidence references")
    candidate_id = result.get("candidate_id")
    if status in {"evaluated", "applying", "applied"}:
        require(isinstance(candidate_id, str) and re.fullmatch("[a-f0-9]{64}", candidate_id), "candidate digest required")
        require(evidence, "evaluation or application evidence required")
    decision_id = digest([batch["id"], result])
    with locked(args.state):
        state = load_state(args.state, batch["target"])
        require(state.get('batches', {}).get(batch['id']) == digest(batch), 'unknown or modified batch')
        if decision_id in state["decisions"]:
            return {"decision_id": decision_id, "status": "already-recorded"}
        require(state.get('latest_batch') == batch['id'], 'stale batch; collect a fresh batch')
        keys = [unit["key"] for unit in case["units"]]
        require(len(keys) == len(set(keys)) and keys, "invalid case units")
        ledger = state['retrospective_units'] if batch.get('evidence_basis') == 'self-report' else state['units']
        units = [ledger[key] for key in keys]
        require(all(snapshot == {'key': key, **unit['facts'], 'status': unit['status'],
                                 'candidate_id': unit['candidate_id']}
                    for key, unit, snapshot in zip(keys, units, case['units'])),
                'case changed since batch; collect a fresh batch')
        require(all(u["status"] not in TERMINAL for u in units), "case already closed; stale decision")
        if status == "applying":
            require(all(u["status"] == "evaluated" and u["candidate_id"] == candidate_id for u in units),
                    "application requires an evaluated candidate")
            operations = result.get("operations", [])
            require(isinstance(operations, list) and operations and
                    all(op in {"edit", "commit", "push", "pr", "merge", "install"} for op in operations),
                    "explicit invocation operations required; journal is not authorization")
            require(candidate_id not in state["claims"], "candidate already applying/applied; reconcile instead")
            state["claims"][candidate_id] = {"status": "applying", "unit_keys": sorted(keys), "operations": operations}
        elif status == "applied":
            claim = state["claims"].get(candidate_id, {})
            require(all(u["status"] == "applying" and u["candidate_id"] == candidate_id for u in units)
                    and claim.get("unit_keys") == sorted(keys), "application intent/reconciliation required")
            claim["status"] = "applied"
        elif any(u["status"] == "applying" for u in units):
            require(status == "failed" and result.get("reconciled") is True and evidence,
                    "in-flight application requires reconciliation; do not retry")
            # この分岐は「未反映」を確認した証拠がある場合だけ使う。
            for u in units:
                state["claims"].pop(u["candidate_id"], None)
        for unit in units:
            unit["status"] = status
            unit["candidate_id"] = candidate_id if status in {"evaluated", "applying", "applied"} else None
        state["decisions"][decision_id] = {"batch_id": batch["id"], "unit_keys": keys, **result}
        atomic_write(args.state, state)
        return {"decision_id": decision_id, "status": status}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    register_parser = commands.add_parser("register-run")
    for name in ('target', 'repo', 'state'):
        register_parser.add_argument('--' + name, type=Path, required=True)
    for name in ('source-id', 'root-id'):
        register_parser.add_argument('--' + name, required=True)
    collect_parser = commands.add_parser("collect")
    for name in ("input", "target", "repo", "state", "output"):
        collect_parser.add_argument("--" + name, type=Path, required=True)
    collect_parser.add_argument("--cutoff")
    collect_parser.add_argument("--since")
    collect_parser.add_argument("--hours", type=int, default=24)
    collect_parser.add_argument("--new-evidence-only", action="store_true",
                                help="hold unchanged deferred/failed cases; keep unrecorded work and reconciliation")
    collect_parser.add_argument("--exclude-root", action="append", default=[])
    intake_parser = commands.add_parser("intake-retrospectives")
    for name in ("input", "target", "repo", "state", "output"):
        intake_parser.add_argument("--" + name, type=Path, required=True)
    intake_parser.add_argument("--max-reports", type=int, choices=(1, 2), default=2)
    intake_parser.add_argument("--exclude-root", action="append", default=[])
    intake_parser.add_argument("--new-evidence-only", action="store_true")
    select_parser = commands.add_parser("select-retrospectives")
    for name in ("input", "target", "repo", "state"):
        select_parser.add_argument("--" + name, type=Path, required=True)
    select_parser.add_argument("--max-reports", type=int, choices=(1, 2), default=2)
    select_parser.add_argument("--exclude-root", action="append", default=[])
    report_parser = commands.add_parser("report")
    for name in ('acquisitions', 'target', 'repo', 'state', 'output'):
        report_parser.add_argument('--' + name, type=Path, required=True)
    for name in ('since', 'cutoff'):
        report_parser.add_argument('--' + name, required=True)
    report_parser.add_argument('--expected-source-id', action='append', required=True)
    record_parser = commands.add_parser("record")
    for name in ("batch", "result", "state", "repo"):
        record_parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command in {'intake-retrospectives', 'select-retrospectives'}:
            from work_retrospectives import intake, select
            result = intake(args) if args.command == 'intake-retrospectives' else select(args)
        else:
            result = {'collect': collect, 'record': record, 'register-run': register_run, 'report': report}[args.command](args)
        print(json.dumps(result))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
