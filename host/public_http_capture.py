#!/usr/bin/env python3
"""Capture explicit public HTTP(S) sources with bounded bodies and checkpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

FORMAT = "commons.public-http-capture.v1"
MAX_SPEC_BYTES = 131072
MAX_SOURCES = 32
CHUNK_BYTES = 65536
HEADER_CHARS = 2048
HEADER_VALUES = 4
HEADERS = (
    "Content-Type", "Content-Length", "Content-Encoding", "Transfer-Encoding",
    "Last-Modified", "ETag", "Date", "Content-Disposition", "Cache-Control",
    "Location",
)
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
USER_AGENT = "Mozilla/5.0 (compatible; CommonsPublicSourceCapture/1.0)"


class CaptureInputError(ValueError):
    """The complete request specification must be valid before any GET."""


class CaptureLimitError(ValueError):
    """A configured body budget stopped this response."""


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _error(exc):
    return {"type": type(exc).__name__, "message": str(exc)[:2048]}


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CaptureInputError(name + " must be a positive integer")
    return value


def _read_spec(path):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise CaptureInputError("sources must be a regular JSON file")
        if before.st_size > MAX_SPEC_BYTES:
            raise CaptureInputError("sources exceed the 128 KiB input limit")
        raw = stream.read(MAX_SPEC_BYTES + 1)
        after = os.fstat(stream.fileno())
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if len(raw) > MAX_SPEC_BYTES or any(
        getattr(before, key) != getattr(after, key) for key in fields
    ):
        raise CaptureInputError("sources changed or exceeded the input limit")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise CaptureInputError("sources are not valid UTF-8 JSON") from exc


def _validate_spec(spec):
    if not isinstance(spec, dict) or set(spec) - {"operation_id", "sources"}:
        raise CaptureInputError("sources JSON needs operation_id and sources only")
    operation = spec.get("operation_id")
    if not isinstance(operation, str) or not NAME.fullmatch(operation):
        raise CaptureInputError("operation_id must be a 1-128 character simple name")
    items = spec.get("sources")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_SOURCES:
        raise CaptureInputError("sources must contain between 1 and 32 entries")
    result, ids, filenames = [], set(), set()
    for item in items:
        if not isinstance(item, dict) or set(item) - {"id", "url", "filename", "accept"}:
            raise CaptureInputError("each source needs id, url, and optional filename/accept")
        source_id = item.get("id")
        filename = item.get("filename", str(source_id) + ".body")
        if not isinstance(source_id, str) or not NAME.fullmatch(source_id):
            raise CaptureInputError("source id must be a simple name")
        if not isinstance(filename, str) or not NAME.fullmatch(filename):
            raise CaptureInputError("source filename must be a simple basename")
        if source_id in ids or filename in filenames:
            raise CaptureInputError("source ids and filenames must be unique")
        url = item.get("url")
        if (
            not isinstance(url, str) or not 1 <= len(url) <= 8192
            or any(ord(char) <= 32 or ord(char) == 127 for char in url)
        ):
            raise CaptureInputError("source URL must be a nonempty HTTP(S) URL without spaces")
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError as exc:
            raise CaptureInputError("source URL has invalid host or port syntax") from exc
        if (
            parts.scheme not in {"http", "https"} or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.fragment or (port is not None and not 1 <= port <= 65535)
        ):
            raise CaptureInputError("source URL needs HTTP(S), a host, and no userinfo/fragment")
        accept = item.get("accept", "*/*")
        if (
            not isinstance(accept, str) or not 1 <= len(accept) <= 512
            or any(ord(char) < 32 or ord(char) == 127 for char in accept)
        ):
            raise CaptureInputError("accept must be a single bounded header value")
        ids.add(source_id)
        filenames.add(filename)
        result.append({"id": source_id, "url": url, "filename": filename, "accept": accept})
    return operation, result


def _write_all(stream, raw):
    remaining = memoryview(raw)
    while remaining:
        count = stream.write(remaining)
        if count is None or count <= 0:
            raise OSError("output write made no progress")
        remaining = remaining[count:]


def _checkpoint(root, manifest):
    """Replace only this new capture's manifest after a fully flushed write."""
    raw = (json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=".acquisition-", suffix=".tmp", dir=root)
    try:
        with os.fdopen(fd, "wb", buffering=0) as stream:
            _write_all(stream, raw)
            os.fsync(stream.fileno())
        os.replace(temporary, root / "acquisition.json")
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _body_identity(path, maximum):
    flags = (
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    with os.fdopen(os.open(path, flags), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise OSError("retained body is not the bounded regular file")
        size = before.st_size
        sha256 = hashlib.sha256()
        git = hashlib.sha1(("blob " + str(size) + "\0").encode("ascii"))
        count = 0
        while count < size:
            chunk = stream.read(min(CHUNK_BYTES, size - count))
            if not chunk:
                raise OSError("retained body shortened while hashing")
            sha256.update(chunk)
            git.update(chunk)
            count += len(chunk)
        after = os.fstat(stream.fileno())
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, key) != getattr(after, key) for key in fields):
            raise OSError("retained body changed while hashing")
    return {"bytes": size, "sha256": sha256.hexdigest(), "git_blob_sha1": git.hexdigest()}


def _response_headers(headers):
    values, truncated = {}, {}
    for name in HEADERS:
        observed = headers.get_all(name, [])
        if observed:
            kept = observed[:HEADER_VALUES]
            values[name] = [str(value)[:HEADER_CHARS] for value in kept]
            lengths = [len(str(value)) for value in kept]
            if len(observed) > HEADER_VALUES or any(length > HEADER_CHARS for length in lengths):
                truncated[name] = {
                    "observed_values": len(observed),
                    "retained_value_lengths": lengths,
                }
    return values, truncated


def _declared_length(headers, status):
    if 100 <= status < 200 or status in {204, 304}:
        return 0
    # Transfer-Encoding controls framing; its Content-Length must not be used.
    if headers.get("Transfer-Encoding") is not None:
        return None
    values = headers.get_all("Content-Length", [])
    if len(values) != 1:
        return None
    value = values[0].strip()
    if not value.isascii() or not value.isdigit() or len(value) > 20:
        return None
    return int(value)


def _capture_one(opener, source, record, root, source_limit, total_remaining, io_timeout):
    path = root / "raw" / source["filename"]
    tick = time.perf_counter()
    created = False
    read_sha256 = hashlib.sha256()
    try:
        record["attempted"] = True
        request = Request(
            source["url"], method="GET",
            headers={
                "User-Agent": USER_AGENT,
                "Accept": source["accept"],
                "Accept-Encoding": "identity",
            },
        )
        try:
            response = opener.open(request, timeout=io_timeout)
        except HTTPError as exc:
            response = exc
        with response:
            record["http_status"] = response.status
            record["http_success"] = 200 <= response.status < 300
            record["response_url"] = response.geturl()
            record["headers"], record["truncated_header_lengths"] = _response_headers(response.headers)
            length = _declared_length(response.headers, response.status)
            record["declared_body_bytes"] = length
            available = min(source_limit, total_remaining)
            if length is not None and length > available:
                raise CaptureLimitError("declared body exceeds the remaining source/aggregate budget")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            with os.fdopen(fd, "wb", buffering=0) as target:
                read = getattr(response, "read1", response.read)
                record["read_method"] = "read1" if hasattr(response, "read1") else "read"
                while True:
                    remaining = available - record["body_bytes_read"]
                    if remaining == 0:
                        # A trusted HTTP length is a framing boundary. An unknown
                        # length at the exact budget is partial, without a +1 read.
                        if length is not None and record["body_bytes_read"] == length:
                            record["completion_basis"] = "content_length"
                            break
                        raise CaptureLimitError("body budget reached before observing its end")
                    chunk = read(min(CHUNK_BYTES, remaining))
                    if not chunk:
                        if length is not None and record["body_bytes_read"] != length:
                            raise OSError("body ended before its declared Content-Length")
                        record["completion_basis"] = "response_end"
                        break
                    record["body_bytes_read"] += len(chunk)
                    read_sha256.update(chunk)
                    if len(chunk) > remaining:
                        raise OSError("HTTP reader returned more bytes than requested")
                    _write_all(target, chunk)
                os.fsync(target.fileno())
            record["body_complete"] = True
            record["state"] = "COMPLETE"
    except Exception as exc:
        record["state"] = "PARTIAL" if created else "FAILED"
        record["error"] = _error(exc)
    finally:
        if created:
            try:
                identity = _body_identity(path, source_limit)
                record["body"] = {"file": "raw/" + source["filename"], **identity}
                if record["body_complete"] and identity["sha256"] != read_sha256.hexdigest():
                    raise OSError("retained body differs from the bytes returned by HTTP")
            except Exception as exc:
                record["body_complete"] = False
                record["state"] = "PARTIAL"
                record["identity_error"] = _error(exc)
        record["read_body_sha256"] = read_sha256.hexdigest()
        record["completed_at"] = _utc()
        record["elapsed_seconds"] = round(time.perf_counter() - tick, 6)


def _refresh_totals(manifest):
    records = manifest["sources"]
    manifest["totals"] = {
        "specified_sources": len(records),
        "attempted_requests": sum(record["attempted"] for record in records),
        "complete_responses": sum(record["body_complete"] for record in records),
        "http_success_responses": sum(record.get("http_success", False) for record in records),
        "body_bytes_read": sum(record["body_bytes_read"] for record in records),
        "retained_body_bytes": sum(record.get("body", {}).get("bytes", 0) for record in records),
    }


def capture_sources(spec, output, *, max_source_bytes=8388608, max_total_bytes=8388608, io_timeout=20.0):
    """Return a manifest; source gaps are data, while local checkpoint errors raise."""
    operation, sources = _validate_spec(spec)
    _positive_int(max_source_bytes, "max_source_bytes")
    _positive_int(max_total_bytes, "max_total_bytes")
    if (
        isinstance(io_timeout, bool) or not isinstance(io_timeout, (int, float))
        or not math.isfinite(io_timeout) or not 0 < io_timeout <= 120
    ):
        raise CaptureInputError("io_timeout must be finite, positive, and at most 120 seconds")
    root = Path(output).absolute()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    (root / "raw").mkdir(mode=0o700)
    tick = time.perf_counter()
    manifest = {
        "format": FORMAT,
        "operation_id": operation,
        "started_at": _utc(),
        "finished": False,
        "capture_complete": False,
        "state": "IN_PROGRESS",
        "limits": {
            "source_count": MAX_SOURCES,
            "per_source_body_bytes": max_source_bytes,
            "aggregate_body_bytes": max_total_bytes,
            "read_chunk_bytes": CHUNK_BYTES,
            "io_timeout_seconds": io_timeout,
            "timeout_scope": "blocking I/O; not a total wall-clock deadline",
        },
        "request_policy": {
            "method": "GET",
            "redirects": "not_followed",
            "origin_authentication": "not_configured",
            "cookie_jar": "not_configured",
            "proxies": "urllib environment defaults",
            "tls_verification": "urllib defaults",
            "automatic_retries": 0,
            "accept_encoding": "identity",
        },
        "sources": [
            {
                "source_id": source["id"],
                "requested_url": source["url"],
                "requested_accept": source["accept"],
                "planned_body_file": "raw/" + source["filename"],
                "state": "PENDING",
                "attempted": False,
                "body_complete": False,
                "body_bytes_read": 0,
            }
            for source in sources
        ],
    }
    _refresh_totals(manifest)
    _checkpoint(root, manifest)
    opener = build_opener(_NoRedirects())
    try:
        for source, record in zip(sources, manifest["sources"]):
            remaining = max_total_bytes - manifest["totals"]["body_bytes_read"]
            if remaining <= 0:
                record["state"] = "NOT_REQUESTED_BUDGET"
                record["error"] = {
                    "type": "CaptureLimitError",
                    "message": "aggregate body budget was consumed by earlier responses",
                }
                _checkpoint(root, manifest)
                continue
            record["state"] = "IN_PROGRESS"
            record["started_at"] = _utc()
            _checkpoint(root, manifest)
            _capture_one(opener, source, record, root, max_source_bytes, remaining, io_timeout)
            _refresh_totals(manifest)
            _checkpoint(root, manifest)
    except KeyboardInterrupt:
        manifest["state"] = "INTERRUPTED"
        _refresh_totals(manifest)
        manifest["interrupted_at"] = _utc()
        _checkpoint(root, manifest)
        raise
    manifest["finished"] = True
    manifest["capture_complete"] = all(record["body_complete"] for record in manifest["sources"])
    manifest["state"] = "COMPLETE" if manifest["capture_complete"] else "PARTIAL"
    manifest["completed_at"] = _utc()
    manifest["elapsed_seconds"] = round(time.perf_counter() - tick, 6)
    _checkpoint(root, manifest)
    return manifest


def _summary(manifest, output):
    return {
        "format": FORMAT,
        "operation_id": manifest["operation_id"],
        "state": manifest["state"],
        "capture_complete": manifest["capture_complete"],
        "manifest": str(Path(output).absolute() / "acquisition.json"),
        "totals": manifest["totals"],
        "sources": [
            {
                "source_id": record["source_id"],
                "state": record["state"],
                "http_status": record.get("http_status"),
                "body_complete": record["body_complete"],
                "body": record.get("body"),
                "error": record.get("error", record.get("identity_error")),
            }
            for record in manifest["sources"]
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", required=True, help="bounded JSON request specification")
    parser.add_argument("--out", required=True, help="new capture directory; existing paths are refused")
    parser.add_argument("--max-source-bytes", type=int, default=8388608)
    parser.add_argument("--max-total-bytes", type=int, default=8388608)
    parser.add_argument("--io-timeout", type=float, default=20.0)
    args = parser.parse_args(argv)
    try:
        spec = _read_spec(args.sources)
        manifest = capture_sources(
            spec, args.out, max_source_bytes=args.max_source_bytes,
            max_total_bytes=args.max_total_bytes, io_timeout=args.io_timeout,
        )
    except CaptureInputError as exc:
        print("public_http_capture: " + str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("public_http_capture: interrupted; inspect the retained checkpoint", file=sys.stderr)
        return 130
    except (OSError, ValueError) as exc:
        print("public_http_capture: " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(_summary(manifest, args.out), ensure_ascii=False, allow_nan=False))
    if not manifest["capture_complete"]:
        print("public_http_capture: incomplete capture; inspect acquisition.json", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
