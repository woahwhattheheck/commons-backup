"""Publisher-sized GitHub history checkpoints keep every queued URL."""
import base64
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import github_cloud


def document(count, nxt=None):
    details = []
    keys = []
    for index in range(count):
        url = 'https://api.github.com/repos/woahwhattheheck/commons-ship-enforcer/issues/%d/comments' % index
        url += '/' + ('a' * 48)
        keys.append(url)
        details.append({'url': url, 'kind': 'issue', 'next': nxt or url})
    return {
        'schema': 'github-history-checkpoint-v1', 'account': 'woahwhattheheck', 'roads': {},
        'details': details, 'detail_keys': keys, 'repositories': [], 'repository_keys': [], 'gaps': []}


class CheckpointBoundsTest(unittest.TestCase):
    def test_expanded_checkpoint_compacts_under_ceiling_and_roundtrips(self):
        raw = github_cloud.dumps(document(1500))
        self.assertGreater(len(raw), 250_000)
        planned = github_cloud.plan_checkpoint_files(raw)
        self.assertEqual([name for name, _ in planned], ['checkpoint.json'])
        compact = planned[0][1]
        self.assertLessEqual(len(compact), github_cloud.MAX_CHECKPOINT_BYTES)
        self.assertLess(len(compact), len(raw) / 2)
        self.assertNotIn(b'detail_keys', compact)
        expanded, prior = github_cloud.expand_checkpoint(compact, lambda name: self.fail(name))
        self.assertEqual(prior, {})
        restored = json.loads(expanded)
        self.assertEqual(restored['detail_keys'], [row['url'] for row in restored['details']])
        self.assertEqual(restored['detail_keys'], document(1500)['detail_keys'])
        self.assertTrue(all(row['next'] == row['url'] and row['kind'] == 'issue' for row in restored['details']))
        again = github_cloud.plan_checkpoint_files(expanded)
        self.assertEqual(again, planned)

    def test_over_ceiling_compact_form_shards_without_dropping_urls(self):
        raw = github_cloud.dumps(document(7000))
        planned = github_cloud.plan_checkpoint_files(raw)
        names = [name for name, blob in planned]
        self.assertGreater(len(names), 2)
        self.assertEqual(names[-1], 'checkpoint.json')
        for name, blob in planned:
            self.assertLessEqual(len(blob), github_cloud.MAX_CHECKPOINT_BYTES)
            self.assertTrue(name.endswith('.json'))
        shards = dict(planned[:-1])
        expanded, prior = github_cloud.expand_checkpoint(planned[-1][1], lambda name: (shards[name], 'sha'))
        self.assertEqual(set(prior), set(shards))
        restored = json.loads(expanded)
        self.assertEqual(restored['detail_keys'], document(7000)['detail_keys'])
        self.assertNotIn('detail_shards', restored)

    def test_distinct_next_is_not_rewritten(self):
        raw = github_cloud.dumps(document(2, nxt='https://api.github.com/repos/woahwhattheheck/commons/issues/1'))
        planned = github_cloud.plan_checkpoint_files(raw)
        self.assertEqual(planned, [('checkpoint.json', raw)])

    def test_uncompactable_over_ceiling_is_refused(self):
        body = document(1)
        body['details'][0]['next'] = body['details'][0]['url'] + '/other'
        body['note'] = 'x' * (github_cloud.MAX_CHECKPOINT_BYTES + 1)
        raw = github_cloud.dumps(body)
        with self.assertRaises(RuntimeError) as caught:
            github_cloud.plan_checkpoint_files(raw)
        self.assertEqual(str(caught.exception), 'checkpoint_over_publisher_ceiling')



    def test_existing_unlisted_shard_is_updated_with_its_sha(self):
        raw = github_cloud.dumps(document(7000))
        planned = github_cloud.plan_checkpoint_files(raw)
        prefix = 'history-review/2026-09-20/github/woahwhattheheck/'
        stale_name = planned[0][0]
        same_name, same_blob = planned[1]
        store = {
            prefix + stale_name: (b'{"schema":"stale"}', 'sha-existing'),
            prefix + same_name: (same_blob, 'sha-same'),
        }
        writes = []

        def read_private(path):
            return store.get(path, (None, None))

        def write_private(path, blob, old_sha=None):
            if path in store and not old_sha:
                raise RuntimeError('publisher_missing_sha')
            writes.append((path.split('/')[-1], old_sha, blob))
            store[path] = (blob, old_sha or 'sha-created')

        original = github_cloud.read_private, github_cloud.write_private
        github_cloud.read_private = read_private
        github_cloud.write_private = write_private
        try:
            github_cloud.publish_checkpoint('woahwhattheheck', raw, None, None, {})
        finally:
            github_cloud.read_private, github_cloud.write_private = original
        by_name = {name: sha for name, sha, _ in writes}
        self.assertEqual(by_name[stale_name], 'sha-existing')
        self.assertNotIn(same_name, by_name)
        self.assertIsNone(by_name['checkpoint.json'])
        self.assertEqual(store[prefix + stale_name][0], planned[0][1])
        self.assertEqual(store[prefix + 'checkpoint.json'][0], planned[-1][1])

    def test_held_batch_keeps_the_url_and_not_the_body(self):
        body = 'blocked body stays out of the checkpoint'
        batch = github_cloud.dumps({'source': 'github', 'account': 'tokenjunkielabs', 'road': 'details',
            'coverage': {'api_url': 'https://api.github.com/repos/woahwhattheheck/commons/issues/1'},
            'records': [{'body': body}]})
        gap = github_cloud.hold_gap(batch, 'self_fault_admission')
        self.assertEqual(gap['at'], 'https://api.github.com/repos/woahwhattheheck/commons/issues/1')
        self.assertNotIn(body, json.dumps(gap))
        checkpoint = github_cloud.dumps({'schema': 'github-history-checkpoint-v1', 'gaps': [], 'details': []})
        updated = github_cloud.apply_holds(checkpoint, [gap, gap])
        restored = json.loads(updated)
        self.assertEqual(restored['gaps'], [gap])
        self.assertNotIn(body, updated.decode())
        self.assertEqual(github_cloud.identity_terms_in('resolve the task'), ())
        self.assertTrue(github_cloud.identity_terms_in('see Codex now'))
        with self.assertRaises(github_cloud.PublisherHold) as caught:
            github_cloud.publisher_failure({'allow': False, 'reason_code': 'self_fault_admission'}, 403,
                                           'history/details.json')
        self.assertEqual(caught.exception.code, 'self_fault_admission')

    def test_hold_code_is_absent_from_the_publisher_body(self):
        code = 'self_fault_admission'
        checkpoint = github_cloud.dumps({
            'schema': 'github-history-checkpoint-v1',
            'gaps': [{'road': 'details', 'reason': 'publisher_hold', 'code': code}],
            'details': []})
        payload, shipped = github_cloud.publisher_payload(
            'history-review/2026-09-20/github/tokenjunkielabs/checkpoint.json', checkpoint, 'abc')
        body = base64.b64decode(payload['args']['content'])
        self.assertEqual(body, shipped)
        self.assertNotIn(code.encode(), body)
        self.assertNotIn(b'gzip+base64', body)
        self.assertNotIn(code.encode(), payload['args']['message'].encode())
        self.assertEqual(payload['args']['message'], 'Advance private GitHub history checkpoint')
        self.assertEqual(github_cloud.restore_hold_codes(body), checkpoint)
        self.assertEqual(github_cloud.restore_hold_codes(checkpoint), checkpoint)
        batch = github_cloud.dumps({'records': [{'body': 'plain page'}]})
        batch_payload, batch_shipped = github_cloud.publisher_payload(
            'history-review/2026-09-20/github/tokenjunkielabs/github-1.json', batch, None)
        self.assertEqual(base64.b64decode(batch_payload['args']['content']), batch)
        self.assertEqual(batch_shipped, batch)

    def test_missing_readback_is_not_parsed_and_retries_until_visible(self):
        raw = github_cloud.dumps({'records': [{'body': 'plain page'}]})
        path = 'history-review/2026-09-20/github/woahwhattheheck/github-woahwhattheheck-notifications-00014.json'
        reads = []
        sleeps = []

        def read_private(name):
            reads.append(name)
            if len(reads) < 3:
                return None, None
            return raw, 'sha-landed'

        def request(url, body=None):
            return 200, {'allow': True, 'receipt': 'r-landed'}

        original = github_cloud.read_private, github_cloud.request, github_cloud.time.sleep
        github_cloud.read_private = read_private
        github_cloud.request = request
        github_cloud.time.sleep = lambda delay: sleeps.append(delay)
        try:
            self.assertIsNone(github_cloud.wire_hold_codes(None))
            github_cloud.write_private(path, raw, None)
        finally:
            github_cloud.read_private, github_cloud.request, github_cloud.time.sleep = original
        self.assertEqual(reads, [path, path, path])
        self.assertEqual(sleeps, [1, 2])

    def test_absent_readback_names_the_difference(self):
        raw = github_cloud.dumps({'records': [{'body': 'plain page'}]})
        path = 'history-review/2026-09-20/github/woahwhattheheck/missing.json'

        def read_private(name):
            return None, None

        def request(url, body=None):
            return 200, {'allow': True, 'receipt': 'r-missing'}

        original = github_cloud.read_private, github_cloud.request, github_cloud.time.sleep
        github_cloud.read_private = read_private
        github_cloud.request = request
        github_cloud.time.sleep = lambda delay: None
        try:
            with self.assertRaises(RuntimeError) as caught:
                github_cloud.write_private(path, raw, None)
        finally:
            github_cloud.read_private, github_cloud.request, github_cloud.time.sleep = original
        self.assertEqual(str(caught.exception), 'private_readback_differs')


if __name__ == '__main__':
    unittest.main()
