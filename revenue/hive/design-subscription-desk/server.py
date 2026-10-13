#!/usr/bin/env python3
"""Local design production desk. Python stdlib only; no external service calls."""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import html
import io
import json
import re
import sqlite3
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
MAX_FILE = 4 * 1024 * 1024
MAX_BODY = 6 * 1024 * 1024
ACTIVE = ('production', 'review', 'revision')
DEFAULT_BRAND = {
    'name': 'Northstar Studio', 'tagline': 'Make room for your next good idea.',
    'accent': '#126b60', 'headline': 'Clear ideas. Thoughtful design. Room to grow.',
    'body': 'A fictional independent studio turning ambitious briefs into useful, expressive digital experiences.',
    'cta': 'Start a conversation', 'voice': 'Warm, clear, practical and quietly confident.',
}


class Problem(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def text(value, label, maximum=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise Problem(f'{label} must be nonempty text, at most {maximum} characters')
    return value.strip()


def integer(value, label, low=0, high=1_000_000):
    if type(value) is not int or not low <= value <= high:
        raise Problem(f'{label} must be an integer from {low} through {high}')
    return value


def object_(value):
    if not isinstance(value, dict):
        raise Problem('Expected a JSON object')
    return value


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def sample_sources(brand):
    """Editable, original HTML/CSS package; generated locally from supplied brand text."""
    e = lambda key: html.escape(brand[key], quote=True)
    css = f'''/* Editable brand tokens: no build step, fonts or external assets. */
:root{{--accent:{brand['accent']};--ink:#152c29;--paper:#f5f1e8;--line:#d9dfd4}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:18px/1.65 system-ui,sans-serif}}
a{{color:inherit}}.wrap{{max-width:1120px;margin:auto;padding:32px}}nav{{display:flex;justify-content:space-between;gap:20px;border-bottom:1px solid var(--line);padding-bottom:24px}}
.hero{{padding:100px 0 80px;max-width:900px}}.eyebrow{{text-transform:uppercase;letter-spacing:.17em;font-size:12px;color:var(--accent)}}h1{{font-size:clamp(46px,7vw,88px);line-height:1.05;letter-spacing:-.055em;margin:24px 0}}h2{{font-size:32px;line-height:1.2}}.lead{{font-size:22px;max-width:680px}}
.button{{display:inline-block;background:var(--accent);color:white;text-decoration:none;padding:14px 24px;border-radius:30px;margin-top:20px}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:28px;border-top:1px solid var(--line);padding:38px 0}}.num{{font-size:13px;color:var(--accent)}}footer{{padding:45px 0;border-top:1px solid var(--line);font-size:14px}}
@media(max-width:700px){{.wrap{{padding:24px}}.hero{{padding:60px 0}}.grid{{grid-template-columns:1fr}}nav{{flex-wrap:wrap}}}}
'''
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e('name')} — editable sample</title><link rel="stylesheet" href="tokens.css"></head>
<body><div class="wrap"><nav><strong>{e('name')}</strong><a href="#contact">{e('cta')}</a></nav>
<main><section class="hero"><p class="eyebrow">Independent studio · original sample</p><h1>{e('headline')}</h1><p class="lead">{e('body')}</p><a class="button" href="#contact">{e('cta')}</a></section>
<section class="grid" aria-label="Our approach"><article><span class="num">01 / CLARITY</span><h2>Start with the right question.</h2><p>A focused brief gives every design decision a purpose.</p></article><article><span class="num">02 / CRAFT</span><h2>Make the useful feel considered.</h2><p>Clear hierarchy, readable type and a generous rhythm bring ideas to life.</p></article><article><span class="num">03 / CONTINUITY</span><h2>Leave room for what comes next.</h2><p>Editable source files keep your next iteration in your hands.</p></article></section>
<section id="contact"><p class="eyebrow">{e('tagline')}</p><h2>Let’s make something useful.</h2><p>This is a fictional sample. Replace this block with your own verified contact information before publication. No message is sent from this page.</p></section></main>
<footer>{e('name')} · Editable original design sample. No client endorsement or business results claimed.</footer></div></body></html>
'''
    brand_doc = '\n'.join(['# Editable brand direction', '', 'Original fictional sample; not a customer delivery claim.', ''] + [f'**{k}:** {v}' for k, v in brand.items()]) + '\n'
    return {'landing.html': page.encode(), 'tokens.css': css.encode(), 'brand.md': brand_doc.encode(),
            'START-HERE.txt': b'Open landing.html beside tokens.css in a browser. Edit either file in any text editor. No dependencies or external assets. Brand direction is in brand.md. Replace fictional claims/contact block before publishing.\n'}


class Desk:
    def __init__(self, database):
        self.database = str(database)
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY,name TEXT NOT NULL,brand TEXT NOT NULL,version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id),title TEXT NOT NULL,brief TEXT NOT NULL,priority INTEGER NOT NULL,status TEXT NOT NULL,version INTEGER NOT NULL,created TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_request ON requests(workspace_id) WHERE status IN ('production','review','revision');
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,request_id TEXT NOT NULL REFERENCES requests(id),kind TEXT NOT NULL,note TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id),request_id TEXT REFERENCES requests(id),revision INTEGER NOT NULL,name TEXT NOT NULL,sha256 TEXT NOT NULL,content BLOB NOT NULL,created TEXT NOT NULL);
''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10, isolation_level='IMMEDIATE')
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def row(db, table, key):
        # Table names are internal constants, never request fields.
        row = db.execute(f'SELECT * FROM {table} WHERE id=?', (key,)).fetchone()
        if row is None:
            raise Problem('Not found', 404)
        return dict(row)

    @staticmethod
    def event(db, rid, kind, note):
        db.execute('INSERT INTO events(request_id,kind,note,created) VALUES(?,?,?,?)', (rid, kind, note, now()))

    def list_workspaces(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,name,version FROM workspaces ORDER BY rowid')]

    def create_workspace(self, data):
        object_(data)
        name = text(data.get('name'), 'Workspace name', 160)
        wid = uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO workspaces VALUES(?,?,?,1)', (wid, name, json.dumps(DEFAULT_BRAND)))
        return self.snapshot(wid)

    def snapshot(self, wid):
        with self.connect() as db:
            db.execute('BEGIN')
            ws = self.row(db, 'workspaces', wid)
            ws['brand'] = json.loads(ws['brand'])
            ws['requests'] = [dict(r) for r in db.execute('SELECT * FROM requests WHERE workspace_id=? ORDER BY priority,created,id', (wid,))]
            for req in ws['requests']:
                req['events'] = [dict(r) for r in db.execute('SELECT * FROM events WHERE request_id=? ORDER BY id', (req['id'],))]
            ws['assets'] = [dict(r) for r in db.execute('SELECT id,request_id,revision,name,sha256,length(content) AS size,created FROM assets WHERE workspace_id=? ORDER BY rowid', (wid,))]
            return ws

    def update_brand(self, wid, data):
        object_(data)
        version = integer(data.get('version'), 'Workspace version', 1)
        brand = object_(data.get('brand'))
        if set(brand) != set(DEFAULT_BRAND):
            raise Problem('Brand fields must match the supplied editor fields')
        clean = {k: text(brand[k], k, 2000) for k in DEFAULT_BRAND}
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', clean['accent']):
            raise Problem('Accent must be a six-digit hex color')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            ws = self.row(db, 'workspaces', wid)
            if ws['version'] != version:
                raise Problem('Workspace changed; reload before saving', 409)
            db.execute('UPDATE workspaces SET brand=?,version=version+1 WHERE id=?', (json.dumps(clean), wid))
        return self.snapshot(wid)

    def create_request(self, data):
        object_(data)
        wid = text(data.get('workspace_id'), 'Workspace ID', 40)
        title = text(data.get('title'), 'Title', 160)
        brief = text(data.get('brief'), 'Brief', 10000)
        priority = integer(data.get('priority', 100), 'Priority')
        rid = uuid4().hex
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.row(db, 'workspaces', wid)
            busy = db.execute("SELECT 1 FROM requests WHERE workspace_id=? AND status IN ('production','review','revision')", (wid,)).fetchone()
            state = 'queued' if busy else 'production'
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,1,?)', (rid, wid, title, brief, priority, state, now()))
            self.event(db, rid, 'submitted', f'Request entered {state}.')
        return {'request_id': rid, 'workspace': self.snapshot(wid)}

    def store_asset(self, db, wid, rid, revision, name, content):
        name = text(name, 'Filename', 160)
        if name in ('.', '..') or any(c in name for c in '/\\') or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise Problem('Filename must be a plain filename without control characters')
        if not content or len(content) > MAX_FILE:
            raise Problem('Files must be nonempty and at most 4 MiB')
        aid = uuid4().hex
        db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?)', (aid, wid, rid, revision, name, hashlib.sha256(content).hexdigest(), content, now()))
        return aid

    @staticmethod
    def decoded(data):
        encoded = data.get('content_base64')
        if not isinstance(encoded, str) or len(encoded) > ((MAX_FILE + 2) // 3) * 4:
            raise Problem('Expected base64 file content, at most 4 MiB decoded')
        try:
            return base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise Problem('Invalid base64 file content') from None

    def add_brand_asset(self, wid, data):
        object_(data)
        content = self.decoded(data)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.row(db, 'workspaces', wid)
            aid = self.store_asset(db, wid, None, 0, data.get('name'), content)
        return {'asset_id': aid, 'workspace': self.snapshot(wid)}

    def change_request(self, rid, data):
        object_(data)
        version = integer(data.get('version'), 'Request version', 1)
        action = text(data.get('action'), 'Action', 30)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            req = self.row(db, 'requests', rid)
            wid, state = req['workspace_id'], req['status']
            if req['version'] != version:
                raise Problem('Request changed; reload before saving', 409)
            note = ''
            if action == 'priority':
                if state != 'queued':
                    raise Problem('Only queued requests can be reprioritized', 409)
                priority = integer(data.get('priority'), 'Priority')
                db.execute('UPDATE requests SET priority=? WHERE id=?', (priority, rid))
                note = f'Priority set to {priority} (lower starts first).'
            elif action == 'brief':
                if state in ('complete', 'cancelled'):
                    raise Problem('Terminal requests are immutable', 409)
                brief = text(data.get('brief'), 'Brief', 10000)
                db.execute('UPDATE requests SET brief=? WHERE id=?', (brief, rid))
                note = brief
            elif action in ('asset', 'sample', 'deliver'):
                if state not in ('production', 'revision'):
                    raise Problem('Work must be in production or revision', 409)
                if action == 'asset':
                    self.store_asset(db, wid, rid, version + 1, data.get('name'), self.decoded(data))
                    note = f"Editable source uploaded: {data['name']}"
                elif action == 'sample':
                    brand = json.loads(self.row(db, 'workspaces', wid)['brand'])
                    for name, content in sample_sources(brand).items():
                        self.store_asset(db, wid, rid, version + 1, name, content)
                    state = 'review'
                    note = 'Original fictional brand + landing-page sample delivered from the current brand fields; all earlier source versions retained.'
                else:
                    if not db.execute('SELECT 1 FROM assets WHERE request_id=?', (rid,)).fetchone():
                        raise Problem('Upload editable source files before delivery', 409)
                    # A revision must include new sources after the most recent review request.
                    last = db.execute("SELECT created FROM events WHERE request_id=? AND kind='revise' ORDER BY id DESC LIMIT 1", (rid,)).fetchone()
                    if last and not db.execute('SELECT 1 FROM assets WHERE request_id=? AND created>?', (rid, last['created'])).fetchone():
                        raise Problem('Upload revised source files before redelivery', 409)
                    note = text(data.get('note'), 'Delivery note')
                    state = 'review'
            elif action == 'revise':
                if state != 'review':
                    raise Problem('Only a delivered request can be revised', 409)
                note = text(data.get('note'), 'Revision request')
                state = 'revision'
            elif action == 'approve':
                if state != 'review':
                    raise Problem('Only a delivered request can be approved', 409)
                state = 'complete'
                note = 'Delivery accepted. Next queued request enters production.'
            else:
                raise Problem('Unknown desk action')
            db.execute('UPDATE requests SET status=?,version=version+1 WHERE id=?', (state, rid))
            self.event(db, rid, action, note)
            if action == 'approve':
                next_req = db.execute("SELECT id FROM requests WHERE workspace_id=? AND status='queued' ORDER BY priority,created,id LIMIT 1", (wid,)).fetchone()
                if next_req:
                    db.execute("UPDATE requests SET status='production',version=version+1 WHERE id=?", (next_req['id'],))
                    self.event(db, next_req['id'], 'started', 'Previous request accepted; queue advanced automatically.')
        return self.snapshot(wid)

    def asset(self, aid):
        with self.connect() as db:
            return self.row(db, 'assets', aid)

    def export(self, rid):
        with self.connect() as db:
            db.execute('BEGIN')
            req = self.row(db, 'requests', rid)
            assets = [dict(r) for r in db.execute('SELECT * FROM assets WHERE request_id=? ORDER BY rowid', (rid,))]
            events = [dict(r) for r in db.execute('SELECT * FROM events WHERE request_id=? ORDER BY id', (rid,))]
        if not assets:
            raise Problem('No source files have been delivered', 409)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as archive:
            latest = {}
            manifest = []
            for a in assets:
                path = f"history/{a['revision']}/{a['id']}/{a['name']}"
                archive.writestr(path, a['content'])
                manifest.append({k: a[k] for k in ('id', 'revision', 'name', 'sha256', 'created')})
                latest[a['name']] = a['content']
            for name, content in latest.items():
                archive.writestr('current/' + name, content)
            archive.writestr('request.json', json.dumps(req, ensure_ascii=False, indent=2))
            archive.writestr('revisions.json', json.dumps(events, ensure_ascii=False, indent=2))
            archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        return buf.getvalue()


def handler_for(desk):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, body, mime='application/json; charset=utf-8', filename=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if filename:
                encoded = quote(filename, safe='')
                self.send_header('Content-Disposition', f"attachment; filename=source-file; filename*=UTF-8''{encoded}")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path == '/':
                    return self.reply(200, (ROOT / 'index.html').read_bytes(), 'text/html; charset=utf-8')
                if path == '/api/workspaces':
                    return self.reply(200, desk.list_workspaces())
                match = re.fullmatch(r'/api/workspaces/([a-f0-9]{32})', path)
                if match:
                    return self.reply(200, desk.snapshot(match[1]))
                match = re.fullmatch(r'/api/assets/([a-f0-9]{32})', path)
                if match:
                    asset = desk.asset(match[1])
                    return self.reply(200, asset['content'], 'application/octet-stream', asset['name'])
                match = re.fullmatch(r'/api/requests/([a-f0-9]{32})/export', path)
                if match:
                    return self.reply(200, desk.export(match[1]), 'application/zip', 'editable-delivery.zip')
                raise Problem('Not found', 404)
            except Problem as exc:
                self.reply(exc.status, {'error': str(exc)})
            except sqlite3.Error:
                self.reply(503, {'error': 'Storage unavailable; retry after reloading'})

        def do_POST(self):
            try:
                length = self.headers.get('Content-Length', '')
                if not length.isdecimal() or not 0 < int(length) <= MAX_BODY:
                    raise Problem('Expected a JSON body of at most 6 MiB', 413)
                if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                    raise Problem('Content-Type must be application/json', 415)
                try:
                    data = object_(json.loads(self.rfile.read(int(length))))
                except (ValueError, UnicodeDecodeError):
                    raise Problem('Malformed JSON') from None
                path = urlsplit(self.path).path
                if path == '/api/workspaces':
                    return self.reply(201, desk.create_workspace(data))
                if path == '/api/requests':
                    return self.reply(201, desk.create_request(data))
                match = re.fullmatch(r'/api/workspaces/([a-f0-9]{32})/(brand|assets)', path)
                if match:
                    result = desk.update_brand(match[1], data) if match[2] == 'brand' else desk.add_brand_asset(match[1], data)
                    return self.reply(200, result)
                match = re.fullmatch(r'/api/requests/([a-f0-9]{32})', path)
                if match:
                    return self.reply(200, desk.change_request(match[1], data))
                raise Problem('Not found', 404)
            except Problem as exc:
                self.reply(exc.status, {'error': str(exc)})
            except sqlite3.Error:
                self.reply(503, {'error': 'Storage unavailable; reload before retrying'})

        def log_message(self, *_args):
            pass
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--db', default=str(ROOT / 'data' / 'desk.sqlite3'))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), handler_for(Desk(args.db)))
    print(f'Design desk: http://{args.host}:{server.server_port} — database {args.db}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
