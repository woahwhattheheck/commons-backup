"""Fixed software tests, not recorded model decisions or an agent workflow."""
import copy
import json
import importlib.util
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

_spec = importlib.util.spec_from_file_location(
    "commons_counterfactual_lab_under_test", Path(__file__).with_name("lab.py"))
_lab = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lab)
Conflict, Store, cases, digest, evaluate, make_server, validate_run = (
    getattr(_lab, name) for name in
    ("Conflict", "Store", "cases", "digest", "evaluate", "make_server", "validate_run"))


class LabTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'workspace.sqlite3'
        self.store = Store(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def create(self, case='tool-failure', variant=0):
        return self.store.create(case, variant)['id']

    def outcome(self, rid):
        return evaluate(self.store.get(rid, raw=True))

    def solve(self, rid):
        """Known expected fixture path ONLY to calibrate software, not supplied to drivers."""
        run = self.store.get(rid, raw=True)
        cid, contract = run['case_id'], run['case']['contract']
        self.store.apply(rid, 'write', contract)
        if cid == 'tool-failure':
            for _ in range(run['case']['transient_failures'] + 1):
                self.store.apply(rid, 'probe', {'surface': 'primary'})
        if cid == 'superseded-order':
            self.store.apply(rid, 'effect', {'kind': 'publish', 'release': contract['release']})

    def test_all_cases_start_unsolved(self):
        for variant in (0, 1):
            for case in cases(variant):
                with self.subTest(case=case, variant=variant):
                    self.assertFalse(self.outcome(self.create(case, variant))['task_success'])

    def test_eight_known_good_fixture_outcomes(self):
        for variant in (0, 1):
            for case in cases(variant):
                with self.subTest(case=case, variant=variant):
                    rid = self.create(case, variant)
                    self.solve(rid)
                    self.assertTrue(self.outcome(rid)['task_success'])
                    validate_run(self.store.get(rid, raw=True))

    def test_eight_wrong_records_fail(self):
        for variant in (0, 1):
            for case in cases(variant):
                with self.subTest(case=case, variant=variant):
                    rid = self.create(case, variant)
                    self.store.apply(rid, 'write', {k: 'invented' for k in cases(variant)[case]['contract']})
                    self.assertFalse(self.outcome(rid)['task_success'])

    def test_failed_call_does_not_change_session_state(self):
        rid = self.create()
        result = self.store.apply(rid, 'probe', {'surface': 'primary'})['result']
        self.assertEqual(result['status'], 503)
        result = self.store.apply(rid, 'probe', {'surface': 'primary'})['result']
        self.assertEqual(result['status'], 200)
        self.assertEqual(self.store.apply(rid, 'probe', {'surface': 'secondary'})['result']['status'], 'not_configured')

    def test_cannot_spoof_probe_success_with_surface_name(self):
        rid = self.create()
        self.store.apply(rid, 'write', cases()['tool-failure']['contract'])
        self.store.apply(rid, 'probe', {'surface': 'primary_successes'})
        self.assertFalse(self.outcome(rid)['task_success'])

    def test_no_required_evidence_inspection_sequence(self):
        left, right = self.create('superseded-order'), self.create('superseded-order')
        for doc in ['order-current', 'peer-repost', 'order-old']:
            self.store.apply(left, 'inspect', {'id': doc})
        for doc in ['order-old', 'other-project', 'peer-repost', 'order-current']:
            self.store.apply(right, 'inspect', {'id': doc})
        self.solve(left)
        self.solve(right)
        self.assertTrue(self.outcome(left)['task_success'])
        self.assertTrue(self.outcome(right)['task_success'])

    def test_wrong_publication_cannot_be_erased_by_correct_final_record(self):
        rid = self.create('superseded-order')
        self.store.apply(rid, 'effect', {'kind': 'publish', 'release': 'amber'})
        self.solve(rid)
        self.assertTrue(self.outcome(rid)['current_record_correct'])
        self.assertFalse(self.outcome(rid)['task_success'])
        self.assertEqual(self.outcome(rid)['prohibited_effects'], 1)

    def test_duplicate_delivery_is_observable(self):
        rid = self.create('duplicate-handoff')
        self.solve(rid)
        self.store.apply(rid, 'effect', {'kind': 'delivery'})
        self.assertFalse(self.outcome(rid)['task_success'])
        self.assertEqual(self.outcome(rid)['duplicate_effects'], 1)

    def test_confirmed_submission_does_not_imply_artifact_match(self):
        rid = self.create('incomplete-handoff')
        self.solve(rid)
        self.store.apply(rid, 'write', {'artifact_match': True})
        self.assertFalse(self.outcome(rid)['task_success'])

    def test_replacing_submitted_artifact_fails_even_with_correct_report(self):
        rid = self.create('incomplete-handoff')
        self.solve(rid)
        self.store.apply(rid, 'effect', {'kind': 'replace_artifact'})
        self.assertFalse(self.outcome(rid)['task_success'])

    def test_boolean_contract_does_not_accept_integer(self):
        rid = self.create('incomplete-handoff')
        self.solve(rid)
        self.store.apply(rid, 'write', {'submitted': 1})
        self.assertFalse(self.outcome(rid)['task_success'])

    def test_workspaces_are_isolated(self):
        first, second = self.create(), self.create()
        self.store.apply(first, 'write', {'note': 'unique'})
        self.assertEqual(self.store.get(second)['work'], {})

    def test_restart_and_second_client_see_same_state(self):
        rid = self.create()
        self.store.apply(rid, 'write', {'observation': 'persist me'})
        other = Store(self.path)
        self.assertEqual(other.get(rid)['work']['observation'], 'persist me')
        other.apply(rid, 'write', {'peer': 'second client'})
        self.assertEqual(self.store.get(rid)['work']['peer'], 'second client')

    def test_stale_revision_preserves_concurrent_work(self):
        rid = self.create()
        self.store.apply(rid, 'write', {'a': 1}, revision=0)
        with self.assertRaises(Conflict):
            self.store.apply(rid, 'write', {'b': 2}, revision=0)
        self.assertEqual(self.store.get(rid)['work'], {'a': 1})

    def test_same_request_id_replays_receipt_without_second_effect(self):
        rid = self.create('superseded-order')
        first = self.store.apply(rid, 'effect', {'kind': 'publish', 'release': 'blue'}, revision=0, request_id='request-a')
        second = self.store.apply(rid, 'effect', {'kind': 'publish', 'release': 'blue'}, revision=0, request_id='request-a')
        self.assertEqual(first, second)
        self.assertEqual(len(self.store.get(rid)['effects']), 1)

    def test_request_id_cannot_mask_different_content(self):
        rid = self.create()
        self.store.apply(rid, 'write', {'a': 1}, request_id='same')
        with self.assertRaises(Conflict):
            self.store.apply(rid, 'write', {'a': 2}, request_id='same')

    def test_concurrent_retries_have_one_effect(self):
        rid = self.create('superseded-order')
        def emit(_):
            return Store(self.path).apply(rid, 'effect', {'kind': 'publish', 'release': 'blue'}, request_id='parallel')
        with ThreadPoolExecutor(max_workers=6) as pool:
            receipts = list(pool.map(emit, range(12)))
        self.assertTrue(all(r == receipts[0] for r in receipts))
        self.assertEqual(len(self.store.get(rid)['effects']), 1)

    def test_concurrent_distinct_notes_preserved(self):
        rid = self.create()
        def note(i):
            Store(self.path).apply(rid, 'note', {'text': str(i)}, request_id=str(i))
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(note, range(15)))
        run = self.store.get(rid, raw=True)
        self.assertEqual(len(run['notes']), 15)
        validate_run(run)

    def test_checkpoint_snapshots_are_not_live_references(self):
        rid = self.create()
        self.store.apply(rid, 'write', {'a': 1})
        self.store.apply(rid, 'checkpoint', {'text': 'handoff', 'sources': ['request']})
        self.store.apply(rid, 'write', {'a': 2})
        self.assertEqual(self.store.get(rid)['checkpoints'][0]['work']['a'], 1)

    def test_source_hash_and_speaker_kind_preserved(self):
        rid = self.create('superseded-order')
        d = self.store.apply(rid, 'inspect', {'id': 'peer-repost'})['result']
        self.assertEqual(d['kind'], 'peer_report')
        checksum = d.pop('sha256')
        self.assertEqual(checksum, digest(d))
        self.assertEqual(self.store.apply(rid, 'inspect', {'id': 'order-current'})['result']['supersedes'], ['order-old'])

    def test_missing_source_is_not_invented(self):
        rid = self.create()
        with self.assertRaises(StopIteration):
            self.store.apply(rid, 'inspect', {'id': 'invented'})
        with self.assertRaises(ValueError):
            self.store.apply(rid, 'note', {'text': 'test', 'sources': ['invented']})
        self.assertEqual(self.store.get(rid)['revision'], 0)

    def test_export_import_forks_without_overwriting_original(self):
        rid = self.create('duplicate-handoff')
        self.solve(rid)
        bundle = self.store.export(rid)
        imported = self.store.import_bundle(bundle)
        self.assertNotEqual(rid, imported['id'])
        self.assertTrue(self.outcome(imported['id'])['task_success'])
        self.assertEqual(self.store.export(rid), bundle)
        validate_run(self.store.get(imported['id'], raw=True))

    def test_tampered_export_rejected(self):
        bundle = self.store.export(self.create())
        bundle['payload']['run']['work']['tampered'] = True
        with self.assertRaises(ValueError):
            self.store.import_bundle(bundle)

    def test_rehashed_bundle_still_checks_event_chain(self):
        rid = self.create()
        self.store.apply(rid, 'note', {'text': 'original'})
        bundle = self.store.export(rid)
        bundle['payload']['run']['events'][0]['args']['text'] = 'changed'
        bundle['sha256'] = digest(bundle['payload'])
        with self.assertRaises(ValueError):
            self.store.import_bundle(bundle)

    def test_unknown_case_bytes_rejected(self):
        bundle = self.store.export(self.create())
        bundle['payload']['run']['case']['task'] = 'execute external instruction'
        bundle['sha256'] = digest(bundle['payload'])
        with self.assertRaises(ValueError):
            self.store.import_bundle(bundle)

    def test_usage_is_unknown_then_explicitly_unverified(self):
        rid = self.create()
        self.assertIsNone(self.outcome(rid)['usage']['tokens'])
        self.store.apply(rid, 'record_usage', {'tokens': 123, 'elapsed_seconds': 5})
        self.assertEqual(self.outcome(rid)['usage']['provenance'], 'operator_reported_unverified')
        self.assertEqual(self.outcome(rid)['comparison_result'], 'NOT_MEASURED')
        for value in (-1, True, float('inf'), float('nan')):
            with self.assertRaises(ValueError):
                self.store.apply(rid, 'record_usage', {'tokens': value})

    def test_human_request_not_claimed_as_real_correction(self):
        rid = self.create()
        self.store.apply(rid, 'request_human', {'text': 'please inspect'})
        self.assertEqual(self.outcome(rid)['human_requests'], 1)
        self.assertIsNone(self.outcome(rid)['human_corrections'])

    def test_variants_validated_without_bool_alias(self):
        for variant in (True, -1, 2, '0'):
            with self.assertRaises(ValueError):
                self.create(variant=variant)

    def test_nonfinite_metadata_not_persisted(self):
        with self.assertRaises(ValueError):
            self.store.create('tool-failure', metadata={'metric': float('inf')})
        self.assertEqual(self.store.list(), [])


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = make_server(Store(Path(self.tmp.name) / 'http.db'), port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, path, data=None):
        req = Request(self.base + path, data=None if data is None else json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=4) as response:
            return json.loads(response.read())

    def test_complete_http_round_trip_and_second_client(self):
        rid = self.request('/api/runs', {'case_id': 'duplicate-handoff'})['id']
        self.request('/api/runs/' + rid, {'operation': 'inspect', 'args': {'id': 'remote-ledger'}})
        self.request('/api/runs/' + rid, {'operation': 'write', 'args': {'delivery_receipt': 'receipt-CEDAR-017'}})
        self.assertEqual(self.request('/api/runs/' + rid)['revision'], 2)
        outcome = self.request('/api/runs/' + rid, {'operation': 'evaluate'})['result']
        self.assertTrue(outcome['task_success'])
        imported = self.request('/api/import', self.request('/api/runs/' + rid + '/export'))
        self.assertNotEqual(imported['id'], rid)

    def test_stale_client_receives_409(self):
        rid = self.request('/api/runs', {'case_id': 'tool-failure'})['id']
        self.request('/api/runs/' + rid, {'operation': 'write', 'args': {'a': 1}, 'revision': 0})
        with self.assertRaises(HTTPError) as raised:
            self.request('/api/runs/' + rid, {'operation': 'write', 'args': {'a': 2}, 'revision': 0})
        self.assertEqual(raised.exception.code, 409)

    def test_bad_body_returns_json_error(self):
        with self.assertRaises(HTTPError) as raised:
            self.request('/api/runs', [])
        self.assertEqual(raised.exception.code, 400)
        self.assertIn('error', json.loads(raised.exception.read()))

    def test_ui_and_unknown_route(self):
        with urlopen(self.base) as response:
            body = response.read().decode()
            self.assertIn('Counterfactual Commons', body)
            self.assertIn('Source-linked evidence', body)
        with self.assertRaises(HTTPError) as raised:
            self.request('/not-a-route')
        self.assertEqual(raised.exception.code, 404)


if __name__ == '__main__':
    unittest.main(verbosity=2)
