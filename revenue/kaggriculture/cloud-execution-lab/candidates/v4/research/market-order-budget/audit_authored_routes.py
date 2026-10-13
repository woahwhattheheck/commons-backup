#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Audit the authenticated frozen native route bank for market-budget pressure."""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zlib

from market_order_budget import DEFAULT_CAP, scan_actions

ARCHIVE_SHA256 = "b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9"
SOURCE_SHA256 = "e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2"
VENDOR_PATH = "reference/next-panel/vendor/arlene.py"
VENDOR_SHA256 = "1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_routes(vendor_source: str) -> dict[str, list[dict]]:
    tree = ast.parse(vendor_source)
    blobs = [
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_BLOB" for target in node.targets)
    ]
    if len(blobs) != 1 or not isinstance(blobs[0], (str, bytes)):
        raise ValueError("expected exactly one literal authored route _BLOB")
    encoded = blobs[0].encode() if isinstance(blobs[0], str) else blobs[0]
    payload = json.loads(zlib.decompress(base64.b64decode(encoded, validate=True)))
    routes = {payload["main"]: payload["full"]}
    for tail in payload["tails"]:
        if tail["h"] in routes or tail["parent"] not in routes:
            raise ValueError("invalid route ancestry")
        routes[tail["h"]] = routes[tail["parent"]][:tail["at"]] + tail["suffix"]
    return routes


def authenticated_routes(archive: Path) -> tuple[dict[str, list[dict]], dict]:
    raw_archive = archive.read_bytes()
    if sha(raw_archive) != ARCHIVE_SHA256:
        raise ValueError("archive hash mismatch")
    with tarfile.open(fileobj=io.BytesIO(raw_archive), mode="r:gz") as tar:
        members = tar.getmembers()
        if len({m.name for m in members}) != len(members) or not all(m.isfile() for m in members):
            raise ValueError("duplicate or non-regular archive member")
        data = {m.name: tar.extractfile(m).read() for m in members}
    if sha(data["SOURCE.json"]) != SOURCE_SHA256:
        raise ValueError("SOURCE.json mismatch")
    manifest = json.loads(data["SOURCE.json"])
    expected = manifest["runtime"]
    if set(data) != set(expected) | {"SOURCE.json"}:
        raise ValueError("archive member set mismatch")
    for name, receipt in expected.items():
        if len(data[name]) != receipt["bytes"] or sha(data[name]) != receipt["sha256"]:
            raise ValueError("runtime member mismatch: " + name)
    if sha(data[VENDOR_PATH]) != VENDOR_SHA256:
        raise ValueError("vendor source mismatch")
    routes = decode_routes(data[VENDOR_PATH].decode("utf-8"))
    if len(routes) != 4 or any(len(tape) != 720 for tape in routes.values()):
        raise ValueError("unexpected route cardinality")
    return routes, {
        "archive_sha256": ARCHIVE_SHA256,
        "source_sha256": SOURCE_SHA256,
        "vendor_path": VENDOR_PATH,
        "vendor_sha256": VENDOR_SHA256,
        "verified_runtime_members": len(expected),
    }


def audit(archive: Path, cap: int = DEFAULT_CAP) -> dict:
    routes, pins = authenticated_routes(archive)
    results = []
    for route, tape in sorted(routes.items()):
        report = scan_actions(tape, cap)
        report["route"] = route
        results.append(report)
    return {
        "schema": "titan.v4.market-order-budget.authored-census.v1",
        "scope": "authenticated authored route intent only; not fill/economics/current-composed execution",
        "pins": pins,
        "cap": cap,
        "routes": results,
        "summary": {
            "routes": len(results),
            "callbacks": sum(row["callbacks"] for row in results),
            "max_raw_rows": max(row["max_raw_rows"] for row in results),
            "max_active_slot": max((row["max_active_slot"] for row in results if row["max_active_slot"] is not None), default=None),
            "structural_overflow_callbacks": sum(row["structural_overflow_callbacks"] for row in results),
            "dropped_nonempty_callbacks": sum(row["dropped_nonempty_callbacks"] for row in results),
            "dropped_nonempty_rows": sum(row["dropped_nonempty_rows"] for row in results),
            "no_admission_slot_callbacks": sum(row["no_admission_slot_callbacks"] for row in results),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cap", type=int, default=DEFAULT_CAP)
    args = parser.parse_args()
    report = audit(args.archive, args.cap)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
