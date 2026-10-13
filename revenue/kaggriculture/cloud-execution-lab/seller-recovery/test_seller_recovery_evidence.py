# SPDX-License-Identifier: Apache-2.0
"""Validate the compact seller-recovery handoff without executing the actor."""
from __future__ import annotations
import ast
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent


class EvidenceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = json.loads((HERE / 'CURRENT-RESULTS.json').read_text())
        cls.pins = json.loads((HERE / 'CURRENT-SOURCE-PINS.json').read_text())
        cls.library = json.loads((HERE / 'LIBRARY-EVIDENCE.json').read_text())

    def test_source_and_input_identity(self):
        self.assertEqual(self.index['source_checkpoint'], self.pins['source_ref'])
        self.assertEqual(len(self.pins['sha256']), self.pins['source_count'])
        self.assertEqual(self.index['input']['encoded_sha256'],
            '6d850535bc06fd9d366119365651e789c32ec8a48c96bedaa992fd19a1ff060e')
        self.assertEqual(self.index['input']['decoded_sha256'],
            '75f39921d9a749b50b84101f34f8119b51f9646d2ab725d8453f17fdee66083f')
        self.assertEqual(self.index['input']['observations'], 719)

    def test_full_current_source_discontinuity(self):
        result = self.index['cases']['baseline_entry450']
        self.assertEqual(result['calls_per_actor'], 719)
        self.assertTrue(result['fallback_equals_uninterrupted_action'])
        self.assertTrue(result['all_routes_equal'])
        self.assertEqual(result['later_action_differences'], [451, 453])
        self.assertFalse(result['continuity_preserved'])
        self.assertEqual(result['actual_parent_events'], [
            {'parent_calls': 719, 'transform_calls': 719},
            {'parent_calls': 719, 'transform_calls': 718},
        ])

    def test_exact_lost_sale_witnesses(self):
        result = self.index['cases']['baseline_entry450']
        self.assertEqual(result['step451']['reference_market'], [['SELL', 'STRAWBERRY', 10]])
        self.assertEqual(result['step451']['recovered_market'], [[]])
        self.assertEqual(result['step453']['reference_market'], [['SELL', 'MILK', 3]])
        self.assertEqual(result['step453']['recovered_market'], [])
        self.assertTrue(result['step451']['route_equal'])
        self.assertTrue(result['step453']['route_equal'])

    def test_bounded_completed_state_rehydration(self):
        result = self.index['cases']['bounded_rehydration_entry450_through460']
        self.assertEqual(result['calls_per_actor'], 461)
        self.assertEqual(result['intervention']['restore_completed_fields'],
            ['planned', 'pending', 'previous', 'observed_harvests'])
        self.assertTrue(result['intervention']['observe_skipped'])
        self.assertEqual(result['later_action_differences'], [])
        self.assertEqual(result['later_seller_state_differences_count'], 0)
        self.assertTrue(result['continuity_preserved'])

    def test_interrupted_replanning_is_not_recreated(self):
        result = self.index['cases']['negative_replan447_through460']
        self.assertEqual(result['cancel_step'], 447)
        self.assertTrue(result['fallback_equals_uninterrupted_action'])
        self.assertEqual(result['later_action_differences'], [449, 453])
        self.assertFalse(result['continuity_preserved'])
        self.assertEqual(result['step449']['reference_market'], [['SELL', 'WHEAT', 4]])
        self.assertEqual(result['step449']['recovered_market'],
                         [['SELL', 'WHEAT', 4], ['SELL', 'MILK', 3]])

    def test_full_evidence_locator_is_bound(self):
        self.assertEqual(self.index['library_evidence'], self.library)
        self.assertEqual(self.library['bytes'], 503295)
        self.assertEqual(self.library['sha256'],
            'c08bc3b79335e6ddb7b2f1576e4f8294b90d1904b6af0d41323457d76b305796')

    def test_reports_are_hash_bound(self):
        for case in self.index['cases'].values():
            report = case['report']
            self.assertEqual(len(report['sha256']), 64)
            self.assertEqual(len(report['decoded_sha256']), 64)
            self.assertGreater(report['decoded_bytes'], report['bytes'])

    def test_no_expected_actions_or_outcomes_enter_runtime_inputs(self):
        tree = ast.parse((HERE / 'check_seller_recovery.py').read_text())
        keys = [n.slice.value for n in ast.walk(tree)
                if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant)
                and isinstance(n.slice.value, str)]
        self.assertNotIn('expected_action', keys)
        self.assertNotIn('original_scores', keys)
        self.assertNotIn('info', keys)

    def test_evidence_category_is_explicit(self):
        self.assertEqual(self.index['scope']['new_games'], 0)
        self.assertEqual(self.index['scope']['engine_interpreter_calls'], 0)
        self.assertFalse(self.index['scope']['policy_strength_claim'])
        self.assertFalse(self.index['scope']['canonical_runtime_changed'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
