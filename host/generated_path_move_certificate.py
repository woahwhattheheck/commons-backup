#!/usr/bin/env python3
"""Attach visibility-plan B6 path classification to drift/custody context.

Consumes ``host.generated_path_moves.classify_paths`` and emits a fail-closed
certificate peers can bind to root-move / custody receipts without trusting
commit messages or authors. This is the B6 consumer slice; the path classifier
primitive remains ``host/generated_path_moves.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

# Repo root on sys.path so `python3 host/generated_path_move_certificate.py`
# works as well as `python3 -m host.generated_path_move_certificate`.
_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from host.generated_path_moves import SCHEMA as PATH_MOVES_SCHEMA
from host.generated_path_moves import classify_paths

SCHEMA = "commons-generated-path-move-certificate/v1"

# Verdicts are conservative: only generated_only is SAFE for auto-trust of
# rebuild noise. mixed always REVIEW. feature is FEATURE (no generated surface).
_VERDICT_BY_DISPOSITION = {
    "generated_only": "GENERATED_ONLY_SAFE",
    "mixed": "MIXED_REVIEW",
    "feature": "FEATURE",
}


class CertificateError(ValueError):
    """Invalid certificate inputs."""


def _optional_nonempty_str(value: object, name: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not value.strip() or value.strip() != value:
        raise CertificateError("%s must be an exact nonempty string when present" % name)
    return value


def build_certificate(
    paths: Iterable[str],
    *,
    custody: Mapping[str, Any] | None = None,
    drift_status: str | None = None,
    base_ref: str | None = None,
    head: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic B6 certificate wrapping classify_paths.

    Optional custody/drift fields are attached as opaque context; they never
    override the path disposition. Unknown/malformed optional fields refuse.
    """
    path_moves = classify_paths(paths)
    if path_moves.get("schema") != PATH_MOVES_SCHEMA:
        raise CertificateError("path_moves schema mismatch")

    disposition = path_moves.get("disposition")
    if disposition not in _VERDICT_BY_DISPOSITION:
        raise CertificateError("unknown path_moves disposition")
    verdict = _VERDICT_BY_DISPOSITION[disposition]

    drift = _optional_nonempty_str(drift_status, "drift_status")
    root = _optional_nonempty_str(base_ref, "base_ref")
    tip = _optional_nonempty_str(head, "head")

    custody_out: dict[str, Any] | None = None
    if custody is not None:
        if not isinstance(custody, Mapping) or isinstance(custody, (str, bytes)):
            raise CertificateError("custody must be a mapping when present")
        # Fail closed on nested secret-shaped keys by refusing non-JSON-safe values.
        try:
            custody_out = json.loads(json.dumps(dict(custody), sort_keys=True))
        except (TypeError, ValueError) as exc:
            raise CertificateError("custody must be JSON-serializable") from exc
        if not isinstance(custody_out, dict):
            raise CertificateError("custody must serialize to an object")

    cert: dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": verdict,
        "path_moves": path_moves,
        "path_moves_schema": PATH_MOVES_SCHEMA,
    }
    if drift is not None:
        cert["drift_status"] = drift
    if root is not None:
        cert["base_ref"] = root
    if tip is not None:
        cert["head"] = tip
    if custody_out is not None:
        cert["custody"] = custody_out
    return cert


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit a visibility-plan B6 generated-path-move certificate."
    )
    parser.add_argument("paths", nargs="+", help="repository-relative changed paths")
    parser.add_argument("--drift-status", default=None)
    parser.add_argument("--base-ref", default=None)
    parser.add_argument("--head", default=None)
    parser.add_argument(
        "--custody-json",
        default=None,
        help="optional JSON object of custody context",
    )
    args = parser.parse_args(argv)
    custody = None
    if args.custody_json is not None:
        try:
            custody = json.loads(args.custody_json)
        except json.JSONDecodeError as exc:
            parser.error("custody-json must be valid JSON: %s" % exc)
    try:
        cert = build_certificate(
            args.paths,
            custody=custody,
            drift_status=args.drift_status,
            base_ref=args.base_ref,
            head=args.head,
        )
    except (CertificateError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(cert, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
