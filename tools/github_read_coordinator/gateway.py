"""Authenticated loopback gateway for bounded read-only GitHub REST calls."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import http.server
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace
from http.client import HTTPException
from pathlib import Path

from broker import Broker, MAX_REQUEST, MAX_RESPONSE, ROUTES, Upstream, dumps, loads, normalize, usable_etag

API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"
USER_AGENT = "commons-github-read-coordinator/1"
TOKEN_RE = re.compile(r"[!-~]{10,4096}")
LOGIN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
# Broker rejects non-JSON payloads without caching them, while preserving the
# observed HTTP status and quota headers for its independent cooldown handling.
_UNUSABLE_PAYLOAD = object()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def build_url(route: str, params: dict) -> str:
    params = normalize(route, params)
    owner = params.get("owner")
    repo = params.get("repo")
    base = f"/repos/{_quote(owner)}/{_quote(repo)}" if owner is not None else ""
    query = {}
    if route == "repo.get":
        path = base
    elif route == "contents.get":
        path = base + "/contents/" + "/".join(_quote(piece) for piece in params["path"].split("/"))
        if "ref" in params:
            query["ref"] = params["ref"]
    elif route == "pull.get":
        path = base + f"/pulls/{params['number']}"
    elif route in {"pull.files", "pull.reviews", "pull.comments", "pull.commits"}:
        # Fixed GET-only suffixes: no caller-defined endpoint or method.
        suffix = {
            "pull.files": "files",
            "pull.reviews": "reviews",
            "pull.comments": "comments",
            "pull.commits": "commits",
        }[route]
        path = base + f"/pulls/{params['number']}/{suffix}"
        query = {k: params[k] for k in ("page", "per_page")}
    elif route == "pulls.list":
        path = base + "/pulls"
        query = {k: v for k, v in params.items() if k not in {"owner", "repo"}}
    elif route == "commit.get":
        path = base + "/commits/" + _quote(params["ref"])
    elif route == "issues.list":
        path = base + "/issues"
        query = {k: v for k, v in params.items() if k not in {"owner", "repo"}}
    elif route == "actions.runs":
        path = base + "/actions/runs"
        query = {k: v for k, v in params.items() if k not in {"owner", "repo"}}
    elif route in {"search.issues", "search.code"}:
        path = "/search/" + route.split(".", 1)[1]
        query = dict(params)
    else:
        raise ValueError("read route is not allowed")
    encoded = urllib.parse.urlencode(query)
    return API_ROOT + path + ("?" + encoded if encoded else "")


class GitHubProvider:
    def __init__(self, token: str):
        if not isinstance(token, str) or TOKEN_RE.fullmatch(token) is None:
            raise ValueError("valid GitHub token required in environment")
        self._token = token
        self._opener = urllib.request.build_opener(NoRedirect())

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self._token.encode()).hexdigest()

    @staticmethod
    def _read_response(response, deadline: float, *, maximum: int = MAX_RESPONSE) -> Upstream:
        observed = Upstream(
            response.status,
            _UNUSABLE_PAYLOAD,
            response.headers.get("Retry-After"),
            response.headers.get("X-RateLimit-Remaining"),
            response.headers.get("X-RateLimit-Reset"),
            False,
            etag=usable_etag(response.headers.get("ETag")),
        )
        try:
            chunks, size = [], 0
            while True:
                if time.monotonic() >= deadline:
                    return observed
                chunk = response.read1(min(16384, maximum + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > maximum:
                    return observed
            return replace(observed, payload=loads(b"".join(chunks)))
        except (OSError, HTTPException, ValueError, RecursionError):
            return observed

    def _request(self, url: str, etag: str | None = None) -> Upstream:
        if not url.startswith(API_ROOT + "/") or any(c in url for c in ("\r", "\n")):
            raise ValueError("fixed GitHub API origin required")
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": "Bearer " + self._token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": USER_AGENT,
            },
            method="GET",
        )
        if etag is not None:
            if usable_etag(etag) is None:
                raise ValueError("invalid conditional request validator")
            request.add_header("If-None-Match", etag)
        deadline = time.monotonic() + 20
        try:
            with self._opener.open(request, timeout=20) as response:
                return self._read_response(response, deadline)
        except urllib.error.HTTPError as error:
            try:
                retry = error.headers.get("Retry-After")
                remaining = error.headers.get("X-RateLimit-Remaining")
                reset = error.headers.get("X-RateLimit-Reset")
                # Retry-After on a 403/429 is provider throttling evidence even
                # if an intermediary or malformed body prevents message parsing.
                secondary = error.code in {403, 429} and retry is not None
                # A Retry-After header already settles throttling; do not wait
                # for an error body that cannot change that classification.
                if error.code in {403, 429} and not secondary:
                    # A trickling error body must not hold a gateway slot past
                    # the request budget. Check between bounded reads just as
                    # for successful responses, retaining the smaller error cap.
                    payload = self._read_response(error, deadline, maximum=min(32768, MAX_RESPONSE)).payload
                    message = payload.get("message") if isinstance(payload, dict) else None
                    body_secondary = isinstance(message, str) and "secondary rate limit" in message.lower()
                    secondary = secondary or body_secondary
                return Upstream(error.code, None, retry, remaining, reset, secondary,
                                etag=usable_etag(error.headers.get("ETag")),
                                validated_etag=etag if error.code == 304 else None)
            finally:
                error.close()
        except (OSError, ValueError, RecursionError):
            return Upstream(502)

    def __call__(self, route: str, params: dict) -> Upstream:
        if route not in ROUTES:
            raise ValueError("read route is not allowed")
        return self._request(build_url(route, params))

    def revalidate(self, route: str, params: dict, etag: str) -> Upstream:
        # The broker supplies a validator only with its matching retained body.
        return self._request(build_url(route, params), etag)

    def authenticate(self, expected_login: str | None = None):
        if expected_login is not None and (not isinstance(expected_login, str) or LOGIN_RE.fullmatch(expected_login) is None):
            raise ValueError("invalid expected login")
        result = self._request(API_ROOT + "/user")
        payload = result.payload
        if result.status != 200 or not isinstance(payload, dict) or not isinstance(payload.get("login"), str):
            raise ValueError("GitHub authentication failed; no service started")
        if expected_login is not None and payload["login"].lower() != expected_login.lower():
            raise ValueError("GitHub login mismatch; no service started")


class Gateway(http.server.ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = True
    allow_reuse_address = True

    def __init__(self, port: int, broker: Broker, provider: GitHubProvider, key: str):
        if not isinstance(key, str) or re.fullmatch(r"[a-f0-9]{64}", key) is None:
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
        pass


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "GitHubReadGateway/1"

    def setup(self):
        self.request.settimeout(10)
        super().setup()

    def log_message(self, *args):
        pass

    def send_json(self, code: int, body):
        raw = dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.send_json(405, {"state": "METHOD_NOT_ALLOWED", "provider_write_authority": False})

    do_PUT = do_DELETE = do_PATCH = do_GET

    def do_POST(self):
        if self.path != "/read":
            self.send_json(404, {"state": "NOT_FOUND", "provider_write_authority": False})
            return
        auth = self.headers.get("Authorization", "")
        expected = "Bearer " + self.server.key
        if not auth.isascii() or not hmac.compare_digest(auth, expected):
            self.send_json(401, {"state": "UNAUTHORIZED", "provider_write_authority": False})
            return
        raw_length = self.headers.get("Content-Length", "")
        if not re.fullmatch(r"[0-9]{1,8}", raw_length):
            self.send_json(400, {"state": "INVALID_REQUEST", "provider_write_authority": False})
            return
        length = int(raw_length)
        if length < 2 or length > MAX_REQUEST:
            self.send_json(413, {"state": "INVALID_REQUEST", "provider_write_authority": False})
            return
        try:
            body = loads(self.rfile.read(length))
            if not isinstance(body, dict) or set(body) - {"route", "params", "max_age_seconds"}:
                raise ValueError
            route = body["route"]
            params = body["params"]
            max_age = body.get("max_age_seconds", 30)
            result = self.server.broker.read(route, params, self.server.provider, max_age)
        except (KeyError, ValueError, TypeError, UnicodeDecodeError, RecursionError):
            self.send_json(400, {"state": "INVALID_REQUEST", "provider_write_authority": False})
            return
        self.send_json(200, result)


def private_state(path: str | Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch(mode=0o600)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--expected-login")
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "")
    key = os.environ.get("GITHUB_READ_GATEWAY_KEY", "")
    provider = GitHubProvider(token)
    provider.authenticate(args.expected_login)
    db = private_state(args.db)
    broker = Broker(db, provider.fingerprint)
    server = Gateway(args.port, broker, provider, key)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
