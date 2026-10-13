#!/usr/bin/env python3
"""Authenticated Twilio webhook edge for the Hive006 Voice Support MerchantGate.

The existing ``desk.py`` and ``merchant_auth.py`` services remain local-only.
This edge verifies Twilio's request signature first, then delegates only to the
per-order-verifying ``MerchantGate``.  The Twilio Auth Token is runtime-only.
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import merchant_auth

HERE = Path(__file__).resolve().parent
MAX_BODY = 2_000_000
MAX_FORM_FIELDS = 512
SIGNATURE_HEADER = "X-Twilio-Signature"
DEFAULT_TOKEN_ENV = "TWILIO_AUTH_TOKEN"
BUNDLE_NAMES = (
    "desk.py",
    "index.html",
    "README.md",
    "test_desk.py",
    "orders.example.csv",
    "merchant_auth.py",
    "test_merchant_auth.py",
    "merchant-access.example.csv",
    "MERCHANT-AUTH.md",
    "twilio_webhook.py",
    "test_twilio_webhook.py",
    "TRUSTED-WEBHOOK.md",
    "requirements-webhook.txt",
)


def _loopback(value: str) -> str:
    """Reuse the merchant edge's loopback-only parser without widening it."""
    return merchant_auth._loopback(value)


def _public_origin(value: str) -> str:
    """Validate the exact externally configured HTTPS origin used by Twilio.

    We intentionally do not reconstruct this from Host/X-Forwarded-* headers.
    The reverse proxy must preserve the raw path and query target.
    """
    if not isinstance(value, str) or not value or value != value.strip():
        raise argparse.ArgumentTypeError("--public-origin must be exact nonblank text")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise argparse.ArgumentTypeError(
            "--public-origin must be an HTTPS origin only, for example https://support.example.com"
        )
    return value[:-1] if value.endswith("/") else value


def _request_url(public_origin: str, raw_target: str) -> str:
    if not isinstance(raw_target, str) or not raw_target.startswith("/") or raw_target.startswith("//"):
        raise ValueError("request target must be origin-form")
    if "#" in raw_target:
        raise ValueError("request target must not contain a fragment")
    return public_origin + raw_target


def _auth_token(env_name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env_name or ""):
        raise ValueError("auth token environment variable name is invalid")
    token = os.environ.get(env_name)
    if token is None or not token or token != token.strip() or len(token) > 1024:
        raise ValueError(f"{env_name} must contain the runtime Twilio Auth Token")
    return token


def _load_validator(token: str):
    """Load Twilio's supported validator only when the authenticated edge runs."""
    try:
        from twilio.request_validator import RequestValidator
    except ImportError as exc:
        raise RuntimeError(
            "twilio==9.11.0 is required; install requirements-webhook.txt"
        ) from exc
    return RequestValidator(token)


def _parse_form(body: str) -> dict[str, str]:
    form = parse_qs(
        body,
        keep_blank_values=True,
        strict_parsing=True,
        encoding="utf-8",
        errors="strict",
        max_num_fields=MAX_FORM_FIELDS,
    )
    # The underlying MerchantGate has single-value semantics. Reject ambiguity
    # before validation/dispatch rather than silently dropping signed values.
    if any(len(values) != 1 for values in form.values()):
        raise ValueError("duplicate form field")
    return {key: values[0] for key, values in form.items()}


def make_handler(gate, validator, public_origin: str):
    public_origin = _public_origin(public_origin)

    class Handler(BaseHTTPRequestHandler):
        server_version = "VoiceSupportTwilioEdge/1"

        def log_message(self, *_args):
            pass  # Do not log request bodies, signatures, call IDs, or order data.

        def send(self, body, status=200, mime="application/json; charset=utf-8"):
            if isinstance(body, bytes):
                data = body
            elif isinstance(body, str):
                data = body.encode("utf-8")
            else:
                data = merchant_auth.desk.canonical(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if urlsplit(self.path).path == "/health":
                self.send(
                    {
                        "status": "ok",
                        "provider_authentication": "twilio-request-validator-required",
                        "order_verification": "required",
                        "live_telephone_tested": False,
                    }
                )
            else:
                self.send({"error": "not found"}, 404)

        def do_POST(self):
            try:
                target = self.path
                route = urlsplit(target)
                if route.path not in ("/voice", "/dial-result"):
                    return self.send({"error": "not found"}, 404)
                _request_url(public_origin, target)  # reject non-origin-form targets

                raw_length = self.headers.get("Content-Length", "")
                if not raw_length.isdecimal() or not 0 < int(raw_length) <= MAX_BODY:
                    raise ValueError("Content-Length must be between 1 and 2000000")
                if self.headers.get_content_type() != "application/x-www-form-urlencoded":
                    raise ValueError("voice requests require form-urlencoded input")
                body = self.rfile.read(int(raw_length)).decode("utf-8")
                params = _parse_form(body)

                signature = self.headers.get(SIGNATURE_HEADER, "")
                request_url = _request_url(public_origin, target)
                try:
                    authenticated = bool(signature) and bool(
                        validator.validate(request_url, params, signature)
                    )
                except Exception:
                    authenticated = False
                if not authenticated:
                    return self.send({"error": "request authentication failed"}, 403)

                # No Store/MerchantGate call occurs before the provider signature
                # validates. Validate route-specific shape only after that boundary.
                if route.path == "/dial-result":
                    if route.query:
                        raise ValueError("dial-result does not accept a query string")
                    result = gate.dial_result(
                        params.get("CallSid", ""), params.get("DialCallStatus", "")
                    )
                else:
                    query = parse_qs(
                        route.query,
                        keep_blank_values=True,
                        strict_parsing=True,
                        max_num_fields=2,
                    ) if route.query else {}
                    if set(query) - {"turn"} or len(query.get("turn", ["0"])) != 1:
                        raise ValueError("invalid turn query")
                    stamp = query.get("turn", ["0"])[0]
                    if not re.fullmatch(r"0|[1-9][0-9]*", stamp):
                        raise ValueError("invalid turn query")
                    result = gate.turn(
                        params.get("CallSid", ""),
                        int(stamp),
                        params.get("SpeechResult", ""),
                        params.get("Digits", ""),
                    )
                self.send(result["twiml"], mime="application/xml; charset=utf-8")
            except (ValueError, UnicodeError, OverflowError) as exc:
                self.send(
                    {"error": str(exc)},
                    409 if isinstance(exc, merchant_auth.desk.Conflict) else 400,
                )
            except sqlite3.Error:
                self.send({"error": "database operation failed; retry the same request"}, 503)

    return Handler


def bundle(destination: Path) -> str:
    """Package source/configuration only; never package DBs, tokens, or logs."""
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in BUNDLE_NAMES:
            archive.write(HERE / name, "voice-support-desk/" + name)
    return str(destination)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="voice-support.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--bind", type=_loopback, default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8098)
    serve.add_argument("--public-origin", type=_public_origin, required=True)
    serve.add_argument("--auth-token-env", default=DEFAULT_TOKEN_ENV)
    package = sub.add_parser("bundle")
    package.add_argument("destination", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "bundle":
            print(bundle(args.destination))
            return 0
        token = _auth_token(args.auth_token_env)
        validator = _load_validator(token)
        gate = merchant_auth.MerchantGate(args.db)
        with ThreadingHTTPServer(
            (args.bind, args.port), make_handler(gate, validator, args.public_origin)
        ) as server:
            print(
                f"Authenticated Voice Support edge: http://{args.bind}:{server.server_port} -> {args.public_origin}",
                flush=True,
            )
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        return 0
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
