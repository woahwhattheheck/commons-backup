#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compose the released receipt and cash-prefix donors for canonical V4.

Source-only, exact-input transformation. Does not activate the scheduler, run
legacy materializers, edit production, or claim competitive improvement.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

import repair_receipt_prefix as receipt_donor

SOURCE_BLOB = receipt_donor.SOURCE_BLOB
RECEIPT_DONOR_BLOB = "39b772c0336e454d506cd0eb9f2d0f3f85aad0c3"
CASH_DONOR_BLOB = "5e8f54ca20fa755bc6ced55decdcdf0193cda812"
CASH_OLD = receipt_donor.FUTURE_OLD.replace("for o in orders:", "for order in orders:")
CASH_NEW = receipt_donor.FUTURE_NEW.replace("for o in orders:", "for order in orders:")
git_blob = receipt_donor.git_blob


def method_range(source: str, name: str) -> tuple[int, int, str]:
    tree = ast.parse(source)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SellScheduler"]
    if len(classes) != 1:
        raise ValueError("expected exactly one SellScheduler")
    methods = [n for n in classes[0].body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(methods) != 1 or methods[0].end_lineno is None:
        raise ValueError(f"missing or ambiguous method: {name}")
    node = methods[0]
    lines = source.splitlines(keepends=True)
    start = sum(map(len, lines[:node.lineno - 1]))
    end = sum(map(len, lines[:node.end_lineno]))
    return start, end, source[start:end]


def repair(source: bytes) -> tuple[bytes, dict]:
    donor_bytes = Path(receipt_donor.__file__).read_bytes()
    if git_blob(donor_bytes) != RECEIPT_DONOR_BLOB:
        raise ValueError("receipt donor drift")
    receipt_fixed, report = receipt_donor.repair(source)
    text = receipt_fixed.decode("utf-8")
    start, end, method = method_range(text, "cash_reserve")
    if method.count(CASH_OLD) != 1:
        raise ValueError("cash queue anchor missing or ambiguous")
    fixed = text[:start] + method.replace(CASH_OLD, CASH_NEW, 1) + text[end:]
    tree = ast.parse(fixed)
    helpers = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_receipt_market_prefix"]
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "_receipt_market_prefix"]
    if len(helpers) != 1 or len(calls) != 3:
        raise ValueError("expected one shared prefix helper and exactly three consumers")
    compile(tree, "<scheduler-three-prefix-consumers>", "exec")
    output = fixed.encode("utf-8")
    report = dict(report, operation="ASTRA-PREFIX3-CANONICAL-COMPOSITION",
                  receipt_donor_git_blob=RECEIPT_DONOR_BLOB,
                  cash_semantics_donor_git_blob=CASH_DONOR_BLOB,
                  intermediate_receipt_git_blob=git_blob(receipt_fixed),
                  candidate_git_blob=git_blob(output),
                  candidate_sha256=hashlib.sha256(output).hexdigest(),
                  candidate_bytes=len(output), cash_reserve_consumers_repaired=1,
                  shared_prefix_helpers=1, total_prefix_consumers=3)
    return output, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, help="Create a new candidate file; never overwrite")
    args = parser.parse_args()
    if args.source.is_symlink() or not args.source.is_file():
        parser.error("source must be a regular non-symlink file")
    original = args.source.read_bytes()
    candidate, report = repair(original)
    if args.output is not None:
        if args.output.resolve() == args.source.resolve():
            parser.error("output must not alias source")
        with args.output.open("xb") as stream:
            stream.write(candidate)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
