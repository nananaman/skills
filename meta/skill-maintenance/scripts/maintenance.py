#!/usr/bin/env python3
"""Collect normalized, private exports and journal maintenance decisions. Python 3.11+."""

import argparse
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta, timezone
from common import require, instant, stamp, text_id, validate_content, validate_evidence
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


def completed_facts(source, session, unit, updated):
    content = unit["content"]
    validate_content(content)
    evidence = {}
    if "evidence" in unit:
        validate_evidence(unit["evidence"])
        evidence["evidence"] = unit["evidence"]
    return {"source_id": source, "root_id": session["root_id"], "id": unit["id"],
            "source_repo": session["source_repo"], "information_scope": session["information_scope"],
            "revision": unit["revision"], "updated_at": stamp(updated), "content": content, **evidence}


def check_selection(state, source, selection):
    require(selection is None or isinstance(selection, dict) and
            selection.get('mode') in {'repo-index', 'thread-ids', 'app-index'}, 'invalid adapter selection')
    for ident, saved in state['sources'].items():
        boundary = saved.get('adapter_selection')
        if boundary and boundary.get('mode') == 'thread-ids':
            require(ident == source and boundary == selection, 'dedicated ID-scoped state selection changed')
    previous = state['sources'].get(source)
    if previous:
        require(previous.get('adapter_selection') == selection,
                'input selection changed or legacy checkpoint; use a dedicated state')


def collect(args, _locked=False):
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
    with nullcontext() if _locked else locked(args.state):
        state = load_state(args.state, identity)
        previous = state["sources"].get(source, {})
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
        if selection and selection['mode'] == 'thread-ids':
            ids = selection.get('thread_ids')
            require(isinstance(ids, list) and ids and all(isinstance(x, str) and x for x in ids),
                    'invalid adapter selection IDs')
            require(len(ids)==len(set(ids)) and set(ids)=={s['id'] for s in sessions},
                    'incomplete or unselected thread ID coverage')
        indexed = {text_id(s["id"]): s for s in sessions}
        require(len(indexed) == len(sessions), "duplicate session ID")
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
            require(session["kind"] in {"work", *EXCLUDED_KINDS}, "unknown session kind")
        excluded_roots = {s["id"] for s in sessions if s["id"] == s["root_id"] and s["kind"] in EXCLUDED_KINDS}
        for exclusions in (document.get('excluded_roots', []), previous.get('excluded_roots', []), args.exclude_root):
            require(isinstance(exclusions, list) and all(isinstance(x, str) and x for x in exclusions),
                    'invalid persistent exclusions')
            excluded_roots.update(exclusions)
        observed = set()
        deferred = {}
        excluded = 0
        for session in sessions:
            if (session["root_id"] in excluded_roots or session["kind"] in EXCLUDED_KINDS
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
                require(unit["status"] in {"completed", "in-progress", "cancelled"}, "invalid unit status")
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
                if unit["status"] == "cancelled":
                    continue
                state["units"][key] = {"facts": completed_facts(source, session, unit, updated),
                                       "status": "pending", "candidate_id": None}
        required_deferred = {k for k, value in previous.get('deferred', {}).items()
                             if value['root_id'] not in excluded_roots}
        require(required_deferred <= observed, "export omitted an unfinished unit")
        grouped = {}
        for key, unit in state["units"].items():
            facts = unit["facts"]
            if (unit["status"] not in TERMINAL and facts["source_repo"] in target["source_repos"]
                    and facts["information_scope"] in {"public", identity["information_scope"]}
                    and facts["root_id"] not in excluded_roots):
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
        pending = [g for g in groups if not g['needs_reconciliation']]
        selected = reconciliation + pending[:max(0, target['budget']['max_cases'] - len(reconciliation))]
        unfinished = len(deferred) + sum(len(saved["deferred"]) for ident, saved in state["sources"].items() if ident != source)
        batch = {"version": 1, "id": uuid.uuid4().hex, "target": identity,
                 "window": {"since": stamp(since), "cutoff": stamp(cutoff)}, "budget": target["budget"],
                 "status": "ready" if selected else "budget-exhausted" if groups else
                           "awaiting-input" if unfinished else "no-new-input",
                 "cases": selected, "queued_cases": len(groups), "unfinished_units": unfinished,
                 "excluded_sessions": excluded}
        selected_units = [u for case in selected for u in case["units"]]
        batch["evidence_quality"] = {"with_trace": sum("evidence" in u for u in selected_units),
                                     "report_only": sum("evidence" not in u for u in selected_units),
                                     "outcomes_independently_verified": False}
        batch_path = args.output / (batch["id"] + ".json")
        if 'coverage_notes' in document:
            batch['coverage_notes'] = document['coverage_notes']
        atomic_write(batch_path, batch)
        state.setdefault('batches', {})[batch['id']] = digest(batch)
        state['latest_batch'] = batch['id']
        state["sources"][source] = {"through": stamp(cutoff), "deferred": deferred,
                                   "excluded_roots": sorted(excluded_roots), 'adapter_selection': selection}
        atomic_write(args.state, state)
        return {"batch": str(batch_path), "status": batch["status"]}


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
        units = [state["units"][key] for key in keys]
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


def import_app(args):
    """Import a minimized app capture, preserving collection/decision idempotency."""
    import codex_app
    private_path(args.state, args.repo)
    private_path(args.output, args.repo)
    private_path(args.snapshot, args.repo)
    with locked(args.state):
        target, config = read(args.target), read(args.source)
        state = load_state(args.state, profile(target))
        boundary = codex_app.selection(config)
        check_selection(state, config['source_id'], boundary)
        previous = state['sources'].get(config['source_id'], {})
        cutoff = instant(args.cutoff)
        since = instant(args.since)
        if previous:
            require(instant(previous['through']) <= cutoff, 'cutoff precedes checkpoint')
            require(instant(previous['through']) >= since,
                    'checkpoint gap precedes authorized start; authorize a wider --since')
            since = min(since, instant(previous['through']))
        config['exclude_roots'] = sorted(set(config['exclude_roots']) |
                                        set(args.exclude_root) | {args.current_root})
        snapshot = read(args.snapshot, limit=8 * 1024 * 1024)
        document = codex_app.export(snapshot, config, target, stamp(since), stamp(cutoff),
                                    previous, state['units'])
        args.input = args.output / ('app-export-' + uuid.uuid4().hex + '.json')
        require(len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode()) <= 8 * 1024 * 1024,
                'generated app export exceeds 8 MiB')
        atomic_write(args.input, document, indent=None)
        args.cutoff, args.since, args.hours = stamp(cutoff), stamp(since), 24
        args.exclude_root = document['excluded_roots']
        return {**collect(args, _locked=True), 'export': str(args.input), 'source': 'codex-app-capture',
                'coverage_notes': document['coverage_notes']}


def capture_app(args):
    """Minimize a transient native bundle; this command does not call app tools."""
    import codex_app
    private_path(args.bundle, args.repo)
    private_path(args.output, args.repo)
    config = read(args.source)
    codex_app.selection(config)
    result = codex_app.minimize_native(read(args.bundle, limit=8 * 1024 * 1024), config,
                                      args.since, args.cutoff)
    atomic_write(args.output, result)
    return {'snapshot': str(args.output), 'source': 'saved-native-tool-results',
            'live_acquisition': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collect_parser = commands.add_parser("collect")
    for name in ("input", "target", "repo", "state", "output"):
        collect_parser.add_argument("--" + name, type=Path, required=True)
    collect_parser.add_argument("--cutoff")
    collect_parser.add_argument("--since")
    collect_parser.add_argument("--hours", type=int, default=24)
    collect_parser.add_argument("--exclude-root", action="append", default=[])
    app_parser = commands.add_parser('import-app', help='import a private app-tool capture; no live RPC')
    for name in ('snapshot', 'source', 'target', 'repo', 'state', 'output'):
        app_parser.add_argument('--' + name, type=Path, required=True)
    app_parser.add_argument('--current-root', required=True)
    app_parser.add_argument('--since', required=True)
    app_parser.add_argument('--cutoff', required=True)
    app_parser.add_argument('--exclude-root', action='append', default=[])
    capture_parser = commands.add_parser('capture-app', help='minimize saved native tool results; no live calls')
    for name in ('bundle', 'source', 'repo', 'output'):
        capture_parser.add_argument('--' + name, type=Path, required=True)
    capture_parser.add_argument('--since', required=True)
    capture_parser.add_argument('--cutoff', required=True)
    record_parser = commands.add_parser("record")
    for name in ("batch", "result", "state", "repo"):
        record_parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        result = {'collect': collect, 'record': record,
                  'import-app': import_app, 'capture-app': capture_app}[args.command](args)
        print(json.dumps(result))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
