"""Record one owner-supplied operation in the existing offline laundry engine.

This is deliberately separate from the read-only cli.py. No network, provider,
accounting, payment, sanitation, or quality-inference action is implemented.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
from typing import Any, Callable

from laundry_desk import LaundryDesk, LaundryDeskError, ValidationError
from storage import copy_database

MAX_INPUT_BYTES = 1_048_576
MAX_INPUT_NODES = 10_000
MAX_INPUT_DEPTH = 32

# Each entry points at the already-reviewed engine method, not a second engine.
# Values are (method, required fields, optional fields). Types are exact: bool
# must not masquerade as an integer quantity or price.
COMMANDS: dict[str, tuple[Callable[..., Any], dict[str, type], dict[str, type]]] = {
    "customer": (LaundryDesk.add_customer, {"customer_id": str, "name": str}, {}),
    "site": (LaundryDesk.add_site, {"site_id": str, "customer_id": str, "name": str}, {}),
    "agreement": (LaundryDesk.add_agreement, {"agreement_id": str, "site_id": str,
        "item_code": str, "unit_price_cents": int, "active_from": str}, {"active_to": str}),
    "plan": (LaundryDesk.add_service_plan, {"plan_id": str, "site_id": str,
        "route_code": str, "weekday": int, "stop_sequence": int,
        "active_from": str}, {"active_to": str}),
    "manifest": (LaundryDesk.create_daily_route, {"service_date": str, "route_code": str}, {}),
    "pickup": (LaundryDesk.pickup, {"stop_id": str, "linen_counts": dict,
        "container_ids": list}, {}),
    "process": (LaundryDesk.process, {"stop_id": str, "processed_counts": dict},
        {"damaged_counts": dict}),
    "deliver": (LaundryDesk.deliver, {"stop_id": str, "delivered_counts": dict,
        "container_ids": list}, {}),
    "resolve": (LaundryDesk.resolve_exception, {"exception_id": str,
        "resolution_code": str, "note": str}, {}),
    "invoice-draft": (LaundryDesk.draft_invoice, {"stop_id": str}, {}),
}


def authority() -> dict[str, bool]:
    return {"customer_messaging": False, "provider_navigation": False,
        "accounting_mutation": False, "payment_mutation": False,
        "deployment": False, "revenue_assertion": False,
        "sanitation_certification": False, "quality_inference": False}


def _reject_number(text: str) -> Any:
    raise ValidationError("only integer JSON numbers are admitted")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("duplicate JSON object key")
        result[key] = value
    return result


def load_input(filename: str) -> dict[str, Any]:
    if filename == "-":
        if sys.stdin.isatty():
            raise ValidationError("pipe JSON to stdin or provide an input file")
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    else:
        with Path(filename).open("rb") as handle:
            raw = handle.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValidationError("input exceeds 1048576 bytes")
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_object,
            parse_float=_reject_number, parse_constant=_reject_number)
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ValidationError("input must be bounded UTF-8 JSON") from exc
    if type(value) is not dict:
        raise ValidationError("input must be one JSON object")
    stack = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_INPUT_NODES or depth > MAX_INPUT_DEPTH:
            raise ValidationError("input exceeds structural bounds")
        if type(item) is str:
            try:
                item.encode("utf-8")
            except UnicodeError as exc:
                raise ValidationError("input contains invalid Unicode text") from exc
        if type(item) is dict:
            for key in item:
                try:
                    key.encode("utf-8")
                except UnicodeError as exc:
                    raise ValidationError("input contains invalid Unicode keys") from exc
            stack.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            stack.extend((child, depth + 1) for child in item)
    return value


def validate_input(command: str, payload: dict[str, Any]) -> None:
    _, required, optional = COMMANDS[command]
    required = {"operation_key": str, **required}
    missing = required.keys() - payload.keys()
    unknown = payload.keys() - (required.keys() | optional.keys())
    if missing:
        raise ValidationError("missing fields: " + ", ".join(sorted(missing)))
    if unknown:
        # Do not echo untrusted keys into terminal diagnostics.
        raise ValidationError("input contains unsupported fields")
    for key, expected in {**required, **optional}.items():
        if key not in payload or (key in optional and payload[key] is None):
            continue
        value = payload[key]
        if type(value) is not expected:
            raise ValidationError(f"{key} must be {expected.__name__}")
        if expected is dict:
            if not value or any(type(k) is not str or type(v) is not int
                                for k, v in value.items()):
                raise ValidationError(f"{key} requires text keys and integer counts")
        if expected is list and any(type(v) is not str for v in value):
            raise ValidationError(f"{key} requires text container identifiers")


def _regular_database(path: Path) -> None:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValidationError("database must be a regular file, not a symlink")


def execute(database: str, command: str, input_file: str | None) -> dict[str, Any]:
    path = Path(database)
    if command == "restore":
        if input_file is None:
            raise ValidationError("restore requires --input with a backup path")
        payload = load_input(input_file)
        if (set(payload) != {"backup"} or type(payload["backup"]) is not str
                or not payload["backup"]):
            raise ValidationError("restore input must contain only a nonempty backup path")
        return {"status": "RESTORED", **copy_database(payload["backup"], path),
            "authority": authority()}
    if command == "init":
        if input_file is not None:
            raise ValidationError("init does not accept an input payload")
        # No parent creation or overwrite. A competing initialization loses at
        # exclusive file creation. The data directory must be operator-owned.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        desk = LaundryDesk(path)
        return {"status": "INITIALIZED", "integrity": desk.verify_integrity(),
            "authority": authority()}
    if command not in COMMANDS:
        raise ValidationError("unsupported operation")
    if input_file is None:
        raise ValidationError("this operation requires --input FILE or --input -")
    payload = load_input(input_file)
    validate_input(command, payload)
    _regular_database(path)
    # Validate existing schema without initializing an empty or unrelated file.
    LaundryDesk.open_read_only(path)
    desk = LaundryDesk(path)
    result = COMMANDS[command][0](desk, **payload)
    return {"status": "REPLAYED" if result.replayed else "APPLIED",
        "operation": command, "operation_key": payload["operation_key"],
        "operation_appended": not result.replayed, "result": result.value,
        "authority": authority()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record offline laundry operations; invoice DRAFTS only")
    parser.add_argument("database", help="operator-owned SQLite database; existing parent directory required")
    parser.add_argument("command", choices=["init", "restore", *COMMANDS])
    parser.add_argument("--input", dest="input_file", help="operation JSON, or restore's backup path object; '-' reads piped stdin")
    args = parser.parse_args(argv)
    try:
        result = execute(args.database, args.command, args.input_file)
    except (LaundryDeskError, OSError, sqlite3.Error, OverflowError, ValueError) as exc:
        print(json.dumps({"status": "REJECTED", "error_type": type(exc).__name__,
            "message": str(exc), "authority": authority()}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
