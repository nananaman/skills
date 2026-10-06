"""Render an explicitly sanitized user-facing summary; no trace reads or delivery."""
from datetime import date
import hashlib
import html
import json
import os
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from common import SENSITIVE, require, text_id
from maintenance import private_path, same_path
from work_retrospectives import fields, read_envelope, safe_strings

PRIVATE = re.compile(r'(?:https?://|(?<!\w)/\S+|~[/\\]|[A-Za-z]:[/\\]|'
                     r'\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b|'
                     r'\b[0-9a-fA-F]{40,64}\b)')
PR = re.compile(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/[1-9][0-9]*')
SESSION_STATUS = dict(acquired='取得済み', empty='検証済み対象なし', excluded='除外',
                      failed='取得失敗', held='持越し', unsupported='未対応', **{'self-report': '自己申告回収'})
DECISIONS = dict(adopted='採用', rejected='見送り', held='保留', **{'no-change': '変更不要'})


def text(value):
    require(isinstance(value, str) and value.strip() and len(value) <= 16000,
            'nonempty bounded report text required')
    require(all(ord(char) >= 32 and ord(char) != 127 for char in value), 'report control characters blocked')
    require(not SENSITIVE.search(value) and not PRIVATE.search(value), 'private report content blocked')
    return re.sub(r'([\\`*_{}\[\]()#+.!|>-])', r'\\\1', html.escape(value, quote=False))


def render(document):
    fields(document, 'version report_date timezone information_scope period summary sessions candidates next_actions')
    require(type(document['version']) is int and document['version'] == 1, 'unsupported daily report version')
    day, zone = text(document['report_date']), text(document['timezone'])
    try:
        require(date.fromisoformat(document['report_date']).isoformat() == document['report_date'], 'invalid report date')
        ZoneInfo(document['timezone'])
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError('invalid daily report date/timezone') from None
    lines = [f'# スキル振り返り {day}', '', f'日付基準: {zone}', '',
             '対象期間: ' + text(document['period']), '', text(document['summary']), '', '## 対象の実務', '']
    require(isinstance(document['sessions'], list), 'report sessions must be a list')
    for session in document['sessions']:
        fields(session, 'label work source evidence_basis status reason next_action')
        require(isinstance(session['status'], str) and session['status'] in SESSION_STATUS, 'invalid report session status')
        lines += ['### ' + text(session['label']), '', text(session['work']), '',
                  f"入力元: {text(session['source'])} / 根拠: {text(session['evidence_basis'])} / 状態: {SESSION_STATUS[session['status']]}", '',
                  '結果・理由: ' + text(session['reason']), '', '次の対応: ' + text(session['next_action']), '']
    if not document['sessions']:
        lines += ['対象実務の詳細は未取得です。対象なしを証明するものではありません。', '']
    lines += ['## 改善候補と検証', '']
    require(isinstance(document['candidates'], list), 'report candidates must be a list')
    for candidate in document['candidates']:
        fields(candidate, 'name basis checks decision reason pr_urls next_action')
        require(isinstance(candidate['decision'], str) and candidate['decision'] in DECISIONS, 'invalid report candidate decision')
        lines += ['### ' + text(candidate['name']), '', '根拠: ' + text(candidate['basis']), '']
        require(isinstance(candidate['checks'], list), 'candidate checks must be a list')
        for check in candidate['checks']:
            fields(check, 'method result limitation')
            lines += [f"- 方法: {text(check['method'])}。結果: {text(check['result'])}。確認の限界: {text(check['limitation'])}"]
        if not candidate['checks']:
            lines += ['検証未実施。']
        lines += ['', f"判断: {DECISIONS[candidate['decision']]}。{text(candidate['reason'])}", '']
        urls = candidate['pr_urls']
        require(isinstance(urls, list) and all(isinstance(url, str) and PR.fullmatch(url) for url in urls), 'invalid report PR URL')
        lines += ['PR: ' + (', '.join(f'[PR]({url})' for url in urls) if urls else 'なし'), '',
                  '次の対応: ' + text(candidate['next_action']), '']
    if not document['candidates']:
        lines += ['抽出済みの改善候補はありません。未取得・未検証の実務まで変更不要と判断したものではありません。', '']
    require(isinstance(document['next_actions'], list), 'next actions must be a list')
    lines += ['## 次の対応', ''] + ['- ' + text(action) for action in document['next_actions']]
    return '\n'.join(lines) + '\n'


def outside_repo(path, repo):
    private_path(path, repo)
    require(not any(same_path(parent, repo) for parent in (path, *path.parents)),
            'daily report input/output must be outside target repository')


def split_parts(content):
    """Preserve every UTF-8 line in ordered parts, including large check lists."""
    limit = 8 * 1024 * 1024
    pieces, current = [], bytearray()
    for line in content.splitlines(keepends=True):
        require(len(line) <= limit, 'single report line exceeds part capacity; retain input and revise partition')
        if current and len(current) + len(line) > limit:
            pieces.append(bytes(current))
            current.clear()
        current.extend(line)
    if current:
        pieces.append(bytes(current))
    return pieces


def daily_report(args):
    require(args.repo.is_dir(), 'target repository directory is missing')
    for path in (args.input, args.config, args.output):
        outside_repo(path, args.repo)
    settings = read_envelope(args.config)
    fields(settings, 'version report_timezone information_scope report_destination')
    safe_strings(settings)
    require(type(settings['version']) is int and settings['version'] == 1, 'unsupported report configuration version')
    scope = text_id(settings['information_scope'])
    kind, separator, owner = scope.partition(':')
    require(separator and kind in {'personal', 'organization'} and owner.strip() == owner and owner,
            'invalid report scope')
    destination = settings['report_destination']
    fields(destination, 'kind reference information_scope')
    require(destination['kind'] in {'host-space', 'local'}, 'unsupported report destination kind')
    text_id(destination['reference'])
    require(destination['information_scope'] == scope, 'report destination scope mismatch')
    document = read_envelope(args.input)
    require(document.get('information_scope') == scope, 'report input scope differs from caller configuration')
    require(document.get('timezone') == settings['report_timezone'], 'report timezone differs from caller configuration')
    content = render(document).encode('utf-8')
    pieces = split_parts(content)
    outputs = [args.output] if len(pieces) == 1 else [
        args.output.with_name(f'{args.output.stem}-part-{number:03d}{args.output.suffix}')
        for number in range(1, len(pieces) + 1)]
    handoff_path = args.output.with_name(args.output.name + '.handoff.json')
    for path in [args.output, *outputs, handoff_path]:
        outside_repo(path, args.repo)
        require(not any(same_path(path, protected) for protected in (args.input, args.config)),
                'daily report must not overwrite protected inputs')
        require(not path.exists(), 'daily report output already exists; use a new revision path')
    parts = [dict(order=n, path=str(path), sha256=hashlib.sha256(piece).hexdigest())
             for n, (path, piece) in enumerate(zip(outputs, pieces), 1)]
    handoff = dict(version=1, report_date=document['report_date'], timezone=document['timezone'],
                   information_scope=scope, destination=destination, parts=parts, remaining_parts=0,
                   delivery_status='host-handoff-pending', reason='host-delivery-and-readback-unverified')
    manifest = (json.dumps(handoff, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    created = []
    try:
        for path, data in [*zip(outputs, pieces), (handoff_path, manifest)]:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            created.append(path)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
    except OSError:
        for path in created:
            path.unlink()
        raise
    return dict(report=str(outputs[0]), parts=parts, sha256=hashlib.sha256(content).hexdigest(),
                handoff=str(handoff_path), delivery_status='host-handoff-pending', checkpoint_written=False)
