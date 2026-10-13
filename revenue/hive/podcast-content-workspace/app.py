#!/usr/bin/env python3
"""Podcast Content Desk: local, source-linked editing; no provider calls or sends."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import sqlite3
import uuid
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

HERE = Path(__file__).resolve().parent
MAX_JSON = 2 * 1024 * 1024
MAX_MEDIA = 64 * 1024 * 1024
MEDIA_TYPES = {'.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4',
               '.ogg': 'audio/ogg', '.flac': 'audio/flac', '.mp4': 'video/mp4',
               '.webm': 'video/webm'}


class Invalid(ValueError):
    pass


class Missing(LookupError):
    pass


class Conflict(RuntimeError):
    pass


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def text(value, label, maximum=2000, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()) or len(value) > maximum:
        raise Invalid(f'{label} must be {"a string" if empty else "nonempty text"} of at most {maximum} characters')
    if '\x00' in value:
        raise Invalid(f'{label} must not contain NUL characters')
    return value.strip()


def number(value, label):
    try:
        valid = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0
    except (OverflowError, ValueError):
        valid = False
    if not valid:
        raise Invalid(f'{label} must be a finite nonnegative number')
    return float(value)


def revision(value):
    if type(value) is not int or value < 1:
        raise Invalid('revision must be a positive integer')
    return value


def validate_document(value):
    if not isinstance(value, dict):
        raise Invalid('episode must be a JSON object')
    title = text(value.get('title'), 'title', 200)
    duration = number(value.get('duration'), 'duration')
    if not 0 < duration <= 86400:
        raise Invalid('duration must be greater than zero and at most 86400 seconds')
    description = text(value.get('description', ''), 'description', 5000, True)
    demo = value.get('synthetic_demo', False)
    if type(demo) is not bool:
        raise Invalid('synthetic_demo must be a boolean')
    segments = value.get('segments', [])
    if not isinstance(segments, list) or len(segments) > 2000:
        raise Invalid('segments must be a list of at most 2000 entries')
    normalized, seen, previous_end = [], set(), 0.0
    for i, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise Invalid(f'segment {i + 1} must be an object')
        sid = text(segment.get('id'), 'segment id', 80)
        if not re.fullmatch(r'[A-Za-z0-9_-]+', sid) or sid in seen:
            raise Invalid('segment ids must be unique letters, digits, underscores or hyphens')
        start, end = number(segment.get('start'), 'start'), number(segment.get('end'), 'end')
        if not start < end <= duration or start < previous_end:
            raise Invalid(f'{sid}: segments must be chronological, nonoverlapping and within duration')
        checked = segment.get('verified', False)
        if type(checked) is not bool:
            raise Invalid('verified must be a boolean')
        normalized.append({'id': sid, 'start': start, 'end': end,
                           'speaker': text(segment.get('speaker', ''), 'speaker', 120, True),
                           'text': text(segment.get('text'), 'segment text', 12000),
                           'verified': checked})
        seen.add(sid)
        previous_end = end
    chapters = value.get('chapters', [])
    if not isinstance(chapters, list) or len(chapters) > 100:
        raise Invalid('chapters must be a list of at most 100 entries')
    clean_chapters, previous = [], -1.0
    for chapter in chapters:
        if not isinstance(chapter, dict):
            raise Invalid('each chapter must be an object')
        start = number(chapter.get('start'), 'chapter start')
        if start >= duration or start <= previous:
            raise Invalid('chapter starts must increase and be within duration')
        clean_chapters.append({'start': start, 'title': text(chapter.get('title'), 'chapter title', 200)})
        previous = start
    return {'title': title, 'description': description, 'duration': duration,
            'synthetic_demo': demo, 'segments': normalized, 'chapters': clean_chapters}


def timestamp(seconds, separator='.'):
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3600000)
    minutes, millis = divmod(millis, 60000)
    secs, millis = divmod(millis, 1000)
    return f'{hours:02}:{minutes:02}:{secs:02}{separator}{millis:03}'


def md(value):
    """Escape imported text so it stays text, not executable markup or links."""
    value = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return re.sub(r'([\\`*_{}\[\]()#+.!|~-])', r'\\\1', value)


def block(value):
    return '\n'.join('> ' + md(line) for line in value.splitlines())


def document_hash(doc):
    return hashlib.sha256(json.dumps(doc, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def generate(doc, media_name=None):
    """Extractive drafts only: no invented quotations, paraphrases or speakers."""
    segments = doc['segments']
    if len(segments) < 5:
        raise Invalid('at least five transcript segments are required for five distinct posts')
    source = 'source-media/' + quote(media_name) if media_name else 'recording-not-attached'
    notice = ('SYNTHETIC DEMO — original scripted sample, not a customer episode.\n\n'
              if doc['synthetic_demo'] else '')
    notice += ('WORKING DRAFT — transcript excerpts are not automatically checked against audio. '
               'Review the recording, names and quotations before publication. Nothing has been sent.\n\n')

    def excerpt(s):
        speaker = f" — {md(s['speaker'])}" if s['speaker'] else ''
        status = 'operator-marked reviewed' if s['verified'] else 'unreviewed'
        return (f"### [{timestamp(s['start'])}]({source}#t={s['start']:g}){speaker}\n\n"
                f"{block(s['text'])}\n\nSource `{s['id']}` · {timestamp(s['start'])}–{timestamp(s['end'])} · {status}\n")

    excerpts = '\n'.join(excerpt(s) for s in segments)
    chapters = '\n'.join(f"- [{timestamp(c['start'])}]({source}#t={c['start']:g}) {md(c['title'])}"
                         for c in doc['chapters']) or '_No chapters entered._'
    notes = f"# {md(doc['title'])} — Show notes\n\n{notice}{md(doc['description'])}\n\n## Chapters\n\n{chapters}\n\n## Source excerpts\n\n{excerpts}"
    newsletter = (f"Subject: {doc['title']}\n\n# {md(doc['title'])}\n\n{notice}"
                  f"{md(doc['description'])}\n\n## From the conversation\n\n{excerpts}\n"
                  '## Before sending\n\nAdd your own introduction, context, links and subscriber-specific footer. '
                  'These excerpts are editable starting points, not automatic editorial synthesis.\n')
    groups = [segments[i * len(segments) // 5:(i + 1) * len(segments) // 5] for i in range(5)]
    posts = [f"# Post {i + 1}: {md(doc['title'])}\n\n{notice}" + '\n'.join(excerpt(s) for s in group)
             for i, group in enumerate(groups)]
    return {'show_notes': notes, 'newsletter': newsletter, 'posts': posts,
            'source_map': {f'post-{i + 1:02}': [s['id'] for s in group] for i, group in enumerate(groups)}}


def validate_drafts(value):
    if not isinstance(value, dict) or set(value) != {'show_notes', 'newsletter', 'posts'}:
        raise Invalid('drafts must contain show_notes, newsletter and posts only')
    posts = value['posts']
    if not isinstance(posts, list) or len(posts) != 5:
        raise Invalid('drafts must contain exactly five posts')
    return {'show_notes': text(value['show_notes'], 'show notes', 150000, True),
            'newsletter': text(value['newsletter'], 'newsletter', 150000, True),
            'posts': [text(p, 'post', 150000, True) for p in posts]}


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS episodes (
              id TEXT PRIMARY KEY, revision INTEGER NOT NULL, created TEXT NOT NULL,
              updated TEXT NOT NULL, document TEXT NOT NULL, drafts TEXT,
              draft_source_hash TEXT, media_name TEXT, media_type TEXT,
              media_sha256 TEXT, media BLOB)''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def public(row):
        doc = json.loads(row['document'])
        drafts = json.loads(row['drafts']) if row['drafts'] else None
        media = None
        if row['media_name']:
            media = {'name': row['media_name'], 'type': row['media_type'],
                     'sha256': row['media_sha256']}
        return {'id': row['id'], 'revision': row['revision'], 'created': row['created'],
                'updated': row['updated'], 'document': doc, 'drafts': drafts,
                'draft_source_hash': row['draft_source_hash'], 'media': media,
                'drafts_stale': bool(drafts and row['draft_source_hash'] != document_hash(doc))}

    def list(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT id, revision, updated, json_extract(document, '$.title') AS title FROM episodes ORDER BY updated DESC, id")]

    def get(self, eid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM episodes WHERE id=?', (eid,)).fetchone()
            if not row:
                raise Missing('episode not found')
            return self.public(row)

    def create(self, value):
        doc = validate_document(value)
        eid, now = uuid.uuid4().hex, utcnow()
        with self.connect() as db:
            db.execute('INSERT INTO episodes(id,revision,created,updated,document) VALUES(?,?,?,?,?)',
                       (eid, 1, now, now, json.dumps(doc, ensure_ascii=False, allow_nan=False)))
        return self.get(eid)

    def change(self, eid, expected, values):
        revision(expected)
        allowed = {'document', 'drafts', 'draft_source_hash', 'media_name', 'media_type', 'media_sha256', 'media'}
        if not values or not set(values) <= allowed:
            raise Invalid('invalid update')
        assignments = ','.join(f'{key}=?' for key in values)
        with self.connect() as db:
            cursor = db.execute(f'UPDATE episodes SET {assignments}, revision=revision+1, updated=? WHERE id=? AND revision=?',
                                (*values.values(), utcnow(), eid, expected))
            if cursor.rowcount != 1:
                if not db.execute('SELECT 1 FROM episodes WHERE id=?', (eid,)).fetchone():
                    raise Missing('episode not found')
                raise Conflict('episode changed in another tab; reload before applying your edits')
        return self.get(eid)

    def save_document(self, eid, expected, doc):
        doc = validate_document(doc)
        return self.change(eid, expected, {'document': json.dumps(doc, ensure_ascii=False, allow_nan=False)})

    def make_drafts(self, eid, expected, replace=False):
        row = self.get(eid)
        if row['drafts'] and not replace:
            raise Conflict('drafts already exist; explicitly choose replace to discard their edits')
        generated = generate(row['document'], row['media']['name'] if row['media'] else None)
        drafts = {k: generated[k] for k in ('show_notes', 'newsletter', 'posts')}
        return self.change(eid, expected, {'drafts': json.dumps(drafts, ensure_ascii=False),
                                          'draft_source_hash': document_hash(row['document'])})

    def save_drafts(self, eid, expected, drafts):
        return self.change(eid, expected, {'drafts': json.dumps(validate_drafts(drafts), ensure_ascii=False)})

    def upload(self, eid, expected, filename, data):
        filename = text(filename, 'media filename', 200)
        if '/' in filename or '\\' in filename or any(ord(c) < 32 or ord(c) == 127 for c in filename):
            raise Invalid('media filename must be a plain filename without control characters')
        extension = Path(filename).suffix.lower()
        if extension not in MEDIA_TYPES or not 0 < len(data) <= MAX_MEDIA:
            raise Invalid('media must be WAV, MP3, M4A, OGG, FLAC, MP4 or WEBM, up to 64 MiB')
        return self.change(eid, expected, {'media_name': filename, 'media_type': MEDIA_TYPES[extension],
                                          'media_sha256': hashlib.sha256(data).hexdigest(), 'media': data,
                                          'draft_source_hash': None})

    def media(self, eid):
        with self.connect() as db:
            row = db.execute('SELECT media_name,media_type,media_sha256,media FROM episodes WHERE id=?', (eid,)).fetchone()
            if not row or row['media'] is None:
                raise Missing('recording not attached')
            return dict(row)

    def delete(self, eid, expected):
        revision(expected)
        with self.connect() as db:
            cursor = db.execute('DELETE FROM episodes WHERE id=? AND revision=?', (eid, expected))
            if cursor.rowcount != 1:
                if not db.execute('SELECT 1 FROM episodes WHERE id=?', (eid,)).fetchone():
                    raise Missing('episode not found')
                raise Conflict('episode changed; reload before deleting')

    def export(self, eid):
        # One SQLite snapshot keeps transcript, edited drafts and media coherent.
        with self.connect() as db:
            row = db.execute('SELECT * FROM episodes WHERE id=?', (eid,)).fetchone()
            if not row:
                raise Missing('episode not found')
            episode = self.public(row)
            media = bytes(row['media']) if row['media'] is not None else None
        if not episode['drafts']:
            raise Invalid('generate drafts before exporting')
        doc, drafts = episode['document'], episode['drafts']
        current_groups = {f'post-{i + 1:02}': [s['id'] for s in doc['segments'][i * len(doc['segments']) // 5:(i + 1) * len(doc['segments']) // 5]] for i in range(5)}
        vtt = 'WEBVTT\n\n'
        srt = ''
        for i, segment in enumerate(doc['segments'], 1):
            # Caption files are plain text; strip cue delimiters embedded in text.
            caption = ((segment['speaker'] + ': ') if segment['speaker'] else '') + segment['text']
            caption = caption.replace('-->', '→')
            caption = re.sub(r'\n\s*\n', '\n', caption)
            vtt += f"{segment['id']}\n{timestamp(segment['start'])} --> {timestamp(segment['end'])}\n{caption}\n\n"
            srt += f"{i}\n{timestamp(segment['start'], ',')} --> {timestamp(segment['end'], ',')}\n{caption}\n\n"
        chapter_csv = io.StringIO(newline='')
        writer = csv.writer(chapter_csv)
        writer.writerow(['start_seconds', 'title'])
        for chapter in doc['chapters']:
            # Spreadsheet-safe display; authoritative exact titles stay in JSON.
            title = chapter['title']
            if title.startswith(('=', '+', '-', '@', '\t', '\r')):
                title = "'" + title
            writer.writerow([chapter['start'], title])
        manifest = {'episode_id': eid, 'revision': episode['revision'],
                    'synthetic_demo': doc['synthetic_demo'], 'media': episode['media'],
                    'document_sha256': document_hash(doc), 'draft_source_sha256': episode['draft_source_hash'],
                    'drafts_stale': episode['drafts_stale'],
                    'current_source_groups': current_groups,
                    'editorial_notice': 'Drafts are editable and may diverge from source. Review against the recording. No sending occurred.'}
        files = {'episode.json': json.dumps(episode, indent=2, ensure_ascii=False),
                 'transcript.json': json.dumps(doc, indent=2, ensure_ascii=False),
                 'transcript.vtt': vtt, 'transcript.srt': srt, 'chapters.csv': chapter_csv.getvalue(),
                 'source-map.json': json.dumps(manifest, indent=2, ensure_ascii=False),
                 'show-notes.md': drafts['show_notes'], 'newsletter.md': drafts['newsletter'],
                 'README.txt': 'Editable podcast content folder.\nOpen transcript.json to preserve exact text and timestamps.\nDrafts are extractive working copies, not automatic audio verification.\nThe current-source grouping in source-map.json is not a verification of edited drafts.\nUse the included original recording to review. No publishing or sending occurs.\n' + ('WARNING: drafts are stale relative to the current transcript or recording.\n' if episode['drafts_stale'] else '')}
        files.update({f'posts/post-{i + 1:02}.md': p for i, p in enumerate(drafts['posts'])})
        packet = io.BytesIO()
        with zipfile.ZipFile(packet, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, value in files.items():
                archive.writestr(name, value)
            if media is not None:
                archive.writestr('source-media/' + episode['media']['name'], media)
        return packet.getvalue()


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, store):
        self.store = store
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server: Server

    def log_message(self, format, *args):
        pass

    def send(self, status, body=b'', content_type='application/json; charset=utf-8', headers=None, head=False):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def json(self, status, value):
        self.send(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode())

    def body(self, maximum=MAX_JSON):
        value = self.headers.get('Content-Length')
        if value is None or not value.isdigit() or int(value) > maximum:
            raise Invalid(f'Content-Length must be provided and at most {maximum} bytes')
        self.connection.settimeout(15)
        content = self.rfile.read(int(value))
        if len(content) != int(value):
            raise Invalid('incomplete request body')
        return content

    def data(self):
        try:
            def constant(value):
                raise Invalid(f'nonfinite JSON number {value} is not supported')
            result = json.loads(self.body(), parse_constant=constant)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise Invalid('request must be valid UTF-8 JSON') from exc
        if not isinstance(result, dict):
            raise Invalid('request must be a JSON object')
        return result

    def dispatch(self, method):
        try:
            url = urlsplit(self.path)
            path = url.path
            if method in ('GET', 'HEAD') and path in ('/', '/index.html'):
                return self.send(200, (HERE / 'index.html').read_bytes(), 'text/html; charset=utf-8', head=method == 'HEAD')
            if path == '/api/episodes':
                if method == 'GET':
                    return self.json(200, self.server.store.list())
                if method == 'POST':
                    return self.json(201, self.server.store.create(self.data()))
            match = re.fullmatch(r'/api/episodes/([a-f0-9]{32})(?:/(media|generate|drafts|export))?', path)
            if not match:
                raise Missing('route not found')
            eid, action = match.groups()
            store = self.server.store
            if not action:
                if method == 'GET':
                    return self.json(200, store.get(eid))
                if method == 'PUT':
                    data = self.data()
                    return self.json(200, store.save_document(eid, data.get('revision'), data.get('document')))
                if method == 'DELETE':
                    store.delete(eid, self.data().get('revision'))
                    return self.json(200, {'deleted': eid})
            if action == 'generate' and method == 'POST':
                data = self.data()
                replace = data.get('replace', False)
                if type(replace) is not bool:
                    raise Invalid('replace must be a boolean')
                return self.json(200, store.make_drafts(eid, data.get('revision'), replace))
            if action == 'drafts' and method == 'PUT':
                data = self.data()
                return self.json(200, store.save_drafts(eid, data.get('revision'), data.get('drafts')))
            if action == 'media':
                if method == 'POST':
                    params = parse_qs(url.query)
                    rev = self.headers.get('If-Match', '')
                    if not rev.isdigit():
                        raise Invalid('If-Match must contain the episode revision')
                    return self.json(200, store.upload(eid, int(rev), params.get('filename', [''])[0], self.body(MAX_MEDIA)))
                if method in ('GET', 'HEAD'):
                    media = store.media(eid)
                    content = media['media']
                    headers = {'Accept-Ranges': 'bytes', 'ETag': '"' + media['media_sha256'] + '"',
                               'Content-Disposition': "inline; filename*=UTF-8''" + quote(media['media_name'])}
                    status = 200
                    value = self.headers.get('Range')
                    if value:
                        requested = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
                        if not requested or not any(requested.groups()):
                            return self.send(416, b'', headers={'Content-Range': f'bytes */{len(content)}'}, head=method == 'HEAD')
                        first, last = requested.groups()
                        if first:
                            start, end = int(first), min(int(last) if last else len(content) - 1, len(content) - 1)
                        else:
                            start, end = max(0, len(content) - int(last)), len(content) - 1
                        if start > end or start >= len(content):
                            return self.send(416, b'', headers={'Content-Range': f'bytes */{len(content)}'}, head=method == 'HEAD')
                        headers['Content-Range'] = f'bytes {start}-{end}/{len(content)}'
                        content, status = content[start:end + 1], 206
                    return self.send(status, content, media['media_type'], headers, head=method == 'HEAD')
            if action == 'export' and method == 'GET':
                return self.send(200, store.export(eid), 'application/zip',
                                 {'Content-Disposition': f'attachment; filename="episode-{eid}.zip"'})
            self.json(405, {'error': 'method not allowed'})
        except Invalid as exc:
            self.json(400, {'error': str(exc)})
        except Missing as exc:
            self.json(404, {'error': str(exc)})
        except Conflict as exc:
            self.json(409, {'error': str(exc)})
        except (sqlite3.Error, OSError) as exc:
            self.json(503, {'error': f'storage or transport unavailable: {type(exc).__name__}'})

    def do_GET(self):
        self.dispatch('GET')

    def do_HEAD(self):
        self.dispatch('HEAD')

    def do_POST(self):
        self.dispatch('POST')

    def do_PUT(self):
        self.dispatch('PUT')

    def do_DELETE(self):
        self.dispatch('DELETE')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8786)
    parser.add_argument('--db', type=Path, default=HERE / 'data' / 'workspace.sqlite3')
    parser.add_argument('--import-document', type=Path, help='Import timestamped transcript JSON and exit')
    parser.add_argument('--media', type=Path, help='Original recording to attach to an imported document')
    args = parser.parse_args()
    store = Store(args.db)
    if args.import_document:
        episode = store.create(json.loads(args.import_document.read_text(encoding='utf-8')))
        if args.media:
            episode = store.upload(episode['id'], episode['revision'], args.media.name, args.media.read_bytes())
        print(json.dumps({'id': episode['id'], 'revision': episode['revision']}))
        return
    if args.media:
        parser.error('--media requires --import-document')
    server = Server((args.host, args.port), store)
    print(f'Podcast Content Desk: http://{args.host}:{server.server_port} | database: {args.db}', flush=True)
    print('Single-workspace local application. No account system, outbound calls or automatic publishing.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
