# SPDX-License-Identifier: Apache-2.0
"""Revision-checked SQLite persistence for the existing Hive prospect workspace."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import mimetypes
import re
import sqlite3
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

MAX_BYTES = 2_000_000


class Conflict(ValueError):
    pass


def reject_constant(value):
    raise ValueError(f'{value} is not a finite JSON number')


def parse_finite_float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        reject_constant(value)
    return parsed


class Store:
    """Persist the consumer's exact JSON text without changing its data model."""
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS workspace (
                  id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL,
                  payload TEXT, digest TEXT);
                INSERT OR IGNORE INTO workspace VALUES(1,0,NULL,NULL);
                CREATE TABLE IF NOT EXISTS operations (
                  operation_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                  revision INTEGER NOT NULL, digest TEXT, present INTEGER NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def read(self):
        with self.connect() as db:
            row = db.execute('SELECT * FROM workspace WHERE id=1').fetchone()
            return {'revision': row['revision'], 'payload': row['payload'],
                    'sha256': row['digest'], 'present': row['payload'] is not None}

    def write(self, payload, expected_revision, operation_id):
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('expected_revision must be a nonnegative integer')
        if not isinstance(operation_id, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', operation_id):
            raise ValueError('operation_id must contain 1-128 letters, digits, dots, colons, underscores or hyphens')
        if payload is not None:
            if not isinstance(payload, str) or len(payload.encode('utf-8')) > MAX_BYTES:
                raise ValueError('payload must be JSON text up to 2 MB, or null to delete')
            parsed = json.loads(payload, parse_constant=reject_constant, parse_float=parse_finite_float)
            if not isinstance(parsed, dict):
                raise ValueError('The workspace JSON root must be an object')
        digest = hashlib.sha256(payload.encode('utf-8')).hexdigest() if payload is not None else None
        fingerprint = hashlib.sha256(json.dumps([expected_revision, payload], ensure_ascii=False).encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT * FROM operations WHERE operation_id=?', (operation_id,)).fetchone()
            if previous:
                if previous['fingerprint'] != fingerprint:
                    raise Conflict('operation_id was already used for different bytes or revision')
                return {'revision': previous['revision'], 'sha256': previous['digest'],
                        'present': bool(previous['present']), 'status': 'already_applied'}
            current = db.execute('SELECT revision FROM workspace WHERE id=1').fetchone()[0]
            if current != expected_revision:
                raise Conflict(f'Workspace changed: expected revision {expected_revision}, current revision {current}. Load before saving.')
            revision = current + 1
            db.execute('UPDATE workspace SET revision=?,payload=?,digest=? WHERE id=1', (revision, payload, digest))
            db.execute('INSERT INTO operations VALUES(?,?,?,?,?)', (operation_id, fingerprint, revision, digest, payload is not None))
            return {'revision': revision, 'sha256': digest, 'present': payload is not None, 'status': 'saved'}


class Server(ThreadingHTTPServer):
    def __init__(self, address, store, assets):
        self.store = store
        self.assets = Path(assets).resolve()
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, body, content_type='application/json; charset=utf-8'):
        if not isinstance(body, (bytes, str)):
            body = json.dumps(body, ensure_ascii=False)
        data = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            if path == '/api/state':
                self.reply(200, self.server.store.read())
                return
            if path in ('/persistence.js', '/persistence.html'):
                kind = 'text/javascript' if path.endswith('.js') else 'text/html'
                self.reply(200, (Path(__file__).parent / path.lstrip('/')).read_bytes(), kind + '; charset=utf-8')
                return
            relative = 'index.html' if path == '/' else path.lstrip('/')
            target = (self.server.assets / relative).resolve()
            if not target.is_relative_to(self.server.assets) or target.suffix not in ('.html', '.js', '.css', '.svg', '.png', '.ico') or not target.is_file():
                self.reply(404, {'error': 'Asset not found'})
                return
            data = target.read_bytes()
            if relative == 'index.html':
                html = data.decode('utf-8')
                if '</body>' not in html:
                    raise ValueError('Consumer index.html has no closing body element')
                # Serve the exact existing UI plus one additive persistence panel.
                data = html.replace('</body>', '<iframe src="/persistence.html" title="Private SQLite backups" style="width:100%;height:360px;border:0;display:block"></iframe></body>', 1).encode('utf-8')
            kind = 'text/javascript' if target.suffix == '.js' else (mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
            self.reply(200, data, kind + ('; charset=utf-8' if kind.startswith('text/') else ''))
        except (ValueError, UnicodeError) as exc:
            self.reply(400, {'error': str(exc)})
        except (OSError, sqlite3.Error):
            self.reply(503, {'error': 'Workspace or assets unavailable'})

    def do_POST(self):
        try:
            if urlsplit(self.path).path != '/api/state':
                self.reply(404, {'error': 'Not found'})
                return
            if self.headers.get_content_type() != 'application/json':
                raise ValueError('Send application/json')
            origin = self.headers.get('Origin')
            if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                raise ValueError('Use this workspace page for changes')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BYTES * 6 + 4096:
                raise ValueError('Invalid request size')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Request must be an object')
            result = self.server.store.write(data['payload'], data['expected_revision'], data['operation_id'])
            self.reply(200, result)
        except Conflict as exc:
            self.reply(409, {'error': str(exc)})
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
            self.reply(400, {'error': str(exc)})
        except sqlite3.Error:
            self.reply(503, {'error': 'Database unavailable; retry the same operation ID and payload'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, help='Private SQLite file; its parent directory must exist')
    parser.add_argument('--assets', required=True, type=Path, help='Existing revenue/hive_prospect_workspace directory')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    if not (args.assets / 'index.html').is_file():
        parser.error('--assets must contain the existing workspace index.html')
    server = Server((args.host, args.port), Store(args.db), args.assets)
    print(f'Existing Hive workspace + SQLite at http://{args.host}:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
