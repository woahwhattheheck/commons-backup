# SPDX-License-Identifier: Apache-2.0
"""Pinned-engine continuation and real current-class opening parity.

This is a component regression test, not a new tournament or economic gate.
The existing unchanged evaluator loader supplies the exact official engine.
No hosted match, full game or game-strength claim is made.
"""
from copy import deepcopy
import json
import random
import sys
import unittest

from test_selected_snapshot import (
    PACKAGE, SnapshotGraphTests, CurrentRuntimeTests, authenticate_package,
    fingerprint, import_module, predecessor,
)
from selected_unit_snapshot import selected_unit_snapshot

COUNTS = {'snapshot_pairs': 0, 'interpreter_calls': 0,
          'runtime_act_calls': 0, 'native_snapshot_calls': 0,
          'borrowed_pair_snapshots': 0, 'completed_parent_callbacks': 0}


def pass_action():
    return {'farmer': ['PASS'], 'hands': [], 'market': []}


class PinnedEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        authenticate_package(PACKAGE)
        sys.path.insert(0, str(PACKAGE))
        cls.ev = import_module('quarry_exact_evaluator', PACKAGE / 'checks/reference/evaluator/evaluate.py')
        cls.engine, cls.hashes = cls.ev.get_engine(
            PACKAGE / 'checks/reference/engine', PACKAGE / 'checks/reference/evaluator/loader.py')

    def fixture(self, seed=9922999):
        S, e = self.ev.Struct, self.engine
        cfg = S({k: v.get('default') if isinstance(v, dict) else v
                 for k,v in e.specification['configuration'].items()})
        cfg.seed = seed
        env = S(configuration=cfg, done=False, info={})
        state = [S(observation=S(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
        e.interpreter(state, env)
        COUNTS['interpreter_calls'] += 1
        return state, env

    def test_native_snapshots_have_identical_full_engine_continuations(self):
        # Constructed selected-unit pairs, then full unit->market->EOD callbacks.
        # Each side has its own complete state/environment and the same RNG input.
        for seat in (0, 1):
            for step in (1, 22, 23, 46, 47, 718):
                for stock in (0, 1, 98, 100):
                    for amount in (0, 1, 4):
                        state, env = self.fixture()
                        for player, s in enumerate(state):
                            s.observation.update(player=player, step=step,
                                day=step // 24, hour=step % 24)
                        obs = dict(state[seat].observation)
                        own = deepcopy(obs['farms'][seat])
                        private = deepcopy(obs['private'])
                        private['shed']['WHEAT'] = stock
                        pair = (own, private)
                        a, b = predecessor(obs, seat, pair), selected_unit_snapshot(obs, seat, pair)
                        self.assertEqual(fingerprint(a, obs, pair), fingerprint(b, obs, pair))
                        left, left_env = deepcopy((state, env))
                        right, right_env = deepcopy((state, env))
                        for world, snapshot in ((left, a), (right, b)):
                            copied = deepcopy(snapshot)
                            world[seat].observation = self.ev.Struct(copied)
                            world[1-seat].observation['farms'] = copied['farms']
                            world[1-seat].observation['market'] = copied['market']
                            world[1-seat].observation['town'] = copied['town']
                            world[seat].action = {'farmer': ['PASS'], 'hands': [],
                                'market': [['SELL', 'WHEAT', amount]]}
                            world[1-seat].action = {'farmer': ['PASS'], 'hands': [],
                                'market': [['BUY_PRODUCT', 'WHEAT', 1]]}
                        rng = random.getstate()
                        self.engine.interpreter(left, left_env)
                        random.setstate(rng)
                        self.engine.interpreter(right, right_env)
                        self.assertEqual(fingerprint(left, left_env), fingerprint(right, right_env))
                        COUNTS['snapshot_pairs'] += 1
                        COUNTS['interpreter_calls'] += 2

    def test_real_current_final_pressure_class_openings_both_seats(self):
        # Use the actual main._new_instance and all default runtime collaborators.
        # Only the imported runtime's selected-snapshot copy seam differs.
        CurrentRuntimeTests.setUpClass()
        old_module, new_module = CurrentRuntimeTests.old, CurrentRuntimeTests.new
        main = import_module('quarry_exact_main', PACKAGE / 'main.py')
        features = json.loads((PACKAGE / 'TITAN-CONFIG.json').read_text())
        missing = object()
        saved_runtime = sys.modules.get('titan_runtime', missing)
        try:
            for seed in (9922999, 9922023):
                for seat in (0, 1):
                    agents = []
                    records = [[], []]
                    for i, module in enumerate((old_module, new_module)):
                        sys.modules['titan_runtime'] = module
                        agent = main._new_instance(PACKAGE, features)
                        bound = agent._selected_snapshot
                        def capture(obs, returned=None, *, _bound=bound, _rows=records[i], _agent=agent):
                            out = _bound(obs, returned)
                            pair = getattr(_agent.consumer, 'selected_post_units', None)
                            _rows.append(fingerprint(out, obs, pair))
                            COUNTS['native_snapshot_calls'] += 1
                            if out is not None and pair is not None and out['private'] is pair[1]:
                                COUNTS['borrowed_pair_snapshots'] += 1
                            return out
                        agent._selected_snapshot = capture
                        agents.append(agent)
                    state, env = self.fixture(seed)
                    for step in range(24):
                        for s in state:
                            s.observation.step = step
                        observation = deepcopy(state[seat].observation)
                        records[0].clear()
                        records[1].clear()
                        before = fingerprint(observation)
                        rng = random.getstate()
                        left = agents[0].act(deepcopy(observation), env.configuration)
                        random.setstate(rng)
                        right = agents[1].act(deepcopy(observation), env.configuration)
                        COUNTS['runtime_act_calls'] += 2
                        self.assertEqual(left, right, (seed, seat, step, left, right))
                        self.assertEqual(records[0], records[1], (seed, seat, step))
                        self.assertEqual(fingerprint(observation), before)
                        for agent in agents:
                            self.assertEqual(agent.diagnostics.get('status'), 'completed',
                                             (seed, seat, step, agent.diagnostics))
                        COUNTS['completed_parent_callbacks'] += 1
                        state[seat].action = deepcopy(left)
                        # Preserve raw returned rows; do not use loader.play's
                        # stricter surplus-hand assertion or truncate actors.
                        state[1-seat].action = self.engine.starter_agent(
                            deepcopy(state[1-seat].observation))
                        self.engine.interpreter(state, env)
                        COUNTS['interpreter_calls'] += 1
            self.assertGreater(COUNTS['borrowed_pair_snapshots'], 0)
        finally:
            if saved_runtime is missing:
                sys.modules.pop('titan_runtime', None)
            else:
                sys.modules['titan_runtime'] = saved_runtime


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PinnedEngineTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'success': result.wasSuccessful(), 'counts': COUNTS}, sort_keys=True))
    sys.exit(0 if result.wasSuccessful() else 1)
