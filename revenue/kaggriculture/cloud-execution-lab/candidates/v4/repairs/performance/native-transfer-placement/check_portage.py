# SPDX-License-Identifier: Apache-2.0
"""Independent official-engine and actual native-caller gate for PORTAGE."""
from __future__ import annotations
import argparse
import ast
from contextlib import contextmanager
import copy
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import types
import unittest

from compose_portage import BASE_BLOB, ORIGINALS, REPLACEMENTS, compose, spans

ROOT = None
CANDIDATE = None
COUNTS = {}

def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def source_module(raw, name):
    module = types.ModuleType(name)
    exec(compile(raw, name, 'exec'), module.__dict__)
    return module

def ordered(value):
    return json.dumps(value, separators=(',', ':'), allow_nan=True)

@contextmanager
def with_mechanics(module, mechanics):
    before = module.m
    module.m = mechanics
    try:
        yield
    finally:
        module.m = before

class Portage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / 'mechanics.py').read_bytes()
        if blob(cls.raw) != BASE_BLOB:
            raise ValueError('wrong baseline mechanics')
        cls.out = CANDIDATE.read_bytes() if CANDIDATE else compose(cls.raw)
        cls.base = source_module(cls.raw, 'portage_baseline')
        cls.fast = source_module(cls.out, 'portage_candidate')
        cls.ev = load(ROOT / 'checks/reference/evaluator/evaluate.py', 'portage_evaluator')
        cls.engine, cls.hashes = cls.ev.get_engine(
            ROOT / 'checks/reference/engine', ROOT / 'checks/reference/evaluator/loader.py')
        cls.changed_engine, _ = cls.ev.get_engine(
            ROOT / 'checks/reference/engine', ROOT / 'checks/reference/evaluator/loader.py')
        for name, (a, b) in spans(cls.out).items():
            if name in ORIGINALS:
                exec(compile(cls.out[a:b], 'portage_engine_component', 'exec'),
                     cls.changed_engine.__dict__)
        sys.path.insert(0, str(ROOT))
        cls.scheduler = load(ROOT / 'scheduler.py', 'portage_native_scheduler')
        COUNTS['engine_sha256'] = cls.hashes
        COUNTS['input_blob'] = blob(cls.raw)
        COUNTS['output_blob'] = blob(cls.out)

    def fixture(self, seat=0, step=23, cap=100, variation=0):
        e, S = self.engine, self.ev.Struct
        cfg = S({k: v.get('default') if isinstance(v, dict) else v
                 for k, v in e.specification['configuration'].items()})
        cfg.shedCapacity = cap
        cfg.weedSpawnChance = 0.1
        farms = [e._new_farm(10, 5000), e._new_farm(10, 5000)]
        market = e._new_market()
        e._refresh_prices(market)
        state = []
        for player in range(2):
            farm = farms[player]
            farm['hands'] = [[5, 4], [4, 5], [5, 5], [0, 0]]
            private = e._new_private()
            private['shed'].update({'MILK': 15, 'WHEAT': 10, 'FERTILIZER': 5})
            private['inventories'] = [
                {'WOOL': 20 + variation, 'MILK': 15}, {'FERTILIZER': 7},
                {'EGG': 6}, {'CARROT': 5}, {'TOMATO': 3}]
            action = {'farmer': ['DROP'],
                      'hands': [['PICKUP', 'WHEAT', 4], ['PLACE', 'EGG', 2],
                                ['DROP'], ['DROP']],
                      'market': [['HIRE'], ['SELL', 'MILK', 7],
                                 ['BUY_PRODUCT', 'FERTILIZER', 3], ['HIRE']]}
            if player != seat:
                action['market'] = [['SELL', 'WHEAT', 5], ['HIRE']]
            state.append(S(observation=S(player=player, step=step, day=step // 24,
                hour=step % 24, farms=farms, private=private, market=market,
                town={'unlocked_shops': ['BAKERY', 'YARN_STORE']}),
                action=action, status='ACTIVE', reward=0))
        return state, S(configuration=cfg, done=False, info={'seed': 83017 + variation})

    def test_01_integer_geometry(self):
        count = 0
        for size in (-7, 0, 1, 2, 3, 10, 11, 64, 10**30):
            h = size // 2
            for x, y in itertools.product(range(h - 3, h + 3), repeat=2):
                for pos in ([x, y], (x, y)):
                    self.assertEqual(self.fast._is_shed_adjacent(pos, size),
                                     self.engine._is_shed_adjacent(pos, size))
                    count += 1
        COUNTS['integer_geometry_cells'] = count

    def test_02_generic_geometry_and_exceptions(self):
        cases = [([4.0, 5.0], 10), ([True, False], 2), ([4, 5], 10.0),
                 ([0, 0], False), (['4', '5'], 10), ([], 10), ([4], 10),
                 ([4, 5, 6], 10), ([[4], 5], 10), (None, 10), ([4, 5], None),
                 ([float('nan'), 5], 10), ({4: 1, 5: 2}, 10)]
        def outcome(fn, pos, size):
            try:
                return ('return', fn(copy.deepcopy(pos), size))
            except Exception as exc:
                return (type(exc).__name__, str(exc))
        for pos, size in cases:
            with self.subTest(pos=pos, size=size):
                self.assertEqual(outcome(self.fast._is_shed_adjacent, pos, size),
                                 outcome(self.base._is_shed_adjacent, pos, size))
        self.assertTrue(self.fast._is_shed_adjacent(iter([4, 5]), 10))

    def test_03_spawn_ties_and_inputs_unchanged(self):
        count = 0
        for size in (2, 10, 11, 32, 10.0, True):
            tiles = self.base._shed_access_tiles(size)
            for counts in itertools.product(range(3), repeat=4):
                farm = {'farmer': [100, 100], 'hands':
                        [list(p) for p, n in zip(tiles, counts) for _ in range(n)]}
                before = copy.deepcopy(farm)
                got = self.fast._spawn_hand(farm, size)
                self.assertEqual(got, self.engine._spawn_hand(farm, size))
                self.assertIs(type(got), list)
                self.assertEqual(farm, before)
                count += 1
        COUNTS['spawn_cells'] = count

    def test_04_transfer_order_overflow_and_cleanup(self):
        rng = random.Random(87013)
        count = 0
        goods = self.base.PRODUCTS + ['COW', 'SHEEP', 'GOOSE']
        for cap in (-1, 0, 1, 30, 100, 200, 10**30, 20.5):
            for _ in range(80):
                rng.shuffle(goods)
                private = {'shed': {p: rng.randrange(0, 12) for p in goods},
                           'inventories': [{p: rng.randrange(-2, 15) for p in
                               rng.sample(goods, rng.randrange(0, len(goods) + 1))}
                               for _ in range(rng.randrange(0, 9))],
                           'seeds': {'WHEAT': 29}}
                a, b = copy.deepcopy(private), copy.deepcopy(private)
                self.fast._drop_inventories_to_shed(a, cap)
                self.engine._drop_inventories_to_shed(b, cap)
                self.assertEqual(ordered(a), ordered(b))
                count += 1
        COUNTS['ordered_transfer_cells'] = count

    def test_05_aliases_and_custom_mappings(self):
        class Unusual(dict):
            def values(self):
                raise AssertionError('must retain items() for subclasses')
            def items(self):
                return list(super().items())[::-1]
        shed = {'WOOL': 6, 'EGG': 10}
        inv = {'MILK': 3, 'WHEAT': 2}
        cases = [{'shed': shed, 'inventories': [shed, inv, inv]},
                 {'shed': Unusual(WOOL=6, EGG=10), 'inventories': [inv]},
                 {'shed': {'WOOL': 2.5, 'EGG': 1.5}, 'inventories': [inv]}]
        for private in cases:
            a, b = copy.deepcopy(private), copy.deepcopy(private)
            self.fast._drop_inventories_to_shed(a, 19.5)
            self.base._drop_inventories_to_shed(b, 19.5)
            self.assertEqual(ordered(a), ordered(b))
        a = copy.deepcopy(cases[0])
        self.fast._drop_inventories_to_shed(a, 19.5)
        self.assertIs(a['shed'], a['inventories'][0])
        self.assertIs(a['inventories'][1], a['inventories'][2])

    def test_06_full_official_interpreter_differential(self):
        count = 0
        for seat, step, cap, variation in itertools.product(
                (0, 1), (0, 1, 22, 23, 46, 47, 70, 71, 718), (0, 1, 30, 100, 200), (0, 1)):
            state, env = self.fixture(seat, step, cap, variation)
            other, other_env = copy.deepcopy(state), copy.deepcopy(env)
            self.engine.interpreter(state, env)
            self.changed_engine.interpreter(other, other_env)
            self.assertEqual(ordered(other), ordered(state))
            self.assertEqual(other_env, env)
            count += 1
        COUNTS['full_interpreter_pairs'] = count

    def test_07_actual_post_units(self):
        count = 0
        for seat, step, cap in itertools.product((0, 1), (1, 22, 23, 47), (0, 1, 30, 100, 200)):
            state, env = self.fixture(seat, step, cap)
            obs, action = state[seat].observation, state[seat].action
            before = ordered((obs, action, env.configuration))
            with with_mechanics(self.scheduler, self.base):
                a = self.scheduler.post_units(obs, action, env.configuration)
            with with_mechanics(self.scheduler, self.fast):
                b = self.scheduler.post_units(obs, action, env.configuration)
            farm, private = copy.deepcopy(obs['farms'][seat]), copy.deepcopy(obs['private'])
            for i, command in enumerate([action['farmer'], *action['hands']]):
                self.engine._apply_unit_action(farm, private, i, command, 10, step // 24, 24, cap)
            self.assertEqual(ordered(a), ordered((farm, private)))
            self.assertEqual(ordered(b), ordered(a))
            self.assertEqual(ordered((obs, action, env.configuration)), before)
            count += 1
        COUNTS['native_post_units_cells'] = count

    def test_08_actual_receipt_consumer_and_optimizer(self):
        count = 0
        for seat, cap, variation in itertools.product((0, 1), (20, 100, 200), range(4)):
            state, env = self.fixture(seat, 20, cap, variation)
            obs, action = state[seat].observation, state[seat].action
            route = [copy.deepcopy(action) for _ in range(24)]
            scheduler = object.__new__(self.scheduler.SellScheduler)
            scheduler.controller = types.SimpleNamespace(R=[route], cur=0)
            results = []
            for mechanics in (self.base, self.fast):
                with with_mechanics(self.scheduler, mechanics):
                    farm, private = self.scheduler.post_units(obs, action, env.configuration)
                    feasible = scheduler.receipt_profile(
                        obs, action, farm, private, 23, 'MILK', env.configuration)
                    profile = copy.deepcopy(dict(zip(feasible.__code__.co_freevars,
                        [cell.cell_contents for cell in feasible.__closure__])))
                    result = self.scheduler.optimize_lot(item='MILK', quantity=6,
                        inventory=10000, params=None, shops=[], config=env.configuration,
                        now=20, dates=[20, 21, 23], reference=((20, 3), (23, 3)),
                        rival_quantity=3, capacity_ok=feasible)
                    results.append((profile, result))
            self.assertEqual(ordered(results[0]), ordered(results[1]))
            count += 1
        COUNTS['native_receipt_optimizer_cells'] = count

    def test_09_composition_idempotence_and_peer_preservation(self):
        def mask(raw):
            for a, b in sorted([v for k, v in spans(raw).items() if k in ORIGINALS], reverse=True):
                raw = raw[:a] + b'<owned>' + raw[b:]
            return raw
        self.assertEqual(compose(compose(self.raw)), compose(self.raw))
        self.assertEqual(mask(self.raw), mask(compose(self.raw)))
        peer = b'# peer Unicode: \xe2\x98\x83\n' + self.raw.replace(
            b'    """Floor at PRICE_FLOOR."""', b'    """Peer price-kernel documentation."""')
        self.assertEqual(mask(peer), mask(compose(peer)))
        all_locations = spans(self.raw)
        for bits in itertools.product((0, 1), repeat=3):
            partial = self.raw
            for (name, (a, b)), enabled in sorted(
                    zip([(k, all_locations[k]) for k in ORIGINALS], bits),
                    key=lambda x: x[0][1][0], reverse=True):
                if enabled:
                    partial = partial[:a] + REPLACEMENTS[name].encode() + partial[b:]
            self.assertEqual(compose(partial), compose(self.raw))

    def test_10_source_drift_rejected(self):
        cases = [self.raw + b'\ndef _spawn_hand(farm, board_size):\n    return [0, 0]\n',
                 self.raw.replace(b'    half = board_size // 2', b'    half = board_size // 3'),
                 self.raw.replace(b'def _spawn_hand(', b'@staticmethod\ndef _spawn_hand('),
                 self.raw + b'\n_spawn_hand = lambda *a: [0, 0]\n',
                 self.raw + b'\nfrom missing import _spawn_hand\n']
        for name, (a, b) in spans(self.raw).items():
            if name in ORIGINALS:
                cases.append(self.raw[:a] + self.raw[a:b].replace(b'    ', b'     ', 1) + self.raw[b:])
        for raw in cases:
            with self.assertRaises((ValueError, SyntaxError)):
                compose(raw)

    def test_11_cli_no_overwrite_or_symlink(self):
        script = Path(__file__).with_name('compose_portage.py')
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src, dst = td / 'input.py', td / 'out.py'
            src.write_bytes(self.raw)
            def call(output):
                return subprocess.run([sys.executable, *(['-O'] if sys.flags.optimize else []),
                    str(script), str(src), str(output)], capture_output=True, timeout=5)
            self.assertEqual(call(dst).returncode, 0)
            self.assertEqual(dst.read_bytes(), compose(self.raw))
            for target in (src, dst):
                self.assertNotEqual(call(target).returncode, 0)
            link = td / 'link.py'
            link.symlink_to(src)
            self.assertNotEqual(call(link).returncode, 0)
            self.assertEqual(src.read_bytes(), self.raw)
            self.assertEqual(dst.read_bytes(), compose(self.raw))

    def test_12_geometry_allocation_elimination(self):
        farm = {'farmer': [4, 4], 'hands': [[5, 4], [4, 5]]}
        counts = []
        for module in (self.base, self.fast):
            original = module._shed_access_tiles
            calls = []
            def traced(size):
                calls.append(size)
                return original(size)
            module._shed_access_tiles = traced
            try:
                self.assertTrue(module._is_shed_adjacent([4, 5], 10))
                adjacent_calls = len(calls)
                calls.clear()
                self.assertEqual(module._spawn_hand(farm, 10), [5, 5])
                counts.append([adjacent_calls, len(calls)])
            finally:
                module._shed_access_tiles = original
        self.assertEqual(counts, [[1, 5], [0, 1]])
        COUNTS['adjacency_spawn_geometry_calls'] = counts


def main():
    global ROOT, CANDIDATE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    ROOT, CANDIDATE = args.runtime_root.resolve(), args.candidate
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Portage)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = dict(COUNTS, tests=result.testsRun, failures=len(result.failures),
                  errors=len(result.errors), skipped=len(result.skipped),
                  optimized=sys.flags.optimize, python=sys.version)
    text = json.dumps(report, indent=2) + '\n'
    if args.receipt:
        args.receipt.write_text(text)
    print(text)
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    raise SystemExit(main())
