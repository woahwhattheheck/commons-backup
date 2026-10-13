#!/usr/bin/env python3
"""Offline SaaS migration parity diagnostic and CLI."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from errors import ParityError
from parity_schema import (
    CLASSIFICATIONS, ENGINE_VERSION, INPUT_SCHEMA, MAX_INPUT_BYTES, MAX_RECORDS, RECEIPT_SCHEMA, REPORT_SCHEMA,
    _age_state, _index_records, _mismatch_fields, _normalize_manifest, _snapshot_public, _strip_runtime,
    canonical_bytes, loads_strict, sha256,
)
from secure_io import read_bounded_regular as _read_bounded_regular, write_pair_exclusive as _write_pair_exclusive

def compile_bytes(raw: bytes) -> tuple[dict[str, Any], str]:
    if len(raw) > MAX_INPUT_BYTES:
        raise ParityError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    obj = loads_strict(raw)
    norm = _normalize_manifest(obj)
    semantic = _strip_runtime(norm)
    source = norm["source_snapshot"]
    target = norm["target_snapshot"]
    cutover = norm["_cutover"]
    max_age = norm["max_snapshot_age_seconds"]
    src_fresh, src_age = _age_state(source, cutover, max_age)
    dst_fresh, dst_age = _age_state(target, cutover, max_age)
    snapshots_complete = source["complete"] and target["complete"]

    src_index, src_invalid_key_count = _index_records(source["records"], norm["key_map"], "source")
    dst_index, dst_invalid_key_count = _index_records(target["records"], norm["key_map"], "target")
    rows: list[dict[str, Any]] = []
    for key in sorted(set(src_index) | set(dst_index)):
        srcs = src_index.get(key, [])
        dsts = dst_index.get(key, [])
        public_key = key.removeprefix("invalid:")
        row: dict[str, Any] = {"key_commitment": public_key, "mismatch_fields": []}
        if key.startswith("invalid:"):
            row["classification"] = "INVALID_EVIDENCE"
            row["reason_codes"] = ["INVALID_RECORD_KEY"]
        elif not snapshots_complete:
            row["classification"] = "INVALID_EVIDENCE"
            row["reason_codes"] = ["SNAPSHOT_INCOMPLETE"]
        elif len(srcs) > 1 or len(dsts) > 1:
            row["classification"] = "DUPLICATE_KEY"
            row["reason_codes"] = [
                *( ["DUPLICATE_SOURCE_KEY"] if len(srcs) > 1 else [] ),
                *( ["DUPLICATE_TARGET_KEY"] if len(dsts) > 1 else [] ),
            ]
        elif not src_fresh or not dst_fresh:
            row["classification"] = "STALE_EVIDENCE"
            row["reason_codes"] = [
                *( ["SOURCE_SNAPSHOT_STALE_OR_FUTURE"] if not src_fresh else [] ),
                *( ["TARGET_SNAPSHOT_STALE_OR_FUTURE"] if not dst_fresh else [] ),
            ]
        elif not srcs:
            row["classification"] = "UNEXPECTED_TARGET"
            row["reason_codes"] = ["TARGET_RECORD_HAS_NO_SOURCE_KEY"]
        elif not dsts:
            row["classification"] = "MISSING_TARGET"
            row["reason_codes"] = ["SOURCE_RECORD_HAS_NO_TARGET_KEY"]
        else:
            valid, mismatches = _mismatch_fields(srcs[0], dsts[0], norm["field_map"])
            if not valid:
                row["classification"] = "INVALID_EVIDENCE"
                row["reason_codes"] = ["MAPPED_FIELD_MISSING_OR_WRONG_TYPE"]
            elif mismatches:
                row["classification"] = "FIELD_MISMATCH"
                row["reason_codes"] = ["MAPPED_VALUE_DIFFERS"]
                row["mismatch_fields"] = mismatches
            else:
                row["classification"] = "PARITY"
                row["reason_codes"] = []
        rows.append(row)

    counts = {name: 0 for name in CLASSIFICATIONS}
    for row in rows:
        counts[row["classification"]] += 1
    clean = (
        counts["PARITY"] == len(rows)
        and snapshots_complete
        and src_fresh
        and dst_fresh
        and len(source["records"]) == len(target["records"])
    )
    report_core: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "engine_version": ENGINE_VERSION,
        "offer": {
            "diagnostic_price_usd_cents": 500_000,
            "max_records_per_snapshot": MAX_RECORDS,
            "optional_integration_sprint_usd_cents": 1_000_000,
            "custom_adapter_included": False,
            "scope": "one sanitized source export + one sanitized target export",
        },
        "authority": {
            "network_calls_performed": False,
            "provider_credentials_used": False,
            "production_migration_write_authorized": False,
            "customer_contact_authorized": False,
            "contract_or_signature_authorized": False,
            "payment_authorized": False,
            "revenue_recognition_authorized": False,
        },
        "input": {
            "raw_input_sha256": sha256(raw),
            "semantic_manifest_sha256": sha256(canonical_bytes(semantic)),
        },
        "cutover_at_utc": norm["cutover_at_utc"],
        "max_snapshot_age_seconds": max_age,
        "source_snapshot": {**_snapshot_public(source), "age_seconds_at_cutover": src_age, "fresh_at_cutover": src_fresh},
        "target_snapshot": {**_snapshot_public(target), "age_seconds_at_cutover": dst_age, "fresh_at_cutover": dst_fresh},
        "key_map": norm["key_map"],
        "field_map": norm["field_map"],
        "summary": {
            "diagnostic_state": "PARITY_CONFIRMED" if clean else "DIFFERENCES_OR_HOLDS_FOUND",
            "union_key_count": len(rows),
            "source_invalid_key_records": src_invalid_key_count,
            "target_invalid_key_records": dst_invalid_key_count,
            "counts": counts,
        },
        "rows": rows,
    }
    report_sha = sha256(canonical_bytes(report_core))
    report = dict(report_core)
    report["receipt"] = {
        "schema": RECEIPT_SCHEMA,
        "report_core_sha256": report_sha,
        "raw_input_sha256": sha256(raw),
        "semantic_manifest_sha256": sha256(canonical_bytes(semantic)),
    }
    return report, render_markdown(report)


def render_markdown(report: dict[str, Any]) -> str:
    counts = report["summary"]["counts"]
    src = report["source_snapshot"]
    dst = report["target_snapshot"]
    lines = [
        "# SaaS Migration Parity Pilot — Export-only Diagnostic",
        "",
        "**Fixed diagnostic:** $5,000 for one sanitized source export + one sanitized target export, up to 500 records per snapshot. **Optional integration sprint:** $10,000 only after the diagnostic establishes value and real adapter scope. No free custom adapter is included.",
        "",
        f"**Point-in-time state:** `{report['summary']['diagnostic_state']}` at cutover `{report['cutover_at_utc']}`.",
        "",
        "## Snapshot custody",
        "",
        f"- Source: `{src['snapshot_id']}` / schema `{src['schema_revision']}` / {src['record_count']} records / captured `{src['captured_at_utc']}` / fresh={str(src['fresh_at_cutover']).lower()} / complete={str(src['complete']).lower()} / records SHA-256 `{src['records_sha256']}`.",
        f"- Target: `{dst['snapshot_id']}` / schema `{dst['schema_revision']}` / {dst['record_count']} records / captured `{dst['captured_at_utc']}` / fresh={str(dst['fresh_at_cutover']).lower()} / complete={str(dst['complete']).lower()} / records SHA-256 `{dst['records_sha256']}`.",
        f"- Exact input bytes SHA-256: `{report['input']['raw_input_sha256']}`.",
        f"- Semantic manifest SHA-256: `{report['input']['semantic_manifest_sha256']}`.",
        "",
        "## Results",
        "",
        "| Classification | Count |",
        "|---|---:|",
    ]
    for name in CLASSIFICATIONS:
        lines.append(f"| {name} | {counts[name]} |")
    lines += [
        "",
        "Row-level JSON contains only opaque key commitments and value digests for differences; raw record identifiers and compared values are not reproduced in this buyer projection.",
        "",
        "## Acceptance boundary",
        "",
        "This diagnostic verifies parity only for the supplied sanitized export bytes, explicit key/field map, declared completeness, and cutover freshness policy. It does **not** mutate either SaaS system, prove unseen records are absent, certify a production cutover, use provider credentials, or authorize customer contact, contract/signature, payment, or revenue recognition.",
        "",
        f"Receipt core SHA-256: `{report['receipt']['report_core_sha256']}`.",
    ]
    return "\n".join(lines) + "\n"


def _verify_compiled_bytes(
    expected: dict[str, Any], expected_bytes: bytes, report_raw: bytes,
) -> tuple[bool, str]:
    observed = loads_strict(report_raw)
    if type(observed) is not dict:
        return False, "report is not object"
    if report_raw != expected_bytes:
        return False, "report bytes differ from deterministic recompilation"
    return True, expected["receipt"]["report_core_sha256"]


def verify_bytes(input_raw: bytes, report_raw: bytes) -> tuple[bool, str]:
    expected, _ = compile_bytes(input_raw)
    return _verify_compiled_bytes(expected, canonical_bytes(expected), report_raw)



def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compile", help="compile deterministic diagnostic")
    c.add_argument("--input", required=True, type=Path)
    c.add_argument("--report-json", required=True, type=Path)
    c.add_argument("--report-md", required=True, type=Path)
    v = sub.add_parser("verify", help="recompile and verify exact report bytes")
    v.add_argument("--input", required=True, type=Path)
    v.add_argument("--report-json", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        input_raw = _read_bounded_regular(args.input, MAX_INPUT_BYTES)
        if args.command == "compile":
            report, markdown = compile_bytes(input_raw)
            _write_pair_exclusive(args.report_json, canonical_bytes(report), args.report_md, markdown.encode("utf-8"))
            print(json.dumps({
                "state": report["summary"]["diagnostic_state"],
                "report_core_sha256": report["receipt"]["report_core_sha256"],
                "raw_input_sha256": report["input"]["raw_input_sha256"],
                "network_calls_performed": False,
            }, sort_keys=True))
            return 0
        expected, _ = compile_bytes(input_raw)
        expected_bytes = canonical_bytes(expected)
        # Mismatch digests can make a valid report larger than its input manifest.
        report_limit = max(MAX_INPUT_BYTES, len(expected_bytes))
        report_raw = _read_bounded_regular(args.report_json, report_limit)
        ok, detail = _verify_compiled_bytes(expected, expected_bytes, report_raw)
        print(json.dumps({"verified": ok, "detail": detail}, sort_keys=True))
        return 0 if ok else 2
    except ParityError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli())
