from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from fleet import FleetError, Store

START = '2026-09-10T09:00:00-05:00'
END = '2026-09-11T09:00:00-05:00'


class CommercialTermsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'fleet.sqlite'
        self.store = Store(self.path)
        self.store.command({
            'action': 'save_asset', 'id': 'asset-01', 'expected_revision': 0,
            'name': 'Example lift', 'unit': 'day', 'rate': '75.25', 'minimum_units': 1,
            'booking_fee': '10.00', 'security_deposit': '200.00', 'notes': 'Synthetic fixture'
        }, 'asset-create')

    def tearDown(self):
        self.temp.cleanup()

    def book(self, **changes):
        command = {
            'action': 'save_reservation', 'id': 'booking-01', 'expected_revision': 0,
            'asset_id': 'asset-01', 'kind': 'booking', 'start': START, 'end': END,
            'customer': 'Example customer', 'contact': 'example@example.invalid', 'notes': 'Synthetic fixture'
        }
        command.update(changes)
        return self.store.command(command)['record']

    def test_quote_components_and_amount_due(self):
        row = self.book()
        self.assertEqual(row['rental_subtotal'], '75.25')
        self.assertEqual(row['total'], '75.25')  # backward-compatible alias
        self.assertEqual(row['booking_fee'], '10.00')
        self.assertEqual(row['security_deposit'], '200.00')
        self.assertEqual(row['amount_due'], '285.25')
        self.assertEqual(row['amount_due_cents'], 28525)

    def test_existing_booking_keeps_commercial_snapshot_when_asset_changes(self):
        first = self.book()
        self.store.command({
            'action': 'save_asset', 'id': 'asset-01', 'expected_revision': 1,
            'name': 'Example lift', 'unit': 'day', 'rate': '90.00', 'minimum_units': 1,
            'booking_fee': '20.00', 'security_deposit': '300.00', 'notes': 'Updated terms'
        })
        revised = self.book(expected_revision=first['revision'], end='2026-09-12T14:00:00Z')
        self.assertEqual((revised['rate'], revised['rental_subtotal']), ('75.25', '150.50'))
        self.assertEqual((revised['booking_fee'], revised['security_deposit'], revised['amount_due']),
                         ('10.00', '200.00', '360.50'))
        later = self.book(id='booking-02', start='2026-09-12T14:00:00Z', end='2026-09-13T14:00:00Z')
        self.assertEqual((later['rate'], later['booking_fee'], later['security_deposit'], later['amount_due']),
                         ('90.00', '20.00', '300.00', '410.00'))

    def test_legacy_asset_update_without_new_fields_preserves_terms(self):
        self.store.command({
            'action': 'save_asset', 'id': 'asset-01', 'expected_revision': 1,
            'name': 'Example lift', 'unit': 'hour', 'rate': '25.00', 'minimum_units': 2,
            'notes': 'Legacy-shaped client update'
        })
        asset = self.store.state()['assets'][0]
        self.assertEqual((asset['booking_fee'], asset['security_deposit']), ('10.00', '200.00'))

    def test_maintenance_has_no_commercial_charge(self):
        row = self.book(kind='maintenance', customer='Service hold')
        self.assertEqual((row['rental_subtotal'], row['booking_fee'], row['security_deposit'], row['amount_due']),
                         ('0.00', '0.00', '0.00', '0.00'))

    def test_availability_exposes_complete_quote(self):
        quote = self.store.availability(START, END)['assets'][0]
        self.assertTrue(quote['available'])
        self.assertEqual((quote['quote'], quote['rental_subtotal'], quote['booking_fee'],
                          quote['security_deposit'], quote['amount_due']),
                         ('75.25', '75.25', '10.00', '200.00', '285.25'))

    def test_customer_draft_matches_snapshot_and_remains_unsent(self):
        row = self.book()
        draft = self.store.message(row['id'])
        self.assertEqual(draft['status'], 'draft_not_sent')
        for expected in ('Rental subtotal: USD 75.25', 'Booking fee: USD 10.00',
                         'Refundable security deposit: USD 200.00',
                         'Amount due before taxes/delivery: USD 285.25', 'No payment is recorded'):
            self.assertIn(expected, draft['body'])

    def test_commercial_amount_validation_is_fail_closed(self):
        for key, value in [('booking_fee', '-1'), ('booking_fee', '1.001'),
                           ('security_deposit', 'NaN'), ('security_deposit', 10)]:
            command = {
                'action': 'save_asset', 'id': 'asset-01', 'expected_revision': 1,
                'name': 'Example lift', 'unit': 'day', 'rate': '75.25', 'minimum_units': 1,
                'booking_fee': '10.00', 'security_deposit': '200.00', 'notes': ''
            }
            command[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(FleetError):
                self.store.command(command)
        asset = self.store.state()['assets'][0]
        self.assertEqual(asset['revision'], 1)

    def test_old_v1_database_migrates_in_place(self):
        legacy = Path(self.temp.name) / 'legacy.sqlite'
        with closing(sqlite3.connect(legacy)) as db:
            db.executescript('''
            CREATE TABLE assets(
             id TEXT PRIMARY KEY, name TEXT NOT NULL, notes TEXT NOT NULL,
             unit TEXT NOT NULL, rate_cents INTEGER NOT NULL, minimum_units INTEGER NOT NULL,
             revision INTEGER NOT NULL);
            CREATE TABLE reservations(
             id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id), kind TEXT NOT NULL,
             status TEXT NOT NULL, start_us INTEGER NOT NULL, end_us INTEGER NOT NULL,
             customer TEXT NOT NULL, contact TEXT NOT NULL, notes TEXT NOT NULL,
             unit TEXT NOT NULL, rate_cents INTEGER NOT NULL, minimum_units INTEGER NOT NULL,
             billed_units INTEGER NOT NULL, total_cents INTEGER NOT NULL, revision INTEGER NOT NULL,
             handover TEXT NOT NULL, returned TEXT NOT NULL);
            CREATE TABLE operations(id TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT NOT NULL);
            CREATE TABLE audit(seq INTEGER PRIMARY KEY, at TEXT NOT NULL, action TEXT NOT NULL,
             entity_id TEXT NOT NULL, before_json TEXT, after_json TEXT NOT NULL);
            INSERT INTO assets VALUES('a','Legacy asset','', 'day', 5000, 1, 1);
            INSERT INTO reservations VALUES('r','a','booking','reserved',0,86400000000,
             'Legacy customer','','','day',5000,1,1,5000,1,'{}','{}');
            ''')
        migrated = Store(legacy)
        state = migrated.state()
        self.assertEqual((state['assets'][0]['booking_fee'], state['assets'][0]['security_deposit']),
                         ('0.00', '0.00'))
        row = state['reservations'][0]
        self.assertEqual((row['rental_subtotal'], row['amount_due']), ('50.00', '50.00'))
        with closing(sqlite3.connect(legacy)) as db:
            asset_cols = [r[1] for r in db.execute('PRAGMA table_info(assets)')]
            reservation_cols = [r[1] for r in db.execute('PRAGMA table_info(reservations)')]
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(asset_cols, ['id','name','notes','unit','rate_cents','minimum_units','revision'])
        self.assertEqual(reservation_cols, ['id','asset_id','kind','status','start_us','end_us','customer',
                                            'contact','notes','unit','rate_cents','minimum_units','billed_units',
                                            'total_cents','revision','handover','returned'])
        self.assertTrue({'asset_commercial_terms', 'reservation_commercial_terms'} <= tables)

    def test_legacy_positional_asset_insert_still_works(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("INSERT INTO assets VALUES('asset-legacy','Legacy raw insert','','day',100,1,1)")
            db.commit()
        asset = next(item for item in Store(self.path).state()['assets'] if item['id'] == 'asset-legacy')
        self.assertEqual((asset['rate'], asset['booking_fee'], asset['security_deposit']),
                         ('1.00', '0.00', '0.00'))

    def test_sqlite_backup_preserves_sidecar_terms(self):
        self.book()
        copied = Path(self.temp.name) / 'copy.sqlite'
        with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(copied)) as target:
            source.backup(target)
        reopened = Store(copied)
        asset = reopened.state()['assets'][0]
        booking = reopened.state()['reservations'][0]
        self.assertEqual((asset['booking_fee'], asset['security_deposit']), ('10.00', '200.00'))
        self.assertEqual((booking['rental_subtotal'], booking['amount_due']), ('75.25', '285.25'))


if __name__ == '__main__':
    unittest.main()
