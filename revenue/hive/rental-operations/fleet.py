"""Fleetline: transactional single-unit rental and maintenance scheduling."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
HOUR = 3_600_000_000
DAY = 24 * HOUR
TIME = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)\Z')
CHECKS = {'handover': ('condition_recorded', 'accessories_counted', 'instructions_shared'),
          'return': ('condition_recorded', 'accessories_counted', 'issues_noted')}


class FleetError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise FleetError('Use finite, JSON-compatible values.') from exc


def text(value, label, maximum=4000, empty=False):
    if not isinstance(value, str) or '\x00' in value or len(value) > maximum:
        raise FleetError(f'{label} must be text of at most {maximum} characters.')
    value = value.strip()
    if not empty and not value:
        raise FleetError(f'{label} is required.')
    return value


def integer(value, label, minimum=0, maximum=1_000_000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise FleetError(f'{label} must be an integer from {minimum} to {maximum}.')
    return value


def timestamp(value):
    if not isinstance(value, str) or not TIME.fullmatch(value):
        raise FleetError('Times need an explicit offset or Z and at most six fractional digits.')
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise FleetError('Invalid date or time.') from exc
    delta = moment - EPOCH
    return delta.days * DAY + delta.seconds * 1_000_000 + delta.microseconds


def iso(microseconds):
    return (EPOCH + timedelta(microseconds=microseconds)).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def interval(start, end):
    first, last = timestamp(start), timestamp(end)
    if not 0 < last - first <= 366 * DAY:
        raise FleetError('The end must follow the start, with a maximum duration of 366 days.')
    return first, last


def cents(value, label='Rate'):
    if not isinstance(value, str) or not re.fullmatch(r'(?:0|[1-9]\d{0,6})(?:\.\d{1,2})?', value):
        raise FleetError(f'{label} must be a nonnegative dollar amount with at most two decimals.')
    whole, _, fraction = value.partition('.')
    return int(whole) * 100 + int((fraction + '00')[:2])


def money(value):
    return f'{value // 100}.{value % 100:02d}'


def quote(start, end, unit, rate, minimum):
    divisor = HOUR if unit == 'hour' else DAY
    units = max(minimum, (end - start + divisor - 1) // divisor)
    return units, units * rate


def commercial(subtotal, booking_fee, security_deposit):
    return subtotal + booking_fee + security_deposit


# Keep the original assets/reservations table shapes intact. Commercial terms
# live in sidecar tables so older backups, raw fixtures and previous binaries can
# still open the database and ignore the additive v2 data safely.
SCHEMA = '''
CREATE TABLE IF NOT EXISTS assets(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, notes TEXT NOT NULL,
 unit TEXT NOT NULL, rate_cents INTEGER NOT NULL, minimum_units INTEGER NOT NULL,
 revision INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS reservations(
 id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id), kind TEXT NOT NULL,
 status TEXT NOT NULL, start_us INTEGER NOT NULL, end_us INTEGER NOT NULL,
 customer TEXT NOT NULL, contact TEXT NOT NULL, notes TEXT NOT NULL,
 unit TEXT NOT NULL, rate_cents INTEGER NOT NULL, minimum_units INTEGER NOT NULL,
 billed_units INTEGER NOT NULL, total_cents INTEGER NOT NULL, revision INTEGER NOT NULL,
 handover TEXT NOT NULL, returned TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS reservation_intervals ON reservations(asset_id,start_us,end_us);
CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY, at TEXT NOT NULL, action TEXT NOT NULL,
 entity_id TEXT NOT NULL, before_json TEXT, after_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS asset_commercial_terms(
 asset_id TEXT PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
 booking_fee_cents INTEGER NOT NULL, security_deposit_cents INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS reservation_commercial_terms(
 reservation_id TEXT PRIMARY KEY REFERENCES reservations(id) ON DELETE CASCADE,
 booking_fee_cents INTEGER NOT NULL, security_deposit_cents INTEGER NOT NULL,
 amount_due_cents INTEGER NOT NULL);
'''


class Store:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db:
            db.executescript(SCHEMA)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    @staticmethod
    def row(db, table, identifier):
        # table is an internal constant, never supplied by HTTP callers.
        row = db.execute(f'SELECT * FROM {table} WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise FleetError('Record not found.', 404)
        return dict(row)

    @staticmethod
    def asset_terms(db, identifier):
        row = db.execute('SELECT booking_fee_cents,security_deposit_cents '
                         'FROM asset_commercial_terms WHERE asset_id=?', (identifier,)).fetchone()
        if row is None:
            return {'booking_fee_cents': 0, 'security_deposit_cents': 0}
        return dict(row)

    @staticmethod
    def reservation_terms(db, identifier, subtotal=0):
        row = db.execute('SELECT booking_fee_cents,security_deposit_cents,amount_due_cents '
                         'FROM reservation_commercial_terms WHERE reservation_id=?', (identifier,)).fetchone()
        if row is None:
            return {'booking_fee_cents': 0, 'security_deposit_cents': 0, 'amount_due_cents': subtotal}
        return dict(row)

    @classmethod
    def asset_row(cls, db, identifier):
        base = cls.row(db, 'assets', identifier)
        return dict(base, **cls.asset_terms(db, identifier))

    @classmethod
    def reservation_row(cls, db, identifier):
        base = cls.row(db, 'reservations', identifier)
        return dict(base, **cls.reservation_terms(db, identifier, base['total_cents']))

    @staticmethod
    def serialize(row):
        value = dict(row)
        value['rate'] = money(value['rate_cents'])
        value['booking_fee'] = money(value.get('booking_fee_cents', 0))
        value['security_deposit'] = money(value.get('security_deposit_cents', 0))
        if 'start_us' in value:
            subtotal = value['total_cents']
            due = value.get('amount_due_cents', subtotal)
            value.update(start=iso(value['start_us']), end=iso(value['end_us']),
                         handover=json.loads(value['handover']), returned=json.loads(value['returned']),
                         total=money(subtotal), rental_subtotal=money(subtotal), amount_due=money(due))
        return value

    @staticmethod
    def revision(old, expected):
        integer(expected, 'expected_revision')
        if expected != (old['revision'] if old else 0):
            raise FleetError('This record changed. Reopen the current revision before saving.', 409)

    @staticmethod
    def collision(db, asset, start, end, exclude=''):
        hit = db.execute('SELECT id,kind FROM reservations WHERE asset_id=? AND id<>? '
                         "AND status<>'cancelled' AND start_us<? AND end_us>? LIMIT 1",
                         (asset, exclude, end, start)).fetchone()
        if hit:
            raise FleetError(f'The interval overlaps a {hit["kind"]} ({hit["id"]}).', 409)

    @staticmethod
    def audit(db, action, entity, before, after):
        now = datetime.now(timezone.utc).isoformat()
        db.execute('INSERT INTO audit(at,action,entity_id,before_json,after_json) VALUES(?,?,?,?,?)',
                   (now, action, entity, canonical(before) if before else None, canonical(after)))

    def command(self, command, operation_id=None):
        if not isinstance(command, dict):
            raise FleetError('Command must be an object.')
        digest = hashlib.sha256(canonical(command).encode()).hexdigest()
        operation_id = text(str(uuid.uuid4()) if operation_id is None else operation_id, 'operation_id', 120)
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                prior = db.execute('SELECT digest,result FROM operations WHERE id=?', (operation_id,)).fetchone()
                if prior:
                    if prior['digest'] != digest:
                        raise FleetError('That operation ID belongs to a different request.', 409)
                    result = json.loads(prior['result'])
                else:
                    action = command.get('action')
                    if action == 'save_asset':
                        result = self.save_asset(db, command)
                    elif action == 'save_reservation':
                        result = self.save_reservation(db, command)
                    elif action == 'cancel':
                        result = self.cancel(db, command)
                    elif action == 'checklist':
                        result = self.checklist(db, command)
                    else:
                        raise FleetError('Unknown command.')
                    result = {'operation_id': operation_id, 'record': self.serialize(result)}
                    db.execute('INSERT INTO operations VALUES(?,?,?)', (operation_id, digest, canonical(result)))
                db.commit()
                return result
            except Exception:
                db.rollback()
                raise

    def save_asset(self, db, data):
        identifier = text(str(uuid.uuid4()) if data.get('id') is None else data['id'], 'id', 120)
        found = db.execute('SELECT * FROM assets WHERE id=?', (identifier,)).fetchone()
        old = self.asset_row(db, identifier) if found else None
        self.revision(old, data.get('expected_revision', 0))
        unit = data.get('unit')
        if unit not in ('hour', 'day'):
            raise FleetError('Pricing unit must be hour or day.')
        fee = old['booking_fee_cents'] if old and 'booking_fee' not in data else cents(data.get('booking_fee', '0.00'), 'Booking fee')
        deposit = old['security_deposit_cents'] if old and 'security_deposit' not in data else cents(data.get('security_deposit', '0.00'), 'Security deposit')
        value = dict(id=identifier, name=text(data.get('name'), 'Asset name', 120),
                     notes=text(data.get('notes', ''), 'Notes', empty=True), unit=unit,
                     rate_cents=cents(data.get('rate')),
                     minimum_units=integer(data.get('minimum_units', 1), 'Minimum units', 1, 366 * 24),
                     revision=(old['revision'] if old else 0) + 1)
        db.execute('INSERT INTO assets VALUES(:id,:name,:notes,:unit,:rate_cents,:minimum_units,:revision) '
                   'ON CONFLICT(id) DO UPDATE SET name=excluded.name,notes=excluded.notes,unit=excluded.unit,'
                   'rate_cents=excluded.rate_cents,minimum_units=excluded.minimum_units,revision=excluded.revision', value)
        db.execute('INSERT INTO asset_commercial_terms VALUES(?,?,?) ON CONFLICT(asset_id) DO UPDATE SET '
                   'booking_fee_cents=excluded.booking_fee_cents,security_deposit_cents=excluded.security_deposit_cents',
                   (identifier, fee, deposit))
        enriched = dict(value, booking_fee_cents=fee, security_deposit_cents=deposit)
        self.audit(db, 'save_asset', identifier, old, enriched)
        return enriched

    def save_reservation(self, db, data):
        identifier = text(str(uuid.uuid4()) if data.get('id') is None else data['id'], 'id', 120)
        found = db.execute('SELECT * FROM reservations WHERE id=?', (identifier,)).fetchone()
        old = self.reservation_row(db, identifier) if found else None
        self.revision(old, data.get('expected_revision', 0))
        if old and old['status'] != 'reserved':
            raise FleetError('Only a reserved booking or hold can be rescheduled.', 409)
        asset_id = text(data.get('asset_id'), 'Asset', 120)
        asset = self.asset_row(db, asset_id)
        kind = data.get('kind', 'booking')
        if kind not in ('booking', 'maintenance'):
            raise FleetError('Kind must be booking or maintenance.')
        if old and (old['asset_id'] != asset_id or old['kind'] != kind):
            raise FleetError('Retain the asset and kind when editing; cancel to replace them.', 409)
        start, end = interval(data.get('start'), data.get('end'))
        self.collision(db, asset_id, start, end, identifier)
        pricing = old or asset
        unit, rate, minimum = pricing['unit'], pricing['rate_cents'], pricing['minimum_units']
        if kind == 'booking':
            billed, subtotal = quote(start, end, unit, rate, minimum)
            fee = pricing['booking_fee_cents']
            deposit = pricing['security_deposit_cents']
            due = commercial(subtotal, fee, deposit)
        else:
            billed = subtotal = fee = deposit = due = 0
        value = dict(id=identifier, asset_id=asset_id, kind=kind, status='reserved',
                     start_us=start, end_us=end,
                     customer=text(data.get('customer', ''), 'Customer or hold title', 160),
                     contact=text(data.get('contact', ''), 'Contact', 254, empty=True),
                     notes=text(data.get('notes', ''), 'Notes', empty=True),
                     unit=unit, rate_cents=rate, minimum_units=minimum, billed_units=billed,
                     total_cents=subtotal, revision=(old['revision'] if old else 0) + 1,
                     handover=old['handover'] if old else '{}', returned=old['returned'] if old else '{}')
        db.execute('INSERT INTO reservations VALUES(:id,:asset_id,:kind,:status,:start_us,:end_us,'
                   ':customer,:contact,:notes,:unit,:rate_cents,:minimum_units,:billed_units,:total_cents,'
                   ':revision,:handover,:returned) ON CONFLICT(id) DO UPDATE SET start_us=excluded.start_us,'
                   'end_us=excluded.end_us,customer=excluded.customer,contact=excluded.contact,notes=excluded.notes,'
                   'billed_units=excluded.billed_units,total_cents=excluded.total_cents,revision=excluded.revision', value)
        db.execute('INSERT INTO reservation_commercial_terms VALUES(?,?,?,?) '
                   'ON CONFLICT(reservation_id) DO UPDATE SET amount_due_cents=excluded.amount_due_cents',
                   (identifier, fee, deposit, due))
        enriched = dict(value, booking_fee_cents=fee, security_deposit_cents=deposit, amount_due_cents=due)
        self.audit(db, 'save_reservation', identifier, old, enriched)
        return enriched

    def cancel(self, db, data):
        old = self.reservation_row(db, text(data.get('id'), 'Reservation', 120))
        self.revision(old, data.get('expected_revision'))
        if old['status'] in ('out', 'returned'):
            raise FleetError('Handed-over or returned bookings remain in the schedule.', 409)
        value = dict(old, status='cancelled', revision=old['revision'] + 1)
        db.execute('UPDATE reservations SET status=?,revision=? WHERE id=?',
                   ('cancelled', value['revision'], old['id']))
        self.audit(db, 'cancel', old['id'], old, value)
        return value

    def checklist(self, db, data):
        old = self.reservation_row(db, text(data.get('id'), 'Reservation', 120))
        self.revision(old, data.get('expected_revision'))
        stage, checks = data.get('stage'), data.get('checks')
        if not isinstance(stage, str) or stage not in CHECKS or not isinstance(checks, dict) or set(checks) != set(CHECKS[stage]):
            raise FleetError('Supply the named checklist items for handover or return.')
        if any(type(value) is not bool for value in checks.values()) or type(data.get('complete')) is not bool:
            raise FleetError('Checklist items and complete must be booleans.')
        if old['kind'] != 'booking' or old['status'] not in (('reserved', 'out') if stage == 'handover' else ('out', 'returned')):
            raise FleetError('The booking is not at this handover stage.', 409)
        completed = old['status'] == ('out' if stage == 'handover' else 'returned')
        if (data['complete'] or completed) and not all(checks.values()):
            raise FleetError('Complete all checklist items before completing the stage.')
        if stage == 'handover' and data['complete']:
            other = db.execute("SELECT id FROM reservations WHERE asset_id=? AND id<>? AND status='out' LIMIT 1",
                               (old['asset_id'], old['id'])).fetchone()
            if other:
                raise FleetError('This asset is still handed over on another booking. Record its return first.', 409)
        content = dict(checks=checks, notes=text(data.get('notes', ''), 'Checklist notes', empty=True))
        value = dict(old, revision=old['revision'] + 1)
        field = 'handover' if stage == 'handover' else 'returned'
        value[field] = canonical(content)
        if data['complete']:
            value['status'] = 'out' if stage == 'handover' else 'returned'
        db.execute(f'UPDATE reservations SET {field}=?,status=?,revision=? WHERE id=?',
                   (value[field], value['status'], value['revision'], old['id']))
        self.audit(db, 'checklist_' + stage, old['id'], old, value)
        return value

    def state(self):
        with closing(self.connect()) as db:
            db.execute('BEGIN')
            assets = [self.serialize(dict(dict(row), **self.asset_terms(db, row['id'])))
                      for row in db.execute('SELECT * FROM assets ORDER BY name,id')]
            reservations = [self.serialize(dict(dict(row), **self.reservation_terms(db, row['id'], row['total_cents'])))
                            for row in db.execute('SELECT * FROM reservations ORDER BY start_us,id')]
            return dict(version=2, currency='USD', assets=assets, reservations=reservations)

    def availability(self, start, end):
        first, last = interval(start, end)
        with closing(self.connect()) as db:
            db.execute('BEGIN')
            results = []
            for row in db.execute('SELECT * FROM assets ORDER BY name,id'):
                base = dict(row)
                terms = self.asset_terms(db, base['id'])
                conflicts = [dict(hit) for hit in db.execute('SELECT id,kind FROM reservations WHERE asset_id=? '
                             "AND status<>'cancelled' AND start_us<? AND end_us>?", (base['id'], last, first))]
                count, subtotal = quote(first, last, base['unit'], base['rate_cents'], base['minimum_units'])
                fee, deposit = terms['booking_fee_cents'], terms['security_deposit_cents']
                due = commercial(subtotal, fee, deposit)
                results.append(dict(self.serialize(dict(base, **terms)), available=not conflicts, conflicts=conflicts,
                                    billed_units=count, quote=money(subtotal), total_cents=subtotal,
                                    rental_subtotal=money(subtotal), booking_fee=money(fee),
                                    security_deposit=money(deposit), amount_due=money(due), amount_due_cents=due))
            return dict(start=iso(first), end=iso(last), assets=results)

    def message(self, identifier):
        with closing(self.connect()) as db:
            row = self.reservation_row(db, identifier)
            asset = self.row(db, 'assets', row['asset_id'])
        if row['kind'] != 'booking':
            raise FleetError('Maintenance holds do not have customer messages.')
        body = (f"Hello {row['customer']},\n\nYour {asset['name']} booking is {row['status']}.\n"
                f"Start (UTC): {iso(row['start_us'])}\nEnd (UTC): {iso(row['end_us'])}\n"
                f"Rental subtotal: USD {money(row['total_cents'])} "
                f"({row['billed_units']} {row['unit']} units).\n"
                f"Booking fee: USD {money(row['booking_fee_cents'])}.\n"
                f"Refundable security deposit: USD {money(row['security_deposit_cents'])}.\n"
                f"Amount due before taxes/delivery: USD {money(row['amount_due_cents'])}.\n"
                'Taxes, delivery and other unconfigured charges are not included. No payment is recorded.\n'
                'Please contact us to arrange pickup or changes.\n')
        return dict(to=row['contact'], subject=f"Rental booking — {asset['name']}", body=body,
                    status='draft_not_sent', reservation_revision=row['revision'])

    def export(self):
        with closing(self.connect()) as db:
            db.execute('BEGIN')
            assets = [dict(dict(row), **self.asset_terms(db, row['id'])) for row in db.execute('SELECT * FROM assets')]
            reservations = [dict(dict(row), **self.reservation_terms(db, row['id'], row['total_cents']))
                            for row in db.execute('SELECT * FROM reservations')]
            tables = {
                'assets': assets,
                'reservations': reservations,
                'audit': [dict(row) for row in db.execute('SELECT * FROM audit')],
                'operations': [dict(row) for row in db.execute('SELECT * FROM operations')],
            }
            return dict(format='fleetline-export-v1', exported_at=datetime.now(timezone.utc).isoformat(),
                        currency='USD', tables=tables)
