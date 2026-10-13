# SPDX-License-Identifier: Apache-2.0
"""Regression coverage for SpatialTempo committed same-step replay."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spatial_tempo import SpatialTempo


class Mechanics:
    @staticmethod
    def _farmer_position(farm, worker):
        return farm['farmer'] if worker == 0 else farm['hands'][worker - 1]


def row():
    return {'farmer': ['PASS'], 'hands': [], 'market': []}


def observation(step):
    return {
        'step': step,
        'day': step // 24,
        'player': 0,
        'farms': [{
            'farmer': [0, 0],
            'hands': [],
            'tiles': [[None for _ in range(10)] for _ in range(10)],
        }],
        'private': {'inventories': [{}], 'shed': {}, 'seeds': {}},
    }


def committed(step, *, day=None):
    plan = {
        'step': step,
        'end': step + 2,
        'route': 'r',
        'origin': (0, 0),
        'goal': (0, 0),
        'replacement': [['WATER'], ['PASS']],
    }
    return {
        'patches': {},
        'plans': {0: plan},
        'events': [{'kind': 'fixture', 'step': step, 'worker': 0}],
        'reserved': {(1, 1)},
        'active': {0: step + 2},
        'day': step // 24 if day is None else day,
        'step': step,
    }


class SpatialSameStepReplayTest(unittest.TestCase):
    def begin(self, committed_state, now):
        tempo = SpatialTempo(Mechanics())
        tempo._committed = deepcopy(committed_state)
        pristine = {'r': [row() for _ in range(48)]}
        controller = SimpleNamespace(cur='r', R=deepcopy(pristine))
        tempo._begin(controller, pristine, observation(now))
        return tempo, controller

    def test_same_step_preserves_committed_plan_and_replays_patch(self):
        tempo, controller = self.begin(committed(10), 10)

        self.assertIn(0, tempo.plans)
        self.assertEqual(controller.R['r'][10]['farmer'], ['WATER'])
        self.assertEqual(tempo.events, [{'kind': 'fixture', 'step': 10, 'worker': 0}])
        self.assertEqual(tempo.reserved, {(1, 1)})

    def test_backward_step_still_resets_committed_state(self):
        tempo, controller = self.begin(committed(10), 9)

        self.assertEqual(tempo.plans, {})
        self.assertEqual(controller.R['r'][10]['farmer'], ['PASS'])
        self.assertEqual(tempo.events, [])

    def test_new_day_still_resets_committed_state(self):
        state = committed(23, day=0)
        state['plans'][0]['end'] = 26
        tempo, controller = self.begin(state, 24)

        self.assertEqual(tempo.plans, {})
        self.assertEqual(controller.R['r'][24]['farmer'], ['PASS'])
        self.assertEqual(tempo.events, [])


if __name__ == '__main__':
    unittest.main()
