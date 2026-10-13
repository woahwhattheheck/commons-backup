"""Real cell/worker IPC fixtures for existing LARK consumption; no games."""
import argparse
import contextlib
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_league as driver

HERE = Path(__file__).resolve().parent
LARK = HERE.parent / 'cloud-opponent-league/lark-responsive'
PATHS = {name: str(LARK / (name + '.py'))
         for name in ('sell_priority', 'pressure_priority')}
ACTION = {'farmer': ['PASS'], 'hands': [],
          'market': [['SELL', 'WHEAT', 2], ['SELL', 'WOOL', 2],
                     ['SELL', 'MILK', 2], ['HIRE']]}
OBS = {'player': 0, 'farms': [], 'market': {
    'inventory': {'WHEAT': 0, 'WOOL': 0, 'MILK': 0},
    'prices': {'WHEAT': 40, 'WOOL': 100, 'MILK': 20}}}


class LarkConsumptionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.function = self.root / 'fixture.py'
        self.function.write_text('def agent(observation, configuration):\n'
                                 '    return ' + repr(ACTION) + '\n')

    def evaluator(self):
        path = HERE.parent / 'cloud-eval/evaluate.py'
        spec = importlib.util.spec_from_file_location('lark_ipc_fixture_evaluator', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def run_cell(self, label, suffix='', enabled=True, quote=None, pressure_clock=None):
        ev = self.evaluator()
        children = []
        quote_calls = []

        def price(item, inventory, params=None):
            quote_calls.append((item, inventory, params))
            return {'WHEAT': 40, 'WOOL': 100, 'MILK': max(1, 20-3*inventory)}[item]

        class Engine:
            specification = {}
            market_price = staticmethod(quote or price)

            def interpreter(self, state, env):
                return state

        def play(engine, specs, cache, loader, seed, seat, rng, timeout, startup, *args):
            if pressure_clock is not None:
                # Replace only this wrapper module's clock; real child IPC and
                # the evaluator's clock/deadline remain intact.
                ev.Actor.act.__globals__['time'] = SimpleNamespace(perf_counter=pressure_clock)
            responses = []
            actors = []
            try:
                for value in specs:
                    actor = ev.Actor(value, cache, loader, rng, startup)
                    actors.append(actor)
                    children.append(actor.proc)
                    self.assertEqual(actor.ready['kind'], 'ready')
                    responses.append(actor.act(OBS, {'maxMarketOrdersPerTurn': 10}, timeout))
                state = [ev.Struct(observation=OBS, action=r.get('action', {}))
                         for r in responses]
                engine.interpreter(state, None)
            finally:
                for actor in actors:
                    actor.close()
            failed = next((r for r in responses if r['kind'] != 'action'), None)
            return {'seed': seed, 'candidate_seat': seat,
                    'status': 'failed' if failed else 'complete',
                    'scores': None if failed else [1, 0], 'failure': failed,
                    'wall_seconds': 0.0, 'actors': [a.report() for a in actors],
                    'responses': responses}

        ev.get_engine = lambda *args: (Engine(), {'fixture': 'synthetic'})
        ev.play = play
        cfg = {'candidate': str(self.function) + '::agent',
               'opponents': {'fixture': str(self.function) + '::agent' + suffix},
               'cells': [{'id': label, 'seed': 123, 'seat': 0, 'opponent': 'fixture'}],
               'output': str(self.root / 'output'), 'engine': 'unused', 'loader': 'unused',
               'rng_seed': 123, 'action_timeout': 5.0,
               'startup_timeout': 5.0, 'game_timeout': 10.0}
        if enabled:
            cfg['lark_wrappers'] = PATHS
        config = self.root / (label + '.json')
        config.write_text(json.dumps(cfg))
        args = argparse.Namespace(config=str(config), cell=label)
        with patch.object(driver, 'load_evaluator', return_value=ev):
            with contextlib.redirect_stdout(io.StringIO()):
                code = driver.cell(args)
        self.assertTrue(all(p.returncode is not None for p in children))
        folder = Path(cfg['output']) / label
        result = json.loads((folder / 'result.json').read_text())
        data = (folder / 'trajectory.jsonl.gz').read_bytes()
        self.assertEqual(result['trajectory_sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(len(gzip.decompress(data).splitlines()), 1)
        self.assertEqual(result['recorded_transitions'], 1)
        return code, result, quote_calls

    def test_default_cell_never_loads_wrappers_and_retains_detailed_samples(self):
        with patch.object(driver, 'lark_actor', side_effect=AssertionError('unexpected hook')):
            code, result, calls = self.run_cell('default', enabled=False)
        self.assertEqual(code, 0)
        self.assertEqual(calls, [])
        for response, actor in zip(result['responses'], result['actors']):
            self.assertEqual(response['action'], ACTION)
            self.assertEqual(len(actor['call_seconds']), 1)
            self.assertEqual(len(actor['rpc_seconds']), 1)
            self.assertNotIn('pressure_priority_enabled', actor)
            self.assertNotIn('sell_priority_enabled', actor)

    def test_cell_consumes_each_real_wrapper_and_preserves_unmarked_actor(self):
        for label, suffix, expected, prefix in (
                ('quote', '|sell-priority', ['WOOL', 'WHEAT', 'MILK'], 'sell_priority'),
                ('pressure', '|supply-pressure', ['MILK', 'WHEAT', 'WOOL'], 'pressure_priority')):
            with self.subTest(mode=label):
                code, result, calls = self.run_cell(label, suffix)
                self.assertEqual(code, 0)
                self.assertEqual(result['responses'][0]['action'], ACTION)
                changed = result['responses'][1]['action']
                self.assertEqual([row[1] for row in changed['market'][:3]], expected)
                self.assertEqual(changed['market'][3:], ACTION['market'][3:])
                self.assertEqual(changed['farmer'], ACTION['farmer'])
                self.assertEqual(changed['hands'], ACTION['hands'])
                actor = result['actors'][1]
                self.assertTrue(actor[prefix + '_enabled'])
                self.assertEqual(actor[prefix + '_changed_turns'], 1)
                self.assertEqual(len(actor[prefix + '_transform_seconds']), 1)
                self.assertEqual(len(actor[prefix + '_total_seconds']), 1)
                self.assertEqual(len(actor['call_seconds']), 1)
                self.assertEqual(len(actor['rpc_seconds']), 1)
                self.assertEqual(bool(calls), label == 'pressure')

    def test_marked_parent_failure_preserves_rpc_failure_and_teardown(self):
        self.function.write_text('def agent(observation, configuration):\n'
                                 '    raise RuntimeError("fixture failure")\n')
        code, result, calls = self.run_cell('crash', '|supply-pressure')
        self.assertEqual(code, 1)
        self.assertEqual(result['responses'][1]['kind'], 'crash')
        self.assertIn('fixture failure', result['responses'][1]['error'])
        self.assertIn('rpc_failure', result['responses'][1])
        self.assertEqual(result['actors'][1]['pressure_priority_transform_seconds'], [])
        self.assertEqual(calls, [])

    def test_cell_retains_combined_parent_and_transform_deadline_failure(self):
        clock = [0.0]
        called = []

        def budget_exhausting_price(item, inventory, params=None):
            if not called:
                called.append(True)
                clock[0] += 6.0
            return {'WHEAT': 40, 'WOOL': 100, 'MILK': max(1, 20-3*inventory)}[item]

        code, result, _ = self.run_cell('deadline', '|supply-pressure',
                                      quote=budget_exhausting_price,
                                      pressure_clock=lambda: clock[0])
        self.assertEqual(code, 1)
        self.assertEqual(result['failure']['kind'], 'timeout')
        self.assertEqual(result['failure']['phase'], 'pressure_priority')
        actor = result['actors'][1]
        self.assertEqual(len(actor['call_seconds']), 1)
        self.assertEqual(actor['pressure_priority_total_seconds'], [6.0])

    def test_configured_sibling_import_restores_prior_module_on_success_and_error(self):
        foreign = object()
        engine = type('Engine', (), {'market_price': staticmethod(lambda *args: 1)})()
        with patch.dict(sys.modules, {'sell_priority': foreign}):
            driver.lark_actor(object, PATHS, engine)
            self.assertIs(sys.modules['sell_priority'], foreign)
            bad = dict(PATHS, pressure_priority=str(self.root / 'missing.py'))
            with self.assertRaises(FileNotFoundError):
                driver.lark_actor(object, bad, engine)
            self.assertIs(sys.modules['sell_priority'], foreign)


if __name__ == '__main__':
    unittest.main()
