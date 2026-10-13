"""Arrival handoff tests on exact FLOW and the previously pinned interpreter."""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_town_demand as prior
from flow_scenarios import make_flow_scenario

FLOW = None
EVIDENCE = []


def load_flow(path):
    path = Path(path)
    data = path.read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if actual not in ('1070bcade1c0c3ed72f1f5ea7858621d875c130d',
                      'ddbbe439c93082ab68b2e7e8dcfe302bbee052e7'):
        raise ValueError('FLOW source differs from the tested integration pin')
    spec = importlib.util.spec_from_file_location('_amber_flow', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module._validated_blob = actual
    return module


class FlowBindingTests(unittest.TestCase):
    def make(self, obs=None, cfg=None, draws=None, **kwargs):
        obs = prior.observed() if obs is None else obs
        cfg = prior.config() if cfg is None else cfg
        draws = ('BAKERY',) * 5 if draws is None else draws
        return make_flow_scenario(obs, cfg, prior.ENGINE, FLOW.Scenario,
                                  name='declared', future_shops=draws, **kwargs)

    def test_default_arrival_mapping(self):
        scenario, report = self.make()
        self.assertEqual(scenario.shop_additions,
                         {288: ('BAKERY',), 360: ('BAKERY',), 432: ('BAKERY',),
                          504: ('BAKERY',), 576: ('BAKERY',)})
        self.assertFalse(report['inventory_deltas_applied_by_adapter'])
        self.assertFalse(report['scenario_bank_exhaustive'])
        self.assertIsNone(report['probabilities'])

    def test_known_only_is_not_complete_future(self):
        with self.assertRaises(ValueError):
            make_flow_scenario(prior.observed(), prior.config(), prior.ENGINE,
                               FLOW.Scenario, name='unknown', future_shops=None)

    def test_no_market_after_terminal(self):
        with self.assertRaises(ValueError):
            self.make(prior.observed(719), draws=())

    def test_full_town_accepts_no_future(self):
        scenario, report = make_flow_scenario(
            prior.observed(226, ('YARN_STORE',) * 8), prior.config(), prior.ENGINE,
            FLOW.Scenario, name='full', future_shops=None)
        self.assertEqual(scenario.shop_additions, {})
        self.assertEqual(report['schedule']['coverage'], 'specified_future_scenario')

    def test_terminal_arrival_is_retained_not_applied(self):
        scenario, report = self.make(prior.observed(286),
                                    prior.config(episodeSteps=289), ('YARN_STORE',))
        self.assertEqual(scenario.shop_additions, {})
        self.assertEqual(report['arrivals_after_final_market'],
                         [{'after_step': 287, 'shop': 'YARN_STORE'}])

    def test_custom_coincident_ticks(self):
        scenario, _ = self.make(prior.observed(8, ()),
                               prior.config(turnsPerDay=5, townShopUnlockInterval=2,
                                            townShopSellInterval=3, episodeSteps=22),
                               ('YARN_STORE', 'YARN_STORE'))
        self.assertEqual(scenario.shop_additions,
                         {10: ('YARN_STORE',), 20: ('YARN_STORE',)})

    def test_eight_instance_cap(self):
        scenario, _ = self.make(prior.observed(70, ('YARN_STORE',) * 7),
                               draws=('YARN_STORE',))
        self.assertEqual(scenario.shop_additions, {72: ('YARN_STORE',)})

    def test_missing_extra_unknown_draws(self):
        for draws in [(), ('BAKERY',) * 6, ('MISSING',) * 5]:
            with self.subTest(draws=draws), self.assertRaises(ValueError):
                self.make(draws=draws)

    def test_names_and_mapping(self):
        for name in ['', '   ', None, 9]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                make_flow_scenario(prior.observed(), prior.config(), prior.ENGINE,
                                   FLOW.Scenario, name=name, future_shops=('BAKERY',) * 5)
        with self.assertRaises(ValueError):
            self.make(rival_orders=[])

    def test_input_and_rival_isolation(self):
        obs, cfg = prior.observed(), prior.config()
        original = copy.deepcopy((obs, vars(cfg)))
        rival = {290: [['SELL', 'WOOL', 2]]}
        scenario, report = self.make(obs, cfg, rival_orders=rival)
        scenario.rival_orders[290][0][2] = 9
        self.assertEqual(rival, {290: [['SELL', 'WOOL', 2]]})
        scenario.shop_additions[288] = ('YARN_STORE',)
        self.assertEqual(report['first_active_shop_additions'][288], ('BAKERY',))
        self.assertEqual(original, (obs, vars(cfg)))

    def test_no_price_or_controller_use(self):
        constants = SimpleNamespace(SHOPS=prior.ENGINE.SHOPS,
                                    PRODUCTS=prior.ENGINE.PRODUCTS,
                                    TOWN_CENTER_PRODUCTS=prior.ENGINE.TOWN_CENTER_PRODUCTS,
                                    MAX_SHOP_INSTANCES=prior.ENGINE.MAX_SHOP_INSTANCES)
        scenario, _ = make_flow_scenario(prior.observed(), prior.config(), constants,
                                        FLOW.Scenario, name='pure', future_shops=('BAKERY',) * 5)
        self.assertIsInstance(scenario, FLOW.Scenario)

    def test_new_boundary_cases_match_whole_interpreter(self):
        cases = [
            ('default', 286, 290, ('BAKERY', 'PIZZA_SHOP', 'BRUNCH_SPOT'),
             ('YARN_STORE',), {}),
            ('cap', 70, 74, ('YARN_STORE',) * 7, ('YARN_STORE',), {}),
            ('custom', 8, 12, (), ('YARN_STORE',),
             {'turnsPerDay': 5, 'townShopUnlockInterval': 2,
              'townShopSellInterval': 3, 'townCenterSellInterval': 7}),
            ('last', 286, 287, (), ('YARN_STORE',), {}),
        ]
        m = prior.ENGINE
        for label, start, end, shops, path, changes in cases:
            for seat in (0, 1):
                with self.subTest(case=label, seat=seat):
                    cfg = prior.config(episodeSteps=end + 2, startingMoney=100_000, **changes)
                    state = prior.state_for(prior.observed(start, shops), cfg)
                    for actor in state:
                        actor.observation.private['shed'].update(WOOL=20, EGG=20, WHEAT=20,
                                                                FERTILIZER=5)
                    state[0].observation.market['inventory']['WOOL'] = 9900
                    state[0].observation.market['inventory']['WHEAT'] = 9900
                    state[0].observation.market['inventory']['EGG'] = 9900
                    obs = copy.deepcopy(vars(state[seat].observation))
                    own = {t: [['SELL', 'WOOL', 2], ['BUY_PRODUCT', 'WHEAT', 1],
                               ['SELL', 'EGG', 1]] for t in range(start, end + 1)}
                    rival = {t: [['SELL', 'WOOL', 1], ['SELL', 'WHEAT', 1]]
                             for t in range(start, end + 1)}
                    scenario, binding = self.make(obs, cfg, path, rival_orders=rival)
                    offer = SimpleNamespace(route_id='same-queue', orders=[
                        {'step': t, 'slot': j, 'order': order, 'delta': 0}
                        for t, queue in own.items() for j, order in enumerate(queue)])
                    flow = FLOW.value_route(offer, obs, vars(cfg), m, scenario, retain_trace=True)
                    env = SimpleNamespace(configuration=cfg, info={'seed': 0}, done=False)
                    draws = prior.ControlledDraws(path)
                    trajectory = []
                    with patch.object(m.random, 'Random', lambda unused: draws):
                        for t in range(start, end + 1):
                            for actor in state:
                                actor.observation.step = t
                            state[seat].action['market'] = own[t]
                            state[1-seat].action['market'] = rival[t]
                            m.interpreter(state, env)
                            trajectory.append({'step': t,
                                'own_cash': state[seat].observation.farms[seat]['money'],
                                'rival_cash': state[seat].observation.farms[1-seat]['money'],
                                'inventory': copy.deepcopy(state[0].observation.market['inventory'])})
                    actual = trajectory[-1]
                    self.assertEqual(flow['final_market_inventory'], actual['inventory'])
                    self.assertEqual(flow['final_marked_cash'], actual['own_cash'])
                    self.assertEqual(flow['rival_receipts'] - flow['rival_product_spend'],
                                     actual['rival_cash'] - cfg.startingMoney)
                    self.assertEqual(draws.shops, [])
                    for t in range(start, end + 1):
                        last = [r for r in flow['trace'] if r['step'] == t][-1]
                        self.assertEqual(last['marked_cash'], trajectory[t-start]['own_cash'])
                    EVIDENCE.append({'case': label, 'seat': seat, 'binding': binding,
                                     'flow': flow, 'official': trajectory})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--flow', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    global FLOW
    prior.ENGINE = prior.load_engine(args.engine)
    FLOW = load_flow(args.flow)
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(FlowBindingTests))
    report = {'methods': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'passed': result.wasSuccessful(),
              'new_controlled_cases': len(EVIDENCE),
              'new_official_transitions': sum(len(x['official']) for x in EVIDENCE),
              'full_games': 0, 'engine_sha256': prior.PIN,
              'flow_git_blob': FLOW._validated_blob,
              'adapter_sha256': hashlib.sha256(Path(__file__).with_name('flow_scenarios.py').read_bytes()).hexdigest(),
              'evidence': EVIDENCE}
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
