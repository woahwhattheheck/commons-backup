# SPDX-License-Identifier: Apache-2.0
"""Loader regressions using the existing unchanged pinned Kaggle definitions."""
import hashlib
import importlib.util
import json
from pathlib import Path
import os
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
PACK = HERE.parent / 'cloud-pack'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class RawEntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.official = load('t06_test_official', PACK / 'official.py')
        cls.pack = load('t06_test_pack', PACK / 'pack.py')

    def setUp(self):
        self.paths = list(sys.path)
        self.cwd = Path.cwd()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.wrapper = self.root / 'main.py'
        shutil.copyfile(HERE / 'raw_entrypoint.py', self.wrapper)
        target = self.root / 'cloud-search-kernel'
        target.mkdir()
        (target / 'entrypoint.py').write_text(
            "calls=0\n"
            "def agent(observation, configuration=None):\n"
            "    global calls\n"
            "    calls += 1\n"
            "    return {'calls':calls, 'step':observation['step'], 'setting':configuration['setting']}\n")

    def tearDown(self):
        os.chdir(self.cwd)
        sys.path[:] = self.paths
        self.tmp.cleanup()

    def test_raw_loader_without_file_global(self):
        runner = self.official.make_agent(self.wrapper)
        self.assertEqual(runner({'step': 0}, {'setting': 7}),
                         {'calls': 1, 'step': 0, 'setting': 7})

    def test_state_persists_across_calls(self):
        runner = self.official.make_agent(self.wrapper)
        runner({'step': 0}, {'setting': 7})
        self.assertEqual(runner({'step': 1}, {'setting': 9}),
                         {'calls': 2, 'step': 1, 'setting': 9})

    def test_unrelated_working_directory(self):
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir()
        os.chdir(elsewhere)
        self.assertEqual(self.official.make_agent(self.wrapper)(
            {'step': 0}, {'setting': 3})['setting'], 3)

    def test_normal_module_source_layout(self):
        nested = self.root / 'cloud-search-kernel/entrypoint.py'
        nested.rename(self.root / 'entrypoint.py')
        module = load('t06_source_wrapper_test', self.wrapper)
        self.assertEqual(module.agent({'step': 0}, {'setting': 4})['setting'], 4)

    def test_missing_asset_is_explicit(self):
        (self.root / 'cloud-search-kernel/entrypoint.py').unlink()
        with self.assertRaisesRegex(FileNotFoundError, 'absent'):
            self.official.make_agent(self.wrapper)({'step': 0}, {})

    def test_existing_file_entrypoint_is_not_raw_compatible(self):
        # Preserve the old module as historical execution bytes, not a raw-file
        # deployment claim. The new wrapper is the explicit compatible route.
        sys.path.insert(0, str(HERE))
        with self.assertRaisesRegex(Exception, '__file__'):
            self.official.make_agent(HERE / 'entrypoint.py')({'step': 0}, {})

    def test_export_profile_and_unchanged_runtime(self):
        spec, sources = self.pack.read_spec(HERE / 'export-profile.json')
        self.assertEqual(len(sources), 15)
        for name in ('search_kernel.py', 'sell_backend.py', 'entrypoint.py'):
            self.assertEqual(spec['files']['cloud-search-kernel/' + name]['sha256'],
                             hashlib.sha256((HERE / name).read_bytes()).hexdigest())
        self.assertIn('cloud-titan-composition/vendor/sell/NOTICE', sources)
        self.assertIn('cloud-search-kernel/LICENSE', sources)

    def test_reproducible_bundle_with_complete_assets(self):
        a = self.pack.build(HERE / 'export-profile.json', self.root / 'a')
        b = self.pack.build(HERE / 'export-profile.json', self.root / 'b')
        self.assertEqual(a['archive_sha256'], b['archive_sha256'])
        manifest = self.pack.verify(self.root / 'a', self.root / 'extracted')
        self.assertEqual(len(manifest['members']), 15)
        self.assertTrue((self.root / 'extracted/cloud-search-kernel/entrypoint.py').is_file())


if __name__ == '__main__':
    unittest.main()
