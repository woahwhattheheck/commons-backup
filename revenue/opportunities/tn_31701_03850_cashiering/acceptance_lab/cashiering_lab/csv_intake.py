"""Explicit normalized CSV assembly and retained-source cashiering replay.

The existing cashiering engine remains the only reconciliation implementation.
Source mapping, source authenticity and completeness remain owner-supplied.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys

from .artifacts import ALL_FILES, FILE_LIMIT, _read_fd, _require_posix, bundle, read_input
from .core import ID, MAX_BYTES, MAX_ROWS, SCOPE, InputError, _pairs, canonical, parse


CASE_FIELDS = ("schema", "case_id", "period", "currency_scale", "variance_reason_threshold_minor")
HEADERS = {
    "batches.csv": ("id", *SCOPE, "cashier", "opened_at", "closed_at", "opening_cash_minor",
                    "counted_cash_minor", "retained_cash_minor", "declared_total_minor", "variance_reason"),
    "transactions.csv": ("id", "batch_id", "kind", "timestamp", "original_id", "original_minor",
                         "rounding_minor", "collected_minor", "evidence_ref"),
    "tenders.csv": ("transaction_id", "type", "amount_minor"),
    "allocations.csv": ("transaction_id", "account_id", "amount_minor"),
    "deposits.csv": ("id", *SCOPE, "tender", "observed_minor", "variance_reason", "evidence_ref"),
    "deposit_batches.csv": ("deposit_id", "batch_id"),
}
SOURCE_FILES = {"case.json", *HEADERS}
ROOT_FILES = {"source", "review", "lineage.json", "manifest.json"}
NULLABLE = {"counted_cash_minor", "declared_total_minor", "observed_minor", "variance_reason", "original_id"}
INTEGER = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")


def _constant(value: str) -> None:
    raise InputError(f"case.json: unsupported constant {value}")


def _source_bytes(sources: dict[str, bytes]) -> None:
    if type(sources) is not dict or set(sources) != SOURCE_FILES:
        raise InputError("source requires exactly case.json and the six documented CSV files")
    if any(type(value) is not bytes for value in sources.values()):
        raise InputError("source values must be original file bytes")
    if sum(map(len, sources.values())) > MAX_BYTES:
        raise InputError(f"combined source bytes exceed {MAX_BYTES}")


def _table(name: str, raw: bytes) -> list[tuple[dict, dict]]:
    try:
        stream = io.StringIO(raw.decode("utf-8-sig"), newline="")
    except UnicodeError as exc:
        raise InputError(f"{name}: requires UTF-8 CSV") from exc
    reader = csv.reader(stream, strict=True)
    rows = []
    try:
        header = next(reader, None)
        if header is None or len(header) != len(HEADERS[name]) or set(header) != set(HEADERS[name]):
            raise InputError(f"{name}: header must contain exactly {', '.join(HEADERS[name])}")
        previous_line = reader.line_num
        for cells in reader:
            location = {"source_file": name, "line_start": previous_line + 1, "line_end": reader.line_num}
            previous_line = reader.line_num
            label = f"{name}:{location['line_start']}"
            if len(cells) != len(header):
                raise InputError(f"{label}: expected {len(header)} cells; blank and ragged records are unsupported")
            row = dict(zip(header, cells))
            for field, value in row.items():
                if not value and field in NULLABLE:
                    row[field] = None
                elif field.endswith("_minor"):
                    if len(value) > 17 or not INTEGER.fullmatch(value):
                        raise InputError(f"{label}.{field}: requires integer minor units without plus, decimals, grouping or leading zeroes")
                    row[field] = int(value)
            rows.append((row, location))
            if len(rows) > 4 * MAX_ROWS:
                raise InputError(f"{name}: at most {4 * MAX_ROWS} CSV records are supported")
    except csv.Error as exc:
        raise InputError(f"{name}:{reader.line_num}: malformed CSV: {exc}") from exc
    return rows


def _keyed(rows: list[tuple[dict, dict]]) -> dict[str, tuple[int, dict]]:
    result = {}
    for index, (row, location) in enumerate(rows):
        key = row["id"]
        label = f"{location['source_file']}:{location['line_start']}"
        if not ID.fullmatch(key):
            raise InputError(f"{label}.id: requires a stable ASCII identifier")
        if key in result:
            raise InputError(f"{label}.id: duplicate id {key}")
        result[key] = (index, row)
    return result


def assemble(sources: dict[str, bytes]) -> tuple[bytes, dict]:
    """Join explicit tables, preserving order and source locations, then validate."""
    _source_bytes(sources)
    try:
        metadata = json.loads(sources["case.json"].decode("utf-8"), object_pairs_hook=_pairs,
                              parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise InputError(f"case.json: unsupported strict UTF-8 JSON: {exc}") from exc
    if type(metadata) is not dict or set(metadata) != set(CASE_FIELDS):
        raise InputError(f"case.json: fields must be exactly {', '.join(CASE_FIELDS)}")
    tables = {name: _table(name, sources[name]) for name in HEADERS}
    data = dict(metadata)
    lineage = [{"pointer": f"/{field}", "source_file": "case.json", "line_start": 1,
                "line_end": max(1, len(sources['case.json'].splitlines()))} for field in CASE_FIELDS]
    indexes = {}
    for name in ("batches", "transactions", "deposits"):
        rows = tables[f"{name}.csv"]
        indexes[name] = _keyed(rows)
        data[name] = [row for row, _ in rows]
        lineage.extend({"pointer": f"/{name}/{index}", **location} for index, (_, location) in enumerate(rows))
    for row, location in tables["transactions.csv"]:
        if row["batch_id"] not in indexes["batches"]:
            raise InputError(f"transactions.csv:{location['line_start']}.batch_id: unknown batch {row['batch_id']}")
        row["tenders"], row["allocations"] = [], []
    for row, _ in tables["deposits.csv"]:
        row["batch_ids"] = []
    for name, code in (("tenders", "type"), ("allocations", "account_id")):
        seen = set()
        for row, location in tables[f"{name}.csv"]:
            tid = row["transaction_id"]
            label = f"{name}.csv:{location['line_start']}"
            if tid not in indexes["transactions"]:
                raise InputError(f"{label}.transaction_id: unknown transaction {tid}")
            key = (tid, row[code])
            if key in seen:
                raise InputError(f"{label}: duplicate {code} {row[code]} for transaction {tid}")
            seen.add(key)
            index, transaction = indexes["transactions"][tid]
            parts = transaction[name]
            lineage.append({"pointer": f"/transactions/{index}/{name}/{len(parts)}", **location})
            parts.append({code: row[code], "amount_minor": row["amount_minor"]})
    seen_assignments = set()
    for row, location in tables["deposit_batches.csv"]:
        did, bid = row["deposit_id"], row["batch_id"]
        label = f"deposit_batches.csv:{location['line_start']}"
        if did not in indexes["deposits"] or bid not in indexes["batches"]:
            raise InputError(f"{label}: unknown deposit_id {did} or batch_id {bid}")
        if (did, bid) in seen_assignments:
            raise InputError(f"{label}: duplicate deposit/batch assignment {did}/{bid}")
        seen_assignments.add((did, bid))
        index, deposit = indexes["deposits"][did]
        lineage.append({"pointer": f"/deposits/{index}/batch_ids/{len(deposit['batch_ids'])}", **location})
        deposit["batch_ids"].append(bid)
    raw = canonical(data)
    parse(raw)
    return raw, {"schema": "cashiering-csv-lineage/1", "input_sha256": hashlib.sha256(raw).hexdigest(),
                 "locations": lineage}


def split(raw: bytes) -> dict[str, bytes]:
    """Produce editable normalized CSVs from an already supported JSON input."""
    data = parse(raw)
    sources = {"case.json": canonical({key: data[key] for key in CASE_FIELDS})}
    rows = {name: [] for name in HEADERS}
    for name in ("batches", "transactions", "deposits"):
        rows[f"{name}.csv"] = [{key: row[key] for key in HEADERS[f"{name}.csv"]} for row in data[name]]
    for transaction in data["transactions"]:
        for name in ("tenders", "allocations"):
            rows[f"{name}.csv"].extend({"transaction_id": transaction["id"], **part} for part in transaction[name])
    for deposit in data["deposits"]:
        rows["deposit_batches.csv"].extend({"deposit_id": deposit["id"], "batch_id": bid} for bid in deposit["batch_ids"])
    for name, header in HEADERS.items():
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows[name])
        sources[name] = stream.getvalue().encode("utf-8")
    assemble(sources)
    return sources


def handoff(sources: dict[str, bytes]) -> dict[str, bytes]:
    """Build the full handoff from retained source bytes without trusting hashes."""
    raw, lineage = assemble(sources)
    files = {f"source/{name}": value for name, value in sources.items()}
    files.update({f"review/{name}": value for name, value in bundle(raw).items()})
    files["lineage.json"] = canonical(lineage)
    files["manifest.json"] = canonical({
        "schema": "cashiering-csv-handoff/1", "input_sha256": hashlib.sha256(raw).hexdigest(),
        "source_authenticity": "NOT_ATTESTED", "source_completeness": "NOT_ATTESTED",
        "files": {name: {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
                  for name, value in sorted(files.items())},
    })
    if any(len(value) > FILE_LIMIT for value in files.values()):
        raise InputError(f"an assembled handoff artifact exceeds {FILE_LIMIT} bytes")
    return files


def _open_directory(path: Path | str, *, dir_fd: int | None = None) -> int:
    _require_posix()
    return os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=dir_fd)


def _read_files(fd: int, expected: set[str], limit: int) -> dict[str, bytes]:
    if set(os.listdir(fd)) != expected:
        raise InputError(f"directory entries must be exactly {', '.join(sorted(expected))}")
    result = {}
    for name in sorted(expected):
        child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            result[name] = _read_fd(child, limit)
        finally:
            os.close(child)
    return result


def read_sources(path: Path | str) -> dict[str, bytes]:
    fd = _open_directory(path)
    try:
        sources = _read_files(fd, SOURCE_FILES, MAX_BYTES)
        _source_bytes(sources)
        return sources
    finally:
        os.close(fd)


def _write_files(fd: int, files: dict[str, bytes]) -> None:
    for name in sorted(files, key=lambda value: (value == "manifest.json", value)):
        child = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        try:
            remaining = memoryview(files[name])
            while remaining:
                written = os.write(child, remaining)
                if written <= 0:
                    raise OSError(f"short write without progress: {name}")
                remaining = remaining[written:]
            os.fsync(child)
        finally:
            os.close(child)
    os.fsync(fd)


def write_sources(path: Path | str, files: dict[str, bytes]) -> None:
    _source_bytes(files)
    _require_posix()
    os.mkdir(path, 0o700)
    fd = _open_directory(path)
    try:
        _write_files(fd, files)
    finally:
        os.close(fd)


def write_handoff(path: Path | str, files: dict[str, bytes]) -> None:
    expected = {"lineage.json", "manifest.json"} | {f"source/{name}" for name in SOURCE_FILES} | {f"review/{name}" for name in ALL_FILES}
    if type(files) is not dict or set(files) != expected:
        raise InputError("handoff artifacts require the exact source, review, lineage and manifest files")
    if any(type(value) is not bytes or len(value) > FILE_LIMIT for value in files.values()):
        raise InputError(f"handoff artifacts require bytes no larger than {FILE_LIMIT}")
    _require_posix()
    os.mkdir(path, 0o700)
    fd = _open_directory(path)
    try:
        for name in ("source", "review"):
            os.mkdir(name, 0o700, dir_fd=fd)
            child = _open_directory(name, dir_fd=fd)
            try:
                _write_files(child, {key.split("/", 1)[1]: value for key, value in files.items() if key.startswith(name + "/")})
            finally:
                os.close(child)
        _write_files(fd, {key: value for key, value in files.items() if "/" not in key})
    finally:
        os.close(fd)


def verify(path: Path | str) -> dict:
    fd = _open_directory(path)
    try:
        if set(os.listdir(fd)) != ROOT_FILES:
            raise InputError("handoff requires exactly source, review, lineage.json and manifest.json")
        actual = {}
        for directory, names, limit in (("source", SOURCE_FILES, MAX_BYTES), ("review", ALL_FILES, FILE_LIMIT)):
            child = _open_directory(directory, dir_fd=fd)
            try:
                actual.update({f"{directory}/{name}": value for name, value in _read_files(child, names, limit).items()})
            finally:
                os.close(child)
        for name in ("lineage.json", "manifest.json"):
            child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            try:
                actual[name] = _read_fd(child, FILE_LIMIT)
            finally:
                os.close(child)
        expected = handoff({name: actual[f"source/{name}"] for name in SOURCE_FILES})
        for name, value in expected.items():
            if actual[name] != value:
                raise InputError(f"{name}: retained-source replay differs")
        report = json.loads(expected["review/report.json"])
        return {"verification": "EXACT_REPLAY_MATCH", "report_status": report["status"],
                "findings_count": report["findings_count"], "input_sha256": report["input_sha256"],
                "source_authenticity": "NOT_ATTESTED", "source_completeness": "NOT_ATTESTED"}
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, source in (("split", "input"), ("compile", "source")):
        command = subparsers.add_parser(name)
        command.add_argument(source, type=Path)
        command.add_argument("--out", type=Path, required=True)
    subparsers.add_parser("verify").add_argument("handoff", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "split":
            sources = split(read_input(args.input))
            write_sources(args.out, sources)
            print(f"WROTE {len(sources)} normalized source files: {args.out}")
            return 0
        if args.command == "verify":
            print(canonical(verify(args.handoff)).decode(), end="")
            return 0
        files = handoff(read_sources(args.source))
        write_handoff(args.out, files)
        report = json.loads(files["review/report.json"])
        print(f"{report['status']}: {report['findings_count']} findings; handoff: {args.out}")
        return 1 if report["findings_count"] else 0
    except (InputError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
