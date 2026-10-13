"""Real-engine regressions for the existing V4 counterfactual/RNG3 lanes.

Run: python [-O] test_town_rng_audit.py --engine PATH -v
No RNG outcomes are replaced except in explicitly named counterexample tests.
"""
from __future__ import annotations
import argparse
import copy
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

import town_rng_audit as R

ENGINE_PATH = R.default_engine_path()


class TownRngTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = R.load_engine(ENGINE_PATH)

    def eod(self, state, env, day=2):
        with R.TownAudit(self.e) as audit:
            self.e._end_of_day(state, env, day)
        return audit.events

    def test_01_wrong_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'engine.py'
            p.write_bytes(b'print("not the pinned engine")\n')
            with self.assertRaises(ValueError):
                R.load_engine(p)

    def test_02_exact_pass_plant_witness(self):
        result = R.planting_pair(self.e)
        self.assertEqual(result['PASS']['shops_after'], ['YARN_STORE'])
        self.assertEqual(result['PLANT_TOMATO']['shops_after'], ['ICE_CREAM_SHOP'])
        self.assertEqual(result['PASS']['weed_rng_calls'], 50)
        self.assertEqual(result['PLANT_TOMATO']['weed_rng_calls'], 49)
        self.assertTrue(result['same_immediate_cash'])
        self.assertTrue(result['same_immediate_market'])
        self.assertFalse(result['comparison']['same_shop_path'])

    def test_03_both_seats_can_shift_shared_shop_rng(self):
        a = R.planting_pair(self.e, seat=0)
        b = R.planting_pair(self.e, seat=1)
        self.assertEqual(a['PLANT_TOMATO']['shops_after'], b['PLANT_TOMATO']['shops_after'])
        self.assertEqual(a['PLANT_TOMATO']['farms'][0]['empty_before_weed'], 24)
        self.assertEqual(b['PLANT_TOMATO']['farms'][1]['empty_before_weed'], 24)

    def test_04_zero_and_standard_weed_chance_same_current_choice(self):
        a = R.planting_pair(self.e, weed_chance=0.0)
        b = R.planting_pair(self.e, weed_chance=0.005)
        self.assertEqual(a['PASS']['shops_after'], b['PASS']['shops_after'])
        self.assertEqual(a['PLANT_TOMATO']['shops_after'], b['PLANT_TOMATO']['shops_after'])

    def test_05_rng_offset_is_real_not_only_an_empty_counter(self):
        rng = random.Random(2)  # seed=0, EOD day=2
        for _ in range(50):
            rng.random()
        self.assertEqual(rng.choice(sorted(self.e.SHOPS)), 'YARN_STORE')
        rng = random.Random(2)
        for _ in range(49):
            rng.random()
        self.assertEqual(rng.choice(sorted(self.e.SHOPS)), 'ICE_CREAM_SHOP')

    def test_06_skipping_zero_chance_weed_loop_is_not_semantics_preserving(self):
        a, env = R.fixture(self.e, 0, step=71, weed_chance=0)
        b = copy.deepcopy(a)
        self.e._end_of_day(a, env, 2)
        with patch.object(self.e, '_spawn_weeds', lambda *args: None):
            self.e._end_of_day(b, copy.deepcopy(env), 2)
        self.assertNotEqual(a[0].observation.town, b[0].observation.town)

    def test_07_geometry_does_not_change_choice_when_total_empty_count_equal(self):
        a, env = R.fixture(self.e, 77, step=71, weed_chance=0)
        b = copy.deepcopy(a)
        a[0].observation.farms[0]['tiles'][0][0] = {'kind': 'WEED'}
        b[0].observation.farms[0]['tiles'][4][4] = {'kind': 'WEED'}
        ta, tb = self.eod(a, env), self.eod(b, copy.deepcopy(env))
        self.assertEqual(ta[0]['weed_rng_calls'], 49)
        self.assertEqual(ta[0]['shops_after'], tb[0]['shops_after'])

    def test_08_distribution_across_farms_not_just_own_farm_count(self):
        a, env = R.fixture(self.e, 18, step=71, weed_chance=0)
        b = copy.deepcopy(a)
        for x in range(5):
            a[0].observation.farms[0]['tiles'][0][x] = {'kind': 'WEED'}
            b[0].observation.farms[1]['tiles'][0][x] = {'kind': 'WEED'}
        ta, tb = self.eod(a, env), self.eod(b, copy.deepcopy(env))
        self.assertEqual(ta[0]['weed_rng_calls'], 45)
        self.assertEqual(ta[0]['shops_after'], tb[0]['shops_after'])

    def test_09_audit_is_observational_not_a_rng_intervention(self):
        a, env = R.fixture(self.e, 5, step=71, weed_chance=0.25)
        b, other_env = copy.deepcopy(a), copy.deepcopy(env)
        self.e._end_of_day(a, env, 2)
        trace = self.eod(b, other_env)
        self.assertEqual(a, b)
        self.assertEqual(env, other_env)
        self.assertEqual(trace[0]['weed_rng_calls'], 50)
        self.assertGreater(sum(f['new_weeds'] for f in trace[0]['farms']), 0)

    def test_10_audit_restores_functions_after_exception(self):
        before = (self.e._spawn_weeds, self.e._end_of_day)
        with self.assertRaisesRegex(RuntimeError, 'sentinel'):
            with R.TownAudit(self.e):
                raise RuntimeError('sentinel')
        self.assertEqual(before, (self.e._spawn_weeds, self.e._end_of_day))
        self.assertFalse(hasattr(self.e, '_town_audit_attached'))

    def test_11_nested_audits_are_rejected(self):
        with R.TownAudit(self.e):
            with self.assertRaises(RuntimeError):
                with R.TownAudit(self.e):
                    pass

    def test_12_a_vs_a_passes_exact_comparison(self):
        a, env = R.fixture(self.e, 28, step=71)
        b = copy.deepcopy(a)
        ta, tb = self.eod(a, env), self.eod(b, copy.deepcopy(env))
        self.assertEqual(a, b)
        self.assertEqual(ta, tb)
        self.assertTrue(R.compare_traces(ta, tb)['same_shop_path'])

    def test_13_no_silent_truncation_of_trace_lengths(self):
        a = R.planting_pair(self.e)['PASS']
        with self.assertRaises(ValueError):
            R.compare_traces([a], [a, a])

    def test_14_empty_trace_is_not_a_false_green_control(self):
        with self.assertRaises(ValueError):
            R.compare_traces([], [])

    def test_15_seed_and_step_alignment_are_required(self):
        a = R.planting_pair(self.e)['PASS']
        for key in ('seed', 'step', 'day'):
            b = copy.deepcopy(a)
            b[key] += 1
            with self.subTest(field=key), self.assertRaises(ValueError):
                R.compare_traces([a], [b])

    def test_16_duplicate_or_skipped_days_are_rejected(self):
        a = R.planting_pair(self.e)['PASS']
        for day in (a['day'], a['day'] + 2):
            b = copy.deepcopy(a)
            b['day'] = day
            b['step'] += 24
            with self.subTest(day=day), self.assertRaises(ValueError):
                R.compare_traces([a, b], [a, b])

    def test_17_incomplete_evidence_is_rejected(self):
        a = R.planting_pair(self.e)['PASS']
        b = copy.deepcopy(a)
        del b['weed_rng_calls']
        with self.assertRaises(ValueError):
            R.compare_traces([a], [b])

    def test_18_shop_cap_leaves_rng_activity_but_no_new_shop(self):
        state, env = R.fixture(self.e, 0, step=647, weed_chance=0)
        state[0].observation.town['unlocked_shops'] = ['YARN_STORE'] * 8
        trace = self.eod(state, env, day=26)
        self.assertEqual(trace[0]['weed_rng_calls'], 50)
        self.assertEqual(trace[0]['new_shops'], [])
        self.assertEqual(len(trace[0]['shops_after']), 8)

    def test_19_nonunlock_day_has_no_immediate_shop_delta(self):
        state, env = R.fixture(self.e, 0, step=47, weed_chance=0)
        self.assertEqual(self.eod(state, env, day=1)[0]['new_shops'], [])

    def test_20_all_occupied_tiles_consume_zero_weed_draws(self):
        state, env = R.fixture(self.e, 0, step=71, weed_chance=0)
        for farm in state[0].observation.farms:
            for y in range(5):
                for x in range(5):
                    farm['tiles'][y][x] = {'kind': 'WEED'}
        trace = self.eod(state, env)
        self.assertEqual(trace[0]['weed_rng_calls'], 0)
        self.assertEqual(trace[0]['shops_after'], [random.Random(2).choice(sorted(self.e.SHOPS))])

    def test_21_buy_land_changes_rng_exposure(self):
        state, env = R.fixture(self.e, 0, step=71, weed_chance=0)
        self.e._do_buy_land(state[0].observation.farms[0], 10)
        self.assertEqual(self.eod(state, env)[0]['weed_rng_calls'], 75)

    def test_22_natural_default_pass_game_reaches_large_tomato_quote(self):
        result = R.run_pass_season(self.e, 7040)
        self.assertEqual(result['official_callbacks'], 719)
        self.assertEqual(result['terminal_status'], ['DONE', 'DONE'])
        self.assertEqual(result['final_money'], [3000.0, 3000.0])
        self.assertEqual(result['first_quote_at_target'], {'step': 685, 'price': 1491, 'inventory': 9271})
        self.assertEqual(result['peak_pre_market_quote'], 1803)
        self.assertEqual(result['shops'], ['PIZZA_SHOP'] * 4 + ['FARMERS_MARKET', 'PIZZA_SHOP', 'FARMERS_MARKET', 'PET_CAFE'])
        self.assertEqual(len(result['town_trace']), 29)
        unlock_days = [row['day'] + 1 for row in result['town_trace'] if row['new_shops']]
        self.assertEqual(unlock_days, list(range(3, 25, 3)))

    def test_23_pin_engine_shim_never_initializes_an_episode(self):
        with self.assertRaises(RuntimeError):
            self.e.resolve_episode_seed(None)

    def test_24_panel_uses_256_unique_seeds_not_1024_independent_games(self):
        flips = sum(not R.planting_pair(self.e, seed)['comparison']['same_shop_path'] for seed in range(256))
        self.assertEqual(flips, 164)

    def test_25_loader_restores_import_environment(self):
        missing = object()
        names = ('kaggle_environments', 'kaggle_environments.utils')
        before = {name: sys.modules.get(name, missing) for name in names}
        R.load_engine(ENGINE_PATH)
        self.assertEqual(before, {name: sys.modules.get(name, missing) for name in names})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', type=Path, default=ENGINE_PATH)
    args, rest = parser.parse_known_args()
    ENGINE_PATH = args.engine
    unittest.main(argv=[sys.argv[0], *rest])
