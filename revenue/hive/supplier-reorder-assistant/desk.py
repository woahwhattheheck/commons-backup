#!/usr/bin/env python3
"""Local browser workspace for the existing supplier reorder engine (stdlib only)."""
from __future__ import annotations

import argparse
from contextlib import closing
import csv
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import sqlite3
import tempfile
from urllib.parse import urlsplit
import uuid

import reorder_assistant as engine

MAX_BODY = 8 * 1024 * 1024
MAX_CSV = 2 * 1024 * 1024
MAX_ROWS = 20000
RECEIPT_FIELDS = ['receipt_id', 'received_at', 'supplier_id', 'supplier_sku', 'sku', 'quantity']
INPUT_FIELDS = {
    'stock': ['sku', 'name', 'on_hand', 'on_order', 'allocated', 'unit'],
    'rules': ['sku', 'reorder_at', 'target_stock', 'preferred_supplier'],
    'catalog': ['supplier_id', 'supplier_sku', 'sku', 'description', 'unit_cost',
                'available_qty', 'lead_days', 'alternative_for_sku'],
}


class DeskError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def packed(value):
    try:
        result = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        result.encode('utf-8')
        return result
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise DeskError('request must contain finite JSON values and valid Unicode text') from exc


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def text(value, label, maximum=500):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise DeskError(f'{label} must be nonempty text of at most {maximum} characters')
    return value


def csv_rows(value, fields, label):
    try:
        encoded_size = len(value.encode('utf-8')) if isinstance(value, str) else MAX_CSV + 1
    except UnicodeError as exc:
        raise DeskError(f'{label}: expected valid Unicode CSV text') from exc
    if not isinstance(value, str) or encoded_size > MAX_CSV or '\x00' in value:
        raise DeskError(f'{label}: expected UTF-8 CSV text, at most {MAX_CSV} bytes, without NUL')
    try:
        reader = csv.reader(io.StringIO(value.lstrip('\ufeff'), newline=''), strict=True)
        header = next(reader, [])
        if len(set(header)) != len(header) or any(not field for field in header):
            raise DeskError(f'{label}: blank or duplicate column headings')
        if set(fields) - set(header):
            raise DeskError(f'{label}: missing columns {sorted(set(fields) - set(header))}')
        rows = []
        for number, values in enumerate(reader, 2):
            if not values:
                continue
            if len(values) != len(header):
                raise DeskError(f'{label}: row {number} has {len(values)} cells, expected {len(header)}')
            rows.append(dict(zip(header, (v.strip() for v in values))))
            if len(rows) > MAX_ROWS:
                raise DeskError(f'{label}: exceeds {MAX_ROWS} rows')
        return rows
    except (csv.Error, UnicodeError) as exc:
        raise DeskError(f'{label}: invalid CSV: {exc}') from exc


def receipt_rows(value):
    rows = csv_rows(value, RECEIPT_FIELDS, 'receipts')
    normalized = []
    seen = set()
    for row in rows:
        clean = {key: row[key] for key in RECEIPT_FIELDS}
        for key in RECEIPT_FIELDS:
            text(clean[key], f'receipt {key}', 500)
        if clean['receipt_id'] in seen:
            raise DeskError('duplicate receipt_id within this upload')
        seen.add(clean['receipt_id'])
        normalized.append(clean)
    if not normalized:
        raise DeskError('receipts must contain at least one row')
    return normalized


def stock_csv(stock):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=INPUT_FIELDS['stock'])
    writer.writeheader()
    for sku in sorted(stock):
        writer.writerow(stock[sku].__dict__)
    return output.getvalue()


def compute(inputs, receipts=(), saved_plan=None):
    """Always replay cumulative receipts against immutable imported stock, once."""
    with tempfile.TemporaryDirectory(prefix='reorder-desk-') as directory:
        root = Path(directory)
        for kind, fields in INPUT_FIELDS.items():
            csv_rows(inputs.get(kind), fields, kind)
            (root / f'{kind}.csv').write_bytes(inputs[kind].encode('utf-8'))
        try:
            stock = engine.load_stock(root / 'stock.csv')
            rules = engine.load_rules(root / 'rules.csv')
            catalog = engine.load_catalog(root / 'catalog.csv')
            plan = saved_plan if saved_plan is not None else engine.build_plan(
                stock, rules, catalog, inputs['as_of'])
            updated, log = engine.apply_receipts(stock, plan, list(receipts),
                                                pipeline_includes_draft=inputs['pipeline_includes_draft'])
            return plan, stock_csv(updated), log
        except (engine.ReorderError, ArithmeticError) as exc:
            raise DeskError(str(exc)) from exc


def validate_inputs(raw):
    if not isinstance(raw, dict):
        raise DeskError('inputs must be an object')
    inputs = {kind: raw.get(kind) for kind in INPUT_FIELDS}
    inputs['as_of'] = text(raw.get('as_of'), 'as_of', 10)
    currency = raw.get('currency', 'USD')
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isascii() or not currency.isalpha():
        raise DeskError('currency must be a three-letter catalog currency label')
    inputs['currency'] = currency.upper()
    pipeline = raw.get('pipeline_includes_draft', False)
    if type(pipeline) is not bool:
        raise DeskError('pipeline_includes_draft must be a boolean')
    inputs['pipeline_includes_draft'] = pipeline
    return inputs


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, document TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS revisions(run_id TEXT NOT NULL, revision INTEGER NOT NULL, document TEXT NOT NULL,
                PRIMARY KEY(run_id,revision));
              CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, response TEXT NOT NULL);
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    def get(self, run_id, revision=None):
        with closing(self.connect()) as db:
            if revision is None:
                row = db.execute('SELECT document FROM runs WHERE id=?', (run_id,)).fetchone()
            else:
                row = db.execute('SELECT document FROM revisions WHERE run_id=? AND revision=?',
                                 (run_id, revision)).fetchone()
            if row is None:
                raise DeskError('saved plan not found', 404)
            return json.loads(row['document'])

    def list(self):
        with closing(self.connect()) as db:
            result = []
            for row in db.execute('SELECT document FROM runs ORDER BY rowid DESC'):
                doc = json.loads(row['document'])
                result.append({key: doc[key] for key in ('id', 'title', 'revision', 'created_at', 'updated_at')})
            return result

    def history(self, run_id):
        self.get(run_id)
        with closing(self.connect()) as db:
            return [row[0] for row in db.execute('SELECT revision FROM revisions WHERE run_id=? ORDER BY revision', (run_id,))]

    @staticmethod
    def save(db, doc):
        body = packed(doc)
        db.execute('INSERT INTO runs VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision, document=excluded.document',
                   (doc['id'], doc['revision'], body))
        db.execute('INSERT INTO revisions VALUES(?,?,?)', (doc['id'], doc['revision'], body))

    def transact(self, action, request, callback):
        if not isinstance(request, dict):
            raise DeskError('request must be a JSON object')
        operation = text(request.get('operation_id'), 'operation_id', 160)
        fingerprint = digest(packed([action, request]))
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                previous = db.execute('SELECT * FROM operations WHERE id=?', (operation,)).fetchone()
                if previous:
                    if previous['fingerprint'] != fingerprint:
                        raise DeskError('operation_id already describes a different change', 409)
                    db.commit()
                    return json.loads(previous['response'])
                doc = callback(db)
                db.execute('INSERT INTO operations VALUES(?,?,?)', (operation, fingerprint, packed(doc)))
                db.commit()
                return doc
            except BaseException:
                db.rollback()
                raise

    def create(self, request):
        def action(db):
            title = text(request.get('title'), 'title', 200)
            inputs = validate_inputs(request.get('inputs'))
            plan, updated, log = compute(inputs)
            created = now()
            doc = {'id': uuid.uuid4().hex, 'title': title, 'revision': 1,
                   'created_at': created, 'updated_at': created, 'inputs': inputs,
                   'source_sha256': {kind: digest(inputs[kind]) for kind in INPUT_FIELDS},
                   'plan': plan, 'receipts': [], 'receipt_sources': [],
                   'updated_stock': updated, 'receipt_log': log}
            self.save(db, doc)
            return doc
        return self.transact('create', request, action)

    def receive(self, run_id, request):
        def action(db):
            row = db.execute('SELECT document FROM runs WHERE id=?', (run_id,)).fetchone()
            if row is None:
                raise DeskError('saved plan not found', 404)
            doc = json.loads(row['document'])
            expected = request.get('expected_revision')
            if type(expected) is not int or expected != doc['revision']:
                raise DeskError('saved plan changed; reopen current revision before applying receipts', 409)
            rows = receipt_rows(request.get('csv'))
            previous = {r['receipt_id']: r for r in doc['receipts']}
            fresh = []
            for receipt in rows:
                old = previous.get(receipt['receipt_id'])
                if old is not None and old != receipt:
                    raise DeskError('receipt_id already describes different received goods', 409)
                if old is None:
                    fresh.append(receipt)
            if not fresh:
                return doc
            cumulative = doc['receipts'] + fresh
            plan, updated, log = compute(doc['inputs'], cumulative, doc['plan'])
            doc.update(revision=doc['revision'] + 1, updated_at=now(), receipts=cumulative,
                       plan=plan, updated_stock=updated, receipt_log=log)
            doc['receipt_sources'].append({'csv': request['csv'], 'sha256': digest(request['csv']),
                                           'new_receipt_ids': [r['receipt_id'] for r in fresh]})
            self.save(db, doc)
            return doc
        return self.transact(f'receive:{run_id}', request, action)


def handler(store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def send(self, status, body, kind='application/json; charset=utf-8', filename=None):
            raw = body if isinstance(body, bytes) else body.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if filename:
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(raw)

        def dispatch_get(self):
            path = urlsplit(self.path).path
            if path in ('/', '/desk.html'):
                self.send(200, Path(__file__).with_name('desk.html').read_bytes(), 'text/html; charset=utf-8')
                return
            if path == '/api/runs':
                self.send(200, packed(store.list()))
                return
            parts = path.strip('/').split('/')
            if len(parts) >= 3 and parts[:2] == ['api', 'runs']:
                run_id = parts[2]
                if len(parts) == 3:
                    self.send(200, packed(store.get(run_id)))
                    return
                if parts[3:] == ['history']:
                    self.send(200, packed(store.history(run_id)))
                    return
                if len(parts) == 5 and parts[3] == 'history' and parts[4].isdigit():
                    self.send(200, packed(store.get(run_id, int(parts[4]))))
                    return
                doc = store.get(run_id)
                if parts[3:] == ['export.json']:
                    self.send(200, packed(doc) + '\n', filename='reorder-workspace.json')
                    return
                if parts[3:] == ['updated-stock.csv']:
                    self.send(200, doc['updated_stock'], 'text/csv; charset=utf-8', 'updated-stock.csv')
                    return
                if len(parts) == 5 and parts[3] == 'source' and parts[4] in INPUT_FIELDS:
                    kind = parts[4]
                    self.send(200, doc['inputs'][kind], 'text/csv; charset=utf-8', f'{kind}.csv')
                    return
            raise DeskError('route not found', 404)

        def dispatch_post(self):
            if self.headers.get_content_type() != 'application/json':
                raise DeskError('send application/json', 415)
            try:
                length = int(self.headers.get('Content-Length', '-1'))
            except ValueError as exc:
                raise DeskError('invalid Content-Length') from exc
            if not 0 < length <= MAX_BODY:
                raise DeskError(f'body must contain 1..{MAX_BODY} bytes', 413)
            body = self.rfile.read(length)
            if len(body) != length:
                raise DeskError('incomplete request body')
            try:
                data = json.loads(body.decode('utf-8'), parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise DeskError('invalid JSON') from exc
            parts = urlsplit(self.path).path.strip('/').split('/')
            if parts == ['api', 'runs']:
                self.send(200, packed(store.create(data)))
            elif len(parts) == 4 and parts[:2] == ['api', 'runs'] and parts[3] == 'receipts':
                self.send(200, packed(store.receive(parts[2], data)))
            else:
                raise DeskError('route not found', 404)

        def perform(self, action):
            try:
                action()
            except DeskError as exc:
                self.send(exc.status, packed({'error': str(exc)}))
            except (sqlite3.Error, OSError):
                self.send(503, packed({'error': 'workspace storage unavailable; no successful save reported'}))

        def do_GET(self):
            self.perform(self.dispatch_get)

        def do_POST(self):
            self.perform(self.dispatch_post)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=Path.home() / '.commons-reorder' / 'workspace.sqlite3')
    parser.add_argument('--port', type=int, default=8086)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(Store(args.db)))
    print(f'Supplier reorder desk: http://127.0.0.1:{server.server_port} | {args.db}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
