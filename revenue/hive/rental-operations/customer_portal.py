"""Customer request rail for Fleetline. Requests are pending intents, not holds."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import uuid
from contextlib import closing
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fleet import FleetError, Store, canonical, commercial, interval, iso, money, quote, text

ROOT = Path(__file__).resolve().parent
MAX_BODY = 64 * 1024
TOKEN = re.compile(r"[A-Za-z0-9_-]{32,160}\Z")
SCHEMA = """
CREATE TABLE IF NOT EXISTS customer_requests(
 id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, status TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, asset_id TEXT NOT NULL,
 start_us INTEGER NOT NULL, end_us INTEGER NOT NULL, customer TEXT NOT NULL,
 contact TEXT NOT NULL, notes TEXT NOT NULL, unit TEXT NOT NULL,
 rate_cents INTEGER NOT NULL, minimum_units INTEGER NOT NULL,
 billed_units INTEGER NOT NULL, rental_subtotal_cents INTEGER NOT NULL,
 booking_fee_cents INTEGER NOT NULL, security_deposit_cents INTEGER NOT NULL,
 amount_due_cents INTEGER NOT NULL, reservation_id TEXT, decision_note TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS customer_requests_status
 ON customer_requests(status,created_at,id);
CREATE TABLE IF NOT EXISTS customer_request_operations(
 request_key TEXT PRIMARY KEY, digest TEXT NOT NULL, result_json TEXT NOT NULL);
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _token_hash(value):
    if not isinstance(value, str) or not TOKEN.fullmatch(value):
        raise FleetError('status_token must be 32-160 URL-safe characters.')
    return hashlib.sha256(value.encode()).hexdigest()


def _strict_json(raw):
    def constant(_):
        raise ValueError('Non-finite number')
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError('Duplicate JSON key')
            out[key] = value
        return out
    return json.loads(raw, parse_constant=constant, object_pairs_hook=pairs)


class CustomerPortal:
    def __init__(self, path):
        self.core = Store(path)
        self.path = self.core.path
        with closing(self.core.connect()) as db:
            db.executescript(SCHEMA)

    def connect(self):
        return self.core.connect()

    @staticmethod
    def _row(db, identifier):
        row = db.execute('SELECT * FROM customer_requests WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise FleetError('Request not found.', 404)
        return dict(row)

    @staticmethod
    def _serialize(row, public=False):
        status = row['status']
        out = {
            'id': row['id'], 'status': status, 'created_at': row['created_at'],
            'updated_at': row['updated_at'], 'asset_id': row['asset_id'],
            'start': iso(row['start_us']), 'end': iso(row['end_us']),
            'customer': row['customer'], 'contact': row['contact'], 'notes': row['notes'],
            'unit': row['unit'], 'rate': money(row['rate_cents']),
            'minimum_units': row['minimum_units'], 'billed_units': row['billed_units'],
            'rental_subtotal': money(row['rental_subtotal_cents']),
            'booking_fee': money(row['booking_fee_cents']),
            'security_deposit': money(row['security_deposit_cents']),
            'amount_due': money(row['amount_due_cents']),
            'reservation_id': row['reservation_id'], 'decision_note': row['decision_note'],
            'reservation_created': status == 'accepted',
        }
        if public and status != 'accepted':
            out['reservation_id'] = None
        return out

    def catalog(self, start, end):
        source = self.core.availability(start, end)
        fields = ('id', 'name', 'available', 'unit', 'rate', 'minimum_units', 'billed_units',
                  'rental_subtotal', 'booking_fee', 'security_deposit', 'amount_due')
        assets = [{key: item[key] for key in fields} for item in source['assets']]
        return {
            'start': source['start'], 'end': source['end'], 'currency': 'USD', 'assets': assets,
            'reservation_created': False,
            'notice': 'Availability and quote are current estimates only. Submitting a request does not hold inventory.',
        }

    @staticmethod
    def _conflict(db, asset_id, start_us, end_us):
        return db.execute(
            "SELECT 1 FROM reservations WHERE asset_id=? AND status<>'cancelled' "
            'AND start_us<? AND end_us>? LIMIT 1', (asset_id, end_us, start_us)
        ).fetchone() is not None

    @staticmethod
    def _submission(data):
        if not isinstance(data, dict):
            raise FleetError('Request must be an object.')
        allowed = {'request_key', 'status_token', 'asset_id', 'start', 'end', 'customer', 'contact', 'notes'}
        if set(data) - allowed:
            raise FleetError('Unsupported request field.')
        request_key = text(data.get('request_key'), 'request_key', 120)
        first, last = interval(data.get('start'), data.get('end'))
        return request_key, {
            'token_hash': _token_hash(data.get('status_token')),
            'asset_id': text(data.get('asset_id'), 'Asset', 120),
            'start_us': first, 'end_us': last,
            'customer': text(data.get('customer'), 'Customer', 160),
            'contact': text(data.get('contact'), 'Contact', 254),
            'notes': text(data.get('notes', ''), 'Notes', 2000, empty=True),
        }

    def submit(self, data):
        request_key, normalized = self._submission(data)
        digest = hashlib.sha256(canonical(normalized).encode()).hexdigest()
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                prior = db.execute(
                    'SELECT digest,result_json FROM customer_request_operations WHERE request_key=?',
                    (request_key,),
                ).fetchone()
                if prior:
                    if prior['digest'] != digest:
                        raise FleetError('That request_key belongs to a different request.', 409)
                    db.commit()
                    return json.loads(prior['result_json'])
                asset = self.core.asset_row(db, normalized['asset_id'])
                if self._conflict(db, normalized['asset_id'], normalized['start_us'], normalized['end_us']):
                    raise FleetError('That time is no longer available.', 409)
                billed, subtotal = quote(normalized['start_us'], normalized['end_us'], asset['unit'],
                                         asset['rate_cents'], asset['minimum_units'])
                fee, deposit = asset['booking_fee_cents'], asset['security_deposit_cents']
                stamp = _now()
                row = dict(
                    id=str(uuid.uuid4()), token_hash=normalized['token_hash'], status='pending',
                    created_at=stamp, updated_at=stamp, asset_id=normalized['asset_id'],
                    start_us=normalized['start_us'], end_us=normalized['end_us'],
                    customer=normalized['customer'], contact=normalized['contact'], notes=normalized['notes'],
                    unit=asset['unit'], rate_cents=asset['rate_cents'], minimum_units=asset['minimum_units'],
                    billed_units=billed, rental_subtotal_cents=subtotal, booking_fee_cents=fee,
                    security_deposit_cents=deposit, amount_due_cents=commercial(subtotal, fee, deposit),
                    reservation_id=None, decision_note='',
                )
                db.execute(
                    'INSERT INTO customer_requests VALUES('
                    ':id,:token_hash,:status,:created_at,:updated_at,:asset_id,:start_us,:end_us,'
                    ':customer,:contact,:notes,:unit,:rate_cents,:minimum_units,:billed_units,'
                    ':rental_subtotal_cents,:booking_fee_cents,:security_deposit_cents,:amount_due_cents,'
                    ':reservation_id,:decision_note)', row,
                )
                result = self._serialize(row, public=True)
                result['notice'] = 'Request received. Inventory is not held until the operator accepts it.'
                db.execute('INSERT INTO customer_request_operations VALUES(?,?,?)',
                           (request_key, digest, canonical(result)))
                db.commit()
                return result
            except Exception:
                db.rollback()
                raise

    def status(self, identifier, status_token):
        identifier, digest = text(identifier, 'Request', 120), _token_hash(status_token)
        with closing(self.connect()) as db:
            row = db.execute('SELECT * FROM customer_requests WHERE id=?', (identifier,)).fetchone()
            if row is None or not hmac.compare_digest(row['token_hash'], digest):
                raise FleetError('Request not found.', 404)
            return self._serialize(dict(row), public=True)

    def pending(self):
        with closing(self.connect()) as db:
            rows = db.execute("SELECT * FROM customer_requests WHERE status='pending' ORDER BY created_at,id")
            return [self._serialize(dict(row)) for row in rows]

    def approve(self, identifier):
        """Revalidate quote and reserve atomically under one SQLite write lock."""
        identifier = text(identifier, 'Request', 120)
        operation_id, reservation_id = 'customer-request-approve-' + identifier, 'customer-request-' + identifier
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row = self._row(db, identifier)
                if row['status'] == 'rejected':
                    raise FleetError('A rejected request cannot be approved.', 409)
                if row['status'] == 'accepted':
                    db.commit()
                    return self._serialize(row)
                if row['status'] != 'pending':
                    raise FleetError('Request is not pending.', 409)
                asset = self.core.asset_row(db, row['asset_id'])
                if self._conflict(db, row['asset_id'], row['start_us'], row['end_us']):
                    raise FleetError('Approval blocked because the requested interval is no longer available.', 409)
                billed, subtotal = quote(row['start_us'], row['end_us'], asset['unit'],
                                         asset['rate_cents'], asset['minimum_units'])
                current = (asset['unit'], asset['rate_cents'], asset['minimum_units'], billed, subtotal,
                           asset['booking_fee_cents'], asset['security_deposit_cents'],
                           commercial(subtotal, asset['booking_fee_cents'], asset['security_deposit_cents']))
                quoted = (row['unit'], row['rate_cents'], row['minimum_units'], row['billed_units'],
                          row['rental_subtotal_cents'], row['booking_fee_cents'],
                          row['security_deposit_cents'], row['amount_due_cents'])
                if current != quoted:
                    raise FleetError('Approval blocked because the quoted commercial terms changed.', 409)
                command = {
                    'action': 'save_reservation', 'id': reservation_id, 'expected_revision': 0,
                    'asset_id': row['asset_id'], 'kind': 'booking', 'start': iso(row['start_us']),
                    'end': iso(row['end_us']), 'customer': row['customer'], 'contact': row['contact'],
                    'notes': row['notes'],
                }
                digest = hashlib.sha256(canonical(command).encode()).hexdigest()
                prior = db.execute('SELECT digest,result FROM operations WHERE id=?', (operation_id,)).fetchone()
                if prior:
                    if prior['digest'] != digest:
                        raise FleetError('The approval operation ID belongs to a different request.', 409)
                    result = json.loads(prior['result'])
                    if result.get('record', {}).get('id') != reservation_id:
                        raise FleetError('Approval operation receipt does not match this request.', 409)
                else:
                    record = self.core.save_reservation(db, command)
                    result = {'operation_id': operation_id, 'record': self.core.serialize(record)}
                    db.execute('INSERT INTO operations VALUES(?,?,?)', (operation_id, digest, canonical(result)))
                stamp = _now()
                db.execute(
                    "UPDATE customer_requests SET status='accepted',updated_at=?,reservation_id=?,decision_note=? "
                    "WHERE id=? AND status='pending'", (stamp, reservation_id, 'Accepted by operator.', identifier),
                )
                final = self._row(db, identifier)
                if final['status'] != 'accepted' or final['reservation_id'] != reservation_id:
                    raise FleetError('Approval could not be finalized.', 409)
                db.commit()
                return self._serialize(final)
            except Exception:
                db.rollback()
                raise

    def reject(self, identifier, note='Declined by operator.'):
        identifier, note = text(identifier, 'Request', 120), text(note, 'Decision note', 500)
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row = self._row(db, identifier)
                if row['status'] == 'accepted':
                    raise FleetError('An accepted request is already a reservation.', 409)
                if row['status'] == 'pending':
                    db.execute("UPDATE customer_requests SET status='rejected',updated_at=?,decision_note=? WHERE id=?",
                               (_now(), note, identifier))
                    row = self._row(db, identifier)
                db.commit()
                return self._serialize(row)
            except Exception:
                db.rollback()
                raise


def make_server(portal, port=8087):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _fmt, *_args):
            pass

        def send(self, status, body, content_type='application/json; charset=utf-8'):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            for key, value in (
                ('Content-Type', content_type), ('Content-Length', str(len(body))), ('Cache-Control', 'no-store'),
                ('X-Content-Type-Options', 'nosniff'), ('Referrer-Policy', 'no-referrer'),
                ('Cross-Origin-Resource-Policy', 'same-origin'),
                ('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; "
                 "connect-src 'self'; img-src 'self' data:; base-uri 'none'; object-src 'none'; "
                 "frame-ancestors 'none'; form-action 'self'"),
            ):
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def run(self, action):
            try:
                action()
            except FleetError as exc:
                self.send(exc.status, {'error': str(exc)})
            except (UnicodeError, ValueError, TypeError, KeyError, RecursionError):
                self.send(400, {'error': 'Malformed request.'})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.send(500, {'error': 'The request could not be completed.'})

        def do_GET(self):
            self.run(self.get)

        def get(self):
            url = urlsplit(self.path)
            if url.path in ('/', '/customer_portal.html', '/customer_portal.js'):
                name = 'customer_portal.html' if url.path == '/' else url.path[1:]
                target = ROOT / name
                self.send(200, target.read_bytes(),
                          ('text/html' if target.suffix == '.html' else 'text/javascript') + '; charset=utf-8')
                return
            if url.path == '/api/catalog':
                params = parse_qs(url.query)
                if len(params.get('start', [])) != 1 or len(params.get('end', [])) != 1:
                    raise FleetError('Supply exactly one start and end.')
                self.send(200, portal.catalog(params['start'][0], params['end'][0]))
                return
            raise FleetError('Not found.', 404)

        def _body(self):
            if self.headers.get_content_type() != 'application/json':
                raise FleetError('Use application/json.', 415)
            if self.headers.get('Transfer-Encoding'):
                raise FleetError('Supply Content-Length instead of chunked encoding.')
            lengths = self.headers.get_all('Content-Length', [])
            if len(lengths) != 1:
                raise FleetError('Supply one Content-Length header.', 411)
            try:
                length = int(lengths[0])
            except ValueError as exc:
                raise FleetError('Invalid Content-Length.') from exc
            if not 0 < length <= MAX_BODY:
                raise FleetError('Request body must be between 1 and 65536 bytes.', 413)
            self.connection.settimeout(10)
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise FleetError('Incomplete request body.')
            return _strict_json(raw.decode())

        def do_POST(self):
            self.run(self.post)

        def post(self):
            origin, host = self.headers.get('Origin'), self.headers.get('Host', '')
            if origin and origin != f'http://{host}':
                raise FleetError('Cross-origin requests are not accepted.', 403)
            path, data = urlsplit(self.path).path, self._body()
            if path == '/api/request':
                self.send(202, portal.submit(data))
            elif path == '/api/status':
                if not isinstance(data, dict) or set(data) != {'id', 'status_token'}:
                    raise FleetError('Supply id and status_token only.')
                self.send(200, portal.status(data['id'], data['status_token']))
            else:
                raise FleetError('Not found.', 404)

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description='Fleetline customer request portal (loopback only).')
    parser.add_argument('--db', type=Path, default=Path.home() / '.fleetline' / 'fleet.sqlite')
    sub = parser.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve'); serve.add_argument('--port', type=int, default=8087)
    approve = sub.add_parser('approve'); approve.add_argument('request_id')
    reject = sub.add_parser('reject'); reject.add_argument('request_id'); reject.add_argument('--note', default='Declined by operator.')
    sub.add_parser('pending')
    args = parser.parse_args(argv)
    portal = CustomerPortal(args.db)
    if args.command == 'approve':
        print(json.dumps(portal.approve(args.request_id), ensure_ascii=False, sort_keys=True)); return 0
    if args.command == 'reject':
        print(json.dumps(portal.reject(args.request_id, args.note), ensure_ascii=False, sort_keys=True)); return 0
    if args.command == 'pending':
        print(json.dumps(portal.pending(), ensure_ascii=False, sort_keys=True)); return 0
    with make_server(portal, args.port) as server:
        print(f'Fleetline customer requests: http://127.0.0.1:{server.server_port} — requests are pending, not reservations.')
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
