import importlib.util
import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'plugin/skills/skill-maintenance/scripts/render_report.py'
spec = importlib.util.spec_from_file_location('render_report', SCRIPT)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class ReportRendererTest(unittest.TestCase):
    def test_decision_table_keeps_explicit_judgment_and_full_evidence_separate_from_test_result(self):
        reflection = {'title': '元の案', 'happened': '長い経緯', 'next': '追加の入力を用意する',
                      'change': '実装候補', 'result': 'passed', 'evidence': '限定した確認は成功',
                      'decision': 'held', 'overview': {'title': '短い案名', 'change': '変更の要点',
                                                     'evaluation': '比較0実行', 'reason': '因果関係は未確認'}}
        report = {'version': 1, 'date': '2026-10-07', 'timezone': 'Asia/Tokyo', 'reflections': [reflection]}

        result = renderer.render_report(report)

        self.assertIn('<table', result['html'])
        self.assertIn('<details', result['html'])
        for document in result.values():
            self.assertIn('成果はありません', document)
            for value in ['保留', '短い案名', '変更の要点', '比較0実行', '因果関係は未確認',
                          '長い経緯', '追加の入力を用意する', '実装候補', '限定した確認は成功']:
                self.assertIn(value, document)
        del reflection['decision']
        self.assertIn('判断未記載', renderer.render_report(report)['html'])
        for invalid in [{'decision': 'unknown'}, {'overview': {'title': '不足'}},
                        {'overview': {**reflection['overview'], 'reason': 1}}]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                renderer.render_report({**report, 'reflections': [{**reflection, **invalid}]})

    def test_durations_use_minutes_and_seconds_without_mutating_precise_input(self):
        report = {'version': 1, 'date': '2026-10-07', 'timezone': 'Asia/Tokyo',
                  'timing': {'wall_seconds': 1471.333666, 'stages': [
                      {'title': '秒未満', 'seconds': 0.9, 'detail': '端数は表示で切り捨て'},
                      {'title': '一分', 'seconds': 60, 'detail': '境界'},
                      {'title': '未計測', 'seconds': None, 'detail': '未知'}]}}
        original = copy.deepcopy(report)

        result = renderer.render_report(report)

        self.assertEqual(report, original)
        for document in result.values():
            for value in ['24分31秒', '0分0秒', '1分0秒', '未計測']:
                self.assertIn(value, document)
            self.assertNotIn('1471.333666秒', document)

    def test_period_counts_and_reader_hold_reasons_are_preserved_without_success_inference(self):
        period = '2026-10-05 03:51:53 JST以上、2026-10-07 17:40 JST未満'
        counts = '発見3・対象2・取得1・振り返り1・保留1・期間外1'
        report = {'version': 1, 'date': '2026-10-07', 'timezone': 'Asia/Tokyo', 'period': period,
                  'checks': [{'title': '取得範囲', 'result': 'partial', 'detail': counts}],
                  'sessions': [
                      {'title': '終了不明', 'source': 'Mac', 'evidence': 'history', 'status': 'held', 'detail': '終了を確認できず本文を保留'},
                      {'title': '期間外', 'source': 'Mac', 'evidence': 'history', 'status': 'outside_period', 'detail': '指定期間に活動なし'},
                  ]}

        result = renderer.render_report(report)

        self.assertIn(period, result['html'])
        self.assertIn(period.replace('-', r'\-'), result['markdown'])
        for document in result.values():
            for value in [counts, '終了を確認できず本文を保留', '指定期間に活動なし']:
                self.assertIn(value, document)

    def test_io_failure_is_not_reported_as_success_and_preserves_input_and_partial_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'input.json'
            source.write_text(json.dumps({'version': 1, 'date': '2026-10-07', 'timezone': 'Asia/Tokyo'}))
            before = source.read_bytes()
            output = root / 'output'
            original_open = renderer.os.open

            def fail_markdown(path, *args):
                if Path(path).name == 'report.md':
                    raise OSError('synthetic write failure')
                return original_open(path, *args)

            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.object(sys, 'argv', [str(SCRIPT), '--input', str(source), '--repo', str(root / 'repo'), '--output', str(output)]), patch.object(sys, 'path', [str(SCRIPT.parent), *sys.path]), patch.object(renderer.os, 'open', side_effect=fail_markdown), redirect_stdout(stdout), redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as exited:
                    renderer.main()

            self.assertEqual(exited.exception.code, 1)
            self.assertEqual(stdout.getvalue(), '')
            self.assertIn('render failed', stderr.getvalue())
            self.assertEqual(source.read_bytes(), before)
            self.assertTrue((output / 'report.html').is_file())
            self.assertFalse((output / 'report.md').exists())

    def test_html_and_markdown_escape_untrusted_text_without_embedding_executable_json(self):
        attack = '</script><img src="https://example.com/tracker" onerror="alert(1)">\n[click](javascript:alert(1)) $sections'
        report = {'version': 1, 'date': '2026-10-07', 'timezone': 'Asia/Tokyo', 'summary': attack,
                  'reflections': [{'title': attack, 'happened': attack, 'next': attack, 'result': 'unverified', 'evidence': attack,
                                   'decision': 'held', 'overview': dict.fromkeys(['title', 'change', 'evaluation', 'reason'], attack)}]}

        result = renderer.render_report(report)

        self.assertNotIn('<img', result['html'])
        self.assertIn('&lt;/script&gt;', result['html'])
        self.assertNotIn('<script>', result['html'])
        self.assertIn('$sections', result['html'])
        self.assertNotIn('<img', result['markdown'])
        self.assertNotIn('[click](javascript:', result['markdown'])

    def test_empty_failed_and_unverified_reports_keep_unknown_results_explicit(self):
        empty = renderer.render_report({'version': 1, 'date': '2026-10-07', 'timezone': 'Asia/Tokyo'})
        failed = renderer.render_report({'version': 1, 'date': '2026-10-07', 'timezone': 'Asia/Tokyo', 'checks': [{'title': '取得', 'result': 'failed', 'detail': '合成の取得失敗'}], 'remaining': [{'title': '再取得', 'detail': '未分析'}]})

        for doc in empty.values():
            self.assertIn('成果はありません', doc)
            self.assertIn('未計測', doc)
        for doc in failed.values():
            self.assertIn('合成の取得失敗', doc)
            self.assertIn('未分析', doc)

    def test_long_unicode_is_preserved_but_embedding_limit_refuses_oversized_html(self):
        long_text = '長い合成結果\n' * 1500
        report = {'version': 1, 'date': '2026-10-07', 'timezone': 'Asia/Tokyo', 'summary': long_text}
        result = renderer.render_report(report)
        self.assertIn(long_text, result['html'])
        self.assertIn(long_text, result['markdown'])
        report['summary'] = '長' * 100000
        with self.assertRaisesRegex(ValueError, '256 KiB'):
            renderer.render_report(report)

    def test_cli_writes_private_outputs_preserves_json_and_refuses_existing_or_git_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repo = root / 'repo'
            repo.mkdir()
            (repo / '.git').mkdir()
            source = root / 'report.json'
            source.write_text(json.dumps({'version': 1, 'date': '2026-10-07', 'timezone': 'Asia/Tokyo'}))
            before = source.read_bytes()
            output = root / 'rendered'
            args = [sys.executable, str(SCRIPT), '--input', str(source), '--repo', str(repo), '--output', str(output)]

            result = subprocess.run(args, capture_output=True, text=True)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({p.name for p in output.iterdir()}, {'report.html', 'report.md'})
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in output.iterdir()))
            preserved = (output / 'report.html').read_bytes()
            repeated = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertEqual((output / 'report.html').read_bytes(), preserved)
            args[-1] = str(repo / 'rendered')
            rejected = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertFalse((repo / 'rendered').exists())

    def test_thin_data_contract_rejects_raw_metadata_bad_types_unknown_states_and_invalid_time(self):
        base = {'version': 1, 'date': '2026-10-07', 'timezone': 'Asia/Tokyo'}
        cases = [
            {'raw_log': 'synthetic private source'},
            {'version': True}, {'version': 2}, {'date': 'not-a-date'}, {'timezone': 'Unknown/Zone'},
            {'summary': {'nested': 'not text'}}, {'checks': 'not a list'},
            {'checks': [{'title': '確認', 'result': 'clean', 'detail': '未確認'}]},
            {'remaining': [{'title': '確認', 'detail': '保留', 'private_path': '/synthetic'}]},
            {'sessions': [{'title': '確認', 'source': 'Mac', 'evidence': 'verified', 'status': 'read', 'detail': ''}]},
            {'timing': {'wall_seconds': True}}, {'timing': {'wall_seconds': -1}}, {'timing': {'wall_seconds': float('nan')}},
            {'timing': {'start': '2026-10-07T09:00:00'}},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                report = copy.deepcopy(base)
                report.update(changes)
                with self.assertRaises(ValueError):
                    renderer.render_report(report)

    def test_links_refuse_executable_local_credentialed_and_ambiguous_urls(self):
        credentialed_url = 'https://' + ':'.join(('synthetic-user', 'synthetic-password')) + '@example.com/pr'
        for url in ['javascript:alert(1)', 'data:text/html,test', 'file:///private/example', '//example.com/pr', credentialed_url, 'https://example.com/\npr', 'https://example.com/" onclick="alert(1)', 'https://example.com\\@other.example/pr', 'https://example.com/pull/1?access_token=synthetic', 'https://example.com/pull/1#token=synthetic']:
            with self.subTest(url=url):
                report = {'version': 1, 'date': '2026-10-07', 'timezone': 'Asia/Tokyo', 'outcomes': [{'title': '合成PR', 'change': '合成変更', 'status': 'draft', 'pr_url': url}]}
                with self.assertRaises(ValueError):
                    renderer.render_report(report)

    def test_results_and_connected_reflection_precede_checks_remaining_sessions_and_time(self):
        report = {
            'version': 1, 'date': '2026-10-07', 'timezone': 'Asia/Tokyo',
            'outcomes': [{'title': '合成の改善', 'change': '読みやすい出力へ変更', 'status': 'draft', 'pr_url': 'https://example.com/pull/1'}],
            'reflections': [{'title': '合成の反省', 'happened': '最後の確認が漏れた', 'next': '最終編集後に確認する', 'change': '確認手順を更新', 'result': 'passed', 'evidence': '合成の確認が成功'}],
            'checks': [{'title': '合成検証', 'result': 'passed', 'detail': '1件成功'}],
            'remaining': [{'title': '採用判断', 'detail': 'draftの内容を確認'}],
            'sessions': [{'title': '合成実務', 'source': 'Mac', 'evidence': 'history', 'status': 'read', 'detail': '観測した範囲を整理'}],
            'timing': {'start': None, 'end': None, 'wall_seconds': None, 'scope': '全体は未計測', 'stages': []},
        }

        result = renderer.render_report(report)

        self.assertEqual(result, renderer.render_report(report))
        for document in result.values():
            positions = [document.index(title) for title in ['今日の成果', '採用と判断', '検証結果', '残件・判断待ち', '対象一覧', '時間']]
            self.assertEqual(positions, sorted(positions))
            for text in ['最後の確認が漏れた', '最終編集後に確認する', '確認手順を更新', '合成の確認が成功']:
                self.assertIn(text, document)
            self.assertIn('https://example.com/pull/1', document)


if __name__ == '__main__':
    unittest.main()
