# SPDX-License-Identifier: Apache-2.0
"""Reject behavioral faults with real contracts; never edit the checked source."""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
MUTATIONS = [
    ('identity_only', '    return candidate + orders[end:] if exposed else orders',
     '    return orders', 'test_01_exact_baseline_counterexample_both_seats'),
    ('stale_pre_unit_stock', '        _, private = post_units(observation, baseline, cfg)',
     "        private = observation['private']", 'test_13_adapter_uses_selected_unit_vector_not_cached_snapshot'),
    ('duplicate_double_count', '        remaining[item] = remaining.get(item, 0) - fill',
     '        remaining[item] = remaining.get(item, 0)', 'test_02_duplicate_exhaustion_and_partial_lots_keep_rows'),
    ('trim_requested_quantity', '            positive.append(row)',
     "            positive.append(['SELL', item, fill])", 'test_02_duplicate_exhaustion_and_partial_lots_keep_rows'),
    ('ignore_raw_slot_cap', '    end = min(len(orders), limit)',
     '    end = len(orders)', 'test_03_dead_raw_suffix_and_minimum_one_cap'),
    ('move_operating_input', '        if row[2] and row[1] not in SALE_ONLY:',
     '        if False:', 'test_04_economic_input_unknown_and_malformed_barriers'),
    ('swallow_deadline', '    except (ArithmeticError, LookupError, TypeError, ValueError):',
     '    except BaseException:', 'test_09_invalid_player_and_projection_decline_not_swallow_deadline'),
    ('skip_public_curve', '    prices, inventories = market.get(\'prices\'), market.get(\'inventory\')',
     "    return candidate + orders[end:]\n    prices, inventories = market.get('prices'), market.get('inventory')",
     'test_06_bad_configuration_and_quote_fail_closed'),
    ('reverse_productive_order', '    candidate = positive + empty',
     '    candidate = list(reversed(positive)) + empty', 'test_02_duplicate_exhaustion_and_partial_lots_keep_rows'),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    source = (HERE/'stockless_pressure.py').read_text()
    spec = importlib.util.spec_from_file_location('_stockless_contracts', HERE/'test_stockless_pressure.py')
    tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tests)
    tests.ROOT = args.runtime.resolve()
    rows = []
    # A control must pass every exact test used to kill a mutant. Import or
    # source-pin errors are NOT accepted as evidence of a behavioral kill.
    originals = sorted({row[3] for row in MUTATIONS})
    result = unittest.TextTestRunner(stream=io.StringIO()).run(
        unittest.TestSuite(tests.Contracts(name) for name in originals))
    if not result.wasSuccessful():
        raise RuntimeError('unmodified mutation control failed')
    for name, old, new, test in MUTATIONS:
        count = source.count(old)
        expected = 2 if name == 'swallow_deadline' else 1
        if count != expected:
            raise RuntimeError(f'{name}: ambiguous mutation target ({count} != {expected})')
        changed = source.replace(old, new)
        module = types.ModuleType('stockless_pressure')
        exec(compile(changed, str(HERE/'stockless_pressure.py'), 'exec'), module.__dict__)
        tests.candidate = module
        with patch.dict(sys.modules, {'stockless_pressure': module}):
            sink = io.StringIO()
            with contextlib.redirect_stdout(sink):
                r = unittest.TextTestRunner(stream=sink).run(tests.Contracts(test))
        behavioral_failure = bool(r.failures) and not r.errors and r.testsRun == 1
        rows.append({'name': name, 'test': test, 'rejected_by_assertion': behavioral_failure,
                     'failures': len(r.failures), 'errors': len(r.errors),
                     'mutant_sha256': hashlib.sha256(changed.encode()).hexdigest()})
        if not behavioral_failure:
            raise RuntimeError(f'{name} was not rejected behaviorally: {sink.getvalue()}')
    report = {'optimized': not __debug__, 'control_tests_passed': len(originals),
              'mutants_rejected': len(rows), 'mutants': rows,
              'source_unchanged': (HERE/'stockless_pressure.py').read_text() == source}
    text = json.dumps(report, sort_keys=True, indent=2)+'\n'
    if args.receipt:
        args.receipt.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
