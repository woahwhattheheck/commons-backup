# SPDX-License-Identifier: Apache-2.0
"""Native delivery regressions over the recovered, unchanged HAZEL source.

These are binding/export cases, not an economic panel or natural step226 states.
The short constructed observations come from official-engine initialization.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import build as builder
import capital_routes as capital
import entry

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ENGINE_DIR = Path(os.environ.get('OSPREY_ENGINE_DIR', ''))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def observation(seat=0, step=0):
    ev = load(BASE / 'cloud-eval/evaluate.py', '_capital_test_evaluator')
    engine, _ = ev.get_engine(ENGINE_DIR)
    cfg = ev.Struct({key: value.get('default') if isinstance(value, dict) else value
                     for key, value in engine.specification['configuration'].items()})
    # A deterministic initialization fixture, not a reserved or scored game.
    cfg.seed = 0
    env = ev.Struct(configuration=cfg, done=False, info={})
    state = [ev.Struct(observation=ev.Struct(), action={}, status='ACTIVE', reward=0)
             for _ in range(2)]
    engine.interpreter(state, env)
    assert cfg.seed is None
    obs = copy.deepcopy(state[seat].observation)
    obs['step'], obs['day'], obs['hour'] = step, step // 24, step % 24
    obs['remainingOverageTime'] = 0
    return obs, dict(cfg)


class NativeDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ENGINE_DIR / 'kaggriculture.py').exists():
            raise unittest.SkipTest('Set OSPREY_ENGINE_DIR to the existing pinned engine cache')
        cls.temp = tempfile.TemporaryDirectory(prefix='capital-delivery-tests-')
        cls.root = Path(cls.temp.name)
        cls.receipt = builder.build(cls.root / 'export')
        cls.payload = cls.root / 'export/extracted'
        cls.native = load(BASE / 'cloud-pack/official.py', '_capital_native_contract')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_original_source_blobs_preserved(self):
        for name, expected in builder.SOURCE_BLOBS.items():
            raw = (HERE / name).read_bytes()
            self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(), expected)
            self.assertEqual(raw, (self.payload / 'policy' / name).read_bytes())

    def test_existing_raw_entry_needs_module_filename(self):
        obs, cfg = observation()
        with self.assertRaisesRegex(Exception, '__file__'):
            self.native.make_agent(HERE / 'entry.py')(obs, cfg)

    def test_new_main_in_empty_globals(self):
        obs, cfg = observation()
        space = {}
        exec(compile((HERE / 'main.py').read_bytes(), 'main.py', 'exec'), space)
        self.assertNotIn('__file__', space)
        cfg['__raw_path__'] = str(HERE / 'main.py')
        actual = space['agent'](obs, cfg)
        self.assertEqual(actual, entry.make_agent().act(obs, cfg))

    def test_no_path_is_an_explicit_loader_error(self):
        space = {}
        exec(compile((HERE / 'main.py').read_bytes(), 'main.py', 'exec'), space)
        with self.assertRaisesRegex(ValueError, '__raw_path__'):
            space['agent']({}, {})

    def test_actual_native_loader_source_and_export_both_seats(self):
        for seat in (0, 1):
            for step in (0, 226):
                with self.subTest(seat=seat, step=step):
                    obs, cfg = observation(seat, step)
                    reference = entry.make_agent().act(copy.deepcopy(obs), copy.deepcopy(cfg))
                    self.assertEqual(self.native.make_agent(HERE/'main.py')(obs, cfg), reference)
                    self.assertEqual(self.native.make_agent(self.payload/'main.py')(obs, cfg), reference)

    def test_one_authoritative_parent_at_selection(self):
        obs, cfg = observation(step=226)
        agent = entry.make_agent()
        with patch.object(agent.scheduler.controller, 'act', wraps=agent.scheduler.controller.act) as counted:
            result = agent.act(obs, cfg)
        self.assertEqual(counted.call_count, 1)
        self.assertIsInstance(result, dict)

    def test_custom_selector_retains_complete_route_and_no_parent_call(self):
        obs, cfg = observation(step=226)
        parent = entry.make_agent().scheduler.controller
        before = copy.deepcopy(parent.R)
        offered = []
        def choose(offers, observation):
            offered.extend(offers)
            return capital.SHEEP
        with patch.object(parent, 'act', wraps=parent.act) as counted:
            report = capital.choose_before_action(parent, obs, cfg, entry.scheduler.m, choose)
        self.assertEqual(counted.call_count, 0)
        self.assertEqual(parent.cur, capital.SHEEP)
        self.assertTrue(report['changed'])
        self.assertEqual(parent.R, before)
        self.assertEqual([v.route_id for v in offered], [capital.MAIN, capital.SHEEP])
        self.assertTrue(all(v.orders for v in offered))

    def test_missing_selector_choice_retains_incumbent(self):
        obs, cfg = observation(step=226)
        parent = entry.make_agent().scheduler.controller
        result = capital.choose_before_action(parent, obs, cfg, entry.scheduler.m,
                                               lambda offers, observation: 'unknown')
        self.assertEqual(parent.cur, capital.MAIN)
        self.assertEqual(result['reason'], 'no_offered_choice')

    def test_unsupported_quote_retains_incumbent(self):
        obs, cfg = observation(step=226)
        obs['market']['prices'].pop('WOOL')
        parent = entry.make_agent().scheduler.controller
        result = capital.choose_before_action(parent, obs, cfg, entry.scheduler.m)
        self.assertEqual(parent.cur, capital.MAIN)
        self.assertEqual(result['reason'], 'unpriced_program')

    def test_outside_checkpoint_does_not_touch_evaluator(self):
        obs, cfg = observation(step=225)
        parent = entry.make_agent().scheduler.controller
        def no_call(*args):
            raise AssertionError('Selector should not run here')
        result = capital.choose_before_action(parent, obs, cfg, entry.scheduler.m, no_call)
        self.assertEqual(result['reason'], 'outside_checkpoint')
        self.assertEqual(parent.cur, capital.MAIN)

    def test_inputs_and_route_tables_preserved_by_full_binding(self):
        obs, cfg = observation(step=226)
        agent = entry.make_agent()
        before = copy.deepcopy((obs, cfg, agent.scheduler.controller.R))
        agent.act(obs, cfg)
        self.assertEqual((obs, cfg, agent.scheduler.controller.R), before)

    def test_builder_preserves_existing_output(self):
        marker = self.root/'preserved'
        marker.mkdir()
        (marker/'keep.txt').write_text('keep')
        with self.assertRaises(FileExistsError):
            builder.build(marker)
        self.assertEqual((marker/'keep.txt').read_text(), 'keep')

    def test_build_is_byte_reproducible(self):
        repeated = builder.build(self.root/'repeat')
        self.assertEqual(repeated['archive_sha256'], self.receipt['archive_sha256'])

    def test_runtime_tree_has_licenses_and_original_dependency(self):
        for p in ['LICENSE', 'NOTICE', 'cloud-titan-composition/vendor/sell/LICENSE',
                  'cloud-titan-composition/vendor/sell/NOTICE']:
            self.assertTrue((self.payload/p).is_file(), p)
        self.assertEqual(builder.sha256(self.payload/'cloud-titan-composition/vendor/sell/scheduler.py'),
                         builder.SELL_SHA256)

    def test_new_game_resets_original_instance(self):
        obs, cfg = observation()
        namespace = {}
        exec(compile((HERE/'main.py').read_bytes(), 'main.py', 'exec'), namespace)
        cfg['__raw_path__'] = str(HERE/'main.py')
        namespace['agent'](obs,cfg)
        first = namespace['_module']._INSTANCE
        namespace['agent'](obs,cfg)
        self.assertIsNot(namespace['_module']._INSTANCE, first)

    def test_export_runs_in_fresh_process_without_kaggle_package(self):
        runner = '''import importlib.abc, importlib.util, json, sys
from pathlib import Path
class BlockKaggle(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname == 'kaggle_environments' or fullname.startswith('kaggle_environments.'):
   raise ImportError('Runtime must not import evaluator package')
sys.meta_path.insert(0, BlockKaggle())
payload=Path(sys.argv[1]); loader=Path(sys.argv[2]); inputs=json.loads(sys.stdin.read())
s=importlib.util.spec_from_file_location('native_contract',loader)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
a=m.make_agent(payload/'main.py')(inputs['observation'],inputs['configuration'])
paths={name: str(Path(getattr(mod,'__file__','')).resolve()) for name,mod in sys.modules.items()
       if name in ('capital_routes','scheduler','mechanics','_capital_bundle_entry')}
print(json.dumps({'action':a,'paths':paths},sort_keys=True))
'''
        for seat in (0,1):
            obs,cfg=observation(seat,226)
            result=subprocess.run([sys.executable,'-B','-c',runner,str(self.payload),
                str(BASE/'cloud-pack/official.py')],input=json.dumps({'observation':obs,'configuration':cfg}),
                cwd=self.root,text=True,capture_output=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            output=json.loads(result.stdout)
            self.assertEqual(output['action'],entry.make_agent().act(obs,cfg))
            self.assertEqual(len(output['paths']),4)
            for path in output['paths'].values():
                self.assertTrue(Path(path).is_relative_to(self.payload),path)


if __name__ == '__main__':
    unittest.main()
