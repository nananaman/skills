"""Read-contract and scope regressions using synthetic schemas and metadata."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugin/skills/skill-maintenance/scripts'))
from codex_compat import ReadContract, matches, METHODS
from codex_index import source_boundary, index_page, permitted_scope
from codex_proxy import verify_server_version, validate_read_params
from codex_reader import read_completed
import codex_reader as READER
from tests import test_reader_regressions as fixtures


def schemas():
    params = {
        'InitializeParams': {'clientInfo': {'type': 'object'}, 'capabilities': {'type': 'object'}},
        'ThreadListParams': {'archived': {'type': 'boolean'}, 'sortKey': {'enum': ['updated_at']},
            'sortDirection': {'enum': ['asc', 'desc']}, 'sourceKinds': {'type': 'array', 'items': {'type': 'string'}},
            'useStateDbOnly': {'type': 'boolean'}, 'cwd': {'type': 'array', 'items': {'type': 'string'}}, 'limit': {'type': 'integer'}},
        'ThreadReadParams': {'threadId': {'type': 'string'}, 'includeTurns': {'type': 'boolean'}},
        'ThreadTurnsListParams': {'threadId': {'type': 'string'}, 'itemsView': {'enum': ['notLoaded']},
            'sortDirection': {'enum': ['asc', 'desc']}, 'limit': {'type': 'integer'}},
        'ThreadItemsListParams': {'threadId': {'type': 'string'}, 'turnId': {'type': 'string'},
            'sortDirection': {'enum': ['asc', 'desc']}, 'limit': {'type': 'integer'}},
    }
    definitions = {name: {'type': 'object', 'properties': properties} for name, properties in params.items()}
    request = {'definitions': definitions, 'oneOf': []}
    for method, (_, name) in METHODS.items():
        request['oneOf'].append({'type': 'object', 'required': ['id', 'method', 'params'],
            'properties': {'id': {'type': 'integer'}, 'method': {'enum': [method]},
                           'params': {'$ref': '#/definitions/' + (name or 'InitializeParams')}}})
    responses = {method: {'type': 'object', 'required': ['data'],
                         'properties': {'data': {'type': 'array', 'items': {'type': 'string'}}}}
                 for method in METHODS}
    return request, responses


class CompatibilityTest(unittest.TestCase):
    def test_server_build_is_observation_not_an_allowlist(self):
        for version in ('0.159.2', '0.160.0', '1.42.7-preview'):
            self.assertEqual(version, verify_server_version('desktop/' + version + ' (Mac OS; arm64)'))
        with self.assertRaises(ValueError): verify_server_version('unknown identity')

    def test_missing_rpc_or_metadata_control_fails_before_read(self):
        request, responses = schemas()
        ReadContract(request, responses)
        for alteration in ('method', 'body-control', 'cwd-filter', 'items-view'):
            with self.subTest(alteration=alteration):
                bad = copy.deepcopy(request)
                if alteration == 'method': bad['oneOf'].pop()
                elif alteration == 'body-control': del bad['definitions']['ThreadReadParams']['properties']['includeTurns']
                elif alteration == 'cwd-filter': del bad['definitions']['ThreadListParams']['properties']['cwd']
                else: bad['definitions']['ThreadTurnsListParams']['properties']['itemsView']['enum'] = ['full']
                with self.assertRaises(ValueError): ReadContract(bad, responses)

    def test_unknown_response_fields_types_and_schema_keywords_fail(self):
        request, responses = schemas()
        contract = ReadContract(request, responses)
        contract.validate_response('thread/list', {'data': ['synthetic']})
        for result in ({'data': ['synthetic'], 'unknown': True}, {'data': [1]}, {'data': False}):
            with self.assertRaises(ValueError): contract.validate_response('thread/list', result)
        self.assertFalse(matches('x', {'type': 'string', 'unknownKeyword': True}, {}))

    def test_declared_opaque_tool_payloads_use_boolean_json_schemas(self):
        # The installed schema declares MCP/dynamic arguments and content this way.
        schema = {'type': 'object', 'required': ['arguments', 'content'],
            'properties': {'arguments': True, 'content': {'type': 'array', 'items': True},
                           '_meta': True, 'structuredContent': True, 'results': {'type': 'array', 'items': True}}}
        self.assertTrue(matches({'arguments': {'synthetic': [1, None]},
            'content': [{'type': 'text', 'text': 'synthetic'}], '_meta': {},
            'structuredContent': {'synthetic': True}, 'results': [{}]}, schema, schema))
        self.assertFalse(matches('anything', False, {}))

    def test_metadata_request_guards_still_reject_body_reads_and_unbounded_listing(self):
        with self.assertRaises(ValueError): validate_read_params('thread/read', {'threadId': 'fixture', 'includeTurns': True})
        with self.assertRaises(ValueError): validate_read_params('thread/list', {'archived': False,
            'sortKey': 'updated_at', 'sortDirection': 'desc', 'sourceKinds': ['cli', 'vscode', 'exec', 'appServer'],
            'useStateDbOnly': True, 'limit': 50})


class OrganizationTest(unittest.TestCase):
    def source(self, owner='example'):
        source = fixtures.ReaderRegressions().source()
        source['repos'][0].update(id=owner + '/project', information_scope='organization:' + owner)
        return source

    def test_registered_organization_matches_both_repo_and_cwd(self):
        for owner in ('example', 'another'):
            with self.subTest(owner=owner):
                source = self.source(owner)
                source_boundary(source)
                row = fixtures.ReaderRegressions().metadata('fixture', 1)
                row['gitInfo']['originUrl'] = 'https://github.com/' + owner + '/project.git'
                home = str(Path.home() / '.codex')
                self.assertIsNotNone(index_page([row], source, home)[0]['thread'])
                for wrong in ('repo', 'cwd'):
                    bad = copy.deepcopy(row)
                    if wrong == 'repo': bad['gitInfo']['originUrl'] = 'https://github.com/' + owner + '/outside.git'
                    else: bad['cwd'] += '-another'
                    self.assertIsNone(index_page([bad], source, home)[0]['thread'])

    def test_unknown_empty_and_unnormalized_scope_is_rejected(self):
        for scope in ('public', 'organization:', 'organization: example',
                      'organization:example ', 'personal: ', 'unknown:example', None):
            with self.subTest(scope=scope):
                self.assertFalse(permitted_scope(scope))

    def test_mixed_scope_and_caller_owner_mismatch_fail(self):
        for wrong in ('mixed', 'mixed-organizations', 'organization', 'owner'):
            source = self.source()
            if wrong == 'mixed':
                source['repos'].append(dict(id='example/personal', cwd='/synthetic/personal', information_scope='personal:example'))
            elif wrong == 'mixed-organizations':
                source['repos'].append(dict(id='another/project', cwd='/synthetic/another', information_scope='organization:another'))
            elif wrong == 'organization': source['repos'][0]['information_scope'] = 'organization:another'
            else: source['repos'][0]['id'] = 'another/example'
            with self.assertRaises(ValueError): source_boundary(source)

    def test_body_is_not_read_after_registered_local_origin_changes(self):
        selection = fixtures.ReaderRegressions().selection()
        selection['adapter_selection'] = source_boundary(self.source())
        selection['turn_selection_complete'] = True
        selection['threads'][0].update(repository='example/project', information_scope='organization:example', turns=[])
        for change in ({'cwd': '/synthetic/personal-copy'}, {'ephemeral': True},
                       {'source': 'unknown'}, {'extra': {'remoteHost': 'another'}}):
            row = fixtures.ReaderRegressions().metadata('root', 1)
            row['gitInfo']['originUrl'] = 'https://github.com/example/project.git'
            row.update(change)
            class Fake:
                body_calls = 0
                def call(self, method, params):
                    if method == 'thread/read': return {'thread': row}
                    self.body_calls += 1
                    raise AssertionError('body must not be fetched')
            fake = Fake()
            with self.subTest(change=change), self.assertRaises(ValueError):
                read_completed(fake, selection, {'sources': {}, 'units': {}})
            self.assertEqual(0, fake.body_calls)

    def test_read_rejects_other_scope_state_before_proxy_or_body(self):
        selection = fixtures.ReaderRegressions().selection()
        selection['adapter_selection'] = source_boundary(self.source())
        selection['turn_selection_complete'] = True
        selection['threads'][0].update(repository='example/project', information_scope='organization:example', turns=[])
        for scope in ('personal:example', 'organization:another'):
            ledger = dict(target={'information_scope': scope}, sources={}, units={})
            with self.subTest(scope=scope):
                with patch.object(READER, 'Proxy') as proxy:
                    with self.assertRaisesRegex(ValueError, 'selection and state information scopes differ'):
                        read_completed(proxy, selection, ledger)
                    proxy.call.assert_not_called()
                with tempfile.TemporaryDirectory() as tmp:
                    private = Path(tmp)
                    selection_path, state_path, output = [private/name for name in ('selection.json', 'state.json', 'output.json')]
                    selection_path.write_text(json.dumps(selection))
                    state_path.write_text(json.dumps(ledger))
                    args = ['reader', 'read', '--selection', str(selection_path), '--state', str(state_path),
                            '--read-completed', '--repo',str(ROOT),'--codex-home', str(Path.home()/'.codex'), '--output', str(output)]
                    with patch.object(READER, 'Proxy') as proxy, patch.object(sys, 'platform', 'darwin'), patch.object(sys, 'argv', args):
                        self.assertEqual(2, READER.main())
                        proxy.assert_not_called()
                    self.assertFalse(output.exists())
                    result = json.loads(output.with_suffix('.result.json').read_text())
                    self.assertEqual(0, result['body_read_calls'])
                    self.assertFalse(result['output_written'])


if __name__ == '__main__': unittest.main()
