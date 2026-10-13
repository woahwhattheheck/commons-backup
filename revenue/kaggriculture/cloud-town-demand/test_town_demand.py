"""Source-pinned tests; uses the real interpreter, with controlled future draws.

The unavailable framework seed helper import is removed at load time only.
Initialization is not invoked. All engine functions are otherwise unchanged.
"""
from __future__ import annotations
import argparse
import ast
import copy
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from town_demand import DemandRules, build_schedule, scenario_family

PIN = 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e'
EVIDENCE = []
ENGINE = None
ENGINE_PATH = None


def load_engine(filename):
    global ENGINE_PATH
    filename = Path(filename)
    code = filename.read_bytes()
    if hashlib.sha256(code).hexdigest() != PIN:
        raise ValueError('Engine differs from the recorded source pin')
    tree = ast.parse(code, str(filename))
    removed = [n for n in tree.body if isinstance(n, ast.ImportFrom)
               and n.module == 'kaggle_environments.utils']
    if len(removed) != 1:
        raise ValueError('Unexpected framework import shape')
    tree.body = [n for n in tree.body if n not in removed]
    def no_framework_seed(*args, **kwargs):
        raise AssertionError('These tests do not initialize or resolve hidden seeds')
    namespace = {'__file__': str(filename), '__name__': 'pinned_town_mechanics',
                 'resolve_episode_seed': no_framework_seed}
    exec(compile(tree, str(filename), 'exec'), namespace)
    ENGINE_PATH = str(filename)
    return SimpleNamespace(**namespace)


def config(**changes):
    values = dict(episodeSteps=720, turnsPerDay=24, boardSize=10,
                  startingMoney=3000, weedSpawnChance=0, shedCapacity=100,
                  townShopUnlockInterval=3, townShopSellInterval=4,
                  townCenterSellInterval=24, maxMarketOrdersPerTurn=10)
    values.update(changes)
    return SimpleNamespace(**values)


def observed(step=226, shops=('BAKERY', 'PIZZA_SHOP', 'BRUNCH_SPOT')):
    return {'step': step, 'town': {'unlocked_shops': list(shops)}}


def state_for(obs, cfg):
    m = ENGINE
    farms = [m._new_farm(cfg.boardSize, cfg.startingMoney) for _ in range(2)]
    market = m._new_market()
    town = copy.deepcopy(obs['town'])
    return [SimpleNamespace(
        observation=SimpleNamespace(step=obs['step'], farms=farms, market=market,
                                    town=town, player=i, private=m._new_private()),
        action={'farmer': ['PASS'], 'hands': [], 'market': []},
        status='ACTIVE', reward=0) for i in range(2)]


class ControlledDraws:
    def __init__(self, shops):
        self.shops = list(shops)
        self.calls = []
    def random(self):
        return 1.0
    def choice(self, names):
        if not self.shops:
            raise AssertionError('Unexpected additional shop draw')
        name = self.shops.pop(0)
        if name not in names:
            raise AssertionError('Scenario supplied a non-source shop')
        self.calls.append(name)
        return name


class DemandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = DemandRules.from_engine(ENGINE)

    def compare_interpreter(self, obs, cfg, path, end, products=None, label='case'):
        schedule = build_schedule(obs, cfg, self.rules, future_shops=path,
                                  end_step=end, products=products)
        state = state_for(obs, cfg)
        env = SimpleNamespace(configuration=cfg, info={'seed': 0}, done=False)
        start_inventory = dict(state[0].observation.market['inventory'])
        draw = ControlledDraws(path)
        rows = {r.step: r for r in schedule.rows}
        trajectory = []
        with patch.object(ENGINE.random, 'Random', lambda unused: draw):
            for step in range(schedule.start_step, schedule.end_step + 1):
                for seat in state:
                    seat.observation.step = step
                before = dict(state[0].observation.market['inventory'])
                ENGINE.interpreter(state, env)
                after = dict(state[0].observation.market['inventory'])
                expected = (dict(zip(schedule.products, rows[step].inventory_delta))
                            if step in rows else {p: 0 for p in schedule.products})
                self.assertEqual({p: after[p] - before[p] for p in schedule.products},
                                 expected, (label, step))
                self.assertIs(state[1].observation.market, state[0].observation.market)
                trajectory.append({'step': step, 'inventory': after,
                                   'prices': dict(state[0].observation.market['prices']),
                                   'shops_after': list(state[0].observation.town['unlocked_shops'])})
        self.assertEqual(draw.shops, [])
        self.assertEqual(schedule.before_market(schedule.end_step + 1),
                         {p: after[p] - start_inventory[p] for p in schedule.products})
        EVIDENCE.append({'label': label, 'start': obs, 'configuration': vars(cfg),
                         'future_shops': list(path), 'products': schedule.products,
                         'coverage': schedule.coverage, 'trajectory': trajectory})
        return schedule

    def test_default_wool_support_all_32_paths(self):
        obs = observed()
        family = scenario_family(obs, config(), self.rules, products=['WOOL'])
        self.assertEqual(family.unlock_after_steps, (287, 359, 431, 503, 575))
        self.assertEqual(family.total_scenarios, 32)
        for i, path in enumerate(family.representatives()):
            self.compare_interpreter(obs, config(), path, 718, ['WOOL'], f'wool-{i:02d}')
        self.assertTrue(family.coverage(32)['complete'])

    def test_complete_all_product_schedules(self):
        for i, path in enumerate([('YARN_STORE',), ('BAKERY',), ('FARMERS_MARKET',),
                                  ('PET_CAFE',), ('PIZZA_SHOP',), ('BRUNCH_SPOT',),
                                  ('SMOOTHIE_SHOP',), ('ICE_CREAM_SHOP',)]):
            self.compare_interpreter(observed(70, ()), config(), path, 100,
                                     label=f'all-products-{i}')

    def test_arrival_not_consumed_on_coincident_tick(self):
        cfg = config(turnsPerDay=5, townShopUnlockInterval=2,
                     townShopSellInterval=3, townCenterSellInterval=7, episodeSteps=42)
        sch = self.compare_interpreter(observed(8, ()), cfg,
                                       ('YARN_STORE', 'YARN_STORE'), 21,
                                       ['WOOL', 'FERTILIZER'], 'coincident-eod')
        rows = {r.step: dict(zip(sch.products, r.inventory_delta)) for r in sch.rows}
        self.assertNotIn(9, rows)  # new shop appears AFTER tick 9
        self.assertEqual(rows[12]['WOOL'], -2)
        self.assertEqual(rows[21]['WOOL'], -5)  # two YARN plus town center

    def test_replacement_and_instance_cap(self):
        obs = observed(70, ('YARN_STORE',) * 7)
        self.compare_interpreter(obs, config(), ('YARN_STORE',), 150,
                                 label='eight-instances')
        fam = scenario_family(obs, config(), self.rules, products=['WOOL'])
        self.assertEqual(len(fam.unlock_after_steps), 1)

    def test_full_town_has_no_draw(self):
        obs = observed(226, ('YARN_STORE',) * 8)
        schedule = self.compare_interpreter(obs, config(), (), 300, label='full-town')
        self.assertEqual(schedule.unlock_after_steps, ())

    def test_terminal_boundary_excludes_nonexistent_action_719(self):
        sch = self.compare_interpreter(observed(716, ('BAKERY',) * 8), config(), (),
                                       900, label='terminal')
        self.assertEqual(sch.end_step, 718)
        self.assertTrue(all(r.step <= 718 for r in sch.rows))

    def test_public_current_step_already_includes_previous_unlock(self):
        fam = scenario_family(observed(72, ('YARN_STORE',)), config(), self.rules,
                              products=['WOOL'], end_step=150)
        self.assertEqual(fam.unlock_after_steps, (143,))

    def test_after_market_not_same_market(self):
        obs = observed(72, ('YARN_STORE',))
        cfg = config()
        state = state_for(obs, cfg)
        state[0].observation.private['shed']['WOOL'] = 1
        state[0].action['market'] = [['SELL', 'WOOL', 1]]
        env = SimpleNamespace(configuration=cfg, info={'seed': 0}, done=False)
        market_only = copy.deepcopy(state)
        ENGINE._process_market(market_only, env)
        expected_money = market_only[0].observation.farms[0]['money']
        expected_inventory = market_only[0].observation.market['inventory']['WOOL']
        ENGINE.interpreter(state, env)
        self.assertEqual(state[0].observation.farms[0]['money'], expected_money)
        self.assertEqual(state[0].observation.market['inventory']['WOOL'],
                         expected_inventory - 3)
        sch = build_schedule(obs, cfg, self.rules, future_shops=(),
                             end_step=72, products=['WOOL'])
        self.assertEqual(sch.before_market(72), {'WOOL': 0})
        self.assertEqual(sch.before_market(73), {'WOOL': -3})
        EVIDENCE.append({'label': 'same-market-sale', 'transition_count': 1,
                         'money_after_market': expected_money,
                         'money_after_interpreter': state[0].observation.farms[0]['money'],
                         'wool_after_market': expected_inventory,
                         'wool_after_town': expected_inventory - 3})

    def test_missing_future_not_silently_complete(self):
        sch = build_schedule(observed(), config(), self.rules, future_shops=None,
                             products=['WOOL'])
        self.assertEqual(sch.coverage, 'known_shops_only')
        self.assertTrue(sch.as_dict()['unknown_future_draws'])
        self.assertEqual(sch.before_market(719), {'WOOL': -20})
        with self.assertRaises(ValueError):
            build_schedule(observed(), config(), self.rules, future_shops=())

    def test_wool_extremal_demand(self):
        cfg = config()
        no_yarn = build_schedule(observed(), cfg, self.rules,
                                 future_shops=('BAKERY',) * 5, products=['WOOL'])
        all_yarn = build_schedule(observed(), cfg, self.rules,
                                  future_shops=('YARN_STORE',) * 5, products=['WOOL'])
        self.assertEqual(no_yarn.before_market(719), {'WOOL': -20})
        self.assertEqual(all_yarn.before_market(719), {'WOOL': -740})

    def test_before_day15_market_new_draw_has_not_consumed(self):
        sch = build_schedule(observed(), config(), self.rules,
                             future_shops=('YARN_STORE', 'YARN_STORE'),
                             products=['WOOL'], end_step=360)
        self.assertEqual(sch.before_market(360), {'WOOL': -41}) # 36 shop +5 center
        self.assertEqual(sch.before_market(361), {'WOOL': -46})

    def test_projected_equivalence_is_not_observation_equivalence(self):
        fam = scenario_family(observed(), config(), self.rules, products=['WOOL'])
        zero = next(g for g in fam.groups if g.per_shop_tick == (0,))
        self.assertEqual(len(zero.shop_names), 7)
        self.assertFalse(fam.public_observations_interchangeable)
        self.assertIsNone(fam.coverage(32)['probabilities'])

    def test_joint_wool_egg_support_and_truncation(self):
        fam = scenario_family(observed(), config(), self.rules, products=['WOOL', 'EGG'])
        self.assertEqual(len(fam.groups), 3)
        self.assertEqual(fam.total_scenarios, 243)
        self.assertEqual(len(list(fam.representatives(32))), 32)
        self.assertFalse(fam.coverage(32)['complete'])

    def test_no_input_mutation_or_hidden_field_reads(self):
        class PublicOnly(dict):
            def get(self, name, default=None):
                if name in ('seed', 'private', 'farms', 'info', 'market'):
                    raise AssertionError(f'unneeded field read: {name}')
                return super().get(name, default)
        obs = PublicOnly(observed())
        before = copy.deepcopy(obs)
        cfg = PublicOnly(vars(config()))
        build_schedule(obs, cfg, self.rules, future_shops=('BAKERY',) * 5,
                       products=['WOOL'])
        self.assertEqual(obs, before)

    def test_missing_public_snapshot_and_unknown_inputs(self):
        bad_observations = ({'town': {'unlocked_shops': []}}, {'step': 1},
                            {'step': 1, 'town': {}}, observed(1, ('UNKNOWN',)),
                            observed(1, ('BAKERY',) * 9), observed(-1, ()))
        for obs in bad_observations:
            with self.assertRaises((ValueError, TypeError)):
                build_schedule(obs, config(), self.rules, future_shops=None)
        for names in ([], ['WOOL', 'WOOL'], ['UNKNOWN']):
            with self.assertRaises(ValueError):
                build_schedule(observed(), config(), self.rules,
                               future_shops=None, products=names)

    def test_no_inventory_floor_added(self):
        obs = observed(72, ('YARN_STORE',) * 8)
        cfg = config()
        state = state_for(obs, cfg)
        state[0].observation.market['inventory']['WOOL'] = 0
        ENGINE.interpreter(state, SimpleNamespace(configuration=cfg, info={'seed': 0}, done=False))
        self.assertEqual(state[0].observation.market['inventory']['WOOL'], -17)
        sch = build_schedule(obs, cfg, self.rules, future_shops=(), end_step=72,
                             products=['WOOL'])
        self.assertEqual(sch.before_market(73), {'WOOL': -17})
        EVIDENCE.append({'label': 'negative-inventory', 'transition_count': 1,
                         'initial_wool': 0, 'final_wool': -17})

    def test_config_interval_coercion_matches_engine(self):
        self.compare_interpreter(observed(0, ()),
                                 config(turnsPerDay=0, townShopUnlockInterval=0,
                                        townShopSellInterval=0, townCenterSellInterval=0,
                                        episodeSteps=12),
                                 ('YARN_STORE',) * 8, 10, label='coerced-intervals')

    def test_query_horizon_is_explicit(self):
        sch = build_schedule(observed(), config(), self.rules, future_shops=(), end_step=230)
        for step in (225, 232):
            with self.assertRaises(ValueError):
                sch.before_market(step)
        fam = scenario_family(observed(), config(), self.rules, products=['WOOL'])
        with self.assertRaises(ValueError):
            list(fam.representatives(-1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', required=True, type=Path)
    parser.add_argument('--report', type=Path, default=Path('validation.json'))
    parser.add_argument('--evidence', type=Path, default=Path('engine-cases.json.gz'))
    args = parser.parse_args()
    global ENGINE
    ENGINE = load_engine(args.engine)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DemandTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    payload = json.dumps(EVIDENCE, sort_keys=True, separators=(',', ':')).encode()
    compressed = gzip.compress(payload, mtime=0)
    args.evidence.write_bytes(compressed)
    transitions = sum(len(c.get('trajectory', [])) + c.get('transition_count', 0) for c in EVIDENCE)
    report = {'engine_sha256': PIN, 'engine_ref': '28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c',
              'runtime_sha256': hashlib.sha256(Path(__file__).with_name('town_demand.py').read_bytes()).hexdigest(),
              'tests_run': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'case_count': len(EVIDENCE),
              'official_interpreter_transitions': transitions,
              'full_games': 0, 'seed_reservations': [], 'source_published': False,
              'scope': 'conditional mechanics; directed RNG fixture, empty farms except explicit sale case',
              'framework_shim': 'seed-helper import removed; initializer not called; interpreter functions unchanged',
              'evidence_sha256': hashlib.sha256(compressed).hexdigest(),
              'passed': result.wasSuccessful()}
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)

if __name__ == '__main__':
    main()
