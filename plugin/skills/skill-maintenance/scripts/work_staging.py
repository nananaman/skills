"""Persist one response at a time, then preflight independent v2 task envelopes."""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time

from common import require, text_id
from maintenance import atomic_write, same_path
from daily_report import outside_repo
from work_retrospectives import fields, read_envelope, validate


def partition(document):
    """Never repair identities or weaken the canonical intake validator."""
    fields(document, 'version source_id requested_tasks reports enumeration_complete selection_basis')
    header = dict(document, requested_tasks=[], reports=[])
    validate(header)
    require(document['version'] == 2, 'staging requires turn-bound v2 input')
    require(isinstance(document['requested_tasks'], list) and isinstance(document['reports'], list),
            'retrospective lists required')
    tasks, reports, held = defaultdict(list), defaultdict(list), []
    for kind, rows, groups in (('request', document['requested_tasks'], tasks),
                               ('report', document['reports'], reports)):
        for position, row in enumerate(rows):
            if not isinstance(row, dict) or not isinstance(row.get('task_id'), str) or not row['task_id'].strip():
                held.append(dict(kind=kind, position=position, reason='missing task identity'))
            else:
                groups[row['task_id']].append(row)
    envelopes = []
    for task_id in sorted(tasks.keys() | reports.keys()):
        requests, bodies = tasks[task_id], reports[task_id]
        if len(requests) != 1 or len(bodies) > 1:
            held.append(dict(task_id=task_id, reason='ambiguous or missing request/report binding'))
            continue
        envelope = dict(header, requested_tasks=requests, reports=bodies, enumeration_complete=False)
        try:
            validate(envelope)
        except (ValueError, KeyError, TypeError, OverflowError):
            held.append(dict(task_id=task_id, reason='canonical task validation failed; original retained'))
        else:
            envelopes.append(envelope)
    return envelopes, held


def stage(args):
    started = datetime.now(timezone.utc).isoformat()
    clock = time.monotonic()
    require(args.repo.is_dir(), 'target repository directory is missing')
    for path in (args.input, args.output):
        outside_repo(path, args.repo)
    require(not same_path(args.input, args.output), 'response and journal overlap')
    text_id(args.response_id)
    fd = os.open(args.input, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'response must be a regular file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(8 * 1024 * 1024 + 1)
        require(len(raw) <= 8 * 1024 * 1024, 'response exceeds 8 MiB; retain and partition upstream')
    finally:
        os.close(fd)
    sha = hashlib.sha256(raw).hexdigest()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    event = args.output / hashlib.sha256(args.response_id.encode()).hexdigest()
    outside_repo(event, args.repo)
    if not event.exists():
        temporary = Path(tempfile.mkdtemp(dir=args.output, prefix='.staging-'))
        try:
            raw_path = temporary / 'response.json'
            with raw_path.open('xb') as stream:
                os.chmod(raw_path, 0o600)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            # Publish the complete raw response before attempting any parsing.
            os.rename(temporary, event)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    saved_raw = event / 'response.json'
    outside_repo(saved_raw, args.repo)
    require(saved_raw.read_bytes() == raw, 'response ID reused with different bytes; original retained')
    receipt_path = event / 'receipt.json'
    if receipt_path.exists():
        receipt = read_envelope(receipt_path)
        require(receipt['sha256'] == sha, 'staged response digest mismatch')
        for item in receipt['prepared']:
            path = event / item['name']
            outside_repo(path, args.repo)
            require(hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'], 'staged envelope changed')
        return dict(receipt=str(receipt_path), status=receipt['status'], reused=True, state_written=False)
    try:
        envelopes, held = partition(read_envelope(saved_raw))
    except (ValueError, KeyError, TypeError, UnicodeError, OverflowError):
        envelopes, held = [], [dict(reason='response validation failed; original retained')]
    prepared = []
    for number, envelope in enumerate(envelopes, 1):
        path = event / f'envelope-{number:04d}.json'
        outside_repo(path, args.repo)
        if path.exists():
            require(read_envelope(path) == envelope, 'staged envelope conflicts with saved response')
        else:
            atomic_write(path, envelope)
        prepared.append(dict(name=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    receipt = dict(version=1, response_id=args.response_id, sha256=sha, bytes=len(raw), raw_path=str(saved_raw),
                   envelopes=[str(event / item['name']) for item in prepared], prepared=prepared, held=held,
                   status='partial' if held and prepared else 'held' if held else 'staged', state_written=False,
                   started_at=started, finished_at=datetime.now(timezone.utc).isoformat(),
                   elapsed_seconds=time.monotonic() - clock, communication_bytes=None)
    atomic_write(receipt_path, receipt)
    return dict(receipt=str(receipt_path), status=receipt['status'], reused=False, state_written=False)
