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
DECISIONS = {'adopted': '採用', 'rejected': '見送り', 'held': '保留', 'no_change': '変更不要', 'proposed': '提案'}


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
        'reflections': ({'title', 'happened', 'next', 'result', 'evidence'}, {'change', 'decision', 'overview'}, {'result': RESULTS, 'decision': DECISIONS}),
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
            strings(item, (required | optional) - {'overview'})
            for key, values in enums.items():
                if key in item and item[key] not in values:
                    raise ValueError(f'unknown {name}.{key}')
            if name == 'reflections' and 'overview' in item:
                overview_keys = {'title', 'change', 'evaluation', 'reason'}
                object_fields(item['overview'], overview_keys)
                strings(item['overview'], overview_keys)
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


def table(headers, rows, css_class=''):
    """Rows contain only escaped text or markup assembled by this renderer."""
    head = ''.join(f'<th scope="col">{text(label)}</th>' for label in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{cell}</td>' for cell in row) + '</tr>' for row in rows)
    return f'<div class="table-scroll" tabindex="0" role="region" aria-label="{text(headers[0])}の表"><table class="{css_class}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def section(identifier, title, content, empty):
    return f'<section aria-labelledby="{identifier}"><h2 id="{identifier}">{text(title)}</h2>{content or f"<p>{text(empty)}</p>"}</section>'


def duration(value):
    if value is None:
        return '未計測'
    minutes, whole_seconds = divmod(math.floor(value), 60)
    return f'{minutes}分{whole_seconds}秒'


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

    outcome_rows = []
    md += ['## 今日の成果', '']
    for item in outcomes:
        body = f'<p>{text(item["change"])}</p>'
        if item.get('pr_url'):
            body += f'<a class="pr-link" href="{text(item["pr_url"])}" target="_blank" rel="noopener noreferrer">PRを開く ↗</a>'
        outcome_rows.append([text(OUTCOMES[item['status']]), text(item['title']), body])
        md += [f'### {markdown_text(item["title"])}', '', f'状態：{OUTCOMES[item["status"]]}', '', markdown_text(item['change']), '']
        if item.get('pr_url'):
            md += [f'[PRを開く](<{item["pr_url"]}>)', '']
    if not outcomes:
        md += ['成果はありません。', '']
    sections.append(section('outcomes', '今日の成果', table(['状態', '成果', '変更内容'], outcome_rows) if outcomes else '', '成果はありません。'))

    reflection_rows, detail_rows = [], []
    md += ['## 採用と判断', '']
    for item in reflections:
        result = item['result']
        decision = DECISIONS.get(item.get('decision'), '判断未記載')
        overview = item.get('overview', {'title': item['title'], 'change': item.get('change') or '変更は未実施', 'evaluation': RESULTS[result] + '：' + item['evidence'], 'reason': item['next']})
        reflection_rows.append([text(decision), f'<strong>{text(overview["title"])}</strong><p>{text(overview["change"])}</p>', f'<p>{text(overview["evaluation"])}</p><p>{text(overview["reason"])}</p>'])
        md += [f'### {markdown_text(item["title"])}', '', f'判断：{decision}', '']
        if 'overview' in item:
            for label, key in [('概要の案名', 'title'), ('変更の要点', 'change'), ('実評価', 'evaluation'), ('判断理由', 'reason')]:
                md += [f'**{label}**：{markdown_text(overview[key])}', '']
        for label, value in [('何が起きた', item['happened']), ('次にどうする', item['next']), ('変更・対応', item.get('change') or '変更は未実施'), ('検証', RESULTS[result]), ('根拠', item['evidence'])]:
            detail_rows.append([text(item['title']), text(label), text(value)])
            md += [f'**{label}**：{markdown_text(value)}', '']
    if not reflections:
        md += ['反省点はありません。未分析・取得失敗は検証結果と残件に記載します。', '']
    reflection_content = table(['判断', '案と変更内容', '実評価と判断理由'], reflection_rows, 'decisions') if reflections else ''
    if reflections:
        reflection_content += '<details><summary>反省点と次の対応・根拠の全文</summary>' + table(['案', '項目', '内容'], detail_rows) + '</details>'
    sections.append(section('reflections', '採用と判断', reflection_content, '反省点はありません。未分析・取得失敗は検証結果と残件を参照してください。'))

    md += ['## 検証結果', '']
    check_rows = []
    for item in checks:
        check_rows.append([text(item['title']), text(RESULTS[item['result']]), text(item['detail'])])
        md += [f'### {markdown_text(item["title"])} — {RESULTS[item["result"]]}', '', markdown_text(item['detail']), '']
    if not checks:
        md += ['検証結果はありません。', '']
    sections.append(section('checks', '検証結果', table(['確認', '状態', '内容'], check_rows) if checks else '', '検証結果はありません。'))

    md += ['## 残件・判断待ち', '']
    sections.append(section('remaining', '残件・判断待ち', table(['未了事項', '理由と次の対応'], [[text(item['title']), text(item['detail'])] for item in remaining]) if remaining else '', '記録された残件はありません。'))
    for item in remaining:
        md += [f'### {markdown_text(item["title"])}', '', markdown_text(item['detail']), '']
    if not remaining:
        md += ['記録された残件はありません。', '']

    md += ['## 対象一覧', '']
    session_rows = []
    for item in sessions:
        evidence = '履歴の観測' if item['evidence'] == 'history' else '自己申告'
        session_rows.append([text(item['title']), text(item['source'] + ' · ' + evidence + ' · ' + SESSION_STATES[item['status']]), text(item['detail'])])
        md += [f'### {markdown_text(item["title"])}', '', f'{markdown_text(item["source"])}・{evidence}・{SESSION_STATES[item["status"]]}', '', markdown_text(item['detail']), '']
    if not sessions:
        md += ['記録された対象はありません。取得失敗とは区別してください。', '']
    session_content = '<details><summary>対象ごとの取得状態・結果・未確認事項</summary>' + table(['対象', '入力元と取得状態', '確認した内容'], session_rows) + '</details>' if sessions else ''
    sections.append(section('sessions', '対象一覧', session_content, '記録された対象はありません。取得失敗とは区別してください。'))

    wall = duration(timing.get('wall_seconds'))
    time_pairs = [('開始', timing.get('start') or '未計測'), ('終了', timing.get('end') or '未計測'), ('全体wall time', wall), ('計測範囲・再利用条件', timing.get('scope') or '記録なし')]
    time_content = table(['計測項目', '内容'], [[text(label), text(value)] for label, value in time_pairs])
    stage_rows = []
    md += ['## 時間', '']
    for label, value in time_pairs:
        md += [f'**{label}**：{markdown_text(value)}', '']
    for stage in timing.get('stages', []):
        elapsed = duration(stage['seconds'])
        stage_rows.append([text(stage['title']), elapsed, text(stage['detail'])])
        md += [f'### {markdown_text(stage["title"])} — {elapsed}', '', markdown_text(stage['detail']), '']
    if stage_rows:
        time_content += table(['段階', '実測', '計測範囲'], stage_rows)
    sections.append(section('timing', '時間', time_content, '時間は未計測です。'))

    metrics = f'採用済み成果 {sum(item["status"] == "adopted" for item in outcomes)}件 · 実測 {wall}'
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
