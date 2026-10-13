"""Reject rolled-over timezone offsets without changing Fleetline's valid workflow.

Run beside fleet.py: python -B -m unittest -v test_timestamp_offsets
Uses only synthetic data, temporary SQLite files and a loopback HTTP server.
"""
from __future__ import annotations

import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from contextlib import closing
from urllib.parse import urlencode

import fleet
from server import make_server


class TimestampTests(unittest.TestCase):
    def test_offset_minutes_never_roll_into_hours(self):
        accepted = []
        for sign in ('+', '-'):
            for hour in (0, 1, 5, 22):
                for minute in range(60, 100):
                    value = f'2026-09-20T10:00{sign}{hour:02}:{minute:02}'
                    try:
                        fleet.timestamp(value)
                    except fleet.FleetError as exc:
                        self.assertEqual(exc.status, 400)
                    else:
                        accepted.append(value)
        self.assertEqual(len(accepted), 0, f'Accepted {len(accepted)} invalid offsets: {accepted[:8]}')

    def test_every_valid_hour_minute_offset_is_exact(self):
        local_us = fleet.timestamp('2026-09-20T10:15:30.123456Z')
        for sign in ('+', '-'):
            for hour in range(24):
                for minute in range(60):
                    suffix = f'{sign}{hour:02}:{minute:02}'
                    offset_us = (hour * 60 + minute) * 60_000_000
                    expected = local_us - offset_us if sign == '+' else local_us + offset_us
                    self.assertEqual(fleet.timestamp('2026-09-20T10:15:30.123456' + suffix),
                                     expected, suffix)

    def test_zero_offsets_and_pre_epoch_microseconds(self):
        for suffix in ('Z', '+00:00', '-00:00'):
            self.assertEqual(fleet.timestamp('1970-01-01T00:00:00' + suffix), 0)
            self.assertEqual(fleet.timestamp('1969-12-31T23:59:59.999999' + suffix), -1)

    def test_existing_invalid_shapes_calendar_and_offsets_stay_invalid(self):
        for value in (None, [], {}, True, 0, '', '2026-09-20T10:00',
                      '2026-09-20 10:00Z', '2026-09-20T10:00+0530',
                      '2026-09-20T10:00+5:30', '2026-09-20T10:00+05:3',
                      '2026-09-20T10:00+24:00', '2026-09-20T10:00-24:00',
                      '2026-09-20T10:00+99:00', '2026-09-20T10:00Z\n',
                      '2026-09-20T10:00:00.1234567Z', '2026-02-30T10:00Z',
                      '2026-09-20T24:00Z', '2026-09-20T10:60Z'):
            with self.subTest(value=value), self.assertRaises(fleet.FleetError):
                fleet.timestamp(value)

    def test_utc_conversion_overflow_is_a_domain_error(self):
        for value in ('0001-01-01T00:00+23:59', '9999-12-31T23:59:59-23:59'):
            with self.assertRaises(fleet.FleetError) as caught:
                fleet.timestamp(value)
            self.assertEqual(caught.exception.status, 400)

    def test_fractional_interval_and_quote_keep_integer_precision(self):
        start, end = fleet.interval('2026-09-20T10:00:00.000000+05:45',
                                    '2026-09-20T11:00:00.000001+05:45')
        self.assertEqual(end - start, fleet.HOUR + 1)
        self.assertEqual(fleet.quote(start, end, 'hour', 1234, 1), (2, 2468))


class StoreFixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='fleet-offsets-')
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'fleet.sqlite'
        self.store = fleet.Store(self.path)
        self.store.command(dict(action='save_asset', id='asset', name='Synthetic drill',
                                unit='hour', rate='12.34'), 'asset-create')

    @staticmethod
    def booking(**changes):
        value = dict(action='save_reservation', id='booking', asset_id='asset',
                     customer='Synthetic example', contact='example@example.invalid',
                     start='2026-09-20T10:00Z', end='2026-09-20T11:00Z')
        value.update(changes)
        return value

    def snapshot(self):
        return self.store.export()['tables'], self.path.read_bytes()

    def rejected_without_changes(self, command, operation_id):
        before = self.snapshot()
        with self.assertRaises(fleet.FleetError) as caught:
            self.store.command(command, operation_id)
        self.assertEqual(caught.exception.status, 400)
        self.assertEqual(self.snapshot(), before)


class StoreOffsetTests(StoreFixture):
    def test_invalid_booking_start_preserves_all_tables_and_database_bytes(self):
        for index, offset in enumerate(('+00:60', '-00:60', '+05:99', '-05:99', '+22:99')):
            self.rejected_without_changes(
                self.booking(start='2026-09-20T10:00' + offset, end='2026-09-22T11:00Z'),
                f'bad-start-{index}')

    def test_invalid_booking_end_preserves_all_tables_and_database_bytes(self):
        for index, offset in enumerate(('+00:60', '-00:60', '+05:99', '-05:99', '+22:99')):
            self.rejected_without_changes(
                self.booking(start='2026-09-19T10:00Z', end='2026-09-20T11:00' + offset),
                f'bad-end-{index}')

    def test_invalid_maintenance_does_not_remove_availability(self):
        before = self.store.availability('2026-09-20T09:00Z', '2026-09-20T10:00Z')
        self.assertTrue(before['assets'][0]['available'])
        self.rejected_without_changes(
            self.booking(kind='maintenance', start='2026-09-20T10:00+00:60',
                         end='2026-09-20T11:00+00:60'), 'bad-hold')
        self.assertEqual(self.store.availability('2026-09-20T09:00Z', '2026-09-20T10:00Z'), before)

    def test_invalid_reschedule_preserves_revision_quote_and_history(self):
        self.store.command(self.booking(), 'initial-booking')
        self.rejected_without_changes(
            self.booking(expected_revision=1, start='2026-09-21T10:00+00:60',
                         end='2026-09-21T12:00Z'), 'invalid-edit')
        self.assertEqual(self.store.state()['reservations'][0]['revision'], 1)
        self.assertEqual(self.store.state()['reservations'][0]['total'], '12.34')

    def test_failed_command_leaves_operation_id_available_for_correction(self):
        self.rejected_without_changes(self.booking(start='2026-09-20T10:00+00:60'), 'retry')
        valid = self.booking(start='2026-09-20T10:00+00:00')
        result = self.store.command(valid, 'retry')
        before = self.snapshot()
        self.assertEqual(fleet.Store(self.path).command(valid, 'retry'), result)
        self.assertEqual(self.snapshot(), before)

    def test_valid_offsets_preserve_overlap_and_adjacent_interval_rules(self):
        self.store.command(self.booking(start='2026-09-20T10:00+05:30',
                                        end='2026-09-20T11:00+05:30'), 'first')
        before = self.snapshot()
        with self.assertRaises(fleet.FleetError) as caught:
            self.store.command(self.booking(id='hold', kind='maintenance',
                                            start='2026-09-20T04:45Z',
                                            end='2026-09-20T05:00Z'), 'overlap')
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(self.snapshot(), before)
        result = self.store.command(self.booking(id='adjacent', start='2026-09-20T05:30Z',
                                                end='2026-09-20T06:30Z'), 'adjacent')
        self.assertEqual(result['record']['total'], '12.34')
        availability = self.store.availability('2026-09-20T10:15+05:30', '2026-09-20T10:30+05:30')
        self.assertFalse(availability['assets'][0]['available'])

    def test_valid_reschedule_preserves_original_rate_snapshot(self):
        self.store.command(self.booking(), 'first')
        self.store.command(dict(action='save_asset', id='asset', expected_revision=1,
                                name='Synthetic drill', unit='hour', rate='99.00'), 'new-price')
        result = self.store.command(self.booking(expected_revision=1,
                                                start='2026-09-21T12:00+01:00',
                                                end='2026-09-21T14:00+01:00'), 'reschedule')
        self.assertEqual((result['record']['revision'], result['record']['rate'],
                          result['record']['total']), (2, '12.34', '24.68'))
        self.assertEqual(result['record']['start'], '2026-09-21T11:00:00.000000Z')

    def test_existing_operation_receipts_are_replayed_without_rewriting_history(self):
        # Model a pre-fix stored request digest using an otherwise valid record.
        # Old operation receipts are immutable; new malformed commands are refused.
        result = self.store.command(self.booking(start='2026-09-20T09:00Z',
                                                end='2026-09-20T10:00Z'), 'original')
        legacy = self.booking(start='2026-09-20T10:00+00:60', end='2026-09-20T11:00+00:60')
        digest = hashlib.sha256(fleet.canonical(legacy).encode()).hexdigest()
        legacy_result = dict(result, operation_id='legacy')
        with closing(self.store.connect()) as db:
            db.execute('INSERT INTO operations VALUES(?,?,?)',
                       ('legacy', digest, fleet.canonical(legacy_result)))
        before = self.snapshot()
        self.assertEqual(self.store.command(legacy, 'legacy'), legacy_result)
        self.assertEqual(self.snapshot(), before)
        self.rejected_without_changes(dict(legacy, id='new'), 'new-request')


class HTTPOffsetTests(StoreFixture):
    def setUp(self):
        super().setUp()
        server = make_server(self.store, port=0)
        thread = threading.Thread(target=server.serve_forever,
                                  kwargs={'poll_interval': 0.01}, daemon=True)
        def stop():
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.addCleanup(stop)
        thread.start()
        self.port = server.server_port

    def request(self, method, path, data=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            body = json.dumps(data).encode() if data is not None else None
            conn.request(method, path, body=body,
                         headers={'Content-Type': 'application/json'} if body is not None else {})
            response = conn.getresponse()
            content = response.read()
            self.assertEqual(int(response.getheader('Content-Length')), len(content))
            return response.status, json.loads(content)
        finally:
            conn.close()

    def post(self, command, operation_id):
        return self.request('POST', '/api/command', dict(command=command, operation_id=operation_id))

    def test_invalid_booking_returns_400_and_preserves_export(self):
        before = self.snapshot()
        status, body = self.post(self.booking(start='2026-09-20T10:00+00:60'), 'bad-http')
        self.assertEqual(status, 400)
        self.assertIn('error', body)
        self.assertEqual(self.snapshot(), before)
        status, exported = self.request('GET', '/api/export')
        self.assertEqual(status, 200)
        self.assertEqual(exported['tables'], before[0])

    def test_invalid_availability_returns_400_instead_of_shifted_quote(self):
        before = self.snapshot()
        for field in ('start', 'end'):
            for offset in ('+00:60', '-00:60', '+05:99', '-05:99'):
                params = dict(start='2026-09-19T10:00Z', end='2026-09-22T11:00Z')
                params[field] = '2026-09-20T10:00' + offset
                status, body = self.request('GET', '/api/availability?' + urlencode(params))
                self.assertEqual(status, 400, (field, offset, body))
                self.assertIn('error', body)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_edit_leaves_current_unsent_message_unchanged(self):
        self.assertEqual(self.post(self.booking(), 'book')[0], 200)
        before = self.request('GET', '/api/message?id=booking')
        status, _ = self.post(self.booking(expected_revision=1,
                                          start='2026-09-21T10:00-00:60',
                                          end='2026-09-21T12:00Z'), 'bad-edit')
        self.assertEqual(status, 400)
        self.assertEqual(self.request('GET', '/api/message?id=booking'), before)
        self.assertEqual(before[1]['status'], 'draft_not_sent')

    def test_corrected_http_retry_uses_original_operation_id(self):
        self.assertEqual(self.post(self.booking(start='2026-09-20T10:00+00:60'), 'retry')[0], 400)
        valid = self.booking()
        result = self.post(valid, 'retry')
        self.assertEqual(result[0], 200)
        before = self.snapshot()
        self.assertEqual(self.post(valid, 'retry'), result)
        self.assertEqual(self.snapshot(), before)

    def test_valid_http_offset_round_trip_and_maintenance_conflict(self):
        status, result = self.post(self.booking(start='2026-09-20T05:00-05:00',
                                               end='2026-09-20T06:00-05:00'), 'valid-offset')
        self.assertEqual(status, 200)
        self.assertEqual(result['record']['start'], '2026-09-20T10:00:00.000000Z')
        status, _ = self.post(self.booking(id='hold', kind='maintenance'), 'hold')
        self.assertEqual(status, 409)
        status, result = self.post(self.booking(id='adjacent', start='2026-09-20T11:00Z',
                                               end='2026-09-20T12:00Z'), 'adjacent')
        self.assertEqual(status, 200)
        self.assertEqual(result['record']['total'], '12.34')


if __name__ == '__main__':
    unittest.main()
