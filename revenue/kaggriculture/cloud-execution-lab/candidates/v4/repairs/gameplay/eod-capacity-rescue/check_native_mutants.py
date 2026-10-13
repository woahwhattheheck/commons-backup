# SPDX-License-Identifier: Apache-2.0
"""Reject deliberately broken native candidates with the real engine gate."""
from __future__ import annotations
import io
import json
from pathlib import Path
import types
import unittest
import test_native_eod_capacity_rescue as gate


def main():
    path = Path(__file__).with_name('native_eod_capacity_rescue.py')
    source = path.read_text()
    variants = {
        'preunit_inventory': ('_, projected = post_units(observation, action, configuration)',
                              '_, projected = None, observation["private"]'),
        'off_not_identity': ('return skip("disabled")',
                             'return deepcopy(action), {"changed": False, "reason": "disabled"}'),
        'dead_eleventh_slot': ('len(market) >= 10', 'len(market) >= 12'),
        'one_excess_unit': ('overflow = shed_total + carried_total - 100',
                            'overflow = shed_total + carried_total - 99'),
        'mixed_cargo': ('len(positive) != 1', 'not positive'),
        'swallow_deadline': ('except (KeyError, IndexError, TypeError, ValueError, OverflowError):',
                             'except Exception:'),
        'legacy_neutral_veto': ('    from scheduler import post_units\n',
                                '    if any(row[0] in ("HARVEST", "COLLECT_FERTILIZER") for row in rows):\n'
                                '        return skip("legacy_neutral_only")\n'
                                '    from scheduler import post_units\n'),
    }
    reports = {}
    original = gate.rescue
    try:
        for name, (old, new) in variants.items():
            if source.count(old) != 1:
                raise ValueError('Non-unique mutation anchor: ' + name)
            module = types.ModuleType('eod_mutant_' + name)
            exec(compile(source.replace(old, new), str(path), 'exec'), module.__dict__)
            gate.rescue = module.apply_native_eod_capacity_rescue
            gate.COUNTS.clear()
            outcome = unittest.TextTestRunner(stream=io.StringIO()).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(gate.NativeEOD))
            reports[name] = {'rejected': not outcome.wasSuccessful(),
                             'tests_run': outcome.testsRun,
                             'failures': len(outcome.failures), 'errors': len(outcome.errors)}
    finally:
        gate.rescue = original
    print(json.dumps(reports, indent=2, sort_keys=True))
    if not all(r['rejected'] and r['tests_run'] == 19 for r in reports.values()):
        raise SystemExit('A broken variant survived or test setup did not execute')


if __name__ == '__main__':
    main()
