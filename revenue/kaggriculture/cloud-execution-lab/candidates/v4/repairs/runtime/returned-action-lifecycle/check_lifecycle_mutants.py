# SPDX-License-Identifier: Apache-2.0
"""Reject one semantic regression at a time, without changing source pin gates.

Mutations are made only to already validated output source in this process.
Only the named behavioral witness is run: source-identity tests cannot kill a
mutant vacuously. Inputs, Git refs and source files are never overwritten.
"""
from __future__ import annotations
import io
import json
import sys
import unittest
import test_return_lifecycle as tests


def replace_once(source, before, after):
    text = source.decode('utf-8')
    if text.count(before) != 1:
        raise ValueError('mutation anchor is not unique')
    result = text.replace(before, after, 1).encode('utf-8')
    compile(result, '<lifecycle-mutant>', 'exec')
    return result


CASES = [
    ('retain_prior_packet', 'integrated',
     '        self.last_packet = None\n        self.last_selected = self.last_seeded = None\n        cfg',
     '        self.last_selected = self.last_seeded = None\n        cfg',
     'ConsumerLifecycle', 'test_predecessor_retains_packet_after_new_call_fails'),
    ('remove_step_seat_check', 'runtime',
     "or binding[:2] != (int(obs['step']), int(obs['player']))):", 'or False):',
     'SnapshotConsumers', 'test_ordered_rejects_changed_step_seat_or_units'),
    ('remove_returned_units_check', 'runtime',
     "if (not isinstance(action, dict) or binding[2:] !=\n                    (action.get('farmer', ['PASS']), action.get('hands', []))):",
     'if not isinstance(action, dict):',
     'SnapshotConsumers', 'test_ordered_predecessor_accepts_wrong_returned_units'),
    ('alias_binding_to_caller', 'integrated',
     '*deepcopy(_snapshot_units(selected))', '*_snapshot_units(selected)',
     'ConsumerLifecycle', 'test_binding_is_deeply_detached'),
    ('wrong_ready_gate', 'runtime',
     '            if initialization_completed:\n                output = self._finish_production',
     '            if self.ready:\n                output = self._finish_production',
     'RuntimeLifecycle', 'test_ready_bypass_timeout_still_finalizes'),
    ('premature_initialization_latch', 'runtime',
     '        initialization_completed = False\n', '        initialization_completed = True\n',
     'RuntimeLifecycle', 'test_coldstart_cancellation_skips_uninitialized_finalizer'),
    ('history_without_returned_binding', 'runtime',
     'self.post = self._selected_snapshot(obs, output)', 'self.post = self._selected_snapshot(obs)',
     'RuntimeLifecycle', 'test_history_sees_final_selected_transform_units'),
    ('accept_seed_callback_unit_rewrite', 'integrated',
     "            if _snapshot_units(seeded) != _snapshot_units(selected):\n                raise ValueError('Seed queue selector changed selected unit rows')\n",
     '', 'ConsumerLifecycle', 'test_seed_only_callback_cannot_rewrite_units'),
    ('omit_early_ordered_invalidation', 'runtime',
     "            if self.features.consumer == 'ordered':\n                self.consumer.last_packet = None\n        self.diagnostics",
     '        self.diagnostics',
     'RuntimeLifecycle', 'test_ordered_packet_is_cleared_before_history_and_entry_prelude'),
    ('discard_every_current_packet', 'integrated',
     '            if _snapshot_units(out) != _snapshot_units(selected):\n',
     '            if True:\n',
     'ConsumerLifecycle', 'test_good_snapshot_matches_full_engine_matrix'),
]


def main():
    original_r = tests.repair_runtime
    original_i = tests.repair_integrated
    results = []
    for name, target, before, after, cls, method in CASES:
        function = original_r if target == 'runtime' else original_i
        def mutate(data, function=function, before=before, after=after):
            return replace_once(function(data), before, after)
        tests.repair_runtime = mutate if target == 'runtime' else original_r
        tests.repair_integrated = mutate if target == 'integrated' else original_i
        log = io.StringIO()
        result = unittest.TextTestRunner(stream=log).run(
            unittest.TestSuite([getattr(tests, cls)(method)]))
        rejected = result.testsRun == 1 and len(result.failures) == 1 and not result.errors
        results.append({'mutant': name, 'witness': cls+'.'+method,
                        'tests': result.testsRun, 'failures': len(result.failures),
                        'errors': len(result.errors), 'rejected': rejected})
        if not rejected:
            print(log.getvalue(), file=sys.stderr)
    tests.repair_runtime = original_r
    tests.repair_integrated = original_i
    report = {'schema': 'titan.return-lifecycle.mutations/v1',
              'optimized': not __debug__, 'cases': results,
              'all_rejected': all(row['rejected'] for row in results),
              'full_games': 0}
    print(json.dumps(report, sort_keys=True))
    return 0 if report['all_rejected'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
