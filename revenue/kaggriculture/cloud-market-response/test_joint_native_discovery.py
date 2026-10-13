# SPDX-License-Identifier: MIT
"""Optional-resource discovery and registration lifetime, no game execution."""
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

TARGET = Path(os.environ.get('TITAN_NATIVE_TEST_PATH', Path(__file__).with_name('test_joint_terminal_native.py'))).resolve()
ROOT = TARGET.parent
NAMES = ('joint_native_flow', 'kaggle_environments', 'kaggle_environments.utils',
         'joint_native_mechanics', 'joint_poly_terminal_inputs')


def environment(**updates):
    env = dict(os.environ)
    for name in ('TITAN_ENGINE_DIR', 'TITAN_TERMINAL_INPUTS_PATH', 'TITAN_FLOW_PATH', 'TITAN_JOINT_REPORT'):
        env.pop(name, None)
    env.update(updates)
    return env


def load_target():
    spec = importlib.util.spec_from_file_location('native_discovery_subject', TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DiscoveryTests(unittest.TestCase):
    def child(self, code, **updates):
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT,
                                env=environment(**updates), text=True,
                                capture_output=True, timeout=15)
        return result

    def test_import_requires_no_engine_configuration_or_registration(self):
        code = f'''import importlib.util, sys
from types import ModuleType
names = {NAMES!r}
originals = {{name: ModuleType(name) for name in names}}
sys.modules.update(originals)
spec = importlib.util.spec_from_file_location('subject', {str(TARGET)!r})
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert all(sys.modules[name] is old for name, old in originals.items())
assert 'm' not in vars(m) and 'terminal' not in vars(m)
'''
        result = self.child(code)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_discovery_records_one_named_class_skip(self):
        code = f'''import importlib.util, json, unittest
spec=importlib.util.spec_from_file_location('subject', {str(TARGET)!r})
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
r=unittest.TestResult()
unittest.defaultTestLoader.loadTestsFromTestCase(m.NativeJoinTests).run(r)
assert r.testsRun == 0 and len(r.skipped) == 1
assert not r.errors and not r.failures
assert 'TITAN_ENGINE_DIR' in r.skipped[0][1]
print(json.dumps({{'tests': r.testsRun, 'skipped': len(r.skipped)}}))
'''
        result = self.child(code)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'tests': 0, 'skipped': 1})

    def test_standalone_skip_report_cannot_look_like_executed_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            report = str(Path(temp)/'report.json')
            result = subprocess.run([sys.executable, '-B', str(TARGET)], cwd=ROOT,
                env=environment(TITAN_JOINT_REPORT=report), capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(Path(report).read_text())
            self.assertEqual(data['tests'], 0)
            self.assertEqual(data['skipped'], 1)
            self.assertIn('native inputs not configured', data['skip_reasons'][0])
            self.assertTrue(all(v == 0 for v in data['counts'].values()))

    def test_configured_bad_path_is_error_not_skip_and_restores_modules(self):
        code = f'''import importlib.util, sys, unittest
from types import ModuleType
originals = {{n: ModuleType(n) for n in {NAMES!r}}}
sys.modules.update(originals)
spec=importlib.util.spec_from_file_location('subject', {str(TARGET)!r})
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
r=unittest.TestResult(); unittest.defaultTestLoader.loadTestsFromTestCase(m.NativeJoinTests).run(r)
assert len(r.errors) == 1 and not r.skipped
assert 'FileNotFoundError' in r.errors[0][1]
assert all(sys.modules[n] is old for n,old in originals.items())
'''
        with tempfile.TemporaryDirectory() as temp:
            result = self.child(code, TITAN_ENGINE_DIR=str(Path(temp)/'absent-engine'),
                                TITAN_TERMINAL_INPUTS_PATH=str(Path(temp)/'absent-inputs.py'))
        self.assertEqual(result.returncode, 0, result.stderr)

    def fixtures(self, root, *, terminal_error=False):
        (root/'utils.py').write_text('def resolve_episode_seed(*args, **kwargs):\n    return 0\n')
        (root/'kaggriculture.py').write_text('from kaggle_environments.utils import resolve_episode_seed\nPRODUCTS=[]\n')
        terminal = root/'terminal_inputs.py'
        terminal.write_text('raise RuntimeError("configured-terminal-error")\n' if terminal_error else 'VALUE = 1\n')
        return {'TITAN_ENGINE_DIR': str(root), 'TITAN_TERMINAL_INPUTS_PATH': str(terminal)}

    def test_successful_setup_restores_preexisting_registrations(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, environment(), clear=True):
            module = load_target()
            settings = self.fixtures(Path(temp))
            originals = {n: ModuleType(n) for n in NAMES}
            with patch.dict(sys.modules, originals), patch.dict(os.environ, settings):
                with ExitStack() as stack:
                    module.configure(stack)
                    self.assertTrue(all(sys.modules[n] is not old for n,old in originals.items()))
                self.assertTrue(all(sys.modules[n] is old for n,old in originals.items()))

    def test_failed_setup_restores_preexisting_registrations(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, environment(), clear=True):
            module = load_target()
            settings = self.fixtures(Path(temp), terminal_error=True)
            originals = {n: ModuleType(n) for n in NAMES}
            with patch.dict(sys.modules, originals), patch.dict(os.environ, settings):
                with self.assertRaisesRegex(RuntimeError, 'configured-terminal-error'):
                    with ExitStack() as stack:
                        module.configure(stack)
                self.assertTrue(all(sys.modules[n] is old for n,old in originals.items()))

    def test_successful_setup_removes_only_its_new_registrations(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, environment(), clear=True):
            module = load_target()
            settings = self.fixtures(Path(temp))
            with patch.dict(sys.modules), patch.dict(os.environ, settings):
                for name in NAMES:
                    sys.modules.pop(name, None)
                with ExitStack() as stack:
                    module.configure(stack)
                    # A different import is not owned by this native-test harness.
                    unrelated = ModuleType('native_discovery_unrelated')
                    sys.modules['native_discovery_unrelated'] = unrelated
                self.assertTrue(all(n not in sys.modules for n in NAMES))
                self.assertIs(sys.modules['native_discovery_unrelated'], unrelated)

    def test_explicit_terminal_hash_mismatch_still_fails(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, environment(), clear=True):
            module = load_target()
            settings = self.fixtures(Path(temp))
            with patch.dict(os.environ, settings), ExitStack() as stack:
                module.configure(stack)
                with self.assertRaises(AssertionError):
                    module.NativeJoinTests('test_actual_source_identities').test_actual_source_identities()


if __name__ == '__main__':
    unittest.main(verbosity=2)
