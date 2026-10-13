"""Checklist JSON-shape regressions using the real Fleetline SQLite store.

Run from this directory: python -m unittest -v test_checklist_stage_shapes
No HTTP requests, external services, or customer records are used.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fleet import CHECKS, FleetError, Store


class ChecklistStageShapes(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'fleet.sqlite3'
        self.store = Store(self.path)
        self.asset = self.store.command({
            'action': 'save_asset', 'id': 'synthetic-asset', 'name': 'Fixture trailer',
            'unit': 'hour', 'rate': '12.50', 'minimum_units': 1,
        }, 'setup-asset')['record']
        self.booking = self.store.command({
            'action': 'save_reservation', 'id': 'synthetic-booking',
            'asset_id': self.asset['id'], 'kind': 'booking',
            'customer': 'Synthetic fixture', 'start': '2026-09-10T10:00:00Z',
            'end': '2026-09-10T12:00:00Z',
        }, 'setup-booking')['record']

    def request(self, stage='handover', revision=1, complete=False):
        return {
            'action': 'checklist', 'id': self.booking['id'],
            'expected_revision': revision, 'stage': stage,
            'checks': dict.fromkeys(CHECKS['handover'], True), 'complete': complete,
        }

    def tables(self):
        # Separate connections check committed DB state, not an in-memory mock.
        return Store(self.path).export()['tables']

    def assert_rejected_without_writes(self, command, operation='shape-attempt', status=400):
        before = self.tables()
        command = json.loads(json.dumps(command))
        with self.assertRaises(FleetError) as caught:
            self.store.command(command, operation)
        self.assertEqual(caught.exception.status, status)
        self.assertEqual(before, self.tables())
        self.assertEqual(self.store.state(), Store(self.path).state())
        return caught.exception

    def test_rejected_stage_does_not_consume_operation_id(self):
        self.assert_rejected_without_writes(self.request([]), 'retry-stage')
        command = self.request(complete=True)
        result = self.store.command(command, 'retry-stage')
        self.assertEqual(result['record']['status'], 'out')
        self.assertEqual(result['record']['revision'], 2)
        before = self.tables()
        self.assertEqual(Store(self.path).command(command, 'retry-stage'), result)
        self.assertEqual(self.tables(), before)

    def test_valid_handover_and_return_persist(self):
        handed = self.store.command(self.request(complete=True), 'handover')['record']
        self.assertEqual((handed['status'], handed['revision']), ('out', 2))
        command = self.request('return', revision=2, complete=True)
        command['checks'] = dict.fromkeys(CHECKS['return'], True)
        returned = Store(self.path).command(command, 'return')['record']
        self.assertEqual((returned['status'], returned['revision']), ('returned', 3))
        self.assertEqual(Store(self.path).state()['reservations'][0], returned)
        self.assertEqual(returned['total_cents'], self.booking['total_cents'])
        self.assertEqual(returned['start'], self.booking['start'])
        self.assertEqual(returned['end'], self.booking['end'])

    def test_draft_checklist_keeps_reserved_state(self):
        command = self.request()
        command['checks']['instructions_shared'] = False
        result = self.store.command(command, 'draft')['record']
        self.assertEqual((result['status'], result['revision']), ('reserved', 2))
        self.assertFalse(result['handover']['checks']['instructions_shared'])
        self.assertEqual(Store(self.path).state()['reservations'][0], result)

    def test_revision_conflict_still_precedes_stage_validation(self):
        self.assert_rejected_without_writes(self.request([], revision=50), status=409)

    def test_missing_reservation_still_precedes_stage_validation(self):
        command = self.request({})
        command['id'] = 'nonexistent-fixture'
        self.assert_rejected_without_writes(command, status=404)

    def test_missing_stage_is_rejected(self):
        command = self.request()
        del command['stage']
        self.assert_rejected_without_writes(command)

    def test_return_before_handover_remains_conflict(self):
        command = self.request('return')
        command['checks'] = dict.fromkeys(CHECKS['return'], True)
        self.assert_rejected_without_writes(command, status=409)

    def test_missing_check_is_rejected(self):
        command = self.request()
        del command['checks']['instructions_shared']
        self.assert_rejected_without_writes(command)

    def test_additional_check_is_rejected(self):
        command = self.request()
        command['checks']['extra'] = True
        self.assert_rejected_without_writes(command)

    def test_nonboolean_check_is_rejected(self):
        command = self.request()
        command['checks']['instructions_shared'] = 1
        self.assert_rejected_without_writes(command)

    def test_nonboolean_completion_is_rejected(self):
        command = self.request()
        command['complete'] = 1
        self.assert_rejected_without_writes(command)


def stage_case(value):
    def test(self):
        exc = self.assert_rejected_without_writes(self.request(value))
        self.assertEqual(str(exc), 'Supply the named checklist items for handover or return.')
    return test


# Separate methods make the baseline regression count visible to unittest.
for name, value in (
    ('empty_array', []), ('string_array', ['handover']), ('nested_array', [[]]),
    ('empty_object', {}), ('stage_object', {'stage': 'handover'}),
    ('null', None), ('false', False), ('true', True), ('integer', 1),
    ('fraction', 1.5), ('empty_string', ''), ('unknown_string', 'inspect'),
    ('wrong_case', 'Handover'), ('whitespace', ' handover '),
):
    setattr(ChecklistStageShapes, 'test_stage_' + name, stage_case(value))


def checks_case(value):
    def test(self):
        command = self.request()
        command['checks'] = value
        self.assert_rejected_without_writes(command)
    return test


for name, value in (('array', []), ('null', None), ('text', 'done'), ('boolean', True)):
    setattr(ChecklistStageShapes, 'test_checks_' + name, checks_case(value))


if __name__ == '__main__':
    unittest.main()
