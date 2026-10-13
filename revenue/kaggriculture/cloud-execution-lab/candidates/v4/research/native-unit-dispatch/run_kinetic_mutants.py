# SPDX-License-Identifier: Apache-2.0
"""Run named behavioral fault controls; exceptions alone never count as kills."""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path
import sys
import unittest
import check_kinetic as checks
import compose_kinetic as composer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-root', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    checks.ROOT = args.native_root
    original = (args.native_root/'mechanics.py').read_text()
    good = composer.compose(original)
    selected = ['test_01_actor_inventory_movement_matrix', 'test_02_alias_replacement_not_in_place',
                'test_03_pass_grows_inventory_and_ghost_precedes_bad_opcode',
                'test_04_malformed_action_and_position_side_effects', 'test_05_complete_action_tail',
                'test_06_dynamic_helper_overrides', 'test_07_rebound_list_uses_original_setter',
                'test_08_mutable_moves_table_remains_live', 'test_09_mapping_access_order']
    mutations = [
        ('skip_pass_inventory', '    op = action[0]', '    op = action[0]\n    if op == "PASS": return'),
        ('skip_inventory_growth', '        while len(private["inventories"]) <= idx:',
         '        while False and len(private["inventories"]) <= idx:'),
        ('ghost_is_farmer', '            pos = farm["hands"][idx - 1] if idx - 1 < len(farm["hands"]) else None',
         '            pos = farm["hands"][idx - 1] if idx - 1 < len(farm["hands"]) else farm["farmer"]'),
        ('in_place_position_alias', '                farm["farmer"] = [nx, ny]',
         '                farm["farmer"][:] = [nx, ny]'),
        ('ignore_position_override', '    if _farmer_position is _KINETIC_POSITION:', '    if True:'),
        ('ignore_rebound_list', ' and list is _KINETIC_LIST:', ':'),
        ('clamp_negative_actor', '    op = action[0]', '    op = action[0]\n    idx = max(0, idx)'),
        ('move_outside_board', '        if not (0 <= nx < board_size and 0 <= ny < board_size):',
         '        if False and not (0 <= nx < board_size and 0 <= ny < board_size):'),
        ('inspect_op_before_ghost', '    op = action[0]', '    op = action[0]\n    op in FARMER_MOVES'),
        ('lose_fertilizer_action', '    if op == "FERTILIZE":', '    if op == "NEVER_FERTILIZE":'),
    ]
    reports = []
    for name, text in [('control', good)] + [(name, good.replace(before, after, 1))
                                          for name, before, after in mutations]:
        checks.OVERRIDE = text
        suite = unittest.TestSuite(checks.KineticChecks(test) for test in selected)
        result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=2).run(suite)
        row = {'name': name, 'tests': result.testsRun, 'failures': len(result.failures),
               'errors': len(result.errors), 'skips': len(result.skipped),
               'assertion_witnesses': [t.id().rsplit('.', 1)[-1] for t, _ in result.failures]}
        reports.append(row)
        print(json.dumps(row, sort_keys=True), flush=True)
    success = (reports[0]['failures'] == reports[0]['errors'] == reports[0]['skips'] == 0
               and all(r['failures'] > 0 and r['errors'] == r['skips'] == 0 for r in reports[1:]))
    report = {'mode': 'optimized' if sys.flags.optimize else 'normal', 'success': success,
              'controls': reports, 'scope': 'behavioral unit-kernel mutants, not input-authentication failures'}
    args.report.write_text(json.dumps(report, sort_keys=True, indent=2)+'\n')
    return 0 if success else 1

if __name__ == '__main__':
    raise SystemExit(main())
