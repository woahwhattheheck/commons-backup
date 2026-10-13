"""HTTP/browser consumer. Transport pattern adapted from Hive Fleetline server.py
(blob 62044e5e231c0e3f66a8bfeb52f5fef1dfbdb7c0); existing files unchanged.
"""
from __future__ import annotations
import argparse
import json
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from desk import DeskError, Store

ROOT = Path(__file__).resolve().parent
MAX_BODY = 9 * 1024 * 1024


def strict_json(raw):
    def constant(_):
        raise ValueError('Non-finite number')
    def floating(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('Non-finite number')
        return result
    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise ValueError('Duplicate JSON key')
            obj[key] = value
        return obj
    return json.loads(raw, parse_constant=constant, parse_float=floating, object_pairs_hook=pairs)


def make_server(store, port=8089, host='127.0.0.1'):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Do not copy property/request details into default console logs.

        def send(self, status, body, mime='application/json; charset=utf-8', attachment=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            if attachment:
                self.send_header('Content-Disposition', f'attachment; filename="{attachment}"')
            self.end_headers()
            self.wfile.write(body)

        def run(self, action):
            try:
                action()
            except DeskError as exc:
                self.send(exc.status, {'error': str(exc)})
            except (UnicodeError, ValueError, TypeError, KeyError, RecursionError):
                self.send(400, {'error': 'Malformed request.'})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.send(500, {'error': 'Unable to complete this request. Retry with the same operation ID.'})

        def do_GET(self):
            self.run(self.get)

        def get(self):
            path = urlsplit(self.path).path
            assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                      '/index.html': ('index.html', 'text/html; charset=utf-8'),
                      '/app.js': ('app.js', 'text/javascript; charset=utf-8')}
            if path in assets:
                name, mime = assets[path]
                self.send(200, (ROOT / name).read_bytes(), mime)
            elif path == '/api/state':
                self.send(200, store.state())
            elif path == '/api/export':
                self.send(200, store.state(), attachment='tenant-maintenance.json')
            elif path.startswith('/api/photo/'):
                photo = store.photo(path[len('/api/photo/'):])
                suffix = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp'}[photo['mime']]
                # Keep caller-controlled filenames out of response headers.
                self.send(200, photo['data'], photo['mime'], 'maintenance-photo.' + suffix)
            else:
                raise DeskError('Not found.', 404)

        def do_POST(self):
            self.run(self.post)

        def post(self):
            if urlsplit(self.path).path != '/api/command':
                raise DeskError('Not found.', 404)
            if self.headers.get_content_type() != 'application/json':
                raise DeskError('Use application/json.', 415)
            if self.headers.get('Transfer-Encoding'):
                raise DeskError('Supply Content-Length rather than chunked encoding.')
            lengths = self.headers.get_all('Content-Length', [])
            if len(lengths) != 1:
                raise DeskError('Supply one Content-Length header.', 411)
            try:
                length = int(lengths[0])
            except ValueError as exc:
                raise DeskError('Invalid Content-Length.') from exc
            if not 0 < length <= MAX_BODY:
                raise DeskError('Body must be between 1 byte and 9 MiB.', 413)
            self.connection.settimeout(10)
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise DeskError('Incomplete request body.')
            data = strict_json(raw.decode('utf-8'))
            if not isinstance(data, dict):
                raise DeskError('Supply a JSON object with command and optional operation_id.')
            self.send(200, store.command(data.get('command'), data.get('operation_id')))

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description='Tenant maintenance desk — no external messages are sent.')
    parser.add_argument('--db', type=Path, required=True, help='SQLite path in your runtime data volume, outside source control.')
    parser.add_argument('--port', type=int, default=8089)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--demo', action='store_true', help='Add clearly labelled fictional fixtures; repeat-safe.')
    args = parser.parse_args()
    store = Store(args.db)
    if args.demo:
        store.seed_demo()
    with make_server(store, args.port, args.host) as server:
        print(f'Tenant desk: http://{args.host}:{server.server_port} — shared workspace, no messages sent.')
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
