#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed provenance gate for TITAN weed-continuation evidence.

The gate binds ``main.py``, ``spatial_tempo.py``, ``titan_runtime.py``, and
``TITAN-CONFIG.json``; proves the independent weed-capability path; emits a
deterministic receipt; and re-analyzes the exact checkout before accepting a
downstream W0, W1, or legacy-pre-gate evidence claim.

It does not execute a policy or infer gameplay quality.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from weed_gate import build_claim, gate_claim
from weed_model import AnalysisError, Decision, Semantics
from weed_receipt import (
    _validate_receipt_integrity,
    certify_bytes,
    certify_paths,
    receipt_id,
    verify_receipt_against_bytes,
    verify_receipt_against_paths,
)
from weed_semantic_analysis import DuplicateKeyError, _reject_json_constant, _unique_object

def _read_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        DuplicateKeyError,
        ValueError,
    ) as exc:
        raise AnalysisError(f"cannot read {path}: {exc}") from exc


def _write_json(path: Path | None, value: Any) -> None:
    text = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if path is None:
        sys.stdout.write(text)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    certify = sub.add_parser("certify", help="classify and bind an exact executable source/config closure")
    certify.add_argument("--spatial", required=True, type=Path)
    certify.add_argument("--runtime", required=True, type=Path)
    certify.add_argument("--entrypoint", required=True, type=Path)
    certify.add_argument("--config", required=True, type=Path)
    certify.add_argument("--revision")
    certify.add_argument("--output", type=Path)
    certify.add_argument(
        "--timestamp",
        action="store_true",
        help="include wall-clock metadata (excluded from the deterministic receipt ID)",
    )
    certify.add_argument(
        "--require",
        choices=[item.value for item in Semantics],
        help="exit 2 unless the classification equals this value",
    )

    claim = sub.add_parser("make-claim", help="create a hash-bound evidence claim template")
    claim.add_argument("--receipt", required=True, type=Path)
    claim.add_argument("--claim-id", required=True)
    claim.add_argument(
        "--declared",
        required=True,
        choices=["W0", "W1", "LEGACY_PRE_GATE_W1"],
    )
    claim.add_argument("--label", action="append", default=[])
    claim.add_argument("--output", type=Path)

    gate = sub.add_parser("gate", help="accept or quarantine a bound evidence claim")
    gate.add_argument("--receipt", required=True, type=Path)
    gate.add_argument("--claim", required=True, type=Path)
    gate.add_argument("--spatial", required=True, type=Path)
    gate.add_argument("--runtime", required=True, type=Path)
    gate.add_argument("--entrypoint", required=True, type=Path)
    gate.add_argument("--config", required=True, type=Path)
    gate.add_argument("--revision", required=True)
    gate.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "certify":
            receipt = certify_paths(
                args.spatial,
                args.runtime,
                args.config,
                entrypoint_path=args.entrypoint,
                source_revision=args.revision,
                generated_utc=_utc_now() if args.timestamp else None,
            )
            _write_json(args.output, receipt)
            if args.require and receipt["classification"] != args.require:
                return 2
            return 0
        if args.command == "make-claim":
            receipt = _read_json(args.receipt)
            errors = _validate_receipt_integrity(receipt)
            if errors:
                raise AnalysisError("invalid receipt: " + ", ".join(errors))
            claim = build_claim(receipt, args.claim_id, args.declared, args.label)
            _write_json(args.output, claim)
            return 0
        if args.command == "gate":
            receipt = _read_json(args.receipt)
            claim = _read_json(args.claim)
            if not isinstance(receipt, Mapping) or not isinstance(claim, Mapping):
                raise AnalysisError("receipt and claim must be JSON objects")
            verification_errors = verify_receipt_against_paths(
                receipt,
                args.spatial,
                args.runtime,
                args.config,
                entrypoint_path=args.entrypoint,
                source_revision=args.revision,
            )
            result = gate_claim(receipt, claim)
            if verification_errors:
                result["decision"] = Decision.INVALID.value
                result["reason_codes"] = sorted(
                    set(result.get("reason_codes", [])) | set(verification_errors)
                )
            _write_json(args.output, result)
            return (
                0
                if result["decision"] == Decision.ACCEPT.value
                else 2
                if result["decision"] == Decision.QUARANTINE.value
                else 3
            )
    except (AnalysisError, OSError, UnicodeDecodeError) as exc:
        sys.stderr.write(f"weed-evidence-certifier: {exc}\n")
        return 3
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
