#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""E7 helper lifecycle + real-interpreter checks, NOT a full runtime/ABI gate.

Requires complete pinned engine and baseline files. r04_full_router is replaced
ONLY inside this process by the explicit selected-function test slice. Supply
--router to compare the slice's selected ASTs with the complete pinned donor.
No tape, full router, production agent, network or materializer is executed.
"""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest

HERE = Path(__file__).resolve().parent
BASELINE_BLOB = 'e5ed61613cfa8a6d23809166d9310a8f569a65d4'
ENGINE_BLOB = '3c202c7ee921da239356789e266b694635103fc4'
ROUTER_BLOB = 'a3e2fe87c717d128e43c9b65bae2265f40d1d76d'
COUNTS = {}
CANDIDATE = BASELINE = ENGINE = HOST = None


def blob(path):
    data = Path(path).read_bytes()
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def pinned(path, expected):
    actual = blob(path)
    if actual != expected:
        raise ValueError(f'{path}: expected Git blob {expected}; got {actual}')
    return actual


def count(name):
    COUNTS[name] = COUNTS.get(name, 0) + 1


def config(**patch):
    value = dict(turnsPerDay=24, shedCapacity=100,
                 maxMarketOrdersPerTurn=10, townCenterSellInterval=24)
    value.update(patch)
    return value


def action(market=None):
    return dict(farmer=['PASS'], hands=[], market=[] if market is None else market)


class Parent:
    def __init__(self, actions=None):
        self.actions = actions or {}
        self.calls = 0
        self.last_action = None

    def __call__(self, observation, configuration=None):
        self.calls += 1
        self.last_action = copy.deepcopy(self.actions.get(observation['step'], action()))
        return self.last_action


def obs(step, seat=0, quantity=5, prices=None, shed=None):
    return dict(step=step, player=seat,
                farms=[dict(tiles=[[None]*10 for _ in range(10)], farmer=[4, 4], hands=[])
                       for _ in range(2)],
                private=dict(shed={'MILK': quantity} if shed is None else dict(shed),
                             seeds={}, inventories=[{}]),
                market=dict(prices=prices or {'MILK': 160}),
                town=dict(unlocked_shops=[]))


class Attr(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def engine_sequence(module, episode_steps, seat, quantity, rival_rows=None):
    """Constructed legal suffix starting at47; complete interpreter each callback."""
    cfg = Attr(config(episodeSteps=episode_steps, boardSize=10, weedSpawnChance=0,
                      townShopUnlockInterval=3, townShopSellInterval=4,
                      farmHandCostMult=1))
    farms = [ENGINE._new_farm(10, 3000) for _ in range(2)]
    market, town = ENGINE._new_market(), ENGINE._new_town()
    state = []
    for player in range(2):
        private = ENGINE._new_private()
        private['shed']['MILK'] = quantity if player == seat else 5
        state.append(Attr(observation=Attr(step=47, player=player, farms=farms,
                                          market=market, town=town, private=private),
                          action=action(), status='ACTIVE', reward=None))
    env = Attr(configuration=cfg, done=False, info={'seed': 741})
    wrapper = module.install(Parent(), enabled=True)
    callbacks = []
    for step in range(47, episode_steps-1):
        for s in state:
            s.observation.step = step
        selected = copy.deepcopy(dict(state[seat].observation))
        state[seat].action = wrapper(selected, dict(cfg))
        state[1-seat].action = action(copy.deepcopy(rival_rows or []))
        ENGINE.interpreter(state, env)
        count('interpreter_calls')
        callbacks.append(step)
        if state[seat].status == 'DONE':
            break
    return dict(callbacks=callbacks, cash=farms[seat]['money'],
                reward=state[seat].reward, status=state[seat].status,
                milk=state[seat].observation.private['shed']['MILK'],
                rival_cash=farms[1-seat]['money'])


class LifecycleTests(unittest.TestCase):
    def test_off_is_parent_identity(self):
        parent = Parent()
        self.assertIs(parent, CANDIDATE.install(parent, enabled=False))

    def test_short_horizons_retain_incumbent_sale_both_seats(self):
        for seat in range(2):
            for step in range(47, 696, 24):
                for horizon in (step+2, step+3):
                    with self.subTest(seat=seat, step=step, horizon=horizon):
                        parent = Parent()
                        agent = CANDIDATE.install(parent, True)
                        observation = obs(step, seat)
                        expected = HOST.evening_flush(observation, action())
                        self.assertEqual(expected, agent(observation, config(episodeSteps=horizon)))
                        self.assertEqual(1, agent.telemetry['horizon_reject'])
                        self.assertIsNone(agent.players[seat]['pending'])
                        count('short_horizon_cells')

    def test_exact_final_release_callback_is_admitted(self):
        for seat in range(2):
            for step in range(47, 696, 24):
                agent = CANDIDATE.install(Parent(), True)
                cfg = config(episodeSteps=step+4)
                self.assertEqual([], agent(obs(step, seat), cfg)['market'])
                self.assertEqual([], agent(obs(step+1, seat), cfg)['market'])
                self.assertEqual([['SELL', 'MILK', 5]], agent(obs(step+2, seat), cfg)['market'])
                count('exact_boundary_cells')

    def test_default_720_action_and_state_compatibility(self):
        for seat in range(2):
            for step in range(23, 720, 24):
                for cfg in (None, config(), config(episodeSteps=720)):
                    a, b = CANDIDATE.install(Parent(), True), BASELINE.install(Parent(), True)
                    for t in range(step, step+3):
                        self.assertEqual(b(obs(t, seat), cfg), a(obs(t, seat), cfg))
                        self.assertEqual(b.players, a.players)
                        count('default_callback_comparisons')

    def test_invalid_horizon_types_fail_closed(self):
        for value in (True, False, None, 720.0, '720', 0, 1, -1, float('nan'), float('inf'), [], {}):
            with self.subTest(value=repr(value)):
                parent = Parent()
                a = CANDIDATE.install(parent, True)
                self.assertEqual(HOST.evening_flush(obs(47), action()),
                                 a(obs(47), config(episodeSteps=value)))
                self.assertIsNone(a.players[0]['pending'])

    def test_attribute_configuration_boundary(self):
        for horizon, held in ((49, False), (50, False), (51, True)):
            a = CANDIDATE.install(Parent(), True)
            result = a(obs(47), types.SimpleNamespace(**config(episodeSteps=horizon)))
            self.assertEqual([] if held else [['SELL', 'MILK', 5]], result['market'])

    def test_changed_release_configuration_does_not_edit_parent(self):
        patches = [dict(episodeSteps=50), dict(episodeSteps=True), dict(turnsPerDay=12),
                   dict(shedCapacity=99), dict(maxMarketOrdersPerTurn=1),
                   dict(townCenterSellInterval=12), dict(marketParams={'MILK': {}})]
        for patch in patches:
            p = Parent({49: action([['HIRE']])})
            a = CANDIDATE.install(p, True)
            a(obs(47), config())
            actual = a(obs(49), config(**patch))
            self.assertIs(p.last_action, actual)
            self.assertEqual(1, a.telemetry['release_config_reject'])
            self.assertIsNone(a.players[0]['pending'])

    def test_full_partial_zero_release_conserves_issued_ledger(self):
        for seat in range(2):
            for wanted in range(1, 13):
                for stock in range(0, 13):
                    for parent_sell in (0, 1, 4, 20):
                        with self.subTest(seat=seat, wanted=wanted, stock=stock, parent_sell=parent_sell):
                            raw = [['SELL', 'MILK', parent_sell]]
                            p = Parent({49: action(raw)})
                            a = CANDIDATE.install(p, True)
                            a(obs(47, seat, quantity=wanted), config())
                            observation = obs(49, seat, quantity=stock)
                            saved = copy.deepcopy(observation)
                            result = a(observation, config())
                            issued = min(wanted, max(0, stock-parent_sell))
                            self.assertEqual(parent_sell+issued, result['market'][0][2])
                            self.assertEqual(issued, a.telemetry['released_units'])
                            self.assertEqual(wanted-issued, a.telemetry['release_shortfall_units'])
                            event = a.events[-1]
                            self.assertEqual(wanted, sum(event['released'].values())+sum(event['shortfall'].values()))
                            self.assertEqual(saved, observation)
                            self.assertEqual(raw, p.last_action['market'])
                            self.assertEqual(2, p.calls)
                            count('release_accounting_cells')

    def test_multiple_items_partial_release_ledger(self):
        prices = dict(MILK=160, WOOL=200, MELON=250, STRAWBERRY=120)
        p = Parent({49: action([['SELL', 'MILK', 1], ['HIRE']])})
        a = CANDIDATE.install(p, True)
        a(obs(47, prices=prices, shed={x: 5 for x in prices}), config())
        r = a(obs(49, prices=prices, shed=dict(MILK=3, WOOL=4, MELON=1, STRAWBERRY=0)), config())
        self.assertEqual([['SELL', 'MILK', 3], ['HIRE']], r['market'][:2])
        self.assertEqual(7, a.telemetry['released_units'])
        self.assertEqual(13, a.telemetry['release_shortfall_units'])

    def test_full_market_topup_does_not_reindex(self):
        raw = [['HIRE']]*9 + [['SELL', 'MILK', 2]]
        a = CANDIDATE.install(Parent({49: action(raw)}), True)
        a(obs(47), config())
        r = a(obs(49), config())
        self.assertEqual(raw[:9], r['market'][:9])
        self.assertEqual([['SELL', 'MILK', 5]], r['market'][9:])
        self.assertEqual(2, a.telemetry['release_shortfall_units'])

    def test_raw_release_rejections_keep_action_identity(self):
        for raw in ([[], ['SELL', 'MILK', 1]], [['HIRE']]*11, None, [None], [('HIRE',)]):
            p = Parent({49: {'farmer': ['PASS'], 'hands': [], 'market': raw}})
            a = CANDIDATE.install(p, True)
            a(obs(47), config())
            result = a(obs(49), config())
            self.assertIs(result, p.last_action)
            self.assertIsNone(a.players[0]['pending'])
            self.assertEqual(0, a.telemetry['released_units'])

    def test_full_market_clears_pending_and_records_shortfall(self):
        p = Parent({49: action([['HIRE']]*10)})
        a = CANDIDATE.install(p, True)
        a(obs(47), config())
        r = a(obs(49), config())
        self.assertIs(r, p.last_action)
        self.assertEqual(5, a.telemetry['release_shortfall_units'])
        self.assertIsNone(a.players[0]['pending'])

    def test_stale_pending_never_releases_later(self):
        a = CANDIDATE.install(Parent(), True)
        a(obs(47), config())
        self.assertEqual([], a(obs(50), config())['market'])
        self.assertEqual(1, a.telemetry['stale_pending'])
        self.assertEqual([], a(obs(73), config())['market'])

    def test_reset_step_clears_pending(self):
        a = CANDIDATE.install(Parent(), True)
        a(obs(47), config())
        a(obs(0), config())
        self.assertEqual([], a(obs(49), config())['market'])
        self.assertEqual(0, a.telemetry['released_units'])

    def test_players_have_independent_pending(self):
        a = CANDIDATE.install(Parent(), True)
        a(obs(47, 0, quantity=3), config())
        a(obs(47, 1, quantity=7), config())
        self.assertEqual([['SELL', 'MILK', 7]], a(obs(49, 1, quantity=7), config())['market'])
        self.assertEqual([['SELL', 'MILK', 3]], a(obs(49, 0, quantity=3), config())['market'])

    def test_invalid_clock_and_market_configuration_preserve_flush(self):
        for patch in (dict(turnsPerDay='24'), dict(shedCapacity=True), dict(marketParams=[])):
            a = CANDIDATE.install(Parent(), True)
            self.assertEqual(HOST.evening_flush(obs(47), action()), a(obs(47), config(**patch)))

    def test_capacity_rejects_worker_inventory_and_producing_actions(self):
        for command in (['HARVEST'], ['PICKUP', 'MILK'], ['DROP'], ['PLACE', 'MILK'], ['COLLECT_FERTILIZER']):
            row = action()
            row['farmer'] = command
            p = Parent({47: row})
            a = CANDIDATE.install(p, True)
            expected = HOST.evening_flush(obs(47), row)
            self.assertEqual(expected, a(obs(47), config()))
            self.assertEqual(0, a.telemetry['withheld_units'])
        observation = obs(47)
        observation['private']['inventories'] = [{'MILK': 1}]
        a = CANDIDATE.install(Parent(), True)
        self.assertEqual(HOST.evening_flush(observation, action()), a(observation, config()))

    def test_native_rows_preserved_on_admission(self):
        raw = [['SELL', 'MILK', 2], ['HIRE']]
        p = Parent({47: action(raw)})
        a = CANDIDATE.install(p, True)
        result = a(obs(47), config())
        self.assertIs(result, p.last_action)
        self.assertEqual(raw, result['market'])
        self.assertEqual(3, a.telemetry['withheld_units'])

    def test_malformed_prices_reject_release_and_clear_state(self):
        for price in (0, True, '10', None):
            p = Parent()
            a = CANDIDATE.install(p, True)
            a(obs(47), config())
            result = a(obs(49, prices={'MILK': price}), config())
            self.assertIs(result, p.last_action)
            self.assertIsNone(a.players[0]['pending'])

    def test_actual_interpreter_short_horizon_preserves_terminal_cash(self):
        for seat in range(2):
            for horizon in (49, 50):
                for quantity in (1, 5, 20):
                    with self.subTest(seat=seat, horizon=horizon, quantity=quantity):
                        old = engine_sequence(BASELINE, horizon, seat, quantity)
                        new = engine_sequence(CANDIDATE, horizon, seat, quantity)
                        self.assertEqual('DONE', old['status'])
                        self.assertEqual('DONE', new['status'])
                        self.assertEqual(list(range(47, horizon-1)), new['callbacks'])
                        self.assertEqual(quantity, old['milk'])
                        self.assertEqual(0, new['milk'])
                        self.assertEqual(3000, old['reward'])
                        self.assertGreater(new['reward'], old['reward'])
                        self.assertEqual(new['cash'], new['reward'])
                        count('engine_short_horizon_pairs')

    def test_actual_interpreter_equality_boundary_preserves_old_behavior(self):
        for seat in range(2):
            for quantity in (1, 5, 20):
                for rival in ([], [['SELL', 'MILK', 2]]):
                    old = engine_sequence(BASELINE, 51, seat, quantity, rival)
                    new = engine_sequence(CANDIDATE, 51, seat, quantity, rival)
                    self.assertEqual(old, new)
                    self.assertEqual([47, 48, 49], new['callbacks'])
                    self.assertEqual('DONE', new['status'])
                    self.assertEqual(0, new['milk'])
                    count('engine_boundary_pairs')


def compare_router(path):
    pinned(path, ROUTER_BLOB)
    names = {'FarmView', 'projected_shed', 'evening_flush'}
    def selected(p):
        return {n.name: ast.dump(n, include_attributes=False)
                for n in ast.parse(Path(p).read_text()).body
                if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names}
    if selected(path) != selected(HERE/'e7_router_test_slice.py'):
        raise ValueError('selected R04 collaborator ASTs differ')
    # Independently bind every constant referenced by the selected functions.
    tree = ast.parse(Path(path).read_text())
    constants = {}
    wanted = {'LAST_STEP', 'SHED_CAPACITY', 'MAX_ORDERS', 'PRODUCTS', 'ANIMALS', 'FLUSH_ITEMS', 'FLUSH_HOURS'}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in wanted:
                constants[name] = ast.literal_eval(node.value)
    if set(constants) != wanted or any(constants[n] != getattr(HOST, n) for n in wanted):
        raise ValueError('selected R04 constants differ')


def main():
    global CANDIDATE, BASELINE, ENGINE, HOST
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--target', type=Path, default=HERE/'e7_post_tick_evening_flush.py')
    parser.add_argument('--router', type=Path)
    args = parser.parse_args()
    pinned(args.engine, ENGINE_BLOB)
    pinned(args.baseline, BASELINE_BLOB)
    HOST = load('r04_full_router', HERE/'e7_router_test_slice.py')
    if args.router:
        compare_router(args.router)
    # The full interpreter is imported. Initialization is never used; an accidental
    # call into seed resolution raises, rather than faking a successfully seeded env.
    def no_seed_resolution(*unused, **kwargs):
        raise RuntimeError('seed resolver must not be called in constructed suffix tests')
    utility = types.ModuleType('kaggle_environments.utils')
    utility.resolve_episode_seed = no_seed_resolution
    sys.modules['kaggle_environments.utils'] = utility
    ENGINE = load('e7_official_engine', args.engine)
    BASELINE = load('e7_exact_predecessor', args.baseline)
    CANDIDATE = load('e7_target', args.target)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LifecycleTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    output = dict(schema='titan-e7-lifecycle/v1', tests=result.testsRun,
                  failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
                  optimized=not __debug__, counts=COUNTS,
                  target_blob=blob(args.target), baseline_blob=blob(args.baseline),
                  engine_blob=blob(args.engine), host_slice_blob=blob(HERE/'e7_router_test_slice.py'),
                  router_ast_check='PASS' if args.router else 'NOT_RUN',
                  scope='helper + complete official interpreter on constructed suffixes; not full router/runtime/economics')
    print(json.dumps(output, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ImportError) as exc:
        print(f'INPUT ERROR: {exc}', file=sys.stderr)
        raise SystemExit(2)
