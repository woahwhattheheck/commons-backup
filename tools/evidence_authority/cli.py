"""CLI: compile/verify source-bound authority receipts. Domain errors -> rc=2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .codec import GateError, loads_strict_json, require_sha256
from .engine import compile_current, verify_current, verify_receipt


def _read_bytes(path: str) -> bytes:
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise GateError(f"input is not a regular file: {path}")
    data = target.read_bytes()
    if Path(path).read_bytes() != data:
        raise GateError(f"input reminted during read: {path}")
    return data


def _read_json(path: str):
    return loads_strict_json(_read_bytes(path))


def _parse_sources(items: list[str]) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for item in items:
        if "=" not in item:
            raise GateError("source mapping must be path=file")
        rel, file_path = item.split("=", 1)
        if rel in out:
            raise GateError("duplicate source path on CLI")
        out[rel] = _read_bytes(file_path)
    return dict(sorted(out.items()))


def _dump(value) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile/verify source-bound authority receipts")
    sub = parser.add_subparsers(dest="command", required=True)

    c = sub.add_parser("compile", help="compile a process-current authority receipt")
    c.add_argument("candidate")
    c.add_argument("manifest")
    c.add_argument("pinned_root")
    c.add_argument("--source", action="append", default=[], dest="sources")

    v = sub.add_parser("verify", help="verify historical receipt integrity (never current-positive)")
    v.add_argument("candidate")
    v.add_argument("manifest")
    v.add_argument("pinned_root")
    v.add_argument("receipt")
    v.add_argument("--source", action="append", default=[], dest="sources")

    n = sub.add_parser("verify-current", help="recompile at process UTC; never uses caller time")
    n.add_argument("candidate")
    n.add_argument("manifest")
    n.add_argument("pinned_root")
    n.add_argument("--source", action="append", default=[], dest="sources")

    args = parser.parse_args(argv)
    try:
        require_sha256(args.pinned_root, "pinned_root")
        candidate = _read_json(args.candidate)
        manifest = _read_bytes(args.manifest)
        sources = _parse_sources(args.sources)
        if args.command == "compile":
            _dump(compile_current(candidate, manifest, sources, args.pinned_root))
            return 0
        if args.command == "verify-current":
            _dump(verify_current(candidate, manifest, sources, args.pinned_root))
            return 0
        receipt = _read_json(args.receipt)
        _dump(verify_receipt(candidate, manifest, sources, args.pinned_root, receipt))
        return 0
    except (GateError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
