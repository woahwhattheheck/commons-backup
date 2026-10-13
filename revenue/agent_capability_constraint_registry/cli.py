#!/usr/bin/env python3
"""Compile or verify the execution-free agent capability registry."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .core import RegistryError, load_json_bytes, verify_compiled, write_compiled
except ImportError:  # direct execution
    from core import RegistryError, load_json_bytes, verify_compiled, write_compiled


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic agent capability & constraint registry")
    sub = ap.add_subparsers(dest="command", required=True)

    build = sub.add_parser("compile", help="compile a strict source census")
    build.add_argument("--input", required=True)
    build.add_argument("--out-dir", required=True)

    verify = sub.add_parser("verify", help="recompile and byte-verify an output bundle")
    verify.add_argument("--input", required=True)
    verify.add_argument("--out-dir", required=True)

    ns = ap.parse_args()
    try:
        source = load_json_bytes(Path(ns.input).read_bytes())
        if ns.command == "compile":
            compiled = write_compiled(source, ns.out_dir)
            print(json.dumps({
                "counts": compiled.result["counts"],
                "input_sha256": compiled.result["input_sha256"],
                "receipt_sha256": compiled.receipt["receipt_sha256"],
                "authority": "OBSERVATIONAL_ONLY",
            }, sort_keys=True))
            return 0

        out = Path(ns.out_dir)
        proof = verify_compiled(
            source,
            (out / "registry.json").read_bytes(),
            (out / "registry.md").read_bytes(),
            (out / "receipt.json").read_bytes(),
        )
        print(json.dumps(proof, sort_keys=True))
        return 0
    except (RegistryError, OSError) as exc:
        print(f"HOLD: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
