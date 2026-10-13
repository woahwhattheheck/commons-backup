#!/usr/bin/env python3
"""Persistent inbound order support and TwiML adapter. Python standard library only."""
from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as dt
import hashlib
import io
import json
import re
import sqlite3
import sys
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
COLUMNS = ('order_ref', 'status', 'eta', 'delivered_on', 'returnable')
STATUSES = {'processing', 'shipped', 'delivered', 'cancelled'}
DEFAULT_POLICY = {'shop_name': 'Order Support', 'shipping_text': 'Shipping information has not been supplied. Please ask the team.', 'return_days': 30, 'staff_phone': '', 'revision': 1}
MENU = 'For order status, say status or press 1. For a return, say return or press 2. For shipping policy, press 3. For the team, say agent or press 0.'
DIGIT_WORDS = dict(zip('zero one two three four five six seven eight nine'.split(), '0123456789'))


def text(value, name, maximum=2000, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise ValueError(f'{name} must be text of 1 to {maximum} characters' if not empty else f'{name} must be text up to {maximum} characters')
    # XML 1.0 cannot represent most control characters or lone surrogates.
    if any(not (c in '\t\n\r' or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF) for c in value):
        raise ValueError(f'{name} contains unsupported control characters')
    return value.strip()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def order_reference(value):
    value = text(value, 'order reference', 80).upper()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9-]{0,31}', value):
        raise ValueError('order reference must contain 1 to 32 letters, digits or hyphens')
    return value


def spoken_reference(value):
    """Accept literal references or individually spoken digits; never guess a match."""
    value = value.strip().lower().rstrip('.')
    words = value.split()
    if words and all(w in DIGIT_WORDS for w in words):
        return ''.join(DIGIT_WORDS[w] for w in words)
    return order_reference(value)


def twiml(result):
    root = ET.Element('Response')
    if result.get('dial_phone'):
        ET.SubElement(root, 'Say').text = result['message']
        dial = ET.SubElement(root, 'Dial', {'action': '/dial-result', 'method': 'POST', 'timeout': '20', 'answerOnBridge': 'true'})
        ET.SubElement(dial, 'Number').text = result['dial_phone']
    elif result['state'] == 'ended':
        ET.SubElement(root, 'Say').text = result['message']
        ET.SubElement(root, 'Hangup')
    else:
        gather = ET.SubElement(root, 'Gather', {'input': 'dtmf speech', 'action': '/voice?' + urlencode({'turn': result['next_turn']}), 'method': 'POST', 'actionOnEmptyResult': 'true', 'speechTimeout': 'auto', 'timeout': '6', 'finishOnKey': '#', 'language': 'en-US'})
        ET.SubElement(gather, 'Say').text = result['message']
    return ET.tostring(root, encoding='unicode', xml_declaration=False)


class Conflict(ValueError):
    """A call turn has already been used or is not the next sequential turn."""


class Store:
    def __init__(self, path, today=None):
        self.path = str(path)
        if self.path == ':memory:':
            raise ValueError('use a file-backed database; each request has its own connection')
        self.today = today or dt.date.today
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS policy (id INTEGER PRIMARY KEY CHECK(id=1), document TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS orders (order_ref TEXT PRIMARY KEY, status TEXT NOT NULL, eta TEXT NOT NULL, delivered_on TEXT NOT NULL, returnable INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS calls (call_id TEXT PRIMARY KEY, state TEXT NOT NULL, order_ref TEXT, reason TEXT NOT NULL DEFAULT '', next_turn INTEGER NOT NULL, misses INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS turns (call_id TEXT NOT NULL REFERENCES calls(call_id), turn INTEGER NOT NULL, request_hash TEXT NOT NULL, response TEXT NOT NULL, PRIMARY KEY(call_id,turn));
            CREATE TABLE IF NOT EXISTS returns (id TEXT PRIMARY KEY, order_ref TEXT NOT NULL UNIQUE REFERENCES orders(order_ref), call_id TEXT NOT NULL, reason TEXT NOT NULL, policy_revision INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'requested', note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS handoffs (id TEXT PRIMARY KEY, call_id TEXT NOT NULL UNIQUE REFERENCES calls(call_id), order_ref TEXT, reason TEXT NOT NULL, dial_status TEXT NOT NULL, operator_status TEXT NOT NULL DEFAULT 'open', note TEXT NOT NULL DEFAULT '', callback_status TEXT, callback_response TEXT, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL);
            ''')
            db.execute('INSERT OR IGNORE INTO policy VALUES(1,?)', (canonical(DEFAULT_POLICY),))

    @contextlib.contextmanager
    def connection(self, write=False):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                db.commit()
        except BaseException:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def log(db, kind, details):
        db.execute('INSERT INTO audit(kind,details,created_at) VALUES(?,?,?)', (kind, canonical(details), dt.datetime.now(dt.timezone.utc).isoformat()))

    @staticmethod
    def policy(db):
        return json.loads(db.execute('SELECT document FROM policy WHERE id=1').fetchone()[0])

    def update_policy(self, value):
        if not isinstance(value, dict) or set(value) != set(DEFAULT_POLICY) - {'revision'}:
            raise ValueError('policy requires shop_name, shipping_text, return_days and staff_phone')
        cleaned = {k: text(value[k], k, 3000 if k == 'shipping_text' else 100, empty=(k == 'staff_phone')) for k in ('shop_name', 'shipping_text', 'staff_phone')}
        days = value['return_days']
        if type(days) is not int or not 0 <= days <= 3650:
            raise ValueError('return_days must be an integer from 0 to 3650')
        if cleaned['staff_phone'] and not re.fullmatch(r'\+[1-9][0-9]{7,14}', cleaned['staff_phone']):
            raise ValueError('staff_phone must be blank or an international +number')
        cleaned['return_days'] = days
        with self.connection(write=True) as db:
            cleaned['revision'] = self.policy(db)['revision'] + 1
            db.execute('UPDATE policy SET document=? WHERE id=1', (canonical(cleaned),))
            self.log(db, 'policy_updated', {'revision': cleaned['revision']})
        return cleaned

    def import_csv(self, content):
        text(content, 'CSV', 2_000_000)
        reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff'), newline=''))
        if reader.fieldnames != list(COLUMNS):
            raise ValueError('CSV header must be: ' + ','.join(COLUMNS))
        rows, seen = [], set()
        for number, row in enumerate(reader, 2):
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError('wrong column count')
                ref = order_reference(row['order_ref'])
                if ref in seen:
                    raise ValueError('duplicate order reference in this import')
                seen.add(ref)
                status = text(row['status'], 'status', 20)
                if status not in STATUSES:
                    raise ValueError('status must be processing, shipped, delivered or cancelled')
                delivered = text(row['delivered_on'], 'delivered_on', 10, empty=True)
                if delivered:
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', delivered):
                        raise ValueError('delivered_on must use YYYY-MM-DD')
                    date = dt.date.fromisoformat(delivered)
                    if date > self.today():
                        raise ValueError('delivered_on cannot be in the future')
                if status == 'delivered' and not delivered:
                    raise ValueError('delivered orders require delivered_on')
                if status != 'delivered' and delivered:
                    raise ValueError('only delivered orders may have delivered_on')
                if row['returnable'] not in ('true', 'false'):
                    raise ValueError('returnable must be true or false')
                rows.append((ref, status, text(row['eta'], 'eta', 200, empty=True), delivered, int(row['returnable'] == 'true')))
            except ValueError as exc:
                raise ValueError(f'CSV row {number}: {exc}') from exc
        if not rows:
            raise ValueError('CSV has no order rows')
        with self.connection(write=True) as db:
            db.executemany('INSERT INTO orders VALUES(?,?,?,?,?) ON CONFLICT(order_ref) DO UPDATE SET status=excluded.status,eta=excluded.eta,delivered_on=excluded.delivered_on,returnable=excluded.returnable', rows)
            self.log(db, 'orders_imported', {'count': len(rows)})
        return {'imported': len(rows)}

    def snapshot(self, include_audit=False):
        with self.connection() as db:
            db.execute('BEGIN')
            tables = [('orders', 'order_ref'), ('returns', 'created_at,id'), ('handoffs', 'created_at,id'), ('calls', 'call_id')]
            if include_audit:
                tables.append(('audit', 'id'))
            return {'policy': self.policy(db), **{table: [dict(r) for r in db.execute(f'SELECT * FROM {table} ORDER BY {key}')] for table, key in tables}}

    def eligible(self, order, policy):
        if policy['revision'] == 1 or order is None or order['status'] != 'delivered' or not order['returnable']:
            return False
        age = (self.today() - dt.date.fromisoformat(order['delivered_on'])).days
        return 0 <= age <= policy['return_days']

    def handoff(self, db, call, policy, reason):
        old = db.execute('SELECT * FROM handoffs WHERE call_id=?', (call['call_id'],)).fetchone()
        hid = old['id'] if old else 'H-' + uuid.uuid4().hex[:12]
        if not old:
            db.execute('INSERT INTO handoffs(id,call_id,order_ref,reason,dial_status,created_at) VALUES(?,?,?,?,?,?)', (hid, call['call_id'], call['order_ref'], reason, 'dial_requested' if policy['staff_phone'] else 'not_configured', dt.datetime.now(dt.timezone.utc).isoformat()))
            self.log(db, 'handoff_requested', {'id': hid, 'call_id': call['call_id']})
        call['state'] = 'ended'
        result = {'handoff_id': hid}
        if policy['staff_phone']:
            result.update(message='This needs a team member. I will try the configured team number now.', dial_phone=policy['staff_phone'])
        else:
            result['message'] = 'This needs a team member. Your request is in the team queue. A live transfer number has not been configured. Please contact the shop through its usual support channel.'
        return result

    def turn(self, call_id, turn, speech='', digits=''):
        call_id = text(call_id, 'call_id', 100)
        speech = text(speech, 'speech', 1000, empty=True)
        digits = text(digits, 'digits', 32, empty=True)
        if digits and not re.fullmatch(r'[0-9*#]+', digits):
            raise ValueError('digits contains a non-keypad character')
        if type(turn) is not int or turn < 0:
            raise ValueError('turn must be a nonnegative integer')
        digest = hashlib.sha256(canonical([speech, digits]).encode()).hexdigest()
        with self.connection(write=True) as db:
            old = db.execute('SELECT * FROM turns WHERE call_id=? AND turn=?', (call_id, turn)).fetchone()
            if old:
                if old['request_hash'] != digest:
                    raise Conflict('this call turn already has different input')
                return json.loads(old['response'])
            found = db.execute('SELECT * FROM calls WHERE call_id=?', (call_id,)).fetchone()
            policy = self.policy(db)
            if found is None:
                if turn != 0 or speech or digits:
                    raise Conflict('a call must start with empty turn 0')
                call = {'call_id': call_id, 'state': 'order', 'order_ref': None, 'reason': '', 'next_turn': 1, 'misses': 0}
                db.execute('INSERT INTO calls(call_id,state,next_turn) VALUES(?,?,?)', (call_id, 'order', 1))
                result = {'message': f"Welcome to {policy['shop_name']}. This is the automated order desk. Enter your order reference, then pound, or speak its digits individually. Say agent or press 0 for the team."}
            else:
                call = dict(found)
                if turn != call['next_turn'] or call['state'] == 'ended':
                    raise Conflict('not the next active call turn')
                call['next_turn'] += 1
                value = (digits or speech).lower().strip().rstrip('.')
                order = db.execute('SELECT * FROM orders WHERE order_ref=?', (call['order_ref'],)).fetchone()
                if value in ('0', 'agent', 'human', 'person', 'team', 'speak to an agent'):
                    result = self.handoff(db, call, policy, 'caller requested team')
                elif not value:
                    call['misses'] += 1
                    result = self.handoff(db, call, policy, 'two empty inputs') if call['misses'] >= 2 else {'message': 'I did not receive an answer. Please try again, or say agent or press 0.'}
                else:
                    call['misses'] = 0
                    if call['state'] == 'order':
                        try:
                            ref = spoken_reference(value)
                        except ValueError:
                            ref = ''
                        order = db.execute('SELECT * FROM orders WHERE order_ref=?', (ref,)).fetchone()
                        if order is None:
                            result = self.handoff(db, call, policy, 'order not found or reference not understood')
                        else:
                            call.update(state='menu', order_ref=ref)
                            result = {'message': f'Order {ref} found. {MENU}'}
                    elif call['state'] == 'menu':
                        if value in ('1', 'status', 'order status', 'where is my order'):
                            result = {'message': f"Order {call['order_ref']} is {order['status']}. " + (f"Shipping update: {order['eta']}. " if order['eta'] else '') + MENU}
                        elif value in ('3', 'shipping', 'shipping policy', 'policy'):
                            result = {'message': policy['shipping_text'] + ' ' + MENU}
                        elif value in ('2', 'return', 'returns', 'return order'):
                            existing = db.execute('SELECT id,status FROM returns WHERE order_ref=?', (call['order_ref'],)).fetchone()
                            if existing:
                                result = {'message': f"Return request {existing['id']} is already {existing['status']}. No new request was created. {MENU}", 'return_id': existing['id']}
                            elif not self.eligible(order, policy):
                                result = self.handoff(db, call, policy, 'return outside current automated policy')
                            else:
                                call['state'] = 'reason'
                                result = {'message': 'Please briefly say why you want to return this order. Or press 1 for damaged, 2 for incorrect item, or 3 for changed mind. This creates a request for review, not a refund.'}
                        else:
                            result = self.handoff(db, call, policy, 'request outside supported status/return/shipping workflow')
                    elif call['state'] == 'reason':
                        reason = {'1': 'damaged', '2': 'incorrect item', '3': 'changed mind'}.get(value, speech if speech else '')
                        if not reason:
                            result = {'message': 'Say the reason, or press 1 for damaged, 2 for incorrect item, or 3 for changed mind.'}
                        else:
                            call.update(state='confirm', reason=reason)
                            result = {'message': f"Create one return request for order {call['order_ref']} with reason: {reason}? Say yes or press 1 to confirm; say no or press 2 to cancel. This does not approve a return or issue a refund."}
                    elif call['state'] == 'confirm':
                        if value in ('2', 'no', 'cancel'):
                            call.update(state='menu', reason='')
                            result = {'message': 'Cancelled. No return request was created. ' + MENU}
                        elif value not in ('1', 'yes', 'confirm'):
                            result = {'message': 'Please say yes or press 1 to create the request; say no or press 2 to cancel.'}
                        elif not self.eligible(order, policy):
                            result = self.handoff(db, call, policy, 'order or policy changed before return confirmation')
                        else:
                            existing = db.execute('SELECT id FROM returns WHERE order_ref=?', (call['order_ref'],)).fetchone()
                            rid = existing['id'] if existing else 'R-' + uuid.uuid4().hex[:12]
                            if not existing:
                                db.execute('INSERT INTO returns(id,order_ref,call_id,reason,policy_revision,created_at) VALUES(?,?,?,?,?,?)', (rid, call['order_ref'], call_id, call['reason'], policy['revision'], dt.datetime.now(dt.timezone.utc).isoformat()))
                                self.log(db, 'return_requested', {'id': rid, 'order_ref': call['order_ref']})
                            call.update(state='menu', reason='')
                            result = {'message': f'Return request {rid} is recorded for team review. No refund has been issued. {MENU}', 'return_id': rid}
                    else:
                        raise Conflict('invalid persisted call state')
            result.update(call_id=call_id, state=call['state'], order_ref=call['order_ref'], next_turn=call['next_turn'])
            result['twiml'] = twiml(result)
            db.execute('UPDATE calls SET state=?,order_ref=?,reason=?,next_turn=?,misses=? WHERE call_id=?', (call['state'], call['order_ref'], call['reason'], call['next_turn'], call['misses'], call_id))
            db.execute('INSERT INTO turns VALUES(?,?,?,?)', (call_id, turn, digest, canonical(result)))
            return result

    def dial_result(self, call_id, status):
        call_id = text(call_id, 'CallSid', 100)
        if status not in {'completed', 'busy', 'no-answer', 'failed', 'canceled'}:
            raise ValueError('unsupported DialCallStatus')
        with self.connection(write=True) as db:
            row = db.execute('SELECT * FROM handoffs WHERE call_id=?', (call_id,)).fetchone()
            if not row or row['dial_status'] == 'not_configured':
                raise Conflict('no configured transfer for this call')
            if row['callback_status']:
                if row['callback_status'] != status:
                    raise Conflict('a different terminal dial result is already recorded')
                return json.loads(row['callback_response'])
            message = 'The transfer call has ended. Thank you.' if status == 'completed' else 'The team could not be reached on that transfer. Your request remains in the team queue. Please contact the shop through its usual support channel.'
            result = {'message': message, 'state': 'ended', 'next_turn': None, 'dial_status': status, 'handoff_id': row['id']}
            result['twiml'] = twiml(result)
            db.execute('UPDATE handoffs SET dial_status=?,callback_status=?,callback_response=? WHERE id=?', (status, status, canonical(result), row['id']))
            self.log(db, 'dial_result', {'id': row['id'], 'provider_status': status})
            return result

    def review(self, kind, identifier, status, note):
        choices = {'returns': ('status', {'requested', 'reviewed', 'closed'}), 'handoffs': ('operator_status', {'open', 'resolved'})}
        if not isinstance(kind, str) or not isinstance(status, str) or kind not in choices or status not in choices[kind][1]:
            raise ValueError('invalid review kind or status')
        identifier, note = text(identifier, 'id', 100), text(note, 'note', 2000)
        with self.connection(write=True) as db:
            cursor = db.execute(f'UPDATE {kind} SET {choices[kind][0]}=?,note=? WHERE id=?', (status, note, identifier))
            if cursor.rowcount != 1:
                raise ValueError('request not found')
            self.log(db, 'operator_review', {'kind': kind, 'id': identifier, 'status': status, 'note': note})
        return {'updated': identifier}

    def export(self):
        snapshot = self.snapshot(include_audit=True)
        return (json.dumps({'schema_version': 1, **snapshot}, ensure_ascii=False, indent=2) + '\n').encode()


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'VoiceSupportDesk/1'

        def log_message(self, *_args):
            pass  # Do not echo call references or request bodies into server logs.

        def send(self, body, status=200, mime='application/json; charset=utf-8', download=None):
            data = body if isinstance(body, bytes) else (body.encode() if isinstance(body, str) else canonical(body).encode())
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if download:
                self.send_header('Content-Disposition', f'attachment; filename="{download}"')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/':
                self.send((HERE / 'index.html').read_bytes(), mime='text/html; charset=utf-8')
            elif path == '/api/state':
                self.send(store.snapshot())
            elif path == '/api/export':
                self.send(store.export(), download='voice-support-data.json')
            elif path == '/health':
                self.send({'status': 'ok', 'live_telephone_tested': False})
            else:
                self.send({'error': 'not found'}, 404)

        def do_POST(self):
            route = urlsplit(self.path)
            try:
                raw_length = self.headers.get('Content-Length', '')
                if not raw_length.isdecimal() or not 0 < int(raw_length) <= 2_000_000:
                    raise ValueError('Content-Length must be between 1 and 2000000')
                body = self.rfile.read(int(raw_length)).decode('utf-8')
                if route.path in ('/voice', '/dial-result'):
                    if self.headers.get_content_type() != 'application/x-www-form-urlencoded':
                        raise ValueError('voice requests require form-urlencoded input')
                    form = parse_qs(body, keep_blank_values=True, strict_parsing=True, encoding='utf-8', errors='strict')
                    if any(len(v) != 1 for v in form.values()):
                        raise ValueError('duplicate form field')
                    params = {k: v[0] for k, v in form.items()}
                    if route.path == '/dial-result':
                        result = store.dial_result(params.get('CallSid', ''), params.get('DialCallStatus', ''))
                    else:
                        query = parse_qs(route.query, keep_blank_values=True)
                        if set(query) - {'turn'} or len(query.get('turn', ['0'])) != 1:
                            raise ValueError('invalid turn query')
                        stamp = query.get('turn', ['0'])[0]
                        if not re.fullmatch(r'0|[1-9][0-9]*', stamp):
                            raise ValueError('invalid turn query')
                        result = store.turn(params.get('CallSid', ''), int(stamp), params.get('SpeechResult', ''), params.get('Digits', ''))
                    self.send(result['twiml'], mime='application/xml; charset=utf-8')
                elif route.path == '/api/import':
                    self.send(store.import_csv(body))
                else:
                    value = json.loads(body)
                    if not isinstance(value, dict):
                        raise ValueError('JSON must be an object')
                    if route.path == '/api/policy':
                        result = store.update_policy(value)
                    elif route.path == '/api/turn':
                        result = store.turn(value.get('call_id'), value.get('turn'), value.get('speech', ''), value.get('digits', ''))
                    elif route.path == '/api/review':
                        result = store.review(value.get('kind'), value.get('id'), value.get('status'), value.get('note'))
                    else:
                        return self.send({'error': 'not found'}, 404)
                    self.send(result)
            except (ValueError, UnicodeError, csv.Error, OverflowError) as exc:
                self.send({'error': str(exc)}, 409 if isinstance(exc, Conflict) else 400)
            except sqlite3.Error:
                self.send({'error': 'database operation failed; retry the same request'}, 503)
    return Handler


def bundle(destination):
    """Package source only; no database, customer data, logs or ambient files."""
    paths = ['desk.py', 'index.html', 'README.md', 'test_desk.py', 'orders.example.csv']
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in paths:
            archive.write(HERE / name, 'voice-support-desk/' + name)
    return str(destination)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='voice-support.sqlite3')
    sub = parser.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve')
    serve.add_argument('--bind', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=8096)
    load = sub.add_parser('import')
    load.add_argument('csv_file', type=Path)
    policy = sub.add_parser('policy')
    policy.add_argument('json_file', type=Path)
    out = sub.add_parser('export')
    out.add_argument('destination', type=Path)
    package = sub.add_parser('bundle')
    package.add_argument('destination', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'bundle':
            print(bundle(args.destination))
            return 0
        store = Store(args.db)
        if args.command == 'import':
            print(canonical(store.import_csv(args.csv_file.read_text(encoding='utf-8-sig'))))
        elif args.command == 'policy':
            print(canonical(store.update_policy(json.loads(args.json_file.read_text(encoding='utf-8')))))
        elif args.command == 'export':
            with args.destination.open('xb') as output:
                output.write(store.export())
            print(args.destination)
        else:
            with ThreadingHTTPServer((args.bind, args.port), make_handler(store)) as server:
                print(f'Voice Support Desk: http://{args.bind}:{server.server_port}', flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
        return 0
    except (ValueError, OSError, sqlite3.Error, csv.Error) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
