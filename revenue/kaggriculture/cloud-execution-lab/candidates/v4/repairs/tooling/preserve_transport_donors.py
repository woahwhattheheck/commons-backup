# SPDX-License-Identifier: Apache-2.0
"""Attach three fixed donor blobs to canonical main, without executing them.

This is an explicitly invoked preservation tool, not a production module.
Requires an authorized repository GH_TOKEN. No import-time network or writes.
The historical checker/materializer donors are never executed by this tool.
"""
import base64
import hashlib
import json
import os
import urllib.error
import urllib.request

API = 'https://api.github.com/repos/woahwhattheheck/commons'
WORKSPACE = 'revenue/kaggriculture/cloud-execution-lab/candidates/v4'
TARGETS = {
    WORKSPACE + '/repairs/checker/check_v4_plumbing_stage2_scaffold_12a3.py': '12a3eb23dd1052a769baa16ce861890f21911e14',
    WORKSPACE + '/repairs/performance/fold_v4_fast_clone_a83de6.py': 'a83de6bfcc60c51c8bdc9106f8565c52eb5fe764',
    WORKSPACE + '/repairs/TRANSPORT-PRESERVATION-20260912.json': '442529fff610a4321908f0fa5f943d6179b368db',
}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def oid(value):
    require(type(value) is str and len(value) == 40 and all(c in '0123456789abcdef' for c in value), 'invalid object id')
    return value


def request(path, body=None, method=None):
    verb = method or ('GET' if body is None else 'POST')
    allowed = ((verb == 'GET' and (path == '/git/ref/heads/main' or any(path.startswith(p) for p in ('/git/commits/', '/git/trees/', '/git/blobs/'))))
               or (verb == 'POST' and path in ('/git/trees', '/git/commits'))
               or (verb == 'PATCH' and path == '/git/refs/heads/main' and body.get('force') is False))
    require(allowed, 'out-of-scope Git API operation')
    data = None if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(API + path, data=data, method=verb, headers={
        'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
        'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json',
        'X-GitHub-Api-Version': '2022-11-28'})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read(4_000_001)
    require(len(raw) <= 4_000_000, 'API response too large')
    return json.loads(raw)


class Store:
    def __init__(self, api):
        self.api = api
        self.trees = {}

    def blob(self, sha):
        obj = self.api('/git/blobs/' + oid(sha))
        require(obj.get('sha') == sha and obj.get('encoding') == 'base64', 'bad blob metadata')
        data = base64.b64decode(''.join(obj['content'].split()), validate=True)
        actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        require(len(data) == obj['size'] and actual == sha, 'blob hash/size mismatch')
        return data

    def tree(self, sha):
        if sha not in self.trees:
            obj = self.api('/git/trees/' + oid(sha))
            require(obj.get('sha') == sha and obj.get('truncated') is False, 'bad/truncated tree')
            entries = obj['tree']
            require(len({e['path'] for e in entries}) == len(entries), 'duplicate tree entry')
            self.trees[sha] = {e['path']: e for e in entries}
        return self.trees[sha]

    def lookup(self, tree_sha, path):
        parts = path.split('/')
        require(parts and all(p not in ('', '.', '..') for p in parts), 'invalid path')
        for index, part in enumerate(parts):
            entry = self.tree(tree_sha).get(part)
            if entry is None:
                return None
            if index == len(parts) - 1:
                return entry
            require(entry['type'] == 'tree' and entry['mode'] == '040000', 'non-directory path ancestor')
            tree_sha = entry['sha']
        raise RuntimeError('unreachable lookup')

    def head(self):
        ref = self.api('/git/ref/heads/main')
        require(ref.get('ref') == 'refs/heads/main' and ref['object']['type'] == 'commit', 'wrong canonical ref')
        sha = oid(ref['object']['sha'])
        commit = self.api('/git/commits/' + sha)
        require(commit.get('sha') == sha, 'commit identity mismatch')
        return sha, oid(commit['tree']['sha'])


def pending_entries(store, tree_sha):
    entries = []
    for path, sha in TARGETS.items():
        existing = store.lookup(tree_sha, path)
        if existing is not None:
            require(existing['mode'] == '100644' and existing['type'] == 'blob' and existing['sha'] == sha,
                    'refusing to overwrite different existing donor: ' + path)
        else:
            entries.append({'path': path, 'mode': '100644', 'type': 'blob', 'sha': sha})
    return entries


def preserve(api=request):
    store = Store(api)
    for sha in TARGETS.values():
        store.blob(sha)
    for attempt in range(1, 9):
        parent, base_tree = store.head()
        contract = store.lookup(base_tree, WORKSPACE + '/CANONICAL.json')
        require(contract is not None and contract['mode'] == '100644' and contract['type'] == 'blob', 'missing canonical contract')
        authority = json.loads(store.blob(contract['sha']))
        require(authority.get('canonical_branch') == 'main' and authority.get('workspace') == WORKSPACE, 'canonical contract changed')
        entries = pending_entries(store, base_tree)
        if not entries:
            return {'status': 'already-present', 'observed_main': parent, 'attempt': attempt, 'paths': TARGETS}
        created_tree = oid(api('/git/trees', {'base_tree': base_tree, 'tree': entries})['sha'])
        require(not pending_entries(store, created_tree), 'created tree missing donor entries')
        commit = api('/git/commits', {'message': 'v4: preserve exact checker scaffold and fast-clone donor (no activation)',
                                      'tree': created_tree, 'parents': [parent]})
        new_sha = oid(commit['sha'])
        require(commit['tree']['sha'] == created_tree and [p['sha'] for p in commit['parents']] == [parent], 'commit topology mismatch')
        try:
            moved = api('/git/refs/heads/main', {'sha': new_sha, 'force': False}, method='PATCH')
        except urllib.error.HTTPError as exc:
            if exc.code == 422 and store.head()[0] != parent:
                print(json.dumps({'status': 'retry-concurrent-main', 'attempt': attempt}))
                continue
            raise
        require(moved.get('ref') == 'refs/heads/main' and moved['object']['sha'] == new_sha, 'ref update mismatch')
        current, current_tree = store.head()
        require(not pending_entries(store, current_tree), 'latest main readback lacks preserved objects')
        return {'status': 'preserved', 'commit': new_sha, 'parent': parent, 'observed_main': current,
                'attempt': attempt, 'paths': TARGETS, 'production_activation': False}
    raise RuntimeError('main kept moving; stopped after eight non-force attempts')


if __name__ == '__main__':
    receipt = preserve()
    print(json.dumps(receipt, sort_keys=True))
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as stream:
            stream.write('# Canonical V4 donor preservation\n\n```json\n' + json.dumps(receipt, indent=2) + '\n```\n')
            stream.write('Only the three fixed repair paths were attached. No downloaded Python executed; no gameplay or production activation.\n')
