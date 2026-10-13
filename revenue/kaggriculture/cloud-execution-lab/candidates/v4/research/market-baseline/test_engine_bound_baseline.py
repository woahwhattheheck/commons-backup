#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
MODULE = HERE / 'engine_bound_baseline.py'
spec = importlib.util.spec_from_file_location('engine_bound_baseline', MODULE)
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)

# candidates/v4/research/market-baseline -> cloud-execution-lab
ENGINE = HERE.parents[3] / 'reference' / 'engine' / 'kaggriculture.py'


class EngineBoundBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = baseline.load_engine(ENGINE)
        cls.seeds = tuple(range(1, 101))
        cls.paths = [baseline.simulate(cls.engine, seed) for seed in cls.seeds]
        cls.envelope = baseline.envelope(cls.engine)
        cls.curves, cls.crossings, cls.summary = baseline.analyze(
            cls.engine, cls.paths, cls.envelope)

    def test_exact_engine_is_pinned(self):
        self.assertEqual(baseline.git_blob(ENGINE.read_bytes()), baseline.ENGINE_BLOB)

    def test_full_visible_episode_shape(self):
        self.assertEqual(len(self.paths), 100)
        self.assertTrue(all(len(path) == 720 for path in self.paths))
        self.assertEqual(self.paths[0][0]['step'], 0)
        self.assertFalse(self.paths[0][718]['terminal'])
        self.assertTrue(self.paths[0][719]['terminal'])

    def test_sample_paths_stay_inside_exact_all_shop_envelope(self):
        for path in self.paths:
            for row, bound in zip(path, self.envelope):
                for product in self.engine.PRODUCTS:
                    inv = row['inventory'][product]
                    b = bound['products'][product]
                    self.assertGreaterEqual(inv, b['min_inventory'])
                    self.assertLessEqual(inv, b['max_inventory'])

    def test_fertilizer_is_town_flow_control(self):
        for path in self.paths:
            self.assertTrue(all(row['inventory']['FERTILIZER'] == 10000 for row in path))
            self.assertTrue(all(row['price']['FERTILIZER'] == 100 for row in path))
        self.assertEqual(self.summary['FERTILIZER']['seeds_crossing_at_T'], 0)

    def test_seed_1_shop_sequence_binds_weed_rng_before_choice(self):
        self.assertEqual(
            self.paths[0][-1]['shops'],
            ('FARMERS_MARKET', 'FARMERS_MARKET', 'BAKERY', 'BAKERY',
             'BRUNCH_SPOT', 'ICE_CREAM_SHOP', 'BAKERY', 'SMOOTHIE_SHOP'),
        )

    def test_requested_strawberry_and_wool_visible_crossing_receipt(self):
        strawberry = self.summary['STRAWBERRY']
        self.assertEqual(strawberry['seeds_crossing_at_T'], 97)
        self.assertEqual(strawberry['first_at_T_step_min'], 261)
        self.assertEqual(strawberry['first_at_T_step_p50'], 349)
        self.assertEqual(strawberry['first_at_T_step_max'], 681)
        wool = self.summary['WOOL']
        self.assertEqual(wool['seeds_crossing_at_T'], 55)
        self.assertEqual(wool['first_at_T_step_min'], 201)
        self.assertEqual(wool['first_at_T_step_p50'], 389)
        self.assertEqual(wool['first_at_T_step_max'], 657)

    def test_public_diagnostic_never_emits_action(self):
        step = 360
        mid = {}
        for product, bound in self.envelope[step]['products'].items():
            mid[product] = (bound['min_inventory'] + bound['max_inventory']) // 2
        result = baseline.classify(
            self.engine, {'step': step, 'market': {'inventory': mid}}, self.envelope)
        self.assertEqual(result['status'], 'OK')
        self.assertTrue(all(v['status'] == 'WITHIN_PASSIVE_ENVELOPE'
                            for v in result['products'].values()))
        self.assertNotIn('action', result)

    def test_engine_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            altered = Path(td) / 'kaggriculture.py'
            altered.write_bytes(ENGINE.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'Git blob mismatch'):
                baseline.load_engine(altered)


if __name__ == '__main__':
    unittest.main(verbosity=2)
