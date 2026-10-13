# SPDX-License-Identifier: Apache-2.0
"""Independent full-interpreter tests for the existing evaluator repair.

Run with --source LAB/reference/evaluator/loader.py --engine LAB/reference/engine.
--candidate may supply a staged loader or a deliberately broken control.
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

from repair_loader import SOURCE_BLOB, blob_hash, repair_source

ENGINE_PINS = {
    'kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
}
CONFIG = {'episodeSteps': 5, 'weedSpawnChance': 0}
BASE = CAND = ENGINE = SOURCE = None
TRANSITIONS = 0


def load_bytes(name, source, filename):
    module = types.ModuleType(name)
    module.__file__ = str(filename)
    exec(compile(source, str(filename), 'exec'), module.__dict__)
    return module


def serialized(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


class RecordedEngine:
    """Wrap, never replace, the entire pinned official interpreter."""
    def __init__(self, setup=None):
        self.specification = ENGINE.specification
        self.setup = setup
        self.frames = []
        self.action_objects = []

    def interpreter(self, state, env):
        global TRANSITIONS
        initial = not state[0].observation.get('farms')
        if not initial:
            self.action_objects.append([s.action for s in state])
        result = ENGINE.interpreter(state, env)
        TRANSITIONS += 1
        if initial and self.setup:
            self.setup(state, env)
        self.frames.append(serialized({'state': state, 'info': env.info, 'configuration': env.configuration}))
        return result


def direct_play(engine, agents, seed, configuration):
    """Independent oracle loop; no repaired helper, counting or truncation."""
    cfg = BASE.Struct({k: v.get('default') if isinstance(v, dict) else v
                       for k, v in engine.specification['configuration'].items()})
    cfg.update(configuration)
    cfg.seed = seed
    env = BASE.Struct(configuration=cfg, done=False, info={})
    state = [BASE.Struct(observation=BASE.Struct(), action={}, status='ACTIVE', reward=0)
             for _ in agents]
    engine.interpreter(state, env)
    for step in range(cfg.episodeSteps):
        for seat in range(len(agents)):
            state[seat].observation.step = step
            state[seat].action = agents[seat](copy.deepcopy(state[seat].observation), cfg)
        engine.interpreter(state, env)
        if any(s.status == 'DONE' for s in state):
            env.done = True
            break
    return {'bank': [s.reward for s in state], 'status': [s.status for s in state], 'steps': step + 1}


def fixed(action):
    return lambda obs, cfg: action


def seed_fixture(state, env):
    for seat in (0, 1):
        farm = state[seat].observation.farms[seat]
        farm['hands'] = [[3, 4]]
        state[seat].observation.private['inventories'] = [{}, {}]
        state[seat].observation.private['seeds'] = {'WHEAT': 2, 'CARROT': 1}


class SourceContract(unittest.TestCase):
    def test_source_pin(self):
        self.assertEqual(blob_hash(SOURCE), SOURCE_BLOB)

    def test_repair_compiles(self):
        compile(repair_source(SOURCE), 'candidate', 'exec')

    def test_method_drift_rejected(self):
        with self.assertRaisesRegex(ValueError, 'play source changed'):
            repair_source(SOURCE.replace(b'    daily = []', b'    daily = []  # peer'))

    def test_double_application_rejected(self):
        with self.assertRaisesRegex(ValueError, 'already present'):
            repair_source(repair_source(SOURCE))

    def test_missing_function_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            repair_source(SOURCE.replace(b'def play(', b'def other_play('))

    def test_duplicate_function_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            repair_source(SOURCE + b'\ndef play():\n    pass\n')

    def test_preserve_unrelated_peer_bytes(self):
        modified = SOURCE.replace(b'ENGINE_REF = ', b'# Independent peer comment stays byte-exact.\nENGINE_REF = ')
        out = repair_source(modified)
        marker = b'# Independent peer comment stays byte-exact.\nENGINE_REF = '
        self.assertIn(marker, out)
        before = ast.parse(SOURCE)
        after = ast.parse(out)
        def rest(tree):
            return [ast.dump(n, include_attributes=False) for n in tree.body
                    if not isinstance(n, ast.FunctionDef) or n.name not in ('play', '_record_raw_action')]
        self.assertEqual(rest(before), rest(after))


class EngineContract(unittest.TestCase):
    def compare(self, action, setup=None, config=None, seat=0):
        cfg = dict(CONFIG, **(config or {}))
        pair = [fixed({}), fixed({})]
        pair[seat] = fixed(action)
        original = copy.deepcopy(action)
        oracle_pair = [fixed({}), fixed({})]
        oracle_pair[seat] = fixed(copy.deepcopy(action))
        actual, oracle = RecordedEngine(setup), RecordedEngine(setup)
        report = CAND.play(actual, pair, 271828, cfg)
        expected = direct_play(oracle, oracle_pair, 271828, cfg)
        self.assertTrue(actual.frames == oracle.frames, 'Full official state sequence differs')
        self.assertEqual(action, original, 'Returned action was mutated')
        for key in expected:
            self.assertEqual(report[key], expected[key], key)
        for actions in actual.action_objects:
            self.assertIs(actions[seat], action, 'Raw returned object replaced')
        return report, actual

    def test_valid_actions_original_report_parity(self):
        actions = [{'farmer': ['WEST'], 'hands': [], 'market': [['HIRE']]}, {}]
        left, right = RecordedEngine(), RecordedEngine()
        expected = BASE.play(left, list(map(fixed, actions)), 1, CONFIG)
        result = CAND.play(right, list(map(fixed, actions)), 1, CONFIG)
        self.assertTrue(left.frames == right.frames, 'Baseline state sequence differs')
        for key in expected.keys() - {'max_call_seconds', 'mean_call_seconds'}:
            self.assertEqual(result[key], expected[key])
        self.assertEqual(result['raw_action_contract'][0]['extra_hand_rows'], 0)

    def test_empty_unit_rows(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                report, _ = self.compare({'farmer': [], 'hands': [[], []]}, seat=seat)
                self.assertEqual(report['raw_action_contract'][seat]['uncounted_unit_rows'], 12)
                self.assertEqual(report['actions'][seat], {})

    def test_opaque_nonlist_farmer_noops(self):
        for value in (None, True, 7, 'WEST', ('WEST',), {}):
            with self.subTest(value=value):
                self.compare({'farmer': value})

    def test_nonlist_hands_noop(self):
        for value in (None, True, 3, 'WEST', ('WEST',), {}):
            with self.subTest(value=value):
                report, _ = self.compare({'hands': value})
                self.assertEqual(report['raw_action_contract'][0]['nonlist_hands_callbacks'], 4)
                self.assertEqual(report['actions'][0], {'PASS': 4})

    def test_nonlist_market_noop(self):
        for value in (None, True, 3, 'HIRE', ('HIRE',), {}):
            with self.subTest(value=value):
                report, _ = self.compare({'market': value})
                self.assertEqual(report['raw_action_contract'][0]['nonlist_market_callbacks'], 4)

    def test_nonstring_opcode(self):
        for value in (None, 0, False):
            with self.subTest(value=value):
                report, _ = self.compare({'farmer': [value]})
                self.assertEqual(report['actions'][0], {})

    def test_unknown_string_opcode_is_counted_not_executed(self):
        report, _ = self.compare({'farmer': ['UNKNOWN_OP']})
        self.assertEqual(report['actions'][0], {'UNKNOWN_OP': 4})
        self.assertEqual(report['bank'], [3000.0, 3000.0])

    def test_surplus_hand_rows_preserved(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                report, _ = self.compare({'hands': [['WEST'], ['NORTH'], ['PASS']]}, seat=seat)
                self.assertEqual(report['raw_action_contract'][seat]['extra_hand_rows'], 12)
                self.assertEqual(report['actions'][seat], {'PASS': 8, 'WEST': 4, 'NORTH': 4})

    def test_ghost_plant_changes_real_unit_admission(self):
        action = {'farmer': ['PLANT', 'WHEAT'], 'hands': [['PLANT', 'WHEAT'], ['PLANT', 'WHEAT']]}
        for seat in (0, 1):
            with self.subTest(seat=seat):
                _, actual = self.compare(action, setup=seed_fixture, seat=seat)
                frame = json.loads(actual.frames[1])['state'][seat]['observation']
                self.assertIsNone(frame['farms'][seat]['tiles'][4][4])
                self.assertIsNone(frame['farms'][seat]['tiles'][4][3])
                self.assertEqual(frame['private']['seeds']['WHEAT'], 2)
                # Independent real-engine counterfactual: truncating ghost row permits both plants.
                cut = dict(action, hands=action['hands'][:1])
                oracle = RecordedEngine(seed_fixture)
                pair = [fixed({}), fixed({})]
                pair[seat] = fixed(cut)
                direct_play(oracle, pair, 271828, CONFIG)
                cropped = json.loads(oracle.frames[1])['state'][seat]['observation']
                self.assertEqual(cropped['farms'][seat]['tiles'][4][4]['crop'], 'WHEAT')
                self.assertEqual(cropped['private']['seeds']['WHEAT'], 0)
                self.assertNotEqual(actual.frames[1], oracle.frames[1])

    def test_omitted_real_hand_is_not_padded(self):
        report, _ = self.compare({'farmer': ['WEST']}, setup=seed_fixture)
        self.assertEqual(report['actions'][0], {'WEST': 4})

    def test_seed_admission_separate_by_crop(self):
        action = {'farmer': ['PLANT', 'CARROT'], 'hands': [['PLANT', 'WHEAT'], ['PLANT', 'WHEAT'], ['PLANT', 'WHEAT']]}
        _, actual = self.compare(action, setup=seed_fixture)
        obs = json.loads(actual.frames[1])['state'][0]['observation']
        self.assertEqual(obs['farms'][0]['tiles'][4][4]['crop'], 'CARROT')
        self.assertIsNone(obs['farms'][0]['tiles'][4][3])
        self.assertEqual(obs['private']['seeds']['WHEAT'], 2)

    def test_market_tail_is_ignored_by_engine_not_loader(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                action = {'market': [[] for _ in range(10)] + [['HIRE']]}
                report, _ = self.compare(action, seat=seat)
                self.assertEqual(report['bank'], [3000.0, 3000.0])
                self.assertEqual(report['raw_action_contract'][seat]['market_tail_rows'], 4)

    def test_market_padding_consumes_raw_slots(self):
        for pad in ([], ['PASS'], ['SELL', 'WHEAT', 0], None, 'HIRE'):
            with self.subTest(pad=pad):
                report, _ = self.compare({'market': [pad, ['HIRE']]}, config={'maxMarketOrdersPerTurn': 1})
                self.assertEqual(report['bank'], [3000.0, 3000.0])

    def test_executable_hire_not_lost(self):
        report, _ = self.compare({'market': [['HIRE'], [], ['BUY_LAND']]}, config={'maxMarketOrdersPerTurn': 1})
        self.assertEqual(report['bank'], [2993.0, 3000.0])

    def test_minimum_one_market_slot(self):
        # Interpreter-level robustness controls outside the hosted minimum=1 schema.
        for cap in (0, -4):
            with self.subTest(cap=cap):
                report, _ = self.compare({'market': [['HIRE'], ['BUY_LAND']]}, config={'maxMarketOrdersPerTurn': cap})
                self.assertEqual(report['bank'], [2993.0, 3000.0])
                self.assertEqual(report['raw_action_contract'][0]['market_tail_rows'], 4)

    def test_aliases_and_opaque_metadata_not_rewritten(self):
        row = ['PLANT', 'WHEAT']
        action = {'farmer': row, 'hands': [row, row], 'market': [[]], 'metadata': {'future': [1, 2]}}
        before = copy.deepcopy(action)
        self.compare(action, setup=seed_fixture)
        self.assertEqual(action, before)
        self.assertIs(action['farmer'], action['hands'][1])

    def test_nonobject_action_fails_consistently(self):
        for invalid in (None, [], 'PASS', 7):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(TypeError, 'action dict'):
                    CAND.play(RecordedEngine(), [fixed(invalid), fixed({})], 2, CONFIG)

    def test_numeric_engine_exception_not_swallowed(self):
        # Official PLANT/MARKET callbacks can reject bad argument conversion.
        action = {'farmer': ['PICKUP', 'WHEAT', 'not-a-number']}
        for driver in (CAND.play, direct_play):
            with self.subTest(driver=driver.__name__):
                with self.assertRaises(ValueError):
                    driver(RecordedEngine(), [fixed(action), fixed({})], 2, CONFIG)

    def test_malformed_market_quantity_is_engine_noop(self):
        self.compare({'market': [['SELL', 'WHEAT', 'not-a-number']]})

    def test_terminal_and_eod_full_transition(self):
        self.compare({'farmer': ['WEST'], 'hands': [['PASS']], 'market': [[], ['HIRE']]},
                     config={'episodeSteps': 50})

    def test_both_seats_raw_vector_matrix(self):
        variations = [
            {}, {'farmer': []}, {'hands': [[], ['WEST']]}, {'market': [[], ['HIRE']]},
            {'hands': [['PLANT', 'WHEAT']] * 4}, {'market': [['HIRE']] * 12},
            {'farmer': None, 'hands': 'WEST', 'market': False},
        ]
        for seat in (0, 1):
            for cap in (1, 3, 10):
                for action in variations:
                    with self.subTest(seat=seat, cap=cap, action=action):
                        self.compare(action, setup=seed_fixture, config={'maxMarketOrdersPerTurn': cap}, seat=seat)


def main():
    global BASE, CAND, ENGINE, SOURCE
    p = argparse.ArgumentParser(description=__doc__)
    lab = Path(__file__).resolve().parents[5]
    p.add_argument('--source', type=Path, default=lab/'reference/evaluator/loader.py')
    p.add_argument('--engine', type=Path, default=lab/'reference/engine')
    p.add_argument('--candidate', type=Path)
    p.add_argument('--report', type=Path)
    args = p.parse_args()
    SOURCE = args.source.read_bytes()
    if blob_hash(SOURCE) != SOURCE_BLOB:
        raise ValueError('Test fixture loader is not the pinned baseline')
    for name, expected in ENGINE_PINS.items():
        if blob_hash((args.engine/name).read_bytes()) != expected:
            raise ValueError(f'Engine mismatch: {name}')
    BASE = load_bytes('_raw_baseline', SOURCE, args.source)
    CAND = load_bytes('_raw_candidate', args.candidate.read_bytes() if args.candidate else repair_source(SOURCE),
                      args.candidate or args.source)
    ENGINE, _ = BASE.get_engine(args.engine)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
        unittest.defaultTestLoader.loadTestsFromTestCase(SourceContract),
        unittest.defaultTestLoader.loadTestsFromTestCase(EngineContract),
    ]))
    report = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'skipped': len(result.skipped), 'official_interpreter_calls': TRANSITIONS,
              'optimization': sys.flags.optimize, 'passed': result.wasSuccessful(),
              'failed_tests': [str(t) for t, _ in result.failures],
              'error_tests': [str(t) for t, _ in result.errors]}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
