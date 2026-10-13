# SPDX-License-Identifier: Apache-2.0
"""Real current consumer + pinned engine; full current runtime lifecycle tests.

TITAN_PACKAGE_ROOT supplies the complete retained dependency package.
TITAN_RUNTIME_SOURCE supplies exact b952 source (not necessarily its package).
No missing-dependency skip and no full-game/strength assertion.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import os
import json
import subprocess
import tempfile
from pathlib import Path
import sys
import time
import types
import unittest
from unittest.mock import patch

from repair_return_lifecycle import (git_blob, repair, repair_integrated,
                                     repair_runtime, RUNTIME_BLOB, INTEGRATED_BLOB)

ROOT = Path(os.environ['TITAN_PACKAGE_ROOT']).resolve()
RUNTIME = Path(os.environ['TITAN_RUNTIME_SOURCE']).resolve()
ENGINE_BLOB = '3c202c7ee921da239356789e266b694635103fc4'
sys.path[:0] = [str(ROOT), str(ROOT/'checks')]
import test_ordered_selected_sell as selected_tests
action = selected_tests.action


def module_from(data, name, filename):
    module = types.ModuleType(name)
    module.__file__ = str(filename)
    sys.modules[name] = module
    exec(compile(data, str(filename), 'exec'), module.__dict__)
    return module


class CurrentInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_i = (ROOT/'integrated_selected.py').read_bytes()
        cls.original_r = RUNTIME.read_bytes()
        if git_blob(cls.original_i) != INTEGRATED_BLOB:
            raise ValueError('not the current IntegratedSelectedAgent preimage')
        if git_blob(cls.original_r) != RUNTIME_BLOB:
            raise ValueError('not the current TitanAgent preimage')
        engine = ROOT/'checks/reference/engine/kaggriculture.py'
        if git_blob(engine.read_bytes()) != ENGINE_BLOB:
            raise ValueError('wrong full official interpreter')
        cls.candidate_i = repair_integrated(cls.original_i)
        cls.candidate_r = repair_runtime(cls.original_r)
        cls.legacy = module_from(cls.original_i, '_rl_legacy_i', ROOT/'integrated_selected.py')
        cls.fixed = module_from(cls.candidate_i, '_rl_fixed_i', ROOT/'integrated_selected.py')
        cls.legacy_r = module_from(cls.original_r, '_rl_legacy_r', ROOT/'titan_runtime.py')
        cls.fixed_r = module_from(cls.candidate_r, '_rl_fixed_r', ROOT/'titan_runtime.py')
        selected_tests.OrderedSelectedSellTests.setUpClass()
        cls.h = selected_tests.OrderedSelectedSellTests()

    def fixture(self, seat=0, step=100, stock=2, carried=3):
        _, cfg, state, env = self.h.fixture(step)
        obs = state[seat].observation
        farm = obs['farms'][seat]
        positions = self.h.engine._shed_access_tiles(10)
        farm['farmer'] = list(positions[0])
        farm['hands'] = [list(positions[1])]
        obs['private']['shed'] = {'MILK': stock}
        obs['private']['inventories'] = [{'MILK': carried}, {}]
        return obs, cfg, state, env

    def consumer(self, module=None, seed=False):
        mod = self.fixed if module is None else module
        obj = mod.IntegratedSelectedAgent(seed=seed, committed=False, horizon=1)
        obj.controller.R = {'case': [action(hands=[['PASS']]) for _ in range(720)]}
        obj.controller.cur = 'case'
        obj.production.plans = {}
        return obj

    def advance(self, state, env, seat, returned):
        for row in state:
            row.action = action()
        state[seat].action = deepcopy(returned)
        self.h.engine.interpreter(state, env)

    def bound_agent(self, module, obs, consumer, selected):
        obj = module.TitanAgent(module.Features(consumer='ordered', seed=False, funding=False))
        obj.consumer = consumer
        obj.selected = deepcopy(selected)
        return obj


class ConsumerLifecycle(CurrentInputs):
    def test_predecessor_retains_packet_after_new_call_fails(self):
        for mod, retains in ((self.legacy, True), (self.fixed, False)):
            obj = self.consumer(mod)
            obs, cfg, _, _ = self.fixture()
            obj.transform(obs, cfg, action(['DROP'], [['PASS']]))
            self.assertIsNotNone(obj.last_packet)
            obj.production.one_way = False
            later = deepcopy(obs); later['step'] += 1
            obj.transform(later, cfg, action(hands=[['PASS']]))
            self.assertEqual(obj.last_packet is not None, retains)

    def test_invalidation_precedes_normalization_exception(self):
        obj = self.consumer(); obj.last_packet = {'old': True}
        obj.last_selected = obj.last_seeded = {'old': True}
        with self.assertRaises((TypeError, ValueError)):
            obj.transform(None, {}, action())
        self.assertIsNone(obj.last_packet)
        self.assertIsNone(obj.last_selected)
        self.assertIsNone(obj.last_seeded)

    def test_no_sell_control_does_not_reuse_packet(self):
        obj = self.consumer(); obs, cfg, _, _ = self.fixture()
        selected = action(['DROP'], [['PASS']])
        obj.transform(obs, cfg, selected); self.assertIsNotNone(obj.last_packet)
        obj.sell = False
        self.assertEqual(obj.transform(obs, cfg, selected), selected)
        self.assertIsNone(obj.last_packet)

    def test_real_seller_fallback_real_engine_discriminator_both_seats(self):
        for seat in (0, 1):
            for mod, old in ((self.legacy, True), (self.fixed, False)):
                obj = self.consumer(mod)
                obs, cfg, state, env = self.fixture(seat)
                selected = action(['DROP'], [['PASS']])
                fallback = action(hands=[['PASS']])
                out = obj.transform(obs, cfg, selected, fallback_action=fallback,
                    reservations={'cash': [{'step': 100, 'phase': 'after_market',
                                            'minimum': 1000000000}]})
                self.assertEqual(out, fallback)
                self.advance(state, env, seat, out)
                self.assertEqual(state[seat].observation['private']['shed']['MILK'], 2)
                self.assertEqual(state[seat].observation['private']['inventories'][0]['MILK'], 3)
                if old:
                    self.assertEqual(obj.last_packet['post_unit_observation']['private']['shed']['MILK'], 5)
                else:
                    self.assertIsNone(obj.last_packet)

    def test_good_snapshot_matches_full_engine_matrix(self):
        # 2 seats x 4 incoming stocks x 4 unit operations = 32 complete callbacks.
        count = 0
        for seat in (0, 1):
            for stock in (0, 2, 50, 99):
                for row in (['PASS'], ['DROP'], ['PICKUP', 'MILK', 1], ['NORTH']):
                    obj = self.consumer(); obs, cfg, state, env = self.fixture(seat, stock=stock)
                    selected = action(row, [['PASS']])
                    saved = deepcopy((obs, cfg, selected))
                    out = obj.transform(obs, cfg, selected)
                    packet = obj.last_packet
                    self.assertIsNotNone(packet)
                    self.assertEqual(packet['selected_post_units_binding'],
                                     (100, seat, selected['farmer'], selected['hands']))
                    self.assertEqual((obs, cfg, selected), saved)
                    self.advance(state, env, seat, out)
                    actual = state[seat].observation
                    self.assertEqual(packet['post_unit_observation']['private'], actual['private'])
                    self.assertEqual(packet['post_unit_observation']['farms'][seat]['farmer'],
                                     actual['farms'][seat]['farmer'])
                    count += 1
        self.assertEqual(count, 32)

    def test_market_only_fallback_keeps_snapshot_and_raw_slots(self):
        for tail in ([], [None], [['HIRE']], [['SELL', 'MILK', 9]]):
            obj = self.consumer(); obs, cfg, _, _ = self.fixture()
            selected = action(['DROP'], [['PASS']], [[], ['SELL', 'MILK', 1]])
            fallback = action(['DROP'], [['PASS']], [[]] * 10 + tail)
            out = obj.transform(obs, cfg, selected, fallback_action=fallback,
                reservations={'cash': [{'step': 100, 'phase': 'after_market',
                                        'minimum': 1000000000}]})
            self.assertEqual(out, fallback)
            self.assertIsNotNone(obj.last_packet)
            rt = self.bound_agent(self.fixed_r, obs, obj, selected)
            self.assertIs(rt._selected_snapshot(obs, out), obj.last_packet['post_unit_observation'])

    def test_binding_is_deeply_detached(self):
        obj = self.consumer(); obs, cfg, _, _ = self.fixture()
        selected = action(['DROP'], [['PASS']])
        obj.transform(obs, cfg, selected)
        selected['farmer'][0] = 'PASS'; selected['hands'][0][0] = 'NORTH'
        self.assertEqual(obj.last_packet['selected_post_units_binding'],
                         (100, 0, ['DROP'], [['PASS']]))

    def test_exception_fallback_with_other_units_discards_current_packet(self):
        obj = self.consumer(); obs, cfg, _, _ = self.fixture()
        with patch.object(obj.execution.seller, 'transform', side_effect=ValueError('late failure')):
            out = obj.transform(obs, cfg, action(['DROP'], [['PASS']]),
                                fallback_action=action(hands=[['PASS']]))
        self.assertEqual(out['farmer'], ['PASS'])
        self.assertIsNone(obj.last_packet)

    def test_exception_same_units_preserves_valid_current_snapshot(self):
        obj = self.consumer(); obs, cfg, _, _ = self.fixture()
        selected = action(['DROP'], [['PASS']])
        with patch.object(obj.execution.seller, 'transform', side_effect=ValueError('late failure')):
            self.assertEqual(obj.transform(obs, cfg, selected), selected)
        self.assertEqual(obj.last_packet['post_unit_observation']['private']['shed']['MILK'], 5)

    def test_seed_only_callback_cannot_rewrite_units(self):
        obj = self.consumer(seed=True); obs, cfg, _, _ = self.fixture()
        selected = action(['DROP'], [['PASS']], [['BUY_SEED', 'WHEAT', 10], ['HIRE']])
        proposed = deepcopy(selected); proposed['market'][0][2] = 1
        obj.budget.apply = lambda *a, **k: deepcopy(proposed)
        obj.seed_queue_selector = lambda *a: (action(['PASS'], [['PASS']], proposed['market']),
                                              {'status': 'certified'})
        out = obj.transform(obs, cfg, selected)
        self.assertEqual(out, selected)
        self.assertIsNone(obj.last_packet)
        self.assertIn('changed selected unit rows', obj.diagnostics['reason'])

    def test_deadline_after_packet_preserves_exact_selected_binding(self):
        obj = self.consumer(); obs, cfg, _, _ = self.fixture()
        selected = action(['DROP'], [['PASS']])
        error = self.fixed_r.deadline.DeadlineExceeded('test cancellation')
        with patch.object(obj.execution.seller, 'transform', side_effect=error):
            with self.assertRaises(type(error)):
                obj.transform(obs, cfg, selected)
        rt = self.bound_agent(self.fixed_r, obs, obj, selected)
        self.assertIsNotNone(rt._selected_snapshot(obs, selected))
        self.assertIsNone(rt._selected_snapshot(obs, action(hands=[['PASS']])))


class SnapshotConsumers(CurrentInputs):
    def test_ordered_rejects_changed_step_seat_or_units(self):
        obj = self.consumer(); obs, cfg, _, _ = self.fixture()
        selected = action(['DROP'], [['PASS']]); obj.transform(obs, cfg, selected)
        rt = self.bound_agent(self.fixed_r, obs, obj, selected)
        for what in ('step', 'seat', 'farmer', 'hands', 'post_step', 'missing_binding'):
            test_obs = deepcopy(obs); returned = deepcopy(selected); packet = deepcopy(obj.last_packet)
            if what == 'step': test_obs['step'] += 1
            elif what == 'seat': test_obs['player'] = 1
            elif what == 'farmer': returned['farmer'] = ['PASS']
            elif what == 'hands': returned['hands'][0] = ['NORTH']
            elif what == 'post_step': packet['post_unit_observation']['step'] += 1
            else: packet.pop('selected_post_units_binding')
            with patch.object(obj, 'last_packet', packet):
                self.assertIsNone(rt._selected_snapshot(test_obs, returned), what)

    def test_ordered_predecessor_accepts_wrong_returned_units(self):
        obj = self.consumer(); obs, cfg, _, _ = self.fixture()
        selected = action(['DROP'], [['PASS']]); obj.transform(obs, cfg, selected)
        old = self.bound_agent(self.legacy_r, obs, obj, selected)
        new = self.bound_agent(self.fixed_r, obs, obj, selected)
        fallback = action(hands=[['PASS']])
        self.assertIsNotNone(old._selected_snapshot(obs, fallback))
        self.assertIsNone(new._selected_snapshot(obs, fallback))

    def test_default_snapshot_argument_binds_completed_selected_action(self):
        obj = self.consumer(); obs, cfg, _, _ = self.fixture()
        selected = action(['DROP'], [['PASS']]); obj.transform(obs, cfg, selected)
        rt = self.bound_agent(self.fixed_r, obs, obj, selected)
        self.assertIsNotNone(rt._selected_snapshot(obs))
        rt.selected = None
        self.assertIsNone(rt._selected_snapshot(obs))

    def test_missing_or_malformed_ordered_packets_do_not_certify(self):
        obs, _, _, _ = self.fixture()
        obj = types.SimpleNamespace(last_packet=None)
        rt = self.bound_agent(self.fixed_r, obs, obj, action())
        for packet in (None, [], {}, {'selected_post_units_binding': (100, 0)},
                       {'selected_post_units_binding': (100, 0, ['PASS'], []),
                        'post_unit_observation': []}):
            obj.last_packet = packet
            self.assertIsNone(rt._selected_snapshot(obs, action()))

    def test_frozen_snapshot_behavior_is_unchanged(self):
        obs, _, _, _ = self.fixture()
        selected = action(['DROP'], [['PASS']])
        post = deepcopy(obs); post['private']['shed']['MILK'] = 5
        c = types.SimpleNamespace(selected_post_units=(post['farms'][0], post['private']),
            selected_post_units_binding=(100, 0, selected['farmer'], selected['hands']))
        for returned in (None, selected, action(hands=[['PASS']]),
                         action(['DROP'], [['PASS']], [['HIRE']])):
            outputs = []
            for mod in (self.legacy_r, self.fixed_r):
                a = mod.TitanAgent(mod.Features(seed=False, funding=False)); a.consumer = c
                outputs.append(a._selected_snapshot(obs, returned))
            self.assertEqual(*outputs)

    def test_frozen_no_snapshot_pass_identity_is_unchanged(self):
        obs, _, _, _ = self.fixture()
        for mod in (self.legacy_r, self.fixed_r):
            a = mod.TitanAgent(mod.Features()); a.consumer = types.SimpleNamespace()
            self.assertIs(a._selected_snapshot(obs, action(hands=[['PASS']])), obs)


class RuntimeLifecycle(CurrentInputs):
    def timer(self, module):
        class Timer:
            expired = module.deadline.DeadlineExceeded('deterministic lifecycle cut')
            def __init__(self, seconds): pass
            def __enter__(self): return self
            def __exit__(self, *args): return False
        return Timer

    def test_coldstart_cancellation_skips_uninitialized_finalizer(self):
        for seat in (0, 1):
            obs, cfg, _, _ = self.fixture(seat)
            for mod, fixed in ((self.legacy_r, False), (self.fixed_r, True)):
                a = mod.TitanAgent(mod.Features(early_capital=True))
                timer = self.timer(mod)
                a._initialize = lambda: (_ for _ in ()).throw(timer.expired)
                a._finish_production = lambda *x: (_ for _ in ()).throw(AssertionError('uninitialized'))
                with patch.object(mod.deadline, '_DeadlineTimer', timer):
                    if fixed:
                        out = a.act(obs, cfg)
                        self.assertEqual(out, mod.deadline.legal_pass(obs))
                        self.assertFalse(a.ready)
                    else:
                        with self.assertRaisesRegex(AssertionError, 'uninitialized'):
                            a.act(obs, cfg)

    def test_ready_bypass_timeout_still_finalizes(self):
        obs, cfg, _, _ = self.fixture()
        a = self.fixed_r.TitanAgent(self.fixed_r.Features(consumer='ordered', seed=False, funding=False))
        a.ready = True; a.consumer = types.SimpleNamespace(last_packet=None)
        timer = self.timer(self.fixed_r)
        a.production = types.SimpleNamespace(act=lambda obs: (_ for _ in ()).throw(timer.expired))
        calls = []
        a._finish_production = lambda obs, out, cfg: (calls.append('finish') or out)
        with patch.object(self.fixed_r.deadline, '_DeadlineTimer', timer):
            a.act(obs, cfg)
        self.assertEqual(calls, ['finish'])
        self.assertFalse(a.ready)

    def test_successful_initialization_then_timeout_still_finalizes(self):
        obs, cfg, _, _ = self.fixture()
        a = self.fixed_r.TitanAgent(self.fixed_r.Features(consumer='ordered', seed=False, funding=False))
        timer = self.timer(self.fixed_r)
        def initialize():
            a.consumer = types.SimpleNamespace(last_packet=None)
            a.production = types.SimpleNamespace(act=lambda obs: (_ for _ in ()).throw(timer.expired))
            a.ready = True
        a._initialize = initialize
        calls = []; a._finish_production = lambda obs, out, cfg: (calls.append(1) or out)
        with patch.object(self.fixed_r.deadline, '_DeadlineTimer', timer): a.act(obs, cfg)
        self.assertEqual(calls, [1])

    def test_ordered_packet_is_cleared_before_history_and_entry_prelude(self):
        obs, cfg, _, _ = self.fixture()
        a = self.fixed_r.TitanAgent(self.fixed_r.Features(consumer='ordered', seed=False, funding=False))
        a.ready = True; a.consumer = types.SimpleNamespace(last_packet={'prior': True})
        a.act(obs, cfg, entry_started=time.perf_counter()-2)
        self.assertIsNone(a.consumer.last_packet)
        a.consumer.last_packet = {'prior': True}
        timer = self.timer(self.fixed_r)
        def observe(obs):
            self.assertIsNone(a.consumer.last_packet)
            raise timer.expired
        a.history = types.SimpleNamespace(observe=observe)
        a._finish_production = lambda obs, out, cfg: out
        with patch.object(self.fixed_r.deadline, '_DeadlineTimer', timer): a.act(obs, cfg)
        self.assertIsNone(a.history)

    def test_foreign_deadline_is_not_swallowed(self):
        obs, cfg, _, _ = self.fixture()
        a = self.fixed_r.TitanAgent(self.fixed_r.Features())
        error = self.fixed_r.deadline.DeadlineExceeded('foreign')
        a._initialize = lambda: (_ for _ in ()).throw(error)
        with self.assertRaises(type(error)) as caught: a.act(obs, cfg)
        self.assertIs(caught.exception, error)

    def test_history_sees_final_selected_transform_units(self):
        for mod, fixed in ((self.legacy_r, False), (self.fixed_r, True)):
            obs, cfg, _, _ = self.fixture()
            a = mod.TitanAgent(mod.Features(seed=False, funding=False))
            a.ready = True
            selected = action(['DROP'], [['PASS']]); returned = action(hands=[['PASS']])
            a.production = types.SimpleNamespace(act=lambda obs: deepcopy(selected))
            a.controller = types.SimpleNamespace(cur='case')
            a.consumer = types.SimpleNamespace(planned={}, pending={}, previous=None, observed_harvests={})
            def transform(obs, cfg, chosen):
                post = deepcopy(obs); post['private']['shed']['MILK'] = 5
                a.consumer.selected_post_units = (post['farms'][0], post['private'])
                a.consumer.selected_post_units_binding = (100, 0, selected['farmer'], selected['hands'])
                return deepcopy(returned)
            a.transform_selected = transform
            seen = []
            a.history = types.SimpleNamespace(observe=lambda obs: None, diagnostics={},
                transform=lambda obs, cfg, out, post, **k: (seen.append(post) or out),
                remember=lambda *args: None)
            self.assertEqual(a.act(obs, cfg), returned)
            self.assertEqual(seen[0] is None, fixed)


class SourceContracts(CurrentInputs):
    def test_whole_file_pins_reject_drift(self):
        for function, source in ((repair_runtime, self.original_r),
                                 (repair_integrated, self.original_i)):
            for drift in (b'', source+b'\n', source.replace(b'from copy import deepcopy', b'from copy import copy')):
                with self.assertRaises(ValueError): function(drift)

    def test_two_source_bundle_matches_individual_repairs(self):
        out = repair(self.original_r, self.original_i)
        self.assertEqual(out, {'titan_runtime.py': self.candidate_r,
                              'integrated_selected.py': self.candidate_i})
        with self.assertRaises(ValueError): repair(self.original_r, b'bad')

    def test_feature_defaults_and_unrelated_runtime_methods_unchanged(self):
        old, new = ast.parse(self.original_r), ast.parse(self.candidate_r)
        def definitions(tree):
            return {n.name: ast.dump(n, include_attributes=False) for n in tree.body
                    if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
        self.assertEqual(definitions(old)['Features'], definitions(new)['Features'])
        classes = [next(n for n in t.body if isinstance(n, ast.ClassDef) and n.name=='TitanAgent')
                   for t in (old, new)]
        methods = [{n.name: ast.dump(n, include_attributes=False) for n in c.body
                    if isinstance(n, ast.FunctionDef)} for c in classes]
        self.assertEqual({k for k in methods[0] if methods[0][k] != methods[1][k]},
                         {'act', '_selected_snapshot'})

    def test_repair_is_not_silently_reapplied(self):
        with self.assertRaises(ValueError): repair_runtime(self.candidate_r)
        with self.assertRaises(ValueError): repair_integrated(self.candidate_i)



class StagingCLI(CurrentInputs):
    def run_cli(self, runtime, integrated, output):
        command = [sys.executable]
        if not __debug__: command.append('-O')
        command += [str(Path(__file__).with_name('repair_return_lifecycle.py')),
                    '--runtime', str(runtime), '--integrated', str(integrated),
                    '--output-dir', str(output)]
        return subprocess.run(command, capture_output=True, text=True, timeout=10)

    def stage_inputs(self, root):
        r = root/'r.py'; i = root/'i.py'
        r.write_bytes(self.original_r); i.write_bytes(self.original_i)
        return r, i

    def test_cli_positive_receipt_and_input_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); r, i = self.stage_inputs(root); out = root/'stage'
            result = self.run_cli(r, i, out)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads((out/'SOURCE-REPAIR.json').read_text())
            self.assertEqual((out/'titan_runtime.py').read_bytes(), self.candidate_r)
            self.assertEqual((out/'integrated_selected.py').read_bytes(), self.candidate_i)
            self.assertEqual(receipt['sources']['titan_runtime.py']['output_blob'],
                             git_blob(self.candidate_r))
            self.assertEqual(r.read_bytes(), self.original_r)
            self.assertEqual(i.read_bytes(), self.original_i)

    def test_cli_never_overwrites_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); r, i = self.stage_inputs(root); out = root/'stage'
            out.mkdir(); sentinel = out/'titan_runtime.py'; sentinel.write_bytes(b'peer')
            result = self.run_cli(r, i, out)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(sentinel.read_bytes(), b'peer')
            self.assertEqual(sorted(x.name for x in out.iterdir()), ['titan_runtime.py'])

    def test_cli_bad_second_pin_does_not_create_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); r, i = self.stage_inputs(root); out = root/'stage'
            i.write_bytes(self.original_i+b'\n')
            result = self.run_cli(r, i, out)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(out.exists())
            self.assertEqual(r.read_bytes(), self.original_r)

    def test_cli_symlink_input_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); r, i = self.stage_inputs(root); out = root/'stage'
            alias = root/'alias.py'; alias.symlink_to(r)
            result = self.run_cli(alias, i, out)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(out.exists())

    def test_cli_symlink_output_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); r, i = self.stage_inputs(root); protected = root/'protected'
            protected.mkdir(); (protected/'sentinel').write_bytes(b'peer')
            out = root/'stage'; out.symlink_to(protected, target_is_directory=True)
            result = self.run_cli(r, i, out)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(sorted(x.name for x in protected.iterdir()), ['sentinel'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
