# SPDX-License-Identifier: Apache-2.0
"""Independent mixed FERT/feed/native-return controls; normal and -O required.

Run with STOCKBRIDGE_SOURCE pointing to the immutable archived runtime and
STOCKBRIDGE_COMPOSED pointing to its source-bound test composition. No peer
receipt counts are imported as this suite's own execution evidence.
"""
from copy import deepcopy
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace, ModuleType
import unittest

import stock_bridge as bridge

BASE = Path(os.environ['STOCKBRIDGE_SOURCE']).resolve()
CURRENT = Path(os.environ['STOCKBRIDGE_COMPOSED']).resolve()
sys.path.insert(0, str(CURRENT))
import operating_stock as stock
import mechanics as mechanics
from titan_runtime import Features, TitanAgent

PEERS = bridge.peers()
ENGINE_PAIRS = 0
ENGINE_CALLS = 0


def module_bytes(path):
    return path.read_bytes()


def fixture(now=684, seat=0, harvest=False):
    farm = {'farmer': [0, 0], 'hands': [[4, 4], [4, 4]], 'money': 50000,
            'hires_today': 2, 'unlocked_quadrants': ['NW'],
            'tiles': [[None for _ in range(10)] for _ in range(10)]}
    for x in (2, 3):
        farm['tiles'][4][x] = {
            'kind': 'PLANT', 'crop': 'STRAWBERRY',
            'planted_day': now//24-mechanics.CROPS['STRAWBERRY']['first_yield_day']+1,
            'yield_units': 0, 'fertilized_until_day': -1, 'max_lifespan_step': -1,
            'consecutive_unwatered': 0, 'watered_today': True}
    for y, animal in ((2 if harvest else 3, 'COW'), (1 if harvest else 2, 'SHEEP')):
        farm['tiles'][y][4] = mechanics._new_animal(animal, 1)
    if harvest:
        farm['tiles'][3][4] = {
            'kind': 'PLANT', 'crop': 'WHEAT', 'planted_day': now//24-5,
            'yield_units': 2, 'fertilized_until_day': -1, 'max_lifespan_step': -1,
            'consecutive_unwatered': 0, 'watered_today': True}
    private = {'inventories': [{}, {}, {}], 'shed': {'FERTILIZER': 9, 'WHEAT': 9}, 'seeds': {}}
    observation = {'step': now, 'hour': now % 24, 'day': now//24, 'player': seat,
        'market': {'inventory': {'WHEAT': 9800, 'FERTILIZER': 10300, 'STRAWBERRY': 9900}},
        'farms': [deepcopy(farm), deepcopy(farm)], 'private': private}
    observation['farms'][seat] = farm
    selected = {'farmer': ['PASS'], 'hands': [['PASS'], ['PASS']],
                'market': [['SELL', 'FERTILIZER', 9], [], ['SELL', 'WHEAT', 9]]}
    route = [{'farmer': ['PASS'], 'hands': [['PASS'], ['PASS']], 'market': []} for _ in range(720)]
    fert = [['PICKUP', 'FERTILIZER', 3], ['WEST'], ['FERTILIZE'], ['WEST'], ['FERTILIZE']]
    feed = ([['PICKUP', 'WHEAT', 3], ['NORTH'], ['HARVEST'], ['NORTH'], ['FEED'], ['NORTH'], ['FEED']]
            if harvest else [['PICKUP', 'WHEAT', 3], ['NORTH'], ['FEED'], ['NORTH'], ['FEED']])
    for index, action in enumerate(fert, now+1): route[index]['hands'][0] = action
    for index, action in enumerate(feed, now+1): route[index]['hands'][1] = action
    return observation, selected, route


def native(observation, selected, route, *, enabled=True):
    agent = TitanAgent(Features(operating_stock=enabled))
    agent.selected = selected
    agent.controller = SimpleNamespace(R={'current': route}, cur='current')
    seat = observation['player']
    agent.consumer = SimpleNamespace(
        selected_post_units=(observation['farms'][seat], observation['private']),
        selected_post_units_binding=(observation['step'], seat, selected['farmer'], selected['hands']))
    agent.diagnostics = {'status': 'completed'}
    first = agent._operating_stock_selected(observation, {}, selected)
    final = agent._finish_production(observation, first, {})
    return first, final, agent


def engine_loader():
    path = BASE/'checks/reference/evaluator/loader.py'
    spec = importlib.util.spec_from_file_location('_stockbridge_test_loader', path)
    loader = importlib.util.module_from_spec(spec); spec.loader.exec_module(loader)
    for name, expected in {
            'kaggriculture.py': bridge.ENGINE,
            'kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
            'utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87'}.items():
        if bridge.blob((BASE/'checks/reference/engine'/name).read_bytes()) != expected:
            raise ValueError('engine fixture drift')
    engine, _ = loader.get_engine(BASE/'checks/reference/engine')
    return loader, engine


LOADER, ENGINE = engine_loader()


def advance(observation, selected, route):
    global ENGINE_CALLS
    cfg = LOADER.Struct({k: v.get('default') if isinstance(v, dict) else v
                        for k, v in ENGINE.specification['configuration'].items()})
    cfg.seed = 1729
    env = LOADER.Struct(configuration=cfg, done=False, info={})
    state = [LOADER.Struct(observation=LOADER.Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
    ENGINE.interpreter(state, env); ENGINE_CALLS += 1
    seat = observation['player']; now = observation['step']
    state[0].observation.farms[seat] = deepcopy(observation['farms'][seat])
    state[seat].observation.private = deepcopy(observation['private'])
    state[0].observation.market['inventory'].update(observation['market']['inventory'])
    for s in state:
        s.observation.day = now//24
        s.observation.hour = now % 24
    for step in range(now, (now//24+1)*24):
        for s in state:
            s.observation.step = step
            s.action = {'farmer': ['PASS'], 'hands': [], 'market': []}
        state[seat].action = deepcopy(selected if step == now else route[step])
        ENGINE.interpreter(state, env); ENGINE_CALLS += 1
    return deepcopy(state[seat].observation)


class StockBridgeTests(unittest.TestCase):
    def test_exact_composition_and_current_copy(self):
        s, r, report = bridge.compose(module_bytes(BASE/'operating_stock.py'), module_bytes(BASE/'titan_runtime.py'))
        self.assertEqual(s, module_bytes(CURRENT/'operating_stock.py'))
        self.assertEqual(r, module_bytes(CURRENT/'titan_runtime.py'))
        self.assertEqual(report['stock_combined'], 'a353e122032f24bf83dd46cb9a43756163cab99b')
        self.assertEqual(report['runtime_after'], 'a43339a1d6de445581aebd0f74bbd4de343cdda8')

    def test_peer_source_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'peer.py'; path.write_text('pass\n')
            with self.assertRaisesRegex(ValueError, 'source drift'):
                bridge.load_bound(path, bridge.PEERS['prefix'][1])

    def test_reapplying_does_not_reset_current_helper(self):
        with self.assertRaisesRegex(ValueError, 'unsupported stock baseline'):
            bridge.compose(module_bytes(CURRENT/'operating_stock.py'), module_bytes(BASE/'titan_runtime.py'))

    def test_runtime_unrelated_bytes_survive(self):
        original = module_bytes(BASE/'titan_runtime.py') + b'\n# concurrent unrelated peer comment\n'
        _, actual, _ = bridge.compose(module_bytes(BASE/'operating_stock.py'), original)
        self.assertTrue(actual.endswith(b'\n# concurrent unrelated peer comment\n'))

    def test_prefix_must_precede_harvest(self):
        harvested = PEERS['harvest'].repair_source((BASE/'operating_stock.py').read_text())
        with self.assertRaisesRegex(ValueError, 'preimage mismatch'):
            PEERS['prefix'].port_helper(harvested)

    def test_harvest_preserves_all_prefix_edits(self):
        prefix = PEERS['prefix'].port_helper((BASE/'operating_stock.py').read_text())
        a, b, _ = PEERS['harvest'].function_span(prefix)
        c, d, _ = PEERS['harvest'].function_span((CURRENT/'operating_stock.py').read_text())
        combined = (CURRENT/'operating_stock.py').read_text()
        self.assertEqual(prefix[:a] + prefix[b:], combined[:c] + combined[d:])

    def test_two_reservations_survive_native_finalizer_both_seats(self):
        for seat in (0, 1):
            obs, selected, route = fixture(seat=seat)
            before = deepcopy((obs, selected, route))
            first, final, agent = native(obs, selected, route)
            self.assertEqual(first['market'], [['SELL', 'FERTILIZER', 7], [], ['SELL', 'WHEAT', 9]])
            self.assertEqual(final['market'], [['SELL', 'FERTILIZER', 7], [], ['SELL', 'WHEAT', 7]])
            self.assertTrue(agent.diagnostics['feed_stock']['certified'])
            self.assertEqual((obs, selected, route), before)

    def test_terminal_restores_post_fertilizer_not_parent(self):
        for seat in (0, 1):
            obs, selected, route = fixture(seat=seat)
            probe = bridge.StockProbe(PEERS['terminal'], release=True)
            with probe.installed(stock):
                first, final, agent = native(obs, selected, route)
            self.assertIs(final, first)
            self.assertEqual(final['market'], [['SELL', 'FERTILIZER', 7], [], ['SELL', 'WHEAT', 9]])
            self.assertEqual(probe.counts['terminal_matches'], 1)
            self.assertEqual(agent.diagnostics['feed_stock']['reason'], 'terminal_feed_no_survival_or_care_payoff')

    def test_observer_is_identity_preserving(self):
        obs, selected, route = fixture()
        delegate = stock.protect_feed_stock
        args = (mechanics, obs, {}, selected, obs['farms'][0], obs['private'], route)
        proposed, report = delegate(*args)
        # Return exact fixed delegate objects to distinguish identity from equality.
        stock.protect_feed_stock = lambda *args: (proposed, report)
        try:
            with bridge.StockProbe(PEERS['terminal']).installed(stock):
                actual, receipt = stock.protect_feed_stock(*args)
            self.assertIs(actual, proposed); self.assertIs(receipt, report)
        finally:
            stock.protect_feed_stock = delegate

    def test_probe_restores_callables_on_exception(self):
        old = stock.protect_operating_stock, stock.protect_feed_stock
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            with bridge.StockProbe(PEERS['terminal']).installed(stock):
                raise RuntimeError('injected')
        self.assertEqual((stock.protect_operating_stock, stock.protect_feed_stock), old)

    def test_double_probe_is_rejected(self):
        with bridge.StockProbe(PEERS['terminal']).installed(stock):
            with self.assertRaisesRegex(ValueError, 'already installed'):
                with bridge.StockProbe(PEERS['terminal']).installed(stock):
                    pass

    def test_literal_flag_required(self):
        for bad in (1, 'true', None, []):
            with self.assertRaises(ValueError): bridge.StockProbe(PEERS['terminal'], release=bad)

    def test_feature_off_has_no_calls_no_actions_changed(self):
        obs, selected, route = fixture()
        probe = bridge.StockProbe(PEERS['terminal'], release=True)
        with probe.installed(stock):
            first, final, _ = native(obs, selected, route, enabled=False)
        self.assertIs(first, selected); self.assertIs(final, selected)
        self.assertFalse(probe.counts)

    def test_harvest_rejection_does_not_erase_fertilizer(self):
        for seat in (0, 1):
            obs, selected, route = fixture(seat=seat, harvest=True)
            probe = bridge.StockProbe(PEERS['terminal'], release=True)
            with probe.installed(stock):
                first, final, agent = native(obs, selected, route)
            self.assertEqual(first['market'][0], ['SELL', 'FERTILIZER', 7])
            self.assertIs(final, first)
            self.assertEqual(agent.diagnostics['feed_stock']['reason'], PEERS['harvest'].REASON)
            self.assertEqual(probe.counts['terminal_matches'], 0)

    def test_terminal_boundary_care_and_survival_controls(self):
        for kind in ('earlier', 'care', 'missed', 'bonus', 'cared'):
            obs, selected, route = fixture(now=660 if kind == 'earlier' else 684)
            tile = obs['farms'][0]['tiles'][3][4]
            if kind == 'care': route[690]['farmer'] = ['CARE']
            if kind == 'missed': tile['consecutive_unfed'] = 1
            if kind == 'bonus': tile['pending_care_bonus'] = 1
            if kind == 'cared': tile['cared_today'] = True
            probe = bridge.StockProbe(PEERS['terminal'], release=True)
            with probe.installed(stock): _, final, _ = native(obs, selected, route)
            self.assertEqual(final['market'][2], ['SELL', 'WHEAT', 7], kind)
            self.assertEqual(probe.counts['terminal_matches'], 0, kind)

    def test_dead_tail_fertilizer_hire_and_sale_slots(self):
        for seat in (0, 1):
            obs, selected, route = fixture(seat=seat)
            selected['market'] += [[] for _ in range(7)] + [['HIRE'], ['SELL', 'FERTILIZER', 90]]
            route[685]['market'] = [[] for _ in range(10)] + [['HIRE']]
            before = deepcopy(selected['market'][10:])
            first, final, agent = native(obs, selected, route)
            self.assertEqual(first['market'][0], ['SELL', 'FERTILIZER', 7])
            self.assertEqual(final['market'][10:], before)
            self.assertEqual(final['market'][2], ['SELL', 'WHEAT', 7])

    def test_live_hire_is_not_treated_as_dead_tail(self):
        obs, selected, route = fixture()
        selected['market'].append(['HIRE'])
        first, _, agent = native(obs, selected, route)
        self.assertIs(first, selected)
        self.assertEqual(agent.diagnostics['operating_stock']['reason'], 'current_hiring_boundary')

    def test_raw_slot_matrix_preserves_two_products_and_tail(self):
        for seat in (0, 1):
            for fert_slot in range(10):
                for wheat_slot in range(10):
                    if fert_slot == wheat_slot: continue
                    obs, selected, route = fixture(seat=seat)
                    selected['market'] = [[] for _ in range(10)] + [['HIRE'], ['SELL', 'FERTILIZER', 99]]
                    selected['market'][fert_slot] = ['SELL', 'FERTILIZER', 9]
                    selected['market'][wheat_slot] = ['SELL', 'WHEAT', 9]
                    with bridge.StockProbe(PEERS['terminal'], release=True).installed(stock):
                        _, final, _ = native(obs, selected, route)
                    expected = deepcopy(selected); expected['market'][fert_slot][2] = 7
                    self.assertEqual(final, expected)

    def test_actual_engine_keeps_fertilizer_payoff_after_terminal_release(self):
        global ENGINE_PAIRS
        for seat in (0, 1):
            for fert_slot, wheat_slot in ((f, w) for f in range(10) for w in range(10) if f != w):
                obs, selected, route = fixture(seat=seat)
                selected['market'] = [[] for _ in range(10)] + [['HIRE']]
                selected['market'][fert_slot] = ['SELL', 'FERTILIZER', 9]
                selected['market'][wheat_slot] = ['SELL', 'WHEAT', 9]
                with bridge.StockProbe(PEERS['terminal'], release=True).installed(stock):
                    _, final, _ = native(obs, selected, route)
                good = advance(obs, final, route)
                bad = advance(obs, selected, route)  # deliberately restoring pre-FERT input
                ENGINE_PAIRS += 1
                for x in (2, 3):
                    self.assertEqual(good['farms'][seat]['tiles'][4][x]['yield_units'],
                                     bad['farms'][seat]['tiles'][4][x]['yield_units'] + 1)
                self.assertEqual(good['private']['shed'].get('WHEAT', 0), 0)
                self.assertEqual(good['farms'][seat]['tiles'][3][4]['animal'], 'COW')

    def test_actual_engine_harvest_service_remains_successful(self):
        global ENGINE_PAIRS
        for seat in (0, 1):
            obs, selected, route = fixture(seat=seat, harvest=True)
            first, final, _ = native(obs, selected, route)
            self.assertIs(final, first)
            before = advance(obs, first, route)
            wasteful = deepcopy(first); wasteful['market'][2][2] = 7
            after = advance(obs, wasteful, route)
            ENGINE_PAIRS += 1
            expected_cash = sum(ENGINE.market_price('WHEAT', 9800 + q) for q in (7, 8))
            self.assertEqual(before['farms'][seat]['money'] - after['farms'][seat]['money'], expected_cash)
            self.assertEqual(after['private']['shed'].get('WHEAT', 0), 2)
            self.assertEqual(before['private']['shed'].get('WHEAT', 0), 0)
            for y in (1, 2):
                self.assertEqual(before['farms'][seat]['tiles'][y][4], after['farms'][seat]['tiles'][y][4])


if __name__ == '__main__':
    result = unittest.main(exit=False, verbosity=2).result
    print(f'STOCKBRIDGE engine_pairs={ENGINE_PAIRS} interpreter_calls={ENGINE_CALLS}', flush=True)
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun and not result.skipped else 1)
