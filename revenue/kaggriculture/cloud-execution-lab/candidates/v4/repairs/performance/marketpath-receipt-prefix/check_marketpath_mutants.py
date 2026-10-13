# SPDX-License-Identifier: Apache-2.0
"""Reject deliberately broken receipt kernels using the existing semantic gate."""
from __future__ import annotations
import argparse
import contextlib
import io
import json
from pathlib import Path
import unittest
import check_marketpath_receipt_prefix as gate

MUTANTS = {
    'floor_admits_supply': ('current + stride if price > 1 else current', 'current + stride'),
    'paired_quotes_sequentially': ('min(own, rival), 2, False', 'min(own, rival), 1, False'),
    'single_loses_float_rounding': ('quantity, 1, True', 'quantity, 1, False'),
    'paired_loses_integer_rounding': ('min(own, rival), 2, False', 'min(own, rival), 2, True'),
    'asymmetric_tail_dropped': ('abs(own-rival), 1, False', '0, 1, False'),
    'cash_receipt_offset': ('return int(cash), end', 'return int(cash) + 1, end'),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    original = gate.patch.transform
    report = {'optimized_python': not __debug__, 'mutants': {}}
    for name, (before, after) in MUTANTS.items():
        def transform(source, before=before, after=after):
            revised = original(source)
            if revised.count(before) != 1:
                raise ValueError('mutant anchor is not unique: ' + before)
            return revised.replace(before, after)
        gate.patch.transform = transform
        gate.ROOT = args.runtime.resolve()
        gate.bootstrap(gate.ROOT)
        tests = unittest.TestSuite()
        # Mechanism tests only: source-integrity failures are not credited as
        # detection of an actual numerical or engine mutation.
        for method in ('test_single_all_quantities_all_products',
                       'test_joint_order_asymmetry_and_floor_boundaries',
                       'test_float_single_vs_integer_joint_discriminator'):
            tests.addTest(gate.NumericalContract(method))
        tests.addTest(gate.EngineAndOptimizer('test_actual_official_market_both_physical_seats'))
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            result = unittest.TextTestRunner(stream=stream, verbosity=1).run(tests)
        entry = {'tests_run': result.testsRun, 'failures': len(result.failures),
                 'errors': len(result.errors), 'rejected': not result.wasSuccessful(),
                 'failing_tests': [str(test) for test, _ in result.failures],
                 'error_tests': [str(test) for test, _ in result.errors]}
        report['mutants'][name] = entry
        print(name, json.dumps(entry, sort_keys=True))
    gate.patch.transform = original
    with args.report.open('x') as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write('\n')
    # Require assertion failures, not just exceptions or bootstrap failures.
    raise SystemExit(0 if all(x['failures'] > 0 and x['errors'] == 0
                             for x in report['mutants'].values()) else 1)


if __name__ == '__main__':
    main()
