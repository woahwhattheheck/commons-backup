# SPDX-License-Identifier: Apache-2.0
"""Run pinned native-consumer, lifecycle and official-interpreter cache checks.

Usage: python validate_rival_supply_cache.py --runtime-root UNPACKED_B567 --output result.json
Run again with python -O. No network access or runtime-input writes are needed.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import io
import json
import random
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from rival_supply_cache import SOURCE_BLOB, git_blob, sha256, transform

SOURCE_MANIFEST_SHA256 = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
ENGINE_BLOB = '3c202c7ee921da239356789e266b694635103fc4'
REPORT = {'native_cases': 0, 'official_interpreter_pairs': 0, 'scans': []}
ROOT = None
OLD = NEW = ENGINE = LOADER = None


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def prepare(root):
    global ROOT, OLD, NEW, ENGINE, LOADER
    ROOT = root.resolve()
    manifest_bytes = (ROOT / 'SOURCE.json').read_bytes()
    if sha256(manifest_bytes) != SOURCE_MANIFEST_SHA256:
        raise ValueError('not the exact current b567 source manifest')
    manifest = json.loads(manifest_bytes)
    for name, entry in manifest['runtime'].items():
        data = (ROOT / name).read_bytes()
        if len(data) != entry['bytes'] or sha256(data) != entry['sha256']:
            raise ValueError('runtime source mismatch: ' + name)
    source = (ROOT / 'frozen_selected.py').read_bytes()
    result = transform(source)
    sys.path.insert(0, str(ROOT))
    OLD = load(ROOT / 'frozen_selected.py', 'observe_cache_control')
    NEW = types.ModuleType('observe_cache_candidate')
    NEW.__file__ = str(ROOT / 'frozen_selected.py')
    sys.modules[NEW.__name__] = NEW
    exec(compile(result, NEW.__file__, 'exec'), NEW.__dict__)
    engine_path = ROOT / 'checks/reference/engine/kaggriculture.py'
    if git_blob(engine_path.read_bytes()) != ENGINE_BLOB:
        raise ValueError('official engine pin mismatch')
    LOADER = load(ROOT / 'checks/reference/evaluator/loader.py', 'observe_cache_loader')
    ENGINE, engine_hashes = LOADER.get_engine(engine_path.parent)
    REPORT.update(runtime_files_verified=len(manifest['runtime']),
                  source_manifest_sha256=sha256(manifest_bytes),
                  source_git_blob=git_blob(source), postimage_git_blob=git_blob(result),
                  postimage_sha256=sha256(result), engine_git_blob=ENGINE_BLOB,
                  engine_sha256=engine_hashes,
                  runner_git_blob=git_blob(Path(__file__).read_bytes()),
                  transformer_git_blob=git_blob(Path(__file__).with_name('rival_supply_cache.py').read_bytes()))


def consumer(module, route, cls=None):
    cls = module.FrozenSelected if cls is None else cls
    bot = cls.__new__(cls)
    bot.controller = types.SimpleNamespace(R={'fixture': copy.deepcopy(route)}, cur='fixture')
    bot.mode = 'candidate'
    bot.planned = {}
    bot.pending = {}
    bot.previous = None
    bot.observed_harvests = {}
    bot.diagnostics = {}
    return bot


def fixture(seat=0, step=100, money=0, lots=None, inventory=10000, rich=True):
    e, S = ENGINE, LOADER.Struct
    cfg = S({k: v.get('default') if isinstance(v, dict) else v
             for k, v in e.specification['configuration'].items()})
    cfg.weedSpawnChance = 0
    cfg.seed = 318116
    farms = [e._new_farm(10, money), e._new_farm(10, money)]
    # Full valid public livestock structures, not fabricated private rival stock.
    if rich:
        for y in range(5):
            for x in range(5):
                tile = e._new_animal(('COW', 'SHEEP', 'GOOSE')[(x+y) % 3], 0)
                tile.update(yield_units=2, fed_today=True, cared_today=True)
                farms[1-seat]['tiles'][y][x] = tile
    market = e._new_market()
    market['inventory'].update({p: inventory for p in e.PRODUCTS})
    e._refresh_prices(market)
    town = e._new_town()
    state = []
    for player in range(2):
        private = e._new_private()
        private['shed'].update(lots or {'MILK': 30, 'EGG': 20, 'WOOL': 30})
        state.append(S(observation=S(player=player, step=step, day=step//24, hour=step%24,
                                     farms=farms, private=private, market=market, town=town),
                       action={'farmer': ['PASS'], 'hands': [], 'market': []},
                       status='ACTIVE', reward=0))
    env = S(configuration=cfg, done=False, info={'seed': 318116})
    route = [{'farmer': ['PASS'], 'hands': [], 'market': []} for _ in range(720)]
    base = copy.deepcopy(route[step])
    base['market'] = [[], ['BUY_SEED', 'CARROT', 30], ['SELL', 'MILK', 30],
                      ['SELL', 'EGG', 20], ['SELL', 'WOOL', 30]]
    return state, env, route, base


def snapshot(bot):
    names = ('planned', 'pending', 'previous', 'observed_harvests', 'diagnostics',
             'selected_post_units', 'selected_post_units_binding')
    return {name: copy.deepcopy(getattr(bot, name)) for name in names if hasattr(bot, name)}


def call(bot, obs, cfg, base):
    counts = [0]
    code = OLD.SellScheduler.rival_supply.__code__
    def profile(frame, event, arg):
        if event == 'call' and frame.f_code is code:
            counts[0] += 1
    prior = sys.getprofile()
    try:
        sys.setprofile(profile)
        result = bot.transform(obs, cfg, base)
    finally:
        sys.setprofile(prior)
    return result, snapshot(bot), counts[0]


class CacheTests(unittest.TestCase):
    def pair(self, state, env, route, base, seat=0, setup=None):
        results = []
        for module in (OLD, NEW):
            bot = consumer(module, route)
            if setup:
                setup(bot)
            obs, cfg, action = copy.deepcopy((state[seat].observation, env.configuration, base))
            before = copy.deepcopy((obs, cfg, action))
            out, saved, calls = call(bot, obs, cfg, action)
            self.assertEqual((obs, cfg, action), before)
            self.assertEqual(bot.controller.R['fixture'], route)
            results.append((out, saved, calls))
        self.assertEqual(results[0][:2], results[1][:2])
        REPORT['native_cases'] += 1
        return results

    def test_01_exact_source_and_all_runtime_pins(self):
        self.assertEqual(REPORT['source_git_blob'], SOURCE_BLOB)
        self.assertEqual(REPORT['runtime_files_verified'], 109)
        self.assertEqual(NEW.SellScheduler, OLD.SellScheduler)

    def test_02_same_turn_seed_funding_scan_reduction(self):
        result = self.pair(*fixture())
        self.assertTrue(result[0][1]['diagnostics']['same_turn_funding']['applied'])
        self.assertEqual(result[0][2], 29)
        self.assertEqual(result[1][2], 3)
        REPORT['scans'].append({'case': 'seed-funding', 'control': result[0][2], 'candidate': result[1][2]})

    def test_03_failed_acquisition_scan_reduction(self):
        state, env, route, base = fixture()
        base['market'][1] = ['BUY_LAND']
        result = self.pair(state, env, route, base)
        self.assertGreater(result[0][2], result[1][2])
        REPORT['scans'].append({'case': 'land-funding', 'control': result[0][2], 'candidate': result[1][2]})

    def test_04_all_products_and_boundary_quantities(self):
        for seat in (0, 1):
            for product in ENGINE.PRODUCTS:
                for quantity in (0, 1, 7):
                    with self.subTest(seat=seat, product=product, quantity=quantity):
                        state, env, route, base = fixture(seat=seat, lots={product: quantity})
                        base['market'] = [[], ['BUY_ANIMAL', 'COW', 2], ['SELL', product, quantity]]
                        self.pair(state, env, route, base, seat)

    def test_05_floor_scarcity_and_all_fixed_acquisition_kinds(self):
        for inventory in (9700, 10000, 11000):
            for buy in (['BUY_ANIMAL', 'COW', 2], ['BUY_SEED', 'CARROT', 30], ['HIRE'], ['BUY_LAND']):
                with self.subTest(inventory=inventory, buy=buy):
                    state, env, route, base = fixture(inventory=inventory)
                    base['market'][1] = buy
                    self.pair(state, env, route, base)

    def test_06_buy_product_barrier_raw_suffix_and_duplicate_sales(self):
        for market in (
            [[], ['BUY_PRODUCT', 'WHEAT', 2], ['SELL', 'MILK', 30]],
            [['SELL', 'MILK', 3], [], ['BUY_SEED', 'CARROT', 5], ['SELL', 'MILK', 27]],
            [[]] * 10 + [['BUY_ANIMAL', 'COW', 2], ['SELL', 'MILK', 30]],
        ):
            state, env, route, base = fixture()
            base['market'] = market
            self.pair(state, env, route, base)

    def test_07_terminal_and_day_boundaries_no_eager_lookup(self):
        for step in (0, 22, 23, 24, 717, 718):
            state, env, route, base = fixture(step=step, lots={'MILK': 2})
            result = self.pair(state, env, route, base)
            if step == 718:
                self.assertEqual((result[0][2], result[1][2]), (0, 0))

    def test_08_empty_shed_and_unused_malformed_product_are_lazy(self):
        state, env, route, base = fixture(lots={'MILK': 0}, rich=False)
        state[0].observation.farms[1]['tiles'][0][0] = {'kind': 'PLANT', 'crop': 'MELON', 'yield_units': 'invalid'}
        base['market'] = []
        result = self.pair(state, env, route, base)
        self.assertEqual((result[0][2], result[1][2]), (0, 0))
        bot = consumer(NEW, route)
        lookup = NEW._rival_supply_for_transform(bot, state[0].observation)
        self.assertEqual(lookup('MILK'), 0)
        for _ in range(2):
            with self.assertRaises(ValueError):
                lookup('MELON')
        self.assertEqual(lookup.cache_info().misses, 3)  # Errors never cached.

    def test_09_zero_supply_is_cached_and_cache_is_bounded(self):
        state, _, route, _ = fixture(rich=False)
        bot = consumer(NEW, route)
        lookup = NEW._rival_supply_for_transform(bot, state[0].observation)
        self.assertEqual([lookup('MILK') for _ in range(8)], [0]*8)
        self.assertEqual(lookup.cache_info().hits, 7)
        for i in range(100):
            lookup('unused-' + str(i))
        self.assertEqual(lookup.cache_info().currsize, len(ENGINE.PRODUCTS))
        self.assertFalse(any('cache' in name for name in vars(bot)))

    def test_10_new_transform_sees_in_place_yield_changes_and_history(self):
        state, env, route, base = fixture(lots={'MILK': 7}, rich=False)
        bots = [consumer(module, route) for module in (OLD, NEW)]
        observations = [copy.deepcopy(state[0].observation) for _ in bots]
        for step, amount in ((100, 6), (101, 0), (101, 4), (110, 1), (0, 0)):
            results = []
            for bot, obs in zip(bots, observations):
                obs.update(step=step, day=step//24, hour=step%24)
                obs.farms[1]['tiles'][0][0] = ENGINE._new_animal('COW', 0)
                obs.farms[1]['tiles'][0][0]['yield_units'] = amount
                results.append(call(bot, obs, env.configuration, copy.deepcopy(base)))
            self.assertEqual(results[0][:2], results[1][:2])
            REPORT['native_cases'] += 1

    def test_11_new_episode_and_cross_seat_factories_are_isolated(self):
        for seat in (0, 1):
            state, _, route, _ = fixture(seat=seat, rich=False)
            bot = consumer(NEW, route)
            obs = state[seat].observation
            a = NEW._rival_supply_for_transform(bot, obs)
            self.assertEqual(a('MILK'), 0)
            obs.farms[1-seat]['tiles'][0][0] = ENGINE._new_animal('COW', 0)
            obs.farms[1-seat]['tiles'][0][0]['yield_units'] = 4
            b = NEW._rival_supply_for_transform(bot, obs)
            self.assertEqual(b('MILK'), 4)
            self.assertEqual(a.cache_info().currsize, 1)
            other = consumer(NEW, route)
            other.observed_harvests = {'MILK': [(100, 98)]}
            self.assertEqual(NEW._rival_supply_for_transform(other, obs)('MILK'), 98)

    def test_12_native_cap_and_history_window_exact(self):
        state, _, route, _ = fixture(rich=False)
        for age, count in ((8, 60), (9, 60), (0, 200), (-1, 4)):
            bot = consumer(NEW, route)
            bot.observed_harvests = {'MILK': [(100-age, count)]}
            obs = state[0].observation
            lookup = NEW._rival_supply_for_transform(bot, obs)
            self.assertEqual(lookup('MILK'), bot.rival_supply(obs, 'MILK'))

    def test_13_subclass_override_keeps_call_order(self):
        state, env, route, base = fixture()
        results = []
        for module in (OLD, NEW):
            class Derived(module.FrozenSelected):
                def rival_supply(self, obs, item):
                    self.sequence.append(item)
                    return len(self.sequence) % 4
            bot = consumer(module, route, Derived)
            bot.sequence = []
            results.append((call(bot, copy.deepcopy(state[0].observation), env.configuration, copy.deepcopy(base))[:2], bot.sequence))
        self.assertEqual(results[0], results[1])
        self.assertGreater(len(results[0][1]), 10)

    def test_14_instance_override_and_replacement_remain_dynamic(self):
        state, _, route, _ = fixture()
        bot = consumer(NEW, route)
        sequence = []
        def supply(obs, item):
            sequence.append(item)
            return len(sequence)
        bot.rival_supply = supply
        lookup = NEW._rival_supply_for_transform(bot, state[0].observation)
        self.assertEqual([lookup('MILK'), lookup('MILK')], [1, 2])
        bot.rival_supply = lambda obs, item: 71
        self.assertEqual(lookup('MILK'), 71)

    def test_15_other_native_method_override_disables_cache(self):
        state, _, route, _ = fixture()
        for method in ('observe', 'cash_reserve', 'receipt_profile'):
            bot = consumer(NEW, route)
            setattr(bot, method, lambda *args: None)
            self.assertFalse(hasattr(NEW._rival_supply_for_transform(bot, state[0].observation), 'cache_info'))

    def test_16_class_monkeypatch_after_import_is_not_cached(self):
        state, _, route, _ = fixture()
        bot = consumer(NEW, route)
        with patch.object(NEW.SellScheduler, 'rival_supply', lambda self, obs, item: 17):
            lookup = NEW._rival_supply_for_transform(bot, state[0].observation)
            self.assertEqual(lookup('MILK'), 17)
            self.assertFalse(hasattr(lookup, 'cache_info'))

    def test_17_capture_postunits_and_fallback_reentry_identity(self):
        state, env, route, base = fixture(lots={'MILK': 7, 'WHEAT': 5})
        def setup(bot):
            bot.capture_post_units = True
            bot.capture_operating_stock = True
            bot.observed_harvests = {'MILK': [(99, 5)]}
        self.pair(state, env, route, base, setup=setup)
        before = copy.deepcopy(state[0].observation)
        bot = consumer(NEW, route)
        bot.transform(copy.deepcopy(before), env.configuration, copy.deepcopy(base))
        saved = snapshot(bot)
        bot2 = consumer(NEW, route)
        for name in ('pending', 'planned', 'previous', 'observed_harvests'):
            setattr(bot2, name, copy.deepcopy(saved[name]))
        self.assertFalse(any('cache' in name for name in saved))
        self.assertEqual(call(bot, copy.deepcopy(before), env.configuration, copy.deepcopy(base))[:2],
                         call(bot2, copy.deepcopy(before), env.configuration, copy.deepcopy(base))[:2])

    def test_18_official_interpreter_both_seats_units_market_eod_terminal(self):
        for seat in (0, 1):
            for step in (22, 23, 100, 718):
                for inventory in (9700, 10000, 11000):
                    with self.subTest(seat=seat, step=step, inventory=inventory):
                        state, env, route, base = fixture(seat=seat, step=step, inventory=inventory,
                                                         lots={'MILK': 7, 'EGG': 3, 'WOOL': 4})
                        state[seat].observation.private['inventories'][0] = {'MILK': 3}
                        base['farmer'] = ['DROP']
                        outputs = self.pair(state, env, route, base, seat)
                        transitions = []
                        for output in outputs:
                            states, environment = copy.deepcopy((state, env))
                            states[seat].action = output[0]
                            states[1-seat].action = {'farmer': ['PASS'], 'hands': [],
                                                    'market': [['SELL', 'MILK', 6], ['SELL', 'WOOL', 3]]}
                            ENGINE.interpreter(states, environment)
                            transitions.append((states, environment))
                        self.assertEqual(transitions[0], transitions[1])
                        REPORT['official_interpreter_pairs'] += 1

    def test_19_naive_consumer_mode_keeps_choices(self):
        self.pair(*fixture(money=100000), setup=lambda b: setattr(b, 'mode', 'naive'))

    def test_20_history_and_tiles_input_not_mutated_by_cached_query(self):
        state, _, route, _ = fixture()
        bot = consumer(NEW, route)
        bot.observed_harvests = {'MILK': [(99, 6), (91, 44)]}
        before = copy.deepcopy((state, bot.observed_harvests))
        lookup = NEW._rival_supply_for_transform(bot, state[0].observation)
        for product in ENGINE.PRODUCTS * 2:
            self.assertEqual(lookup(product), bot.rival_supply(state[0].observation, product))
        self.assertEqual((state, bot.observed_harvests), before)

    def test_21_alternative_economic_rules_and_custom_parameters_are_unchanged(self):
        for rule in ('strict', 'expected_downside', 'minimax_regret'):
            for seat in (0, 1):
                state, env, route, base = fixture(seat=seat, lots={'MILK': 7, 'EGG': 3})
                env.configuration.update(sellAcceptanceRule=rule, sellDownsideBound=10,
                                         sellScenarioWeights={'no_rival': 3, 'observed_paired': 1})
                params = copy.deepcopy(ENGINE.MARKET_PARAMS)
                params['MILK'].update(base=71, above_func='log', above_target=0.4)
                state[seat].observation.market['params'] = params
                ENGINE._refresh_prices(state[seat].observation.market)
                self.pair(state, env, route, base, seat)

    def test_22_terminal_callback_does_not_validate_unused_rival_tiles(self):
        state, env, route, base = fixture(step=718)
        state[0].observation.farms[1]['tiles'][0][0] = {'kind': 'PLANT', 'crop': 'MILK', 'yield_units': 'bad'}
        result = self.pair(state, env, route, base)
        self.assertEqual((result[0][2], result[1][2]), (0, 0))

    def test_23_transformer_rejects_wrong_bytes_under_optimization(self):
        source = (ROOT / 'frozen_selected.py').read_bytes()
        for wrong in (b'', source + b'\n', transform(source)):
            with self.assertRaises(ValueError):
                transform(wrong)
        with self.assertRaises(TypeError):
            transform(source.decode())

    def test_24_cli_rejects_overwrite_source_alias_and_wrong_pin(self):
        script = Path(__file__).with_name('rival_supply_cache.py')
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory)/'in.py', Path(directory)/'out.py'
            original = (ROOT / 'frozen_selected.py').read_bytes()
            source.write_bytes(original)
            def run(a, b):
                return subprocess.run([sys.executable, *(['-O'] if not __debug__ else []),
                                       str(script), str(a), str(b)], capture_output=True, text=True)
            self.assertEqual(run(source, output).returncode, 0)
            postimage = output.read_bytes()
            self.assertEqual(run(source, output).returncode, 2)
            self.assertEqual(run(source, source).returncode, 2)
            self.assertEqual(output.read_bytes(), postimage)
            self.assertEqual(source.read_bytes(), original)
            source.write_bytes(original + b'\n')
            output.unlink()
            self.assertEqual(run(source, output).returncode, 2)
            self.assertFalse(output.exists())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        prepare(args.runtime_root)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, str(error) + '\n')
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(CacheTests))
    REPORT.update(tests=result.testsRun, errors=len(result.errors), failures=len(result.failures),
                  passed=result.wasSuccessful(), optimized=not __debug__, python=sys.version,
                  stdout=output.getvalue(), full_game_strength_measured=False,
                  production_activated=False)
    args.output.write_text(json.dumps(REPORT, indent=2, sort_keys=True) + '\n')
    print(output.getvalue(), end='')
    print(json.dumps({k:v for k,v in REPORT.items() if k not in ('stdout','engine_sha256')}, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
