"""Verify the installed CLI's read contract without opening history or settings."""
import json
import subprocess
import tempfile
from pathlib import Path
from common import require

CONTRACT = 'bounded-metadata-read-v1'
METHODS = {
    'initialize': ('v1/InitializeResponse.json', None),
    'thread/list': ('v2/ThreadListResponse.json', 'ThreadListParams'),
    'thread/read': ('v2/ThreadReadResponse.json', 'ThreadReadParams'),
    'thread/turns/list': ('v2/ThreadTurnsListResponse.json', 'ThreadTurnsListParams'),
    'thread/items/list': ('v2/ThreadItemsListResponse.json', 'ThreadItemsListParams'),
}
KEYWORDS = {'$schema', '$ref', 'definitions', 'description', 'title', 'default',
            'format', 'type', 'enum', 'required', 'properties', 'additionalProperties',
            'items', 'allOf', 'anyOf', 'oneOf', 'minimum', 'minLength'}


def matches(value, schema, document, depth=0):
    """Fail closed on unsupported schema syntax, fields, types and enum values."""
    if type(schema) is bool:
        return schema
    if depth > 128 or not isinstance(schema, dict) or set(schema) - KEYWORDS:
        return False
    if '$ref' in schema:
        ref = schema['$ref']
        if not isinstance(ref, str) or not ref.startswith('#/definitions/'):
            return False
        definition = document.get('definitions', {}).get(ref.removeprefix('#/definitions/'))
        return matches(value, definition, document, depth + 1)
    for operator in ('allOf', 'anyOf', 'oneOf'):
        if operator in schema:
            outcomes = [matches(value, item, document, depth + 1) for item in schema[operator]]
            if not (all(outcomes) if operator == 'allOf' else any(outcomes)
                    if operator == 'anyOf' else sum(outcomes) == 1):
                return False
    kinds = schema.get('type')
    actual = ('null' if value is None else 'boolean' if type(value) is bool else
              'integer' if type(value) is int else 'number' if type(value) is float else
              'string' if isinstance(value, str) else 'array' if isinstance(value, list) else
              'object' if isinstance(value, dict) else None)
    if kinds is not None:
        kinds = [kinds] if isinstance(kinds, str) else kinds
        if actual not in kinds and not (actual == 'integer' and 'number' in kinds):
            return False
    if 'enum' in schema and value not in schema['enum']:
        return False
    if actual in {'integer', 'number'} and 'minimum' in schema and value < schema['minimum']:
        return False
    if actual == 'string' and len(value) < schema.get('minLength', 0):
        return False
    if actual == 'array' and 'items' in schema:
        if not all(matches(item, schema['items'], document, depth + 1) for item in value):
            return False
    if actual == 'object':
        if not set(schema.get('required', [])) <= value.keys():
            return False
        properties = schema.get('properties', {})
        for key, item in value.items():
            if key in properties:
                if not matches(item, properties[key], document, depth + 1):
                    return False
            elif 'properties' in schema or 'additionalProperties' in schema:
                additional = schema.get('additionalProperties', False)
                if additional is not True and not matches(item, additional, document, depth + 1):
                    return False
    return True


class ReadContract:
    def __init__(self, request, responses):
        self.request = request
        self.responses = responses
        self.methods = {}
        for branch in request.get('oneOf', []):
            method = branch.get('properties', {}).get('method', {}).get('enum', [])
            if len(method) == 1 and method[0] in METHODS:
                require(method[0] not in self.methods, 'ambiguous read method schema')
                self.methods[method[0]] = branch
        require(set(self.methods) == set(METHODS), 'required read RPC unavailable')
        definitions = request.get('definitions', {})
        guards = {'ThreadListParams': {'useStateDbOnly', 'cwd', 'sourceKinds', 'sortKey', 'sortDirection'},
                  'ThreadReadParams': {'includeTurns', 'threadId'},
                  'ThreadTurnsListParams': {'itemsView', 'threadId', 'sortDirection'},
                  'ThreadItemsListParams': {'turnId', 'threadId', 'sortDirection'}}
        for name, fields in guards.items():
            require(fields <= definitions.get(name, {}).get('properties', {}).keys(),
                    'required metadata-only control unavailable')
        self.validate_request('thread/list', dict(archived=False, sortKey='updated_at',
            sortDirection='desc', sourceKinds=['cli', 'vscode', 'exec', 'appServer'],
            useStateDbOnly=True, cwd=['/synthetic/repo'], limit=50))
        self.validate_request('thread/read', dict(threadId='synthetic', includeTurns=False))
        self.validate_request('thread/turns/list', dict(threadId='synthetic', itemsView='notLoaded',
            sortDirection='desc', limit=20))
        self.validate_request('thread/items/list', dict(threadId='synthetic', turnId='synthetic',
            sortDirection='asc', limit=20))

    def validate_request(self, method, params):
        require(method in self.methods and matches(dict(id=1, method=method, params=params),
                self.methods[method], self.request), 'incompatible read request schema')

    def validate_response(self, method, result):
        schema = self.responses[method]
        require(matches(result, schema, schema), 'unknown read response schema: ' + method)


def inspect_cli(executable, env, budget):
    def run(arguments):
        budget.check()
        return subprocess.run([executable, *arguments], env=env, capture_output=True, text=True,
            timeout=min(15, max(0.001, budget.deadline - __import__('time').monotonic())), check=True)
    version = run(['--version']).stdout.strip()
    require(version.startswith('codex-cli ') and len(version) < 128,
            'unknown Codex CLI identity')
    run(['app-server', 'proxy', '--help'])
    with tempfile.TemporaryDirectory(prefix='codex-read-schema-') as directory:
        run(['app-server', 'generate-json-schema', '--experimental', '--out', directory])
        root = Path(directory)
        require(sum(p.stat().st_size for p in root.rglob('*.json')) <= 64 * 1024 * 1024,
                'CLI schema size budget exceeded')
        request = json.loads((root / 'ClientRequest.json').read_text())
        responses = {method: json.loads((root / path).read_text()) for method, (path, _) in METHODS.items()}
    budget.check()
    return ReadContract(request, responses), version
