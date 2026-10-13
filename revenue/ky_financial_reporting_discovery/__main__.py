"""Compare retained report rows and export a local exception list."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys

from .demo import demo_input
from .parity_probe import compare_rows
from .validation_probe import ValidationError

MAX_INPUT_BYTES = 16_000_000
INPUT_KEYS = {"schema", "key_fields", "compare_fields", "legacy_rows", "target_rows"}
KINDS = ("MISSING_TARGET_ROW", "EXTRA_TARGET_ROW", "VALUE_DRIFT")


def encode(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                       indent=2) + "\n").encode("utf-8")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def reject_number(value):
    raise ValidationError("floats and non-finite numbers are unsupported; use exact decimal strings")


def read_input(path):
    # Inspect the opened object before reading, including pipes and devices.
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValidationError("input must be a regular UTF-8 JSON file")
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValidationError(f"input exceeds {MAX_INPUT_BYTES} bytes; nothing was truncated")
    data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_object,
                      parse_float=reject_number, parse_constant=reject_number)
    return data, raw


def compile_report(data, raw):
    if type(data) is not dict or set(data) != INPUT_KEYS:
        raise ValidationError("input must contain exactly: " + ", ".join(sorted(INPUT_KEYS)))
    if data["schema"] != "report-row-parity/v1":
        raise ValidationError("schema must be report-row-parity/v1")
    findings = compare_rows(data["legacy_rows"], data["target_rows"],
                            data["key_fields"], data["compare_fields"])
    rows = [{"kind": kind, "key": list(key), "field": field}
            for kind, key, field in findings]
    return {
        "schema": "report-row-parity-result/v1",
        "state": "DIFFERENCES" if rows else "MATCH",
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "legacy_row_count": len(data["legacy_rows"]),
        "target_row_count": len(data["target_rows"]),
        "key_fields": data["key_fields"],
        "compare_fields": data["compare_fields"],
        "finding_count": len(rows),
        "finding_counts": {kind: sum(row["kind"] == kind for row in rows) for kind in KINDS},
        "findings": rows,
        "scope": "Exact supplied rows and selected fields only; no completeness, live-source, cutover or financial acceptance claim.",
    }


def render_csv(report):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["kind", "key_json", "field_json"])
    for finding in report["findings"]:
        # JSON keeps scalar types and prevents spreadsheet formula interpretation.
        writer.writerow([finding["kind"], json.dumps(finding["key"], ensure_ascii=False),
                         json.dumps(finding["field"], ensure_ascii=False)])
    return stream.getvalue().encode("utf-8")


def render_markdown(report):
    def cell(value):
        return json.dumps(value, ensure_ascii=False).replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")

    lines = ["# Report row comparison", "", f"State: **{report['state']}**", "",
             f"Legacy rows: {report['legacy_row_count']}. Target rows: {report['target_row_count']}.",
             f"Findings: {report['finding_count']} (value drift counts fields, not unique rows).", "",
             report["scope"], "", "| Finding | Key (JSON) | Field (JSON) |", "| --- | --- | --- |"]
    for finding in report["findings"]:
        lines.append(f"| {finding['kind']} | {cell(finding['key'])} | {cell(finding['field'])} |")
    if not report["findings"]:
        lines.append("| No differences in supplied rows | | |")
    lines.extend(["", "Input SHA-256: `" + report["input_sha256"] + "`", ""])
    return "\n".join(lines).encode("utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="sanitized UTF-8 JSON comparison input")
    source.add_argument("--demo", action="store_true", help="run the retained fictional one-row demonstration")
    parser.add_argument("--out", type=Path, help="new directory for report.json, findings.csv and report.md")
    args = parser.parse_args(argv)
    try:
        if args.demo:
            data = demo_input()
            raw = encode(data)
        else:
            data, raw = read_input(args.input)
        report = compile_report(data, raw)
        payloads = {"report.json": encode(report), "findings.csv": render_csv(report),
                    "report.md": render_markdown(report)}
        if args.out is not None:
            args.out.mkdir(mode=0o700)
            for name, payload in payloads.items():
                with (args.out / name).open("xb") as stream:
                    stream.write(payload)
        sys.stdout.buffer.write(payloads["report.json"])
        return 0
    except (ValidationError, ValueError, OSError, UnicodeError, RecursionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
