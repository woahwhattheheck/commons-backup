# SPDX-License-Identifier: Apache-2.0
"""Offline tests. Run unittest discovery from this directory; no token required."""
import base64
import hashlib
import io
import json
import unittest
import urllib.error
from unittest.mock import patch
import preserve_transport_donors as p


def sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


class Fake:
    def __init__(self, race=0, wrong_contract=False):
        self.blobs = {}
        self.trees = {}
        self.commits = {}
        self.calls = []
        self.race = race
        self.count = 0
        self.paths = {}
        contract = {'canonical_branch': 'other' if wrong_contract else 'main', 'workspace': p.WORKSPACE}
        self.paths[p.WORKSPACE + '/CANONICAL.json'] = ('100644', self.add_blob(json.dumps(contract).encode()))
        self.advance()

    def add_blob(self, data):
        key = sha(data)
        self.blobs[key] = data
        return key

    def object_id(self, obj):
        return hashlib.sha1(json.dumps(obj, sort_keys=True).encode()).hexdigest()

    def tree_of(self, paths):
        nested = {}
        for path, spec in paths.items():
            parts = path.split('/')
            current = nested
            for part in parts[:-1]:
                current = current.setdefault(part, {})
            current[parts[-1]] = spec
        def make(node):
            entries = []
            for name, value in sorted(node.items()):
                if isinstance(value, dict):
                    entries.append({'path': name, 'type': 'tree', 'mode': '040000', 'sha': make(value)})
                else:
                    entries.append({'path': name, 'type': 'blob', 'mode': value[0], 'sha': value[1]})
            key = self.object_id(entries)
            self.trees[key] = {'sha': key, 'tree': entries, 'truncated': False}
            return key
        return make(nested)

    def flatten(self, root, prefix=''):
        result = {}
        for entry in self.trees[root]['tree']:
            path = prefix + entry['path']
            if entry['type'] == 'tree':
                result.update(self.flatten(entry['sha'], path + '/'))
            else:
                result[path] = (entry['mode'], entry['sha'])
        return result

    def advance(self):
        tree = self.tree_of(self.paths)
        self.count += 1
        key = self.object_id([tree, self.count])
        self.commits[key] = {'sha': key, 'tree': {'sha': tree}, 'parents': []}
        self.current = key

    def __call__(self, path, body=None, method=None):
        verb = method or ('GET' if body is None else 'POST')
        self.calls.append((verb, path, body))
        if path == '/git/ref/heads/main':
            return {'ref': 'refs/heads/main', 'object': {'type': 'commit', 'sha': self.current}}
        if verb == 'GET' and path.startswith('/git/commits/'):
            return self.commits[path.rsplit('/', 1)[1]]
        if verb == 'GET' and path.startswith('/git/trees/'):
            return self.trees[path.rsplit('/', 1)[1]]
        if verb == 'GET' and path.startswith('/git/blobs/'):
            key = path.rsplit('/', 1)[1]
            data = self.blobs[key]
            return {'sha': key, 'encoding': 'base64', 'size': len(data), 'content': base64.b64encode(data).decode()}
        if verb == 'POST' and path == '/git/trees':
            paths = self.flatten(body['base_tree'])
            for entry in body['tree']:
                paths[entry['path']] = (entry['mode'], entry['sha'])
            return {'sha': self.tree_of(paths)}
        if verb == 'POST' and path == '/git/commits':
            key = self.object_id(body)
            obj = {'sha': key, 'tree': {'sha': body['tree']}, 'parents': [{'sha': s} for s in body['parents']]}
            self.commits[key] = obj
            return obj
        if verb == 'PATCH' and path == '/git/refs/heads/main':
            if self.race:
                self.race -= 1
                self.paths['peer-' + str(self.count) + '.txt'] = ('100644', self.add_blob(b'peer'))
                self.advance()
            target = self.commits[body['sha']]
            if target['parents'] != [{'sha': self.current}]:
                raise urllib.error.HTTPError('fake', 422, 'not fast forward', {}, io.BytesIO(b''))
            if body['force'] is not False:
                raise AssertionError('force update attempted')
            self.current = target['sha']
            self.paths = self.flatten(target['tree']['sha'])
            return {'ref': 'refs/heads/main', 'object': {'sha': self.current}}
        raise AssertionError((verb, path))


class Tests(unittest.TestCase):
    def setUp(self):
        self.fake = Fake()
        self.targets = {p.WORKSPACE + '/repairs/checker/a.py': self.fake.add_blob(b'# scaffold\n'),
                        p.WORKSPACE + '/repairs/performance/b.py': self.fake.add_blob(b'# donor\n'),
                        p.WORKSPACE + '/repairs/receipt.json': self.fake.add_blob(b'{}\n')}
        self.patch = patch.object(p, 'TARGETS', self.targets)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_atomic_three_path_addition(self):
        original = dict(self.fake.paths)
        result = p.preserve(self.fake)
        self.assertEqual(result['status'], 'preserved')
        self.assertEqual(set(self.fake.paths) - set(original), set(self.targets))
        self.assertTrue(all(self.fake.paths[k] == v for k, v in original.items()))

    def test_idempotent(self):
        p.preserve(self.fake)
        self.fake.calls.clear()
        self.assertEqual(p.preserve(self.fake)['status'], 'already-present')
        self.assertFalse(any(verb != 'GET' for verb, _, _ in self.fake.calls))

    def test_concurrent_writers_preserved(self):
        self.fake.race = 2
        result = p.preserve(self.fake)
        self.assertEqual(result['attempt'], 3)
        self.assertEqual(len([name for name in self.fake.paths if name.startswith('peer-')]), 2)

    def test_bounded_retries(self):
        self.fake.race = 99
        with self.assertRaisesRegex(RuntimeError, 'eight'):
            p.preserve(self.fake)
        self.assertEqual(len([1 for verb, _, _ in self.fake.calls if verb == 'PATCH']), 8)
        self.assertTrue(set(self.targets).isdisjoint(self.fake.paths))

    def test_different_existing_file_refused(self):
        path = next(iter(self.targets))
        self.fake.paths[path] = ('100644', self.fake.add_blob(b'newer peer work'))
        self.fake.advance()
        with self.assertRaisesRegex(RuntimeError, 'overwrite'):
            p.preserve(self.fake)
        self.assertFalse(any(verb != 'GET' for verb, _, _ in self.fake.calls))

    def test_symlink_file_refused(self):
        path = next(iter(self.targets))
        self.fake.paths[path] = ('120000', self.targets[path])
        self.fake.advance()
        with self.assertRaisesRegex(RuntimeError, 'overwrite'):
            p.preserve(self.fake)

    def test_nondirectory_ancestor_refused(self):
        self.fake.paths[p.WORKSPACE + '/repairs'] = ('120000', self.fake.add_blob(b'elsewhere'))
        self.fake.advance()
        with self.assertRaisesRegex(RuntimeError, 'ancestor'):
            p.preserve(self.fake)

    def test_changed_canonical_contract_refused(self):
        path = p.WORKSPACE + '/CANONICAL.json'
        self.fake.paths[path] = ('100644', self.fake.add_blob(b'{"canonical_branch":"other"}'))
        self.fake.advance()
        with self.assertRaisesRegex(RuntimeError, 'contract changed'):
            p.preserve(self.fake)

    def test_truncated_tree_refused(self):
        root = self.fake.commits[self.fake.current]['tree']['sha']
        self.fake.trees[root]['truncated'] = True
        with self.assertRaisesRegex(RuntimeError, 'truncated'):
            p.preserve(self.fake)

    def test_bad_blob_content_refused(self):
        self.fake.blobs[next(iter(self.targets.values()))] = b'wrong bytes'
        with self.assertRaisesRegex(RuntimeError, 'hash/size mismatch'):
            p.preserve(self.fake)
        self.assertFalse(any(verb != 'GET' for verb, _, _ in self.fake.calls))

    def test_matching_existing_subset_not_rewritten(self):
        path = next(iter(self.targets))
        self.fake.paths[path] = ('100644', self.targets[path])
        self.fake.advance()
        p.preserve(self.fake)
        edits = [body['tree'] for verb, path, body in self.fake.calls if verb == 'POST' and path == '/git/trees']
        self.assertEqual(len(edits[0]), 2)

    def test_out_of_scope_api_rejected_before_auth(self):
        with self.assertRaisesRegex(RuntimeError, 'out-of-scope'):
            p.request('/git/refs/heads/other', {'sha': 'a' * 40, 'force': False}, method='PATCH')
        with self.assertRaisesRegex(RuntimeError, 'out-of-scope'):
            p.request('/git/refs/heads/main', {'sha': 'a' * 40, 'force': True}, method='PATCH')


if __name__ == '__main__':
    unittest.main()
