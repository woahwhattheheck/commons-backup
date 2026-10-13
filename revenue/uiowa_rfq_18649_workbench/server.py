#!/usr/bin/env python3
"""Loopback-only analyst workbench for the University of Iowa RFQ 18649 carrier.

This server deliberately exposes only the existing compiler's *untrusted inspection*
path. It cannot accept or mint a trusted authority root and cannot emit current READY
or any buyer/commercial authority.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

MAX_BODY_BYTES = 2 * 1024 * 1024
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/sample_session.js": ("sample_session.js", "text/javascript; charset=utf-8"),
    "/draft_bundle.js": ("draft_bundle.js", "text/javascript; charset=utf-8"),
    "/handoff_import.js": ("handoff_import.js", "text/javascript; charset=utf-8"),
    "/handoff.js": ("handoff.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/review_navigation.js": ("review_navigation.js", "text/javascript; charset=utf-8"),
    "/review_navigation.css": ("review_navigation.css", "text/css; charset=utf-8"),
    "/review_navigation_workbench.js": ("review_navigation_workbench.js", "text/javascript; charset=utf-8"),
}


class WorkbenchError(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise WorkbenchError(f"duplicate JSON key: {ascii(key)}")
        out[key] = value
    return out


def _reject_constant(token: str) -> Any:
    raise WorkbenchError("non-finite JSON numeric constants are not supported")


def _finite_float(token: str) -> float:
    # Preserve the compiler's existing Python-float interface. Do not silently
    # introduce Decimal into its schemas or claim arbitrary decimal precision.
    value = float(token)
    if not math.isfinite(value):
        raise WorkbenchError("JSON number overflows the supported finite numeric range")
    significand = token.lower().partition("e")[0]
    if value == 0.0 and any(digit in "123456789" for digit in significand):
        raise WorkbenchError("JSON number underflows the supported numeric range; not treated as zero")
    return value


def _check_scalar_text(value: Any) -> None:
    # JSON escapes can encode lone surrogates even when the input bytes are valid
    # UTF-8. Check both keys and values before compiler or response serialization.
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            try:
                item.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise WorkbenchError("JSON strings must contain valid Unicode scalar values") from exc
        elif isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)


def loads_strict_json(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise WorkbenchError("request body must be valid UTF-8") from exc
    try:
        value = json.loads(
            text, object_pairs_hook=_strict_object,
            parse_constant=_reject_constant, parse_float=_finite_float,
        )
        _check_scalar_text(value)
        return value
    except WorkbenchError:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError, OverflowError) as exc:
        raise WorkbenchError("request body must be strict JSON within supported parsing limits") from exc


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkbenchError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise WorkbenchError(
            f"{label} keys must be exactly {sorted(expected)}; got {sorted(actual)}"
        )
    return value


class CompilerAdapter:
    """Narrow adapter to the already-landed parent compiler.

    Only compile_untrusted_inspection + semantic integrity verification are used.
    Trusted-root/current/historical APIs are intentionally never imported into this
    adapter's callable surface.
    """

    def __init__(self) -> None:
        parent = Path(__file__).resolve().parents[1] / "uiowa_rfq_18649_workshare"
        if not parent.is_dir():
            raise WorkbenchError("parent Iowa workshare compiler directory is missing")
        parent_s = str(parent)
        if parent_s not in sys.path:
            sys.path.insert(0, parent_s)
        try:
            import compiler as carrier  # type: ignore
        except Exception as exc:  # fail closed: never substitute a home-grown compiler
            raise WorkbenchError("parent Iowa workshare compiler could not be loaded") from exc
        self._carrier = carrier

    def inspect(self, candidate: Any, authority: Any) -> dict[str, Any]:
        carrier = self._carrier
        try:
            normalized_authority = carrier.normalize_authority(authority)
            sources = normalized_authority["sources"]
            if not sources:
                raise WorkbenchError("authority must contain at least one source")
            inspection_at = max(
                carrier._parse_utc(row["observed_at"], "source.observed_at")
                for row in sources
            )
            report = carrier.compile_untrusted_inspection(candidate, authority, now=inspection_at)
            integrity = carrier.verify_report_integrity(report)
        except WorkbenchError:
            raise
        except Exception as exc:
            raise WorkbenchError(f"compiler rejected the supplied evidence: {exc}") from exc

        if report.get("mode") != "UNTRUSTED_INSPECTION":
            raise WorkbenchError("compiler returned a non-inspection mode")
        trust = report.get("trust")
        if not isinstance(trust, dict):
            raise WorkbenchError("compiler report omitted trust boundary")
        if trust.get("authority_root_supplied_out_of_band") is not False:
            raise WorkbenchError("inspection unexpectedly used a trusted authority root")
        if trust.get("current_evidence_review_authority") is not False:
            raise WorkbenchError("inspection unexpectedly emitted current review authority")
        if integrity.get("receipt_sha256") != report.get("receipt_sha256"):
            raise WorkbenchError("semantic-integrity receipt mismatch")
        return report


class _Handler(BaseHTTPRequestHandler):
    server_version = "TJLabs-Iowa-Workbench/1"
    protocol_version = "HTTP/1.1"
    static_root: Path
    adapter: Any

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Intentionally suppress request logging: intake may contain private evidence.
        return

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")

    def _send_bytes(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, "application/json; charset=utf-8", body)

    def _host_is_loopback(self) -> bool:
        raw = (self.headers.get("Host") or "").strip()
        if not raw or any(ch in raw for ch in "\r\n/@"):
            return False
        # urlsplit handles bracketed IPv6; server itself still binds IPv4 loopback.
        try:
            parsed = urlsplit("//" + raw)
        except ValueError:
            return False
        return parsed.hostname in {"127.0.0.1", "localhost", "::1"}

    def _origin_matches_host(self) -> bool:
        host = (self.headers.get("Host") or "").strip()
        origin = (self.headers.get("Origin") or "").strip()
        return origin == f"http://{host}"

    def _reject_bad_host(self) -> bool:
        if self._host_is_loopback():
            return False
        self._send_json(421, {"error": "loopback Host required"})
        return True

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        if self._reject_bad_host():
            return
        entry = STATIC_FILES.get(urlsplit(self.path).path)
        if entry is None:
            self._send_json(404, {"error": "not found"})
            return
        filename, content_type = entry
        path = self.static_root / filename
        try:
            body = path.read_bytes()
        except OSError:
            self._send_json(500, {"error": "static asset unavailable"})
            return
        self._send_bytes(200, content_type, body)

    def do_POST(self) -> None:  # noqa: N802
        if self._reject_bad_host():
            return
        if self.path != "/api/inspect":
            self._send_json(404, {"error": "not found"})
            return
        if not self._origin_matches_host():
            self._send_json(403, {"error": "same-origin browser request required"})
            return
        media_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            self._send_json(415, {"error": "Content-Type application/json required"})
            return
        raw_len = (self.headers.get("Content-Length") or "").strip()
        if not raw_len.isdigit():
            self._send_json(411, {"error": "valid Content-Length required"})
            return
        length = int(raw_len)
        if length <= 0 or length > MAX_BODY_BYTES:
            self._send_json(413, {"error": "request body outside bounded size"})
            return
        raw = self.rfile.read(length)
        if len(raw) != length:
            self._send_json(400, {"error": "truncated request body"})
            return
        try:
            payload = _exact_keys(loads_strict_json(raw), {"candidate", "authority"}, "request")
            report = self.adapter.inspect(payload["candidate"], payload["authority"])
        except WorkbenchError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        self._send_json(200, {"report": report})

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "method not allowed"})

    def do_PUT(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "method not allowed"})

    def do_DELETE(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "method not allowed"})


def make_handler(static_root: Path, adapter: Any) -> type[_Handler]:
    class Handler(_Handler):
        pass

    Handler.static_root = static_root
    Handler.adapter = adapter
    return Handler


def create_server(
    *,
    port: int = 8765,
    adapter: Any | None = None,
    static_root: Path | None = None,
) -> ThreadingHTTPServer:
    if not (0 <= port <= 65535):
        raise WorkbenchError("port outside valid range")
    root = static_root or Path(__file__).resolve().parent
    handler = make_handler(root, adapter or CompilerAdapter())
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        server = create_server(port=args.port)
    except (OSError, WorkbenchError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    host, port = server.server_address[:2]
    print(f"UIOWA_WORKBENCH_LOCAL_ONLY http://{host}:{port}/", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
