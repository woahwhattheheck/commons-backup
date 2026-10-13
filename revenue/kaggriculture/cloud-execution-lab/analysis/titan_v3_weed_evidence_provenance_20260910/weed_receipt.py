# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from weed_model import (
    Artifact,
    RECEIPT_SCHEMA,
    Semantics,
    _GIT_SHA1_RE,
    _SHA256_RE,
    canonical_json,
    stable_digest,
)
from weed_entrypoint_analysis import analyze_entrypoint
from weed_semantic_analysis import analyze_config, classify
from weed_source_analysis import analyze_runtime, analyze_spatial

def _receipt_core(receipt: Mapping[str, Any]) -> dict[str, Any]:
    core = copy.deepcopy(dict(receipt))
    core.pop("receipt_id", None)
    core.pop("generated_utc", None)
    return core


def receipt_id(receipt: Mapping[str, Any]) -> str:
    return stable_digest(_receipt_core(receipt))


def certify_bytes(
    spatial_source: bytes,
    runtime_source: bytes,
    config_source: bytes,
    *,
    entrypoint_source: bytes,
    spatial_path: str = "spatial_tempo.py",
    runtime_path: str = "titan_runtime.py",
    entrypoint_path: str = "main.py",
    config_path: str = "TITAN-CONFIG.json",
    source_revision: str | None = None,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    artifacts = [
        Artifact("spatial_source", spatial_path, spatial_source),
        Artifact("runtime_source", runtime_path, runtime_source),
        Artifact("entrypoint_source", entrypoint_path, entrypoint_source),
        Artifact("runtime_config", config_path, config_source),
    ]
    spatial = analyze_spatial(spatial_source)
    runtime = analyze_runtime(runtime_source)
    entrypoint = analyze_entrypoint(entrypoint_source)
    config = analyze_config(config_source)
    semantics, reasons = classify(spatial, runtime, entrypoint, config)
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "source_revision": source_revision,
        "classification": semantics.value,
        "claimable_semantics": (
            ["W0"]
            if semantics == Semantics.EXPLICIT_W0
            else ["W1"]
            if semantics == Semantics.EXPLICIT_W1
            else ["LEGACY_PRE_GATE_W1"]
            if semantics == Semantics.LEGACY_PRE_GATE_W1
            else []
        ),
        "promotion_eligible_as_w0": semantics == Semantics.EXPLICIT_W0,
        "reason_codes": reasons,
        "artifacts": {artifact.role: artifact.receipt() for artifact in artifacts},
        "analysis": {
            "spatial": spatial,
            "runtime": runtime,
            "entrypoint": entrypoint,
            "config": config,
        },
    }
    if generated_utc is not None:
        receipt["generated_utc"] = generated_utc
    receipt["receipt_id"] = receipt_id(receipt)
    return receipt


def _logical_paths(paths: Sequence[Path]) -> list[str]:
    """Return stable audit labels without embedding worker-specific checkout roots."""

    resolved = [path.resolve() for path in paths]
    try:
        common = Path(os.path.commonpath([str(path.parent) for path in resolved]))
        return [path.relative_to(common).as_posix() for path in resolved]
    except (ValueError, OSError):
        return [path.name for path in resolved]


def certify_paths(
    spatial_path: Path,
    runtime_path: Path,
    config_path: Path,
    *,
    entrypoint_path: Path,
    source_revision: str | None = None,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    paths = [spatial_path, runtime_path, entrypoint_path, config_path]
    logical = _logical_paths(paths)
    return certify_bytes(
        spatial_path.read_bytes(),
        runtime_path.read_bytes(),
        config_path.read_bytes(),
        entrypoint_source=entrypoint_path.read_bytes(),
        spatial_path=logical[0],
        runtime_path=logical[1],
        entrypoint_path=logical[2],
        config_path=logical[3],
        source_revision=source_revision,
        generated_utc=generated_utc,
    )


def _artifact_hash_map(receipt: Mapping[str, Any]) -> dict[str, str]:
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, Mapping):
        return {}
    result: dict[str, str] = {}
    for role, row in artifacts.items():
        digest = row.get("sha256") if isinstance(row, Mapping) else None
        if isinstance(role, str) and isinstance(digest, str) and _SHA256_RE.fullmatch(digest):
            result[role] = digest
    return result


def _validate_receipt_integrity(receipt: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        errors.append("RECEIPT_SCHEMA_MISMATCH")
    source_revision = receipt.get("source_revision")
    if source_revision is not None and not isinstance(source_revision, str):
        errors.append("RECEIPT_SOURCE_REVISION_INVALID")

    supplied_id = receipt.get("receipt_id")
    if not isinstance(supplied_id, str) or not _SHA256_RE.fullmatch(supplied_id):
        errors.append("RECEIPT_ID_FORMAT_INVALID")
    try:
        expected = receipt_id(receipt)
    except (TypeError, ValueError):
        errors.append("RECEIPT_CANONICALIZATION_FAILED")
    else:
        if supplied_id != expected:
            errors.append("RECEIPT_ID_MISMATCH")

    classification: Semantics | None = None
    try:
        classification = Semantics(str(receipt.get("classification")))
    except ValueError:
        errors.append("RECEIPT_CLASSIFICATION_INVALID")

    expected_claimable = {
        Semantics.EXPLICIT_W0: ["W0"],
        Semantics.EXPLICIT_W1: ["W1"],
        Semantics.LEGACY_PRE_GATE_W1: ["LEGACY_PRE_GATE_W1"],
        Semantics.COUPLED_WEED: [],
        Semantics.AMBIGUOUS: [],
    }
    if classification is not None:
        if receipt.get("claimable_semantics") != expected_claimable[classification]:
            errors.append("RECEIPT_CLAIMABLE_SEMANTICS_INCONSISTENT")
        if receipt.get("promotion_eligible_as_w0") is not (
            classification == Semantics.EXPLICIT_W0
        ):
            errors.append("RECEIPT_PROMOTION_ELIGIBILITY_INCONSISTENT")

    reasons = receipt.get("reason_codes")
    if not (
        isinstance(reasons, list)
        and reasons
        and all(isinstance(item, str) and item for item in reasons)
    ):
        errors.append("RECEIPT_REASON_CODES_INVALID")

    artifacts = receipt.get("artifacts")
    required_roles = {
        "spatial_source",
        "runtime_source",
        "entrypoint_source",
        "runtime_config",
    }
    if not isinstance(artifacts, Mapping) or set(artifacts) != required_roles:
        errors.append("RECEIPT_ARTIFACT_SET_INVALID")
    else:
        for role in sorted(required_roles):
            row = artifacts.get(role)
            if not isinstance(row, Mapping):
                errors.append(f"RECEIPT_ARTIFACT_{role.upper()}_INVALID")
                continue
            if row.get("role") != role:
                errors.append(f"RECEIPT_ARTIFACT_{role.upper()}_ROLE_MISMATCH")
            if not isinstance(row.get("path"), str) or not row.get("path"):
                errors.append(f"RECEIPT_ARTIFACT_{role.upper()}_PATH_INVALID")
            size = row.get("bytes")
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                errors.append(f"RECEIPT_ARTIFACT_{role.upper()}_SIZE_INVALID")
            sha256 = row.get("sha256")
            if not isinstance(sha256, str) or not _SHA256_RE.fullmatch(sha256):
                errors.append(f"RECEIPT_ARTIFACT_{role.upper()}_SHA256_INVALID")
            git_sha1 = row.get("git_blob_sha1")
            if not isinstance(git_sha1, str) or not _GIT_SHA1_RE.fullmatch(git_sha1):
                errors.append(f"RECEIPT_ARTIFACT_{role.upper()}_GIT_SHA1_INVALID")

    analysis = receipt.get("analysis")
    if not isinstance(analysis, Mapping) or set(analysis) != {
        "spatial",
        "runtime",
        "entrypoint",
        "config",
    }:
        errors.append("RECEIPT_ANALYSIS_SET_INVALID")
    return sorted(set(errors))


def _artifact_label(receipt: Mapping[str, Any], role: str, fallback: str) -> str:
    artifacts = receipt.get("artifacts")
    if isinstance(artifacts, Mapping):
        row = artifacts.get(role)
        if isinstance(row, Mapping) and isinstance(row.get("path"), str):
            return str(row["path"])
    return fallback


def verify_receipt_against_bytes(
    receipt: Mapping[str, Any],
    spatial_source: bytes,
    runtime_source: bytes,
    config_source: bytes,
    *,
    entrypoint_source: bytes,
    source_revision: str,
) -> list[str]:
    """Re-run the analyzer over exact bytes before a promotion decision."""

    errors = _validate_receipt_integrity(receipt)
    if receipt.get("source_revision") != source_revision:
        errors.append("RECEIPT_SOURCE_REVISION_MISMATCH")
    expected = certify_bytes(
        spatial_source,
        runtime_source,
        config_source,
        entrypoint_source=entrypoint_source,
        spatial_path=_artifact_label(receipt, "spatial_source", "spatial_tempo.py"),
        runtime_path=_artifact_label(receipt, "runtime_source", "titan_runtime.py"),
        entrypoint_path=_artifact_label(receipt, "entrypoint_source", "main.py"),
        config_path=_artifact_label(receipt, "runtime_config", "TITAN-CONFIG.json"),
        source_revision=source_revision,
    )
    try:
        if canonical_json(_receipt_core(receipt)) != canonical_json(_receipt_core(expected)):
            errors.append("RECEIPT_EXACT_REANALYSIS_MISMATCH")
    except (TypeError, ValueError):
        errors.append("RECEIPT_CANONICALIZATION_FAILED")
    return sorted(set(errors))


def verify_receipt_against_paths(
    receipt: Mapping[str, Any],
    spatial_path: Path,
    runtime_path: Path,
    config_path: Path,
    *,
    entrypoint_path: Path,
    source_revision: str,
) -> list[str]:
    return verify_receipt_against_bytes(
        receipt,
        spatial_path.read_bytes(),
        runtime_path.read_bytes(),
        config_path.read_bytes(),
        entrypoint_source=entrypoint_path.read_bytes(),
        source_revision=source_revision,
    )
