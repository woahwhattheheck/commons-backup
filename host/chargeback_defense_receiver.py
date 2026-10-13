#!/usr/bin/env python3
"""Deployment-neutral HTTP ingress adapter for the private chargeback-defense desk.

This module is a thin, transport-only boundary around the landed ingest path in
``host/chargeback_defense.py``. It accepts a POST body as exact bytes, forwards
the exact ``Stripe-Signature`` header, and hands both unchanged to the core's
own ``verify()`` and ``normalize()`` before performing the same durable,
atomic, event-ID-deduplicated ledger write the ``ingest`` CLI performs. No
verification, normalization, or storage logic is reimplemented: the
``Stripe-Signature`` parse below is mapping-only (it chooses the deterministic
HTTP status for a rejected delivery) and the core's ``verify()`` remains the
authoritative cryptographic check on every request.

Deliberate non-goals, enforced by construction:

* No account authentication and no provider configuration. The adapter itself
  performs no login; the endpoint signing secret and the private SQLite ledger
  path are operator-supplied runtime configuration that must live outside the
  repository.
* No provider calls, no charges, refunds, captures, dispute submissions, and
  no customer contact. Nothing here moves money or claims revenue, cash,
  acceptance, or settlement.
* No web framework and no new dependencies: the WSGI application runs under
  any WSGI server, and ``main()`` serves it with the standard library
  ``http.server`` for private-backend loopback and operator use.
* Public-safe operation only: receipts, responses, and logs carry operational
  metadata (schema version, status, event ID, record kind, counts, HTTP
  status, byte sizes, timestamps). Raw bodies, secrets, customer fields,
  account identifiers, and private filesystem paths are never emitted.

Deterministic HTTP mapping:

* 200 ``recorded``   -- first verified delivery, durably committed to the ledger.
* 200 ``duplicate``  -- exact replay of recorded bytes; no second effect.
* 400 ``body_empty`` / ``content_length_invalid`` / ``payload_truncated``
* 400 ``signature_malformed`` -- header fails the Stripe v1 shape.
* 400 ``event_invalid``       -- verified bytes are not a well-formed event.
* 401 ``signature_required``  -- no ``Stripe-Signature`` header.
* 401 ``signature_stale``     -- timestamp outside the configured tolerance.
* 401 ``signature_invalid``   -- HMAC verification failed.
* 404 ``not_found``           -- unknown path.
* 405 ``method_not_allowed``  -- anything other than POST on the route.
* 409 ``event_conflict``      -- same event ID, different payload bytes;
  the original ledger row is preserved.
* 411 ``length_required``     -- missing ``Content-Length``.
* 413 ``body_too_large``      -- declared or actual body exceeds the bound.
* 415 ``content_type_unsupported`` -- not ``application/json``.
* 500 ``storage_failure`` / ``internal_failure`` -- durable write or an
  unexpected internal error. Success is never emitted before the core
  reports a durable recorded/duplicate outcome.

``host/stripe_event_bridge.py`` is intentionally not imported: it requires
unrelated commerce dependencies (``checkout_handoff``). The equivalent
signature semantics are already embedded in ``host/chargeback_defense.py``
(which documents this equivalence itself); composing with the chargeback
module keeps this adapter dependency-free.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import re
import sqlite3
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Mapping, Optional

try:  # Sibling import when host/ is on the path; path fallback otherwise.
    import chargeback_defense as _core
except ImportError:  # pragma: no cover - exercised only from a foreign cwd.
    _HOST_DIR = os.path.dirname(os.path.abspath(__file__))
    if _HOST_DIR not in sys.path:
        sys.path.insert(0, _HOST_DIR)
    import chargeback_defense as _core

LOG = logging.getLogger("chargeback_defense_receiver")

_SIGNATURE_HEADER = "stripe-signature"
_V1_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_JSON_CONTENT_RE = re.compile(r"^application/json(\s*;.*)?$", re.IGNORECASE)
_STATUS_PHRASES = {
    200: "OK", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found",
    405: "Method Not Allowed", 409: "Conflict", 411: "Length Required",
    413: "Content Too Large", 415: "Unsupported Media Type",
    500: "Internal Server Error",
}

ERROR_MESSAGES = {
    "body_empty": "request body must be nonempty",
    "body_too_large": "request body exceeds the configured size bound",
    "content_length_invalid": "Content-Length must be a non-negative integer",
    "content_type_unsupported": "Content-Type must be application/json",
    "event_conflict": "event-ID conflict: verified delivery has different payload bytes; original ledger row preserved",
    "event_invalid": "verified body is not a well-formed chargeback-defense event",
    "internal_failure": "unexpected internal failure while handling the delivery",
    "length_required": "Content-Length is required",
    "method_not_allowed": "only POST is accepted on the ingest route",
    "not_found": "unknown route",
    "payload_truncated": "fewer body bytes arrived than Content-Length declared",
    "signature_invalid": "Stripe webhook signature verification failed",
    "signature_malformed": "Stripe-Signature header is malformed",
    "signature_required": "Stripe-Signature header is missing",
    "signature_stale": "Stripe-Signature timestamp is outside tolerance; use a fresh provider delivery",
    "storage_failure": "durable write failed; nothing was recorded",
}


class ReceiverError(Exception):
    """A deterministic, public-safe request failure."""

    def __init__(self, http_status: int, code: str, message: Optional[str] = None):
        super().__init__(message or ERROR_MESSAGES[code])
        self.http_status = http_status
        self.code = code


@dataclass
class ReceiverConfig:
    """Operator runtime configuration. Secrets and paths live in memory or in
    operator-owned private locations; nothing here is committed anywhere."""

    db_path: str
    secret: str
    tolerance: int = 300
    max_body_bytes: int = 0  # 0 means the core's MAX_BODY bound.
    bind: str = "127.0.0.1"
    port: int = 0
    route: str = "/ingest"

    def __post_init__(self) -> None:
        self.db_path = str(_core.private_path(self.db_path))
        if not isinstance(self.secret, str) or not self.secret or len(self.secret) > 4096:
            raise ReceiverError(500, "internal_failure", "endpoint signing secret is unavailable or invalid")
        if isinstance(self.tolerance, bool) or not isinstance(self.tolerance, int) or not 1 <= self.tolerance <= 3600:
            raise ReceiverError(500, "internal_failure", "signature tolerance must be between 1 and 3600 seconds")
        if self.max_body_bytes == 0:
            self.max_body_bytes = _core.MAX_BODY
        if isinstance(self.max_body_bytes, bool) or not isinstance(self.max_body_bytes, int) or self.max_body_bytes < 1:
            raise ReceiverError(500, "internal_failure", "max body bound must be a positive integer")
        if not isinstance(self.route, str) or not self.route.startswith("/"):
            raise ReceiverError(500, "internal_failure", "route must be an absolute path")


def _public_error(code: str, message: Optional[str] = None) -> dict[str, Any]:
    return {"error": code, "message": message or ERROR_MESSAGES[code]}


def _inspect_signature_header(header: str, tolerance: int) -> tuple[bool, bool]:
    """Mapping-only parse of the Stripe-Signature header.

    Returns (well_formed, stale). This function never verifies anything: it
    only decides which deterministic HTTP status a rejected delivery maps to.
    ``_core.verify()`` remains the authoritative check and runs on every
    request afterwards with the exact same bytes and header. Timestamp text
    must be bounded ASCII decimal digits: ``str.isdigit()`` also accepts
    Unicode characters that cannot be converted to an integer.
    """
    if not header or len(header) > 8192 or "\n" in header or "\r" in header:
        return False, False
    timestamps: list[str] = []
    signatures: list[str] = []
    for part in header.split(","):
        key, sep, value = part.strip().partition("=")
        if not sep:
            return False, False
        if key == "t":
            timestamps.append(value)
        elif key == "v1":
            signatures.append(value)
    if (len(timestamps) != 1 or not re.fullmatch(r"[0-9]{1,12}", timestamps[0])
            or not signatures):
        return False, False
    if any(not _V1_HEX_RE.fullmatch(item) for item in signatures):
        return False, False
    stamp = int(timestamps[0])
    return True, abs(int(time.time()) - stamp) > tolerance


def _durable_write(item: dict[str, Any], raw: bytes, stamp: int, config: ReceiverConfig) -> dict[str, Any]:
    """Atomically record the normalized event. Transaction semantics mirror
    ``chargeback_defense.ingest()`` exactly: BEGIN IMMEDIATE, duplicate bytes
    roll back with a duplicate receipt, conflicting bytes raise EventConflict
    with the original row preserved, and a single INSERT commits."""
    digest = hashlib.sha256(raw).hexdigest()
    received_ns = time.time_ns()
    db = _core.connect(config.db_path)
    try:
        db.execute("BEGIN IMMEDIATE")
        old = db.execute("SELECT payload_sha256 FROM events WHERE event_id=?", (item["event_id"],)).fetchone()
        if old:
            if old[0] != digest:
                raise _core.EventConflict(ERROR_MESSAGES["event_conflict"])
            db.execute("ROLLBACK")
            return {"schema_version": _core.SCHEMA, "status": "duplicate",
                    "event_id": item["event_id"], "record_count_added": 0}
        db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            item["event_id"], item["provider"], item["account_id"], int(item["livemode"]),
            item["event_type"], item["created"], received_ns // 10**9, received_ns, stamp,
            digest, item["kind"], item["object_id"], item["charge_id"],
            item["payment_intent_id"], _core.canonical(item),
        ))
        db.execute("COMMIT")
        return {"schema_version": _core.SCHEMA, "status": "recorded",
                "event_id": item["event_id"], "record_kind": item["kind"],
                "record_count_added": 1,
                "operator_flags": ["UNSUPPORTED_EVENT_RECORDED_WITHOUT_OBJECT_DATA"] if item["kind"] == "unsupported" else []}
    except Exception:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    finally:
        db.close()


def handle_delivery(method: str, path: str, headers: Mapping[str, str],
                    body: bytes, config: ReceiverConfig) -> tuple[int, dict[str, Any]]:
    """Pure request handler: no I/O except the durable ledger write.

    ``body`` must be the exact received bytes; ``headers`` maps lower-cased
    header names to values. Returns (http_status, public-safe payload).
    """
    lowered = {str(name).lower(): value for name, value in headers.items()}
    if path != config.route:
        return 404, _public_error("not_found")
    if method.upper() != "POST":
        return 405, _public_error("method_not_allowed")
    if not _JSON_CONTENT_RE.match(lowered.get("content-type", "") or ""):
        return 415, _public_error("content_type_unsupported")
    if len(body) > config.max_body_bytes:
        return 413, _public_error("body_too_large")
    if not body:
        return 400, _public_error("body_empty")
    signature = lowered.get(_SIGNATURE_HEADER)
    if not signature:
        return 401, _public_error("signature_required")
    well_formed, stale = _inspect_signature_header(signature, config.tolerance)
    if not well_formed:
        return 400, _public_error("signature_malformed")
    if stale:
        return 401, _public_error("signature_stale")
    # Exact bytes and the exact header reach the core unchanged from here on.
    try:
        stamp = _core.verify(body, signature, config.secret, config.tolerance)
    except _core.DefenseError:
        # The header passed the mapping-only shape and freshness checks, so
        # the only remaining core rejection is a failed HMAC comparison.
        return 401, _public_error("signature_invalid")
    except Exception:
        return 500, _public_error("internal_failure")
    try:
        item = _core.normalize(body)
    except _core.DefenseError as exc:
        return 400, _public_error("event_invalid", str(exc))
    except Exception:
        return 500, _public_error("internal_failure")
    try:
        receipt = _durable_write(item, body, stamp, config)
    except _core.EventConflict as exc:
        return 409, _public_error("event_conflict", str(exc))
    except Exception:
        return 500, _public_error("storage_failure")
    return 200, receipt


def create_app(config: ReceiverConfig) -> Callable[..., Any]:
    """Return a WSGI application serving the receiver on ``config.route``."""

    def app(environ: Mapping[str, Any], start_response: Callable[..., Any]) -> list[bytes]:
        method = str(environ.get("REQUEST_METHOD", ""))
        path = str(environ.get("PATH_INFO", ""))
        headers: dict[str, str] = {}
        for name, value in environ.items():
            if name.startswith("HTTP_"):
                headers[name[5:].replace("_", "-").lower()] = str(value)
        if environ.get("CONTENT_TYPE") is not None:
            headers["content-type"] = str(environ["CONTENT_TYPE"])
        if environ.get("CONTENT_LENGTH") is not None:
            headers["content-length"] = str(environ["CONTENT_LENGTH"])
        raw_length = str(environ.get("CONTENT_LENGTH", "") or "")
        if (method.upper() != "POST" or path != config.route) and not raw_length:
            # Method/path mapping never needs a body; Content-Length is only
            # required for POST deliveries to the ingest route.
            started = time.time()
            status, payload = handle_delivery(method, path, headers, b"", config)
            _log_delivery(method, path, status, payload, 0, started)
            return _respond(start_response, status, payload)
        if not raw_length:
            return _respond(start_response, 411, _public_error("length_required"))
        try:
            declared = int(raw_length)
            if declared < 0:
                raise ValueError
        except ValueError:
            return _respond(start_response, 400, _public_error("content_length_invalid"))
        if declared > config.max_body_bytes:
            return _respond(start_response, 413, _public_error("body_too_large"))
        try:
            body = environ["wsgi.input"].read(declared) if declared else b""
        except Exception:
            return _respond(start_response, 500, _public_error("internal_failure"))
        if len(body) < declared:
            return _respond(start_response, 400, _public_error("payload_truncated"))
        started = time.time()
        status, payload = handle_delivery(method, path, headers, body, config)
        _log_delivery(method, path, status, payload, len(body), started)
        return _respond(start_response, status, payload)

    return app


def _respond(start_response: Callable[..., Any], status: int,
             payload: dict[str, Any]) -> list[bytes]:
    body = (json.dumps(payload, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    headers = [("Content-Type", "application/json"),
               ("Content-Length", str(len(body)))]
    if status == 405:
        headers.append(("Allow", "POST"))
    phrase = _STATUS_PHRASES.get(status, "Unknown")
    start_response(f"{status} {phrase}", headers)
    return [body]


def _log_delivery(method: str, path: str, status: int, payload: Mapping[str, Any],
                  body_bytes: int, started: float) -> None:
    """Log public-safe operational metadata only. Never headers, raw bodies,
    secrets, customer fields, account identifiers, or private paths."""
    event_id = payload.get("event_id", "-") if isinstance(payload, Mapping) else "-"
    outcome = payload.get("status", payload.get("error", "-")) if isinstance(payload, Mapping) else "-"
    # Request targets can contain customer data or credentials, even when the
    # route is unknown. Log only the route category and a bounded method name.
    route = "unmatched" if status == 404 else "ingest"
    logged_method = method if method in {"GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"} else "OTHER"
    LOG.info("method=%s route=%s status=%d outcome=%s event_id=%s body_bytes=%d duration_ms=%d",
             logged_method, route, status, outcome, event_id, body_bytes,
             int((time.time() - started) * 1000))


class _Handler(BaseHTTPRequestHandler):
    """Standard-library HTTP front end. Reads exactly Content-Length bytes (or
    rejects deterministically) and delegates everything else to
    ``handle_delivery``."""

    config: ReceiverConfig = None  # type: ignore[assignment]
    server_version = "ChargebackDefenseReceiver/1.0"
    protocol_version = "HTTP/1.1"

    def _dispatch(self, method: str) -> None:
        if method != "POST" or self.path != self.config.route:
            # Method/path mapping never needs a body; Content-Length is only
            # required for POST deliveries to the ingest route.
            # Do not let an unread rejected body become the next request line.
            if (any(value.strip() != "0" for value in self.headers.get_all("Content-Length", []))
                    or "Transfer-Encoding" in self.headers):
                self.close_connection = True
            headers = {name.lower(): value for name, value in self.headers.items()}
            started = time.time()
            status, payload = handle_delivery(method, self.path, headers, b"", self.config)
            _log_delivery(method, self.path, status, payload, 0, started)
            self._send(status, payload)
            return
        length_header = self.headers.get("Content-Length")
        if length_header is None:
            self.close_connection = True
            self._send(411, _public_error("length_required"))
            return
        try:
            declared = int(length_header)
            if declared < 0:
                raise ValueError
        except ValueError:
            self.close_connection = True
            self._send(400, _public_error("content_length_invalid"))
            return
        if declared > self.config.max_body_bytes:
            self.close_connection = True
            self._send(413, _public_error("body_too_large"))
            return
        try:
            body = self.rfile.read(declared) if declared else b""
        except Exception:
            self._send(500, _public_error("internal_failure"))
            return
        if len(body) < declared:
            self._send(400, _public_error("payload_truncated"))
            return
        headers = {name.lower(): value for name, value in self.headers.items()}
        started = time.time()
        status, payload = handle_delivery(method, self.path, headers, body, self.config)
        _log_delivery(method, self.path, status, payload, len(body), started)
        self._send(status, payload)

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = (json.dumps(payload, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        self.send_response(status, _STATUS_PHRASES.get(status, "Unknown"))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if self.close_connection:
            self.send_header("Connection", "close")
        if status == 405:
            self.send_header("Allow", "POST")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def do_PATCH(self) -> None:
        self._dispatch("PATCH")

    def do_HEAD(self) -> None:
        self._dispatch("HEAD")

    def do_OPTIONS(self) -> None:
        self._dispatch("OPTIONS")

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        # BaseHTTPRequestHandler otherwise logs the complete request line.
        status = code if isinstance(code, int) else "-"
        response_bytes = size if isinstance(size, int) else "-"
        LOG.info("http_server: status=%s response_bytes=%s", status, response_bytes)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        # Parser error text can echo untrusted methods, targets and headers.
        LOG.info("http_server: protocol_error")


def serve_forever(config: ReceiverConfig) -> tuple[ThreadingHTTPServer, threading.Thread]:
    """Bind ``config`` and serve in a background thread. Returns (server, thread)."""
    handler = type("_BoundHandler", (_Handler,), {"config": config})
    server = ThreadingHTTPServer((config.bind, config.port), handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05},
                              name="chargeback-receiver", daemon=True)
    thread.start()
    return server, thread


def initialize_ledger(db_path: str) -> dict[str, Any]:
    """Create the private ledger if absent. Enforces the core's private-path,
    ownership, and mode rules before touching the filesystem."""
    db = _core.connect(db_path, initialize=True)
    try:
        count = db.execute("SELECT count(*) FROM events").fetchone()[0]
    finally:
        db.close()
    return {"schema_version": _core.SCHEMA, "status": "initialized",
            "events_observed": count, "financial_coverage": "UNMEASURED"}


def _load_secret(args: argparse.Namespace) -> str:
    if args.secret_file:
        return _core.private_read(args.secret_file, limit=4096).decode("utf-8").strip()
    return os.environ.get(args.secret_env, "")


def _synthetic_event(event_id: str = "evt_synthetic_loopback_0001") -> bytes:
    """Build an explicitly synthetic charge.succeeded event. Never a real
    provider delivery: every identifier carries the synthetic marker."""
    now = int(time.time())
    event = {
        "id": event_id,
        "object": "event",
        "type": "charge.succeeded",
        "livemode": False,
        "created": now,
        "data": {"object": {
            "id": "ch_synthetic_loopback_0001",
            "object": "charge",
            "created": now,
            "amount": 2500,
            "currency": "usd",
            "paid": True,
            "captured": True,
            "payment_intent": "pi_synthetic_loopback_0001",
        }},
    }
    return json.dumps(event, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sign(body: bytes, secret: str, stamp: int) -> str:
    digest = hmac.new(secret.encode("utf-8"), str(stamp).encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"t={stamp},v1={digest}"


def run_loopback_proof(secret: str = "synthetic-loopback-endpoint-secret-20261001",
                       tolerance: int = 300) -> dict[str, Any]:
    """Local loopback proof: real HTTP over 127.0.0.1, an explicitly synthetic
    HMAC-signed event, and zero external/provider calls.

    Spins up the stdlib server on an ephemeral port, initializes a private
    throwaway ledger outside the repository, delivers one synthetic event
    (expect 200 recorded), replays the exact bytes (expect 200 duplicate with
    no second row), then exercises the deterministic rejections. Returns a
    public-safe proof receipt.
    """
    if not secret.startswith("synthetic-"):
        raise ReceiverError(500, "internal_failure", "loopback proof requires an explicitly synthetic secret")
    workdir = tempfile.mkdtemp(prefix="chargeback-receiver-proof-")
    os.chmod(workdir, 0o700)
    db_path = os.path.join(workdir, "ledger.sqlite")
    initialize_ledger(db_path)
    config = ReceiverConfig(db_path=db_path, secret=secret, tolerance=tolerance,
                            bind="127.0.0.1", port=0)
    server, _ = serve_forever(config)
    port = server.server_address[1]
    checks: list[dict[str, Any]] = []

    def post(body: bytes, headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
        connection = HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            connection.request("POST", config.route, body=body, headers=headers)
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, payload
        finally:
            connection.close()

    def get(path: str) -> int:
        connection = HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            connection.request("GET", path)
            return connection.getresponse().status
        finally:
            connection.close()

    def note(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": ok, "detail": detail})
        if not ok:
            raise ReceiverError(500, "internal_failure", "loopback proof failed at " + name)

    try:
        stamp = int(time.time())
        body = _synthetic_event()
        headers = {"Content-Type": "application/json",
                   "Stripe-Signature": _sign(body, secret, stamp)}
        status, payload = post(body, headers)
        note("valid_event_recorded", status == 200 and payload.get("status") == "recorded",
             f"status={status}")
        status, payload = post(body, headers)
        note("exact_replay_idempotent", status == 200 and payload.get("status") == "duplicate",
             f"status={status}")
        db = _core.connect(db_path)
        try:
            rows = db.execute("SELECT count(*) FROM events").fetchone()[0]
        finally:
            db.close()
        note("single_durable_row", rows == 1, f"rows={rows}")
        bad = dict(headers)
        bad["Stripe-Signature"] = _sign(body, "synthetic-wrong-secret", stamp)
        status, _ = post(body, bad)
        note("invalid_signature_rejected", status == 401, f"status={status}")
        no_sig = {"Content-Type": "application/json"}
        status, _ = post(body, no_sig)
        note("missing_signature_rejected", status == 401, f"status={status}")
        stale_header = _sign(body, secret, stamp - tolerance - 60)
        status, _ = post(body, {"Content-Type": "application/json",
                               "Stripe-Signature": stale_header})
        note("stale_timestamp_rejected", status == 401, f"status={status}")
        try:
            status, _ = post(b"x" * (config.max_body_bytes + 1),
                             {"Content-Type": "application/json",
                              "Stripe-Signature": _sign(b"x", secret, stamp)})
            oversized_ok = (status == 413)
            oversized_detail = f"status={status}"
        except (BrokenPipeError, ConnectionResetError):
            # The server rejected and closed the connection before consuming
            # the 8 MiB body: the deterministic 413 path. The live-listener
            # checks below confirm the server stayed healthy.
            oversized_ok = True
            oversized_detail = "connection closed on oversized body"
        note("oversized_body_rejected", oversized_ok, oversized_detail)
        note("wrong_method_rejected", get(config.route) == 405, "")
        note("unknown_path_rejected", get("/nope") == 404, "")
    finally:
        server.shutdown()
        server.server_close()
    return {"schema_version": _core.SCHEMA, "kind": "LOOPBACK_PROOF",
            "external_calls": 0, "synthetic_only": True,
            "checks": checks, "passed": all(check["passed"] for check in checks)}


def _build_config(args: argparse.Namespace) -> ReceiverConfig:
    secret = _load_secret(args)
    try:
        return ReceiverConfig(db_path=args.db, secret=secret, tolerance=args.tolerance,
                              bind=args.bind, port=args.port, route=args.route)
    except ReceiverError as exc:
        print("chargeback-defense-receiver: " + str(exc), file=sys.stderr)
        raise SystemExit(2)


def _parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    result.add_argument("--db", default=os.environ.get("CHARGEBACK_DB"),
                        help="absolute private off-repository SQLite path, or CHARGEBACK_DB")
    result.add_argument("--secret-env", default="STRIPE_WEBHOOK_SECRET",
                        help="environment variable containing the endpoint signing secret")
    result.add_argument("--secret-file", help="mode-600 private file containing the endpoint signing secret")
    result.add_argument("--tolerance", type=int, default=300,
                        help="signature timestamp tolerance in seconds (1-3600, default 300)")
    result.add_argument("--bind", default="127.0.0.1",
                        help="interface to bind (default 127.0.0.1; keep private)")
    result.add_argument("--port", type=int, default=0,
                        help="port to bind (default 0 = ephemeral)")
    result.add_argument("--route", default="/ingest", help="ingest route (default /ingest)")
    result.add_argument("--init", action="store_true",
                        help="initialize the private ledger and exit (no server, no secret needed)")
    result.add_argument("--loopback-proof", action="store_true",
                        help="run the synthetic loopback proof and exit (no server kept running)")
    return result


def main(argv: list[str] | None = None) -> int:
    os.umask(0o077)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    args = _parser().parse_args(argv)
    try:
        if args.loopback_proof:
            print(json.dumps(run_loopback_proof(), indent=2, sort_keys=True))
            return 0
        if not args.db:
            raise ReceiverError(500, "internal_failure", "--db or CHARGEBACK_DB is required; there is no in-repository default store")
        if args.init:
            print(json.dumps(initialize_ledger(args.db), indent=2, sort_keys=True))
            return 0
        config = _build_config(args)
        server, _ = serve_forever(config)
        LOG.info("listening route=%s bind=%s port=%d", config.route, config.bind, server.server_address[1])
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()
        return 0
    except ReceiverError as exc:
        print("chargeback-defense-receiver: " + str(exc), file=sys.stderr)
        return 2
    except SystemExit:
        raise
    except Exception as exc:  # Never leak internals to the operator surface.
        print("chargeback-defense-receiver: private input/storage operation failed (" + type(exc).__name__ + ")",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
