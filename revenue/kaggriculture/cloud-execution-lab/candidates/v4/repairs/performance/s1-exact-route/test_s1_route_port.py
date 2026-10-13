# SPDX-License-Identifier: Apache-2.0
"""Route-adapter tests use literal donor functions, not a full engine fixture."""
import ast
import copy
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import apply_s1_route as port

PREFIX = '''from __future__ import annotations
# sentinel: preserve all unrelated S1 cash and parent-ownership code
REACH = 6
TURNS_PER_DAY = 24
REPORT = {"collections": 0}
CASH_RESERVE = 1000.0

def untouched_owner_rule():
    return "preserve-peer-byte"

'''
MIDDLE = '\n\n# untouched between definitions\n\n'
SUFFIX = '\n\n# untouched source suffix\n'
SOURCE = PREFIX + port.OLD_COUNT + MIDDLE + port.OLD_COMMAND + SUFFIX


def namespace():
    # The parsing/target filters remain incumbent-owned; these test stubs expose
    # only their already-validated geometry surface to the two ported functions.
    ns = {}
    exec(compile(port.port_source(SOURCE), '<route-adapter-fixture>', 'exec'), ns)
    ns['_farm'] = lambda obs: (obs['step'], 0, obs['farm'], {}, {}) if obs else None
    ns['_targets'] = lambda farm: list(farm['targets'])
    def move(pos, target):
        if pos[0] != target[0]:
            return ['EAST' if pos[0] < target[0] else 'WEST']
        if pos[1] != target[1]:
            return ['SOUTH' if pos[1] < target[1] else 'NORTH']
        return None
    ns['_step_toward'] = move
    return ns


class RoutePortTests(unittest.TestCase):
    def test_preserves_every_nonroute_byte(self):
        result = port.port_source(SOURCE)
        self.assertEqual(result, PREFIX + port.NEW_COUNT + MIDDLE + port.NEW_COMMAND + SUFFIX)
        self.assertEqual(port.port_source(result), result)
        ast.parse(result)

    def test_independent_peer_cash_repair_is_preserved(self):
        source = SOURCE.replace('CASH_RESERVE = 1000.0', 'CASH_RESERVE = 1234.0')
        self.assertIn('CASH_RESERVE = 1234.0', port.port_source(source))

    def test_edited_route_function_is_not_overwritten(self):
        with self.assertRaises(ValueError):
            port.port_source(SOURCE.replace('count < REACH', 'count < REACH - 1'))

    def test_duplicate_missing_and_partial_routes_conflict(self):
        cases = (SOURCE + port.OLD_COUNT, SOURCE.replace(port.OLD_COMMAND, ''),
                 SOURCE.replace(port.OLD_COUNT, port.NEW_COUNT))
        for source in cases:
            with self.assertRaises(ValueError):
                port.port_source(source)

    def test_decorated_route_conflicts(self):
        with self.assertRaises(ValueError):
            port.port_source(SOURCE.replace('def _reachable_count', '@staticmethod\ndef _reachable_count'))

    def test_admission_and_executed_commands_agree_all_spawns(self):
        targets = {(4, 3), (2, 4), (2, 5)}
        moves = {'EAST': (1, 0), 'WEST': (-1, 0), 'NORTH': (0, -1), 'SOUTH': (0, 1)}
        for start in ((4, 4), (5, 4), (4, 5), (5, 5)):
            ns = namespace()
            predicted = ns['_reachable_count'](start, list(targets), 6)
            farm = {'hands': [list(start)], 'targets': set(targets)}
            state = SimpleNamespace(index=0)
            collected = 0
            for step in range(18, 24):
                obs = {'step': step, 'farm': farm}
                before = copy.deepcopy(obs)
                command = ns['_hand_command'](obs, state)
                self.assertEqual(obs, before)
                if command == ['COLLECT_FERTILIZER']:
                    site = tuple(farm['hands'][0])
                    self.assertIn(site, farm['targets'])
                    farm['targets'].remove(site)
                    collected += 1
                elif command[0] in moves:
                    dx, dy = moves[command[0]]
                    farm['hands'][0][0] += dx
                    farm['hands'][0][1] += dy
                else:
                    self.assertEqual(command, ['PASS'])
            self.assertEqual(predicted, 2)
            self.assertEqual(collected, predicted)
            self.assertEqual(ns['REPORT']['collections'], collected)

    def test_missing_surface_and_missing_hand_pass(self):
        ns = namespace()
        self.assertEqual(ns['_hand_command'](None, SimpleNamespace(index=0)), ['PASS'])
        obs = {'step': 18, 'farm': {'hands': [[4, 4]], 'targets': {(4, 3)}}}
        self.assertEqual(ns['_hand_command'](obs, SimpleNamespace(index=None)), ['PASS'])
        self.assertEqual(ns['_hand_command'](obs, SimpleNamespace(index=1)), ['PASS'])
        obs['farm']['targets'] = set()
        self.assertEqual(ns['_hand_command'](obs, SimpleNamespace(index=0)), ['PASS'])

    def test_cli_port_preserves_input_and_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source.py'
            output = Path(temp) / 'ported.py'
            source.write_text(SOURCE, encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(port.main([str(source), str(output)]), 0)
            self.assertEqual(source.read_text(), SOURCE)
            self.assertEqual(output.read_text(), port.port_source(SOURCE))
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                port.main([str(source), str(output)])
            self.assertEqual(output.read_text(), port.port_source(SOURCE))


if __name__ == '__main__':
    unittest.main()
