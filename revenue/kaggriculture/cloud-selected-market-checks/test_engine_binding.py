# SPDX-License-Identifier: Apache-2.0
"""Offline CLI-loader regressions using the existing real evaluator and engine.

Run from any directory. Defaults use cloud-execution-lab/reference; arguments
may point to an existing source pack. No source downloads or game panels run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import check_market_contracts as checks

HERE = Path(__file__).resolve().parent
REFERENCE = HERE.parent / 'cloud-execution-lab/reference'
INPUTS = None
MARKET_CASES = 0


class EngineBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='titan binding ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / 'engine cache'
        self.cache.mkdir()
        for name in ('kaggriculture.py', 'kaggriculture.json', 'utils.py'):
            shutil.copyfile(INPUTS.engine_cache / name, self.cache / name)

    def evaluator(self, *, relocated):
        directory = self.root / ('reference/evaluator' if relocated else 'cloud-eval')
        directory.mkdir(parents=True)
        target = directory / 'evaluate.py'
        shutil.copyfile(INPUTS.evaluator, target)
        loader = (directory / 'loader.py' if relocated else
                  self.root / '20260907-offline-agent/evaluate.py')
        loader.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(INPUTS.engine_loader, loader)
        module = checks.load_file('binding_real_evaluator', target)
        return module, target, loader

    def assert_real_market(self, evaluator, engine, hashes):
        global MARKET_CASES
        self.assertEqual(hashes, evaluator.verify_sources(self.cache))
        self.assertTrue(callable(engine.interpreter))
        self.assertTrue(callable(engine._process_market))
        old = checks.EVALUATOR, checks.ENGINE, checks.RECEIPTS
        try:
            checks.EVALUATOR, checks.ENGINE, checks.RECEIPTS = evaluator, engine, []
            for seat in (0, 1):
                case = checks.fixture(seat=seat, orders=[['SELL', 'CARROT', 1]])
                result = checks.market_receipt(case)
                self.assertEqual((result['own_cash'], result['shed']['CARROT']), (1035, 0))
                MARKET_CASES += 1
        finally:
            checks.EVALUATOR, checks.ENGINE, checks.RECEIPTS = old

    def test_existing_default_loader_remains_usable(self):
        evaluator, _, _ = self.evaluator(relocated=False)
        engine, hashes = checks.load_engine(evaluator, self.cache)
        self.assert_real_market(evaluator, engine, hashes)

    def test_explicit_relocated_loader_executes_real_market(self):
        evaluator, _, loader = self.evaluator(relocated=True)
        engine, hashes = checks.load_engine(evaluator, self.cache, loader)
        self.assert_real_market(evaluator, engine, hashes)

    def test_missing_default_is_not_silently_replaced(self):
        evaluator, _, _ = self.evaluator(relocated=True)
        with self.assertRaises(FileNotFoundError) as caught:
            checks.load_engine(evaluator, self.cache)
        self.assertEqual(Path(caught.exception.filename),
                         self.root / 'reference/20260907-offline-agent/evaluate.py')

    def test_explicit_missing_loader_is_reported(self):
        evaluator, _, _ = self.evaluator(relocated=False)
        missing = self.root / 'missing requested loader.py'
        with self.assertRaises(FileNotFoundError) as caught:
            checks.load_engine(evaluator, self.cache, missing)
        self.assertEqual(Path(caught.exception.filename), missing)

    def test_engine_blob_checks_still_precede_loading(self):
        evaluator, _, loader = self.evaluator(relocated=True)
        target = self.cache / 'utils.py'
        target.write_bytes(target.read_bytes() + b'\n# altered fixture\n')
        with self.assertRaisesRegex(ValueError, 'Official source mismatch: utils.py'):
            checks.load_engine(evaluator, self.cache, loader)

    def test_help_exposes_optional_loader(self):
        result = subprocess.run([sys.executable, str(HERE / 'check_market_contracts.py'), '--help'],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--engine-loader', result.stdout)
        self.assertIn('omit to keep the evaluator default', ' '.join(result.stdout.split()))

    def test_cli_forwards_loader_before_seller_import(self):
        _, evaluator, loader = self.evaluator(relocated=True)
        # This intentionally absent seller is a diagnostic boundary, not a stub:
        # the actual evaluator and actual engine must load before reaching it.
        missing_lab = self.root / 'intentionally absent seller'
        command = [sys.executable, str(HERE / 'check_market_contracts.py'),
                   '--lab', str(missing_lab), '--evaluator', str(evaluator),
                   '--engine-loader', str(loader), '--engine-cache', str(self.cache)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(missing_lab / 'selected_action_sell.py'), result.stderr)
        self.assertNotIn('unrecognized arguments', result.stderr)
        self.assertNotIn('reference/20260907-offline-agent', result.stderr)


def main():
    global INPUTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluator', type=Path, default=REFERENCE / 'evaluator/evaluate.py')
    parser.add_argument('--engine-loader', type=Path, default=REFERENCE / 'evaluator/loader.py')
    parser.add_argument('--engine-cache', type=Path, default=REFERENCE / 'engine')
    parser.add_argument('--json-output', type=Path)
    INPUTS = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(EngineBindingTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    paths = {'checker': HERE / 'check_market_contracts.py',
             'evaluator': INPUTS.evaluator, 'loader': INPUTS.engine_loader}
    report = dict(schema='titan.selected-market-loader-tests.v1',
                  test_methods=result.testsRun, failures=len(result.failures),
                  errors=len(result.errors), successful=result.wasSuccessful(),
                  official_market_cases=MARKET_CASES, game_panels=0, seeds_consumed=[],
                  source_sha256={key: hashlib.sha256(path.read_bytes()).hexdigest()
                                 for key, path in paths.items()})
    if INPUTS.json_output:
        INPUTS.json_output.parent.mkdir(parents=True, exist_ok=True)
        INPUTS.json_output.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    print(json.dumps(report, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
