"""Exercise the earlier, actually published draft and its restored entry point."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from revenue.uiowa_rfq_18649_incident_learning.incident_learning import assess_packet

ROOT = Path(__file__).resolve().parent


class LegacyEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / 'examples.json').read_text(encoding='utf-8'))

    def test_published_fixture_identity_and_no_mutation(self):
        raw = (ROOT / 'examples.json').read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        self.assertEqual(blob, 'eee796ce7165d9ce76104d53be0f98b78a62cee8')
        before = copy.deepcopy(self.data)
        result = assess_packet(self.data)
        self.assertEqual(before, self.data)
        self.assertEqual(result['incidents'][0]['supplied_record'], before['incidents'][0])

    def test_retained_references_are_not_verified_improvement(self):
        first, second = assess_packet(self.data)['incidents']
        self.assertEqual([a['record_state'] for a in first['actions']],
                         ['OVERDUE', 'COMPLETION_REFERENCED', 'CHANGE_REFERENCED'])
        self.assertTrue(second['actions'][0]['effectiveness_reference_present'])
        self.assertEqual(second['learning_evidence'], 'REFERENCE_ONLY_REVIEW_REQUIRED')
        self.assertIn('NOT_ESTABLISHED', second['actions'][0]['effectiveness_verification'])

    def test_reported_interval_is_distinct_from_measured(self):
        first, second = assess_packet(self.data)['incidents']
        self.assertEqual(first['reported_detection_to_restoration_minutes'], 45)
        self.assertEqual(second['reported_detection_to_restoration_minutes'], 18)
        self.assertIsNone(first['measured_restoration_minutes'])

    def test_naive_time_and_future_completion_rejected(self):
        for value in ('2026-08-01T10:00:00', '2027-01-01T00:00:00Z'):
            self.data['incidents'][0]['corrective_actions'][0]['completed_at'] = value
            with self.assertRaises(ValueError):
                assess_packet(self.data)

    def test_duplicate_identity_and_reversed_timeline_rejected(self):
        self.data['incidents'].append(copy.deepcopy(self.data['incidents'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate incident'):
            assess_packet(self.data)
        self.data['incidents'].pop()
        self.data['incidents'][0]['corrective_actions'].append(copy.deepcopy(self.data['incidents'][0]['corrective_actions'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate action'):
            assess_packet(self.data)
        self.setUp()
        self.data['incidents'][0]['timeline'].reverse()
        with self.assertRaisesRegex(ValueError, 'chronologically'):
            assess_packet(self.data)

    def test_missing_due_and_incomplete_replacement_stay_unknown(self):
        self.data['incidents'][0]['corrective_actions'][0]['due_at'] = None
        self.data['incidents'][0]['corrective_actions'][2]['changed_approach']['decision_ref'] = ''
        actions = assess_packet(self.data)['incidents'][0]['actions']
        self.assertEqual(actions[0]['record_state'], 'UNKNOWN')
        self.assertEqual(actions[2]['record_state'], 'CHANGE_UNVERIFIED')

    def test_old_command_runs_and_cannot_replace_files(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'result.json'
            cmd = [sys.executable, str(ROOT / 'incident_learning.py'), str(ROOT / 'examples.json'), '--out', str(target)]
            first = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            original = target.read_bytes()
            self.assertEqual(json.loads(original)['schema'], 'uiowa-067-legacy-observations/v2')
            second = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(second.returncode, 2)
            self.assertEqual(target.read_bytes(), original)
            cmd[-1] = str(ROOT / 'examples.json')
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)

    def test_invalid_type_or_duplicate_key_returns_no_partial_report(self):
        for field, value in (('synthetic', 'false'), ('schema', 'different')):
            self.setUp()
            self.data[field] = value
            with self.assertRaises(ValueError):
                assess_packet(self.data)
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / 'bad.json'
            bad.write_text('{"x":1,"x":2}')
            result = subprocess.run([sys.executable, str(ROOT / 'incident_learning.py'), str(bad)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
            self.assertIn('duplicate JSON key', result.stderr)


if __name__ == '__main__':
    unittest.main()
