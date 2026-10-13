# SPDX-License-Identifier: Apache-2.0
"""Tests of the independent observation oracle, not a replacement donor suite."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import tempfile
import unittest
import check_exec_pace_engine_observations as oracle

DONOR = Path(__file__).parent / 'raw' / 'r04_exec_adaptive.py'


def observation(step):
    return {'step': step, 'market': {'prices': {
        good: 1 + step * (index + 1) / 16 for index, good in enumerate(oracle.GOODS)}}}


class OracleTests(unittest.TestCase):
    def setUp(self):
        oracle.checked(DONOR, oracle.DONOR_BLOB)
        self.sensor = oracle.import_file(DONOR, 'oracle_test_donor')
        self.histories = {good: [] for good in oracle.GOODS}

    def feed(self, count=64):
        for step in range(count):
            oracle.check_observation(self.sensor, observation(step), self.histories, str(step))

    def test_source_identity(self):
        self.assertEqual(oracle.identity(DONOR)['git_blob'], oracle.DONOR_BLOB)
        self.assertEqual(oracle.identity(DONOR)['bytes'], 3728)

    def test_mismatched_source_rejected(self):
        with self.assertRaisesRegex(oracle.CheckFailure, 'source mismatch'):
            oracle.checked(DONOR, '0' * 40)

    def test_valid_sequence_retains_exact_window(self):
        self.feed()
        for good in oracle.GOODS:
            self.assertEqual(len(self.histories[good]), 25)
            self.assertTrue(self.sensor.rising(good))

    def test_partial_history_uses_none(self):
        self.feed(24)
        self.assertIsNone(self.sensor.slope('MILK'))
        self.assertFalse(self.sensor.rising('MILK'))

    def test_wrong_numeric_slope_rejected(self):
        original = self.sensor.slope
        self.sensor.slope = lambda good: None if original(good) is None else -original(good)
        with self.assertRaisesRegex(oracle.CheckFailure, 'slope'):
            self.feed()

    def test_wrong_rising_rejected(self):
        self.sensor.rising = lambda good: False
        with self.assertRaisesRegex(oracle.CheckFailure, 'rising mismatch'):
            self.feed()

    def test_observation_mutation_rejected(self):
        original = self.sensor.note_prices
        def mutate(obs):
            original(obs)
            obs['mutated'] = True
        self.sensor.note_prices = mutate
        with self.assertRaisesRegex(oracle.CheckFailure, 'mutated observation'):
            self.feed()

    def test_nonfinite_engine_output_rejected(self):
        obs = observation(0)
        obs['market']['prices']['MILK'] = float('inf')
        with self.assertRaises(ValueError):
            oracle.check_observation(self.sensor, obs, self.histories, 'invalid')

    def test_candidate_pin_pair_required(self):
        with self.assertRaisesRegex(oracle.CheckFailure, 'supplied together'):
            oracle.run('unused', DONOR, candidate=DONOR)

    def test_duplicate_seed_plan_rejected(self):
        with self.assertRaisesRegex(oracle.CheckFailure, 'unique'):
            oracle.run('unused', DONOR, seeds=(1, 1))

    def test_empty_seed_plan_rejected(self):
        with self.assertRaisesRegex(oracle.CheckFailure, 'nonempty'):
            oracle.run('unused', DONOR, seeds=())

    def test_fault_report_is_json_safe_and_not_greenwashed(self):
        report = oracle.characterize_invalid_prices(self.sensor)
        self.assertEqual(report['cells'], 112)
        self.assertEqual(report['invalidated'], 0)
        json.dumps(report, allow_nan=False)
        infinite = [row for row in report['rows']
                    if row['fault'] == 'positive_inf' and row['bad_position'] == 24]
        self.assertEqual(len(infinite), 7)
        self.assertTrue(all(row['slope'] == 'inf' and row['rising'] for row in infinite))

    def test_interpreter_fault_load_fails_before_import(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'kaggriculture.py').write_text('raise RuntimeError("executed")')
            with self.assertRaisesRegex(oracle.CheckFailure, 'source mismatch'):
                oracle.load_engine(directory)

    def test_missing_engine_has_no_network_fallback(self):
        # The runner has no network fallback: absent files must fail closed.
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                oracle.load_engine(directory)

    def test_market_cycle_never_overbuys_known_cash(self):
        obs = observation(0)
        obs['private'] = {'shed': {}}
        obs['farms'] = [{'money': 0}, {'money': 0}]
        self.assertEqual(oracle.action_for(None, obs, 'market-cycle', 0, 0)['market'], [])
        obs['private']['shed']['WOOL'] = 2
        self.assertEqual(oracle.action_for(None, obs, 'market-cycle', 0, 0)['market'],
                         [['SELL', 'WOOL', 2]])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--donor', type=Path, default=DONOR)
    args, remaining = parser.parse_known_args()
    DONOR = args.donor
    unittest.main(argv=[__file__, *remaining])
