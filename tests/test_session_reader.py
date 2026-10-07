import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'plugin/skills/skill-maintenance/scripts/session_reader.py'


class SessionReaderTest(unittest.TestCase):
    def test_visible_context_preserves_calls_results_and_order_without_reasoning(self):
        spec = importlib.util.spec_from_file_location('session_reader', SCRIPT)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        records = [
            {'type': 'session_meta', 'payload': {'id': 'test', 'cwd': '/example'}},
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': 'Keep the fixture assertions.'}]}},
            {'type': 'response_item', 'payload': {'type': 'custom_tool_call', 'name': 'exec', 'call_id': 'a', 'input': 'test --env-disabled'}},
            {'type': 'response_item', 'payload': {'type': 'custom_tool_call_output', 'call_id': 'a', 'output': [{'type': 'input_text', 'text': 'fixture passed\n' + 'ordinary context\n' * 1000}]}},
            {'type': 'response_item', 'payload': {'type': 'reasoning', 'summary': 'private'}},
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'phase': 'analysis', 'content': [{'type': 'text', 'text': 'private'}]}},
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'phase': 'final_answer', 'content': [{'type': 'output_text', 'text': 'Done.'}]}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'session.jsonl'
            source.write_text(''.join(json.dumps(record) + '\n' for record in records))
            result = reader.read_session(source)
        self.assertEqual([item['line'] for item in result['items']], [2, 3, 4, 7])
        self.assertEqual(result['items'][1]['payload']['input'], 'test --env-disabled')
        self.assertEqual(result['items'][2]['payload']['output'], records[3]['payload']['output'])
        self.assertNotIn('private', json.dumps(result['items']))

    def test_collection_accounts_for_every_file_and_isolates_corrupt_history(self):
        spec = importlib.util.spec_from_file_location('session_reader', SCRIPT)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            sessions = root / 'sessions'
            sessions.mkdir()
            for number in range(3):
                (sessions / f'{number}.jsonl').write_text(json.dumps({'type': 'session_meta', 'payload': {'id': str(number)}}) + '\n' + json.dumps({'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': []}}) + '\n' + json.dumps({'type': 'event_msg', 'payload': {'type': 'task_complete'}}) + '\n')
            (sessions / 'broken.jsonl').write_text('{invalid\n')
            result = reader.collect(sessions, root / 'private', root / 'repo')
            self.assertEqual(result['counts'], {'discovered': 4, 'selected': 4, 'read': 3, 'partial': 0, 'failed': 1, 'outside_period': 0, 'excluded': 0, 'held': 0})
            self.assertEqual(len(result['sessions']), 4)
            self.assertTrue(all(Path(item['transcript']).exists() for item in result['sessions'] if item.get('transcript')))

    def test_period_selection_retains_earlier_context_and_marks_source_gaps(self):
        spec = importlib.util.spec_from_file_location('session_reader', SCRIPT)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            sessions = root / 'sessions'
            sessions.mkdir()
            records = [
                {'type': 'session_meta', 'payload': {'id': 'test'}},
                {'timestamp': '2026-10-01T01:00:00Z', 'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'text', 'text': 'Earlier requirement'}]}},
                {'timestamp': '2026-10-07T01:00:00Z', 'type': 'response_item', 'payload': {'type': 'function_call_output', 'output': 'Output truncated by source'}},
                {'timestamp': '2026-10-07T01:01:00Z', 'type': 'event_msg', 'payload': {'type': 'task_complete'}},
                {'timestamp': '2026-10-08T00:00:00Z', 'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'text', 'text': 'Future private request'}]}},
            ]
            (sessions / 'test.jsonl').write_text(''.join(json.dumps(record) + '\n' for record in records))
            result = reader.collect(sessions, root / 'private', root / 'repo', '2026-10-07T00:00:00Z', '2026-10-08T00:00:00Z')
            transcript = Path(result['sessions'][0]['transcript']).read_text()
            self.assertIn('Earlier requirement', transcript)
            self.assertIn('Output truncated by source', transcript)
            self.assertNotIn('Future private request', transcript)
            self.assertEqual(result['sessions'][0]['source_gaps'], [3])

    def test_source_scope_excludes_other_repos_and_children_before_body_read(self):
        spec = importlib.util.spec_from_file_location('session_reader', SCRIPT)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            sessions = root / 'sessions'
            sessions.mkdir()
            for name, repository, parent in [('allowed', 'example/app', None), ('other', 'another/private', None), ('child', 'example/app', 'allowed')]:
                metadata = {'id': name, 'parent_thread_id': parent, 'git': {'repository_url': f'https://github.com/{repository}.git'}}
                (sessions / (name + '.jsonl')).write_text(json.dumps({'type': 'session_meta', 'payload': metadata}) + '\n' + (json.dumps({'type': 'response_item', 'payload': {'type': 'message', 'role': 'user'}}) if name == 'allowed' else '{unread corrupt body') + '\n' + json.dumps({'type': 'event_msg', 'payload': {'type': 'task_complete'}}) + '\n')
            result = reader.collect(sessions, root / 'private', root / 'repo', source={'repos': [{'id': 'example/app', 'cwd': '/example'}]})
            self.assertEqual(result['counts']['read'], 1)
            self.assertEqual(result['counts']['excluded'], 2)
            self.assertEqual(result['counts']['failed'], 0)

    def test_active_session_is_held_without_exporting_visible_body(self):
        spec = importlib.util.spec_from_file_location('session_reader', SCRIPT)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / 'active.jsonl'
            path.write_text('\n'.join(json.dumps(record) for record in [
                {'type': 'session_meta', 'payload': {'id': 'active'}},
                {'type': 'event_msg', 'payload': {'type': 'task_started'}},
                {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'text', 'text': 'Unfinished private task'}]}},
                {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'phase': 'final_answer', 'content': []}},
            ]) + '\n')
            result = reader.collect(path, root / 'private', root / 'repo')
            self.assertEqual(result['sessions'][0]['status'], 'held')
            self.assertFalse(list((root / 'private').glob('session-*')))
            self.assertNotIn('Unfinished private task', (root / 'private/manifest.json').read_text())

    def test_symlink_does_not_expand_authorized_directory(self):
        spec = importlib.util.spec_from_file_location('session_reader', SCRIPT)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            sessions = root / 'sessions'
            sessions.mkdir()
            outside = root / 'outside.jsonl'
            outside.write_text(json.dumps({'type': 'session_meta', 'payload': {'id': 'outside'}}) + '\n' + json.dumps({'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'text', 'text': 'Outside private body'}]}}) + '\n')
            (sessions / 'link.jsonl').symlink_to(outside)
            result = reader.collect(sessions, root / 'private', root / 'repo')
            self.assertEqual(result['counts']['failed'], 1)
            self.assertFalse(list((root / 'private').glob('session-*')))
            self.assertNotIn('Outside private body', (root / 'private/manifest.json').read_text())

    def test_streamed_transcript_keeps_all_items_and_manifest_accounts_for_period_exclusion(self):
        spec = importlib.util.spec_from_file_location('session_reader', SCRIPT)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            sessions = root / 'sessions'
            sessions.mkdir()
            for name, stamp in [('selected', '2026-10-07T01:00:00Z'), ('old', '2026-10-01T01:00:00Z')]:
                records = [{'type': 'session_meta', 'timestamp': stamp, 'payload': {'id': name}}]
                records += [{'type': 'response_item', 'timestamp': stamp, 'payload': {'type': 'function_call_output', 'output': f'{number}:' + 'ordinary context' * 1000}} for number in range(40)]
                records.append({'type': 'event_msg', 'timestamp': stamp, 'payload': {'type': 'task_complete'}})
                (sessions / (name + '.jsonl')).write_text(''.join(json.dumps(item) + '\n' for item in records))
            result = reader.collect(sessions, root / 'private', root / 'repo', '2026-10-07T00:00:00Z')
            self.assertEqual(len(result['sessions']), result['counts']['discovered'])
            selected = next(item for item in result['sessions'] if item['status'] == 'read')
            items = [json.loads(line) for line in Path(selected['transcript']).read_text().splitlines()]
            self.assertEqual([item['line'] for item in items], list(range(2, 42)))
            self.assertEqual(items[-1]['payload']['output'], '39:' + 'ordinary context' * 1000)
            self.assertTrue(all('elapsed_seconds' in item for item in result['sessions']))

    def test_private_output_refuses_git_checkout_and_preserves_existing_directory(self):
        spec = importlib.util.spec_from_file_location('session_reader', SCRIPT)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repo = root / 'repo'
            repo.mkdir()
            with self.assertRaises(ValueError):
                reader.private_directory(repo / 'private', repo)
            self.assertFalse((repo / 'private').exists())
            output = root / 'private'
            output.mkdir()
            marker = output / 'keep'
            marker.write_text('preserve')
            with self.assertRaises(FileExistsError):
                reader.private_directory(output, repo)
            self.assertEqual(marker.read_text(), 'preserve')

    def test_null_git_metadata_still_matches_configured_cwd(self):
        spec = importlib.util.spec_from_file_location('session_reader', SCRIPT)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / 'completed.jsonl'
            records = [
                {'type': 'session_meta', 'payload': {'id': 'test', 'cwd': '/example/app', 'git': None}},
                {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': []}},
                {'type': 'event_msg', 'payload': {'type': 'task_complete'}},
            ]
            path.write_text(''.join(json.dumps(item) + '\n' for item in records))
            result = reader.collect(path, root / 'private', root / 'repo', source={'repos': [{'id': 'example/app', 'cwd': '/example/app'}]})
            self.assertEqual(result['counts']['read'], 1)
            self.assertEqual(result['sessions'][0]['repository'], 'example/app')

    def test_unknown_completion_is_held_instead_of_success(self):
        spec = importlib.util.spec_from_file_location('session_reader', SCRIPT)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / 'unknown.jsonl'
            path.write_text(json.dumps({'type': 'session_meta', 'payload': {'id': 'unknown'}}) + '\n' + json.dumps({'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': []}}) + '\n')
            result = reader.collect(path, root / 'private', root / 'repo')
            self.assertEqual(result['sessions'][0]['status'], 'held')
            self.assertIn('termination', result['sessions'][0]['reason'])
            self.assertFalse(list((root / 'private').glob('session-*')))

    def test_source_root_with_symlink_parent_is_rejected(self):
        spec = importlib.util.spec_from_file_location('session_reader', SCRIPT)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            outside = root / 'outside'
            (outside / 'sessions').mkdir(parents=True)
            (root / 'alias').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                reader.collect(root / 'alias/sessions', root / 'private', root / 'repo')
            self.assertFalse((root / 'private').exists())

    def test_index_byte_boundary_excludes_a_newly_appended_task(self):
        spec = importlib.util.spec_from_file_location('session_reader', SCRIPT)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / 'session.jsonl'
            records = [
                {'type': 'session_meta', 'payload': {'id': 'test'}},
                {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'text', 'text': 'Completed task'}]}},
                {'type': 'event_msg', 'payload': {'type': 'task_complete'}},
            ]
            path.write_text(''.join(json.dumps(record) + '\n' for record in records))
            boundary = path.stat().st_size
            with path.open('a') as stream:
                stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'task_started'}}) + '\n')
                stream.write(json.dumps({'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'text', 'text': 'Appended active task'}]}}) + '\n')
            result = reader.read_session(path, end_bytes=boundary)
            self.assertIn('Completed task', json.dumps(result['items']))
            self.assertNotIn('Appended active task', json.dumps(result['items']))
            self.assertEqual(result['lifecycle'][-1]['event'], 'task_complete')

    def test_append_after_index_does_not_start_visible_body_read(self):
        spec = importlib.util.spec_from_file_location('session_reader', SCRIPT)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / 'session.jsonl'
            records = [
                {'type': 'session_meta', 'payload': {'id': 'test'}},
                {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': []}},
                {'type': 'event_msg', 'payload': {'type': 'task_complete'}},
            ]
            path.write_text(''.join(json.dumps(record) + '\n' for record in records))
            original = reader.read_session
            body_reads = []
            def append_after_index(*args, **kwargs):
                if kwargs.get('sink') is not None:
                    body_reads.append(True)
                result = original(*args, **kwargs)
                if kwargs.get('index_only'):
                    with path.open('a') as stream:
                        stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'task_started'}}) + '\n')
                        stream.write(json.dumps({'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': []}}) + '\n')
                return result
            with patch.object(reader, 'read_session', side_effect=append_after_index):
                result = reader.collect(path, root / 'private', root / 'repo')
            self.assertEqual(body_reads, [])
            self.assertEqual(result['counts']['held'], 1)
            self.assertFalse(list((root / 'private').glob('session-*')))
