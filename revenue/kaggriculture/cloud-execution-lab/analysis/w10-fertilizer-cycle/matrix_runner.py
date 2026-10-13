#!/usr/bin/env python3
"""Run a strict matrix of paired TITAN W10 fertilizer certificates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from realized_fertilizer import canonical_sha256, certify_realized_fertilizer

MATRIX_SCHEMA = "titan.w10.realized-fertilizer-matrix/v1"
MATRIX_RESULT_SCHEMA = "titan.w10.realized-fertilizer-matrix-result/v1"

_MANIFEST_KEYS = {"schema", "pairs"}
_PAIR_KEYS = {"id", "control", "fertilized"}
_PAIR_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
_MAX_PAIRS = 1000
_MAX_TRACE_BYTES = 8 * 1024 * 1024


class MatrixValidationError(ValueError):
    """Raised for a malformed matrix manifest."""


def _exact_keys(value: Mapping[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        detail: list[str] = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if extra:
            detail.append("extra=" + ",".join(extra))
        raise MatrixValidationError(f"{where} keys invalid ({'; '.join(detail)})")


def _relative_file(value: Any, *, where: str, root: Path) -> tuple[str, Path]:
    if not isinstance(value, str) or not value:
        raise MatrixValidationError(f"{where} must be a non-empty relative path")
    raw = Path(value)
    if raw.is_absolute() or ".." in raw.parts:
        raise MatrixValidationError(f"{where} must stay inside the manifest directory")
    normalized = Path(*[part for part in raw.parts if part not in ("", ".")])
    if not normalized.parts:
        raise MatrixValidationError(f"{where} must name a file")
    resolved_root = root.resolve()
    resolved = (resolved_root / normalized).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise MatrixValidationError(f"{where} escapes the manifest directory") from exc
    return normalized.as_posix(), resolved


def validate_manifest(raw: Any, *, root: Path) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise MatrixValidationError("manifest must be an object")
    _exact_keys(raw, _MANIFEST_KEYS, "manifest")
    if raw["schema"] != MATRIX_SCHEMA:
        raise MatrixValidationError(f"manifest.schema must equal {MATRIX_SCHEMA!r}")
    pairs = raw["pairs"]
    if isinstance(pairs, (str, bytes)) or not isinstance(pairs, Sequence):
        raise MatrixValidationError("manifest.pairs must be an array")
    if not pairs:
        raise MatrixValidationError("manifest.pairs must not be empty")
    if len(pairs) > _MAX_PAIRS:
        raise MatrixValidationError(f"manifest.pairs exceeds {_MAX_PAIRS}")

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    normalized_pairs: list[dict[str, str]] = []
    for index, raw_pair in enumerate(pairs):
        where = f"manifest.pairs[{index}]"
        if not isinstance(raw_pair, Mapping):
            raise MatrixValidationError(f"{where} must be an object")
        _exact_keys(raw_pair, _PAIR_KEYS, where)
        pair_id = raw_pair["id"]
        if not isinstance(pair_id, str) or _PAIR_ID_RE.fullmatch(pair_id) is None:
            raise MatrixValidationError(f"{where}.id has an invalid format")
        if pair_id in seen_ids:
            raise MatrixValidationError(f"duplicate pair id {pair_id!r}")
        seen_ids.add(pair_id)

        control_name, _ = _relative_file(
            raw_pair["control"], where=f"{where}.control", root=root
        )
        fertilized_name, _ = _relative_file(
            raw_pair["fertilized"], where=f"{where}.fertilized", root=root
        )
        if control_name == fertilized_name:
            raise MatrixValidationError(f"{where} reuses one file for both variants")
        for name in (control_name, fertilized_name):
            if name in seen_paths:
                raise MatrixValidationError(f"trace file reused across pairs: {name!r}")
            seen_paths.add(name)
        normalized_pairs.append(
            {"id": pair_id, "control": control_name, "fertilized": fertilized_name}
        )
    return {"schema": MATRIX_SCHEMA, "pairs": normalized_pairs}


def _read_json(path: Path) -> tuple[Any, str]:
    data = path.read_bytes()
    if len(data) > _MAX_TRACE_BYTES:
        raise ValueError(f"trace exceeds {_MAX_TRACE_BYTES} bytes")
    text = data.decode("utf-8")
    return json.loads(text), hashlib.sha256(data).hexdigest()


def _invalid_result(reason: str, raw_manifest: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema": MATRIX_RESULT_SCHEMA,
        "decision": "REJECT",
        "reasons": [f"invalid-manifest:{reason}"],
        "manifest_sha256": None,
        "pair_count": 0,
        "certified_count": 0,
        "rejected_count": 0,
        "pairs": [],
    }
    try:
        body["manifest_sha256"] = canonical_sha256(raw_manifest)
    except (TypeError, ValueError):
        pass
    body["result_sha256"] = canonical_sha256(body)
    return body


def run_matrix(raw_manifest: Any, *, root: Path) -> dict[str, Any]:
    """Evaluate every required pair; admit only when all pairs certify."""

    try:
        manifest = validate_manifest(raw_manifest, root=root)
    except (MatrixValidationError, TypeError, ValueError) as exc:
        return _invalid_result(str(exc), raw_manifest)

    pair_results: list[dict[str, Any]] = []
    matrix_reasons: list[str] = []
    seen_identity_hashes: set[str] = set()
    certified_count = 0

    for pair in manifest["pairs"]:
        control_path = (root / pair["control"]).resolve()
        candidate_path = (root / pair["fertilized"]).resolve()
        try:
            control, control_file_sha = _read_json(control_path)
            candidate, candidate_file_sha = _read_json(candidate_path)
            certificate = certify_realized_fertilizer(control, candidate)
            decision = certificate["decision"]
            reasons = list(certificate["reasons"])
            certificate_sha = certificate["certificate_sha256"]
            identity = certificate.get("identity")
            identity_sha = canonical_sha256(identity) if identity is not None else None
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            control_file_sha = None
            candidate_file_sha = None
            decision = "REJECTED"
            reasons = [f"trace-read-error:{type(exc).__name__}:{exc}"]
            certificate_sha = None
            identity_sha = None

        duplicate_identity = identity_sha is not None and identity_sha in seen_identity_hashes
        if duplicate_identity:
            decision = "REJECTED"
            reasons.append("duplicate-comparison-identity")
        elif identity_sha is not None:
            seen_identity_hashes.add(identity_sha)

        if decision == "CERTIFIED":
            certified_count += 1
        else:
            matrix_reasons.append(f"pair-rejected:{pair['id']}")

        pair_results.append(
            {
                "id": pair["id"],
                "decision": decision,
                "reasons": reasons,
                "control": {
                    "path": pair["control"],
                    "file_sha256": control_file_sha,
                },
                "fertilized": {
                    "path": pair["fertilized"],
                    "file_sha256": candidate_file_sha,
                },
                "identity_sha256": identity_sha,
                "certificate_sha256": certificate_sha,
            }
        )

    pair_count = len(pair_results)
    rejected_count = pair_count - certified_count
    body: dict[str, Any] = {
        "schema": MATRIX_RESULT_SCHEMA,
        "decision": "ADMIT" if rejected_count == 0 else "REJECT",
        "reasons": matrix_reasons,
        "manifest_sha256": canonical_sha256(manifest),
        "pair_count": pair_count,
        "certified_count": certified_count,
        "rejected_count": rejected_count,
        "pairs": pair_results,
    }
    body["result_sha256"] = canonical_sha256(body)
    return body


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run an all-required TITAN W10 fertilizer certificate matrix."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    result = run_matrix(manifest, root=args.manifest.parent)
    rendered = json.dumps(
        result,
        sort_keys=True,
        indent=2 if args.pretty else None,
        separators=None if args.pretty else (",", ":"),
    ) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if result["decision"] == "ADMIT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
