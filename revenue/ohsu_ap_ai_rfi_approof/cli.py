"""Command-line entry point for APProof."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

try:
    from .approof import APProofError, canonical_json_bytes, compile_packet, verify_projection
    from .common import load_json_strict
except ImportError:  # direct script execution from package directory
    from approof import APProofError, canonical_json_bytes, compile_packet, verify_projection
    from common import load_json_strict


def _read(path: str):
    try:
        raw = Path(path).read_bytes()
        text = raw.decode("utf-8")
        return load_json_strict(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise APProofError(f"cannot read JSON {path}: {exc}") from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile or verify deterministic APProof shadow-mode evidence."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compile")
    c.add_argument("packet")
    v = sub.add_parser("verify")
    v.add_argument("packet")
    v.add_argument("projection")
    args = parser.parse_args(argv)
    try:
        packet = _read(args.packet)
        if args.command == "compile":
            projection = compile_packet(packet)
            sys.stdout.buffer.write(canonical_json_bytes(projection) + b"\n")
            return 0
        projection = _read(args.projection)
        if verify_projection(packet, projection):
            sys.stdout.write("OK\n")
            return 0
        sys.stderr.write("projection mismatch\n")
        return 2
    except APProofError as exc:
        sys.stderr.write(f"APProofError: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
