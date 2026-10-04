"""Shared private input contract; no reader, transport, or maintenance state imports."""
from datetime import datetime, timezone
from pathlib import PurePosixPath, PureWindowsPath
import re


SENSITIVE = re.compile(r'(?i)(api[_-]?key\s*[:=]|password\s*[:=]|secret\s*[:=]|bearer\s+|-----BEGIN.*PRIVATE KEY|sk-[a-z0-9]{12}|gh[pousr]_[a-z0-9]{12})')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def instant(value):
    require(isinstance(value, str), "timestamp must be a string")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("invalid timestamp") from None
    require(result.tzinfo is not None, "timestamp requires a timezone")
    return result.astimezone(timezone.utc)


def stamp(value):
    return value.isoformat().replace("+00:00", "Z")


def text_id(value):
    require(isinstance(value, str) and value.strip() and len(value) <= 256, "invalid identifier")
    return value


def turn_disposition(status, started, completed, start, end, known=False):
    """Select finished observations by completion, including failed/interrupted work."""
    require(status in {'completed', 'failed', 'interrupted', 'inProgress'}, 'unknown turn status')
    require(started is not None, 'missing turn start time')
    if status == 'inProgress':
        require(completed is None, 'in-progress turn has completion time')
        return 'pending'
    require(completed is not None and completed >= started, 'finished turn lacks valid completion time')
    return 'selected' if completed <= end and (completed >= start or known) else 'skip'


def path_key(value, flavour):
    cls = PureWindowsPath if flavour == 'windows' else PurePosixPath
    path = cls(value)
    require(path.is_absolute() and '..' not in path.parts, 'source cwd must be absolute and normalized')
    return str(path).casefold() if flavour == 'windows' else str(path)


def validate_content(content):
    require(isinstance(content, dict) and set(content) == {'request', 'expected', 'observed'},
            'invalid fact content')
    require(all(isinstance(v, str) and v.strip() for v in content.values()), 'empty fact content')
    require(not any(SENSITIVE.search(v) for v in content.values()), 'sensitive content blocked')


def validate_evidence(evidence):
    """Check ordered, minimized events; completeness remains a reader assertion."""
    require(isinstance(evidence, dict) and set(evidence) == {'version', 'complete', 'truncated', 'events'}
            and type(evidence['version']) is int and evidence['version'] == 1,
            'unknown evidence contract')
    require(evidence['complete'] is True and evidence['truncated'] is False,
            'incomplete or truncated evidence; not no-change')
    events = evidence['events']
    require(isinstance(events, list) and len(events) <= 256, 'evidence event budget exceeded')
    seen, calls, results = set(), set(), set()
    for event in events:
        require(isinstance(event, dict) and {'id', 'kind', 'summary'} <= event.keys(), 'invalid evidence event')
        ident = text_id(event['id'])
        require(ident not in seen, 'duplicate evidence event ID')
        kind = event['kind']
        require(isinstance(kind, str) and kind in {'tool-call', 'tool-result', 'error', 'correction'},
                'unknown evidence event kind')
        fields = {'id', 'kind', 'summary'}
        if kind == 'tool-call':
            fields.add('tool')
            text_id(event['tool'])
            calls.add(ident)
        elif kind == 'tool-result':
            fields.update({'call_id', 'status'})
            require(isinstance(event['call_id'], str) and event['call_id'] in calls,
                    'tool result has no preceding call')
            require(isinstance(event['status'], str) and event['status'] in {'success', 'error', 'cancelled'},
                    'unknown tool result status')
            results.add(event['call_id'])
        if 'references' in event:
            fields.add('references')
            require(isinstance(event['references'], list) and event['references'] and
                    all(isinstance(ref, str) and ref in seen for ref in event['references']),
                    'evidence reference has no preceding event')
        require(set(event) == fields, 'unknown evidence event fields')
        summary = event['summary']
        require(isinstance(summary, str) and summary.strip() and len(summary) <= 4096,
                'evidence summary empty or oversized; minimize without truncating facts')
        strings = [value for value in event.values() if isinstance(value, str)] + event.get('references', [])
        require(not any(SENSITIVE.search(value) for value in strings), 'sensitive evidence blocked')
        seen.add(ident)
    require(calls <= results, 'complete evidence omitted a tool result')
