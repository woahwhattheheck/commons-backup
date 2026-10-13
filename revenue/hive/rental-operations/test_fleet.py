"""Real SQLite transactions, concurrent writers, restart and HTTP regressions."""
from __future__ import annotations

import concurrent.futures
import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from urllib.parse import urlencode

from fleet import CHECKS, FleetError, Store, cents, interval, timestamp
from server import make_server

START = '2026-09-10T09:00:00-05:00'
END = '2026-09-11T09:00:00-05:00'


class FleetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'fleet.sqlite'
        self.store = Store(self.path)
        self.asset = self.asset_command()
        self.store.command(self.asset, 'asset-create')

    def tearDown(self):
        self.temp.cleanup()

    def asset_command(self, **changes):
        return dict(action='save_asset', id='asset-01', name='Example lift', unit='day',
                    rate='75.25', minimum_units=1, **changes)

    def reservation(self, **changes):
        result = dict(action='save_reservation', id='booking-01', asset_id='asset-01',
                      kind='booking', start=START, end=END, customer='Example customer',
                      contact='example@example.invalid', notes='Synthetic fixture only')
        result.update(changes)
        return result

    def book(self, **changes):
        return self.store.command(self.reservation(**changes))['record']

    def checked(self, row, stage='handover', complete=True, **changes):
        result = dict(action='checklist', id=row['id'], expected_revision=row['revision'], stage=stage,
                      checks={key: True for key in CHECKS[stage]}, complete=complete, notes='Example condition')
        result.update(changes)
        return self.store.command(result)['record']

    def test_create_price_and_utc(self):
        row = self.book()
        self.assertEqual((row['billed_units'], row['total'], row['revision']), (1, '75.25', 1))
        self.assertEqual(row['start'], '2026-09-10T14:00:00.000000Z')
        self.assertEqual(row['end'], '2026-09-11T14:00:00.000000Z')

    def test_exact_rate_cents_and_validation(self):
        self.assertEqual([cents(value) for value in ('0', '0.01', '12.3', '9999999.99')], [0, 1, 1230, 999999999])
        for value in ('-1', '1.001', 'NaN', '01', '1e2', True, 12.3, ''):
            with self.subTest(value=value), self.assertRaises(FleetError):
                cents(value)

    def test_one_microsecond_beyond_day_is_second_unit(self):
        row = self.book(end='2026-09-11T14:00:00.000001Z')
        self.assertEqual((row['billed_units'], row['total']), (2, '150.50'))

    def test_hourly_minimum_units(self):
        updated = dict(self.asset, expected_revision=1, unit='hour', rate='10.25', minimum_units=3)
        self.store.command(updated)
        row = self.book(end='2026-09-10T15:00:00Z')
        self.assertEqual((row['billed_units'], row['total']), (3, '30.75'))

    def test_overlap_rejected_and_no_partial_operation(self):
        self.book()
        before = self.store.export()
        with self.assertRaises(FleetError) as caught:
            self.book(id='overlap')
        self.assertEqual(caught.exception.status, 409)
        after = self.store.export()
        self.assertEqual(before['tables'], after['tables'])

    def test_all_overlap_shapes(self):
        self.book()
        for start, end in [('2026-09-09T14:00:00Z','2026-09-12T14:00:00Z'),
                           ('2026-09-10T15:00:00Z','2026-09-10T16:00:00Z'),
                           ('2026-09-09T14:00:00Z','2026-09-10T15:00:00Z'),
                           ('2026-09-11T13:00:00Z','2026-09-12T14:00:00Z')]:
            with self.subTest(start=start), self.assertRaises(FleetError):
                self.book(id='overlap', start=start, end=end)

    def test_adjacent_intervals_are_allowed(self):
        self.book()
        self.book(id='before', start='2026-09-09T14:00:00Z', end='2026-09-10T14:00:00Z')
        self.book(id='after', start='2026-09-11T14:00:00Z', end='2026-09-12T14:00:00Z')
        self.assertEqual(len(self.store.state()['reservations']), 3)

    def test_different_asset_same_interval(self):
        self.book()
        self.store.command(dict(self.asset, id='other-asset'))
        self.book(id='other', asset_id='other-asset')
        self.assertEqual(len(self.store.state()['reservations']), 2)

    def test_maintenance_removes_availability_and_has_zero_quote(self):
        hold = self.book(kind='maintenance', customer='Service hold')
        self.assertEqual((hold['total'], hold['billed_units']), ('0.00', 0))
        item = self.store.availability(START, END)['assets'][0]
        self.assertFalse(item['available'])
        self.assertEqual(item['conflicts'][0]['kind'], 'maintenance')
        with self.assertRaises(FleetError): self.book(id='blocked-booking')
        with self.assertRaises(FleetError): self.store.message(hold['id'])

    def test_maintenance_cannot_silently_replace_a_booking(self):
        self.book()
        with self.assertRaises(FleetError): self.book(id='hold', kind='maintenance')
        self.assertEqual(len(self.store.state()['reservations']), 1)

    def test_cancel_releases_interval_preserving_history(self):
        row = self.book()
        self.store.command(dict(action='cancel', id=row['id'], expected_revision=1))
        self.assertTrue(self.store.availability(START, END)['assets'][0]['available'])
        self.book(id='replacement')
        self.assertEqual(len(self.store.state()['reservations']), 2)
        self.assertEqual(len(self.store.export()['tables']['audit']), 4)

    def test_stale_edit_does_not_overwrite(self):
        self.book()
        self.book(expected_revision=1, customer='Updated customer')
        with self.assertRaises(FleetError): self.book(expected_revision=1, customer='Stale customer')
        self.assertEqual(self.store.state()['reservations'][0]['customer'], 'Updated customer')

    def test_reschedule_self_exclusion_and_conflict(self):
        row = self.book()
        row = self.book(expected_revision=1, end='2026-09-12T14:00:00Z')
        self.assertEqual(row['total'], '150.50')
        self.book(id='later', start='2026-09-12T14:00:00Z', end='2026-09-13T14:00:00Z')
        with self.assertRaises(FleetError): self.book(expected_revision=2, end='2026-09-13T14:00:00Z')
        self.assertEqual(self.store.state()['reservations'][0]['revision'], 2)

    def test_rate_change_preserves_existing_quote_snapshot(self):
        self.book()
        self.store.command(dict(self.asset, expected_revision=1, rate='100.00', unit='hour'))
        row = self.book(expected_revision=1, end='2026-09-12T14:00:00Z')
        self.assertEqual((row['rate'], row['unit'], row['total']), ('75.25', 'day', '150.50'))
        later = self.book(id='later', start='2026-09-12T14:00:00Z', end='2026-09-12T15:00:00Z')
        self.assertEqual((later['unit'], later['total']), ('hour', '100.00'))

    def test_kind_and_asset_immutable_on_reschedule(self):
        self.book()
        self.store.command(dict(self.asset, id='other'))
        for changes in ({'kind':'maintenance'}, {'asset_id':'other'}):
            with self.subTest(changes=changes), self.assertRaises(FleetError):
                self.book(expected_revision=1, **changes)

    def test_retry_is_identical_after_database_reopen(self):
        command = self.reservation()
        first = self.store.command(command, 'stable-request')
        later = Store(self.path).command(command, 'stable-request')
        self.assertEqual(first, later)
        self.assertEqual(len(self.store.export()['tables']['audit']), 2)

    def test_operation_id_cannot_change_content(self):
        self.store.command(self.reservation(), 'stable-request')
        with self.assertRaises(FleetError):
            self.store.command(self.reservation(customer='Changed'), 'stable-request')
        self.assertEqual(self.store.state()['reservations'][0]['customer'], 'Example customer')

    def test_two_concurrent_reservations_have_one_winner(self):
        barrier = threading.Barrier(2)
        def reserve(index):
            barrier.wait()
            try: return Store(self.path).command(self.reservation(id=f'concurrent-{index}'))['record']['id']
            except FleetError as exc: return exc.status
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            values = list(pool.map(reserve, [1, 2]))
        self.assertEqual(values.count(409), 1)
        self.assertEqual(len(self.store.state()['reservations']), 1)

    def test_concurrent_identical_retry_is_one_record(self):
        barrier = threading.Barrier(2)
        def reserve(_):
            barrier.wait()
            return Store(self.path).command(self.reservation(), 'concurrent-retry')
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            values = list(pool.map(reserve, [1, 2]))
        self.assertEqual(values[0], values[1])
        self.assertEqual(len(self.store.export()['tables']['audit']), 2)

    def test_offset_and_precision_rules(self):
        self.assertEqual(timestamp(START), timestamp('2026-09-10T14:00:00Z'))
        self.assertEqual(timestamp('2026-11-01T01:30:00-05:00') + 3_600_000_000, timestamp('2026-11-01T01:30:00-06:00'))
        for value in ('2026-09-10T09:00:00', '2026-02-30T09:00:00Z', '2026-09-10T09:00:00.0000001Z', 'NaN', None):
            with self.subTest(value=value), self.assertRaises(FleetError): timestamp(value)

    def test_bad_intervals(self):
        for end in (START, '2026-09-09T09:00:00-05:00', '2028-09-10T09:00:00-05:00'):
            with self.subTest(end=end), self.assertRaises(FleetError): interval(START, end)

    def test_invalid_types_and_missing_asset(self):
        for changes in ({'id':False}, {'customer':[]}, {'customer':' '}, {'asset_id':'missing'}, {'expected_revision':True}):
            with self.subTest(changes=changes), self.assertRaises(FleetError): self.book(**changes)
        for key in ('', False, 42):
            with self.subTest(key=key), self.assertRaises(FleetError): self.store.command(self.reservation(), key)

    def test_asset_revision_and_minimum_validation(self):
        for changes in ({'minimum_units':True}, {'minimum_units':0}, {'unit':'week'}, {'rate':'1.333'}):
            with self.subTest(changes=changes), self.assertRaises(FleetError):
                self.store.command(dict(self.asset, expected_revision=1, **changes))
        with self.assertRaises(FleetError): self.store.command(self.asset)

    def test_partial_handover_then_complete_then_return(self):
        row = self.book()
        partial = {key: False for key in CHECKS['handover']}
        row = self.checked(row, complete=False, checks=partial)
        self.assertEqual(row['status'], 'reserved')
        row = self.checked(row)
        self.assertEqual(row['status'], 'out')
        row = self.checked(row, 'return')
        self.assertEqual((row['status'], row['revision']), ('returned', 4))
        self.assertEqual(row['returned']['notes'], 'Example condition')
        self.assertFalse(self.store.availability(START, END)['assets'][0]['available'])

    def test_handover_transition_and_incomplete_items(self):
        row = self.book()
        with self.assertRaises(FleetError): self.checked(row, 'return')
        with self.assertRaises(FleetError): self.checked(row, checks={key: False for key in CHECKS['handover']})
        row = self.checked(row)
        with self.assertRaises(FleetError): self.checked(row, complete=False, checks={key: False for key in CHECKS['handover']})
        with self.assertRaises(FleetError): self.book(expected_revision=row['revision'])
        with self.assertRaises(FleetError): self.store.command(dict(action='cancel', id=row['id'], expected_revision=row['revision']))

    def test_one_physical_handover_per_asset_until_return(self):
        first = self.checked(self.book())
        second = self.book(id='second', start='2026-09-11T14:00:00Z', end='2026-09-12T14:00:00Z')
        with self.assertRaises(FleetError): self.checked(second)
        self.checked(first, 'return')
        self.assertEqual(self.checked(second)['status'], 'out')

    def test_hold_and_cancelled_booking_cannot_handover(self):
        row = self.book(kind='maintenance')
        with self.assertRaises(FleetError): self.checked(row)
        self.store.command(dict(action='cancel', id=row['id'], expected_revision=1))
        row = self.book(id='customer')
        row = self.store.command(dict(action='cancel', id=row['id'], expected_revision=1))['record']
        with self.assertRaises(FleetError): self.checked(row)

    def test_customer_draft_is_current_and_unsent(self):
        row = self.book()
        draft = self.store.message(row['id'])
        self.assertEqual(draft['status'], 'draft_not_sent')
        self.assertIn('75.25', draft['body'])
        self.assertEqual(draft['reservation_revision'], 1)
        self.assertIn('No payment is recorded', draft['body'])

    def test_export_is_consistent_and_preserves_unicode(self):
        row = self.book(customer='Café \u2600', notes='Line 1\nLine 2')
        data = self.store.export()
        self.assertEqual(set(data['tables']), {'assets','reservations','audit','operations'})
        self.assertEqual(data['tables']['reservations'][0]['customer'], row['customer'])
        self.assertEqual(json.loads(json.dumps(data))['tables'], data['tables'])
        self.assertEqual(Store(self.path).state()['reservations'][0]['notes'], 'Line 1\nLine 2')


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.store = Store(Path(cls.temp.name) / 'http.sqlite')
        cls.server = make_server(cls.store, 0)
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(); cls.temp.cleanup()

    def request(self, path, method='GET', data=None, headers=None):
        with closing(http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)) as connection:
            connection.request(method, path, body=data, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.headers), response.read()

    def command(self, command, operation_id):
        return self.request('/api/command', 'POST', json.dumps(dict(command=command, operation_id=operation_id)), {'Content-Type':'application/json'})

    def test_static_page_script_and_private_headers(self):
        for path, expected in [('/', b'Fleetline'), ('/app.js', b'/api/command')]:
            status, headers, body = self.request(path)
            self.assertEqual(status, 200)
            self.assertIn(expected, body)
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertIn("script-src 'self'", headers['Content-Security-Policy'])
            self.assertNotIn('Access-Control-Allow-Origin', headers)

    def test_real_http_booking_maintenance_and_export(self):
        asset = dict(action='save_asset', id='http-asset', name='Example generator', unit='hour', rate='12.50', minimum_units=2)
        self.assertEqual(self.command(asset, 'http-asset-op')[0], 200)
        booking = dict(action='save_reservation', id='http-booking', asset_id='http-asset', start=START, end=END, kind='booking', customer='Example user')
        status, _, body = self.command(booking, 'http-booking-op')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['record']['total'], '300.00')
        hold = dict(booking, id='http-hold', kind='maintenance')
        self.assertEqual(self.command(hold, 'http-hold-op')[0], 409)
        query = urlencode(dict(start=START, end=END))
        status, _, body = self.request('/api/availability?' + query)
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)['assets'][0]['available'])
        self.assertEqual(self.request('/api/message?id=http-booking')[0], 200)
        status, headers, body = self.request('/api/export')
        self.assertEqual(status, 200)
        self.assertIn('attachment;', headers['Content-Disposition'])
        self.assertEqual(len(json.loads(body)['tables']['reservations']), 1)

    def test_json_errors_have_no_mutation(self):
        before = self.store.export()['tables']
        for raw in ('{', '[]', '{"command":NaN}', '{"command":{},"command":{}}'):
            with self.subTest(raw=raw):
                self.assertEqual(self.request('/api/command', 'POST', raw, {'Content-Type':'application/json'})[0], 400)
        self.assertEqual(before, self.store.export()['tables'])

    def test_content_type_and_body_limits(self):
        self.assertEqual(self.request('/api/command', 'POST', '{}', {'Content-Type':'text/plain'})[0], 415)
        self.assertEqual(self.request('/api/command', 'POST', '{}', {'Content-Type':'application/json','Content-Length':'131073'})[0], 413)

    def test_unknown_route_does_not_serve_database(self):
        for path in ('/fleet.sqlite', '/../fleet.py', '/api/missing'):
            with self.subTest(path=path): self.assertEqual(self.request(path)[0], 404)

    def test_availability_requires_single_parameter_and_valid_time(self):
        for query in ('', 'start=x&end=y', 'start=x&start=y&end=z'):
            with self.subTest(query=query): self.assertEqual(self.request('/api/availability?' + query)[0], 400)


if __name__ == '__main__':
    unittest.main(verbosity=2)
