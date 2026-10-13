#!/usr/bin/env python3
"""Validate the retained TITAN V5 D2 recovery-status contract.

This module validates only source-custody/readiness truth. It never authorizes
candidate construction, promotion, gameplay, provider mutation, submission,
prize, payment, or revenue state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

STATUS_SCHEMA = "titan-v5-d2-recovery-status-v1"
VALIDATION_SCHEMA = "titan-v5-d2-recovery-status-validation-v1"
STATE_SOURCE_ABSENT = "D2_SOURCE_BYTES_ABSENT"
STATE_SOURCE_AUTHENTICATED = "D2_SOURCE_AUTHENTICATED"

ARCHIVE_NAME = "titan-v5-runtime-one-timer-variant-d2-prewarmed.tar.gz"
ARCHIVE_SHA256 = "3d250d7bd32bf51f26ec1f69c2c10bc3c914e7d0cf64a078ae5bac5832465bd8"
ARCHIVE_BYTES = 424145
ARCHIVE_MEMBER_COUNT = 94
MAIN_SHA256 = "ae7032281ba680cc70fdfc333bb55cbd4aab7127c277c5150f18746c12f549d3"
RUNTIME_MEMBER = "titan_runtime.py"
RUNTIME_GIT_BLOB = "e0cdcf5a5dbe350d442d3b492795d37507449853"
OPERATING_STOCK_GIT_BLOB = "80b372bfd34d04a2c9e2376fa02917f21f659c41"
OFFICIAL_ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
HARNESS_SHA256 = "853850d8673cff0b21fdfe783e2dfcd539b8b2707bfe2d36c2e60d8ec2e43ea4"


class RecoveryStatusError(ValueError):
    """The recovery-status document contradicts the retained D2 contract."""


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise RecoveryStatusError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(token: str) -> None:
    raise RecoveryStatusError(f"non-finite JSON constant: {token}")


def loads_status(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_object_no_duplicates,
            parse_constant=_reject_constant,
        )
    except RecoveryStatusError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise RecoveryStatusError("invalid recovery-status JSON") from exc
    if not isinstance(value, dict):
        raise RecoveryStatusError("recovery status must be a JSON object")
    return value


def load_status(path: Path) -> dict[str, Any]:
    return loads_status(Path(path).read_text(encoding="utf-8"))


def _exact_bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise RecoveryStatusError(f"{label} must be a JSON boolean")
    return value


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RecoveryStatusError(f"{label} must be a JSON object")
    return value


def _require_hex(value: Any, length: int, label: str) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise RecoveryStatusError(f"{label} must be {length} lowercase hex characters")
    if value.lower() != value:
        raise RecoveryStatusError(f"{label} must be lowercase hex")
    try:
        int(value, 16)
    except ValueError as exc:
        raise RecoveryStatusError(f"{label} must be hexadecimal") from exc
    return value


def _require_equal(mapping: dict[str, Any], key: str, expected: Any, label: str) -> None:
    if mapping.get(key) != expected:
        raise RecoveryStatusError(
            f"{label}.{key} drift: expected {expected!r}, got {mapping.get(key)!r}"
        )


def validate_status(status: dict[str, Any]) -> dict[str, Any]:
    """Validate and summarize one retained D2 recovery-status object."""
    if not isinstance(status, dict):
        raise RecoveryStatusError("recovery status must be a JSON object")
    if status.get("schema") != STATUS_SCHEMA:
        raise RecoveryStatusError("unexpected recovery-status schema")

    source_verified = _exact_bool(
        status.get("source_authority_verified"), "source_authority_verified"
    )
    inputs_ready = _exact_bool(
        status.get("execution_inputs_ready"), "execution_inputs_ready"
    )
    candidate_build = _exact_bool(
        status.get("candidate_build_authorized"), "candidate_build_authorized"
    )
    promotion = _exact_bool(
        status.get("promotion_authorized"), "promotion_authorized"
    )
    if candidate_build:
        raise RecoveryStatusError("candidate_build_authorized must remain false")
    if promotion:
        raise RecoveryStatusError("promotion_authorized must remain false")
    if inputs_ready and not source_verified:
        raise RecoveryStatusError("execution inputs cannot be ready before source authority")

    archive = _require_mapping(status.get("archive"), "archive")
    for key, expected in (
        ("name", ARCHIVE_NAME),
        ("sha256", ARCHIVE_SHA256),
        ("bytes", ARCHIVE_BYTES),
        ("member_count", ARCHIVE_MEMBER_COUNT),
        ("main_sha256", MAIN_SHA256),
    ):
        _require_equal(archive, key, expected, "archive")

    bindings = _require_mapping(status.get("retained_source_bindings"), "retained_source_bindings")
    for key, expected in (
        ("runtime_member", RUNTIME_MEMBER),
        ("runtime_git_blob", RUNTIME_GIT_BLOB),
        ("operating_stock_git_blob", OPERATING_STOCK_GIT_BLOB),
        ("official_engine_sha256", OFFICIAL_ENGINE_SHA256),
        ("harness_sha256", HARNESS_SHA256),
    ):
        _require_equal(bindings, key, expected, "retained_source_bindings")

    auth = _require_mapping(
        status.get("operator_host_archive_authentication"),
        "operator_host_archive_authentication",
    )
    nested_source = _exact_bool(
        auth.get("source_authority_verified"),
        "operator_host_archive_authentication.source_authority_verified",
    )
    nested_ready = _exact_bool(
        auth.get("execution_inputs_ready"),
        "operator_host_archive_authentication.execution_inputs_ready",
    )
    if source_verified != nested_source:
        raise RecoveryStatusError(
            "root/nested source_authority_verified mismatch"
        )
    if inputs_ready != nested_ready:
        raise RecoveryStatusError("root/nested execution_inputs_ready mismatch")
    if nested_ready and not nested_source:
        raise RecoveryStatusError("nested execution inputs cannot be ready before source authority")
    _require_hex(auth.get("receipt_sha256"), 64, "operator_host_archive_authentication.receipt_sha256")
    _require_hex(
        auth.get("safe_member_manifest_sha256"),
        64,
        "operator_host_archive_authentication.safe_member_manifest_sha256",
    )

    checked = _require_mapping(status.get("checked_surfaces"), "checked_surfaces")
    operator_surface = checked.get("operator_host_local_outputs")
    state = status.get("state")
    next_step = status.get("next_step")
    if not isinstance(next_step, str) or not next_step.strip():
        raise RecoveryStatusError("next_step must be a non-empty string")

    if source_verified:
        if state != STATE_SOURCE_AUTHENTICATED:
            raise RecoveryStatusError(
                "authenticated source must use D2_SOURCE_AUTHENTICATED root state"
            )
        if operator_surface != "FOUND_AND_AUTHENTICATED":
            raise RecoveryStatusError(
                "authenticated source must bind operator_host_local_outputs=FOUND_AND_AUTHENTICATED"
            )
        if "provide exact d2 archive bytes" in next_step.casefold():
            raise RecoveryStatusError(
                "authenticated source cannot retain the pre-recovery provide-bytes next step"
            )
    else:
        if state != STATE_SOURCE_ABSENT:
            raise RecoveryStatusError(
                "unauthenticated source must use D2_SOURCE_BYTES_ABSENT root state"
            )
        if inputs_ready:
            raise RecoveryStatusError("absent source cannot have execution inputs ready")
        if operator_surface == "FOUND_AND_AUTHENTICATED":
            raise RecoveryStatusError(
                "absent source contradicts FOUND_AND_AUTHENTICATED operator-host custody"
            )

    if status.get("empirical_result") is not None and not source_verified:
        raise RecoveryStatusError("empirical_result cannot exist before source authentication")

    return {
        "schema": VALIDATION_SCHEMA,
        "valid": True,
        "state": state,
        "source_authority_verified": source_verified,
        "execution_inputs_ready": inputs_ready,
        "candidate_build_authorized": False,
        "promotion_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("status", type=Path)
    args = parser.parse_args(argv)
    try:
        result = validate_status(load_status(args.status))
    except (OSError, RecoveryStatusError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
