#!/usr/bin/env python3
"""Local rough-cut workspace. Python standard library + FFmpeg; no account required."""
from __future__ import annotations

import argparse
from copy import deepcopy
from contextlib import contextmanager
import json
import mimetypes
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

import roughcut as core

MAX_UPLOAD = 2 * 1024**3
MAX_JSON = 6 * 1024**2


class Conflict(core.EditError):
    pass


class Store:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root/'media').mkdir(exist_ok=True)
        (self.root/'exports').mkdir(exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
              document TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS revisions(project_id TEXT NOT NULL, revision INTEGER NOT NULL,
              document TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY(project_id,revision));
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root/'workspace.sqlite3', timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def key(value: str) -> str:
        if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value):
            raise core.EditError('Invalid project/export id')
        return value

    def source(self, ident: str) -> Path:
        return self.root/'media'/self.key(ident)/'original'

    def create(self, source: Path, filename: str) -> dict:
        ident = uuid.uuid4().hex
        folder = self.source(ident).parent
        folder.mkdir()
        try:
            shutil.copyfile(source, self.source(ident))
            document = core.new_project(self.source(ident), Path(filename).stem[:300])
            # The upload name is display metadata, never a filesystem destination.
            document['source']['name'] = Path(filename).name[:300] or 'recording'
            raw = json.dumps(document, ensure_ascii=False, allow_nan=False)
            with self.connect() as db:
                db.execute('INSERT INTO projects(id,revision,document) VALUES(?,1,?)', (ident, raw))
                db.execute('INSERT INTO revisions(project_id,revision,document) VALUES(?,1,?)', (ident, raw))
        except BaseException:
            shutil.rmtree(folder)
            raise
        return self.get(ident)

    def get(self, ident: str, revision: int | None = None) -> dict:
        self.key(ident)
        with self.connect() as db:
            if revision is None:
                row = db.execute('SELECT revision,document FROM projects WHERE id=?', (ident,)).fetchone()
            else:
                row = db.execute('SELECT revision,document FROM revisions WHERE project_id=? AND revision=?',
                                 (ident, revision)).fetchone()
        if row is None:
            raise FileNotFoundError('Project/revision not found')
        project = json.loads(row['document'])
        return {'id': ident, 'revision': row['revision'], 'project': project, 'timeline': core.timeline(project)}

    def list(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute('SELECT id,revision,document FROM projects ORDER BY created DESC,id').fetchall()
        return [{'id': r['id'], 'revision': r['revision'], 'title': json.loads(r['document'])['title']} for r in rows]

    def history(self, ident: str) -> list[dict]:
        self.get(ident)
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT revision,created FROM revisions WHERE project_id=? ORDER BY revision DESC', (ident,))]

    def update(self, ident: str, expected: int, changes: dict) -> dict:
        if type(expected) is not int or expected < 1:
            raise core.EditError('expected_revision must be a positive integer')
        if not isinstance(changes, dict):
            raise core.EditError('changes must be an object')
        if set(changes) - {'title', 'cuts', 'cues'}:
            raise core.EditError('Edit title, cuts and cues; original source metadata is immutable')
        current = self.get(ident)
        if current['revision'] != expected:
            raise Conflict('A newer revision exists. Reopen it before composing your edits.')
        project = deepcopy(current['project'])
        project.update(changes)
        core.validate(project)
        raw = json.dumps(project, ensure_ascii=False, allow_nan=False)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            cursor = db.execute('UPDATE projects SET revision=?,document=? WHERE id=? AND revision=?',
                                (expected+1, raw, ident, expected))
            if cursor.rowcount != 1:
                raise Conflict('A concurrent edit won. Your saved revision was not replaced.')
            db.execute('INSERT INTO revisions(project_id,revision,document) VALUES(?,?,?)', (ident, expected+1, raw))
        return self.get(ident, expected+1)

    def export(self, ident: str, revision: int) -> dict:
        if type(revision) is not int or revision < 1:
            raise core.EditError('revision must be a positive integer')
        snapshot = self.get(ident, revision)
        export_id = uuid.uuid4().hex
        path = self.root/'exports'/ident/export_id
        result = core.export_bundle(self.source(ident), snapshot['project'], path)
        return {'id': export_id, 'project_id': ident, 'revision': revision, 'timeline': result,
                'video': f'/exports/{ident}/{export_id}/roughcut.mp4',
                'zip': f'/exports/{ident}/{export_id}/editable-export.zip'}


def make_server(store: Store, port=8788, host='127.0.0.1') -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = 'Roughcut/1'

        def log_message(self, *_):
            pass

        def json_response(self, data, status=200):
            body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def length(self, maximum):
            if self.headers.get('Transfer-Encoding'):
                raise core.EditError('Send a Content-Length rather than chunked upload')
            try:
                n = int(self.headers.get('Content-Length', '-1'))
            except ValueError as exc:
                raise core.EditError('Content-Length must be an integer') from exc
            if not 0 <= n <= maximum:
                raise core.EditError(f'Request body must be at most {maximum} bytes')
            return n

        def read_json(self):
            n = self.length(MAX_JSON)
            raw = self.rfile.read(n)
            if len(raw) != n:
                raise core.EditError('Incomplete request body')
            try:
                data = json.loads(raw)
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise core.EditError('Invalid JSON body') from exc
            if not isinstance(data, dict):
                raise core.EditError('JSON body must be an object')
            return data

        def send_file(self, path: Path, mime=None, download=False):
            if not path.is_file():
                raise FileNotFoundError('File not found')
            with path.open('rb') as f:
                size = path.stat().st_size
                start, end, status = 0, size-1, 200
                header = self.headers.get('Range')
                if header:
                    match = re.fullmatch(r'bytes=(\d*)-(\d*)', header)
                    valid = bool(match and any(match.groups()) and size)
                    if valid:
                        left, right = match.groups()
                        if left:
                            start, end = int(left), min(int(right) if right else size-1, size-1)
                        else:
                            amount = int(right)
                            start, end = max(0, size-amount), size-1
                        valid = 0 <= start <= end < size
                    if not valid:
                        self.send_response(416)
                        self.send_header('Content-Range', f'bytes */{size}')
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    status = 206
                self.send_response(status)
                self.send_header('Content-Type', mime or mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
                self.send_header('Content-Length', str(max(0, end-start+1)))
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('X-Content-Type-Options', 'nosniff')
                if status == 206:
                    self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                if download:
                    self.send_header('Content-Disposition', f'attachment; filename="{path.name}"')
                self.end_headers()
                f.seek(start)
                remaining = end-start+1
                while remaining > 0:
                    block = f.read(min(1024*1024, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)

        def dispatch(self):
            parts = urlsplit(self.path).path.strip('/').split('/')
            if self.command == 'GET':
                if parts == ['']:
                    return self.send_file(Path(__file__).with_name('desk.html'), 'text/html; charset=utf-8')
                if parts == ['api', 'projects']:
                    return self.json_response(store.list())
                if len(parts) >= 3 and parts[:2] == ['api', 'projects']:
                    ident = store.key(parts[2])
                    if len(parts) == 3:
                        return self.json_response(store.get(ident))
                    if parts[3:] == ['history']:
                        return self.json_response(store.history(ident))
                    if len(parts) == 5 and parts[3] == 'revision':
                        return self.json_response(store.get(ident, int(parts[4])))
                    if parts[3:] == ['source']:
                        snap = store.get(ident)
                        mime = mimetypes.guess_type(snap['project']['source']['name'])[0] or 'video/mp4'
                        return self.send_file(store.source(ident), mime)
                if len(parts) == 4 and parts[0] == 'exports':
                    ident, eid, filename = store.key(parts[1]), store.key(parts[2]), parts[3]
                    if filename in {'roughcut.mp4', 'editable-export.zip', 'captions.vtt', 'captions.srt', 'project.json', 'timeline.json', 'kept-intervals.csv', 'manifest.json', 'REVIEW.txt'}:
                        return self.send_file(store.root/'exports'/ident/eid/filename, download=filename != 'roughcut.mp4')
            elif self.command == 'POST':
                if parts == ['api', 'upload']:
                    n = self.length(MAX_UPLOAD)
                    if not n:
                        raise core.EditError('Select a nonempty recording')
                    with tempfile.TemporaryDirectory(dir=store.root) as tmp:
                        path = Path(tmp)/'upload'
                        with path.open('wb') as f:
                            remaining = n
                            while remaining:
                                block = self.rfile.read(min(1024*1024, remaining))
                                if not block:
                                    raise core.EditError('Incomplete recording upload')
                                f.write(block)
                                remaining -= len(block)
                        return self.json_response(store.create(path, unquote(self.headers.get('X-Filename', 'recording.mp4'))), 201)
                if len(parts) == 4 and parts[:2] == ['api', 'projects']:
                    ident, action = store.key(parts[2]), parts[3]
                    data = self.read_json()
                    if action == 'save':
                        return self.json_response(store.update(ident, data.get('expected_revision'), data.get('changes')))
                    if action == 'transcript':
                        snap = store.get(ident)
                        cues = core.parse_captions(data.get('text'), snap['project']['source']['frames'])
                        return self.json_response(store.update(ident, data.get('expected_revision'), {'cues': cues}))
                    if action == 'suggest':
                        snap = store.get(ident, data.get('revision'))
                        project = snap['project']
                        suggestions = core.silence_suggestions(store.source(ident), project) + core.repeated_takes(project)
                        return self.json_response({'revision': snap['revision'], 'suggestions': suggestions[:core.MAX_CUTS], 'automatically_applied': False})
                    if action == 'export':
                        return self.json_response(store.export(ident, data.get('revision')), 201)
            raise FileNotFoundError('Route not found')

        def handle_method(self):
            self.connection.settimeout(60)
            try:
                self.dispatch()
            except Conflict as exc:
                self.json_response({'error': str(exc)}, 409)
            except FileNotFoundError as exc:
                self.json_response({'error': str(exc)}, 404)
            except (core.EditError, ValueError, KeyError, TypeError) as exc:
                self.json_response({'error': str(exc)}, 400)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except (OSError, sqlite3.Error) as exc:
                self.json_response({'error': f'Workspace operation failed: {exc}'}, 500)

        do_GET = handle_method
        do_POST = handle_method

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path('roughcut-workspace'))
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8788)
    args = parser.parse_args()
    server = make_server(Store(args.workspace), args.port, args.host)
    print(f'Roughcut desk: http://{args.host}:{server.server_address[1]}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
