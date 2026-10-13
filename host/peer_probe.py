#!/usr/bin/env python3
"""Emit a bounded, deterministic peer capability self-report.

Input is a JSON object on stdin (or ``--input PATH``)::

    {
      "schema": "commons-peer-probe-input/v1",
      "harness": {"family": "Codex", "surface": "cloud"},
      "observed_at": "2026-09-01T08:00:00Z",
      "roads": [
        {"id": "python", "kind": "command",
         "argv": [sys.executable, "-c", "print('READY')"],
         "timeout_seconds": 2}
      ],
      "claimed_cants": [
        {"id": "no-direct-slack", "condition": "UNAVAILABLE",
         "evidence_ref": "road:slack", "tooling_need": "Slack relay"}
      ]
    }

Roads run in catalog order. Supported road kinds are ``command`` and ``http``.
Commands never use a shell and receive a fixed, credential-free environment.
HTTP probes disable environment proxies and redirects, reject URL credentials,
and cap response reads. Probe failures are report rows, never silent skips.
Invalid input (including an unknown road kind) fails before any probe runs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request


INPUT_SCHEMA = "commons-peer-probe-input/v1"
REPORT_SCHEMA = "commons-peer-self-report/v1"
ROAD_KINDS = ("command", "http")
MAX_TIMEOUT_SECONDS = 30.0
MAX_CAPTURE_BYTES = 65_536
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


class ProbeInputError(ValueError):
    """The requested probe is invalid and no road should be attempted."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        """Keep network access on the exact URL named by the input."""
        return None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeInputError(message)


def _exact_keys(value: object, required: set[str], optional: set[str], at: str) -> None:
    _require(isinstance(value, dict), f"{at} must be an object")
    keys = set(value)
    missing = sorted(required - keys)
    extra = sorted(keys - required - optional)
    _require(not missing, f"{at} missing keys {missing!r}")
    _require(not extra, f"{at} has unknown keys {extra!r}")


def _text(value: object, at: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{at} must be nonempty text")
    return value.strip()


def _timestamp(value: object, at: str) -> str:
    text = _text(value, at)
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProbeInputError(f"{at} must be an RFC3339 timestamp") from exc
    _require(parsed.tzinfo is not None, f"{at} must include a timezone")
    return text


def _timeout(value: object, at: str) -> float:
    _require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{at} must be numeric")
    timeout = float(value)
    _require(0 < timeout <= MAX_TIMEOUT_SECONDS, f"{at} must be > 0 and <= {MAX_TIMEOUT_SECONDS:g}")
    return timeout


def _capture_limit(value: object, at: str) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool), f"{at} must be an integer")
    _require(0 < value <= MAX_CAPTURE_BYTES, f"{at} must be > 0 and <= {MAX_CAPTURE_BYTES}")
    return value


def _validate_road(raw: object, index: int) -> dict:
    at = f"roads[{index}]"
    _require(isinstance(raw, dict), f"{at} must be an object")
    kind = raw.get("kind")
    _require(kind in ROAD_KINDS, f"{at}.kind unknown: {kind!r}")
    common_required = {"id", "kind", "timeout_seconds"}
    common_optional = {"max_capture_bytes"}
    if kind == "command":
        _exact_keys(raw, common_required | {"argv"}, common_optional, at)
        argv = raw["argv"]
        _require(isinstance(argv, list) and argv, f"{at}.argv must be a nonempty list")
        _require(all(isinstance(item, str) and item for item in argv), f"{at}.argv entries must be nonempty text")
        normalized = {
            "id": _text(raw["id"], f"{at}.id"),
            "kind": kind,
            "timeout_seconds": _timeout(raw["timeout_seconds"], f"{at}.timeout_seconds"),
            "max_capture_bytes": _capture_limit(raw.get("max_capture_bytes", MAX_CAPTURE_BYTES), f"{at}.max_capture_bytes"),
            "argv": list(argv),
        }
        return normalized

    _exact_keys(raw, common_required | {"url"}, common_optional | {"method", "expected_status"}, at)
    url = _text(raw["url"], f"{at}.url")
    parsed = urllib.parse.urlsplit(url)
    _require(parsed.scheme in ("http", "https") and bool(parsed.hostname), f"{at}.url must be absolute HTTP(S)")
    _require(parsed.username is None and parsed.password is None, f"{at}.url must not contain credentials")
    _require(not parsed.fragment, f"{at}.url must not contain a fragment")
    method = str(raw.get("method", "HEAD")).upper()
    _require(method in ("GET", "HEAD"), f"{at}.method must be GET or HEAD")
    expected = raw.get("expected_status", [200])
    _require(isinstance(expected, list) and expected, f"{at}.expected_status must be a nonempty list")
    _require(all(isinstance(code, int) and not isinstance(code, bool) and 100 <= code <= 599 for code in expected),
             f"{at}.expected_status entries must be HTTP status integers")
    return {
        "id": _text(raw["id"], f"{at}.id"),
        "kind": kind,
        "timeout_seconds": _timeout(raw["timeout_seconds"], f"{at}.timeout_seconds"),
        "max_capture_bytes": _capture_limit(raw.get("max_capture_bytes", MAX_CAPTURE_BYTES), f"{at}.max_capture_bytes"),
        "url": url,
        "method": method,
        "expected_status": list(expected),
    }


def validate_input(raw: object) -> dict:
    """Validate the entire catalog before any command or network operation."""
    _exact_keys(raw, {"schema", "harness", "roads", "claimed_cants"}, {"observed_at"}, "input")
    _require(raw["schema"] == INPUT_SCHEMA, f"input.schema must be {INPUT_SCHEMA!r}")
    harness = raw["harness"]
    _exact_keys(harness, {"family", "surface"}, set(), "input.harness")
    normalized_harness = {
        "family": _text(harness["family"], "input.harness.family"),
        "surface": _text(harness["surface"], "input.harness.surface"),
    }
    roads = raw["roads"]
    _require(isinstance(roads, list) and roads, "input.roads must be a nonempty catalog")
    normalized_roads = [_validate_road(row, index) for index, row in enumerate(roads)]
    road_ids = [row["id"] for row in normalized_roads]
    _require(len(road_ids) == len(set(road_ids)), "input.roads contains duplicate ids")

    claimed_cants = raw["claimed_cants"]
    _require(isinstance(claimed_cants, list), "input.claimed_cants must be a list")
    normalized_cants = []
    for index, row in enumerate(claimed_cants):
        at = f"claimed_cants[{index}]"
        _exact_keys(row, {"id", "condition", "evidence_ref", "tooling_need"}, set(), at)
        normalized_cants.append({key: _text(row[key], f"{at}.{key}") for key in ("id", "condition", "evidence_ref", "tooling_need")})
    cant_ids = [row["id"] for row in normalized_cants]
    _require(len(cant_ids) == len(set(cant_ids)), "input.claimed_cants contains duplicate ids")

    observed_at = raw.get("observed_at")
    if observed_at is None:
        observed_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    else:
        observed_at = _timestamp(observed_at, "input.observed_at")
    return {
        "harness": normalized_harness,
        "observed_at": observed_at,
        "roads": normalized_roads,
        "claimed_cants": normalized_cants,
    }


def _digest(raw: bytes, limit: int) -> dict:
    clipped = raw[:limit]
    return {
        "bytes": len(clipped),
        "sha256": hashlib.sha256(clipped).hexdigest(),
        "truncated": len(raw) > limit,
    }


def _drain(stream, sink: bytearray, limit: int) -> None:
    """Drain a child pipe while retaining at most limit + 1 bytes."""
    while True:
        chunk = stream.read(8192)
        if not chunk:
            return
        remaining = limit + 1 - len(sink)
        if remaining > 0:
            sink.extend(chunk[:remaining])


def _command_probe(road: dict) -> dict:
    try:
        process = subprocess.Popen(
            road["argv"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            env={"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"},
        )
    except OSError:
        return {"id": road["id"], "kind": "command", "status": "ERROR", "evidence": {"error": "EXEC_ERROR"}}
    stdout = bytearray()
    stderr = bytearray()
    threads = (
        threading.Thread(target=_drain, args=(process.stdout, stdout, road["max_capture_bytes"]), daemon=True),
        threading.Thread(target=_drain, args=(process.stderr, stderr, road["max_capture_bytes"]), daemon=True),
    )
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=road["timeout_seconds"])
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait()
    for thread in threads:
        thread.join()
    process.stdout.close()
    process.stderr.close()
    if timed_out:
        return {
            "id": road["id"], "kind": "command", "status": "ERROR",
            "evidence": {"error": "TIMEOUT", "stdout": _digest(bytes(stdout), road["max_capture_bytes"]),
                         "stderr": _digest(bytes(stderr), road["max_capture_bytes"])},
        }
    evidence = {
        "exit_code": process.returncode,
        "stdout": _digest(bytes(stdout), road["max_capture_bytes"]),
        "stderr": _digest(bytes(stderr), road["max_capture_bytes"]),
    }
    return {"id": road["id"], "kind": "command", "status": "PASS" if process.returncode == 0 else "FAIL", "evidence": evidence}


def _http_probe(road: dict) -> dict:
    request = urllib.request.Request(road["url"], method=road["method"])
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        response = opener.open(request, timeout=road["timeout_seconds"])
    except urllib.error.HTTPError as exc:
        response = exc
    except (OSError, urllib.error.URLError):
        return {"id": road["id"], "kind": "http", "status": "ERROR", "evidence": {"error": "NETWORK_ERROR"}}
    try:
        body = response.read(road["max_capture_bytes"] + 1) if road["method"] == "GET" else b""
        status_code = int(response.getcode())
    finally:
        response.close()
    body_evidence = _digest(body, road["max_capture_bytes"])
    evidence = {"status_code": status_code, "body": body_evidence}
    status = "PASS" if status_code in road["expected_status"] and not body_evidence["truncated"] else "FAIL"
    return {"id": road["id"], "kind": "http", "status": status, "evidence": evidence}


def run_probe(road: dict) -> dict:
    if road["kind"] == "command":
        return _command_probe(road)
    if road["kind"] == "http":
        return _http_probe(road)
    raise AssertionError("validated road kind was not executable")


def validate_report(report: object) -> None:
    _exact_keys(report, {"schema", "harness", "observed_at", "roads_attempted", "road_results", "claimed_cants"}, set(), "report")
    _require(report["schema"] == REPORT_SCHEMA, "report.schema mismatch")
    _exact_keys(report["harness"], {"family", "surface"}, set(), "report.harness")
    _timestamp(report["observed_at"], "report.observed_at")
    _require(isinstance(report["roads_attempted"], list), "report.roads_attempted must be a list")
    _require(isinstance(report["road_results"], list), "report.road_results must be a list")
    _require(report["roads_attempted"] == [row.get("id") for row in report["road_results"]],
             "report road order/result ids mismatch")
    for index, row in enumerate(report["road_results"]):
        _exact_keys(row, {"id", "kind", "status", "evidence"}, set(), f"report.road_results[{index}]")
        _require(row["kind"] in ROAD_KINDS, f"report.road_results[{index}].kind invalid")
        _require(row["status"] in ("PASS", "FAIL", "ERROR"), f"report.road_results[{index}].status invalid")
        _require(isinstance(row["evidence"], dict) and bool(row["evidence"]), f"report.road_results[{index}].evidence empty")
    _require(isinstance(report["claimed_cants"], list), "report.claimed_cants must be a list")
    for index, row in enumerate(report["claimed_cants"]):
        _exact_keys(row, {"id", "condition", "evidence_ref", "tooling_need"}, set(), f"report.claimed_cants[{index}]")


def compile_report(raw: object) -> dict:
    request = validate_input(raw)
    results = [run_probe(road) for road in request["roads"]]
    report = {
        "schema": REPORT_SCHEMA,
        "harness": request["harness"],
        "observed_at": request["observed_at"],
        "roads_attempted": [road["id"] for road in request["roads"]],
        "road_results": results,
        "claimed_cants": request["claimed_cants"],
    }
    validate_report(report)
    return report


def canonical(report: object) -> bytes:
    return (json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def self_test() -> dict:
    fixture = {
        "schema": INPUT_SCHEMA,
        "harness": {"family": "stdlib-self-test", "surface": "local"},
        "observed_at": "2026-09-01T08:00:00Z",
        "roads": [{
            "id": "python", "kind": "command",
            "argv": [sys.executable, "-c", "print('peer-probe-pass')"],
            "timeout_seconds": 2,
        }],
        "claimed_cants": [],
    }
    first = canonical(compile_report(fixture))
    second = canonical(compile_report(fixture))
    if first != second:
        raise AssertionError("fixed self-test fixture was not byte-identical")
    report = json.loads(first)
    validate_report(report)
    if report["road_results"][0]["status"] != "PASS":
        raise AssertionError("self-test command road did not pass")
    return {"schema": "commons-peer-probe-self-test/v1", "status": "PASS", "checks": 3}


def _load_input(path: str) -> object:
    if path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-", help="input JSON path (default: stdin)")
    parser.add_argument("--self-test", action="store_true", help="run the deterministic built-in fixture")
    args = parser.parse_args(argv)
    try:
        result = self_test() if args.self_test else compile_report(_load_input(args.input))
    except (OSError, json.JSONDecodeError, ProbeInputError, AssertionError) as exc:
        print(f"peer-probe: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
