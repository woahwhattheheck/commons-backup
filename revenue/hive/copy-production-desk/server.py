"""Single-operator copy desk. Python standard library; no sending or provider calls."""
import argparse
import io
import json
import re
import sqlite3
import uuid
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
ACTIVE = ('active', 'review', 'revision')


class DeskError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def text(value, name, maximum=100000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise DeskError(f'{name} must be nonempty text (maximum {maximum} characters)')
    return value


def integer(value, name, minimum=0, maximum=100):
    if type(value) is not int or not minimum <= value <= maximum:
        raise DeskError(f'{name} must be an integer from {minimum} to {maximum}')
    return value


def encoded(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise DeskError('Payload must contain finite JSON values') from exc


def brand(data):
    name = text(data.get('name'), 'name', 200)
    voice = text(data.get('voice'), 'voice', 10000)
    claims = data.get('claims')
    if not isinstance(claims, list) or not 1 <= len(claims) <= 100:
        raise DeskError('claims must contain 1 to 100 source-linked claims')
    seen = set()
    cleaned = []
    for claim in claims:
        if not isinstance(claim, dict):
            raise DeskError('Each claim must be an object')
        item = {k: text(claim.get(k), f'claim.{k}', 10000) for k in ('id', 'text', 'source')}
        if item['id'] in seen:
            raise DeskError('Claim IDs must be unique')
        seen.add(item['id'])
        cleaned.append(item)
    return name, encoded({'voice': voice, 'claims': cleaned})


class Desk:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS clients (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, brand TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS requests (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    client_id TEXT NOT NULL REFERENCES clients(id), title TEXT NOT NULL,
                    kind TEXT NOT NULL, brief TEXT NOT NULL, priority INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued', version INTEGER NOT NULL DEFAULT 1,
                    feedback TEXT NOT NULL DEFAULT '');
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_request ON requests(client_id)
                    WHERE status IN ('active', 'review', 'revision');
                CREATE TABLE IF NOT EXISTS drafts (
                    request_id TEXT NOT NULL REFERENCES requests(id), number INTEGER NOT NULL,
                    files TEXT NOT NULL, sources TEXT NOT NULL, brand_snapshot TEXT NOT NULL,
                    brand_version INTEGER NOT NULL, note TEXT NOT NULL, created TEXT NOT NULL,
                    PRIMARY KEY(request_id, number));
                CREATE TABLE IF NOT EXISTS operations (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, result TEXT NOT NULL);
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    @staticmethod
    def row(db, table, identifier):
        # Table names originate only from this module, never from request data.
        row = db.execute(f'SELECT * FROM {table} WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise DeskError('Item not found', 404)
        return dict(row)

    @staticmethod
    def expected(row, data):
        version = integer(data.get('version'), 'version', 1, 2**53 - 1)
        if version != row['version']:
            raise DeskError('This item changed. Refresh before editing.', 409)

    def snapshot(self):
        db = self.connect()
        try:
            db.execute('BEGIN')
            clients = [dict(r) for r in db.execute('SELECT * FROM clients ORDER BY name,id')]
            requests = [dict(r) for r in db.execute('SELECT * FROM requests ORDER BY priority DESC,seq')]
            for client in clients:
                client['brand'] = json.loads(client['brand'])
            for request in requests:
                request['drafts'] = []
                for row in db.execute('SELECT * FROM drafts WHERE request_id=? ORDER BY number', (request['id'],)):
                    draft = dict(row)
                    for field in ('files', 'sources', 'brand_snapshot'):
                        draft[field] = json.loads(draft[field])
                    request['drafts'].append(draft)
            return {'clients': clients, 'requests': requests, 'delivery': 'LOCAL_FILES_ONLY_NOT_SENT'}
        finally:
            db.close()

    def write(self, operation, data):
        if not isinstance(data, dict):
            raise DeskError('Payload must be an object')
        key = text(data.get('operation_id'), 'operation_id', 200)
        payload = encoded({'operation': operation, 'data': data})
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT * FROM operations WHERE id=?', (key,)).fetchone()
            if previous:
                if previous['payload'] != payload:
                    raise DeskError('operation_id already belongs to a different edit', 409)
                return json.loads(previous['result'])
            result = self._apply(db, operation, data)
            db.execute('INSERT INTO operations VALUES (?,?,?)', (key, payload, encoded(result)))
            db.commit()
            return result
        except sqlite3.IntegrityError as exc:
            db.rollback()
            raise DeskError('Only one request per customer can be in production or review.', 409) from exc
        finally:
            db.close()

    def _apply(self, db, operation, data):
        if operation in ('client/create', 'client/update'):
            name, values = brand(data)
            if operation.endswith('create'):
                identifier = uuid.uuid4().hex
                db.execute('INSERT INTO clients(id,name,brand) VALUES (?,?,?)', (identifier, name, values))
            else:
                identifier = text(data.get('id'), 'id', 100)
                old = self.row(db, 'clients', identifier)
                self.expected(old, data)
                db.execute('UPDATE clients SET name=?,brand=?,version=version+1 WHERE id=?', (name, values, identifier))
            return {'id': identifier}
        if operation == 'request/create':
            client_id = text(data.get('client_id'), 'client_id', 100)
            self.row(db, 'clients', client_id)
            title = text(data.get('title'), 'title', 300)
            kind = text(data.get('kind'), 'kind', 100)
            brief = text(data.get('brief'), 'brief', 20000)
            priority = integer(data.get('priority', 0), 'priority')
            identifier = uuid.uuid4().hex
            db.execute('INSERT INTO requests(id,client_id,title,kind,brief,priority) VALUES (?,?,?,?,?,?)',
                       (identifier, client_id, title, kind, brief, priority))
            return {'id': identifier}
        if operation not in ('draft/save', 'request/action'):
            raise DeskError('Unknown operation', 404)
        identifier = text(data.get('id'), 'id', 100)
        request = self.row(db, 'requests', identifier)
        self.expected(request, data)
        if operation == 'draft/save':
            if request['status'] not in ACTIVE:
                raise DeskError('Start this request before saving a draft', 409)
            client = self.row(db, 'clients', request['client_id'])
            files = data.get('files')
            if not isinstance(files, dict) or not 1 <= len(files) <= 20:
                raise DeskError('files must contain 1 to 20 editable documents')
            for name, body in files.items():
                if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}\.(md|txt)', name):
                    raise DeskError('Document names use letters, digits, underscores or hyphens and .md or .txt')
                text(body, 'document content')
            sources = data.get('source_ids')
            known = {c['id'] for c in json.loads(client['brand'])['claims']}
            if not isinstance(sources, list) or not sources or any(not isinstance(s, str) or s not in known for s in sources):
                raise DeskError('source_ids must reference the customer source library')
            number = db.execute('SELECT COALESCE(MAX(number),0)+1 FROM drafts WHERE request_id=?', (identifier,)).fetchone()[0]
            db.execute('INSERT INTO drafts VALUES (?,?,?,?,?,?,?,?)',
                       (identifier, number, encoded(files), encoded(sorted(set(sources))), client['brand'],
                        client['version'], text(data.get('note'), 'revision note', 10000), datetime.now(timezone.utc).isoformat()))
            db.execute("UPDATE requests SET status='review',version=version+1 WHERE id=?", (identifier,))
            return {'id': identifier, 'draft': number}
        action = data.get('action')
        state = request['status']
        if action == 'start' and state == 'queued':
            db.execute("UPDATE requests SET status='active',version=version+1 WHERE id=?", (identifier,))
        elif action == 'priority' and state == 'queued':
            value = integer(data.get('priority'), 'priority')
            db.execute('UPDATE requests SET priority=?,version=version+1 WHERE id=?', (value, identifier))
        elif action == 'revise' and state == 'review':
            feedback = text(data.get('feedback'), 'feedback', 20000)
            db.execute("UPDATE requests SET status='revision',feedback=?,version=version+1 WHERE id=?", (feedback, identifier))
        elif action == 'deliver' and state == 'review':
            current = self.row(db, 'clients', request['client_id'])
            draft = db.execute('SELECT brand_version FROM drafts WHERE request_id=? ORDER BY number DESC LIMIT 1', (identifier,)).fetchone()
            if not draft or draft['brand_version'] != current['version']:
                raise DeskError('Brand/source library changed. Save an updated draft before delivery.', 409)
            db.execute("UPDATE requests SET status='delivered',version=version+1 WHERE id=?", (identifier,))
            next_item = db.execute("SELECT id FROM requests WHERE client_id=? AND status='queued' ORDER BY priority DESC,seq LIMIT 1", (request['client_id'],)).fetchone()
            if next_item:
                db.execute("UPDATE requests SET status='active',version=version+1 WHERE id=?", (next_item['id'],))
            return {'id': identifier, 'next_id': next_item['id'] if next_item else None, 'delivery': 'LOCAL_FILES_ONLY_NOT_SENT'}
        elif action == 'cancel' and state in ('queued', *ACTIVE):
            db.execute("UPDATE requests SET status='cancelled',version=version+1 WHERE id=?", (identifier,))
        else:
            raise DeskError('This action does not apply to the current request state', 409)
        return {'id': identifier}

    def export(self, identifier):
        state = self.snapshot()
        request = next((r for r in state['requests'] if r['id'] == identifier), None)
        if request is None:
            raise DeskError('Request not found', 404)
        if not request['drafts']:
            raise DeskError('No source files have been saved yet', 409)
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('request.json', encoded(request))
            archive.writestr('DELIVERY.txt', 'Editable copy files. Local handoff only; nothing was emailed or published.\n')
            for draft in request['drafts']:
                for name, content in draft['files'].items():
                    archive.writestr(f"revisions/{draft['number']}/{name}", content)
            for name, content in request['drafts'][-1]['files'].items():
                archive.writestr(f'current/{name}', content)
        return output.getvalue()


def load_example(desk):
    example = json.loads((ROOT / 'example.json').read_text(encoding='utf-8'))
    client = desk.write('client/create', {**example['client'], 'operation_id': 'example-client-v1'})['id']
    request = desk.write('request/create', {**example['request'], 'client_id': client, 'operation_id': 'example-request-v1'})['id']
    desk.write('request/action', {'id': request, 'version': 1, 'action': 'start', 'operation_id': 'example-start-v1'})
    desk.write('draft/save', {**example['draft'], 'id': request, 'version': 2, 'operation_id': 'example-draft-v1'})
    desk.write('request/create', {'client_id': client, 'title': 'Accounting CSV product-copy follow-through',
        'kind': 'Product copy', 'brief': 'Explain the review-ready CSV without implying accounting-system integration.',
        'priority': 0, 'operation_id': 'example-next-v1'})
    return request


def make_server(desk, host='127.0.0.1', port=8765):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Avoid writing customer request paths into access logs.

        def reply(self, status, body, kind='application/json; charset=utf-8', attachment=False):
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if attachment:
                self.send_header('Content-Disposition', 'attachment; filename="copy-delivery.zip"')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path == '/':
                    self.reply(200, (ROOT / 'index.html').read_bytes(), 'text/html; charset=utf-8')
                elif path == '/api/state':
                    self.reply(200, encoded(desk.snapshot()).encode('utf-8'))
                elif path.startswith('/api/export/'):
                    self.reply(200, desk.export(path.removeprefix('/api/export/')), 'application/zip', True)
                else:
                    raise DeskError('Not found', 404)
            except DeskError as exc:
                self.reply(exc.status, encoded({'error': str(exc)}).encode('utf-8'))

        def do_POST(self):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 2_000_000:
                    raise DeskError('JSON body must be between 1 and 2000000 bytes', 413)
                if self.headers.get_content_type() != 'application/json':
                    raise DeskError('Use application/json', 415)
                data = json.loads(self.rfile.read(length))
                result = desk.write(urlsplit(self.path).path.removeprefix('/api/'), data)
                self.reply(200, encoded(result).encode('utf-8'))
            except DeskError as exc:
                self.reply(exc.status, encoded({'error': str(exc)}).encode('utf-8'))
            except (ValueError, UnicodeError):
                self.reply(400, b'{"error":"Invalid JSON body"}')
            except sqlite3.OperationalError:
                self.reply(503, b'{"error":"Database is busy; retry with the same operation_id"}')
    return ThreadingHTTPServer((host, port), Handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='copy-desk.sqlite3')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--demo', action='store_true', help='Load editable Commons product sample once')
    args = parser.parse_args()
    desk = Desk(args.db)
    if args.demo:
        load_example(desk)
    server = make_server(desk, args.host, args.port)
    print(f'Copy desk: http://{args.host}:{server.server_port} — shared operator workspace; no email sends', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
