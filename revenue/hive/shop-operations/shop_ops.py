#!/usr/bin/env python3
"""Shop Operations Desk: transactional local merchant inventory and handoff."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

MAX_UNITS = 1_000_000_000


class DomainError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def text(value, name, optional=False):
    if not isinstance(value, str) or (not optional and not value.strip()):
        raise DomainError(f'{name} must be a nonempty string')
    try:
        value.encode('utf-8')
    except UnicodeError as exc:
        raise DomainError(f'{name} must be valid Unicode') from exc
    return value.strip()


def integer(value, name, minimum=0):
    if type(value) is not int or not minimum <= value <= MAX_UNITS:
        raise DomainError(f'{name} must be an integer from {minimum} to {MAX_UNITS}')
    return value


def canonical(value):
    try:
        result = json.dumps(value, ensure_ascii=False, sort_keys=True,
                            separators=(',', ':'), allow_nan=False)
        result.encode('utf-8')
        return result
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DomainError('request must contain finite JSON values') from exc


def now():
    return datetime.now(timezone.utc).isoformat()


SCHEMA = '''
CREATE TABLE IF NOT EXISTS products (
 sku TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
 source_url TEXT NOT NULL, uncertainties TEXT NOT NULL,
 price_minor INTEGER NOT NULL, currency TEXT NOT NULL, listing_state TEXT NOT NULL,
 on_hand INTEGER NOT NULL DEFAULT 0, reserved INTEGER NOT NULL DEFAULT 0,
 version INTEGER NOT NULL DEFAULT 1,
 CHECK(on_hand BETWEEN 0 AND 1000000000 AND reserved BETWEEN 0 AND on_hand));
CREATE TABLE IF NOT EXISTS receipts (
 reference TEXT NOT NULL, sku TEXT NOT NULL REFERENCES products(sku),
 quantity INTEGER NOT NULL, PRIMARY KEY(reference,sku));
CREATE TABLE IF NOT EXISTS orders (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, recipient_ref TEXT NOT NULL,
 status TEXT NOT NULL, created_at TEXT NOT NULL, shipment_ref TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS lines (
 order_id TEXT NOT NULL REFERENCES orders(id), sku TEXT NOT NULL REFERENCES products(sku),
 quantity INTEGER NOT NULL, price_minor INTEGER NOT NULL, currency TEXT NOT NULL,
 PRIMARY KEY(order_id,sku));
CREATE TABLE IF NOT EXISTS returns (
 id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id),
 created_at TEXT NOT NULL, note TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS return_lines (
 return_id TEXT NOT NULL REFERENCES returns(id), sku TEXT NOT NULL REFERENCES products(sku),
 quantity INTEGER NOT NULL, restock INTEGER NOT NULL, PRIMARY KEY(return_id,sku));
CREATE TABLE IF NOT EXISTS movements (
 id INTEGER PRIMARY KEY, sku TEXT NOT NULL REFERENCES products(sku),
 on_hand_delta INTEGER NOT NULL, reserved_delta INTEGER NOT NULL,
 reason TEXT NOT NULL, reference TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS stocktakes (
 reference TEXT NOT NULL, sku TEXT NOT NULL REFERENCES products(sku),
 quantity INTEGER NOT NULL, prior_on_hand INTEGER NOT NULL,
 version_before INTEGER NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(reference,sku));
CREATE TABLE IF NOT EXISTS operations (
 key TEXT PRIMARY KEY, request TEXT NOT NULL, result TEXT NOT NULL);
'''


class Store:
    def __init__(self, path):
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(SCHEMA)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
        finally:
            if db.in_transaction:
                db.rollback()
            db.close()

    def product(self, db, sku):
        row = db.execute('SELECT * FROM products WHERE sku=?', (sku,)).fetchone()
        if row is None:
            raise DomainError(f'Unknown SKU: {sku}', 404)
        return row

    def move(self, db, sku, stock, reserved, reason, reference):
        row = self.product(db, sku)
        hand, held = row['on_hand'] + stock, row['reserved'] + reserved
        if not 0 <= held <= hand <= MAX_UNITS:
            raise DomainError(f'Insufficient stock or quantity overflow: {sku}', 409)
        db.execute('UPDATE products SET on_hand=?,reserved=?,version=version+1 WHERE sku=?',
                   (hand, held, sku))
        db.execute('INSERT INTO movements(sku,on_hand_delta,reserved_delta,reason,reference,created_at) VALUES(?,?,?,?,?,?)',
                   (sku, stock, reserved, reason, reference, now()))

    def save_product(self, db, data):
        if not isinstance(data, dict):
            raise DomainError('product must be an object')
        sku = text(data.get('sku'), 'sku')
        old = db.execute('SELECT * FROM products WHERE sku=?', (sku,)).fetchone()
        version = integer(data.get('version', 0), 'version')
        if version != (old['version'] if old else 0):
            raise DomainError(f'Stale product version: {sku}; refresh and retry', 409)
        title = text(data.get('title'), 'title')
        description = text(data.get('description', ''), 'description', True)
        source = text(data.get('source_url'), 'source_url')
        try:
            parsed = urlsplit(source)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError()
        except ValueError as exc:
            raise DomainError('source_url must be an HTTP(S) source link without credentials') from exc
        unknown = text(data.get('uncertainties', ''), 'uncertainties', True)
        price = integer(data.get('price_minor', 0), 'price_minor')
        currency = text(data.get('currency', 'USD'), 'currency')
        if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
            raise DomainError('currency must be three letters')
        state = data.get('listing_state', 'draft')
        if state not in ('draft', 'ready', 'listed', 'paused'):
            raise DomainError('listing_state must be draft, ready, listed or paused')
        if state in ('ready', 'listed') and (unknown or not description):
            raise DomainError('Complete the description and resolve uncertain attributes before preparing a listing')
        values = (title, description, source, unknown, price, currency.upper(), state)
        if old:
            db.execute('UPDATE products SET title=?,description=?,source_url=?,uncertainties=?,price_minor=?,currency=?,listing_state=?,version=version+1 WHERE sku=?', (*values, sku))
        else:
            db.execute('INSERT INTO products(title,description,source_url,uncertainties,price_minor,currency,listing_state,sku) VALUES(?,?,?,?,?,?,?,?)', (*values, sku))
        return {'sku': sku, 'version': version + 1}

    def stocktake(self, db, data):
        """Apply a version-bound physical count without replacing reserved work."""
        if not isinstance(data, dict):
            raise DomainError('Each stock count must be an object')
        sku = text(data.get('sku'), 'sku')
        quantity = integer(data.get('quantity'), 'quantity')
        version = integer(data.get('version'), 'version', 1)
        reference = text(data.get('reference'), 'stock count reference')
        note = text(data.get('note', ''), 'note', True)
        product = self.product(db, sku)
        if version != product['version']:
            raise DomainError(f'Stale stock count for {sku}; reload and recheck the count', 409)
        if quantity < product['reserved']:
            raise DomainError(
                f'Count {quantity} for {sku} is below {product["reserved"]} reserved units; '
                'resolve the affected allocations, then reload and recount. Nothing changed', 409)
        db.execute('INSERT INTO stocktakes VALUES(?,?,?,?,?,?,?)',
                   (reference, sku, quantity, product['on_hand'], version, note, now()))
        delta = quantity - product['on_hand']
        # Record zero-delta observations too: a count is not an untracked overwrite.
        self.move(db, sku, delta, 0, 'stocktake', reference)
        return {'sku': sku, 'reference': reference, 'prior_on_hand': product['on_hand'],
                'on_hand': quantity, 'reserved': product['reserved'],
                'available': quantity - product['reserved'], 'delta': delta,
                'version': version + 1}

    def execute(self, request):
        if not isinstance(request, dict) or not isinstance(request.get('data'), dict):
            raise DomainError('Expected {key, action, data: {...}}')
        key = text(request.get('key'), 'key')
        action = text(request.get('action'), 'action')
        signature = canonical({'action': action, 'data': request['data']})
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT * FROM operations WHERE key=?', (key,)).fetchone()
            if prior:
                if prior['request'] != signature:
                    raise DomainError('Operation key already belongs to different input', 409)
                return json.loads(prior['result'])
            try:
                result = self.apply(db, action, request['data'])
                result['operation_key'] = key
                db.execute('INSERT INTO operations VALUES(?,?,?)', (key, signature, canonical(result)))
                db.commit()
                return result
            except sqlite3.IntegrityError as exc:
                raise DomainError('Conflicting identifier or inventory state; nothing changed', 409) from exc

    def apply(self, db, action, data):
        if action == 'product':
            return self.save_product(db, data)
        if action == 'catalog':
            products = data.get('products')
            if not isinstance(products, list) or not products:
                raise DomainError('products must be a nonempty list')
            skus = [text(p.get('sku'), 'sku') if isinstance(p, dict) else None for p in products]
            if len(skus) != len(set(skus)):
                raise DomainError('Duplicate SKU in catalog import')
            return {'products': [self.save_product(db, p) for p in products]}
        if action == 'stocktake':
            return self.stocktake(db, data)
        if action == 'stocktake_batch':
            counts = data.get('counts')
            if not isinstance(counts, list) or not counts:
                raise DomainError('counts must be a nonempty list')
            if not all(isinstance(count, dict) for count in counts):
                raise DomainError('Each stock count must be an object')
            skus = [text(count.get('sku'), 'sku') for count in counts]
            if len(skus) != len(set(skus)):
                raise DomainError('Duplicate SKU in stock count batch')
            return {'counts': [self.stocktake(db, count) for count in counts]}
        if action == 'receive':
            sku = text(data.get('sku'), 'sku')
            qty = integer(data.get('quantity'), 'quantity', 1)
            reference = text(data.get('reference'), 'receipt reference')
            self.product(db, sku)
            db.execute('INSERT INTO receipts VALUES(?,?,?)', (reference, sku, qty))
            self.move(db, sku, qty, 0, 'receipt', reference)
            return {'sku': sku, 'received': qty}
        if action == 'order':
            oid = text(data.get('id'), 'order id')
            kind = data.get('kind', 'sale')
            if kind not in ('sale', 'sample'):
                raise DomainError('kind must be sale or sample')
            recipient = text(data.get('recipient_ref'), 'recipient_ref')
            lines = data.get('lines')
            if not isinstance(lines, list) or not lines:
                raise DomainError('lines must be a nonempty list')
            merged = {}
            for line in lines:
                if not isinstance(line, dict):
                    raise DomainError('Each order line must be an object')
                sku = text(line.get('sku'), 'sku')
                merged[sku] = integer(merged.get(sku, 0) + integer(line.get('quantity'), 'quantity', 1), 'total quantity', 1)
            db.execute('INSERT INTO orders(id,kind,recipient_ref,status,created_at) VALUES(?,?,?,?,?)', (oid, kind, recipient, 'reserved', now()))
            for sku, qty in merged.items():
                product = self.product(db, sku)
                self.move(db, sku, 0, qty, 'reserve', oid)
                db.execute('INSERT INTO lines VALUES(?,?,?,?,?)', (oid, sku, qty, product['price_minor'], product['currency']))
            return {'id': oid, 'status': 'reserved', 'kind': kind}
        if action in ('fulfill', 'cancel'):
            oid = text(data.get('id'), 'order id')
            order = db.execute('SELECT * FROM orders WHERE id=?', (oid,)).fetchone()
            if order is None:
                raise DomainError('Unknown order', 404)
            target = 'fulfilled' if action == 'fulfill' else 'cancelled'
            if order['status'] == target:
                if action == 'fulfill':
                    reference = text(data.get('shipment_ref', ''), 'shipment_ref')
                    if reference != order['shipment_ref']:
                        raise DomainError(
                            'Shipment reference does not match the fulfilled handoff; nothing changed', 409)
                    return {'id': oid, 'status': target, 'shipment_ref': order['shipment_ref']}
                return {'id': oid, 'status': target}
            if order['status'] != 'reserved':
                raise DomainError('Only a reserved order can be fulfilled or cancelled', 409)
            reference = text(data.get('shipment_ref', ''), 'shipment_ref', action == 'cancel')
            for line in db.execute('SELECT * FROM lines WHERE order_id=?', (oid,)).fetchall():
                qty = line['quantity']
                self.move(db, line['sku'], -qty if action == 'fulfill' else 0, -qty, action, oid)
            db.execute('UPDATE orders SET status=?,shipment_ref=? WHERE id=?', (target, reference, oid))
            result = {'id': oid, 'status': target}
            if action == 'fulfill':
                result['shipment_ref'] = reference
            return result
        if action == 'return':
            rid, oid = text(data.get('id'), 'return id'), text(data.get('order_id'), 'order_id')
            sku = text(data.get('sku'), 'sku')
            qty = integer(data.get('quantity'), 'quantity', 1)
            restock = data.get('restock')
            if type(restock) is not bool:
                raise DomainError('restock must be explicitly true or false after inspection')
            line = db.execute('SELECT l.quantity,o.status FROM lines l JOIN orders o ON o.id=l.order_id WHERE o.id=? AND l.sku=?', (oid, sku)).fetchone()
            if line is None or line['status'] != 'fulfilled':
                raise DomainError('Return requires a fulfilled order line', 409)
            returned = db.execute('SELECT COALESCE(SUM(l.quantity),0) FROM return_lines l JOIN returns r ON r.id=l.return_id WHERE r.order_id=? AND l.sku=?', (oid, sku)).fetchone()[0]
            if returned + qty > line['quantity']:
                raise DomainError('Return exceeds remaining fulfilled quantity', 409)
            db.execute('INSERT INTO returns VALUES(?,?,?,?)', (rid, oid, now(), text(data.get('note', ''), 'note', True)))
            db.execute('INSERT INTO return_lines VALUES(?,?,?,?)', (rid, sku, qty, int(restock)))
            if restock:
                self.move(db, sku, qty, 0, 'return', rid)
            return {'id': rid, 'returned': qty, 'restocked': qty if restock else 0}
        raise DomainError('Unknown operation')

    def snapshot(self):
        with self.connection() as db:
            db.execute('BEGIN')
            result = {table: [dict(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY 1')]
                      for table in ('products', 'orders', 'lines', 'returns', 'return_lines', 'movements', 'receipts', 'stocktakes')}
            for p in result['products']:
                p['available'] = p['on_hand'] - p['reserved']
            return result

    def export_csv(self, table):
        if table not in ('products', 'orders', 'lines', 'returns', 'return_lines', 'movements', 'receipts', 'stocktakes'):
            raise DomainError('Unknown export', 404)
        rows = self.snapshot()[table]
        with self.connection() as db:
            fields = [row[1] for row in db.execute(f'PRAGMA table_info({table})')]
        if table == 'products':
            fields.append('available')
        out = io.StringIO(newline='')
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v) for k, v in row.items()})
        return out.getvalue()


def server_for(store, host='127.0.0.1', port=8765):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, body, content_type='application/json; charset=utf-8'):
            raw = (canonical(body) if content_type.startswith('application/json') else body).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path == '/':
                    self.reply(200, Path(__file__).with_name('desk.html').read_text(encoding='utf-8'), 'text/html; charset=utf-8')
                elif path == '/api/state':
                    self.reply(200, store.snapshot())
                elif path.startswith('/export/') and path.endswith('.csv'):
                    self.reply(200, store.export_csv(path[8:-4]), 'text/csv; charset=utf-8')
                else:
                    raise DomainError('Not found', 404)
            except DomainError as exc:
                self.reply(exc.status, {'error': str(exc)})

        def do_POST(self):
            try:
                if urlsplit(self.path).path != '/api/command':
                    raise DomainError('Not found', 404)
                length = int(self.headers.get('Content-Length', '0'))
                if length < 1 or length > 2_000_000:
                    raise DomainError('Provide a JSON body up to 2 MB', 413)
                request = json.loads(self.rfile.read(length).decode('utf-8'))
                self.reply(200, store.execute(request))
            except DomainError as exc:
                self.reply(exc.status, {'error': str(exc)})
            except (ValueError, UnicodeError, RecursionError):
                self.reply(400, {'error': 'Malformed JSON request'})
            except sqlite3.OperationalError:
                self.reply(503, {'error': 'Database busy or unavailable; retry the same operation key'})
    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='shop-operations.sqlite3')
    sub = parser.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve')
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=8765)
    apply = sub.add_parser('apply', help='Apply one JSON command file')
    apply.add_argument('file', type=Path)
    sub.add_parser('export', help='Print full JSON operational snapshot')
    args = parser.parse_args()
    store = Store(args.db)
    try:
        if args.command == 'apply':
            print(canonical(store.execute(json.loads(args.file.read_text(encoding='utf-8')))))
        elif args.command == 'export':
            print(canonical(store.snapshot()))
        else:
            server = server_for(store, args.host, args.port)
            print(f'Shop Operations Desk: http://{args.host}:{server.server_port}', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
    except (DomainError, OSError, ValueError) as exc:
        parser.exit(2, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
