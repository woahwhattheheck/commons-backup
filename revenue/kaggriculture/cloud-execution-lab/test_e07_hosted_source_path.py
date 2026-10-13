# SPDX-License-Identifier: Apache-2.0
"""Hosted E07 source-path packaging: seller_snapshot lives in cloud-quickstep.

GitHub Actions run 34374954989 (SOL Astra E07 hosted diagnostic, SHA
a5414085c3484b31cc63a2101d566a578f7c16a2) failed while loading
test_e07_same_turn_funding and test_joint_market_slots:

    ModuleNotFoundError: No module named 'seller_snapshot'

The job PYTHONPATH listed cloud-runtime-pulse and cloud-execution-lab but not
cloud-quickstep, where build_integrated.source_files maps seller_snapshot.py.
The same unittest modules import once that sibling is on the path. This
contract does not require the packaged tarball.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

LAB = Path(__file__).resolve().parent
QUICKSTEP = LAB.parent / 'cloud-quickstep'
PULSE = LAB.parent / 'cloud-runtime-pulse'
PROBE = 'from frozen_selected import fund_same_turn_acquisition, sale_quantities'


def _run(pythonpath, probe=PROBE):
    env = os.environ.copy()
    env['PYTHONPATH'] = pythonpath
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    return subprocess.run(
        [sys.executable, '-B', '-c', probe],
        cwd=LAB, env=env, capture_output=True, text=True)


class HostedSourcePathContracts(unittest.TestCase):
    def test_source_files_maps_seller_snapshot_to_quickstep(self):
        from build_integrated import source_files
        mapping = source_files()
        self.assertEqual(
            mapping['seller_snapshot.py'],
            '../cloud-quickstep/seller_snapshot.py')
        self.assertEqual(
            mapping['observed_clone.py'],
            '../cloud-runtime-pulse/observed_clone.py')
        self.assertTrue((QUICKSTEP / 'seller_snapshot.py').is_file())
        self.assertTrue((PULSE / 'observed_clone.py').is_file())

    def test_pulse_and_lab_without_quickstep_cannot_import_frozen_selected(self):
        result = _run(f'{PULSE}:{LAB}')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('seller_snapshot', result.stderr)

    def test_complete_source_path_imports_frozen_selected(self):
        result = _run(f'{PULSE}:{QUICKSTEP}:{LAB}')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_packaged_symbols_resolve_from_source_siblings(self):
        probe = (
            'from seller_snapshot import seller_public_observation\n'
            'from observed_clone import detached_json_value\n'
            'from frozen_selected import fund_same_turn_acquisition\n'
            'assert callable(seller_public_observation)\n'
            'assert callable(detached_json_value)\n'
            'assert callable(fund_same_turn_acquisition)\n'
        )
        result = _run(f'{PULSE}:{QUICKSTEP}:{LAB}', probe)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
