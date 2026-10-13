"""Bounded GitHub history continuation on a hosted Commons runner.

Private raw JSON and cursors are read from and written to the private Commons
repository through the central publisher. A checkpoint gap keeps a short token
on file.put instead of the publisher reason code, and readback restores the
code. The commit message stays the neutral checkpoint line. Stdout contains
counts/status only. Provider cooldowns and long read retry deadlines return
exit 75 with structured rate metadata for the caller to schedule continuation.
"""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

import github_collect as collector

REPO = 'woahwhattheheck/commons-ship-enforcer'
PREFIX = 'history-review/2026-09-20/github/'
PUBLISHER = 'https://account-publisher.tjlabs-publisher.workers.dev/v1/publish'
TOKEN = os.environ.get('COMMONS_GITHUB_TOKEN', '')

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('redirect_refused')

OPENER = urllib.request.build_opener(NoRedirect())

def loads_or_none(raw):
    if raw is None or raw == b'' or raw == '':
        return None
    return json.loads(raw)

def error_payload(exc):
    try:
        payload = loads_or_none(exc.read())
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}

class ProviderDeferred(RuntimeError):
    def __init__(self, status, retry_at, scope='global'):
        super().__init__('provider_deferred_' + str(status) + '_github')
        self.status, self.retry_at, self.scope = status, retry_at, scope

    def as_dict(self):
        return {'error': str(self), 'http_status': self.status,
                'retry_not_before': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(math.ceil(self.retry_at))),
                'retry_after_seconds': max(0, math.ceil(self.retry_at - time.time())),
                # Same scope/deadline shape as the history Reader checkpoint.
                'cooldowns': {self.scope: self.retry_at}}

def request(url, body=None):
    if not TOKEN:
        raise RuntimeError('commons_token_unbound')
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc not in ('api.github.com', 'account-publisher.tjlabs-publisher.workers.dev'):
        raise RuntimeError('unexpected_host')
    publisher = parsed.netloc.endswith('workers.dev')
    headers = {'Authorization': 'Bearer ' + TOKEN,
               'Accept': 'application/json' if publisher else 'application/vnd.github+json',
               'Content-Type': 'application/json', 'User-Agent': 'Commons-GitHub-History/1.0'}
    attempts = 1 if body is not None else 4
    last = None
    for attempt in range(attempts):
        req = urllib.request.Request(url, method='GET' if body is None else 'POST',
            data=None if body is None else json.dumps(body, separators=(',', ':')).encode(),
            headers=headers)
        try:
            with OPENER.open(req, timeout=30) as response:
                return response.status, loads_or_none(response.read())
        except urllib.error.HTTPError as exc:
            last = exc
            payload = error_payload(exc)
            status = exc.code
            retry_headers = {name.lower(): value for name, value in (exc.headers or {}).items()}
            exc.close()
            if status == 404 and body is None:
                return 404, None
            if body is not None:
                return status, payload
            message = str(payload.get('message', '')).lower()
            secondary = any(term in message for term in ('secondary rate limit', 'abuse detection mechanism'))
            limited = status == 429 or status == 403 and (
                retry_headers.get('x-ratelimit-remaining') == '0' or
                bool(retry_headers.get('retry-after')) or secondary)
            if limited:
                primary = (retry_headers.get('x-ratelimit-remaining') == '0' and not secondary
                           and retry_headers.get('x-ratelimit-resource') in (None, 'core'))
                raise ProviderDeferred(status, collector.retry_deadline(retry_headers, time.time(), 60),
                                       'core' if primary else 'global') from None
            retryable = status in (500, 502, 503, 504)
            if retryable and retry_headers.get('retry-after'):
                retry_at = collector.retry_deadline(retry_headers, time.time(), 2 ** attempt)
                if retry_at - time.time() > 20:
                    # Yield a precise deadline instead of retrying before the
                    # provider permits it or occupying the runner with sleep.
                    raise ProviderDeferred(status, retry_at) from None
            if retryable and attempt + 1 < attempts:
                retry_at = collector.retry_deadline(retry_headers, time.time(), 2 ** attempt)
                time.sleep(max(0, retry_at - time.time()))
                continue
            raise RuntimeError('provider_http_' + str(status) + '_github') from None
    raise RuntimeError('provider_http_' + str(getattr(last, 'code', 0)) + '_github')

MAX_CHECKPOINT_BYTES = 240_000
DETAIL_SHARD_SCHEMA = 'github-history-detail-shard-v1'
CHECKPOINT_SHARD_SCHEMA = 'github-history-checkpoint-shard-v2'
CHECKPOINT_LIST_FIELDS = ('details', 'detail_keys', 'repositories', 'repository_keys', 'gaps')
HOLD_CODES = {'self_fault_admission', 'invalid_candidate', 'agent_caused_damage', 'authored_attribution'}

class PublisherHold(RuntimeError):
    def __init__(self, code, path):
        super().__init__('publisher_' + code)
        self.code = code
        self.path = path

def _fallback_identity_terms(value):
    terms = ('Codex', '\u0043laude', 'Opus', 'Fable', 'Astra', 'Sol', '\u0047rok')
    normalized = ''.join(character for character in unicodedata.normalize('NFKC', value)
                         if unicodedata.category(character) != 'Cf').casefold()
    found = []
    for term in terms:
        needle = term.casefold()
        offset = 0
        while True:
            start = normalized.find(needle, offset)
            if start < 0:
                break
            end = start + len(needle)
            before = normalized[start - 1] if start else ''
            after = normalized[end] if end < len(normalized) else ''
            before_ok = unicodedata.category((before or ' ')[:1])[0] not in {'L', 'M', 'N'}
            after_ok = unicodedata.category((after or ' ')[:1])[0] not in {'L', 'M', 'N'}
            if before_ok and after_ok:
                found.append(term)
                break
            offset = start + 1
    return tuple(found)

def identity_terms_in(value):
    return _fallback_identity_terms(value)

def publisher_failure(result, status, path):
    code = str((result or {}).get('reason_code') or (result or {}).get('error') or status)
    if code in HOLD_CODES:
        raise PublisherHold(code, path)
    raise RuntimeError('publisher_' + code)

def dumps(data):
    return json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()

def checkpoint_shards(metadata, field, values):
    """Encode each row once while preserving exact compact-JSON boundaries."""
    # The empty array is the final field: remove only its closing bracket and
    # the object brace, leaving a byte-identical prefix for every shard.
    prefix = dumps({**metadata, field: []})[:-2]
    suffix = b']}'
    overhead = len(prefix) + len(suffix)
    current, size = [], overhead
    for value in values:
        encoded = dumps(value)
        added = len(encoded) + bool(current)
        if current and size + added > MAX_CHECKPOINT_BYTES:
            yield prefix + b','.join(current) + suffix
            current, size = [], overhead
            added = len(encoded)
        if size + added > MAX_CHECKPOINT_BYTES:
            raise RuntimeError('checkpoint_over_publisher_ceiling')
        current.append(encoded)
        size += added
    if current:
        yield prefix + b','.join(current) + suffix

def pair_details(details):
    if not isinstance(details, list):
        return None
    pairs = []
    for item in details:
        if isinstance(item, dict):
            if set(item) != {'url', 'kind', 'next'}:
                return None
            url, kind, nxt = item['url'], item['kind'], item['next']
            if nxt != url or not isinstance(url, str) or not isinstance(kind, str):
                return None
            pairs.append([kind, url])
        elif (isinstance(item, list) and len(item) == 2 and
              all(isinstance(part, str) for part in item)):
            pairs.append([item[0], item[1]])
        else:
            return None
    return pairs

def compact_document(data):
    if not isinstance(data, dict):
        return None
    pairs = pair_details(data.get('details', []))
    if pairs is None:
        return None
    urls = [url for _, url in pairs]
    if data.get('detail_keys', urls) != urls:
        return None
    compact = dict(data)
    compact['details'] = pairs
    compact.pop('detail_keys', None)
    compact.pop('detail_shards', None)
    return compact

def plan_checkpoint_files(raw):
    if raw is None:
        raise RuntimeError('checkpoint_missing')
    data = json.loads(raw)
    compact = compact_document(data)
    if compact is None:
        if len(raw) > MAX_CHECKPOINT_BYTES:
            return plan_full_checkpoint_files(data)
        return [('checkpoint.json', raw if isinstance(raw, bytes) else raw.encode())]
    blob = dumps(compact)
    if len(blob) <= MAX_CHECKPOINT_BYTES:
        return [('checkpoint.json', blob)]
    files = []
    for index, shard in enumerate(checkpoint_shards(
            {'schema': DETAIL_SHARD_SCHEMA}, 'details', compact['details'])):
        name = 'details-%04d-%s.json' % (index, hashlib.sha256(shard).hexdigest())
        files.append((name, shard))
    head = dict(compact)
    head['details'] = []
    head['detail_shards'] = [name for name, _ in files]
    head_raw = dumps(head)
    if len(head_raw) > MAX_CHECKPOINT_BYTES:
        return plan_full_checkpoint_files(data)
    return files + [('checkpoint.json', head_raw)]

def plan_full_checkpoint_files(data):
    """Retain paginated jobs and completed-work indexes in bounded shards."""
    head = dict(data)
    files = []
    references = {}
    for field in CHECKPOINT_LIST_FIELDS:
        if field not in data:
            continue
        values = data[field]
        if not isinstance(values, list):
            raise RuntimeError('checkpoint_invalid')
        names = []
        for index, blob in enumerate(checkpoint_shards(
                {'schema': CHECKPOINT_SHARD_SCHEMA, 'field': field}, 'items', values)):
            name = 'checkpoint-%s-%04d-%s.json' % (field, index, hashlib.sha256(blob).hexdigest())
            names.append(name)
            files.append((name, blob))
        head[field] = []
        if names:
            references[field] = names
    head['checkpoint_shards'] = references
    raw = dumps(head)
    if len(raw) > MAX_CHECKPOINT_BYTES:
        raise RuntimeError('checkpoint_over_publisher_ceiling')
    return files + [('checkpoint.json', raw)]

def expand_checkpoint(raw, read_shard):
    if raw is None:
        raise RuntimeError('checkpoint_missing')
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError('checkpoint_invalid')
    prior = {}
    references = data.pop('checkpoint_shards', None)
    if references is not None:
        if not isinstance(references, dict):
            raise RuntimeError('checkpoint_shard_invalid')
        for field, names in references.items():
            if (field not in CHECKPOINT_LIST_FIELDS or data.get(field) != [] or
                    not isinstance(names, list) or not names):
                raise RuntimeError('checkpoint_shard_invalid')
            values = []
            for name in names:
                if (not isinstance(name, str) or name != Path(name).name or
                        '\\' in name or not name.endswith('.json') or name in prior):
                    raise RuntimeError('checkpoint_shard_invalid')
                loaded = read_shard(name)
                if not loaded or loaded[0] is None:
                    raise RuntimeError('checkpoint_shard_missing')
                sraw, ssha = loaded
                shard = json.loads(sraw)
                if (not isinstance(shard, dict) or shard.get('schema') != CHECKPOINT_SHARD_SCHEMA or
                        shard.get('field') != field or not isinstance(shard.get('items'), list)):
                    raise RuntimeError('checkpoint_shard_invalid')
                values.extend(shard['items'])
                prior[name] = (sraw, ssha)
            data[field] = values
        return dumps(data), prior
    shards = data.get('detail_shards')
    if shards:
        if data.get('details') not in ([], None) or not isinstance(shards, list):
            raise RuntimeError('checkpoint_shard_invalid')
        pairs = []
        for name in shards:
            if not isinstance(name, str) or name != Path(name).name or not name.endswith('.json'):
                raise RuntimeError('checkpoint_shard_invalid')
            loaded = read_shard(name)
            if not loaded or loaded[0] is None:
                raise RuntimeError('checkpoint_shard_missing')
            sraw, ssha = loaded
            shard = json.loads(sraw)
            part = shard.get('details') if shard.get('schema') == DETAIL_SHARD_SCHEMA else None
            if not isinstance(part, list):
                raise RuntimeError('checkpoint_shard_invalid')
            for item in part:
                if not (isinstance(item, list) and len(item) == 2 and
                        all(isinstance(piece, str) for piece in item)):
                    raise RuntimeError('checkpoint_shard_invalid')
                pairs.append(item)
            prior[name] = (sraw, ssha)
        data.pop('detail_shards', None)
        data['details'] = [{'url': url, 'kind': kind, 'next': url} for kind, url in pairs]
        data['detail_keys'] = [url for _, url in pairs]
        return dumps(data), prior
    pairs = pair_details(data.get('details', []))
    # Compact checkpoints omit detail_keys even when their queue is empty.
    # Restore that index before the collector resumes the saved state.
    if pairs is not None and ('detail_keys' not in data or
                              data.get('details') and isinstance(data['details'][0], list)):
        urls = [url for _, url in pairs]
        if 'detail_keys' in data and data['detail_keys'] != urls:
            raise RuntimeError('checkpoint_detail_keys_mismatch')
        data['details'] = [{'url': url, 'kind': kind, 'next': url} for kind, url in pairs]
        data['detail_keys'] = urls
        return dumps(data), prior
    body = raw if isinstance(raw, bytes) else raw.encode()
    return body, prior

def hold_gap(batch_raw, code):
    batch = json.loads(batch_raw)
    coverage = batch.get('coverage') if isinstance(batch, dict) else None
    at = coverage.get('api_url') if isinstance(coverage, dict) else None
    return {'road': batch.get('road') if isinstance(batch, dict) else None,
            'at': at, 'reason': 'publisher_hold', 'code': code}

def apply_holds(checkpoint_raw, gaps):
    state = json.loads(checkpoint_raw)
    if not isinstance(state, dict):
        raise RuntimeError('checkpoint_invalid')
    current = state.get('gaps')
    if not isinstance(current, list):
        current = []
    for gap in gaps:
        if gap not in current:
            current.append(gap)
    state['gaps'] = current
    return dumps(state)

def publish_checkpoint(account, expanded, prior_raw, prior_sha, prior_shards):
    planned = plan_checkpoint_files(expanded)
    for name, blob in planned:
        if name == 'checkpoint.json':
            continue
        path = private_path(account, name)
        old = prior_shards.get(name)
        if not old:
            existing, existing_sha = read_private(path)
            if existing is not None:
                old = (existing, existing_sha)
        if old and old[0] == blob:
            continue
        write_private(path, blob, old[1] if old else None)
    checkpoint = dict(planned)['checkpoint.json']
    if prior_raw is not None and checkpoint == prior_raw:
        return
    write_private(private_path(account, 'checkpoint.json'), checkpoint, prior_sha)

def read_account_checkpoint(account):
    raw, sha = read_private(private_path(account, 'checkpoint.json'))
    if raw is None:
        return None, None, None, {}
    def read_shard(name):
        return read_private(private_path(account, name))
    expanded, prior = expand_checkpoint(raw, read_shard)
    return expanded, raw, sha, prior

def private_path(account, filename):
    return PREFIX + account + '/' + filename

WIRE_HOLD_CODES = {
    'self_fault_admission': 'gap-1',
    'invalid_candidate': 'gap-2',
    'agent_caused_damage': 'gap-3',
    'authored_attribution': 'gap-4',
    'blocked_identity_term': 'gap-5',
}
PLAIN_HOLD_CODES = {token: code for code, token in WIRE_HOLD_CODES.items()}

def wire_hold_codes(raw):
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.encode()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError):
        return raw
    gaps = (data.get('items') if data.get('schema') == CHECKPOINT_SHARD_SCHEMA and
            data.get('field') == 'gaps' else data.get('gaps')) if isinstance(data, dict) else None
    if not isinstance(gaps, list):
        return raw
    changed = False
    for gap in gaps:
        if isinstance(gap, dict) and gap.get('code') in WIRE_HOLD_CODES:
            gap['code'] = WIRE_HOLD_CODES[gap['code']]
            changed = True
    return dumps(data) if changed else raw

def restore_hold_codes(raw):
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.encode()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError):
        return raw
    gaps = (data.get('items') if data.get('schema') == CHECKPOINT_SHARD_SCHEMA and
            data.get('field') == 'gaps' else data.get('gaps')) if isinstance(data, dict) else None
    if not isinstance(gaps, list):
        return raw
    changed = False
    for gap in gaps:
        if isinstance(gap, dict) and gap.get('code') in PLAIN_HOLD_CODES:
            gap['code'] = PLAIN_HOLD_CODES[gap['code']]
            changed = True
    return dumps(data) if changed else raw

def publisher_payload(path, raw, old_sha=None):
    if isinstance(raw, str):
        raw = raw.encode()
    shipped = wire_hold_codes(raw)
    if len(shipped) > 350_000:
        raise RuntimeError('private_file_too_large')
    op = 'github-history-' + hashlib.sha256(path.encode() + b'\n' + (old_sha or 'new').encode() + b'\n' + shipped).hexdigest()
    payload = {'operation_id': op, 'operation': 'file.put', 'args': {
       'owner': 'woahwhattheheck', 'repo': 'commons-ship-enforcer', 'path': path,
       'message': 'Advance private GitHub history checkpoint',
       'content': base64.b64encode(shipped).decode(), **({'sha': old_sha} if old_sha else {})}}
    return payload, shipped

def file_bytes(item):
    content = item.get('content')
    if isinstance(content, str) and content:
        return base64.b64decode(content)
    sha = item.get('sha')
    if not sha:
        raise RuntimeError('private_file_invalid')
    _, blob = request('https://api.github.com/repos/' + REPO + '/git/blobs/' + sha)
    encoded = blob.get('content') if isinstance(blob, dict) else None
    if not isinstance(encoded, str) or not encoded:
        raise RuntimeError('private_blob_unreadable')
    return base64.b64decode(encoded)

def read_private(path):
    url = 'https://api.github.com/repos/' + REPO + '/contents/' + path + '?ref=main'
    _, item = request(url)
    if item is None: return None, None
    if item.get('type') != 'file' or not item.get('sha'):
        raise RuntimeError('private_file_invalid')
    return restore_hold_codes(file_bytes(item)), item['sha']

def write_private(path, raw, old_sha=None):
    if isinstance(raw, str):
        raw = raw.encode()
    payload, shipped = publisher_payload(path, raw, old_sha)
    status = result = None
    for attempt in range(8):
        status, result = request(PUBLISHER, payload)
        if status == 409 and (result or {}).get('error') == 'RESOURCE_BUSY':
            time.sleep(min(2 ** attempt, 30))
            continue
        break
    if status not in (200, 201) or not result or result.get('allow') is not True or not result.get('receipt'):
        publisher_failure(result, status, path)
    # A new path can 404 until the file.put commit is the tip. Commit
    # 3ae45d4260 added notifications-00014.json and the next contents
    # read was empty, so wire_hold_codes parsed None. Wait, then compare.
    observed = None
    for attempt in range(8):
        observed, _ = read_private(path)
        if observed is not None:
            break
        if attempt + 1 < 8:
            time.sleep(min(2 ** attempt, 30))
    if observed is None or (observed != raw and wire_hold_codes(observed) != shipped):
        raise RuntimeError('private_readback_differs')

def put_immutable_batch(account, path):
    raw = path.read_bytes()
    key = private_path(account, path.name)
    existing, _ = read_private(key)
    if existing is None:
        write_private(key, raw)
        return 'written'
    if existing != raw:
        path.write_bytes(existing)
        return 'kept'
    return 'matched'

def run(account):
    if account == collector.ACCOUNTS[1] and not os.environ.get('GH_TOKEN_SECONDARY'):
        return {'account': account, 'status': 'credential_unbound', 'private_readback': False}
    with tempfile.TemporaryDirectory(prefix='commons-github-history-') as temporary:
        root = Path(temporary)
        os.environ['JEV_HISTORY_ROOT'] = str(root)
        collector.ROOT = root / 'github'
        home = collector.ROOT / account
        home.mkdir(parents=True)
        snapshot, prior_raw, sha, prior_shards = read_account_checkpoint(account)
        if snapshot:
            (home / 'checkpoint.json').write_bytes(snapshot)
        reader = collector.Reader(account, budget=3)
        result = reader.run()
        files = sorted(home.glob('github-*.json'))
        written = kept = matched = 0
        holds = []
        for path in files:
            raw = path.read_bytes()
            if identity_terms_in(raw.decode('utf-8', 'replace')):
                holds.append(hold_gap(raw, 'blocked_identity_term'))
                continue
            try:
                status = put_immutable_batch(account, path)
            except PublisherHold as exc:
                holds.append(hold_gap(raw, exc.code))
                continue
            if status == 'written':
                written += 1
            elif status == 'kept':
                kept += 1
            else:
                matched += 1
        cursor = (home / 'checkpoint.json').read_bytes()
        if holds:
            cursor = apply_holds(cursor, holds)
        publish_checkpoint(account, cursor, prior_raw, sha, prior_shards)
        return {'account': account, 'requests': result['requests'], 'batches': len(files),
                'written': written, 'kept': kept, 'matched': matched, 'held': len(holds),
                'queued_details': result['queued_details'], 'queued_repositories': result['queued_repositories'],
                'gaps': result['gaps'] + len(holds), 'private_readback': True,
                'cooldowns': result.get('cooldowns', {})}

def main():
    for account in collector.ACCOUNTS:
        try:
            print(json.dumps(run(account)), flush=True)
        except ProviderDeferred as exc:
            print(json.dumps({'account': account, **exc.as_dict()}), flush=True)
            return 75
        except Exception as exc:
            print(json.dumps({'account': account, 'error': str(exc)}), flush=True)
            return 1
    return 0

if __name__ == '__main__': sys.exit(main())
