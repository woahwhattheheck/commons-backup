# SPDX-License-Identifier: Apache-2.0
"""Archive-backed composition and public callback contracts."""
import argparse
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_production_recovery as build
from build_delivery import members

INPUTS = None


class ProductionRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if INPUTS is None:
            raise unittest.SkipTest('Run this archive-backed suite with --v31 and --delivery')
        cls.v31 = members(INPUTS.v31, build.V31_SHA)
        cls.delivery = members(INPUTS.delivery, build.DELIVERY_SHA)
        cls.overlay = Path(__file__).with_name('production_recovery_overlay.txt').read_bytes()
        cls.output = build.compose(cls.v31, cls.delivery, cls.overlay)

    def test_exact_composition_preserves_all_retained_members(self):
        self.assertEqual(len(self.output), 92)
        self.assertEqual(build.digest(build.archive_bytes(self.output)), build.CANDIDATE_SHA)
        self.assertEqual(len(build.dependency_closure(self.v31)), 13)
        for name in build.DEPENDENCIES:
            self.assertEqual(self.output[name], self.v31[name])
        changed = {'main.py', build.VENDOR}
        for name, raw in self.delivery.items():
            if name not in changed:
                self.assertEqual(self.output[name], raw, name)

    def test_mutated_donor_cannot_produce_authorized_archive(self):
        changed = dict(self.v31)
        changed['b5_fertilize.py'] += b'\n# different donor\n'
        with self.assertRaisesRegex(ValueError, 'differs from the tested'):
            build.compose(changed, self.delivery, self.overlay)

    def test_v2_remains_reproducible_and_v3_changes_only_entry_import(self):
        legacy = build.compose(self.v31, self.delivery, self.overlay, 'v2')
        self.assertEqual(build.digest(build.archive_bytes(legacy)), build.LEGACY_SHA)
        self.assertEqual(set(legacy), set(self.output))
        self.assertEqual([name for name in legacy if legacy[name] != self.output[name]], ['main.py'])
        self.assertEqual(self.output['main.py'], legacy['main.py'].replace(
            b'import baseline_main as baseline\n',
            b'import baseline_main as baseline\nimport full_production_context\n', 1))
        with self.assertRaisesRegex(ValueError, 'Expected v2 or v3'):
            build.compose(self.v31, self.delivery, self.overlay, 'unknown')

    def test_raw_file_callback_from_unrelated_working_directory(self):
        # A real first decision through the existing pinned raw-file loader,
        # in a fresh interpreter with neither checkout nor payload on sys.path.
        script = '''
from pathlib import Path
import importlib.util, json, sys
kg, root = map(Path, sys.argv[1:])
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
ev = load('callback_evaluator', kg/'cloud-execution-lab/reference/evaluator/evaluate.py')
engine, _ = ev.get_engine(kg/'cloud-execution-lab/reference/engine', kg/'20260907-offline-agent/evaluate.py')
cfg = ev.Struct({k: v.get('default') if isinstance(v, dict) else v
                 for k, v in engine.specification['configuration'].items()})
cfg.seed = 1209129901
env = ev.Struct(configuration=cfg, done=False, info={})
state = [ev.Struct(observation=ev.Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
engine.interpreter(state, env)
state[0].observation.step = 0
state[0].observation.remainingOverageTime = 0
official = load('callback_official', kg/'cloud-pack/official.py')
action = official.make_agent(root/'main.py')(state[0].observation, cfg)
print(json.dumps({'action': action, 'status': sys.modules['baseline_main']._INSTANCE.diagnostics['status']}))
'''
        kg = Path(__file__).resolve().parents[4]
        for version in ('v2', 'v3'):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)/'payload'
                for name, raw in build.compose(self.v31, self.delivery, self.overlay, version).items():
                    path = root/name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
                flags = [] if __debug__ else ['-O']
                result = subprocess.run([sys.executable, *flags, '-I', '-B', '-c', script,
                                         str(kg), str(root)], cwd=temp, capture_output=True,
                                        text=True, timeout=30)
                if version == 'v2':
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("No module named 'full_production_context'", result.stderr)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    import json
                    record = json.loads(result.stdout)
                    self.assertIsInstance(record['action'], dict)
                    self.assertEqual(record['status'], 'completed')

    def test_conflicting_dependency_is_not_overwritten(self):
        changed = dict(self.delivery, **{'b5_fertilize.py': b'competing = True\n'})
        with self.assertRaisesRegex(ValueError, 'Incompatible existing dependency'):
            build.compose(self.v31, changed, self.overlay)

    def test_bad_archive_is_rejected_before_composition(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'not-v31.tar.gz'
            path.write_bytes(b'not the required archive')
            with self.assertRaisesRegex(ValueError, 'Archive identity mismatch'):
                members(path, build.V31_SHA)

    def test_single_donor_call_configuration_and_route_identity(self):
        import json
        config = json.loads(self.v31['TITAN-CONFIG.json'])
        calls = []
        r04 = types.ModuleType('r04_full_router')
        r04._POLICY = types.SimpleNamespace(players={1: types.SimpleNamespace(plan=0)})
        def install(**kwargs):
            calls.append(('install', kwargs))
            def selected(obs, cfg):
                calls.append(('act', obs, cfg))
                r04._POLICY.players[1].plan = 2
                return {'farmer': ['PASS'], 'market': [['SELL', 'WOOL', 3]]}
            return selected
        r04.install = install
        tapes = types.ModuleType('r01_tapes')
        tapes.load_tapes = lambda: [[{'route': i}] for i in range(13)]
        context = types.ModuleType('full_production_context')
        context.configuration = {'turnsPerDay': 24}
        class Base:
            def __init__(self):
                self.base_initialized = True
        namespace = {'Agent': Base}
        with patch.dict(sys.modules, {'r04_full_router': r04, 'r01_tapes': tapes,
                                      'full_production_context': context}):
            exec(compile(self.overlay, 'production_recovery_overlay.txt', 'exec'), namespace)
            agent = namespace['Agent']()
            returned = agent.act({'player': 1, 'step': 41})
        self.assertTrue(agent.base_initialized)
        self.assertEqual(len(agent.R), 13)
        self.assertEqual(agent.cur, 'R04-2')
        self.assertEqual(returned['market'], [['SELL', 'WOOL', 3]])
        self.assertEqual([c[0] for c in calls], ['install', 'act'])
        self.assertIs(calls[1][2], context.configuration)
        mapping = {'horizon':'r04_sale_horizon', 'opening':'r04_open_roundtrip'}
        for key, value in calls[0][1].items():
            self.assertEqual(value, config[mapping.get(key, 'r04_' + key)], key)

    def test_outer_callback_normalizes_missing_null_and_present_steps(self):
        for seat in (0, 1):
            for form in ('missing', 'null', 'present'):
                with self.subTest(seat=seat, form=form):
                    baseline = types.ModuleType('baseline_main')
                    baseline._INSTANCE = object()
                    baseline._new_instance = lambda *_: None
                    observed, committed = [], []
                    action = {'farmer': ['PASS']}
                    baseline.agent = lambda obs, cfg: observed.append((obs, cfg)) or action
                    context = types.ModuleType('full_production_context')
                    context.configuration = {}
                    namespace = {}
                    with patch.dict(sys.modules, {'baseline_main': baseline,
                                                  'full_production_context': context}):
                        exec(compile(self.output['main.py'], 'generated_entry', 'exec'), namespace)
                        namespace['_CHOICE'] = types.SimpleNamespace(commit=lambda obs, act: committed.append((obs, act)))
                        obs = {'player': seat, 'day': 3, 'hour': 5}
                        if form != 'missing':
                            obs['step'] = None if form == 'null' else 41
                        before = deepcopy(obs)
                        cfg = {'turnsPerDay': 12}
                        returned = namespace['agent'](obs, cfg)
                    self.assertEqual(obs, before)
                    self.assertIs(returned, action)
                    self.assertEqual(len(observed), 1)
                    self.assertEqual(observed[0][0]['step'], 41)
                    self.assertIs(committed[0][0], observed[0][0])
                    self.assertIs(committed[0][1], action)
                    self.assertEqual(context.configuration, cfg)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--v31', type=Path, required=True)
    parser.add_argument('--delivery', type=Path, required=True)
    INPUTS = parser.parse_args()
    unittest.main(argv=[sys.argv[0]])
