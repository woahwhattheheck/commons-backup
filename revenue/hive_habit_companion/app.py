#!/usr/bin/env python3
"""Run the private Paceboard workspace on the local loopback interface."""
from __future__ import annotations

import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from paceboard import MAX_BACKUP_BYTES, PaceboardError, Store, canonical_json, sha256_bytes

ROOT = Path(__file__).resolve().parent
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


def make_server(
    store: Store,
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    csrf_token: str | None = None,
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost"}:
        raise PaceboardError("Paceboard may bind only to the loopback host 127.0.0.1 or localhost", 400, "LOOPBACK_ONLY")
    token = csrf_token or secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        server_version = "Paceboard/1"
        sys_version = ""

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, *_args: object) -> None:
            # Trigger notes and private check-ins never enter request logs.
            return

        @property
        def expected_hosts(self) -> set[str]:
            bound_port = self.server.server_port
            return {
                f"127.0.0.1:{bound_port}",
                f"localhost:{bound_port}",
                "127.0.0.1" if bound_port == 80 else "",
                "localhost" if bound_port == 80 else "",
            } - {""}

        @property
        def expected_origins(self) -> set[str]:
            bound_port = self.server.server_port
            return {
                f"http://127.0.0.1:{bound_port}",
                f"http://localhost:{bound_port}",
            }

        def _authority(self, *, mutate: bool = False) -> None:
            host_header = self.headers.get("Host", "")
            if host_header not in self.expected_hosts:
                raise PaceboardError("Untrusted Host header", 421, "UNTRUSTED_HOST")
            if mutate:
                origin = self.headers.get("Origin")
                if origin is not None and origin not in self.expected_origins:
                    raise PaceboardError("Untrusted Origin header", 403, "UNTRUSTED_ORIGIN")
                supplied = self.headers.get("X-Paceboard-CSRF", "")
                if not secrets.compare_digest(supplied, token):
                    raise PaceboardError("Valid Paceboard CSRF token required", 403, "CSRF_REQUIRED")

        def _respond(
            self,
            status: int,
            body: bytes | dict[str, object] | list[object],
            content_type: str = "application/json; charset=utf-8",
            *,
            headers: dict[str, str] | None = None,
        ) -> None:
            if not isinstance(body, bytes):
                body = canonical_json(body)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _error(self, exc: PaceboardError) -> None:
            self._respond(exc.status, {"error": str(exc), "code": exc.code})

        def _json_body(self) -> dict[str, object]:
            if self.headers.get("Transfer-Encoding"):
                raise PaceboardError("Transfer-Encoding is not supported", 400, "FRAMING_REJECTED")
            if self.headers.get_content_type() != "application/json":
                raise PaceboardError("Use application/json", 415, "JSON_REQUIRED")
            raw_length = self.headers.get("Content-Length", "")
            if not raw_length.isdecimal():
                raise PaceboardError("Content-Length is required", 411, "LENGTH_REQUIRED")
            length = int(raw_length)
            if length <= 0 or length > MAX_BACKUP_BYTES:
                raise PaceboardError("Request body is outside the allowed size", 413, "BODY_TOO_LARGE")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise PaceboardError("Request body ended early", 400, "INCOMPLETE_BODY")
            try:
                value = json.loads(raw)
            except (UnicodeError, ValueError, RecursionError):
                raise PaceboardError("Request body is not valid JSON", 400, "INVALID_JSON") from None
            if not isinstance(value, dict):
                raise PaceboardError("Request JSON must be an object")
            return value

        def do_HEAD(self) -> None:  # noqa: N802
            self.do_GET()

        def do_GET(self) -> None:  # noqa: N802
            try:
                self._authority()
                path = urlsplit(self.path).path
                if path in STATIC_FILES:
                    filename, content_type = STATIC_FILES[path]
                    return self._respond(200, (ROOT / filename).read_bytes(), content_type)
                if path == "/api/health":
                    return self._respond(200, {"ok": True, "product": "Paceboard", "local_only": True})
                if path == "/api/state":
                    state = store.snapshot()
                    state["csrf_token"] = token
                    return self._respond(200, state)
                if path == "/api/export.json":
                    data = store.backup_bytes()
                    return self._respond(
                        200,
                        data,
                        "application/json; charset=utf-8",
                        headers={
                            "Content-Disposition": 'attachment; filename="paceboard-backup.json"',
                            "X-Content-SHA256": sha256_bytes(data),
                        },
                    )
                if path == "/api/export.csv":
                    data = store.timeline_csv_bytes()
                    return self._respond(
                        200,
                        data,
                        "text/csv; charset=utf-8",
                        headers={
                            "Content-Disposition": 'attachment; filename="paceboard-history.csv"',
                            "X-Content-SHA256": sha256_bytes(data),
                        },
                    )
                raise PaceboardError("Not found", 404, "NOT_FOUND")
            except PaceboardError as exc:
                self._error(exc)
            except (BrokenPipeError, ConnectionResetError):
                return

        def do_POST(self) -> None:  # noqa: N802
            try:
                self._authority(mutate=True)
                if urlsplit(self.path).path != "/api/change":
                    raise PaceboardError("Not found", 404, "NOT_FOUND")
                value = self._json_body()
                result = store.mutate(value.get("action"), value.get("operation_id"), value.get("payload"))
                self._respond(200, result)
            except PaceboardError as exc:
                self._error(exc)
            except TimeoutError:
                self._error(PaceboardError("Request timed out", 408, "TIMEOUT"))
            except (BrokenPipeError, ConnectionResetError):
                return

    server = ThreadingHTTPServer((host, port), Handler)
    server.csrf_token = token  # type: ignore[attr-defined]
    server.store = store  # type: ignore[attr-defined]
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="SQLite workspace file outside the source directory")
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    store = Store(args.db)
    server = make_server(store, args.host, args.port)
    print(f"Paceboard: http://{args.host}:{server.server_port}/", flush=True)
    print("Private local workspace. No cloud sync, tracking, external reminders, or medical claims.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
