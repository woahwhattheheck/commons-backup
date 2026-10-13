#!/usr/bin/env python3
"""Loopback Host router/runtime for isolated Creator Desk communities."""
from __future__ import annotations

import contextlib
import hashlib
import http.client
import ipaddress
import json
import socket
import sqlite3
import tempfile
import threading
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app import make_server
from toolkit import Store
from workspace_copy import CopyError, _check as check_workspace_snapshot
from multisite_registry import (
    MAX_PROXY_BODY, ALLOWED_REQUEST_HEADERS, ALLOWED_RESPONSE_HEADERS, HOP_BY_HOP,
    CommunitySpec, Registry, RegistryError,
)

def _snapshot_bytes_anchored(database: Path, *, max_bytes: int = MAX_PROXY_BODY, timeout_seconds: int = 30):
    """Snapshot one retained database generation without resolving it back to a mutable pathname."""
    deadline = time.monotonic() + timeout_seconds
    with tempfile.TemporaryDirectory(prefix="creator-multisite-download-") as folder:
        destination = Path(folder) / "creator-workspace.sqlite3"
        try:
            with closing(sqlite3.connect(str(database), timeout=5)) as original:
                original.execute("PRAGMA query_only=ON")
                page_size = original.execute("PRAGMA page_size").fetchone()[0]
                if original.execute("PRAGMA page_count").fetchone()[0] * page_size > max_bytes:
                    raise CopyError("Workspace exceeds this multisite snapshot size limit")

                def progress(_status, _remaining, total):
                    if total * page_size > max_bytes:
                        raise CopyError("Workspace exceeds this multisite snapshot size limit")
                    if time.monotonic() > deadline:
                        raise CopyError("Snapshot timed out; source was left in place")

                with closing(sqlite3.connect(destination)) as snapshot:
                    original.backup(snapshot, pages=256, progress=progress, sleep=0.01)
                    check_workspace_snapshot(snapshot)
            data = destination.read_bytes()
        except sqlite3.Error as exc:
            raise CopyError("Could not read a complete Creator Desk SQLite workspace") from exc
        if len(data) > max_bytes:
            raise CopyError("Workspace exceeds this multisite snapshot size limit")
        return data, hashlib.sha256(data).hexdigest()


@dataclass
class TenantRuntime:
    spec: CommunitySpec
    store: Store
    auth: object | None  # Legacy metadata only; no access decision.
    server: ThreadingHTTPServer
    thread: threading.Thread


class MultiSiteRuntime:
    """Run isolated loopback Creator Desk servers behind one host router."""

    def __init__(self, registry: Registry, *, bind_host="127.0.0.1", port=0):
        if bind_host not in {"127.0.0.1", "localhost"}:
            try:
                if not ipaddress.ip_address(bind_host).is_loopback:
                    raise ValueError
            except ValueError:
                raise RegistryError("multisite runtime may bind only to a loopback address") from None
        self.registry = registry
        self.bind_host = bind_host
        self.port = port
        self.tenants: dict[str, TenantRuntime] = {}
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self._started = False

    def start(self):
        if self._started:
            raise RuntimeError("multisite runtime already started")
        started = []
        try:
            for spec in self.registry.specs:
                # The registry owns retained root/workspace/database generations.
                # Existing Creator Desk layers receive the retained database through
                # /proc/self/fd, so their SQLite reopen cannot be redirected by a
                # pathname swap after this check. Reassert the logical-name binding
                # around each lower-layer constructor and fail closed on drift.
                self.registry.assert_spec(spec)
                store = Store(spec.database)
                self.registry.assert_spec(spec)
                server = make_server(store, "127.0.0.1", 0)
                thread = threading.Thread(
                    target=server.serve_forever,
                    kwargs={"poll_interval": 0.05},
                    name=f"creator-tenant-{spec.community_id}",
                    daemon=True,
                )
                thread.start()
                tenant = TenantRuntime(spec, store, None, server, thread)
                self.tenants[spec.community_id] = tenant
                started.append(tenant)
            self.server = _make_router_server(self, self.bind_host, self.port)
            self.thread = threading.Thread(
                target=self.server.serve_forever,
                kwargs={"poll_interval": 0.05},
                name="creator-multisite-router",
                daemon=True,
            )
            self.thread.start()
            self._started = True
            return self
        except Exception:
            if self.server is not None:
                with contextlib.suppress(Exception):
                    self.server.server_close()
            for tenant in reversed(started):
                with contextlib.suppress(Exception):
                    tenant.server.shutdown()
                with contextlib.suppress(Exception):
                    tenant.server.server_close()
                tenant.thread.join(timeout=2)
            self.tenants.clear()
            raise

    @property
    def address(self):
        if not self.server:
            raise RuntimeError("runtime is not started")
        return self.server.server_address

    def close(self):
        if self.server is not None:
            with contextlib.suppress(Exception):
                self.server.shutdown()
            with contextlib.suppress(Exception):
                self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=3)
        for tenant in reversed(tuple(self.tenants.values())):
            with contextlib.suppress(Exception):
                tenant.server.shutdown()
            with contextlib.suppress(Exception):
                tenant.server.server_close()
            tenant.thread.join(timeout=3)
        self.tenants.clear()
        self.server = None
        self.thread = None
        self._started = False

    def __enter__(self):
        return self.start()

    def __exit__(self, *_exc):
        self.close()


def _make_router_server(runtime: MultiSiteRuntime, host: str, port: int):
    class RouterHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, *_args):
            # Host routing must not leak capabilities/member data through access logs.
            pass

        def _json_error(self, code, message):
            raw = json.dumps({"error": message}, separators=(",", ":"), sort_keys=True).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(raw)
            self.close_connection = True

        def _route(self):
            values = self.headers.get_all("Host") or []
            if len(values) != 1:
                raise RegistryError("exactly one Host header is required")
            spec = runtime.registry.resolve(values[0])
            return spec, runtime.tenants[spec.community_id]

        def _body(self):
            if self.headers.get("Transfer-Encoding") is not None:
                raise RegistryError("Transfer-Encoding is unsupported")
            values = self.headers.get_all("Content-Length") or []
            if len(values) > 1:
                raise RegistryError("multiple Content-Length headers are unsupported")
            if not values:
                return None
            value = values[0]
            if not value.isdecimal() or (len(value) > 1 and value.startswith("0")):
                raise RegistryError("Content-Length must be canonical decimal text")
            length = int(value)
            if length > MAX_PROXY_BODY:
                raise OverflowError
            data = self.rfile.read(length)
            if len(data) != length:
                raise RegistryError("request body was truncated")
            return data

        def _proxy(self):
            try:
                if not self.path.startswith("/"):
                    raise RegistryError("request target must use origin-form")
                spec, tenant = self._route()
                # Framing is validated before every successful route, including the
                # control-plane health endpoint. This prevents unread request bytes
                # from becoming a second HTTP/1.1 request on the same connection.
                body = self._body()
                route_path = urlsplit(self.path).path
                if route_path == "/__multisite/health":
                    if self.command not in {"GET", "HEAD"}:
                        self._json_error(405, "health endpoint supports only GET and HEAD")
                        return
                    if body not in (None, b""):
                        self._json_error(400, "health endpoint does not accept a request body")
                        return
                    raw = json.dumps(
                        {"community_id": spec.community_id, "host": spec.host, "status": "ok"},
                        separators=(",", ":"), sort_keys=True,
                    ).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Creator-Community", spec.community_id)
                    self.send_header("Connection", "close")
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(raw)
                    self.close_connection = True
                    return
                if route_path == "/workspace.sqlite3":
                    if self.command not in {"GET", "HEAD"}:
                        self._json_error(405, "workspace snapshot supports only GET and HEAD")
                        return
                    if body not in (None, b""):
                        self._json_error(400, "workspace snapshot does not accept a request body")
                        return
                    runtime.registry.assert_spec(spec)
                    try:
                        snapshot, digest = _snapshot_bytes_anchored(spec.database)
                    except CopyError as exc:
                        self._json_error(409, str(exc))
                        return
                    runtime.registry.assert_spec(spec)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(len(snapshot)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("Referrer-Policy", "no-referrer")
                    self.send_header("Content-Disposition", 'attachment; filename="creator-workspace.sqlite3"')
                    self.send_header("X-Content-SHA256", digest)
                    self.send_header("X-Creator-Community", spec.community_id)
                    self.send_header("Connection", "close")
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(snapshot)
                    self.close_connection = True
                    return
                conn = http.client.HTTPConnection("127.0.0.1", tenant.server.server_port, timeout=15)
                try:
                    # Manual request assembly avoids http.client silently manufacturing
                    # a body/Content-Length that the source request did not provide.
                    conn.putrequest(self.command, self.path, skip_host=False, skip_accept_encoding=True)
                    for name, value in self.headers.items():
                        lower = name.lower()
                        if lower in HOP_BY_HOP:
                            continue
                        if lower in ALLOWED_REQUEST_HEADERS:
                            conn.putheader(name, value)
                    conn.endheaders(body)
                    response = conn.getresponse()
                    response_body = response.read(MAX_PROXY_BODY + 1)
                    if len(response_body) > MAX_PROXY_BODY:
                        raise RegistryError("tenant response exceeded proxy bound")
                    self.send_response(response.status, response.reason)
                    for name, value in response.getheaders():
                        lower = name.lower()
                        if lower in HOP_BY_HOP:
                            continue
                        if lower in ALLOWED_RESPONSE_HEADERS:
                            self.send_header(name, value)
                    self.send_header("X-Creator-Community", spec.community_id)
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(response_body)
                finally:
                    conn.close()
            except OverflowError:
                self._json_error(413, "request body exceeds multisite bound")
            except RegistryError as exc:
                message = str(exc)
                if "not registered" in message:
                    code = 421
                elif "generation" in message or "custody" in message or "unsafe" in message:
                    code = 503
                else:
                    code = 400
                self._json_error(code, message)
            except (BrokenPipeError, ConnectionResetError):
                return
            except (OSError, http.client.HTTPException, socket.timeout):
                self._json_error(502, "selected community runtime is unavailable")

        def do_GET(self):
            self._proxy()

        def do_HEAD(self):
            self._proxy()

        def do_POST(self):
            self._proxy()

        def do_PUT(self):
            self._json_error(405, "method is unsupported")

        def do_PATCH(self):
            self._json_error(405, "method is unsupported")

        def do_DELETE(self):
            self._json_error(405, "method is unsupported")

        def do_CONNECT(self):
            self._json_error(405, "method is unsupported")

    return ThreadingHTTPServer((host, port), RouterHandler)


