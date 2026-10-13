import copy
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from bank_check import audit


def claim(key='a', bank=(1, 10), ts='1788863492.232329', **extra):
    return dict(claim_id=key, message_ts=ts, bank=list(bank), **extra)


def doc(*rows, cutoff='1788863551.559369'):
    return dict(snapshot_ts=cutoff, claims=list(rows))


class BankTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(audit(doc())['conflicts'], [])

    def test_inclusive_endpoint(self):
        result = audit(doc(claim(), claim('b', (10, 20))))
        self.assertEqual(result['conflicts'][0]['bank'], [10, 10])

    def test_adjacent_nonoverlap(self):
        self.assertFalse(audit(doc(claim(), claim('b', (11, 20))))['conflicts'])

    def test_nested_interval(self):
        self.assertEqual(audit(doc(claim(), claim('b', (2, 3))))['conflicts'][0]['bank'], [2, 3])

    def test_distinct_same_name_claims(self):
        result = audit(doc(claim(label='KEPLER'), claim('b', label='KEPLER')))
        self.assertEqual(len(result['active_claims']), 2)
        self.assertEqual(len(result['conflicts']), 1)

    def test_duplicate_replay(self):
        original = claim()
        self.assertEqual(len(audit(doc(original, copy.deepcopy(original)))['active_claims']), 1)

    def test_inconsistent_replay_rejected(self):
        with self.assertRaises(ValueError):
            audit(doc(claim(), claim(bank=(2, 10))))

    def test_explicit_later_supersession(self):
        result = audit(doc(claim(), claim('b', (11, 20), '1788863550.488959', supersedes=['a'])))
        self.assertEqual(result['superseded_claim_ids'], ['a'])
        self.assertEqual([r['claim_id'] for r in result['active_claims']], ['b'])

    def test_started_work_retained(self):
        result = audit(doc(claim(phase='started'), claim('b', (11, 20), '1788863550.488959', supersedes=['a'])))
        self.assertEqual(len(result['active_claims']), 2)
        self.assertEqual(result['blocked_supersessions'], [{'old': 'a', 'replacement': 'b'}])

    def test_completed_work_retained(self):
        result = audit(doc(claim(phase='completed'), claim('b', (11, 20), '1788863550.488959', supersedes=['a'])))
        self.assertEqual(len(result['active_claims']), 2)
        self.assertTrue(result['blocked_supersessions'])

    def test_replacement_overlaps_third_party(self):
        result = audit(doc(claim(), claim('other', (20, 30)), claim('b', (25, 40), '1788863550.488959', supersedes=['a'])))
        self.assertEqual(result['conflicts'], [{'left': 'other', 'right': 'b', 'bank': [25, 30]}])

    def test_missing_superseded_event(self):
        with self.assertRaises(ValueError):
            audit(doc(claim(supersedes=['missing'])))

    def test_equal_time_supersession_rejected(self):
        with self.assertRaises(ValueError):
            audit(doc(claim(), claim('b', supersedes=['a'])))

    def test_earlier_supersession_rejected(self):
        with self.assertRaises(ValueError):
            audit(doc(claim(), claim('b', ts='1788863491.232329', supersedes=['a'])))

    def test_self_supersession_rejected(self):
        with self.assertRaises(ValueError):
            audit(doc(claim(supersedes=['a'])))

    def test_supersession_fork(self):
        result = audit(doc(claim(), claim('b', (11, 20), '1788863550.488959', supersedes=['a']), claim('c', (21, 30), '1788863551.488959', supersedes=['a'])))
        self.assertEqual(result['forks'], {'a': ['b', 'c']})
        self.assertEqual(len(result['active_claims']), 2)

    def test_duplicate_operation_ids_not_deduplicated(self):
        result = audit(doc(claim(operation_id='op'), claim('b', (11, 20), operation_id='op')))
        self.assertEqual(result['reused_active_operation_ids'], {'op': ['a', 'b']})
        self.assertEqual(len(result['active_claims']), 2)

    def test_superseded_operation_id_not_flagged(self):
        result = audit(doc(claim(operation_id='op'), claim('b', (11, 20), '1788863550.488959', operation_id='op', supersedes=['a'])))
        self.assertEqual(result['reused_active_operation_ids'], {})

    def test_distinct_subclaims_same_message(self):
        result = audit(doc(claim('ts/a'), claim('ts/b', (11, 20))))
        self.assertEqual(len(result['active_claims']), 2)

    def test_future_event_rejected(self):
        with self.assertRaises(ValueError):
            audit(doc(claim(ts='1788863551.559370')))

    def test_exact_cutoff_accepted(self):
        self.assertEqual(len(audit(doc(claim(ts='1788863551.559369')))['active_claims']), 1)

    def test_timestamp_precision_not_float(self):
        result = audit(doc(claim(ts='1788863551.559368'), claim('b', (11, 20), '1788863551.559369', supersedes=['a'])))
        self.assertEqual(result['superseded_claim_ids'], ['a'])

    def test_malformed_timestamps(self):
        for bad in (None, False, 1788863492.232329, '1788863492', '1788863492.2', 'nan', '-1.000000'):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                audit(doc(claim(ts=bad)))

    def test_invalid_banks(self):
        for bad in ([0, 1], [2, 1], [-1, 4], [True, 4], [1, False], [1.0, 4], [1], [1, 2, 3], None, '1-10'):
            row = claim(); row['bank'] = bad
            with self.subTest(value=bad), self.assertRaises(ValueError):
                audit(doc(row))

    def test_invalid_phase(self):
        with self.assertRaises(ValueError):
            audit(doc(claim(phase='maybe')))

    def test_invalid_document_and_rows(self):
        for bad in (None, [], {}, dict(snapshot_ts='1788863551.559369', claims={}), doc(None)):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                audit(bad)

    def test_invalid_ids_and_supersedes(self):
        for bad in ('', None, 12, ' '):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                audit(doc(claim(bad)))
        for bad in ('a', [1], ['a', 'a']):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                audit(doc(claim(supersedes=bad)))

    def test_input_unchanged(self):
        original = doc(claim(), claim('b', (11, 20)))
        before = copy.deepcopy(original)
        audit(original)
        self.assertEqual(original, before)

    def test_order_independent_output(self):
        rows = [claim('c', (5, 8)), claim('b', (3, 8)), claim()]
        self.assertEqual(audit(doc(*rows)), audit(doc(*reversed(rows))))

    def test_context_preserved(self):
        original = doc(claim())
        original["coverage_note"] = "HYPOTHETICAL, NOT LIVE"
        self.assertEqual(audit(original)["coverage_note"], "HYPOTHETICAL, NOT LIVE")

    def test_cli_exit_codes_and_json(self):
        executable = str(Path(__file__).with_name('bank_check.py'))
        cases = [(json.dumps(doc(claim())), 0), (json.dumps(doc(claim(), claim('b'))), 1), ('{broken', 2)]
        for text, status in cases:
            with self.subTest(status=status):
                result = subprocess.run([sys.executable, '-B', executable, '-'], input=text, text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, status)
                parsed = json.loads(result.stderr if status == 2 else result.stdout)
                self.assertIsInstance(parsed, dict)


if __name__ == '__main__':
    unittest.main(verbosity=2)
