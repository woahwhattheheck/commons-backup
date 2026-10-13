# SPDX-License-Identifier: Apache-2.0
"""Exact-source/full-interpreter differential checks for KINETIC (offline only)."""
from __future__ import annotations
import argparse
import ast
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest

import compose_kinetic as composer

ROOT = Path(os.environ.get('KINETIC_NATIVE_ROOT', '/nonexistent/explicit-native-root-required'))
COUNTS = {'direct_pairs': 0, 'interpreter_pairs': 0, 'interpreter_completed_pairs': 0, 'interpreter_exception_pairs': 0, 'initializations': 0, 'expected_exceptions': 0}
OVERRIDE = None
ENGINE_PINS = {
    'kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
}


def authenticate(root):
    manifest = (root / 'SOURCE.json').read_bytes()
    if hashlib.sha256(manifest).hexdigest() != 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2':
        raise ValueError('Unverified SOURCE manifest')
    source = json.loads(manifest)
    for name, pin in source['runtime'].items():
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != pin['sha256']:
            raise ValueError(f'Unverified runtime input: {name}')
    for name, pin in ENGINE_PINS.items():
        if composer.git_blob((root / 'checks/reference/engine' / name).read_bytes()) != pin:
            raise ValueError(f'Unverified engine input: {name}')
    if composer.git_blob((root / 'mechanics.py').read_bytes()) != composer.BASE_BLOB:
        raise ValueError('Expected immutable original mechanics input')
    return len(source['runtime'])


def module(text, name):
    result = types.ModuleType(name)
    exec(compile(text, name, 'exec'), result.__dict__)
    return result


def imported(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def graph(value, memo=None):
    """Include mutable alias topology, dict order, types and nonfinite values."""
    memo = {} if memo is None else memo
    if isinstance(value, (dict, list, tuple)):
        identity = id(value)
        if identity in memo:
            return ('ref', memo[identity])
        index = len(memo)
        memo[identity] = index
        type_name = type(value).__name__
        if isinstance(value, dict):
            contents = tuple((graph(k, memo), graph(v, memo)) for k, v in value.items())
        else:
            contents = tuple(graph(v, memo) for v in value)
        return (type_name, index, contents)
    if isinstance(value, float) and not math.isfinite(value):
        return ('float', repr(value))
    return (type(value).__name__, value)


def outcome(fn, *args):
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        try:
            value = fn(*args)
            return ('return', graph(value), stdout.getvalue())
        except Exception as exc:
            return ('raise', type(exc).__name__, str(exc), stdout.getvalue())


def simple_world(position=(1, 1), inventory_count=3, alias=False):
    farm = {'farmer': list(position), 'hands': [[2, 2], [1, 1]],
            'tiles': [[None for _ in range(10)] for _ in range(10)],
            'money': 1000, 'unlocked_quadrants': 1, 'hires_today': 2}
    one = {'WHEAT': 4, 'FERTILIZER': 2, 'COW': 1}
    inventories = [one if alias else copy.deepcopy(one) for _ in range(inventory_count)]
    private = {'inventories': inventories, 'shed': {'WHEAT': 8, 'MILK': 3, 'COW': 2},
               'seeds': {'WHEAT': 2, 'CARROT': 1}}
    return farm, private


class KineticChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = authenticate(ROOT)
        cls.source = (ROOT / 'mechanics.py').read_text()
        cls.candidate = OVERRIDE or composer.compose(cls.source)
        cls.loader = imported('kinetic_checked_loader', ROOT / 'checks/reference/evaluator/loader.py')
        cls.engine_source = (ROOT / 'checks/reference/engine/kaggriculture.py').read_text()
        for name in [*composer.DEPENDENCIES, '_apply_unit_action']:
            if composer.function_span(cls.source, name)[2] != composer.function_span(cls.engine_source, name)[2]:
                raise ValueError('The direct oracle is not the exact pinned engine helper')

    def setUp(self):
        self.base = module(self.source, 'baseline_mechanics')
        self.fast = module(self.candidate, 'candidate_mechanics')

    def pair(self, world, idx, action, board=10, day=8, turns=24, capacity=100):
        left = copy.deepcopy([*world, action])
        right = copy.deepcopy([*world, action])
        result_a = outcome(self.base._apply_unit_action, left[0], left[1], idx, left[2], board, day, turns, capacity)
        result_b = outcome(self.fast._apply_unit_action, right[0], right[1], idx, right[2], board, day, turns, capacity)
        self.assertEqual(result_a, result_b, (idx, action))
        self.assertEqual(graph(left), graph(right), (idx, action))
        COUNTS['direct_pairs'] += 1
        COUNTS['expected_exceptions'] += result_a[0] == 'raise'
        return left, result_a

    def test_01_actor_inventory_movement_matrix(self):
        for pos in [(0, 0), (9, 9), (1, 1), (4, 4), (4, 3)]:
            for n in [0, 1, 3]:
                for idx in [0, 1, 2, 3, 8, -1, -2, False, True, 1.0]:
                    for action in [['PASS'], ['EAST'], ['WEST'], ['NORTH'], ['SOUTH']]:
                        self.pair(simple_world(pos, n), idx, action)

    def test_02_alias_replacement_not_in_place(self):
        for idx in [0, 1, 2, -1]:
            f, p = simple_world(alias=True)
            shared = f['farmer']
            f['hands'] = [shared, shared]
            p['position_alias'] = shared
            for action in [['EAST'], ['SOUTH'], ['PASS'], ['PICKUP', 'WHEAT', 3]]:
                self.pair((f, p), idx, action)

    def test_03_pass_grows_inventory_and_ghost_precedes_bad_opcode(self):
        pair, result = self.pair(simple_world(inventory_count=0), 2, ['PASS'])
        self.assertEqual(len(pair[1]['inventories']), 3)
        for idx in [3, 50]:
            pair, result = self.pair(simple_world(inventory_count=0), idx, [[], 'unused'])
            self.assertEqual(result[0], 'return')
            self.assertEqual(pair[1]['inventories'], [])
        for idx in [-1, -2, -50]:
            self.pair(simple_world(inventory_count=0), idx, ['PASS'])

    def test_04_malformed_action_and_position_side_effects(self):
        actions = [None, [], (), 'PASS', 1, {}, [None], [{}], [[]], [1],
                   ['PICKUP', 'WHEAT', float('inf')], ['PLACE', 'WHEAT', float('nan')],
                   ['PLACE', 'COW', float('inf')], ['PLANT', []], ['UNKNOWN']]
        for action in actions:
            for idx in [0, 1, 3, -1]:
                self.pair(simple_world((4, 4), 0), idx, action)
        for position in [None, [], [1], [1.5, 2], [-1, 0], [20, 20], 3]:
            f, p = simple_world()
            f['farmer'] = position
            for action in [['PASS'], ['EAST'], ['CARE']]:
                self.pair((f, p), 0, action)

    def test_05_complete_action_tail(self):
        actions = [['PASS'], ['PLANT', 'WHEAT'], ['PLANT', 'CARROT'], ['PLANT', 'UNKNOWN'],
                   ['WATER'], ['HARVEST'], ['FERTILIZE'], ['DIG'], ['BUILD_COOP'],
                   ['BUILD_PASTURE'], ['FEED'], ['COLLECT_FERTILIZER'], ['CARE'], ['DROP'],
                   ['PICKUP', 'WHEAT', 3], ['PLACE', 'COW'], ['PLACE', 'WHEAT', 2]]
        tiles = [None, 'LOCKED', {'kind': 'WEED'}, {'kind': 'COOP'}, {'kind': 'PASTURE'},
                 self.base._new_plant('WHEAT', 1, 24), self.base._new_animal('COW', 0),
                 self.base._new_animal('SHEEP', 0), self.base._new_animal('GOOSE', 0)]
        for pos in [(4, 4), (1, 1)]:
            for tile in tiles:
                for action in actions:
                    f, p = simple_world(pos)
                    if isinstance(tile, dict) and 'yield_units' in tile:
                        tile = dict(tile, yield_units=3)
                    if isinstance(tile, dict) and 'animal' in tile:
                        tile = dict(tile, fertilizer_available=True)
                    f['tiles'][pos[1]][pos[0]] = copy.deepcopy(tile)
                    self.pair((f, p), 0, action)

    def test_06_dynamic_helper_overrides(self):
        for target in ['_farmer_position', '_farmer_inventory', '_set_farmer_position']:
            logs = [[], []]
            for which, mod in enumerate([self.base, self.fast]):
                old = getattr(mod, target)
                def replacement(*args, _which=which, _old=old, _target=target):
                    logs[_which].append(_target)
                    if _target == '_farmer_position':
                        return [4, 4]
                    if _target == '_farmer_inventory':
                        return args[0]['inventories'][0]
                    args[0]['override_seen'] = True
                    return _old(*args)
                setattr(mod, target, replacement)
            self.pair(simple_world(), 1, ['EAST'])
            self.pair(simple_world(), 0, ['DROP'])
            self.assertEqual(logs[0], logs[1])
            self.assertGreater(len(logs[1]), 0)

    def test_07_rebound_list_uses_original_setter(self):
        class L(list):
            pass
        self.base.list = L
        self.fast.list = L
        pair, _ = self.pair(simple_world(), 0, L(['EAST']))
        self.assertIsInstance(pair[0]['farmer'], L)

    def test_08_mutable_moves_table_remains_live(self):
        for mod in [self.base, self.fast]:
            mod.FARMER_MOVES['PASS'] = (2, 1)
            mod.FARMER_MOVES['EAST'] = (0, -2)
        for action in [['PASS'], ['EAST']]:
            self.pair(simple_world(), 0, action)

    def test_09_mapping_access_order(self):
        class D(dict):
            def __getitem__(self, k):
                if k != 'log':
                    dict.__getitem__(self, 'log').append(k)
                return dict.__getitem__(self, k)
        for idx in [0, 1, 3, -1]:
            f, p = simple_world(inventory_count=0)
            f = D(f, log=[])
            p = D(p, log=[])
            self.pair((f, p), idx, ['EAST'])

    def engine_pair(self, state, env):
        ea, _ = self.loader.get_engine(ROOT / 'checks/reference/engine')
        eb, _ = self.loader.get_engine(ROOT / 'checks/reference/engine')
        code = composer.ALIASES + composer.function_span(self.candidate, '_apply_unit_action')[2]
        exec(compile(code, 'candidate_unit_only', 'exec'), eb.__dict__)
        left, right = copy.deepcopy((state, env)), copy.deepcopy((state, env))
        ra = outcome(ea.interpreter, *left)
        rb = outcome(eb.interpreter, *right)
        self.assertEqual(ra, rb)
        self.assertEqual(graph(left), graph(right))
        self.last_engine_outcome = ra
        COUNTS['interpreter_pairs'] += 1
        COUNTS['interpreter_completed_pairs'] += ra[0] == 'return'
        COUNTS['interpreter_exception_pairs'] += ra[0] == 'raise'
        return left

    def initialized(self, seed=17):
        engine, _ = self.loader.get_engine(ROOT / 'checks/reference/engine')
        cfg = self.loader.Struct({k: v.get('default') if isinstance(v, dict) else v
                                 for k, v in engine.specification['configuration'].items()})
        cfg.seed = seed
        env = self.loader.Struct(configuration=cfg, done=False, info={})
        state = [self.loader.Struct(observation=self.loader.Struct(), action={}, status='ACTIVE', reward=0)
                 for _ in range(2)]
        engine.interpreter(state, env)
        COUNTS['initializations'] += 1
        return state, env

    def test_10_full_interpreter_matrix(self):
        actions = [['PASS'], ['EAST'], ['WEST'], ['NORTH'], ['SOUTH'], ['PLANT', 'WHEAT'],
                   ['WATER'], ['HARVEST'], ['FERTILIZE'], ['DIG'], ['BUILD_COOP'],
                   ['BUILD_PASTURE'], ['FEED'], ['COLLECT_FERTILIZER'], ['CARE'],
                   ['PICKUP', 'WHEAT', 3], ['PLACE', 'COW'], ['DROP']]
        state, env = self.initialized()
        for seat in [0, 1]:
            for step in [0, 22, 23, 24, 718]:
                for action in actions:
                    st, en = copy.deepcopy((state, env))
                    for s in st:
                        s.observation.step = step
                    farm = st[0].observation.farms[seat]
                    farm['farmer'] = [4, 4]
                    farm['hands'] = [[1, 1], [4, 4]]
                    farm['tiles'][4][4] = None
                    private = st[seat].observation.private
                    private['inventories'] = [{'WHEAT': 3, 'COW': 1, 'FERTILIZER': 2}]
                    private['shed']['WHEAT'] = 20
                    private['seeds']['WHEAT'] = 2
                    st[seat].action = {'farmer': action, 'hands': [['PASS'], ['EAST'], ['PLANT', 'WHEAT']],
                                       'market': [['SELL', 'WHEAT', 2], ['HIRE']]}
                    st[1-seat].action = {'farmer': ['PASS'], 'market': [['BUY_PRODUCT', 'WHEAT', 1]]}
                    self.engine_pair(st, en)

    def test_11_atomic_plant_ghost_remains_engine_owned(self):
        for seat in [0, 1]:
            st, en = self.initialized()
            f = st[0].observation.farms[seat]
            f['farmer'] = [1, 1]
            f['hands'] = [[2, 1]]
            f['tiles'][1][1] = f['tiles'][1][2] = None
            st[seat].observation.private['seeds']['WHEAT'] = 2
            st[seat].observation.private['inventories'] = []
            st[seat].action = {'farmer': ['PLANT', 'WHEAT'],
                               'hands': [['PLANT', 'WHEAT'], ['PLANT', 'WHEAT']]}
            (result, _env) = self.engine_pair(st, en)
            self.assertEqual(result[seat].observation.private['seeds']['WHEAT'], 2)
            self.assertIsNone(result[0].observation.farms[seat]['tiles'][1][1])

    def test_12_full_interpreter_conversion_exceptions(self):
        for seat in [0, 1]:
            for action in [['PICKUP', 'WHEAT', float('inf')], ['PLACE', 'WHEAT', float('nan')],
                           ['PLACE', 'COW', float('inf')]]:
                st, en = self.initialized()
                farm = st[0].observation.farms[seat]
                farm['farmer'] = [4, 4]
                farm['tiles'][4][4] = {'kind': 'PASTURE'}
                st[seat].observation.private['inventories'] = [{'COW': 1, 'WHEAT': 3}]
                st[seat].action = {'farmer': action}
                self.engine_pair(st, en)
                self.assertEqual(self.last_engine_outcome[0], 'return' if action[1] == 'COW' else 'raise')
                if action[1] == 'WHEAT':
                    self.assertEqual(self.last_engine_outcome[1], 'OverflowError' if action[0] == 'PICKUP' else 'ValueError')

    def test_13_composer_idempotence_and_unrelated_bytes(self):
        source = self.source + '\n# unrelated peer suffix\n'
        start, end, old = composer.function_span(source, '_apply_unit_action')
        candidate = composer.compose(source)
        cstart, cend, new = composer.function_span(candidate, '_apply_unit_action')
        self.assertEqual(candidate[:cstart-len(composer.ALIASES)], source[:start])
        self.assertEqual(candidate[cend:], source[end:])
        self.assertEqual(composer.compose(candidate), candidate)
        modified = source.replace('def _spawn_hand(', '# untouched peer change\ndef _spawn_hand(', 1)
        self.assertIn('# untouched peer change', composer.compose(modified))

    def test_14_composer_rejects_drift_and_alias_corruption(self):
        for name in [*composer.DEPENDENCIES, '_apply_unit_action']:
            start, end, old = composer.function_span(self.source, name)
            changed = self.source[:start] + old.replace('\n', '\n    # changed\n', 1) + self.source[end:]
            with self.assertRaises(ValueError):
                composer.compose(changed)
        for changed in [self.source+'\n_KINETIC_POSITION = None\n',
                        composer.compose(self.source).replace('_KINETIC_LIST = list', '_KINETIC_LIST = tuple'),
                        composer.compose(self.source).replace(composer.ALIASES, '')]:
            with self.assertRaises(ValueError):
                composer.compose(changed)

    def test_15_cli_scratch_only_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src, out = td/'in.py', td/'out.py'
            src.write_text(self.source)
            command = [sys.executable] + (['-O'] if sys.flags.optimize else []) + [str(Path(composer.__file__)), '--input', str(src), '--output', str(out)]
            ok = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(out.read_text(), composer.compose(self.source))
            self.assertEqual(src.read_text(), self.source)
            for argv in [command[:-1]+[str(src)], command]:
                src.write_text(self.source.replace('fx + dx', 'fx - dx', 1))
                out.write_text('preserved')
                failure = subprocess.run(argv, capture_output=True, text=True, timeout=10)
                self.assertNotEqual(failure.returncode, 0)
                self.assertEqual(out.read_text(), 'preserved')


def main():
    global ROOT, OVERRIDE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-root', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    ROOT = args.native_root
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(KineticChecks)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'skipped': len(result.skipped), 'mode': 'optimized' if sys.flags.optimize else 'normal',
              'counts': COUNTS, 'scope': 'constructed source/direct/full-interpreter parity, not field economics'}
    if args.report:
        args.report.write_text(json.dumps(report, sort_keys=True, indent=2)+'\n')
    print(json.dumps(report, sort_keys=True))
    return 0 if result.wasSuccessful() and not result.skipped and result.testsRun else 1

if __name__ == '__main__':
    raise SystemExit(main())
