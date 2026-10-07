"""Render a sanitized daily report JSON with a fixed, offline presentation."""

import html
import argparse
from datetime import date, datetime
import math
import hashlib
import json
import os
from pathlib import Path
import re
from string import Template
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

RESULTS = {'passed': '成功', 'failed': '失敗', 'partial': '一部確認', 'unverified': '未確認'}
OUTCOMES = {'draft': 'draft PR', 'adopted': '採用済み', 'proposed': '提案', 'no_change': '変更なし', 'failed': '失敗'}
SESSION_STATES = {'read': '取得済み', 'partial': '部分取得', 'failed': '取得失敗', 'uncollected': '未回収', 'in_progress': '進行中', 'held': '保留', 'outside_period': '期間外', 'excluded': '除外'}


def validate_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment or any(character.isspace() or ord(character) < 32 or ord(character) == 127 or character in '\\<>"' for character in url):
        raise ValueError('pr_url must be an absolute HTTP(S) URL without credentials, query, fragment, or unsafe characters')
    parsed.port


def object_fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ValueError('report object has missing or unknown fields')


def strings(value, keys):
    if any(not isinstance(value[key], str) for key in keys if key in value):
        raise ValueError('report text fields must be strings')


def seconds(value):
    if value is not None and (type(value) not in {int, float} or (isinstance(value, float) and not math.isfinite(value)) or value < 0):
        raise ValueError('seconds must be null or a finite nonnegative number')


def validate_report(report):
    specs = {
        'outcomes': ({'title', 'change', 'status'}, {'pr_url'}, {'status': OUTCOMES}),
        'reflections': ({'title', 'happened', 'next', 'result', 'evidence'}, {'change'}, {'result': RESULTS}),
        'checks': ({'title', 'result', 'detail'}, set(), {'result': RESULTS}),
        'remaining': ({'title', 'detail'}, set(), {}),
        'sessions': ({'title', 'source', 'evidence', 'status', 'detail'}, set(), {'evidence': {'history', 'self_report'}, 'status': SESSION_STATES}),
    }
    object_fields(report, {'version', 'date', 'timezone'}, {'summary', 'period', 'timing', *specs})
    if type(report['version']) is not int or report['version'] != 1:
        raise ValueError('unsupported report version')
    strings(report, {'date', 'timezone', 'summary', 'period'})
    if date.fromisoformat(report['date']).isoformat() != report['date']:
        raise ValueError('date must be YYYY-MM-DD')
    try:
        ZoneInfo(report['timezone'])
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError('timezone must be an IANA timezone') from error
    for name, (required, optional, enums) in specs.items():
        items = report.get(name, [])
        if not isinstance(items, list):
            raise ValueError(f'{name} must be a list')
        for item in items:
            object_fields(item, required, optional)
            strings(item, required | optional)
            for key, values in enums.items():
                if item[key] not in values:
                    raise ValueError(f'unknown {name}.{key}')
            if name == 'outcomes' and 'pr_url' in item:
                validate_url(item['pr_url'])
    timing = report.get('timing', {})
    object_fields(timing, set(), {'start', 'end', 'wall_seconds', 'scope', 'stages'})
    strings(timing, {'scope'})
    seconds(timing.get('wall_seconds'))
    for key in ('start', 'end'):
        if timing.get(key) is not None:
            strings(timing, {key})
            if datetime.fromisoformat(timing[key].replace('Z', '+00:00')).tzinfo is None:
                raise ValueError('timestamps need timezone')
    stages = timing.get('stages', [])
    if not isinstance(stages, list):
        raise ValueError('timing.stages must be a list')
    for stage in stages:
        object_fields(stage, {'title', 'seconds', 'detail'})
        strings(stage, {'title', 'detail'})
        seconds(stage['seconds'])


def text(value):
    return html.escape(str(value), quote=True)


def markdown_text(value):
    return re.sub(r'([\\`*_{}\[\]()#+.!|>-])', r'\\\1', html.escape(str(value), quote=False))


def badge(label, state):
    return f'<span class="badge {state}">{text(label)}</span>'


def fields(pairs):
    return '<dl>' + ''.join(f'<dt>{text(label)}</dt><dd>{text(value)}</dd>' for label, value in pairs) + '</dl>'


def card(title, body, status='', state=''):
    return f'<article class="card"><div class="card-heading"><h3>{text(title)}</h3>{badge(status, state) if status else ""}</div>{body}</article>'


def section(identifier, title, cards, empty, controls=''):
    content = '<div class="cards">' + ''.join(cards) + '</div>' if cards else f'<p class="empty">{text(empty)}</p>'
    return f'<section aria-labelledby="{identifier}"><div class="section-heading"><h2 id="{identifier}">{title}</h2>{controls}</div>{content}</section>'


def render_report(report):
    validate_report(report)
    outcomes = report.get('outcomes', [])
    reflections = report.get('reflections', [])
    checks = report.get('checks', [])
    remaining = report.get('remaining', [])
    sessions = report.get('sessions', [])
    timing = report.get('timing', {})
    date, zone = report['date'], report['timezone']
    summary = report.get('summary', '取得・振り返りの結果')
    period = report.get('period', '記録なし')
    sections = []
    md = [f'# {markdown_text(date)} スキル振り返り', '', f'日付基準：{markdown_text(zone)}', '', f'対象期間：{markdown_text(period)}', '', markdown_text(summary), '']

    outcome_cards = []
    md += ['## 今日の成果', '']
    for item in outcomes:
        body = f'<p>{text(item["change"])}</p>'
        if item.get('pr_url'):
            body += f'<a class="pr-link" href="{text(item["pr_url"])}" target="_blank" rel="noopener noreferrer">PRを開く ↗</a>'
        outcome_cards.append(card(item['title'], body, OUTCOMES[item['status']], item['status']))
        md += [f'### {markdown_text(item["title"])}', '', f'状態：{OUTCOMES[item["status"]]}', '', markdown_text(item['change']), '']
        if item.get('pr_url'):
            md += [f'[PRを開く](<{item["pr_url"]}>)', '']
    if not outcomes:
        md += ['成果はありません。', '']
    sections.append(section('outcomes', '今日の成果', outcome_cards, '成果はありません。'))

    reflection_cards = []
    md += ['## 反省点と次の対応', '']
    for item in reflections:
        result = item['result']
        body = fields([('何が起きた', item['happened']), ('次にどうする', item['next']), ('変更・対応', item.get('change') or '変更は未実施'), ('検証・根拠', item['evidence'])])
        reflection_cards.append(f'<div class="reflection" data-result="{result}">' + card(item['title'], body, RESULTS[result], result) + '</div>')
        md += [f'### {markdown_text(item["title"])}', '']
        for label, value in [('何が起きた', item['happened']), ('次にどうする', item['next']), ('変更・対応', item.get('change') or '変更は未実施'), ('検証', RESULTS[result]), ('根拠', item['evidence'])]:
            md += [f'**{label}**：{markdown_text(value)}', '']
    if not reflections:
        md += ['反省点はありません。未分析・取得失敗は検証結果と残件に記載します。', '']
    controls = '<label class="filter">検証で絞り込む<select id="result-filter"><option value="all">すべて</option>' + ''.join(f'<option value="{value}">{label}</option>' for value, label in RESULTS.items()) + '</select></label>' if reflections else ''
    sections.append(section('reflections', '反省点と次の対応', reflection_cards, '反省点はありません。未分析・取得失敗は検証結果と残件を参照してください。', controls) + ('<p id="filter-count" class="muted" role="status" aria-live="polite"></p>' if reflections else ''))

    md += ['## 検証結果', '']
    check_cards = []
    for item in checks:
        check_cards.append(card(item['title'], f'<p>{text(item["detail"])}</p>', RESULTS[item['result']], item['result']))
        md += [f'### {markdown_text(item["title"])} — {RESULTS[item["result"]]}', '', markdown_text(item['detail']), '']
    if not checks:
        md += ['検証結果はありません。', '']
    sections.append(section('checks', '検証結果', check_cards, '検証結果はありません。'))

    md += ['## 残件・判断待ち', '']
    sections.append(section('remaining', '残件・判断待ち', [card(item['title'], f'<p>{text(item["detail"])}</p>') for item in remaining], '記録された残件はありません。'))
    for item in remaining:
        md += [f'### {markdown_text(item["title"])}', '', markdown_text(item['detail']), '']
    if not remaining:
        md += ['記録された残件はありません。', '']

    md += ['## 対象一覧', '']
    session_cards = []
    for item in sessions:
        evidence = '履歴の観測' if item['evidence'] == 'history' else '自己申告'
        session_cards.append(card(item['title'], f'<p class="muted">{text(item["source"])} · {evidence}</p><p>{text(item["detail"])}</p>', SESSION_STATES[item['status']], item['status']))
        md += [f'### {markdown_text(item["title"])}', '', f'{markdown_text(item["source"])}・{evidence}・{SESSION_STATES[item["status"]]}', '', markdown_text(item['detail']), '']
    if not sessions:
        md += ['記録された対象はありません。取得失敗とは区別してください。', '']
    sections.append(section('sessions', '対象一覧', session_cards, '記録された対象はありません。取得失敗とは区別してください。'))

    wall = f'{timing["wall_seconds"]}秒' if timing.get('wall_seconds') is not None else '未計測'
    time_pairs = [('開始', timing.get('start') or '未計測'), ('終了', timing.get('end') or '未計測'), ('全体wall time', wall), ('計測範囲・再利用条件', timing.get('scope') or '記録なし')]
    time_cards = [card('処理全体', fields(time_pairs))]
    md += ['## 時間', '']
    for label, value in time_pairs:
        md += [f'**{label}**：{markdown_text(value)}', '']
    for stage in timing.get('stages', []):
        duration = f'{stage["seconds"]}秒' if stage['seconds'] is not None else '未計測'
        time_cards.append(card(stage['title'], f'<p>{duration}</p><p>{text(stage["detail"])}</p>'))
        md += [f'### {markdown_text(stage["title"])} — {duration}', '', markdown_text(stage['detail']), '']
    sections.append(section('timing', '時間', time_cards, '時間は未計測です。'))

    metrics = ''.join(f'<div><span>{label}</span><strong>{value}</strong></div>' for label, value in [('成果', len(outcomes)), ('反省点', len(reflections)), ('残件', len(remaining)), ('実測', wall)])
    template = Template((Path(__file__).resolve().parents[1] / 'assets/report.html').read_text(encoding='utf-8'))
    document = template.substitute(date=text(date), timezone=text(zone), period=text(period), summary=text(summary), metrics=metrics, sections=''.join(sections))
    if len(document.encode('utf-8')) > 256 * 1024:
        raise ValueError('HTML exceeds the Page visualization limit of 256 KiB; preserve JSON and shorten the overview')
    return {'html': document, 'markdown': '\n'.join(md)}


def main():
    from session_reader import private_directory

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='sanitized report JSON, never source logs or state')
    parser.add_argument('--repo', type=Path, required=True, help='improvement repository, not an output destination')
    parser.add_argument('--output', type=Path, required=True, help='new private directory outside Git')
    args = parser.parse_args()
    try:
        source = args.input.read_bytes()
        result = render_report(json.loads(source))
        private_directory(args.output, args.repo)
        paths = {}
        for kind, name in [('html', 'report.html'), ('markdown', 'report.md')]:
            path = args.output / name
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                stream.write(result[kind])
            paths[kind] = str(path)
        print(json.dumps({**paths, 'json_sha256': hashlib.sha256(source).hexdigest(), 'html_bytes': len(result['html'].encode('utf-8'))}))
        return 0
    except (OSError, ValueError) as error:
        parser.exit(1, f'render failed: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
