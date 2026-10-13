"""Loopback-only Fleetline HTTP desk. No external service calls or mail sending."""
from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fleet import FleetError, Store

ROOT = Path(__file__).resolve().parent
MAX_BODY = 128 * 1024


def strict_json(raw):
    def constant(value):
        raise ValueError('Non-finite number')
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, parse_constant=constant, object_pairs_hook=object_pairs)


def make_server(store, port=8086):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Request paths and customer fields do not enter default console logs.
            pass

        def send(self, status, body, content_type='application/json; charset=utf-8', filename=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                             "script-src 'self'; connect-src 'self'; img-src 'self' data:; "
                             "base-uri 'none'; object-src 'none'; frame-ancestors 'none'")
            if filename:
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def run(self, action):
            try:
                action()
            except FleetError as exc:
                self.send(exc.status, {'error': str(exc)})
            except (UnicodeError, ValueError, TypeError, KeyError, RecursionError):
                self.send(400, {'error': 'Malformed request.'})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.send(500, {'error': 'The request could not be completed. Refresh or retry with the same operation ID.'})

        def do_GET(self):
            self.run(self.get)

        def get(self):
            url = urlsplit(self.path)
            if url.path in ('/', '/index.html', '/app.js'):
                target = ROOT / ('index.html' if url.path == '/' else url.path[1:])
                mime = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
                self.send(200, target.read_bytes(), mime + '; charset=utf-8')
                return
            params = parse_qs(url.query)
            def param(name):
                if len(params.get(name, [])) != 1:
                    raise FleetError(f'Supply exactly one {name}.')
                return params[name][0]
            if url.path == '/api/state':
                self.send(200, store.state())
            elif url.path == '/api/availability':
                self.send(200, store.availability(param('start'), param('end')))
            elif url.path == '/api/message':
                self.send(200, store.message(param('id')))
            elif url.path == '/api/export':
                self.send(200, store.export(), filename='fleetline-export.json')
            else:
                raise FleetError('Not found.', 404)

        def do_POST(self):
            self.run(self.post)

        def post(self):
            if urlsplit(self.path).path != '/api/command':
                raise FleetError('Not found.', 404)
            if self.headers.get_content_type() != 'application/json':
                raise FleetError('Use application/json.', 415)
            if self.headers.get('Transfer-Encoding'):
                raise FleetError('Supply Content-Length instead of chunked encoding.', 400)
            lengths = self.headers.get_all('Content-Length', [])
            if len(lengths) != 1:
                raise FleetError('Supply one Content-Length header.', 411)
            try:
                length = int(lengths[0])
            except ValueError as exc:
                raise FleetError('Invalid Content-Length.') from exc
            if not 0 < length <= MAX_BODY:
                raise FleetError('Request body must be between 1 and 131072 bytes.', 413)
            self.connection.settimeout(10)
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise FleetError('Incomplete request body.')
            data = strict_json(raw.decode('utf-8'))
            if not isinstance(data, dict) or set(data) - {'command', 'operation_id'}:
                raise FleetError('Supply command and optional operation_id only.')
            self.send(200, store.command(data.get('command'), data.get('operation_id')))

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description='Fleetline rental operations desk (loopback only).')
    parser.add_argument('--db', type=Path, default=Path.home() / '.fleetline' / 'fleet.sqlite')
    parser.add_argument('--port', type=int, default=8086)
    args = parser.parse_args()
    with make_server(Store(args.db), args.port) as server:
        print(f'Fleetline: http://127.0.0.1:{server.server_port} — local workspace, no messages or payments sent.')
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
