"""Authenticated loopback Slack read gateway. No write method or arbitrary URL exists."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import http.server
import json
import os
import re
import sqlite3
import stat
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from broker import Broker, METHODS, MAX_REQUEST, MAX_RESPONSE, Upstream, dumps, loads, normalize


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SlackProvider:
    def __init__(self, token: str):
        if not isinstance(token, str) or not re.fullmatch(r"[!-~]{10,2048}", token):
            raise ValueError("valid Slack token required in environment")
        self._token = token
        self._opener = urllib.request.build_opener(NoRedirect())

    @property
    def fingerprint(self):
        return hashlib.sha256(self._token.encode()).hexdigest()

    def __call__(self, method, params):
        if method not in METHODS:
            raise ValueError("read method is not allowed")
        return self._request(method, normalize(method, params, 100))

    def authenticate(self, expected_workspace):
        result = self._request("auth.test", {})
        body = result.payload
        if result.status != 200 or not isinstance(body, dict) or body.get("ok") is not True or body.get("team_id") != expected_workspace or body.get("is_enterprise_install") is True:
            raise ValueError("Slack workspace authentication failed; no service started")

    def _request(self, method, params):
        if method not in METHODS and method != "auth.test":
            raise ValueError("read method is not allowed")
        encoded = urllib.parse.urlencode({k: str(v).lower() if type(v) is bool else v for k, v in params.items()})
        request = urllib.request.Request(
            "https://slack.com/api/" + method + ("?" + encoded if encoded else ""),
            data=b"{}" if method == "auth.test" else None,
            headers={"Authorization": "Bearer " + self._token, "Accept": "application/json", "Content-Type": "application/json"},
            method="POST" if method == "auth.test" else "GET",
        )
        deadline = time.monotonic() + 20
        try:
            with self._opener.open(request, timeout=20) as response:
                chunks, size = [], 0
                while True:
                    if time.monotonic() >= deadline:
                        return Upstream(502)
                    chunk = response.read1(min(16384, MAX_RESPONSE + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > MAX_RESPONSE:
                        return Upstream(502)
                return Upstream(response.status, loads(b"".join(chunks)), response.headers.get("Retry-After"))
        except urllib.error.HTTPError as error:
            try:
                # Do not read/echo an error body or follow redirects with credentials.
                return Upstream(error.code, retry_after=error.headers.get("Retry-After"))
            finally:
                error.close()
        except (OSError, ValueError, RecursionError):
            return Upstream(502)


class Gateway(http.server.ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = True
    allow_reuse_address = True

    def __init__(self, port, broker, provider, key):
        if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValueError("gateway key must be a separately generated 256-bit hex secret")
        self.broker, self.provider, self.key = broker, provider, key
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(("127.0.0.1", port), Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            try:
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\nRetry-After: 1\r\n\r\n")
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        # No request bodies, auth headers, Slack text, or exception detail in logs.
        pass


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "SlackReadGateway/1"

    def setup(self):
        self.request.settimeout(10)
        super().setup()

    def log_message(self, *args):
        pass

    def send_json(self, code, body):
        raw = dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        if "retry_after_seconds" in body:
            self.send_header("Retry-After", str(body["retry_after_seconds"]))
        self.end_headers()
        self.wfile.write(raw)
        self.close_connection = True

    def authorized(self):
        values = self.headers.get_all("Authorization", [])
        supplied = values[0] if len(values) == 1 else ""
        if not hmac.compare_digest(supplied.encode(), ("Bearer " + self.server.key).encode()):
            self.send_json(401, {"state": "UNAUTHORIZED", "outbound_clearance": False})
            return False
        return True

    def do_GET(self):
        if not self.authorized():
            return
        if self.path != "/health":
            self.send_json(404, {"state": "NOT_FOUND", "outbound_clearance": False})
            return
        self.send_json(200, {"state": "RUNNING", "read_only": True, "outbound_clearance": False})

    def do_POST(self):
        if not self.authorized():
            return
        if self.path != "/v1/read":
            self.send_json(404, {"state": "NOT_FOUND", "outbound_clearance": False})
            return
        try:
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,8}", lengths[0]) or self.headers.get("Transfer-Encoding"):
                raise ValueError("invalid framing")
            length = int(lengths[0])
            if not 1 <= length <= MAX_REQUEST:
                raise ValueError("invalid body size")
            if self.headers.get("Content-Type", "").split(";", 1)[0].lower() != "application/json":
                raise ValueError("JSON content type required")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("incomplete body")
            body = loads(raw)
            if not isinstance(body, dict) or set(body) - {"method", "params", "max_age_seconds"} or not {"method", "params"} <= body.keys():
                raise ValueError("invalid request schema")
            result = self.server.broker.read(body["method"], body["params"], self.server.provider, body.get("max_age_seconds", 30))
            code = {"FETCHED": 200, "CACHED": 200, "BUSY": 202, "DISCARDED": 202, "COOLDOWN": 429, "AUTH_BLOCKED": 503, "UPSTREAM_ERROR": 502}[result["state"]]
            self.send_json(code, result)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            self.send_json(400, {"state": "INVALID_REQUEST", "outbound_clearance": False})
        except sqlite3.Error:
            self.send_json(503, {"state": "STORAGE_UNAVAILABLE", "outbound_clearance": False, "retry_after_seconds": 1})


def private_state(directory):
    if os.name != "posix":
        raise ValueError("service storage requires a POSIX owner-only directory")
    path = Path(directory)
    if path.is_symlink():
        raise ValueError("state directory must not be a symlink")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if os.name == "posix" and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
        raise ValueError("state directory must be owner-only (0700)")
    db = path / "reads.sqlite3"
    if db.is_symlink():
        raise ValueError("database must not be a symlink")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(db, flags, 0o600)
    except FileExistsError:
        info = db.stat()
        if not stat.S_ISREG(info.st_mode) or (os.name == "posix" and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077)):
            raise ValueError("database must be an owner-only regular file")
    else:
        os.close(fd)
    return db


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--state-dir", required=True)
    serve.add_argument("--workspace", required=True)
    serve.add_argument("--app-id", required=True)
    serve.add_argument("--port", type=int, default=8766)
    serve.add_argument("--internal-app", action="store_true", help="Only for an operator-verified internal/Marketplace app with Tier 3 history/replies")
    read = sub.add_parser("read")
    read.add_argument("--port", type=int, default=8766)
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.port <= 65535:
            raise ValueError("invalid port")
        key = os.environ.get("SLACK_READ_GATEWAY_KEY", "")
        if not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValueError("SLACK_READ_GATEWAY_KEY must contain a 256-bit hex secret")
        if args.command == "read":
            raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
            if len(raw) > MAX_REQUEST:
                raise ValueError("request too large")
            request = urllib.request.Request("http://127.0.0.1:%d/v1/read" % args.port, data=raw, headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
            try:
                response = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=30)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                data = response.read(MAX_RESPONSE + MAX_REQUEST + 1)
                if len(data) > MAX_RESPONSE + MAX_REQUEST:
                    raise ValueError("gateway response too large")
                result = loads(data)
                if not isinstance(result, dict):
                    raise ValueError("gateway response must be an object")
                print(dumps(result))
                successful = response.status == 200 and result.get("state") in {"FETCHED", "CACHED"} and result.get("outbound_clearance") is False
                return 0 if successful else 2
        token = os.environ.get("SLACK_READ_TOKEN", "")
        if hmac.compare_digest(token.encode(), key.encode()):
            raise ValueError("gateway and upstream credentials must be distinct")
        provider = SlackProvider(token)
        provider.authenticate(args.workspace)
        broker = Broker(private_state(args.state_dir), args.workspace, args.app_id, provider.fingerprint, internal_app=args.internal_app)
        with Gateway(args.port, broker, provider, key) as server:
            print("Read-only gateway listening on 127.0.0.1:%d; no outbound clearance" % args.port, flush=True)
            server.serve_forever()
        return 0
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, RecursionError, sqlite3.Error):
        print("Gateway failed; check configuration, authorization, state permissions and connectivity. No secret details logged.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
