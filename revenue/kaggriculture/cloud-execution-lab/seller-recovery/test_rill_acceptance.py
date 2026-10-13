# SPDX-License-Identifier: Apache-2.0
"""Validate the compact PR10400 seller-recovery acceptance record."""
from __future__ import annotations
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent


class RillAcceptanceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads((HERE / 'RILL-ACCEPTANCE.json').read_text())
        cls.library = json.loads((HERE / 'RILL-LIBRARY-EVIDENCE.json').read_text())

    def test_exact_production_source(self):
        source = self.result['production_candidate']
        self.assertEqual(source['pr'], 10400)
        self.assertEqual(source['runtime_git_blob'],
                         'a1edf5a6fc2d96ed9731f02883bfebc72e522656')
        self.assertEqual(source['runtime_sha256'],
                         'f718b435e58336acb223ee6e6a7ef7f6686d8916dd7f02733888eb9e98eaf066')
        self.assertEqual(source['runtime_bytes'], 18405)

    def test_completed_transform_entry_is_accepted(self):
        case = self.result['independent_results']['transform_entry']
        self.assertEqual(case['calls_per_actor'], 719)
        self.assertTrue(case['fallback_equals_uninterrupted_action'])
        self.assertTrue(case['all_routes_equal'])
        self.assertEqual(case['later_action_differences'], [])
        self.assertEqual(case['later_seller_state_differences_count'], 0)
        self.assertTrue(case['continuity_preserved'])

    def test_completed_after_observer_is_accepted(self):
        case = self.result['independent_results']['after_observe']
        self.assertEqual(case['calls_per_actor'], 719)
        self.assertEqual(case['later_action_differences'], [])
        self.assertEqual(case['later_seller_state_differences_count'], 0)
        self.assertTrue(case['continuity_preserved'])

    def test_interrupted_replanning_is_not_promoted(self):
        case = self.result['independent_results']['interrupted_replan']
        self.assertEqual(case['calls_per_actor'], 461)
        self.assertTrue(case['fallback_equals_uninterrupted_action'])
        self.assertEqual(case['later_action_differences'], [449, 453])
        self.assertFalse(case['continuity_preserved'])

    def test_one_original_parent_call_per_input(self):
        self.assertTrue(self.result['verdict']['one_parent_call_per_input'])
        for case in self.result['independent_results'].values():
            self.assertTrue(all(event['parent_calls'] == case['calls_per_actor']
                                for event in case['actual_parent_events']))

    def test_input_and_scope_are_non_game_evidence(self):
        self.assertEqual(self.result['input']['observations'], 719)
        self.assertFalse(self.result['input']['expected_actions_used_as_actor_inputs'])
        self.assertFalse(self.result['input']['opponent_private_state_used_as_actor_inputs'])
        self.assertEqual(self.result['scope']['games'], 0)
        self.assertEqual(self.result['scope']['engine_interpreter_calls'], 0)
        self.assertEqual(self.result['scope']['runtime_changes_by_acceptor'], 0)

    def test_full_package_is_hash_bound(self):
        self.assertEqual(self.library['bytes'], 465031)
        self.assertEqual(self.library['sha256'],
                         'fa3deb0a52ca03df6101b3e629b418d4b4ccfdc627c1153da9514146184e072d')


if __name__ == '__main__':
    unittest.main(verbosity=2)
