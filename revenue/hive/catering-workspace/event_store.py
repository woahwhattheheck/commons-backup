#!/usr/bin/env python3
"""Optional durable storage for the existing Hive catering browser workspace.

The browser remains the calculation authority. This service preserves its JSON
without recalculating amounts, inferring dietary suitability or processing money.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit
import uuid

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 1_000_000


class InputError(ValueError):
    pass


class Conflict(ValueError):
    pass


def canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise InputError('Use a finite, JSON-serializable document') from exc


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def parse_json(data):
    def bad_number(value):
        raise InputError(f'Non-finite JSON number: {value}')
    try:
        return json.loads(data, object_pairs_hook=unique_object, parse_constant=bad_number)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise InputError(str(exc)) from exc


def revision_number(value):
    if type(value) is not int or not 0 <= value <= 2_147_483_647:
        raise InputError('expected_revision must be a nonnegative integer')
    return value


def label(value, field, maximum=200):
    if not isinstance(value, str) or len(value) > maximum:
        raise InputError(f'{field} must be text of at most {maximum} characters')
    return value


def event_key(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
        raise InputError('Event id must be the 32-character id returned by a save')
    return value


class Store:
    """Separate events, retained revisions, optimistic concurrency and retry dedupe."""

    def __init__(self, database):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    title TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions (
                    event_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    title TEXT NOT NULL, document TEXT NOT NULL,
                    sha256 TEXT NOT NULL, saved_at TEXT NOT NULL,
                    PRIMARY KEY (event_id, revision));
                CREATE TABLE IF NOT EXISTS operations (
                    id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL,
                    event_id TEXT NOT NULL, revision INTEGER NOT NULL);
            ''')

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(str(self.database), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _read(conn, key, revision=None):
        if revision is None:
            current = conn.execute('SELECT revision FROM events WHERE id=?', (key,)).fetchone()
            if current is None:
                raise KeyError(key)
            revision = current['revision']
        row = conn.execute('SELECT * FROM revisions WHERE event_id=? AND revision=?', (key, revision)).fetchone()
        if row is None:
            raise KeyError(key)
        return {'id': key, 'revision': row['revision'], 'title': row['title'],
                'document': json.loads(row['document']), 'sha256': row['sha256'], 'saved_at': row['saved_at']}

    def list(self):
        with self.connection() as conn:
            return [dict(row) for row in conn.execute('SELECT id, revision, title, updated_at FROM events ORDER BY updated_at DESC, id')]

    def get(self, key, revision=None):
        event_key(key)
        if revision is not None:
            revision_number(revision)
        with self.connection() as conn:
            return self._read(conn, key, revision)

    def history(self, key):
        event_key(key)
        with self.connection() as conn:
            if conn.execute('SELECT 1 FROM events WHERE id=?', (key,)).fetchone() is None:
                raise KeyError(key)
            return [dict(row) for row in conn.execute(
                'SELECT revision, title, sha256, saved_at FROM revisions WHERE event_id=? ORDER BY revision DESC', (key,))]

    def save(self, document, key=None, expected_revision=0, title='', operation_id=None):
        if not isinstance(document, dict):
            raise InputError('document must be a JSON object')
        encoded = canonical(document)
        if len(encoded.encode('utf-8')) > MAX_BYTES:
            raise InputError('Document exceeds the one-megabyte transport size')
        expected_revision = revision_number(expected_revision)
        title = label(title, 'title')
        if key is not None:
            event_key(key)
        if operation_id is not None:
            operation_id = label(operation_id, 'operation_id')
            if not operation_id:
                raise InputError('operation_id must be nonempty when supplied')
        payload = canonical({'document': document, 'id': key, 'expected_revision': expected_revision, 'title': title})
        request_sha = hashlib.sha256(payload.encode()).hexdigest()
        doc_sha = hashlib.sha256(encoded.encode()).hexdigest()
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if operation_id is not None:
                old = conn.execute('SELECT * FROM operations WHERE id=?', (operation_id,)).fetchone()
                if old is not None:
                    if old['request_sha256'] != request_sha:
                        raise Conflict('This operation_id already describes different save contents')
                    return self._read(conn, old['event_id'], old['revision'])
            if key is None:
                if expected_revision != 0:
                    raise Conflict('A new event begins with expected_revision 0')
                key, revision = uuid.uuid4().hex, 1
            else:
                current = conn.execute('SELECT revision FROM events WHERE id=?', (key,)).fetchone()
                if current is None:
                    raise KeyError(key)
                if current['revision'] != expected_revision:
                    raise Conflict('Saved event changed. Reopen it and compose the edits before saving.')
                revision = current['revision'] + 1
            saved_at = datetime.now(timezone.utc).isoformat()
            conn.execute('INSERT INTO revisions VALUES (?,?,?,?,?,?)', (key, revision, title, encoded, doc_sha, saved_at))
            conn.execute('INSERT INTO events VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision, title=excluded.title, updated_at=excluded.updated_at',
                         (key, revision, title, saved_at))
            if operation_id is not None:
                conn.execute('INSERT INTO operations VALUES (?,?,?,?)', (operation_id, request_sha, key, revision))
            return self._read(conn, key, revision)


def make_handler(store, root=ROOT):
    """Serve the existing UI and a same-origin JSON event API on loopback."""
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, *_args):
            pass  # Keep document contents and customer metadata out of access logs.

        def send_json(self, status, value):
            payload = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path == '/api/status':
                    self.send_json(200, {'service': 'hive-catering-event-store', 'schema_version': 1})
                elif path == '/api/events':
                    self.send_json(200, store.list())
                elif path.startswith('/api/events/'):
                    parts = path.strip('/').split('/')
                    if len(parts) == 3:
                        self.send_json(200, store.get(parts[2]))
                    elif len(parts) == 4 and parts[3] == 'revisions':
                        self.send_json(200, store.history(parts[2]))
                    elif len(parts) == 5 and parts[3] == 'revisions' and parts[4].isdigit():
                        self.send_json(200, store.get(parts[2], int(parts[4])))
                    else:
                        self.send_json(404, {'error': 'Route not found'})
                elif path.startswith('/api/'):
                    self.send_json(404, {'error': 'Route not found'})
                else:
                    super().do_GET()
            except InputError as exc:
                self.send_json(400, {'error': str(exc)})
            except KeyError:
                self.send_json(404, {'error': 'Event or revision not found'})
            except sqlite3.OperationalError:
                self.send_json(503, {'error': 'Storage is temporarily busy; retry the same save operation'})

        def do_POST(self):
            if urlsplit(self.path).path != '/api/events':
                self.send_json(404, {'error': 'Route not found'})
                return
            try:
                raw_length = self.headers.get('Content-Length', '')
                if not raw_length.isdigit() or not 0 < int(raw_length) <= MAX_BYTES:
                    raise InputError('Send a JSON request between one byte and one megabyte')
                body = parse_json(self.rfile.read(int(raw_length)))
                if not isinstance(body, dict):
                    raise InputError('Request must be a JSON object')
                result = store.save(body.get('document'), key=body.get('id'), expected_revision=body.get('expected_revision', 0),
                                    title=body.get('title', ''), operation_id=body.get('operation_id'))
                self.send_json(200, result)
            except InputError as exc:
                self.send_json(400, {'error': str(exc)})
            except Conflict as exc:
                self.send_json(409, {'error': str(exc)})
            except KeyError:
                self.send_json(404, {'error': 'Event not found'})
            except sqlite3.OperationalError:
                self.send_json(503, {'error': 'Storage is temporarily busy; retry the same save operation'})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=Path.home() / '.hive-catering' / 'event_store.sqlite3')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    # Database lives outside static assets, so serving the app cannot publish it.
    if args.database.resolve().is_relative_to(ROOT):
        parser.error('Choose a database location outside the browser asset directory')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(Store(args.database)))
    print(f'Catering workspace: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
