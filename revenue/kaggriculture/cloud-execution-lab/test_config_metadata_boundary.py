# SPDX-License-Identifier: Apache-2.0
"""Contracts for the private experiment-metadata configuration boundary."""
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parent
if ROOT.name == 'checks':
    ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main


class StrictFeatures:
    """Small strict stand-in that rejects every unsupported public key."""

    def __init__(self, *, consumer='frozen', terminal_route=False,
                 fourth_quadrant=False, budget_seconds=1.0,
                 reserve_seconds=0.01):
        self.consumer = consumer
        self.terminal_route = terminal_route
        self.fourth_quadrant = fourth_quadrant
        self.budget_seconds = float(budget_seconds)
        self.reserve_seconds = float(reserve_seconds)


class FakeTitanAgent:
    def __init__(self, features, fourth_quadrant_admission=None):
        self.features = features
        self.fourth_quadrant_admission = fourth_quadrant_admission
        self.diagnostics = {}


class ConfigMetadataBoundaryTests(unittest.TestCase):
    def make_agent(self, feature_data):
        runtime = ModuleType('titan_runtime')
        runtime.Features = StrictFeatures
        runtime.TitanAgent = FakeTitanAgent
        runtime.load = lambda *args, **kwargs: self.fail('optional admission loaded')
        with patch.dict(sys.modules, {'titan_runtime': runtime}):
            return main._new_instance(ROOT, feature_data)

    def test_private_experiment_metadata_is_ignored_without_mutating_input(self):
        feature_data = {
            'consumer': 'frozen',
            'budget_seconds': 0.95,
            '_ablation': {'name': 'flip-unfav-apex0226'},
            '_experiment': 'titan-v5-3000-wave1',
        }
        original = dict(feature_data)

        agent = self.make_agent(feature_data)

        self.assertEqual(feature_data, original)
        self.assertEqual(agent.features.consumer, 'frozen')
        self.assertEqual(agent.features.budget_seconds, 0.95)
        self.assertFalse(agent.features.fourth_quadrant)

    def test_unknown_public_key_still_fails_closed(self):
        with self.assertRaisesRegex(TypeError, 'market_pressur'):
            self.make_agent({
                'consumer': 'frozen',
                'market_pressur': True,
            })

    def test_filter_only_reserves_top_level_string_underscore_keys(self):
        nested = {'_ablation': 'behavioral data inside a public value'}
        source = {
            'consumer': 'frozen',
            '_ablation': 'harness annotation',
            'metadata': nested,
        }

        filtered = main._runtime_feature_data(source)

        self.assertEqual(filtered, {
            'consumer': 'frozen',
            'metadata': nested,
        })
        self.assertIs(filtered['metadata'], nested)
        self.assertIn('_ablation', source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
