# SPDX-License-Identifier: Apache-2.0
"""Execute both repository and rendered-package dependency closures."""
from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


def _load_builder():
    path = ROOT / 'build_integrated.py'
    spec = importlib.util.spec_from_file_location('_titan_package_closure_builder', path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load canonical builder: {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_isolated(code: str, *, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    command = [sys.executable]
    if sys.flags.optimize == 1:
        command.append('-O')
    elif sys.flags.optimize >= 2:
        command.append('-OO')
    command.extend(('-I', '-B', '-c', code))
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


class PackageDependencyClosureTests(unittest.TestCase):
    def test_source_tree_consumers_resolve_attributed_siblings(self):
        code = f"""
import json
from pathlib import Path
import sys
root = Path({str(ROOT)!r}).resolve()
sys.path.insert(0, str(root))
import main
import scheduler
import frozen_selected
import observed_clone
import seller_snapshot
import town_procurement
configuration = json.loads((root / 'TITAN-CONFIG.json').read_text(encoding='utf-8'))
instance = main._new_instance(root, configuration)
assert callable(instance.act)
assert scheduler.detached_json_value is observed_clone.detached_json_value
assert frozen_selected.seller_public_observation is seller_snapshot.seller_public_observation
assert Path(observed_clone.__source_path__).resolve() == (root.parent / 'cloud-runtime-pulse' / 'observed_clone.py').resolve()
assert Path(seller_snapshot.__source_path__).resolve() == (root.parent / 'cloud-quickstep' / 'seller_snapshot.py').resolve()
value = {{'rows': [{{'x': 1}}]}}
copy = scheduler.detached_json_value(value)
assert copy == value and copy is not value and copy['rows'] is not value['rows']
observation = {{'step': 3, 'player': 0, 'farms': [{{'tiles': []}}, {{'tiles': [[{{'crop': 'WHEAT'}}]]}}]}}
snapshot = frozen_selected.seller_public_observation(observation)
assert snapshot['farms'][1]['tiles'] == observation['farms'][1]['tiles']
assert snapshot['farms'][1]['tiles'] is not observation['farms'][1]['tiles']
assert Path(town_procurement.__file__).resolve() == (root / 'town_procurement.py').resolve()
print('source-tree dependency closure PASS')
"""
        result = _run_isolated(code, cwd=ROOT.parent)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('source-tree dependency closure PASS', result.stdout)

    def test_rendered_archive_executes_complete_root_import_graph(self):
        builder = _load_builder()
        mapping = builder.source_files()
        self.assertEqual(
            mapping.get('observed_clone.py'),
            '../cloud-runtime-pulse/observed_clone.py',
        )
        self.assertEqual(
            mapping.get('seller_snapshot.py'),
            '../cloud-quickstep/seller_snapshot.py',
        )
        self.assertEqual(mapping.get('town_procurement.py'), 'town_procurement.py')
        selected_stack = (
            'integrated_selected.py',
            'ordered_selected_sell.py',
            'selected_action_sell.py',
            'selected_sell_core.py',
        )
        for name in selected_stack:
            self.assertEqual(mapping.get(name), name)

        data, source_bytes, receipt = builder.render()
        self.assertEqual(receipt['runtime_files'], len(mapping))
        manifest = json.loads(source_bytes)
        self.assertEqual(set(manifest['runtime']), set(mapping))
        for name in selected_stack:
            self.assertEqual(manifest['runtime'][name]['source_path'], name)

        with tempfile.TemporaryDirectory(prefix='titan-package-closure-') as raw:
            runtime = Path(raw)
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
                members = archive.getmembers()
                for member in members:
                    path = Path(member.name)
                    self.assertTrue(member.isfile(), member.name)
                    self.assertFalse(path.is_absolute(), member.name)
                    self.assertNotIn('..', path.parts, member.name)
                archive.extractall(runtime)

            code = f"""
import json
from pathlib import Path
import sys
root = Path({str(runtime)!r}).resolve()
sys.path.insert(0, str(root))
import main
import scheduler
import frozen_selected
import observed_clone
import seller_snapshot
import town_procurement
import selected_action_sell
configuration = json.loads((root / 'TITAN-CONFIG.json').read_text(encoding='utf-8'))
instance = main._new_instance(root, configuration)
assert callable(instance.act)
assert scheduler.detached_json_value is observed_clone.detached_json_value
assert frozen_selected.seller_public_observation is seller_snapshot.seller_public_observation
for module in (observed_clone, seller_snapshot, town_procurement):
    path = Path(module.__file__).resolve()
    assert path.parent == root, (module.__name__, path, root)
assert not hasattr(observed_clone, '__source_path__')
assert not hasattr(seller_snapshot, '__source_path__')
try:
    selected_action_sell.observation_player({{'player': True}})
except ValueError:
    pass
else:
    raise AssertionError('packaged selected-action identity accepted bool player')
try:
    selected_action_sell.absolute_step(
        {{'step': None, 'day': 0, 'hour': 0}},
        {{'turnsPerDay': 24}},
    )
except ValueError:
    pass
else:
    raise AssertionError('packaged selected-action clock accepted explicit null step')
print('rendered package dependency closure PASS')
"""
            result = _run_isolated(code, cwd=runtime)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('rendered package dependency closure PASS', result.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
