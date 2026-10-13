#!/usr/bin/env python3
"""One local CSV/JSON workbench, retaining both existing intake contracts.

Run `python workbench.py --port 8767` and open the exact printed loopback URL.
Uploads and downloads remain in request/browser memory; no job store is created.
"""
from __future__ import annotations

import argparse
import base64
import json
import secrets
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from csv_intake import PLAN_SCHEMA, bundle_bytes, compile_csv, inspect_csv
from errors import ParityError
from export_intake import build_manifest, parse_export
from offline_report import render_html
from parity import compile_bytes
from parity_schema import (
    MAX_AGE_SECONDS, MAX_INPUT_BYTES, _bool, _exact_keys, _identifier, _int,
    _normalize_mapping, _safe_string, _timestamp, canonical_bytes, loads_strict, sha256,
)

MAX_REQUEST_BYTES = 12_000_000
MAX_PLAN_BYTES = 100_000
GENERAL_PLAN_SCHEMA = "saas-migration-workbench-plan/v1"
ASSET_ROOT = Path(__file__).resolve().parent
SNAPSHOT_META = {"snapshot_id", "schema_revision", "captured_at_utc", "complete"}
PLAN_KEYS = {"schema", "cutover_at_utc", "max_snapshot_age_seconds", "key_map",
             "field_map", "source_snapshot", "target_snapshot"}


def text_bytes(value: Any, limit: int = MAX_INPUT_BYTES) -> bytes:
    if type(value) is not str:
        raise ParityError("File content must be original UTF-8 text")
    raw = value.encode("utf-8", errors="strict")
    if len(raw) > limit:
        raise ParityError(f"File exceeds {limit} bytes; nothing was truncated")
    return raw


def plan_mode(plan: Any) -> str:
    """Validate an imported reusable plan without inventing export records."""
    _exact_keys(plan, PLAN_KEYS, "intake plan")
    schema = plan["schema"]
    if schema not in (PLAN_SCHEMA, GENERAL_PLAN_SCHEMA):
        raise ParityError("Unsupported plan schema; CSV aliases and original-field plans are not interchangeable")
    mode = "csv-plan" if schema == PLAN_SCHEMA else "general"
    _timestamp(plan["cutover_at_utc"], "cutover_at_utc")
    _int(plan["max_snapshot_age_seconds"], "max_snapshot_age_seconds", low=0, high=MAX_AGE_SECONDS)
    for side in ("source", "target"):
        snapshot = plan[f"{side}_snapshot"]
        _exact_keys(snapshot, SNAPSHOT_META | ({"delimiter"} if mode == "csv-plan" else {"format"}), f"{side}_snapshot")
        _identifier(snapshot["snapshot_id"], f"{side}.snapshot_id")
        _identifier(snapshot["schema_revision"], f"{side}.schema_revision")
        _timestamp(snapshot["captured_at_utc"], f"{side}.captured_at_utc")
        _bool(snapshot["complete"], f"{side}.complete")
        if mode == "csv-plan":
            if snapshot["delimiter"] not in (",", ";", "\t"):
                raise ParityError("CSV plans require an explicit comma, semicolon or tab delimiter")
        elif snapshot["format"] not in ("csv", "json"):
            raise ParityError("General plans require an explicit csv or json format")
    for key, limit in (("key_map", 4), ("field_map", 32)):
        entries = plan[key]
        if mode == "general":
            _normalize_mapping(entries, key, max_rows=limit)
            continue
        if type(entries) is not list or not 1 <= len(entries) <= limit:
            raise ParityError(f"{key} requires 1..{limit} explicit mappings")
        seen: dict[str, set[str]] = {"source": set(), "target": set()}
        for index, entry in enumerate(entries, 1):
            _exact_keys(entry, {"source", "target", "type"}, f"{key}[{index}]")
            types = ("string", "integer") if key == "key_map" else ("string", "integer", "boolean")
            if entry["type"] not in types:
                raise ParityError(f"{key}[{index}] has an unsupported type")
            for side in ("source", "target"):
                name = _safe_string(entry[side], f"{key}[{index}].{side}", max_len=256)
                if name in seen[side]:
                    raise ParityError(f"{key} repeats a {side} column")
                seen[side].add(name)
    if len(canonical_bytes(plan)) > MAX_PLAN_BYTES:
        raise ParityError("Plan exceeds 100,000 bytes")
    return mode


def compare_exports(request: Any) -> dict[str, str]:
    if type(request) is not dict:
        raise ParityError("Comparison request must be an object")
    if "mode" in request:
        _exact_keys(request, {"mode", "plan", "source_text", "target_text"}, "comparison")
        plan = request["plan"]
        mode = plan_mode(plan)
        if request["mode"] != mode:
            raise ParityError("Selected mode does not match the plan schema")
        source = text_bytes(request["source_text"])
        target = text_bytes(request["target_text"])
        if mode == "general":
            intake_request = {key: plan[key] for key in ("cutover_at_utc", "max_snapshot_age_seconds", "key_map", "field_map")}
            for side, raw in (("source", source), ("target", target)):
                intake_request[side] = {**plan[f"{side}_snapshot"], "text": raw.decode("utf-8")}
    else:
        # Retain the previous general comparison payload, now with provenance.
        intake_request = request
        manifest = build_manifest(intake_request)
        mode = "general"
        plan = {"schema": GENERAL_PLAN_SCHEMA, **{key: request[key] for key in ("cutover_at_utc", "max_snapshot_age_seconds", "key_map", "field_map")}}
        for side in ("source", "target"):
            plan[f"{side}_snapshot"] = {key: value for key, value in request[side].items() if key != "text"}
        plan_mode(plan)
        source, target = (text_bytes(request[side]["text"]) for side in ("source", "target"))
    if mode == "csv-plan":
        result = compile_csv(source, target, plan)
        manifest = canonical_bytes(result["manifest"])
    else:
        if "mode" in request:
            manifest = build_manifest(intake_request)
        report, markdown = compile_bytes(manifest)
        result = {"manifest": loads_strict(manifest), "report": report, "markdown": markdown, "plan": plan,
                  "intake": {"columns": [{"role": role, **entry} for role in ("key_map", "field_map") for entry in plan[role]],
                             "notice": "General intake preserves original field names and retains all supplied fields, including unmapped values, in the private replay manifest. Only explicitly mapped fields are compared."}}
    provenance = {**result["intake"], "plan_schema": plan["schema"], "mode": mode,
                  "original_file_sha256": {"source": sha256(source), "target": sha256(target)},
                  "original_file_bytes": {"source": len(source), "target": len(target)},
                  "generated_manifest_sha256": sha256(manifest),
                  "original_files_in_bundle": False}
    # Both routes use the existing five-file bundler. Its plan schema identifies
    # the adapter; the legacy CSV CLI and its own plan remain unchanged.
    result["intake"] = provenance
    return {"manifest_json": manifest.decode("utf-8"),
            "report_json": canonical_bytes(result["report"]).decode("utf-8"),
            "report_markdown": result["markdown"], "report_html": render_html(result["report"]),
            "plan_json": canonical_bytes(plan).decode("utf-8"),
            "intake_json": canonical_bytes(provenance).decode("utf-8"),
            "bundle_base64": base64.b64encode(bundle_bytes(result)).decode("ascii"), "mode": mode}


def inspect_export(request: Any) -> dict[str, Any]:
    if type(request) is dict and "mode" not in request:
        _exact_keys(request, {"format", "text"}, "export preview")
        request = {**request, "mode": "general", "delimiter": ","}
    _exact_keys(request, {"mode", "format", "text", "delimiter"}, "export preview")
    raw = text_bytes(request["text"])
    if request["mode"] == "csv-plan":
        if request["format"] != "csv" or type(request["delimiter"]) is not str:
            raise ParityError("CSV-plan mode requires CSV and an explicit delimiter")
        info = inspect_csv(raw, request["delimiter"])
        columns, count = info["headers"], info["record_count"]
    elif request["mode"] == "general":
        columns, records = parse_export(request["text"], request["format"])
        count = len(records)
    else:
        raise ParityError("Unknown intake mode")
    return {"columns": columns, "record_count": count, "original_file_sha256": sha256(raw), "byte_count": len(raw)}


def make_handler(assets: dict[str, tuple[str, bytes]], token: str) -> type[BaseHTTPRequestHandler]:
    class WorkbenchHandler(BaseHTTPRequestHandler):
        server_version = "ParityWorkbench/1.1"
        sys_version = ""

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(20)

        def log_message(self, format: str, *args: Any) -> None:
            pass  # No uploaded values, filenames, tokens or request bodies.

        def respond(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            if self.command != "HEAD":
                self.wfile.write(body)

        def json_response(self, status: int, value: Any) -> None:
            self.respond(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))

        def valid_host(self) -> bool:
            return self.headers.get_all("Host", []) == [f"127.0.0.1:{self.server.server_port}"]

        def do_GET(self) -> None:
            if not self.valid_host():
                self.json_response(403, {"error": "Open the exact printed loopback URL"})
                return
            asset = assets.get(self.path)
            if asset is None:
                self.json_response(404, {"error": "Unknown route"})
                return
            self.respond(200, asset[1], asset[0])

        do_HEAD = do_GET

        def do_POST(self) -> None:
            origin = f"http://127.0.0.1:{self.server.server_port}"
            supplied = self.headers.get_all("X-Intake-Token", [])
            if (not self.valid_host() or self.headers.get_all("Origin", []) != [origin]
                    or len(supplied) != 1 or not secrets.compare_digest(supplied[0].encode("utf-8"), token.encode("ascii"))):
                self.json_response(403, {"error": "Request must originate from this local workbench page"})
                return
            if self.path not in ("/api/inspect", "/api/compare", "/api/plan"):
                self.json_response(404, {"error": "Unknown route"})
                return
            if self.headers.get("Transfer-Encoding"):
                self.json_response(400, {"error": "Send a fixed-length JSON request"})
                return
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                self.json_response(415, {"error": "Content-Type must be application/json"})
                return
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdecimal() or len(lengths[0]) > 9:
                self.json_response(411, {"error": "One valid Content-Length is required"})
                return
            length = int(lengths[0])
            if not 0 < length <= MAX_REQUEST_BYTES:
                self.json_response(413, {"error": f"Request must contain 1..{MAX_REQUEST_BYTES} bytes"})
                return
            try:
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ParityError("Request ended before its declared length")
                request = loads_strict(raw)
                if self.path == "/api/inspect":
                    result = inspect_export(request)
                elif self.path == "/api/plan":
                    _exact_keys(request, {"plan_text"}, "plan import")
                    plan = loads_strict(text_bytes(request["plan_text"], MAX_PLAN_BYTES))
                    mode = plan_mode(plan)
                    result = {"mode": mode, "plan_json": canonical_bytes(plan).decode("utf-8")}
                else:
                    result = compare_exports(request)
                self.json_response(200, result)
            except (ParityError, UnicodeError, ValueError) as exc:
                self.json_response(400, {"error": str(exc)})
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True
            except TimeoutError:
                self.json_response(408, {"error": "Request timed out"})
            except Exception as exc:
                print(f"ERROR: request failed ({type(exc).__name__})", file=sys.stderr)
                self.json_response(500, {"error": "Comparison could not complete; check the server terminal"})
    return WorkbenchHandler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8767, help="loopback TCP port; 0 selects an available port")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    try:
        token = secrets.token_urlsafe(32)
        page = (ASSET_ROOT / "workbench.html").read_text(encoding="utf-8").replace("__WORKBENCH_TOKEN__", token)
        assets = {"/": ("text/html; charset=utf-8", page.encode("utf-8")),
                  "/workbench.js": ("text/javascript; charset=utf-8", (ASSET_ROOT / "workbench.js").read_bytes())}
        with HTTPServer(("127.0.0.1", args.port), make_handler(assets, token)) as server:
            print(f"Parity workbench: http://127.0.0.1:{server.server_port}/", flush=True)
            print("Local operator tool. No upload storage or external services. Ctrl+C stops it.", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        return 0
    except OSError as exc:
        print(f"ERROR: workbench could not start: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
