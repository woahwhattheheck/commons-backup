# SPDX-License-Identifier: MIT
"""Input and family-completeness checks for the offline WOOL experiment."""
from copy import deepcopy
import gzip
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock
import check_joint_wool_hypotheses as check

ROOT = Path(__file__).parent
PRODUCTS = ['WHEAT','CARROT','TOMATO','STRAWBERRY','MELON','EGG','MILK','WOOL','FERTILIZER']


def saved_fixture(carrot=0):
    payload = {'schema': 'titan.public-own-history.v1',
        'configuration': {'episodeSteps': 720, 'turnsPerDay': 24, 'shedCapacity': 100,
                          'maxMarketOrdersPerTurn': 10},
        'observation': {'step': 718, 'player': 0},
        'selected_action': {'farmer': ['PASS'], 'hands': [], 'market': []}}
    raw = json.dumps(payload, sort_keys=True).encode(); compressed = gzip.compress(raw, mtime=0)
    saved = {'input_decoded_sha256': check.sha(raw), 'input_compressed_sha256': check.sha(compressed),
             'original_action': deepcopy(payload['selected_action']),
             'family': {'status': 'insufficient_joint_history'}, 'training': []}
    for step in (646, 670, 694):
        intervals = {}
        for product in PRODUCTS:
            if product in ('WHEAT', 'FERTILIZER'):
                intervals[product] = {'status': 'unidentified'}
                continue
            lo = carrot if product == 'CARROT' else 0
            intervals[product] = dict(step=step, product=product, lower=lo,
                upper=100 if product=='WOOL' else lo, admitted_lower=lo, admitted_upper=lo,
                reason='floor_censored' if product=='WOOL' else 'identified', exact=product!='WOOL')
        saved['training'].append({'step': step, 'status': 'reconciled', 'intervals': intervals})
    return saved, payload, raw, compressed


class WoolExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.flow = check.load(Path(os.environ.get('TITAN_WOOL_FLOW', ROOT/'flow.py')), '_wool_boundary_flow')
        cls.joint = check.load(Path(os.environ.get('TITAN_WOOL_JOINT', ROOT/'joint_terminal_history.py')), '_wool_boundary_joint')

    def test_restore_keeps_censoring_and_does_not_add_operating_zeros(self):
        saved, _, _, _ = saved_fixture()
        original = deepcopy(saved)
        history = check.restore_history(saved, self.flow, 718, 24)
        self.assertFalse(history.records['WOOL'][694].exact)
        self.assertEqual(history.records['WOOL'][694].upper, 100)
        self.assertFalse(history.records['WHEAT'])
        self.assertFalse(history.records['FERTILIZER'])
        self.assertEqual(saved, original)

    def test_unknown_nonoperating_sample_does_not_become_zero(self):
        saved, _, _, _ = saved_fixture()
        saved['training'][0]['intervals']['CARROT'] = {'status': 'unknown_own_fill'}
        history = check.restore_history(saved, self.flow, 718, 24)
        self.assertNotIn(646, history.records['CARROT'])
        family = self.joint.build_joint_terminal_scenarios(history, PRODUCTS, 718, **check.arguments(PRODUCTS))
        self.assertFalse(family['ready'])
        self.assertEqual(family['status'], 'insufficient_joint_history')

    def test_future_and_duplicate_steps_are_rejected(self):
        for change in ('future', 'duplicate'):
            with self.subTest(change=change):
                saved, _, _, _ = saved_fixture()
                if change == 'future': saved['training'][0]['step'] = 718
                else: saved['training'].append(deepcopy(saved['training'][0]))
                with self.assertRaises(ValueError):
                    check.restore_history(saved, self.flow, 718, 24)

    def test_saved_interval_identity_is_checked(self):
        saved, _, _, _ = saved_fixture()
        saved['training'][0]['intervals']['CARROT']['product'] = 'EGG'
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            check.restore_history(saved, self.flow, 718, 24)

    def test_explicit_hypotheses_keep_slots_and_all_stock_completions(self):
        saved, _, _, _ = saved_fixture()
        history = check.restore_history(saved, self.flow, 718, 24)
        family = self.joint.build_joint_terminal_scenarios(history, PRODUCTS, 718, **check.arguments(PRODUCTS))
        self.assertTrue(family['ready'])
        self.assertEqual(family['joint_support'], 3)
        self.assertEqual(len(family['scenarios']), 12)
        self.assertIsNone(family['scenario_probabilities'])
        self.assertEqual({s['shed'].get('WOOL',0) for s in family['scenarios']}, {0,25,50})
        gap = [s for s in family['scenarios'] if len(s['market']) == 10]
        self.assertEqual(len(gap), 6)
        self.assertTrue(all(s['market'][0] == [] for s in gap))

    def test_scenario_limit_returns_no_trimmed_family(self):
        saved, _, _, _ = saved_fixture()
        history = check.restore_history(saved, self.flow, 718, 24)
        kwargs = check.arguments(PRODUCTS); kwargs['max_scenarios'] = 1
        family = self.joint.build_joint_terminal_scenarios(history, PRODUCTS, 718, **kwargs)
        self.assertFalse(family['ready'])
        self.assertEqual(family['status'], 'scenario_limit')
        self.assertEqual(family['scenarios'], [])

    def test_joint_capacity_failure_preserves_action_without_consumer_calls(self):
        saved, payload, raw, compressed = saved_fixture(carrot=60)
        deps = NS(engine=NS(PRODUCTS=PRODUCTS)); cases = Mock(); ti = Mock()
        out = check.evaluate_saved(saved,payload,raw,compressed,deps,cases,ti,self.flow,self.joint)
        self.assertEqual(out['family']['status'], 'joint_capacity_exceeded')
        self.assertEqual(out['family']['scenarios'], [])
        self.assertEqual(out['fallback_action'], payload['selected_action'])
        self.assertNotIn('choices', out)
        self.assertFalse(out['by_objective'])
        self.assertTrue(all(v == 0 for v in out['counts'].values()))
        cases.own_unit_snapshot.assert_not_called(); ti.build_terminal_inputs.assert_not_called()

    def test_result_map_is_not_named_choices(self):
        source = Path(__file__).with_name('check_joint_wool_hypotheses.py').read_text(encoding='utf-8')
        self.assertNotIn("'choices'", source)
        self.assertIn("'by_objective'", source)

    def test_input_binding_failure_precedes_every_consumer(self):
        saved, payload, raw, compressed = saved_fixture()
        saved['input_compressed_sha256'] = 'not-the-input'
        deps = Mock(); cases = Mock(); ti = Mock(); joint = Mock()
        with self.assertRaisesRegex(ValueError, 'different identities'):
            check.evaluate_saved(saved,payload,raw,compressed,deps,cases,ti,self.flow,joint)
        joint.build_joint_terminal_scenarios.assert_not_called()
        cases.own_unit_snapshot.assert_not_called(); ti.build_terminal_inputs.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
