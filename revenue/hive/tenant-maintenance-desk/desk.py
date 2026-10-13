"""Tenant maintenance desk: durable requests, photos, scheduling, and status history.

No provider calls or notifications. Every command is one SQLite transaction.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

MAX_PHOTO = 2 * 1024 * 1024


class DeskError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def text(value, label, maximum=3000, optional=False):
    if not isinstance(value, str) or len(value) > maximum or (not optional and not value.strip()):
        raise DeskError(f'{label} must be text, {"0" if optional else "1"}–{maximum} characters.')
    if any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise DeskError(f'{label} contains unsupported control characters.')
    return value.strip()


def stamp(value):
    value = text(value, 'Appointment time', 64)
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError('timezone required')
        return dt.astimezone(timezone.utc).isoformat(timespec='microseconds')
    except (ValueError, OverflowError) as exc:
        raise DeskError('Appointment times must include a UTC offset (RFC 3339).') from exc


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def identifier():
    return uuid.uuid4().hex


SCHEMA = '''
CREATE TABLE IF NOT EXISTS properties (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, faq TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vendors (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, trade TEXT NOT NULL,
 available INTEGER NOT NULL CHECK(available IN (0,1))
);
CREATE TABLE IF NOT EXISTS requests (
 id TEXT PRIMARY KEY, property_id TEXT NOT NULL REFERENCES properties(id),
 unit TEXT NOT NULL, description TEXT NOT NULL,
 urgency TEXT NOT NULL CHECK(urgency IN ('routine','urgent','emergency')),
 status TEXT NOT NULL CHECK(status IN ('new','scheduled','needs_reschedule','closed')),
 version INTEGER NOT NULL, created_at TEXT NOT NULL, closure TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS photos (
 id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
 name TEXT NOT NULL, mime TEXT NOT NULL, data BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS appointments (
 id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
 vendor_id TEXT NOT NULL REFERENCES vendors(id), start TEXT NOT NULL, end TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('active','cancelled','completed')), reason TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_appointment
 ON appointments(request_id) WHERE state='active';
CREATE INDEX IF NOT EXISTS vendor_calendar ON appointments(vendor_id,state,start,end);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
 occurred_at TEXT NOT NULL, message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT NOT NULL);
'''


class Store:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(SCHEMA)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
        finally:
            db.close()

    def event(self, db, request_id, message):
        db.execute('INSERT INTO events(request_id,occurred_at,message) VALUES(?,?,?)',
                   (request_id, now(), message))

    def request(self, db, request_id):
        request_id = text(request_id, 'Request ID', 100)
        row = db.execute('SELECT * FROM requests WHERE id=?', (request_id,)).fetchone()
        if row is None:
            raise DeskError('Request not found.', 404)
        return dict(row)

    def editable(self, db, data):
        row = self.request(db, data.get('request_id'))
        version = data.get('version')
        if type(version) is not int or version < 1:
            raise DeskError('Supply the positive integer request version.')
        if row['version'] != version:
            raise DeskError('This request changed. Refresh before editing; your change was not applied.', 409)
        return row

    def detail(self, db, request_id):
        row = self.request(db, request_id)
        row['property_name'] = db.execute('SELECT name FROM properties WHERE id=?',
                                          (row['property_id'],)).fetchone()[0]
        row['photos'] = [dict(p) for p in db.execute(
            'SELECT id,name,mime,length(data) AS size FROM photos WHERE request_id=? ORDER BY rowid', (request_id,))]
        row['appointments'] = [dict(p) for p in db.execute(
            '''SELECT a.*,v.name AS vendor_name FROM appointments a JOIN vendors v ON v.id=a.vendor_id
               WHERE request_id=? ORDER BY a.rowid''', (request_id,))]
        row['events'] = [dict(e) for e in db.execute(
            'SELECT occurred_at,message FROM events WHERE request_id=? ORDER BY id', (request_id,))]
        row['appointment'] = next((a for a in row['appointments'] if a['state'] == 'active'), None)
        return row

    def state(self):
        with self.connection() as db:
            db.execute('BEGIN')
            return {
                'properties': [dict(r) for r in db.execute('SELECT * FROM properties ORDER BY name,id')],
                'vendors': [dict(r) for r in db.execute('SELECT * FROM vendors ORDER BY name,id')],
                'requests': [self.detail(db, r[0]) for r in db.execute('''SELECT id FROM requests
                    ORDER BY status='closed', CASE urgency WHEN 'emergency' THEN 0 WHEN 'urgent' THEN 1 ELSE 2 END,
                    created_at,id''')],
            }

    def photo(self, photo_id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM photos WHERE id=?', (photo_id,)).fetchone()
            if row is None:
                raise DeskError('Photo not found.', 404)
            return dict(row)

    def command(self, data, operation_id=None):
        if not isinstance(data, dict):
            raise DeskError('Command must be a JSON object.')
        kind = text(data.get('type'), 'Command type', 64)
        operation_id = identifier() if operation_id is None else text(operation_id, 'Operation ID', 100)
        try:
            encoded = json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False)
            digest = hashlib.sha256(encoded.encode('utf-8')).hexdigest()
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise DeskError('Command must contain finite, valid JSON values.') from exc
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                previous = db.execute('SELECT digest,result FROM operations WHERE id=?', (operation_id,)).fetchone()
                if previous:
                    if previous['digest'] != digest:
                        raise DeskError('Operation ID already belongs to a different command.', 409)
                    return json.loads(previous['result'])
                if kind == 'property':
                    rid = identifier()
                    db.execute('INSERT INTO properties VALUES(?,?,?)',
                               (rid, text(data.get('name'), 'Property name', 200), text(data.get('faq', ''), 'Property FAQ', 12000, True)))
                    result = {'id': rid}
                elif kind == 'faq':
                    rid = text(data.get('property_id'), 'Property ID', 100)
                    changed = db.execute('UPDATE properties SET faq=? WHERE id=?',
                                         (text(data.get('faq'), 'Property FAQ', 12000, True), rid))
                    if not changed.rowcount:
                        raise DeskError('Property not found.', 404)
                    result = {'id': rid}
                elif kind == 'vendor':
                    rid = identifier()
                    db.execute('INSERT INTO vendors VALUES(?,?,?,1)',
                               (rid, text(data.get('name'), 'Vendor name', 200), text(data.get('trade'), 'Trade', 100)))
                    result = {'id': rid}
                elif kind == 'vendor_availability':
                    result = self.availability(db, data)
                elif kind == 'request':
                    result = self.create_request(db, data)
                elif kind == 'schedule':
                    result = self.schedule(db, data)
                elif kind == 'close':
                    row = self.editable(db, data)
                    if row['status'] == 'closed':
                        raise DeskError('Request is already closed.', 409)
                    note = text(data.get('closure'), 'Closure note')
                    db.execute("UPDATE requests SET status='closed',closure=?,version=version+1 WHERE id=?", (note, row['id']))
                    db.execute("UPDATE appointments SET state='completed' WHERE request_id=? AND state='active'", (row['id'],))
                    self.event(db, row['id'], 'Closed: ' + note)
                    result = self.detail(db, row['id'])
                elif kind == 'reopen':
                    row = self.editable(db, data)
                    if row['status'] != 'closed':
                        raise DeskError('Only a closed request can be reopened.', 409)
                    note = text(data.get('reason'), 'Reopening reason')
                    db.execute("UPDATE requests SET status='new',closure='',version=version+1 WHERE id=?", (row['id'],))
                    self.event(db, row['id'], 'Reopened: ' + note)
                    result = self.detail(db, row['id'])
                else:
                    raise DeskError('Unknown command type.')
                db.execute('INSERT INTO operations VALUES(?,?,?)',
                           (operation_id, digest, json.dumps(result, ensure_ascii=False, allow_nan=False)))
                db.execute('COMMIT')
                return result
            except sqlite3.IntegrityError as exc:
                db.execute('ROLLBACK')
                raise DeskError('A referenced record is missing or the change conflicts with current data.', 409) from exc
            except Exception:
                db.execute('ROLLBACK')
                raise

    def create_request(self, db, data):
        urgency = data.get('urgency', 'routine')
        if not isinstance(urgency, str) or urgency not in ('routine', 'urgent', 'emergency'):
            raise DeskError('Urgency must be routine, urgent, or emergency.')
        pictures = data.get('photos', [])
        if not isinstance(pictures, list) or len(pictures) > 3:
            raise DeskError('Attach up to three photos, each no larger than 2 MiB.')
        rid = identifier()
        db.execute('INSERT INTO requests(id,property_id,unit,description,urgency,status,version,created_at) VALUES(?,?,?,?,?,\'new\',1,?)',
                   (rid, text(data.get('property_id'), 'Property ID', 100), text(data.get('unit'), 'Unit', 100),
                    text(data.get('description'), 'Description', 6000), urgency, now()))
        for picture in pictures:
            if not isinstance(picture, dict):
                raise DeskError('Each photo must be an object.')
            name = text(picture.get('name'), 'Photo name', 200)
            value = picture.get('base64')
            if not isinstance(value, str) or len(value) > 4 * ((MAX_PHOTO + 2) // 3):
                raise DeskError('Invalid photo encoding or size.')
            try:
                raw = base64.b64decode(value, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise DeskError('Photo must contain valid base64.') from exc
            if not 0 < len(raw) <= MAX_PHOTO:
                raise DeskError('Photo must be between 1 byte and 2 MiB.')
            mime = ('image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else
                    'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else
                    'image/webp' if raw.startswith(b'RIFF') and raw[8:12] == b'WEBP' else None)
            if mime is None:
                raise DeskError('Use a PNG, JPEG, or WebP photo.')
            db.execute('INSERT INTO photos VALUES(?,?,?,?,?)', (identifier(), rid, name, mime, raw))
        self.event(db, rid, 'Request received. Priority: ' + urgency + '.')
        return self.detail(db, rid)

    def availability(self, db, data):
        vendor_id = text(data.get('vendor_id'), 'Vendor ID', 100)
        available = data.get('available')
        if type(available) is not bool:
            raise DeskError('Available must be true or false.')
        vendor = db.execute('SELECT * FROM vendors WHERE id=?', (vendor_id,)).fetchone()
        if vendor is None:
            raise DeskError('Vendor not found.', 404)
        db.execute('UPDATE vendors SET available=? WHERE id=?', (int(available), vendor_id))
        affected = []
        if not available:
            for row in db.execute("SELECT request_id FROM appointments WHERE vendor_id=? AND state='active'", (vendor_id,)).fetchall():
                rid = row['request_id']
                db.execute("UPDATE appointments SET state='cancelled',reason='Vendor unavailable' WHERE request_id=? AND state='active'", (rid,))
                db.execute("UPDATE requests SET status='needs_reschedule',version=version+1 WHERE id=?", (rid,))
                self.event(db, rid, f'{vendor["name"]} is unavailable. Appointment cancelled; replacement needed.')
                affected.append(rid)
        return {'id': vendor_id, 'available': available, 'affected_requests': affected}

    def schedule(self, db, data):
        row = self.editable(db, data)
        if row['status'] == 'closed':
            raise DeskError('Reopen the request before scheduling.', 409)
        vendor_id = text(data.get('vendor_id'), 'Vendor ID', 100)
        vendor = db.execute('SELECT * FROM vendors WHERE id=?', (vendor_id,)).fetchone()
        if vendor is None:
            raise DeskError('Vendor not found.', 404)
        if not vendor['available']:
            raise DeskError('Vendor is unavailable. Choose a replacement.', 409)
        start, end = stamp(data.get('start')), stamp(data.get('end'))
        if start >= end:
            raise DeskError('Appointment end must be later than start.')
        conflict = db.execute("""SELECT id FROM appointments WHERE vendor_id=? AND state='active'
            AND request_id<>? AND start<? AND end>? LIMIT 1""", (vendor_id, row['id'], end, start)).fetchone()
        if conflict:
            raise DeskError('Vendor already has an overlapping appointment. Choose another time or vendor.', 409)
        reason = text(data.get('reason', 'Appointment replaced'), 'Change reason', 3000)
        db.execute("UPDATE appointments SET state='cancelled',reason=? WHERE request_id=? AND state='active'", (reason, row['id']))
        db.execute('INSERT INTO appointments VALUES(?,?,?,?,?,?,?)',
                   (identifier(), row['id'], vendor_id, start, end, 'active', reason))
        db.execute("UPDATE requests SET status='scheduled',version=version+1 WHERE id=?", (row['id'],))
        display_start = datetime.fromisoformat(start).strftime('%Y-%m-%d %H:%M UTC')
        display_end = datetime.fromisoformat(end).strftime('%Y-%m-%d %H:%M UTC')
        self.event(db, row['id'], f'Appointment with {vendor["name"]}: {display_start} to {display_end}. {reason}')
        return self.detail(db, row['id'])

    def seed_demo(self):
        prop = self.command({'type': 'property', 'name': 'DEMO · Maple Court',
                             'faq': 'All records in this demo are fictional.\nRoutine repairs: submit a request below.\nAccess: tell the manager which appointment windows work for you.\nImmediate danger: contact local emergency services; this desk is not emergency dispatch.'}, 'demo-property-v1')['id']
        self.command({'type': 'vendor', 'name': 'DEMO · Northstar Repairs', 'trade': 'General maintenance'}, 'demo-vendor-a-v1')
        self.command({'type': 'vendor', 'name': 'DEMO · Harbor Plumbing', 'trade': 'Plumbing'}, 'demo-vendor-b-v1')
        self.command({'type': 'request', 'property_id': prop, 'unit': 'DEMO 2B', 'description': 'Kitchen tap drips after closing.', 'urgency': 'routine'}, 'demo-request-v1')
