#!/usr/bin/env python3
"""Compile and verify VeriCodeGen Lean Refactor evidence packages."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .core import compile_run, load_json_bytes, result_bytes, verify_result, write_exclusive
except ImportError:  # direct execution from this directory
    from core import compile_run, load_json_bytes, result_bytes, verify_result, write_exclusive


def main() -> int:
    ap = argparse.ArgumentParser(description="Offline VeriCodeGen Lean refactor evidence harness")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--input", help="refactor-run JSON to compile/evaluate")
    mode.add_argument("--verify", help="result package JSON to verify")
    ap.add_argument("--output", help="create-exclusive result JSON path for --input")
    ap.add_argument("--expected-digest", help="out-of-band SHA-256 package commitment")
    ap.add_argument("--rerun-compilers", action="store_true", help="rerun configured compiler pass vectors during verify")
    ns = ap.parse_args()

    if ns.input:
        if not ns.output:
            ap.error("--input requires --output")
        run = load_json_bytes(Path(ns.input).read_bytes(), "run")
        package = compile_run(run)
        write_exclusive(ns.output, result_bytes(package))
        print(json.dumps({
            "package_digest": package["package_digest"],
            "selected_id": package["selected_id"],
            "pareto_ids": package["pareto_ids"],
            "used_microusd": package["budget"]["used_microusd"],
            "notice": package["metric_notice"],
        }, sort_keys=True))
        return 0

    package = load_json_bytes(Path(ns.verify).read_bytes(), "result")
    proof = verify_result(package, expected_package_digest=ns.expected_digest, rerun_compilers=ns.rerun_compilers)
    print(json.dumps(proof, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
