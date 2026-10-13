#!/usr/bin/env python3
"""CLI and public API for the deterministic, fail-closed paid-proof compiler."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

from .core import ProofError, strict_json_loads
from .compiler import (
    compile_proof,
    compile_text,
    public_json,
    public_payload,
    write_outputs,
)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="strict JSON commercial-evidence record")
    parser.add_argument(
        "--internal-dir",
        type=Path,
        help="fresh directory for private proof.json + internal receipt",
    )
    parser.add_argument(
        "--public-dir",
        type=Path,
        help="fresh disjoint directory for proof.md + public.json + public receipt",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print INTERNAL audit proof JSON; never treat this as a public artifact",
    )
    parser.add_argument(
        "--public-json",
        action="store_true",
        help="print the release-authorized public JSON envelope",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if (args.internal_dir is None) != (args.public_dir is None):
        parser.error("--internal-dir and --public-dir must be provided together")
    if args.json and args.public_json:
        parser.error("--json and --public-json are mutually exclusive")

    try:
        compiled = compile_text(args.input.read_text(encoding="utf-8"))
        if args.internal_dir is not None and args.public_dir is not None:
            write_outputs(compiled, args.internal_dir, args.public_dir)
    except (OSError, ProofError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        sys.stdout.write(compiled.proof_json())
    elif args.public_json:
        sys.stdout.write(public_json(compiled))
    elif args.internal_dir is None:
        sys.stdout.write(compiled.markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
