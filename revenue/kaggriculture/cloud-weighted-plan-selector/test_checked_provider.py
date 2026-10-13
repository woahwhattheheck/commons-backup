# SPDX-License-Identifier: Apache-2.0
"""Additive actual-provider/checker/selector integration, not peer-suite reruns."""
import argparse
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import unittest

import test_weighted_selector as source
from checked_provider import checked_provider


class BindingTests(unittest.TestCase):
    def binding(self, provider=None, checker=None):
        return checked_provider(source.POLY.solve_full_table if provider is None else provider,
                                TRIAD.check_certificate if checker is None else checker)

    def test_actual_positive_result_passes_unchanged(self):
        binding = self.binding()
        actual = binding(source.TABLE)
        self.assertEqual(actual, source.POLY.solve_full_table(source.TABLE))
        self.assertEqual(binding.last_check['support'], [1, 2, 3])
        self.assertTrue(binding.last_check['positive_optimum'])

    def test_actual_all_four_consumers_commit_once(self):
        binding = self.binding()
        selected = source.make(2, provider=binding)
        actor = source.ASH(selected)
        for now in range(700, 704):
            out = source.act(actor, now, continuation_feasible=lambda p, c: True)
            self.assertEqual(out['market'][1], ['SELL', 'TOMATO', 8] if now == 703 else [])
        self.assertEqual((binding.calls, selected.provider_calls, selected.draws), (1, 1, 1))
        self.assertEqual(selected.active['plan_index'], 3)

    def test_actual_support_metadata_mismatch_keeps_full_fallback(self):
        def altered(rows):
            result = source.POLY.solve_full_table(rows)
            result['support'] = [0]
            self.assertTrue(source.POLY.verify_certificate(rows, result)['valid'])
            return result
        binding = self.binding(altered)
        selected = source.make(provider=binding)
        self.assertEqual(source.act(selected), source.BASE)
        self.assertEqual(selected.draws, 0)
        self.assertFalse(binding.last_check['valid'])
        self.assertEqual(source.act(selected), source.BASE)
        self.assertEqual(binding.calls, 1)

    def test_actual_stale_ordered_table_keeps_fallback(self):
        old_result = source.POLY.solve_full_table(source.TABLE)
        table = [source.TABLE[i] for i in (0, 2, 1, 3)]
        binding = self.binding(lambda rows: old_result)
        selected = source.make(provider=binding)
        self.assertEqual(source.act(selected, win=source.window(table=table)), source.BASE)
        self.assertFalse(binding.last_check['valid'])
        self.assertEqual(selected.draws, 0)

    def test_closed_bounds_at_budget_limit_are_not_completion(self):
        table = [[0, 0]] * 4
        binding = self.binding(lambda rows: source.POLY.solve_full_table(rows, max_pivots=0))
        selected = source.make(provider=binding)
        self.assertEqual(source.act(selected, win=source.window(table=table)), source.BASE)
        self.assertTrue(binding.last_check['valid'])
        self.assertTrue(binding.last_check['bounds_closed'])
        self.assertFalse(binding.last_check['completed'])
        self.assertFalse(binding.last_check['positive_optimum'])
        self.assertEqual(selected.draws, 0)

    def test_completed_zero_optimum_is_still_baseline(self):
        binding = self.binding()
        selected = source.make(provider=binding)
        self.assertEqual(source.act(selected, win=source.window(table=[[0]] * 4)), source.BASE)
        self.assertTrue(binding.last_check['completed'])
        self.assertFalse(binding.last_check['positive_optimum'])
        self.assertEqual(selected.draws, 0)

    def test_verdict_requires_exact_true_for_every_fact(self):
        for key in ('valid', 'completed', 'positive_optimum'):
            verdict = {'valid': True, 'completed': True, 'positive_optimum': True}
            verdict[key] = 1
            binding = self.binding(checker=lambda rows, result: verdict)
            self.assertIsNone(binding(source.TABLE))

    def test_checker_receives_detached_result(self):
        original = source.POLY.solve_full_table(source.TABLE)
        def checker(rows, result):
            verdict = TRIAD.check_certificate(rows, result)
            result['weights'][1] = '0'
            return verdict
        binding = self.binding(lambda rows: original, checker)
        self.assertEqual(binding(source.TABLE), original)
        self.assertEqual(original['weights'][1], '1/3')

    def test_exception_and_invalid_verdict_do_not_expose_context(self):
        def error(*args):
            raise RuntimeError('PRIVATE-SENTINEL')
        for provider, checker in ((error, TRIAD.check_certificate),
                                  (source.POLY.solve_full_table, error),
                                  (source.POLY.solve_full_table, lambda *args: None)):
            binding = self.binding(provider, checker)
            self.assertIsNone(binding(source.TABLE))
            self.assertNotIn('SENTINEL', repr(binding.last_check))


def main():
    global TRIAD
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--t15-dir', type=Path, default=root / 'cloud-market-game-theory')
    parser.add_argument('--continuation-dir', type=Path, default=root / 'cloud-plan-continuation')
    parser.add_argument('--full-support-dir', type=Path, default=root / 'cloud-full-support')
    parser.add_argument('--checker-dir', type=Path, default=root / 'cloud-market-support')
    parser.add_argument('--json-output', type=Path)
    args = parser.parse_args()
    source.setup_sources(args)
    checker_path = args.checker_dir / 'certificate_consumer.py'
    TRIAD = source.load_module('prism_triad', checker_path)
    capture = io.StringIO()
    result = unittest.TextTestRunner(stream=capture, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(BindingTests))
    print(capture.getvalue(), end='')
    hashes = deepcopy(source.SOURCES)
    for name, path in [('certificate_consumer', checker_path),
                       ('weighted_selector', Path(__file__).with_name('weighted_selector.py')),
                       ('checked_provider', Path(__file__).with_name('checked_provider.py')),
                       ('test_checked_provider', Path(__file__))]:
        b = path.read_bytes()
        hashes[name] = {'git_blob': hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest(),
                        'sha256': hashlib.sha256(b).hexdigest()}
    record = {'tests_run': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'passed': result.wasSuccessful(),
              'source_hashes': hashes, 'engine_executions': 0, 'full_games': 0,
              'original_33_method_receipt': 'VALIDATION.json unchanged',
              'peer_suites_rerun': False}
    if args.json_output:
        args.json_output.write_text(json.dumps(record, indent=2)+'\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
