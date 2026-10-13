#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed replay audit for TITAN unit-route rigidity and worker binding.

Kaggle replay rows bind the action stored at row ``k`` to the transition from the
observation at row ``k-1`` to the observation at row ``k``. This tool proves
that orientation from hand-count/HIRE transitions before reporting any command
binding or observed action effect. It does not execute the environment, infer
counterfactual score, or claim that a deterministic route is intrinsically bad.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Sequence

from audit_common import AuditError, canonical_json, sha256_bytes
from audit_report import build_report

__all__ = [
    "AuditError", "build_report", "canonical_json", "sha256_bytes",
    "write_json_atomic", "main",
]


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
    ).encode("utf-8") + b"\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--replay-dir", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = build_report(args.manifest, args.replay_dir)
        write_json_atomic(args.output, report)
    except AuditError as exc:
        print(f"AUDIT_ERROR: {exc}", file=os.sys.stderr)
        return 2
    print(
        f"AUDIT_PASS replay_count={report['replay_count']} "
        f"report_payload_sha256={report['report_payload_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
