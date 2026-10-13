from __future__ import annotations
import base64
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
AUDITOR_PATH = Path(__file__).with_name('github_workflow_fleet_audit.py')
SPEC = importlib.util.spec_from_file_location('fleet_audit', AUDITOR_PATH)
fleet = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = fleet
SPEC.loader.exec_module(fleet)
TRANSFORM_PATH = Path(__file__).with_name('actions_queue_storm_fix.py')
TRANSFORM_SPEC = importlib.util.spec_from_file_location('fleet_transform_fixture', TRANSFORM_PATH)
transform = importlib.util.module_from_spec(TRANSFORM_SPEC)
assert TRANSFORM_SPEC.loader is not None
sys.modules[TRANSFORM_SPEC.name] = transform
TRANSFORM_SPEC.loader.exec_module(transform)

def content_payload(path: str, sha: str, text: str):
    raw = text.encode('utf-8')
    return {'type': 'file', 'path': path, 'sha': sha, 'size': len(raw), 'encoding': 'base64', 'content': base64.b64encode(raw).decode('ascii')}

class FakeClient:

    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls = []

    def get_json(self, path):
        self.calls.append(('GET', path))
        if path not in self.responses:
            raise AssertionError(f'unexpected GET {path}')
        return self.responses[path]

class AuditTests(unittest.TestCase):

    def test_parse_target_default_and_explicit_ref(self):
        self.assertEqual(fleet.parse_target('owner/repo', 'main'), fleet.Target('owner/repo', 'main'))
        self.assertEqual(fleet.parse_target('owner/repo@release/v1', 'main'), fleet.Target('owner/repo', 'release/v1'))

    def test_parse_target_rejects_invalid(self):
        with self.assertRaises(Exception):
            fleet.parse_target('just-a-repo', 'main')
        with self.assertRaises(Exception):
            fleet.parse_target('owner/repo@-danger', 'main')

    def test_contents_path_encodes_ref_without_path_escape(self):
        path = fleet.contents_path('owner/repo', '.github/workflows/folder name.yml', 'release/v1+hotfix')
        self.assertEqual(path, '/repos/owner/repo/contents/.github/workflows/folder%20name.yml?ref=release%2Fv1%2Bhotfix')

    def test_validate_path_rejects_traversal_and_non_workflow(self):
        for path in ('../secret.yml', '.github/workflows/../secret.yml', '.github/other/ci.yml', '.github/workflows/ci.txt', '/.github/workflows/ci.yml'):
            with self.subTest(path=path):
                with self.assertRaises(fleet.AuditError):
                    fleet.validate_workflow_path(path)

    def make_repository_fixture(self):
        repository = 'owner/repo'
        ref = 'main'
        target = fleet.Target(repository, ref)
        directory_path = fleet.contents_path(repository, '.github/workflows', ref)
        change_path = '.github/workflows/change.yml'
        clean_path = '.github/workflows/clean.yml'
        pr_only_path = '.github/workflows/pr-only.yaml'
        change_sha = 'a' * 40
        clean_sha = 'b' * 40
        pr_sha = 'c' * 40
        change_text = 'name: Change\non:\n  push:\n    paths:\n      - app/**\n  pull_request:\n    paths:\n      - app/**\n'
        clean_text = 'name: Clean\non:\n  push:\n    branches: [main]\n  pull_request:\n'
        pr_text = 'name: PR only\non:\n  pull_request:\n'
        entries = [{'type': 'file', 'path': change_path, 'sha': change_sha, 'size': len(change_text.encode())}, {'type': 'file', 'path': clean_path, 'sha': clean_sha, 'size': len(clean_text.encode())}, {'type': 'file', 'path': pr_only_path, 'sha': pr_sha, 'size': len(pr_text.encode())}, {'type': 'file', 'path': '.github/workflows/README.md', 'sha': 'd' * 40, 'size': 0}, {'type': 'dir', 'path': '.github/workflows/nested', 'sha': 'e' * 40, 'size': 0}]
        responses = {directory_path: entries, fleet.contents_path(repository, change_path, ref): content_payload(change_path, change_sha, change_text), fleet.contents_path(repository, clean_path, ref): content_payload(clean_path, clean_sha, clean_text), fleet.contents_path(repository, pr_only_path, ref): content_payload(pr_only_path, pr_sha, pr_text)}
        return (target, FakeClient(responses), change_text)

    def test_repository_audit_classifies_and_generates_patch(self):
        target, client, change_text = self.make_repository_fixture()
        audit, patch, receipt = fleet.audit_repository(client, target, transform, default_branch='main', include_push_only=False, max_files=10)
        self.assertEqual(audit.files_seen, 3)
        self.assertEqual(audit.changes_required, 1)
        self.assertEqual(audit.unsupported_requiring_review, 0)
        self.assertEqual(audit.status_counts, {'already_scoped': 1, 'changed': 1, 'no_push': 1})
        self.assertIn('branches: [main]', patch)
        self.assertIn('a/.github/workflows/change.yml', patch)
        self.assertNotIn('clean.yml', patch)
        self.assertEqual(receipt['patch_sha256'], hashlib.sha256(patch.encode()).hexdigest())
        self.assertEqual({method for method, _ in client.calls}, {'GET'})

    def test_listing_limit_fails_closed(self):
        target, client, _ = self.make_repository_fixture()
        with self.assertRaises(fleet.AuditError):
            fleet.list_workflow_items(client, target, max_files=2)

    def test_blob_sha_mismatch_fails_closed(self):
        path = '.github/workflows/ci.yml'
        payload = content_payload(path, 'b' * 40, 'on:\n  pull_request:\n')
        with self.assertRaises(fleet.AuditError):
            fleet.decode_content_payload(payload, expected_path=path, expected_sha='a' * 40, expected_size=payload['size'])

    def test_size_mismatch_fails_closed(self):
        path = '.github/workflows/ci.yml'
        payload = content_payload(path, 'a' * 40, 'on:\n  pull_request:\n')
        with self.assertRaises(fleet.AuditError):
            fleet.decode_content_payload(payload, expected_path=path, expected_sha='a' * 40, expected_size=payload['size'] + 1)

    def test_invalid_base64_fails_closed(self):
        path = '.github/workflows/ci.yml'
        payload = {'path': path, 'sha': 'a' * 40, 'size': 3, 'encoding': 'base64', 'content': '%%%'}
        with self.assertRaises(fleet.AuditError):
            fleet.decode_content_payload(payload, expected_path=path, expected_sha='a' * 40, expected_size=3)

    def test_main_writes_audit_files_and_uses_get_only(self):
        target, client, _ = self.make_repository_fixture()
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'out'
            code = fleet.main(['owner/repo', '--output-dir', str(out), '--transform-module', str(TRANSFORM_PATH)], client=client)
            self.assertEqual(code, 1)
            summary = json.loads((out / 'fleet-summary.json').read_text(encoding='utf-8'))
            self.assertEqual(summary['request_methods'], ['GET'])
            self.assertEqual(summary['totals']['changes_required'], 1)
            self.assertTrue((out / 'owner__repo__main.patch').is_file())
            self.assertTrue((out / 'owner__repo__main.json').is_file())
            self.assertEqual({method for method, _ in client.calls}, {'GET'})

    def test_empty_patch_is_hash_pinned(self):
        repository = 'owner/clean'
        ref = 'main'
        target = fleet.Target(repository, ref)
        path = '.github/workflows/ci.yml'
        text = 'on:\n  pull_request:\n'
        sha = 'f' * 40
        client = FakeClient({fleet.contents_path(repository, '.github/workflows', ref): [{'type': 'file', 'path': path, 'sha': sha, 'size': len(text.encode())}], fleet.contents_path(repository, path, ref): content_payload(path, sha, text)})
        audit, patch, _ = fleet.audit_repository(client, target, transform, default_branch='main', include_push_only=False, max_files=10)
        self.assertEqual(patch, '')
        self.assertEqual(audit.patch_sha256, hashlib.sha256(b'').hexdigest())
        self.assertEqual(audit.changes_required, 0)
if __name__ == '__main__':
    unittest.main(verbosity=2)
