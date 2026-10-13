#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed exact-source gate for the V217 observation-only probe.

This verifier is intentionally separate from the repository unit suite because
canonical production-v3 is an authenticated external archive, not a checked-in
tarball. Both inputs are mandatory; absence or SHA-256 drift is a hard failure.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import v217_engagement_probe as probe


def verify(production_raw: bytes, evaluator_raw: bytes) -> dict:
    files = probe.archive_members(production_raw)
    if len(files) != probe.PRODUCTION_MEMBERS:
        raise ValueError("production archive member count mismatch")
    if probe.ROUTER not in files:
        raise ValueError("production router member missing")
    router = files[probe.ROUTER]
    if probe.digest(router) != probe.ROUTER_SHA:
        raise ValueError("production router member mismatch")
    if probe.digest(probe.archive_bytes(files)) != probe.PRODUCTION_SHA:
        raise ValueError("production archive does not reproduce canonically")
    if probe.digest(evaluator_raw) != probe.EVALUATOR_SHA:
        raise ValueError("evaluator source identity mismatch")

    instrumented_router = probe.instrument_router(router)
    instrumented_evaluator = probe.instrument_evaluator(evaluator_raw)
    compile(instrumented_router, probe.ROUTER, "exec")
    compile(instrumented_evaluator, "evaluate.py", "exec")

    return {
        "schema": "titan-v5-v217-exact-source-verification/v1",
        "production_archive_sha256": probe.PRODUCTION_SHA,
        "production_member_count": len(files),
        "router_member": probe.ROUTER,
        "router_sha256": probe.ROUTER_SHA,
        "evaluator_sha256": probe.EVALUATOR_SHA,
        "router_instrumented_sha256": probe.digest(instrumented_router),
        "evaluator_instrumented_sha256": probe.digest(instrumented_evaluator),
        "compile_ok": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production", type=Path, required=True,
                        help="authenticated canonical production-v3 tar.gz")
    parser.add_argument("--evaluator", type=Path, required=True,
                        help="exact offline evaluator source")
    args = parser.parse_args()
    result = verify(args.production.read_bytes(), args.evaluator.read_bytes())
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
