# SPDX-License-Identifier: Apache-2.0
"""Narrow late-choice binding tests using the actual supplied Arlene controller."""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from late_milk import LateMilkChoice, MAIN, MILK_EXIT

ARLENE = None
CFG = {'turnsPerDay': 24, 'episodeSteps': 720}


def observation(step=577, milk=10067):
    farm = {'tiles': [[None for _ in range(10)] for _ in range(10)],
            'farmer': [4, 4], 'hands': [[4, 4] for _ in range(12)], 'money': 10000}
    return {'step': step, 'day': step // 24, 'hour': step % 24, 'player': 0,
            'farms': [deepcopy(farm), deepcopy(farm)], 'town': {'unlocked_shops': []},
            'private': {'shed': {'WOOL': 65}, 'seeds': {}, 'inventories': [{} for _ in range(13)]},
            'market': {'inventory': {p: milk if p == 'MILK' else 10000 for p in ARLENE.PRODUCTS},
                       'prices': {p: 25 for p in ARLENE.PRODUCTS}}}


def make(route=MAIN, enabled=True):
    controller = ARLENE.Agent()
    controller.cur = route
    count = []
    def original(obs, cfg):
        count.append(controller.cur)
        return controller.act(obs)
    return LateMilkChoice(original, controller, enabled=enabled), count


class ChoiceTests(unittest.TestCase):
    def test_future_public_input_does_not_change_original433_rule(self):
        for stock, target in [(10066, MAIN), (10067, MILK_EXIT)]:
            actor, calls = make()
            out = actor.act(observation(433, stock), CFG)
            direct = ARLENE.Agent().act(observation(433, stock))
            self.assertEqual(out, direct)
            self.assertEqual(actor.controller.cur, target)
            self.assertFalse(actor.attempted)
            self.assertEqual(len(calls), 1)

    def test_high_inventory_rechecks_main_at577(self):
        actor, calls = make()
        actor.act(observation(), CFG)
        self.assertEqual(actor.controller.cur, MILK_EXIT)
        self.assertEqual(calls, [MILK_EXIT])
        self.assertTrue(actor.last_choice['changed'])

    def test_low_inventory_can_reverse_old_milk_choice(self):
        actor, calls = make(MILK_EXIT)
        actor.act(observation(milk=10066), CFG)
        self.assertEqual(actor.controller.cur, MAIN)
        self.assertEqual(calls, [MAIN])

    def test_exact_threshold_and_unchanged_choice(self):
        actor, _ = make(MILK_EXIT)
        actor.act(observation(milk=10067), CFG)
        self.assertFalse(actor.last_choice['changed'])
        self.assertEqual(actor.controller.cur, MILK_EXIT)

    def test_calls_before_and_after_checkpoint_do_not_retime(self):
        for step in [434, 576, 578, 600]:
            actor, _ = make()
            actor.act(observation(step), CFG)
            self.assertEqual(actor.controller.cur, MAIN)
            self.assertFalse(actor.attempted)

    def test_disabled_control_preserves_actual_action(self):
        actor, calls = make(enabled=False)
        self.assertEqual(actor.act(observation(), CFG), ARLENE.Agent().act(observation()))
        self.assertEqual(actor.controller.cur, MAIN)
        self.assertEqual(calls, [MAIN])

    def test_other_complete_route_preserved(self):
        actor, _ = make('dc76e4003029ac51')
        actor.act(observation(), CFG)
        self.assertEqual(actor.controller.cur, 'dc76e4003029ac51')
        self.assertEqual(actor.last_choice['reason'], 'other_route')

    def test_existing_prefix_check_is_used(self):
        actor, _ = make()
        actor.controller.R = deepcopy(actor.controller.R)
        actor.controller.R[MILK_EXIT][300] = deepcopy(actor.controller.R[MILK_EXIT][300])
        actor.controller.R[MILK_EXIT][300]['market'] = [['SELL', 'WOOL', 999]]
        actor.act(observation(), CFG)
        self.assertEqual(actor.controller.cur, MAIN)
        self.assertEqual(actor.last_choice['reason'], 'program_prefix_differs')

    def test_same_step_does_not_oscillate(self):
        actor, calls = make()
        actor.act(observation(), CFG)
        actor.act(observation(milk=0), CFG)
        self.assertEqual(actor.controller.cur, MILK_EXIT)
        self.assertEqual(calls, [MILK_EXIT, MILK_EXIT])

    def test_future_sale_cache_follows_actual_route(self):
        actor, _ = make()
        old = actor.controller.future_sells('MILK', 578)
        actor.act(observation(), CFG)
        new = actor.controller.future_sells('MILK', 578)
        direct = ARLENE.Agent(); direct.cur = MILK_EXIT
        self.assertEqual(new, direct.future_sells('MILK', 578))
        self.assertNotEqual(old, new)

    def test_different_configuration_retains_parent(self):
        actor, _ = make()
        actor.act(observation(), dict(CFG, episodeSteps=800))
        self.assertEqual(actor.controller.cur, MAIN)
        self.assertEqual(actor.last_choice['reason'], 'other_configuration')

    def test_unknown_inventory_does_not_switch(self):
        for value in [None, '10067', 10067.0, True]:
            actor, _ = make()
            ob = observation(); ob['market']['inventory']['MILK'] = value
            actor.act(ob, CFG)
            self.assertEqual(actor.controller.cur, MAIN)

    def test_sparse_public_clock_and_detached_input(self):
        actor, _ = make()
        ob = observation(); del ob['step']; before = deepcopy(ob)
        actor.act(ob, CFG)
        self.assertEqual(actor.controller.cur, MILK_EXIT)
        self.assertEqual(ob, before)
        report = actor.reconsider(ob, CFG); report['after'] = 'different'
        self.assertEqual(actor.last_choice['after'], MILK_EXIT)

    def test_actual_sale_override_differs_before_stored_boundary(self):
        # Existing-controller witness: not a new policy or reached game.
        main = ARLENE.Agent(); exit_ = ARLENE.Agent(); exit_.cur = MILK_EXIT
        self.assertEqual(main.R[MAIN][434], exit_.R[MILK_EXIT][434])
        self.assertEqual(main.act(observation(434))['market'], [])
        self.assertEqual(exit_.act(observation(434))['market'], [['SELL', 'WOOL', 1]])


def main():
    global ARLENE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arlene', type=Path, default=Path(__file__).resolve().parent.parent / 'cloud-titan-composition/vendor/base/arlene.py')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('late_milk_actual_arlene', args.arlene)
    ARLENE = importlib.util.module_from_spec(spec); spec.loader.exec_module(ARLENE)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ChoiceTests))
    record = {'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'passed': result.wasSuccessful(), 'arlene_sha256': hashlib.sha256(args.arlene.read_bytes()).hexdigest(),
              'runtime_sha256': hashlib.sha256(Path(__file__).with_name('late_milk.py').read_bytes()).hexdigest(),
              'scope': 'actual-controller binding on constructed observations; not game outcomes'}
    if args.report: args.report.write_text(json.dumps(record, indent=2) + '\n')
    return not result.wasSuccessful()

if __name__ == '__main__': raise SystemExit(main())
