"""Private, scope-bound cache of normalized pages; never a coverage checkpoint."""
from datetime import datetime, timezone
import json
from common import require, SENSITIVE
from maintenance import atomic_write, digest, read


def safe_values(value):
    if isinstance(value, str):
        require(not SENSITIVE.search(value), 'sensitive progress value blocked')
    elif isinstance(value, dict):
        for key, item in value.items():
            safe_values(key)
            safe_values(item)
    elif isinstance(value, list):
        for item in value:
            safe_values(item)
    else:
        require(value is None or type(value) in {bool, int, float}, 'unknown progress value')


class Progress:
    def __init__(self, path, binding):
        self.path = path
        self.hits = self.added = 0
        self.binding = binding
        if path.exists():
            document = read(path)
            require(set(document) == {'version', 'binding', 'pages', 'digest', 'created_at', 'updated_at'} and
                    document['version'] == 1, 'unknown progress contract')
            require(document['binding'] == binding, 'progress window/source/state binding changed; do not reuse')
            require(document['digest'] == digest({k: v for k, v in document.items() if k != 'digest'}),
                    'progress integrity mismatch; do not reuse')
            require(isinstance(document['pages'], dict), 'invalid progress pages')
            safe_values(document)
            self.document = document
        else:
            now = datetime.now(timezone.utc).isoformat()
            self.document = dict(version=1, binding=binding, pages={}, created_at=now, updated_at=now)

    def get(self, method, params, context):
        key = digest([method, params, context])
        page = self.document['pages'].get(key)
        if page is not None:
            require(isinstance(page, dict) and set(page) == {'data', 'nextCursor'}, 'unknown cached page')
            self.hits += 1
        return page

    def save(self, method, params, context, data, next_cursor):
        safe_values(data)
        safe_values(next_cursor)
        key = digest([method, params, context])
        require(key not in self.document['pages'], 'cached page changed; do not replace')
        candidate = {**self.document,
                     'pages': {**self.document['pages'], key: dict(data=data, nextCursor=next_cursor)},
                     'updated_at': datetime.now(timezone.utc).isoformat()}
        candidate['digest'] = digest({k: v for k, v in candidate.items() if k != 'digest'})
        atomic_write(self.path, candidate)
        self.document = candidate
        self.added += 1

    def usage(self):
        return dict(path=str(self.path), saved_pages=len(self.document['pages']),
                    cached_pages_reused=self.hits, new_pages_saved=self.added,
                    normalized_only=True, checkpoint_written=False)
