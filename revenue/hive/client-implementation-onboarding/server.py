#!/usr/bin/env python3
"""Read-only loopback browser surface for the onboarding workspace."""
from __future__ import annotations
import argparse, html, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote
from onboarding import OnboardingError, compile_packet, connect_readonly, list_workspaces

ALLOWED_HOSTS = {"127.0.0.1", "localhost"}

class Handler(BaseHTTPRequestHandler):
    db_path = ""
    server_version = "OnboardingReadOnly/1"
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store"); self.send_header("X-Content-Type-Options", "nosniff"); self.end_headers(); self.wfile.write(body)
    def _json(self, code: int, obj) -> None: self._send(code, json.dumps(obj, sort_keys=True, ensure_ascii=False).encode(), "application/json; charset=utf-8")
    def do_GET(self):
        conn = None
        try:
            conn = connect_readonly(self.db_path)
            if self.path == "/api/workspaces": return self._json(200, {"workspaces": list_workspaces(conn), "readOnly": True})
            if self.path.startswith("/api/workspaces/"):
                wid = unquote(self.path[len("/api/workspaces/"):])
                return self._json(200, compile_packet(conn, wid))
            if self.path == "/":
                rows = list_workspaces(conn)
                lis = "".join(f"<li><code>{html.escape(r['workspaceId'])}</code> — {html.escape(r['kickoffState'])} — {html.escape(r['handoffState'])}</li>" for r in rows)
                body = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Client implementation onboarding</title>"
                        "<style>body{font:16px system-ui;max-width:920px;margin:3rem auto;padding:0 1rem}code{background:#eee;padding:.1rem .25rem}</style>"
                        "<h1>Client implementation onboarding</h1><p><strong>Read-only browser view.</strong> Mutations require the local CLI.</p><ul>" + lis + "</ul>").encode()
                return self._send(200, body, "text/html; charset=utf-8")
            return self._json(404, {"error":"not found"})
        except OnboardingError as exc: return self._json(400, {"error":str(exc)})
        finally:
            if conn is not None: conn.close()
    def _readonly(self): self._json(405, {"error":"read-only HTTP surface; use local CLI for mutation"})
    do_POST = _readonly; do_PUT = _readonly; do_PATCH = _readonly; do_DELETE = _readonly
    def log_message(self, fmt, *args): pass

def serve(db_path: str, host: str, port: int) -> None:
    if host not in ALLOWED_HOSTS: raise OnboardingError("server may bind only to 127.0.0.1 or localhost")
    if not isinstance(port, int) or isinstance(port, bool) or port < 0 or port > 65535: raise OnboardingError("invalid port")
    Handler.db_path = db_path
    httpd = ThreadingHTTPServer((host, port), Handler)
    try: httpd.serve_forever()
    finally: httpd.server_close()

if __name__ == "__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--db",required=True); ap.add_argument("--host",default="127.0.0.1"); ap.add_argument("--port",type=int,default=8765); a=ap.parse_args()
    try: serve(a.db,a.host,a.port)
    except OnboardingError as exc: raise SystemExit(str(exc))
