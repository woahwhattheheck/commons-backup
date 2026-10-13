from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from laundry_desk import LaundryDesk, LaundryDeskError
from storage import copy_database


def _export_stem(prefix: str, object_id: str) -> str:
    readable = f"{prefix}-{object_id.replace(':', '_')}"
    if len((readable + ".json").encode("utf-8")) <= 240:
        return readable
    digest = hashlib.sha256(object_id.encode("utf-8")).hexdigest()
    return f"{prefix}-sha256-{digest}"


def _write_export_bundle(out: Path, prefix: str, object_id: str, exports: dict[str, str]) -> dict[str, str]:
    out.mkdir(parents=True, exist_ok=True)
    if out.is_symlink():
        raise RuntimeError("refusing symlink export directory")

    suffixes = {"json": "json", "csv": "csv", "markdown": "md"}
    stem = _export_stem(prefix, object_id)
    planned: list[tuple[str, Path, str]] = []
    for kind, text in exports.items():
        if kind not in suffixes:
            raise RuntimeError(f"unsupported export kind: {kind}")
        target = out / f"{stem}.{suffixes[kind]}"
        planned.append((kind, target, text))

    occupied = [target for _, target, _ in planned if target.exists() or target.is_symlink()]
    if occupied:
        raise FileExistsError(f"refusing to overwrite existing export path: {occupied[0]}")

    created_paths: list[Path] = []
    created: dict[str, str] = {}
    try:
        for kind, target, text in planned:
            with target.open("x", encoding="utf-8", newline="") as handle:
                created_paths.append(target)
                handle.write(text)
                handle.flush()
            created[kind] = str(target)
    except BaseException:
        for target in reversed(created_paths):
            try:
                target.unlink()
            except FileNotFoundError:
                pass
        raise
    return created


def _cli_authority() -> dict[str, bool]:
    return {
        "customer_messaging": False,
        "provider_navigation": False,
        "accounting_mutation": False,
        "payment_mutation": False,
        "deployment": False,
        "revenue_assertion": False,
        "sanitation_certification": False,
        "quality_inference": False,
    }


def _run() -> int:
    parser = argparse.ArgumentParser(description="Commercial Laundry Route & Linen Custody Operations Desk")
    parser.add_argument("database", help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("route-snapshot")
    p.add_argument("route_id")
    p = sub.add_parser("customer-snapshot")
    p.add_argument("customer_id")
    sub.add_parser("integrity")
    p = sub.add_parser("export-route")
    p.add_argument("route_id")
    p.add_argument("directory")
    p = sub.add_parser("export-customer")
    p.add_argument("customer_id")
    p.add_argument("directory")

    p = sub.add_parser("backup", help="write a standalone SQLite backup to a new file")
    p.add_argument("destination", help="new backup file; parent must already exist")

    args = parser.parse_args()
    if args.command == "backup":
        result = {"status": "BACKED_UP", **copy_database(args.database, args.destination),
            "authority": _cli_authority()}
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    # Every CLI command is observational with respect to the source SQLite
    # database. Export commands may create only their requested handoff bundle.
    desk = LaundryDesk.open_read_only(args.database)
    if args.command == "route-snapshot":
        result = desk.route_snapshot(args.route_id)
    elif args.command == "customer-snapshot":
        result = desk.customer_snapshot(args.customer_id)
    elif args.command == "integrity":
        result = desk.verify_integrity()
        # The library keeps its historical `integrity` key; the CLI exposes a
        # stable human/operator status field without mutating that library API.
        result["status"] = result["integrity"]
    else:
        route_mode = args.command == "export-route"
        object_id = args.route_id if route_mode else args.customer_id
        exports = desk.render_route_exports(object_id) if route_mode else desk.render_customer_exports(object_id)
        out = Path(args.directory)
        prefix = "route" if route_mode else "customer"
        created = _write_export_bundle(out, prefix, object_id, exports)
        result = {"created": created, "authority": _cli_authority()}
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


def main() -> int:
    try:
        return _run()
    except (LaundryDeskError, OSError, sqlite3.Error, ValueError) as exc:
        print(json.dumps({"status": "REJECTED", "error_type": type(exc).__name__,
            "message": str(exc), "authority": _cli_authority()}, sort_keys=True),
            file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
