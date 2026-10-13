#!/usr/bin/env python3
"""Lossless UIOWA-023 CSV/JSON transport.

Uses the existing evidence semantics, never recomputes an assessment. All I/O
is offline. Transport validation does not authenticate sources.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = "uiowa-023-evidence-register/1"
HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "uiowa023_register_validator", HERE / "validate_23_evidence_register.py"
)
if _spec is None or _spec.loader is None:
    raise ImportError("Cannot load sibling UIOWA-023 validator")
_validator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_validator)


class RegisterError(ValueError):
    """Malformed, inconsistent or unsupported register input."""


def _fail(errors: list[str]) -> None:
    if errors:
        raise RegisterError("; ".join(errors))


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RegisterError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise RegisterError(f"non-finite JSON value is not supported: {value}")


def validate_packet(packet: Any) -> dict[str, Any]:
    if not isinstance(packet, dict) or set(packet) != {"schema", "columns", "rows"}:
        raise RegisterError("packet must contain exactly schema, columns and rows")
    if packet["schema"] != SCHEMA:
        raise RegisterError(f"unsupported register schema: {packet['schema']!r}")
    _fail(_validator.validate_records(packet["columns"], packet["rows"]))
    # Return fresh containers. Callers cannot accidentally change their input by
    # sorting or otherwise modifying the normalized transport representation.
    columns = list(packet["columns"])
    return {"schema": SCHEMA, "columns": columns,
            "rows": [{c: row[c] for c in columns} for row in packet["rows"]]}


def from_csv(text: str) -> dict[str, Any]:
    columns, rows, errors = _validator.parse_csv(text)
    _fail(errors)
    return {"schema": SCHEMA, "columns": columns, "rows": rows}


def from_json(text: str) -> dict[str, Any]:
    if not isinstance(text, str):
        raise RegisterError("JSON input must be text")
    try:
        packet = json.loads(text, object_pairs_hook=_unique_object,
                            parse_constant=_reject_constant)
    except RegisterError:
        raise
    except (ValueError, RecursionError) as exc:
        raise RegisterError(f"JSON input error: {exc}") from exc
    return validate_packet(packet)


def to_json(packet: Any) -> str:
    return json.dumps(validate_packet(packet), ensure_ascii=False, indent=2,
                      allow_nan=False) + "\n"


def to_csv(packet: Any) -> str:
    packet = validate_packet(packet)
    output = io.StringIO(newline="")
    # CRLF quotes either embedded newline spelling correctly. Record-level
    # fidelity is promised, not identical source quoting or physical newlines.
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(packet["columns"])
    for row in packet["rows"]:
        writer.writerow([row[c] for c in packet["columns"]])
    return output.getvalue()


def _read_text(path: Path) -> str:
    try:
        # read_bytes + decode preserves CRLF inside a cell; read_text does not.
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        raise RegisterError(f"cannot read UTF-8 input {path}: {exc}") from exc


def load_packet(path: Path, kind: str) -> dict[str, Any]:
    text = _read_text(path)
    if kind == "csv":
        return from_csv(text)
    if kind == "json":
        return from_json(text)
    raise RegisterError(f"unsupported input format: {kind!r}")


def publish_new(path: Path, text: str) -> None:
    """Publish fully prepared bytes without overwriting an existing path.

    Temp and final are on one filesystem. Link creation is exclusive. This is
    for a trusted working directory, not an adversarial concurrent filesystem.
    """
    payload = text.encode("utf-8")
    temporary: str | None = None
    publication_error: OSError | ValueError | None = None
    cleanup_error: OSError | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent,
                                         prefix=".uiowa031-", delete=False) as stream:
            temporary = stream.name
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    except (OSError, ValueError) as exc:
        publication_error = exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError as exc:
                cleanup_error = exc
    if publication_error is not None:
        detail = f"cannot publish new output {path}: {publication_error}"
        if cleanup_error is not None:
            detail += f"; cannot remove temporary file {temporary}: {cleanup_error}"
        raise RegisterError(detail) from publication_error
    if cleanup_error is not None:
        # Exclusive link creation already committed the complete output. A
        # cleanup warning must not relabel that successful publication as a
        # refusal or encourage a retry that would encounter an existing file.
        print(f"WARNING: output published at {path}; cannot remove temporary "
              f"file {temporary}: {cleanup_error}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("csv-to-json", "json-to-csv"):
        command = commands.add_parser(name)
        command.add_argument("input", type=Path)
        command.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "csv-to-json":
            text = to_json(load_packet(args.input, "csv"))
        elif args.command == "json-to-csv":
            text = to_csv(load_packet(args.input, "json"))
        publish_new(args.output, text)
    except (RegisterError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"OK {args.command}: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
