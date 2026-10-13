#!/usr/bin/env python3
"""V2 file-backed acceptance root for the INPRS CLM migration handoff.

V2 closes the historical-version trust gap found in the recovered v1 carrier:
each historical revision is rooted by the independently pinned manifest as an
exact (revision, path, sha256) tuple before the reviewed v1 byte/semantic gate
is allowed to run. The retained v1 engine remains private compatibility code;
this module is the canonical public acceptance entry point.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from typing import Any

_LEGACY_PATH = Path(__file__).with_name("_file_backed_acceptance_v1.py")
_spec = importlib.util.spec_from_file_location("inprs_file_backed_acceptance_v1", _LEGACY_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError("unable to load retained v1 acceptance engine")
_legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy)

SCHEMA_VERSION = 2
OPPORTUNITY_ID = _legacy.OPPORTUNITY_ID
SOURCE_SYSTEM = _legacy.SOURCE_SYSTEM
MAX_MANIFEST_BYTES = _legacy.MAX_MANIFEST_BYTES
MAX_BUNDLE_BYTES = _legacy.MAX_BUNDLE_BYTES
MAX_VERSIONS_PER_CONTRACT = _legacy.MAX_VERSIONS_PER_CONTRACT
AcceptanceError = _legacy.AcceptanceError
canonical_manifest_bytes = _legacy.canonical_manifest_bytes
canonical_receipt_bytes = _legacy.canonical_receipt_bytes
source_record_digest = _legacy.source_record_digest
_sha = _legacy._sha
_is_sha = _legacy._is_sha

_CONTRACT_KEYS_V2 = {
    "legacy_id", "source_path", "source_sha256", "source_size_bytes", "source_record_sha256",
    "target_path", "version_paths", "version_roots", "public_action", "public_path",
    "redaction_attestation_path",
}
_VERSION_ROOT_KEYS = {"revision", "path", "sha256"}


def _v2_failure(errors: list[str], *, manifest_sha: str | None = None) -> dict[str, Any]:
    receipt = _legacy._failure(errors, manifest_sha=manifest_sha)
    receipt["schema_version"] = SCHEMA_VERSION
    receipt["trust_schema"] = "inprs-file-backed-acceptance/v2"
    receipt["version_bytes_verified"] = 0
    receipt["version_roots_verified"] = 0
    return receipt


def _load_bundle_no_duplicates(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, [f"BUNDLE_READ_FAILED:{exc.__class__.__name__}"]
    if len(raw) > MAX_BUNDLE_BYTES:
        return None, [f"BUNDLE_TOO_LARGE:{len(raw)}"]

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise AcceptanceError(f"BUNDLE_DUPLICATE_KEY:{key}")
            out[key] = value
        return out

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=hook)
    except AcceptanceError as exc:
        return None, [str(exc)]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, [f"BUNDLE_JSON_INVALID:{exc.__class__.__name__}"]
    if not isinstance(value, dict):
        return None, ["BUNDLE_ROOT_INVALID"]
    return value, []


def _validate_version_roots(
    manifest: dict[str, Any], bundle: dict[str, Any] | None, root: Path
) -> tuple[list[str], int, int]:
    errors: list[str] = []
    version_bytes_verified = 0
    version_roots_verified = 0
    rows = manifest.get("contracts")
    if not isinstance(rows, list):
        return ["MANIFEST_CONTRACTS_INVALID"], 0, 0
    bundle_rows = bundle.get("contracts") if isinstance(bundle, dict) else None
    bundle_contracts = {
        row.get("legacy_id"): row
        for row in bundle_rows
        if isinstance(bundle_rows, list) and isinstance(row, dict) and isinstance(row.get("legacy_id"), str)
    } if isinstance(bundle_rows, list) else {}

    for idx, row in enumerate(rows):
        label = f"contract-{idx}"
        errors.extend(_legacy._strict_keys(row, _CONTRACT_KEYS_V2, f"MANIFEST_CONTRACT:{label}"))
        if not isinstance(row, dict):
            continue
        cid = row.get("legacy_id")
        if not isinstance(cid, str) or not cid:
            errors.append(f"MANIFEST_CONTRACT_ID_INVALID:{label}")
            continue
        version_paths = row.get("version_paths")
        version_roots = row.get("version_roots")
        if (
            not isinstance(version_roots, list)
            or not version_roots
            or len(version_roots) > MAX_VERSIONS_PER_CONTRACT
        ):
            errors.append(f"VERSION_ROOTS_INVALID:{cid}")
            continue
        expected_paths: list[str] = []
        candidate = bundle_contracts.get(cid)
        history = candidate.get("version_history") if isinstance(candidate, dict) else None
        if not isinstance(history, list):
            history = []
        if len(history) != len(version_roots):
            errors.append(f"VERSION_ROOT_CANDIDATE_COUNT_MISMATCH:{cid}")

        for pos, version_root in enumerate(version_roots, start=1):
            errors.extend(_legacy._strict_keys(version_root, _VERSION_ROOT_KEYS, f"VERSION_ROOT:{cid}:{pos}"))
            if not isinstance(version_root, dict):
                continue
            revision = version_root.get("revision")
            path = version_root.get("path")
            digest = version_root.get("sha256")
            if revision != pos or isinstance(revision, bool):
                errors.append(f"VERSION_ROOT_REVISION_INVALID:{cid}:{pos}")
            rel, path_errors = _legacy._relative_path(path, "target", f"{cid}:version-root:{pos}")
            errors.extend(path_errors)
            if rel is not None:
                expected_paths.append(rel)
            if not _is_sha(digest):
                errors.append(f"VERSION_ROOT_HASH_INVALID:{cid}:{pos}")
            if pos <= len(history) and isinstance(history[pos - 1], dict):
                candidate_revision = history[pos - 1].get("revision")
                candidate_digest = history[pos - 1].get("sha256")
                if candidate_revision != revision:
                    errors.append(f"VERSION_ROOT_CANDIDATE_REVISION_MISMATCH:{cid}:{pos}")
                if candidate_digest != digest:
                    errors.append(f"VERSION_ROOT_CANDIDATE_HASH_MISMATCH:{cid}:{pos}")
            elif pos <= len(history):
                errors.append(f"VERSION_ROOT_CANDIDATE_ENTRY_INVALID:{cid}:{pos}")

            if rel is not None:
                data, file_errors = _legacy._read_bound_file(root, rel, f"{cid}:version-root:{pos}")
                errors.extend(file_errors)
                if data is not None:
                    version_bytes_verified += len(data)
                    if _sha(data) != digest:
                        errors.append(f"VERSION_ROOT_FILE_HASH_MISMATCH:{cid}:{pos}")
                    else:
                        version_roots_verified += 1

        if version_paths != expected_paths:
            errors.append(f"VERSION_ROOT_PATH_SEQUENCE_MISMATCH:{cid}")
        if version_roots and isinstance(version_roots[-1], dict):
            if version_roots[-1].get("sha256") != row.get("source_sha256"):
                errors.append(f"VERSION_ROOT_FINAL_SOURCE_MISMATCH:{cid}")
    return errors, version_bytes_verified, version_roots_verified


def _legacy_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    downgraded = copy.deepcopy(manifest)
    downgraded["schema_version"] = 1
    rows = downgraded.get("contracts")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                row.pop("version_roots", None)
    return downgraded


def verify_handoff(
    manifest_path: Path,
    expected_manifest_sha256: str,
    bundle_path: Path,
    root: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    if not _is_sha(expected_manifest_sha256):
        errors.append("MANIFEST_PIN_INVALID")
    try:
        manifest, manifest_raw = _legacy._load_canonical_json(
            manifest_path, MAX_MANIFEST_BYTES, label="MANIFEST"
        )
    except AcceptanceError as exc:
        return _v2_failure([str(exc)])
    manifest_sha = _sha(manifest_raw)
    if _is_sha(expected_manifest_sha256) and manifest_sha != expected_manifest_sha256:
        errors.append(f"MANIFEST_PIN_MISMATCH:{manifest_sha}")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append("MANIFEST_SCHEMA_INVALID")

    bundle, bundle_errors = _load_bundle_no_duplicates(bundle_path)
    errors.extend(bundle_errors)
    # Freeze the duplicate-checked semantic generation before any path-backed
    # validation. Delegated v1 must consume these exact semantics rather than
    # reopening a caller-controlled bundle pathname after v2 root validation.
    bundle_snapshot = _legacy._canon(bundle) if isinstance(bundle, dict) else b"{}"
    root_errors, version_bytes, version_count = _validate_version_roots(manifest, bundle, root)
    errors.extend(root_errors)

    legacy_manifest = _legacy_manifest(manifest)
    legacy_raw = canonical_manifest_bytes(legacy_manifest)
    with tempfile.TemporaryDirectory(prefix="inprs-accept-v2-") as tmp:
        legacy_path = Path(tmp) / "manifest-v1.json"
        legacy_bundle_path = Path(tmp) / "candidate-bundle-v1.json"
        legacy_path.write_bytes(legacy_raw)
        legacy_bundle_path.write_bytes(bundle_snapshot)
        legacy_receipt = _legacy.verify_handoff(
            legacy_path, _sha(legacy_raw), legacy_bundle_path, root
        )

    errors.extend(str(item) for item in legacy_receipt.get("errors", []))
    receipt = dict(legacy_receipt)
    receipt["accepted"] = not errors
    receipt["errors"] = sorted(set(errors))
    receipt["manifest_sha256"] = manifest_sha
    receipt["schema_version"] = SCHEMA_VERSION
    receipt["trust_schema"] = "inprs-file-backed-acceptance/v2"
    receipt["version_bytes_verified"] = version_bytes
    receipt["version_roots_verified"] = version_count
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args(argv)
    receipt = verify_handoff(args.manifest, args.manifest_sha256, args.bundle, args.root)
    print(canonical_receipt_bytes(receipt).decode("utf-8"), end="")
    return 0 if receipt["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
