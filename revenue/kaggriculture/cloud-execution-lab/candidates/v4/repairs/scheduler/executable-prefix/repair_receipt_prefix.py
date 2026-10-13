#!/usr/bin/env python3
"""Source-only recovery of both current scheduler receipt market consumers.

This does not edit a package, feature flag, canonical branch, or archive.
Consume only after the V4 integrator has verified the final package's source and
reachability. #12018's different, already unit-stage-repaired source is rejected.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

SOURCE_BLOB = "da1b6fb571e79ba7dab54c8d816e45afb934e4d2"
SOURCE_COMMIT = "465f4263da1c98acf78889d67cdd21b61dbba145"
ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
HELPER_ANCHOR = "\n\nclass SellScheduler:\n"
HELPER = '''

def _receipt_market_prefix(action, config):
    # Official interpreter truncates raw slots before interpreting orders.
    market=action.get('market',[]) if isinstance(action,dict) else []
    queue=list(market) if isinstance(market,list) else []
    return queue[:max(1,int(config.get('maxMarketOrdersPerTurn',10)))]


class SellScheduler:
'''
CURRENT_OLD = "        for o in base['market']:\n"
CURRENT_NEW = "        for o in _receipt_market_prefix(base,config):\n"
FUTURE_OLD = (
    "            orders=base['market'] if t==now else "
    "(route[t].get('market',[]) if t<len(route) else [])\n"
    "            for o in orders:\n"
)
FUTURE_NEW = (
    "            market_action=base if t==now else (route[t] if t<len(route) else parent.PASS)\n"
    "            orders=_receipt_market_prefix(market_action,config)\n"
    "            for o in orders:\n"
)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def selected_method(source: str) -> tuple[int, int, str]:
    tree = ast.parse(source)
    roots = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SellScheduler"]
    if len(roots) != 1:
        raise ValueError("expected one SellScheduler")
    methods = [n for n in roots[0].body if isinstance(n, ast.FunctionDef) and n.name == "receipt_profile"]
    if len(methods) != 1:
        raise ValueError("expected one receipt_profile")
    node = methods[0]
    if node.end_lineno is None:
        raise ValueError("missing source range")
    lines = source.splitlines(keepends=True)
    start = sum(map(len, lines[:node.lineno - 1]))
    end = sum(map(len, lines[:node.end_lineno]))
    return start, end, source[start:end]


def _replace_once(source: str, before: str, after: str) -> str:
    count = source.count(before)
    if count != 1:
        raise ValueError(f"expected one replacement anchor, found {count}")
    return source.replace(before, after, 1)


def repair(source: bytes) -> tuple[bytes, dict]:
    if git_blob(source) != SOURCE_BLOB:
        raise ValueError("source drift: this donor accepts only canonical lab scheduler da1b6fb")
    text = source.decode("utf-8")
    start, end, method = selected_method(text)
    if "_receipt_market_prefix" in text:
        raise ValueError("helper already present")
    fixed_method = _replace_once(method, CURRENT_OLD, CURRENT_NEW)
    fixed_method = _replace_once(fixed_method, FUTURE_OLD, FUTURE_NEW)
    fixed = text[:start] + fixed_method + text[end:]
    fixed = _replace_once(fixed, HELPER_ANCHOR, HELPER)
    compile(fixed, "<receipt-prefix-recovered-scheduler>", "exec")
    output = fixed.encode("utf-8")
    receipt = {
        "operation": "RIVET-V4-LEGACY-RECEIPT-TWO-CONSUMER-RECOVERY",
        "source_commit": SOURCE_COMMIT,
        "source_git_blob": SOURCE_BLOB,
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "candidate_git_blob": git_blob(output),
        "candidate_sha256": hashlib.sha256(output).hexdigest(),
        "candidate_bytes": len(output),
        "engine_reference_git_blob": ENGINE_BLOB,
        "current_predebit_consumers_repaired": 1,
        "turn_loop_consumers_repaired": 1,
        "claim": "SOURCE_ONLY_NOT_MATERIALIZED_V4_NOT_STRENGTH_EVIDENCE",
    }
    return output, receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, help="Create a new file; never overwrite or edit the input")
    args = parser.parse_args()
    if args.source.is_symlink() or not args.source.is_file():
        parser.error("source must be a regular non-symlink file")
    candidate, receipt = repair(args.source.read_bytes())
    if args.output is not None:
        if args.output.resolve() == args.source.resolve():
            parser.error("output must not alias source")
        # Exclusive creation also rejects existing files, hardlinks, and symlinks.
        with args.output.open("xb") as stream:
            stream.write(candidate)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
