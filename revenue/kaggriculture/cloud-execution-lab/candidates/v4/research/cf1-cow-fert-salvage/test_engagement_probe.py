# SPDX-License-Identifier: Apache-2.0
"""Probe contract tests; synthetic fixtures are never called natural engagement."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

from engagement_probe import EngagementProbe, blob_hash, digest, summarize
from run_native_engagement import validate_manifest

HERE = Path(__file__).resolve().parent


def fixture(seat=0, hand=False):
    tile = {'kind': 'PASTURE', 'animal': 'COW', 'fed_today': True,
            'cared_today': True, 'fertilizer_available': True,
            'yield_units': 0, 'placed_day': 0, 'consecutive_unfed': 0,
            'pending_care_bonus': 2}
    tiles = [[{'kind': 'EMPTY'} for _ in range(10)] for _ in range(10)]
    tiles[2][2] = tile
    farm = {'tiles': tiles, 'farmer': [0, 0] if hand else [2, 2],
            'hands': [[2, 2]] if hand else []}
    farms = [copy.deepcopy(farm), copy.deepcopy(farm)]
    obs = {'step': 23, 'player': seat, 'farms': farms,
           'private': {'shed': {}, 'inventories': [{}, {}] if hand else [{}]}}
    action = {'farmer': ['PASS'] if hand else ['HARVEST'],
              'hands': [['HARVEST']] if hand else [], 'market': []}
    cfg = {'episodeSteps': 720, 'turnsPerDay': 24, 'boardSize': 10,
           'shedCapacity': 100, 'maxMarketOrdersPerTurn': 10}
    return obs, cfg, action


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.probe = EngagementProbe(HERE / 'r04_cow_fert_salvage.py')

    def test_real_donor_admits_both_seats_and_actor_types(self):
        for seat in (0, 1):
            for hand in (False, True):
                with self.subTest(seat=seat, hand=hand):
                    obs, cfg, action = fixture(seat, hand)
                    row = self.probe.inspect(obs, cfg, action)
                    self.assertTrue(row['would_activate'])
                    self.assertEqual(row['donor_guard'], 'admitted')
                    expected = copy.deepcopy(action)
                    if hand:
                        expected['hands'][0] = ['COLLECT_FERTILIZER']
                    else:
                        expected['farmer'] = ['COLLECT_FERTILIZER']
                    self.assertEqual(row['hypothetical_action'], expected)

    def test_completed_service_remains_off(self):
        obs, cfg, action = fixture()
        for command in ('CARE', 'FEED'):
            action['farmer'] = [command]
            row = self.probe.inspect(obs, cfg, action)
            self.assertFalse(row['would_activate'])
            self.assertIs(row['completed_service'], False)
            # Demonstrate that the new extension would be a distinct treatment.
            candidate = self.probe.function(action, obs, cfg, enabled=True, completed_service=True)
            self.assertIsNot(candidate, action)

    def test_all_days_and_seats_match_uninstrumented_donor(self):
        for day in range(30):
            for seat in (0, 1):
                for hand in (False, True):
                    obs, cfg, action = fixture(seat, hand)
                    obs['step'] = day * 24 + 23
                    expected = self.probe.function(action, obs, cfg, enabled=True)
                    result = self.probe.inspect(obs, cfg, action)
                    self.assertEqual(result['would_activate'], expected is not action)
                    self.assertEqual(result.get('hypothetical_action', action), expected)

    def test_no_input_mutation_or_telemetry_leak(self):
        obs, cfg, action = fixture()
        before = copy.deepcopy((obs, cfg, action))
        self.probe.module.telemetry.update({'activations': 9, 'other': 7})
        counters = self.probe.module.telemetry.copy()
        self.probe.inspect(obs, cfg, action)
        self.assertEqual((obs, cfg, action), before)
        self.assertEqual(self.probe.module.telemetry, counters)

    def test_actual_return_line_identifies_time_rejection(self):
        obs, cfg, action = fixture()
        obs['step'] = 24
        row = self.probe.inspect(obs, cfg, action)
        self.assertFalse(row['would_activate'])
        self.assertIn('step % 24', row['donor_guard'])
        self.assertNotIn('hypothetical_action', row)

    def test_shed_capacity_rejection_is_actual_guard(self):
        obs, cfg, action = fixture()
        obs['private']['shed']['MILK'] = 100
        row = self.probe.inspect(obs, cfg, action)
        self.assertFalse(row['would_activate'])
        self.assertEqual(row['donor_guard'], 'total + 1 > 100')

    def test_market_suffix_is_not_compacted(self):
        obs, cfg, action = fixture()
        action['market'] = [[] for _ in range(10)] + [['BUY_PRODUCT', 'WHEAT', 2]]
        self.assertTrue(self.probe.inspect(obs, cfg, action)['would_activate'])
        action['market'].pop(0)
        self.assertFalse(self.probe.inspect(obs, cfg, action)['would_activate'])

    def test_donor_alias_failclosed_is_preserved(self):
        obs, cfg, action = fixture()
        obs['private']['shed'] = obs['private']['inventories'][0]
        row = self.probe.inspect(obs, cfg, action)
        self.assertFalse(row['would_activate'])
        self.assertIn('id(', row['donor_guard'])

    def test_missing_actor_vector_is_not_positive(self):
        obs, cfg, action = fixture(hand=True)
        action['hands'] = []
        row = self.probe.inspect(obs, cfg, action)
        self.assertFalse(row['would_activate'])
        self.assertIn('len(rows)', row['donor_guard'])

    def test_missing_configuration_is_rejected_by_donor(self):
        obs, cfg, action = fixture()
        del cfg['shedCapacity']
        self.assertFalse(self.probe.inspect(obs, cfg, action)['would_activate'])

    def test_caller_trace_restored(self):
        def previous(frame, event, arg):
            return None
        original = sys.gettrace()
        try:
            sys.settrace(previous)
            self.probe.inspect(*fixture())
            self.assertIs(sys.gettrace(), previous)
        finally:
            sys.settrace(original)

    def test_non_mapping_rejected(self):
        obs, cfg, action = fixture()
        for args in ((None, cfg, action), (obs, None, action), (obs, cfg, None)):
            with self.assertRaises(TypeError):
                self.probe.inspect(*args)

    def test_donor_source_change_requires_review(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'donor.py'
            path.write_bytes((HERE / 'r04_cow_fert_salvage.py').read_bytes() + b'\n')
            with self.assertRaises(ValueError):
                EngagementProbe(path)


class CoverageTests(unittest.TestCase):
    @staticmethod
    def rows(last=718):
        return [{'step': step, 'seat': 0, 'would_activate': False,
                 'off_identity': True, 'input_unchanged': True,
                 'donor_return_line': 80} for step in range(last + 1)]

    def test_complete_zero_is_panel_scoped(self):
        result = summarize(self.rows())
        self.assertTrue(result['complete'])
        self.assertEqual(result['eligible_eod_callbacks'], 29)
        self.assertEqual(result['verdict'], 'ZERO_ON_THIS_PANEL_ONLY')

    def test_positive_requires_economics_not_promotion(self):
        rows = self.rows()
        rows[23]['would_activate'] = True
        result = summarize(rows)
        self.assertEqual(result['would_activate'], 1)
        self.assertEqual(result['verdict'], 'ENGAGED_REQUIRES_PAIRED_ECONOMICS')

    def test_missing_duplicate_and_reordered_are_incomplete(self):
        rows = self.rows()
        for bad in ([], rows[:-1], rows[1:], rows + [rows[-1]], rows[:23] + rows[24:], list(reversed(rows))):
            self.assertFalse(summarize(bad)['complete'])
            self.assertEqual(summarize(bad)['verdict'], 'INCOMPLETE')

    def test_bool_and_missing_integrity_flags_are_incomplete(self):
        for key, value in [('step', False), ('seat', False), ('would_activate', 0),
                           ('off_identity', False), ('input_unchanged', None), ('seat', 1)]:
            for index in (0, 23, 718):
                rows = self.rows()
                rows[index][key] = value
                self.assertFalse(summarize(rows)['complete'], (index, key, value))

    def test_invalid_expected_step_rejected(self):
        for bad in (True, -1, 1.5):
            with self.assertRaises(ValueError):
                summarize(self.rows(), expected_last_step=bad)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.manifest = {}
        for name in ('main.py', 'titan_runtime.py', 'TITAN-CONFIG.json'):
            raw = b'{}\n'
            (self.root / name).write_bytes(raw)
            self.manifest[name] = blob_hash(raw)

    def test_exact_manifest_and_payload(self):
        self.assertEqual(validate_manifest(self.root, self.manifest), self.manifest)

    def test_incomplete_manifest_rejected(self):
        del self.manifest['main.py']
        with self.assertRaises(ValueError):
            validate_manifest(self.root, self.manifest)

    def test_unpinned_extra_source_rejected(self):
        (self.root / 'extra.py').write_text('pass\n')
        with self.assertRaises(ValueError):
            validate_manifest(self.root, self.manifest)

    def test_mismatched_source_rejected(self):
        (self.root / 'main.py').write_text('# modified\n')
        with self.assertRaises(ValueError):
            validate_manifest(self.root, self.manifest)

    def test_path_escape_rejected(self):
        for name in ('../outside.py', '/tmp/outside.py'):
            with self.assertRaises(ValueError):
                validate_manifest(self.root, dict(self.manifest, **{name: '0' * 40}))


if __name__ == '__main__':
    unittest.main()
