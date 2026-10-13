# SPDX-License-Identifier: Apache-2.0
"""Real-CLI custody and false-PASS controls for the EVENTPATH engine oracle."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ORACLE_SHA256 = 'c71f706c2bd693c42fd17510a1524a86508f5e4254bd4e463197346a463a62a6'
ROOT = ORACLE = None
RUNS = []


def digest(data):
    return hashlib.sha256(data).hexdigest()


class OracleCLIContract(unittest.TestCase):
    def invoke(self, surface='selected_sell_core', source=None, pin=None,
               omit_pin=False, baseline=False):
        with tempfile.TemporaryDirectory(prefix='eventpath-contract-') as directory:
            work = Path(directory)
            candidate = work / 'candidate.py'
            report = work / 'result.json'
            source = source if source is not None else (ROOT / (surface + '.py')).read_text()
            candidate.write_text(source, encoding='utf-8')
            command = [sys.executable] + ([] if __debug__ else ['-O']) + [
                str(ORACLE), '--runtime-root', str(ROOT), '--surface', surface,
                '--output', str(report)]
            if not baseline:
                command += ['--candidate', str(candidate)]
                if not omit_pin:
                    command += ['--candidate-sha256', pin or digest(source.encode())]
            process = subprocess.run(command, cwd=work, capture_output=True,
                                     text=True, timeout=30)
            data = json.loads(report.read_text()) if report.exists() else None
            RUNS.append({'name': self.id().split('.')[-1], 'surface': surface,
                         'candidate_sha256': digest(source.encode()) if not baseline else None,
                         'exit_code': process.returncode,
                         'stdout_sha256': digest(process.stdout.encode()),
                         'stderr_sha256': digest(process.stderr.encode()),
                         'unittest': None if data is None else data['unittest']})
            return process, data

    def test_01_baseline_is_explicitly_not_a_candidate_pass(self):
        process, result = self.invoke(baseline=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(result['validation'], 'baselines-only')
        self.assertEqual(result['unittest']['skipped'], 1)
        self.assertNotIn('candidate', result)
        self.assertEqual(result['counts']['optimizer_pairs'], 0)

    def test_02_active_identity_control_exercises_complete_optimizer(self):
        process, result = self.invoke()
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertTrue(result['passed'])
        self.assertEqual(result['unittest'], {'run': 8, 'failures': 0, 'errors': 0, 'skipped': 0})
        self.assertEqual(result['counts']['optimizer_pairs'], 36)

    def test_03_standalone_identity_control(self):
        process, result = self.invoke(surface='scheduler')
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(result['unittest']['skipped'], 0)
        self.assertEqual(result['counts']['optimizer_pairs'], 36)

    def test_04_wrong_hash_rejects_before_candidate_compilation(self):
        process, result = self.invoke(source='this is not valid python !!!', pin='0' * 64)
        self.assertEqual(process.returncode, 2)
        self.assertIn('candidate SHA256 mismatch', process.stderr)
        self.assertNotIn('SyntaxError', process.stderr)
        self.assertIsNone(result)

    def test_05_missing_hash_rejects(self):
        process, result = self.invoke(omit_pin=True)
        self.assertEqual(process.returncode, 2)
        self.assertIn('must be supplied together', process.stderr)
        self.assertIsNone(result)

    def test_06_wrong_rival_semantics_cannot_pass_engine_gate(self):
        source = (ROOT / 'selected_sell_core.py').read_text()
        self.assertEqual(source.count('r=rival_orders.get(step,0)'), 1)
        source = source.replace('r=rival_orders.get(step,0)', 'r=0')
        process, result = self.invoke(source=source)
        self.assertEqual(process.returncode, 1)
        self.assertFalse(result['passed'])
        self.assertGreater(result['unittest']['failures'], 0)
        self.assertIn('test_01_full_score', process.stderr)

    def test_07_town_before_market_cannot_pass_engine_gate(self):
        source = (ROOT / 'selected_sell_core.py').read_text()
        source = source.replace('for step,used in zip(steps,consumed):\n',
                                'for step,used in zip(steps,consumed):\n            inv-=used\n')
        source = source.replace('            inv-=used\n        remaining=', '        remaining=')
        process, result = self.invoke(source=source)
        self.assertEqual(process.returncode, 1)
        self.assertFalse(result['passed'])
        self.assertIn('test_02_floor_admission', process.stderr)

    def test_08_equal_scores_cannot_hide_optimizer_diagnostic_drift(self):
        source = (ROOT / 'selected_sell_core.py').read_text() + '''
_original_optimize_lot = optimize_lot
def optimize_lot(**kwargs):
    plan, info = _original_optimize_lot(**kwargs)
    changed = dict(info)
    changed['false_pass_probe'] = True
    return plan, changed
'''
        process, result = self.invoke(source=source)
        self.assertEqual(process.returncode, 1)
        self.assertFalse(result['passed'])
        self.assertEqual(result['unittest']['failures'], 36)
        self.assertEqual(result['unittest']['errors'], 0)
        self.assertIn('test_06_complete_optimizer', process.stderr)


def main():
    global ROOT, ORACLE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--oracle', type=Path, default=Path(__file__).with_name('test_eventpath_engine.py'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    ROOT, ORACLE = args.runtime_root.resolve(), args.oracle.resolve()
    if digest(ORACLE.read_bytes()) != ORACLE_SHA256:
        parser.exit(2, 'oracle source differs from tested c71f706c pin\n')
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(OracleCLIContract))
    receipt = {'schema': 'titan-eventpath-cli-contract-v1', 'oracle_sha256': ORACLE_SHA256,
               'optimized_python': not __debug__, 'passed': result.wasSuccessful(),
               'unittest': {'run': result.testsRun, 'failures': len(result.failures),
                            'errors': len(result.errors), 'skipped': len(result.skipped)},
               'subprocess_runs': RUNS, 'candidate_claim': 'identity-controls and explicit negative mutants only'}
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.write_text(rendered, encoding='utf-8')
    print(rendered, end='')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
