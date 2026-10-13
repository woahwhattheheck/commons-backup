# SPDX-License-Identifier: Apache-2.0
"""Experiment-contract checks, with no actor or native-market execution."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('arrival_experiment', HERE/'run_arrival_sensitivity.py')
subject = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = subject
spec.loader.exec_module(subject)


def observation(step=226, shops=3):
    return {'step': step, 'town': {'unlocked_shops': ['BAKERY']*shops}}


def pair(left=89291.0, right=84040.0, right_status='complete'):
    return [{'offered_route': subject.ROUTES[0], 'status':'complete', 'final_cash':left},
            {'offered_route': subject.ROUTES[1], 'status':right_status, 'final_cash':right}]


class ExperimentContractTests(unittest.TestCase):
    def test_actual_default_schedule_and_cap(self):
        obs = observation()
        self.assertEqual(subject.arrival_times(obs, {}), [288,360,432,504,576])
        self.assertEqual(obs, observation())

    def test_duplicate_shops_count_as_instances(self):
        self.assertEqual(subject.arrival_times(observation(226, 7), {}), [288])
        self.assertEqual(subject.arrival_times(observation(226, 8), {}), [])

    def test_current_boundary_is_not_future_draw(self):
        self.assertEqual(subject.arrival_times(observation(288, 4), {}), [360,432,504,576])

    def test_custom_periods_and_final_market_bound(self):
        cfg = {'turnsPerDay':5,'townShopUnlockInterval':2,'episodeSteps':22}
        self.assertEqual(subject.arrival_times(observation(6, 0), cfg),[10,20])
        cfg['episodeSteps'] = 21
        self.assertEqual(subject.arrival_times(observation(6, 0), cfg),[10])

    def test_invalid_period_does_not_synthesize_schedule(self):
        for cfg in ({'turnsPerDay':0}, {'townShopUnlockInterval':0}):
            with self.assertRaises(ValueError): subject.arrival_times(observation(), cfg)

    def test_retained_comparison_preserves_cash_and_unknown_rival(self):
        got = subject.comparison(pair(), None)
        self.assertEqual(got['sheep_minus_main'],-5251)
        self.assertTrue(got['complete'])
        self.assertIsNone(got['rival_cash'])
        self.assertIsNone(got['win_utility'])
        positive = subject.comparison(pair(109492,118750),288)
        self.assertEqual(positive['sheep_minus_main'],9258)

    def test_partial_case_never_acquires_score(self):
        result = subject.comparison(pair(right=118750,right_status='incomplete'),360)
        self.assertFalse(result['complete'])
        self.assertIsNone(result['sheep_cash'])
        self.assertIsNone(result['sheep_minus_main'])

    def test_route_names_not_row_order_define_comparison(self):
        self.assertEqual(subject.comparison(pair(),432),subject.comparison(list(reversed(pair())),432))
        for invalid in (pair()[:1],pair()+pair()[:1],pair()[:1]*2):
            with self.assertRaises(ValueError): subject.comparison(invalid,432)

    def test_checkpoint_serialization_preserves_previous_payload_until_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'result.json'
            subject.write_json(path,{'complete':False,'cases':[]})
            subject.write_json(path,{'complete':True,'cases':[1]})
            self.assertEqual(json.loads(path.read_text()),{'complete':True,'cases':[1]})
            self.assertFalse((Path(tmp)/'result.json.tmp').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
