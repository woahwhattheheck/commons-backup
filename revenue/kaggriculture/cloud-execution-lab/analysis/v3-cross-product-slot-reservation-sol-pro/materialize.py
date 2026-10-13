#!/usr/bin/env python3
"""Exact-source materializer for the shared planned-SELL slot reservation repair."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile

EXPECTED_SOURCE_BLOB = "a483b24dd72b580d7d8811636b54d2d44f391575"
OPERATION = "TITAN-V3-CROSS-PRODUCT-SELL-SLOT-RESERVATION-CLOSURE-20260910-01"

CLASS_ANCHOR = "\n\nclass SellScheduler:\n"
HELPER = r'''

def _planned_slot_reservations(planned, current, item, now, step, orders):
    """Executable rows promised to other products that need an appended order."""
    if not isinstance(planned,dict) or not isinstance(current,dict):return None
    reserved=0
    for other,rows in planned.items():
        if not isinstance(other,str) or not other or not isinstance(rows,(list,tuple)):return None
        if other==item:continue
        active=False
        for row in rows:
            if not isinstance(row,(list,tuple)) or len(row)!=2:return None
            due,quantity=row
            if isinstance(due,bool) or isinstance(quantity,bool):return None
            if not isinstance(due,int) or not isinstance(quantity,int) or due<0 or quantity<0:return None
            if quantity<=0:continue
            if step==now and due<=now and other in current:
                try:
                    desired=max(0,int(current[other]))
                    offered=sum(max(0,int(o[2])) for o in orders if o and o[0]=='SELL' and o[1]==other)
                except (TypeError,ValueError,IndexError):return None
                if desired>offered:active=True
            elif step!=now and due<=step:active=True
        if active:reserved+=1
    return reserved
'''


OLD_BLOCK = """                    if len(orders)>=int(config.get('maxMarketOrdersPerTurn',10)):\n                        offered=sum(max(0,int(o[2])) for o in orders if o and o[0]=='SELL' and o[1]==item)\n                        if q>offered:return False"""

NEW_BLOCK = """                    offered=sum(max(0,int(o[2])) for o in orders if o and o[0]=='SELL' and o[1]==item)\n                    reserved=_planned_slot_reservations(self.planned,current,item,now,t,orders)\n                    if reserved is None:return False\n                    if q>offered and len(orders)+reserved>=int(config.get('maxMarketOrdersPerTurn',10)):return False"""


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_source(source: str, *, expected_blob: str | None = EXPECTED_SOURCE_BLOB) -> str:
    raw = source.encode("utf-8")
    if expected_blob is not None and git_blob_sha(raw) != expected_blob:
        raise ValueError("source Git blob does not match the exact reviewed scheduler")
    if "def _planned_slot_reservations(" in source:
        raise ValueError("reservation helper already present")
    if source.count(CLASS_ANCHOR) != 1:
        raise ValueError("SellScheduler class anchor is missing or ambiguous")
    if source.count(OLD_BLOCK) != 1:
        raise ValueError("product-local feasibility preimage is missing or ambiguous")
    patched = source.replace(CLASS_ANCHOR, HELPER + CLASS_ANCHOR, 1)
    patched = patched.replace(OLD_BLOCK, NEW_BLOCK, 1)
    if patched == source:
        raise ValueError("empty patch")
    ast.parse(patched)
    if patched.count("def _planned_slot_reservations(") != 1:
        raise ValueError("patched helper cardinality is not one")
    if patched.count(NEW_BLOCK) != 1 or OLD_BLOCK in patched:
        raise ValueError("patched feasibility cardinality is invalid")
    return patched


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    except Exception:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--expected-blob", default=EXPECTED_SOURCE_BLOB)
    args = parser.parse_args()

    if args.output.resolve() == args.source.resolve() or args.receipt.resolve() in {args.source.resolve(), args.output.resolve()}:
        raise SystemExit("source, output, and receipt paths must be distinct")
    source_bytes = args.source.read_bytes()
    try:
        source = source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"source is not UTF-8: {exc}") from exc
    patched = patch_source(source, expected_blob=args.expected_blob)
    patched_bytes = patched.encode("utf-8")
    receipt = {
        "schema": "titan-v3-cross-product-slot-reservation-materialization-v1",
        "operation": OPERATION,
        "source_git_blob": git_blob_sha(source_bytes),
        "source_sha256": sha256(source_bytes),
        "patched_git_blob": git_blob_sha(patched_bytes),
        "patched_sha256": sha256(patched_bytes),
        "source_bytes": len(source_bytes),
        "patched_bytes": len(patched_bytes),
        "changes": [
            "add fail-closed executable other-product planned-row reservation counter",
            "charge reservations before admitting a candidate extra SELL row",
            "exclude same-product replacement and preserve inherited-row reuse",
        ],
    }
    _atomic_write(args.output, patched_bytes)
    _atomic_write(args.receipt, (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
